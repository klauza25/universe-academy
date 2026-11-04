"""Écriture comptable : le seul chemin qui touche l'argent d'une caisse.

Trois lois y vivent, et nulle part ailleurs : une écriture validée ne met
jamais un compte à découvert, ne se date pas après le jour de la saisie, et ne
s'écrit pas sur une période déjà clôturée — sauf régularisation assumée.
L'écran de caisse, la grille d'encaissement et les ajustements passent tous par
ici ; le modèle refuse en bonus, à l'enregistrement, tout mouvement qui creuserait
un trou, de sorte qu'une reprise en masse ou un script ne passe pas devant la
garde. `juger` est public pour la même raison : le formulaire montre le verdict
du service au lieu de le recalculer.

Le verrou de caisse (`_verrouiller`) est écrit pour PostgreSQL. Sur SQLite,
Django ignore `select_for_update` sans erreur : c'est la transaction qui fait
foi, et deux sorties concurrentes ne peuvent pas dépenser le même solde — la
seconde échoue au lieu de passer en doublon.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import (AuditLog, CashAccount, CashClosure, CashTransaction,
                     TransactionCategory)

CATEGORIE_AJUSTEMENT = 'Ajustements de solde'  # i18n-exempt: nom stocké en base, clé de get_or_create
LIMITE_ALERTE = 80  # part du disponible consommée par une sortie déclenchant un avertissement, en %


def _tracer(requete, action, entity_id, before=None, after=None, agent=None):
    """Une ligne d'audit, que l'appelant vienne d'un écran ou d'une commande."""
    acteur = agent
    utilisateur = getattr(requete, 'user', None) if requete else None
    if utilisateur is not None and utilisateur.is_authenticated:
        acteur = utilisateur
    AuditLog.objects.create(
        actor=acteur, action=action, entity_type='CashTransaction',
        entity_id=str(entity_id), before_summary=before, after_summary=after,
        ip_address=requete.META.get('REMOTE_ADDR') if requete else None,
    )


def _verrouiller(caisse):
    """Relit la caisse sous verrou : contrôle et écriture voient le même solde."""
    return CashAccount.objects.select_for_update().get(pk=caisse.pk)


def _chiffre(valeur):
    return f'{valeur:,}'.replace(',', ' ')


def juger(caisse, *, sortie, survenu=None, nature=None, ignorees=()):
    """Les refus d'une écriture, avant qu'elle ne touche la base.

    Une écriture qui ne débite pas — une recette, un brouillon — ne peut pas
    creuser un trou : elle doit passer, même sur un compte encore en difficulté
    qu'elle contribue à combler.

    Le formulaire de caisse appelle ici plutôt que de recalculer le solde :
    l'écran et le service rendent le même verdict, au même mot près.
    """
    if not caisse.writable:
        raise ValidationError(_("« %(caisse)s » est archivé : plus aucune écriture ne l'atteint.")
                              % {'caisse': caisse.name}, code='compte_archive')
    jour = survenu.date() if survenu else timezone.localdate()
    if jour > timezone.localdate():
        raise ValidationError(_("Une écriture de caisse ne se date pas après aujourd'hui (%(jour)s).")
                              % {'jour': timezone.localdate().strftime('%d/%m/%Y')},
                              code='date_future')
    reguliere = nature in (None, CashTransaction.Nature.NORMAL)
    cloture = CashClosure.objects.filter(
        account=caisse, date__gte=jour).order_by('date').first()
    if cloture and sortie and reguliere:
        raise ValidationError(_("« %(caisse)s » est clôturée au %(date)s : régularisez par une écriture d'ajustement, pas par une écriture ordinaire antidatée.")
                              % {'caisse': caisse.name,
                                 'date': cloture.date.strftime('%d/%m/%Y')},
                              code='periode_cloturee')
    if not sortie:
        return
    creux = caisse.decouvert(debited=sortie, ignored=ignorees)
    if creux:
        raise ValidationError(_("Solde insuffisant sur « %(caisse)s » : il manque %(manque)s %(devise)s (découvert autorisé : %(plafond)s).")
                              % {'caisse': caisse.name, 'manque': _chiffre(creux),
                                 'devise': caisse.currency,
                                 'plafond': _chiffre(caisse.overdraft_limit)},
                              code='solde_insuffisant')


def sortie_prevue(*, sens, montant, statut=None):
    """Ce qu'une écriture en projet débite de sa caisse — la règle de `poster`.

    L'écran de saisie doit annoncer le même chiffre que l'enregistrement : une
    recette et un brouillon ne déboursent rien, une sortie validée débite le
    montant entier. Calculé ici, une seule fois, plutôt que ressassé par le
    formulaire, la vue et le service.
    """
    statut = statut or CashTransaction.Status.VALIDATED
    if sens == CashTransaction.Type.IN:
        return 0
    return montant if statut == CashTransaction.Status.VALIDATED else 0


def avertissement(caisse, *, sortie):
    """Ce que l'écran montre avant validation, ou rien si la sortie est banale.

    Au-delà du disponible, ce n'est plus un avertissement mais un refus, et c'est
    `juger` qui le dit, montant manquant à l'appui — l'écran ne tient pas deux
    discours sur le même argent. Une caisse vide se signale à l'écran, badge par
    badge : « Solde épuisé » sur la liste des comptes, « Aucun fonds disponible »
    au moment de choisir où payer.
    """
    disponible = caisse.disponible()
    if not sortie or sortie > disponible:
        return None
    if sortie * 100 >= disponible * LIMITE_ALERTE:
        return _("Cette sortie consomme %(pourcent)s %% du solde disponible de « %(caisse)s » (%(disponible)s %(devise)s).") % {
            'pourcent': round(sortie * 100 / disponible), 'caisse': caisse.name,
            'disponible': _chiffre(disponible), 'devise': caisse.currency}
    return None


@transaction.atomic
def poster(*, caisse, montant, sens, libelle, categorie=None, description='',
           methode=None, contrepartie='', piece=None, note='', statut=None,
           survenu=None, destination=None, nature=None, remplace=None,
           requete=None, agent=None):
    """Écrit une opération de caisse après l'avoir jugée.

    `sens` vaut `in`, `out` ou `transfer`, et `transfer` exige `destination`.
    Un brouillon se pose sans rien débourser : il ne compte pas en caisse, et
    se verra refuser la validation si la trésorerie n'y suffit pas.
    """
    caisse = _verrouiller(caisse)
    statut = statut or CashTransaction.Status.VALIDATED
    nature = nature or CashTransaction.Nature.NORMAL
    sortie = sortie_prevue(sens=sens, montant=montant, statut=statut)
    if sens == CashTransaction.Type.TRANSFER:
        if not destination:
            raise ValidationError(_("Un transfert doit désigner le compte destinataire."))
        if destination.pk == caisse.pk:
            raise ValidationError(_("Un transfert doit changer de compte."))
        destination = _verrouiller(destination)
    juger(caisse, sortie=sortie, survenu=survenu, nature=nature)
    if destination is not None:
        juger(destination, sortie=0, survenu=survenu, nature=nature)

    tx = CashTransaction(
        tx_type=sens, account=caisse, destination_account=destination,
        category=categorie, label=libelle, description=description,
        amount=montant, currency=caisse.currency,
        occurred_at=survenu or timezone.now(),
        method=methode or CashTransaction.Method.CASH,
        counterparty=contrepartie or '', receipt=piece or '',
        status=statut, nature=nature, replaces=remplace, note=note,
        created_by=agent or getattr(requete, 'user', None),
    )
    tx.save()
    _tracer(requete, 'CASH_TRANSACTION_CREATE', tx.pk,
            after={'reference': tx.reference, 'type': tx.tx_type,
                   'amount': tx.amount, 'account': caisse.name,
                   'status': tx.status, 'nature': tx.nature}, agent=agent)
    return tx


@transaction.atomic
def annuler(tx, *, motif, requete=None, agent=None):
    """Annule une écriture validée — sauf si elle finance ce qui est déjà sorti.

    Retirer une recette déjà dépensée creuserait un trou : la régularisation
    passe alors par une écriture contraire, pas par l'effacement de la recette.
    """
    if not motif:
        raise ValidationError(_("Un motif est obligatoire pour annuler."))
    if tx.status == CashTransaction.Status.CANCELLED:
        return None
    comptes = [_verrouiller(tx.account)]
    if tx.destination_account_id:
        comptes.append(_verrouiller(tx.destination_account))
    # L'écriture disparaît du calcul, et le `ignored` l'en retire déjà : ce qui
    # reste doit rester à flot. Une sortie annulée rend de l'argent et ne peut
    # pas créer de trou ; une recette ou un transfert entrant, si.
    for compte in comptes:
        creux = compte.decouvert(ignored=[tx.pk])
        if creux:
            raise ValidationError(_("Annulation refusée : il manquerait %(creux)s %(devise)s sur « %(caisse)s ». Régularisez plutôt par une écriture contraire.")
                                  % {'creux': _chiffre(creux),
                                     'devise': compte.currency,
                                     'caisse': compte.name})
    avant = {'status': tx.status}
    tx.status = CashTransaction.Status.CANCELLED
    tx.note = ((tx.note + '\n') if tx.note else '') + \
        _('Annulation : %(motif)s') % {'motif': motif}
    tx.save(update_fields=['status', 'note', 'updated_at'])
    _tracer(requete, 'CASH_TRANSACTION_CANCEL', tx.pk, before=avant,
            after={'status': tx.status, 'reason': motif}, agent=agent)
    return tx


def categorie_ajustement(sens):
    """La catégorie qui porte les corrections, créée si la base ne la connaît pas."""
    return TransactionCategory.objects.get_or_create(
        name=CATEGORIE_AJUSTEMENT, direction=sens,
        defaults={'active': True})[0]


@transaction.atomic
def ajuster(caisse, *, montant, sens, motif, survenu=None, auteur=None, requete=None):
    """Ajustement de solde tracé : un solde ne se corrige jamais en silence.

    Positif, l'ajustement est une recette ; négatif, une sortie soumise à la
    même garde de solde qu'une dépense ordinaire. Le solde d'ouverture reste
    intact et l'écriture d'audit dit qui, quand et pourquoi.
    """
    if not motif:
        raise ValidationError(_("Un motif est obligatoire pour ajuster un solde."))
    if montant <= 0:
        raise ValidationError(_("Un ajustement porte un montant non nul."))
    return poster(caisse=caisse, montant=montant, sens=sens,
                  libelle=_("Ajustement de solde"),
                  categorie=categorie_ajustement(sens),
                  note=_("Ajustement %(signe)s %(montant)s demandé : %(motif)s") % {
                      'signe': '+' if sens == CashTransaction.Type.IN else '−',
                      'montant': _chiffre(montant), 'motif': motif},
                  nature=CashTransaction.Nature.ADJUSTMENT, survenu=survenu,
                  statut=CashTransaction.Status.VALIDATED,
                  agent=auteur, requete=requete)


@transaction.atomic
def reinitialiser(caisse, *, motif, confirme, survenu=None, auteur=None, requete=None):
    """Ramène une caisse à zéro par une écriture contraire, l'historique entier conservé.

    Retourne l'écriture et le nombre de brouillons encore en attente, que
    l'écran signale avant coup : une remise à zéro ne rapproche pas ce qui
    n'est pas saisi. `confirme` vient du second geste de l'appelant.
    """
    if not confirme:
        raise ValidationError(_("La réinitialisation d'une caisse demande une confirmation explicite."))
    if not motif:
        raise ValidationError(_("Un motif est obligatoire pour réinitialiser une caisse."))
    brouillons = CashTransaction.objects.filter(
        account=caisse, status=CashTransaction.Status.DRAFT).count()
    solde = _verrouiller(caisse).balance
    if solde == 0:
        return None, brouillons
    sens = CashTransaction.Type.OUT if solde > 0 else CashTransaction.Type.IN
    tx = poster(caisse=caisse, montant=abs(solde), sens=sens,
                libelle=_("Réinitialisation de la caisse"),
                categorie=categorie_ajustement(sens),
                note=_("Réinitialisation du %(jour)s (solde de %(solde)s emporté) : %(motif)s") % {
                    'jour': timezone.localdate().strftime('%d/%m/%Y'),
                    'solde': _chiffre(solde), 'motif': motif},
                nature=CashTransaction.Nature.RESET, survenu=survenu,
                statut=CashTransaction.Status.VALIDATED, agent=auteur,
                requete=requete)
    return tx, brouillons


@transaction.atomic
def corriger(tx, *, montant=None, categorie=None, libelle=None, survenu=None,
             motif, requete=None, agent=None):
    """Corrige une écriture enregistrée sans jamais la faire disparaître.

    Le solde projeté exclut la ligne telle qu'elle est en base : augmenter une
    sortie ne doit pas la compter deux fois. Changer de compte ne se fait pas
    ici — une écriture mal affectée s'annule et se ressaisit sur la bonne
    caisse, les deux lignes restant visibles et reliées.
    """
    if not motif:
        raise ValidationError(_("Un motif est obligatoire pour corriger une écriture."))
    _verrouiller(tx.account)
    avant = {'amount': tx.amount, 'type': tx.tx_type,
             'category': tx.category.name if tx.category else None,
             'occurred_at': tx.occurred_at.isoformat()}
    nouveau_montant = montant or tx.amount
    entree = nouveau_montant if tx.tx_type == CashTransaction.Type.IN else 0
    sortie = (nouveau_montant - entree) if tx.status == CashTransaction.Status.VALIDATED else 0
    juger(tx.account, sortie=sortie, survenu=survenu or tx.occurred_at,
          nature=CashTransaction.Nature.NORMAL, ignorees=[tx.pk])
    tx.amount = nouveau_montant
    if categorie is not None:
        tx.category = categorie
    if libelle:
        tx.label = libelle
    if survenu:
        tx.occurred_at = survenu
    tx.note = ((tx.note + '\n') if tx.note else '') + \
        _('Correction du %(jour)s : %(motif)s') % {
            'jour': timezone.localdate().strftime('%d/%m/%Y'), 'motif': motif}
    tx.save()
    _tracer(requete, 'CASH_TRANSACTION_EDIT', tx.pk, before=avant,
            after={'amount': tx.amount,
                   'category': tx.category.name if tx.category else None,
                   'motif': motif}, agent=agent)
    return tx
