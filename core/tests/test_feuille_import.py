"""Rapprochement du journal de caisse « Contrôles Mensuels » avec les écritures.

Le journal est la source de vérité de la caisse. Les tests vérifient que la
réconciliation ne réinvente pas l'histoire : une ligne de scolarité retrouve son
dossier, un mois déjà soldé ne se rejoue pas, un payeur sans compte devient une
simple opération de caisse, et une sortie de caisse porte la bonne catégorie.
"""
import datetime as dt
import tempfile
from pathlib import Path

import openpyxl

from core import feuille_import
from core.feuille_import import Ligne, MARQUE_FEUILLE, lignes_deja_ecrites, lire, reconcilier
from core.models import CashAccount, CashTransaction, Payment, TransactionCategory
from core.tests.base import BusinessTestBase


def ligne(**champs) -> Ligne:
    base = dict(rang=5, date=dt.datetime(2026, 3, 4), operation='entree',
                libelle='Frais Mensuel', intitule='Frais Mensuel Etudiant',
                mois='Mars', annee=2026, montant=25000, commentaire='',
                nom='', formation='')
    base.update(champs)
    return Ligne(**base)


class LectureDuJournalTests(BusinessTestBase):
    def _ecrire_classeur(self, rangees) -> Path:
        fichier = openpyxl.Workbook()
        feuille = fichier.active
        feuille.title = feuille_import.ONGLET
        feuille.append(['v', '', 'ENREGISTREMENT DES OPERATIONS', '', '', '', '', '', '', ''])
        for _ in range(3):
            feuille.append([''] * 10)
        feuille.append(['Date', 'Opération', 'Libellé', 'Intitulé', 'Mois payé',
                        "De l'année", 'Montant', 'Commentaires', 'Noms & Prénoms',
                        'Formation'])
        for rangee in rangees:
            feuille.append(rangee)
        chemin = Path(self._media_dir) / 'journal.xlsx'
        fichier.save(chemin)
        return chemin

    def test_le_classeur_se_lit_sans_reinventer_les_lignes_vides(self):
        chemin = self._ecrire_classeur([
            [dt.datetime(2026, 3, 4), 'Entrée', 'Frais Mensuel', 'Frais Mensuel Etudiant',
             'Mars', 2026, 25000, '', 'Paul PAUL', 'Anglais'],
            ['', '', '', '', '', 2025, '', '', '', ''],
            [dt.datetime(2026, 3, 5), '', 'Charges', 'Loyer', '', 2026, 90000, '', '', ''],
        ])
        lignes = lire(chemin)
        self.assertEqual(len(lignes), 2, 'une ligne sans montant ne doit pas être retenue')
        entree, sortie = lignes
        self.assertEqual(entree.genre, 'scolarite')
        self.assertEqual(sortie.genre, 'depense',
                         'sans colonne d’opération, le libellé dit le sens')
        self.assertEqual(sortie.categorie, 'Charges de fonctionnement')

    def test_un_classeur_sans_onglet_journal_est_refuse(self):
        fichier = openpyxl.Workbook()
        chemin = Path(self._media_dir) / 'sans_journal.xlsx'
        fichier.save(chemin)
        with self.assertRaises(ValueError):
            lire(chemin)


class ClassificationTests(BusinessTestBase):
    def test_chaque_genre_de_ligne_sa_categorie(self):
        cases = [
            (ligne(libelle='Inscription'), 'Paiements des étudiants'),
            (ligne(libelle='Frais de Bourse'), 'Subventions et dons'),
            (ligne(libelle='Frais d’Agence'), 'Autres recettes'),
            (ligne(operation='sortie', libelle='Charges', intitule='Salaire du Personnel'),
             'Salaires'),
            (ligne(operation='sortie', libelle='Charges', intitule='Avance sur Salaire'),
             'Avances sur salaire'),
            (ligne(operation='sortie', libelle='Charges', intitule='Fourniture de Bureau'),
             'Fournitures et consommables'),
            (ligne(operation='sortie', libelle='Charges', intitule='Maroc'),
             'Déplacements et missions'),
            (ligne(operation='sortie', libelle='Autres', intitule='Pourboire'),
             'Autres dépenses'),
        ]
        for exemple, attendue in cases:
            self.assertEqual(exemple.categorie, attendue, exemple.libelle)

    def test_le_mois_solde_se_lit_dans_la_colonne(self):
        self.assertEqual(ligne(mois='Octobre', annee=2025).cle_periode(), (2025, 10))
        self.assertIsNone(ligne(mois='Inscription').cle_periode(),
                          'une inscription ne solde aucun mois')
        self.assertIsNone(ligne(mois='Mars', annee=None).cle_periode(),
                          'sans année, le mois ne veut rien dire')


class ReconciliationTests(BusinessTestBase):
    nom_etudiant = ''

    def setUp(self):
        super().setUp()
        self.nom_etudiant = self.etudiant.get_full_name()

    def test_une_ligne_de_scolarite_retrouve_son_dossier(self):
        plan = reconcilier([ligne(nom=self.nom_etudiant,
                                  formation=self.session.course.title)])
        self.assertEqual(len(plan.paiements), 1)
        dossier, ___, periode = plan.paiements[0]
        self.assertEqual(dossier, self.enrollment)
        self.assertEqual(periode, (2026, 3))

    def test_un_mois_deja_solde_ne_se_rejoue_pas(self):
        Payment.objects.create(enrollment=self.enrollment, amount=25000,
                               method=Payment.Method.CASH, motif=Payment.Motif.MONTHLY,
                               period_year=2026, period_month=3,
                               recorded_by=self.assistant, status=Payment.Status.COMPLETED)
        plan = reconcilier([ligne(nom=self.nom_etudiant,
                                  formation=self.session.course.title)])
        self.assertEqual(plan.paiements, [])
        self.assertEqual(len(plan.deja_poses), 1)

    def test_un_payeur_sans_compte_devient_une_operation_de_caisse(self):
        plan = reconcilier([ligne(nom='Zoroastre INTROUVABLE', montant=30000)])
        self.assertEqual(plan.paiements, [])
        self.assertEqual(len(plan.sans_dossier), 1)
        categorie, cible, ___ = plan.operations[0]
        self.assertEqual(categorie, 'Paiements des étudiants')
        self.assertEqual(cible.nom, 'Zoroastre INTROUVABLE')

    def test_un_homonyme_ne_raviene_pas_un_dossier(self):
        doublon = type(self.etudiant).objects.create(
            email='homonyme@univers.academy', first_name=self.etudiant.first_name,
            last_name='KANY', is_active=True)
        doublon.roles.add(self.roles['ETUDIANT'])
        plan = reconcilier([ligne(nom=self.etudiant.first_name)])
        self.assertEqual(plan.paiements, [],
                         'un prénom porté par deux comptes ne désigne personne')
        self.assertTrue(any('égalité' in motif for motif, ___, ___ in plan.ecarts))

    def test_une_sortie_de_caisse_est_prepour_ecrire(self):
        plan = reconcilier([ligne(operation='sortie', libelle='Charges', intitule='Loyer',
                                  montant=180000, mois='', annee=2026)])
        self.assertEqual(len(plan.operations), 1)
        categorie, ___, ____ = plan.operations[0]
        self.assertEqual(categorie, 'Charges de fonctionnement')
        self.assertEqual(plan.sorties[0][1].montant, 180000)

    def test_un_paiement_une_fois_par_dossier_et_par_mois(self):
        plan = reconcilier([
            ligne(nom=self.nom_etudiant, formation=self.session.course.title),
            ligne(rang=6, nom=self.nom_etudiant, mois='Avril',
                  formation=self.session.course.title),
        ])
        self.assertEqual(len(plan.paiements), 2)
        self.assertEqual({p[2] for p in plan.paiements}, {(2026, 3), (2026, 4)})

    def test_deux_lignes_du_meme_mois_ne_donnent_qu_un_encaissement(self):
        plan = reconcilier([
            ligne(nom=self.nom_etudiant, formation=self.session.course.title),
            ligne(rang=6, nom=self.nom_etudiant, montant=20000,
                  formation=self.session.course.title),
        ])
        self.assertEqual(len(plan.paiements), 1, 'le mois déjà retenu ne se rejoue pas')
        self.assertIn('mois réglé deux fois au journal',
                      [motif for motif, ___, ___ in plan.ecarts])

    def test_un_mois_deja_paye_a_un_autre_montant_est_signale_sans_toucher(self):
        posé = Payment.objects.create(enrollment=self.enrollment, amount=20000,
                                      method=Payment.Method.CASH,
                                      motif=Payment.Motif.MONTHLY, period_year=2026,
                                      period_month=3, recorded_by=self.assistant,
                                      status=Payment.Status.COMPLETED)
        plan = reconcilier([ligne(nom=self.nom_etudiant,
                                  formation=self.session.course.title)])
        self.assertEqual(plan.paiements, [])
        self.assertEqual(Payment.objects.get(pk=posé.pk).amount, 20000,
                         'un tarif payé ne se retouche pas')
        self.assertIn('mois déjà réglé à un autre montant',
                      [motif for motif, ___, ___ in plan.ecarts])

    def test_relancer_la_vague_ne_double_rien(self):
        exemple = ligne(rang=412, nom='Zoroastre INTROUVABLE', montant=30000)
        self.assertEqual(len(reconcilier([exemple]).operations), 1)
        CashTransaction.objects.create(
            tx_type=CashTransaction.Type.IN,
            category=TransactionCategory.objects.get(name='Paiements des étudiants'),
            label='Frais Mensuel — Frais Mensuel Etudiant', amount=30000,
            account=CashAccount.objects.first(),
            status=CashTransaction.Status.VALIDATED,
            note=f'{MARQUE_FEUILLE} : ligne 412',
        )
        self.assertIn(412, lignes_deja_ecrites())
        self.assertEqual(reconcilier([exemple]).operations, [],
                         'la ligne déjà écrite du journal ne se rejoue pas')


class SoldeApresImportTests(BusinessTestBase):
    """Le journal ne s'écrit pas sur une caisse qui n'a pas de quoi le supporter.

    Deux sorties « mois d'octobre » payées par Mobile Money sans recette
    correspondante avaient laissé ce portefeuille à −100 100 FCFA : le lot entier
    se juge donc avant l'écriture, et un mauvais choix de caisse se refuse plutôt
    que de créer un découvert.
    """

    def entree(self, montant=150000, rang=70):
        return ligne(rang=rang, operation='entree', nom='Zoroastre INTROUVABLE',
                     montant=montant)

    def sortie(self, montant=100000, rang=71):
        return ligne(rang=rang, operation='sortie', libelle='Charges',
                     intitule='Salaire du Personnel', montant=montant,
                     mois='', annee=2026)

    def solde(self, *lignes):
        return feuille_import.solde_apres_ecriture(self.cash, reconcilier(list(lignes)))

    def test_une_sortie_sans_recette_porterait_la_caisse_sous_zero(self):
        plan = reconcilier([self.sortie()])
        self.assertEqual(plan.montant_sorties, 100000)
        self.assertEqual(plan.montant_recettes, 0)
        self.assertEqual(feuille_import.solde_apres_ecriture(self.cash, plan),
                         -100000)

    def test_les_recettes_du_meme_lot_couvrent_les_sorties(self):
        self.assertEqual(self.solde(self.entree(montant=150000), self.sortie()),
                         50000)

    def test_le_solde_deja_en_caisse_compte_aussi(self):
        CashTransaction.objects.create(
            tx_type=CashTransaction.Type.IN,
            category=TransactionCategory.objects.get(name='Paiements des étudiants'),
            label='Recette déjà en caisse', amount=100000, account=self.cash,
            status=CashTransaction.Status.VALIDATED,
        )
        self.assertEqual(self.solde(self.sortie()), 0)
