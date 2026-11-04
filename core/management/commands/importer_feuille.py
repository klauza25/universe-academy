"""Importer le journal de caisse « Contrôles Mensuels » dans les écritures de l'app.

    python manage.py importer_feuille                     # aperçu, rien n'est écrit
    python manage.py importer_feuille --details 40        # plus de lignes detaillees
    python manage.py importer_feuille --ecrire            # après copie de db.sqlite3 dans backups/

Sans ``--ecrire``, la commande se contente de dire ce qui manque. Les lignes déjà
posées par l'import des classeurs ne sont jamais rejouees : elles portent une autre
marque et le rapprochement se fait par dossier, montant et mois solde.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core import feuille_import
from core.models import (CashAccount, CashTransaction, Payment, TransactionCategory,
                         User)

DEFAULT_CLASSEUR = 'feuille_source.xlsx'
MIDI = dt.time(12, 0)


class Command(BaseCommand):
    help = 'Importer le journal de caisse de la feuille dans les écritures de l’application.'

    def add_arguments(self, parser):
        parser.add_argument('--classeur', default=DEFAULT_CLASSEUR,
                            help='Nom du fichier dans docs/donnees')
        parser.add_argument('--agent', default='secretaire@univers.academy',
                            help='Compte rattache aux ecritures')
        parser.add_argument('--caisse', default='Caisse principale',
                            help='Nom de la caisse de destination')
        parser.add_argument('--details', type=int, default=14,
                            help='Nombre de lignes detaillees affichees')
        parser.add_argument('--ecrire', action='store_true',
                            help='Ecrire en base (sans cette option, simple preview)')

    def handle(self, *args, **options):
        chemin = Path('docs/donnees') / options['classeur']
        if not chemin.exists():
            raise CommandError(f'classeur introuvable : {chemin}')
        lignes = feuille_import.lire(chemin)
        plan = feuille_import.reconcilier(lignes)
        feuille_import.decrire(plan, self.stdout, self.style)
        self.stdout.write(f'\n{len(lignes)} ligne(s) lue(s) dans {chemin.name}.')
        if not options['ecrire']:
            self.stdout.write(self.style.WARNING(
                'Prévisualisation : rien n’a été écrit. Sauvegardez db.sqlite3 dans '
                'backups/, puis relancez avec --ecrire.'))
            return
        self._ecrire(plan, options)

    # ------------------------------------------------------------------
    def _ecrire(self, plan, options) -> None:
        agent = User.objects.filter(email=options['agent']).first()
        caisse = CashAccount.objects.filter(name=options['caisse']).first()
        if not caisse:
            raise CommandError(f'caisse introuvable : {options["caisse"]}')
        categories = {t.name: t for t in TransactionCategory.objects.all()}
        # Le lot entier se juge avant d'écrire : une caisse qui finirait sous
        # zéro-signale un mauvais choix de caisse, et l'import n'invente pas de
        # recette pour le boucher.
        solde_apres = feuille_import.solde_apres_ecriture(caisse, plan)
        if solde_apres < 0:
            raise CommandError(
                f'écriture refusée : « {caisse.name} » finirait à '
                f'{self._fcfa(solde_apres)} après '
                f'{self._fcfa(plan.montant_sorties)} de sorties pour '
                f'{self._fcfa(plan.montant_recettes)} d’entrées. Choisissez la '
                'caisse réellement débitée (--caisse) ou enregistrez d’abord la '
                'recette qui alimente ce portefeuille.')
        ecrits = {'paiements': 0, 'caisse': 0, 'montant': 0, 'sorties': 0, 'periodes': 0}
        with transaction.atomic():
            for dossier, ligne, periode in plan.paiements:
                self._paiement(dossier, ligne, periode, agent, caisse,
                               categories[ligne.categorie], ecrits)
            for nom_categorie, ligne, ___ in plan.operations:
                self._operation(nom_categorie, ligne, agent, caisse,
                                categories[nom_categorie], ecrits)
            for pk_paiement, annee, mois in plan.periodes:
                Payment.objects.filter(pk=pk_paiement).update(period_year=annee,
                                                              period_month=mois)
                ecrits['periodes'] += 1
        self.stdout.write(self.style.SUCCESS(
            f'Écrit : {ecrits["paiements"]} paiement(s) étudiant(s), '
            f'{ecrits["caisse"]} entrée(s) et {ecrits["sorties"]} sortie(s) de caisse, '
            f'{ecrits["periodes"]} mois complété(s) — '
            f'{self._fcfa(ecrits["montant"])}.'))

    def _instant(self, ligne):
        jour = (ligne.date.date() if ligne.date else timezone.localdate())
        return timezone.make_aware(dt.datetime.combine(jour, MIDI))

    def _paiement(self, dossier, ligne, periode, agent, caisse, categorie, ecrits) -> None:
        instants = self._instant(ligne)
        paye = Payment.objects.create(
            enrollment=dossier, amount=ligne.montant, method=Payment.Method.CASH,
            status=Payment.Status.COMPLETED, paid_at=instants, recorded_by=agent,
            motif=ligne.motif, period_year=periode[0] if periode else None,
            period_month=periode[1] if periode else None,
            note=(f"{feuille_import.MARQUE_FEUILLE} : ligne {ligne.rang}"
                  + (f' | {ligne.commentaire}' if ligne.commentaire else '')),
        )
        cash = CashTransaction.objects.create(
            tx_type=CashTransaction.Type.IN, category=categorie,
            label=f'{ligne.libelle} {dossier.student.display_label}',
            description=(f'{dossier.session.course.title} — '
                         f'{feuille_import.MARQUE_FEUILLE} : ligne {ligne.rang}'),
            amount=ligne.montant, currency='XAF', occurred_at=instants, account=caisse,
            method=Payment.Method.CASH, counterparty=dossier.student.display_label,
            status=CashTransaction.Status.VALIDATED, created_by=agent,
            note=f'{feuille_import.MARQUE_FEUILLE} : ligne {ligne.rang}',
        )
        paye.transaction = cash
        paye.save(update_fields=['transaction'])
        ecrits['paiements'] += 1
        ecrits['caisse'] += 1
        ecrits['montant'] += ligne.montant

    def _operation(self, nom_categorie, ligne, agent, caisse, categorie, ecrits) -> None:
        instants = self._instant(ligne)
        sens = (CashTransaction.Type.OUT if ligne.genre == 'depense'
                else CashTransaction.Type.IN)
        label = ' — '.join(v for v in (ligne.libelle, ligne.intitule) if v) or nom_categorie
        CashTransaction.objects.create(
            tx_type=sens, category=categorie, label=label[:200],
            description=f'{feuille_import.MARQUE_FEUILLE} : ligne {ligne.rang}'
                        + (f' | {ligne.commentaire}' if ligne.commentaire else ''),
            amount=ligne.montant, currency='XAF', occurred_at=instants, account=caisse,
            method=Payment.Method.CASH, counterparty=ligne.nom[:200],
            status=CashTransaction.Status.VALIDATED, created_by=agent,
            note=f'{feuille_import.MARQUE_FEUILLE} : ligne {ligne.rang}',
        )
        ecrits['caisse' if sens == CashTransaction.Type.IN else 'sorties'] += 1
        ecrits['montant'] += ligne.montant

    @staticmethod
    def _fcfa(montant: int) -> str:
        return f'{montant:,} FCFA'.replace(',', ' ')
