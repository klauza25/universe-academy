"""Import du journal de caisse « Contrôles Mensuels (Brazzaville) » dans les écritures.

Le journal est la source de vérité de la caisse : tout ce qui entre et tout ce qui
sort. La base ne tenait que les paiements d'étudiants repris des classeurs
d'inscription. Ce module rapproche les deux et prépare les écritures manquantes.

Les lignes de scolarité (frais mensuel, inscription) visent un dossier étudiant :
sans dossier reconnaissable, elles restent signalées et ne sont pas écrites. Les
autres recettes et toutes les sorties deviennent de simples opérations de caisse.

`MARQUE_FEUILLE` distingue ces écritures de celles des classeurs : un rapprochement
ne rejoue jamais une ligne déjà posée.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field

from core.models import (CashTransaction, Course, Enrollment, Payment,
                         TransactionCategory, User)

MARQUE_FEUILLE = "d'après le journal de caisse"
ONGLET = 'Enregistrement_Opérations'
PREMIERE_LIGNE = 5

# Libellés de scolarité : le motif de paiement étudiant visé.
SCOLARITE = {'frais mensuel': Payment.Motif.MONTHLY, 'inscription': Payment.Motif.ENROLLMENT}
# Recettes encaissées sans dossier étudiant.
RECETTES = 'Autres recettes'
BOURSE = 'Subventions et dons'
# Motifs du journal -> catégorie comptable, dans l'ordre de priorité.
CATEGORIES_DEPENSES = [
    (('salaire du personnel', 'salaires'), 'Salaires'),
    (('avance sur salaire', 'avance'), 'Avances sur salaire'),
    (('formateur',), 'Paiements des formateurs'),
    (('loyer', 'internet', 'publicite', 'electricite', 'eau', 'telephone'), 'Charges de fonctionnement'),
    (('fourniture', 'consommable', 'impression', 'livre', 'certificat', 'fiche'), 'Fournitures et consommables'),
    (('transport', 'carburant', 'taxi', 'deplacement', 'italie', 'maroc', 'etude a l etranger'), 'Déplacements et missions'),
    (('honoraire', 'traduction', 'accompagnement', 'notaire', 'bank', 'frais bancaires'), 'Dépenses administratives'),
    (('entretien', 'nettoyage'), 'Entretien des locaux'),
    (('maintenance', 'reparation'), 'Maintenance informatique'),
    (('ordinateur', 'imprimante', 'materiel', 'achat'), 'Achat de matériel informatique'),
]
# Le journal ecrit les mois en francais : la table de conversion est une donnee
# du classeur, pas un libelle d'interface (les messages English suivent leur camp).
MOIS_FR = {
    1: 'janvier', 2: 'fevrier', 3: 'mars', 4: 'avril', 5: 'mai', 6: 'juin',
    7: 'juillet', 8: 'aout', 9: 'septembre', 10: 'octobre', 11: 'novembre',
    12: 'decembre',
}
MOIS_PAR_CLE = {motif: numero for numero, motif in MOIS_FR.items()}
MOIS_PAR_CLE['fev'] = 2
MOIS_PAR_CLE['sept'] = 9
# Abregements du journal pour une ligne du catalogue.
ALIAS_FORMATION = {
    'a administratif': 'Assistanat administratif',
    'a comptable': 'Assistanat comptable',
    'a ressources humaines': 'Assistanat ressources humaines',
    'fiscalite des entreprises': 'Fiscalité des entreprises',
    'espagnol': 'Espagnol A1',
    'francais': 'Francais A2',
    'excel avance': 'Excel avancé',
}


def normatif(valeur: object) -> str:
    texte = unicodedata.normalize('NFKD', str(valeur or ''))
    texte = ''.join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', texte.lower()).strip()


@dataclass
class Ligne:
    rang: int
    date: dt.datetime | None
    operation: str
    libelle: str
    intitule: str
    mois: str
    annee: int | None
    montant: int
    commentaire: str
    nom: str
    formation: str

    @property
    def genre(self) -> str:
        if self.operation == 'entree' and normatif(self.libelle) in SCOLARITE:
            return 'scolarite'
        return {'entree': 'recette', 'sortie': 'depense'}.get(self.operation, 'ignoree')

    @property
    def motif(self):
        return SCOLARITE.get(normatif(self.libelle))

    def cle_periode(self) -> tuple[int, int] | None:
        if self.genre != 'scolarite' or self.motif != Payment.Motif.MONTHLY:
            return None
        numero = MOIS_PAR_CLE.get(normatif(self.mois))
        if numero and self.annee:
            return int(self.annee), numero
        return None

    @property
    def categorie(self) -> str:
        if self.genre == 'depense':
            cible = f'{normatif(self.libelle)} {normatif(self.intitule)}'
            for motifs, nom in CATEGORIES_DEPENSES:
                # Une recherche en mot entier : « eau » ne doit pas lire « bureau ».
                if any(re.search(rf'\b{re.escape(m)}', cible) for m in motifs):
                    return nom
            return 'Autres dépenses'
        if self.genre == 'recette':
            return BOURSE if 'bourse' in normatif(self.libelle) else RECETTES
        return 'Paiements des étudiants'


def lire(classeur) -> list[Ligne]:
    import openpyxl
    feuilles = openpyxl.load_workbook(classeur, data_only=True)
    if ONGLET not in feuilles.sheetnames:
        raise ValueError(f"onglet {ONGLET} absent de {classeur}")
    lignes = []
    for rang, rude in enumerate(list(feuilles[ONGLET].values)[PREMIERE_LIGNE - 1:], PREMIERE_LIGNE):
        cells = list(rude) + [None] * 10
        date, operation, libelle, intitule, mois, annee, montant, commentaire, nom, formation = cells[:10]
        montant = int(float(montant)) if isinstance(montant, (int, float)) else 0
        if not montant:
            continue
        operation = normatif(operation)
        if not operation:
            # Le journal marque rarement l'operation : le libelle dit le sens.
            operation = 'sortie' if normatif(libelle) in ('charges', 'impression') else 'entree'
        lignes.append(Ligne(
            rang=rang, date=date if isinstance(date, dt.datetime) else None,
            operation=operation, libelle=str(libelle or '').strip(),
            intitule=str(intitule or '').strip(), mois=str(mois or '').strip(),
            annee=int(float(annee)) if isinstance(annee, (int, float)) else None,
            montant=montant, commentaire=str(commentaire or '').strip(),
            nom=str(nom or '').strip(), formation=str(formation or '').strip(),
        ))
    return lignes


@dataclass
class Plan:
    paiements: list = field(default_factory=list)
    operations: list = field(default_factory=list)
    deja_poses: list = field(default_factory=list)
    sans_dossier: list = field(default_factory=list)
    periodes: list = field(default_factory=list)
    ecarts: list = field(default_factory=list)

    @property
    def montant_paiements(self) -> int:
        return sum(ligne.montant for ___, ligne, ___ in self.paiements)

    @property
    def montant_operations(self) -> int:
        return sum(ligne.montant for ___, ligne, ___ in self.operations)

    @property
    def sorties(self) -> list:
        return [(c, l) for c, l, ___ in self.operations if l.genre == 'depense']

    @property
    def montant_recettes(self) -> int:
        return (self.montant_paiements
                + sum(ligne.montant for ___, ligne, ___ in self.operations
                      if ligne.genre != 'depense'))

    @property
    def montant_sorties(self) -> int:
        return sum(ligne.montant for ___, ligne, ___ in self.operations
                   if ligne.genre == 'depense')


def solde_apres_ecriture(caisse, plan: Plan) -> int:
    """Solde de la caisse une fois tout le lot posé.

    Le journal ne s'écrit pas sur une caisse qui n'a pas de quoi le supporter :
    une sortie sans recette correspondante est un mauvais choix de caisse, pas un
    découvert à inventer en base.
    """
    return caisse.balance_after(debited=plan.montant_sorties,
                                credited=plan.montant_recettes)


def _meme_epoque(paiement: Payment, ligne: Ligne) -> bool:
    """Le paiement et la ligne visent le meme moment d'encaissement.

    Le classeur pose le premier du mois, le journal marque le jour recu : la
    tolerance couvre un glissement de quelques mois, pas un changement d'annee.
    """
    if not ligne.date:
        return True
    écart = abs((paiement.paid_at.date() - ligne.date.date()).days)
    return écart <= 240


def _index_etudiants() -> tuple[dict, dict]:
    par_mot = defaultdict(list)
    for compte in User.objects.filter(roles__key='ETUDIANT').distinct():
        for mot in {*normatif(compte.first_name).split(), *normatif(compte.last_name).split()}:
            if len(mot) > 2:
                par_mot[mot].append(compte)
    titres = {}
    for cours in Course.objects.all():
        titres[normatif(cours.title)] = cours.title
    return par_mot, titres


def _compte_de(ligne: Ligne, par_mot: dict, titres: dict) -> tuple:
    """Le compte que la ligne designe, juge au nombre de jetons communs.

    Le journal abrege : « Misnelle », « AKABANKOU Naomie ». Un compte retient la
    ligne s'il partage le plus de jetons ; a egalite, la formation tranche, sinon
    la ligne est signalee plutot que raviee a un homonyme.
    """
    mots = [mot for mot in normatif(ligne.nom).split() if len(mot) > 2]
    if not mots:
        return None, 'nom illisible'
    scores: dict[int, int] = defaultdict(int)
    comptes = {}
    for mot in mots:
        for compte in par_mot.get(mot, ()):
            scores[compte.pk] += 1
            comptes[compte.pk] = compte
    if not scores:
        return None, 'aucun compte'
    meilleur = max(scores.values())
    meilleurs = [comptes[pk] for pk, score in scores.items() if score == meilleur]
    if len(meilleurs) == 1:
        return meilleurs[0], None
    if ligne.formation:
        titre = ALIAS_FORMATION.get(normatif(ligne.formation),
                                    titres.get(normatif(ligne.formation)))
        riches = [c for c in meilleurs
                  if Enrollment.objects.filter(student=c, session__course__title=titre).exists()]
        if len(riches) == 1:
            return riches[0], None
    return None, f'{len(meilleurs)} comptes à égalité'


def _dossier_de(compte: User, ligne: Ligne, titres: dict) -> tuple:
    titre = ALIAS_FORMATION.get(normatif(ligne.formation), titres.get(normatif(ligne.formation)))
    if ligne.formation and titre:
        dossier = Enrollment.objects.filter(student=compte, session__course__title=titre).first()
        if dossier:
            return dossier, None
    dossiers = list(Enrollment.objects.filter(student=compte).order_by('start_date'))
    if len(dossiers) == 1:
        return dossiers[0], ('formation differente',
                             f'{ligne.formation or "sans formation"} ≠ '
                             f'{dossiers[0].session.course.title}')
    if dossiers:
        return None, f'{len(dossiers)} dossiers pour ce compte'
    return None, 'aucun dossier inscrit'


def lignes_deja_ecrites() -> set[int]:
    """Les numeros de ligne du journal deja poses, payment ou operation de caisse.

    Chaque ecriture porte « d'apres le journal de caisse : ligne N ». Relancer la
    vague ne peut donc pas doubledire : la ligne est reconnue, pas devinee.
    """
    deja = set()
    notes = list(CashTransaction.objects.filter(note__contains='ligne ').values_list('note', flat=True))
    notes += list(Payment.objects.filter(note__contains='ligne ').values_list('note', flat=True))
    for note in notes:
        if not note.startswith(MARQUE_FEUILLE):
            continue
        chiffres = re.search(r'ligne (\d+)', note)
        if chiffres:
            deja.add(int(chiffres.group(1)))
    return deja


def reconcilier(lignes: list[Ligne]) -> Plan:
    """Ce que la base ignore encore du journal. Aucune écriture ici."""
    plan = Plan()
    mois_retenu = set()
    deja_ecrites = lignes_deja_ecrites()
    par_mot, titres = _index_etudiants()
    categories = set(TransactionCategory.objects.values_list('name', flat=True))

    for ligne in lignes:
        if ligne.rang in deja_ecrites:
            plan.deja_poses.append(ligne)
            continue
        genre = ligne.genre
        if genre == 'ignoree':
            plan.ecarts.append(('sans opération', ligne.rang, ligne.libelle or ligne.intitule))
            continue
        if ligne.categorie not in categories:
            plan.ecarts.append(('catégorie inconnue', ligne.rang, ligne.categorie))
            continue
        if genre != 'scolarite':
            plan.operations.append((ligne.categorie, ligne, None))
            continue
        compte, motif_rejet = _compte_de(ligne, par_mot, titres)
        if not compte:
            # L'argent est entre : la caisse le sait meme sans dossier etudiant.
            plan.sans_dossier.append(ligne)
            plan.operations.append((ligne.categorie, ligne, None))
            plan.ecarts.append((f'scolarité {motif_rejet}', ligne.rang, f'{ligne.nom} — {ligne.montant} F'))
            continue
        dossier, ecart = _dossier_de(compte, ligne, titres)
        if not dossier:
            plan.sans_dossier.append(ligne)
            plan.operations.append((ligne.categorie, ligne, None))
            plan.ecarts.append(('scolarité sans dossier', ligne.rang,
                                f'{ligne.nom} — {motif_rejet or "formation inconnue"}'))
            continue
        if ecart:
            plan.ecarts.append((ecart[0], ligne.rang, ecart[1]))
        periode = ligne.cle_periode()
        soldes = list(Payment.objects.filter(enrollment=dossier,
                                             status=Payment.Status.COMPLETED))
        if periode:
            # Un mois ne se solde qu'une fois : le paiement qui porte deja ce
            # mois fait foi, meme a un autre montant. Un tarif paye ne se
            # retouche pas, l'ecart est signale pour arbitrage.
            meme_mois = [p for p in soldes
                         if p.period_year == periode[0] and p.period_month == periode[1]]
            if meme_mois:
                plan.deja_poses.append(ligne)
                if meme_mois[0].amount != ligne.montant:
                    plan.ecarts.append(('mois déjà réglé à un autre montant', ligne.rang,
                                        f'{dossier.student.display_label} — {periode[1]}/{periode[0]} : '
                                        f'{meme_mois[0].amount:,} F posés pour '
                                        f'{ligne.montant:,} F au journal'.replace(',', ' ')))
                continue
            # Un paiement pose sans mois solde, du bon montant et du bon moment :
            # la colonne « Mois payé » vient le compléter plutot qu'un doublon.
            à_combler = [p for p in soldes
                         if p.motif == Payment.Motif.MONTHLY and p.period_month is None
                         and p.amount == ligne.montant and _meme_epoque(p, ligne)]
            if len(à_combler) == 1:
                plan.periodes.append((à_combler[0].pk, periode[0], periode[1]))
                plan.deja_poses.append(ligne)
                continue
        elif any(p.motif == ligne.motif and p.amount == ligne.montant
                 and _meme_epoque(p, ligne) for p in soldes):
            plan.deja_poses.append(ligne)
            continue
        cle_mois = (dossier.pk, *periode) if periode else None
        if cle_mois and cle_mois in mois_retenu:
            plan.deja_poses.append(ligne)
            plan.ecarts.append(('mois réglé deux fois au journal', ligne.rang,
                                f'{dossier.student.display_label} — {periode[1]}/{periode[0]} : '
                                f'{ligne.montant:,} F ignorés'.replace(',', ' ')))
            continue
        plan.paiements.append((dossier, ligne, periode))
        if cle_mois:
            mois_retenu.add(cle_mois)

    # Une sortie deja saisie dans l'application porte le meme montant et la meme date.
    joints = set(CashTransaction.objects.filter(tx_type=CashTransaction.Type.IN)
                 .exclude(student_payment__isnull=True)
                 .values_list('occurred_at__date', 'amount'))
    plan.operations = [(cat, ligne, None) for cat, ligne, ___ in plan.operations
                       if not (ligne.genre == 'recette' and ligne.date
                               and (ligne.date.date(), ligne.montant) in joints)]
    return plan


def decrire(plan: Plan, stdout, style) -> None:
    stdout.write(style.MIGRATE_HEADING('\n— Ce que le journal de caisse apporte à la base'))
    entrees = [x for x in plan.operations if x[1].genre != 'depense']
    sorties = plan.sorties
    stdout.write(f'  {len(plan.paiements)} paiement(s) étudiant(s) de plus pour '
                 f'{plan.montant_paiements:,} FCFA'.replace(',', ' '))
    stdout.write(f'  {len(plan.operations)} opération(s) de caisse de plus pour '
                 f'{plan.montant_operations:,} FCFA'.replace(',', ' ')
                 + f'  (entrées {len(entrees)}, sorties {len(sorties)})')
    stdout.write(f'  {len(plan.deja_poses)} ligne(s) déjà posées, '
                 f'{len(plan.sans_dossier)} ligne(s) de scolarité sans dossier étudiant '
                 f'({sum(l.montant for l in plan.sans_dossier):,} FCFA en caisse sans dossier)'.replace(',', ' '))
    if plan.periodes:
        stdout.write(f'  {len(plan.periodes)} paiement(s) déjà là dont le mois réglé peut être complété.')
    par_categorie = defaultdict(lambda: [0, 0])
    for categorie, ligne, ___ in plan.operations:
        par_categorie[categorie][0] += 1
        par_categorie[categorie][1] += ligne.montant
    stdout.write(style.MIGRATE_HEADING('\n  Détail des opérations nouvelles'))
    for categorie, (nombre, total) in sorted(par_categorie.items(), key=lambda kv: -kv[1][1]):
        stdout.write(f'    {categorie:<34} {nombre:>4} ligne(s)  {total:>11,} FCFA'.replace(',', ' '))
    stdout.write(style.MIGRATE_HEADING('\n  Écarts signalés'))
    par_motif = defaultdict(int)
    for motif, ___, ___ in plan.ecarts:
        par_motif[motif] += 1
    for motif, nombre in sorted(par_motif.items(), key=lambda kv: -kv[1]):
        stdout.write(f'    {motif:<34} {nombre:>4}')
    for motif, rang, detail in plan.ecarts[:12]:
        stdout.write(f'      ligne {rang} — {motif} : {detail}')
