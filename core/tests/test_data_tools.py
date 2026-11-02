"""Tests des lecteurs de classeurs : c'est eux qui décident de ce qui sera importé."""
import datetime as dt

from django.test import SimpleTestCase

from core import data_tools as outils


class MontantsEtDatesTest(SimpleTestCase):
    def test_toutes_les_formes_d_un_montant_des_classeurs(self):
        for valeur, montant, statut in (
            (20000.0, 20000, 'ok'),
            ('20 000FCFA', 20000, 'ok_texte'),
            ('150,000 fcfa ', 150000, 'ok_texte'),
            ('20000.0', 20000, 'ok_texte'),
            (0.0, None, 'nul'),
            ('', None, 'vide'),
            ('*', None, 'marque'),
            ('ok', None, 'texte'),
            ('550000 AVI et assu', None, 'ambigu'),
            ('MAI-JUIN juil 75000', None, 'ambigu'),
        ):
            self.assertEqual(outils.parse_montant(valeur)[:2], (montant, statut), valeur)

    def test_les_dates_se_reconnaissent_sans_confondre_un_montant(self):
        self.assertEqual(outils.parse_date(dt.datetime(2025, 10, 28)), (dt.date(2025, 10, 28), 'ok'))
        self.assertEqual(outils.parse_date(45958), (dt.date(2025, 10, 28), 'serie'))
        self.assertEqual(outils.parse_date('23.10.2026')[0], dt.date(2026, 10, 23))
        # 25 000 FCFA est aussi un n° de série Excel : la date obtenue est hors plage scolaire.
        self.assertFalse(outils.date_verossemblable(outils.parse_date(25000)[0]))
        self.assertTrue(outils.date_verossemblable(dt.date(2026, 10, 28)))

    def test_un_en_tete_numeric_n_est_pas_un_mois(self):
        """Dans « bureautique2evague », le « 7 » de l'en-tête est un compteur de lignes."""
        self.assertIsNone(outils.numero_mois(7))
        self.assertEqual(outils.numero_mois('  Octobre '), 10)
        self.assertEqual(outils.numero_mois(dt.datetime(2026, 7, 1)), 7)


class IdentificationTest(SimpleTestCase):
    def test_les_noms_des_classeurs_se_rapprochent(self):
        self.assertEqual(outils.niveau_ressemblance('GNEKOUMOU LIBALA L', 'GNEKOUMOU LIBALA'), 'probable')
        self.assertEqual(outils.niveau_ressemblance('OHIDA Ramses', 'ohida-ramses'), 'exact')
        self.assertIsNone(outils.niveau_ressemblance('KISSITA Emmanuelle', 'OHIDA Ramses'))
        self.assertIsNone(outils.niveau_ressemblance('de', 'de Gaulle'))
        # Les fautes d'orthographe des classeurs ne sont pas gommées : elles restent à valider.
        self.assertIsNone(outils.niveau_ressemblance('OHIDA Ramses', 'ohida rames'))


class DecoupageTest(SimpleTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.onglet = [
            ['N°', 'NOM & Prénoms', "Date d'inscription", "Frais d'inscription", 'Frais mensuels',
             'Novembre', 'Décembre', 'Commentaire'],
            ['', '', '', '', '', '', '', ''],
            [1.0, 'ENGOBA KELLY marcelle', dt.datetime(2026, 10, 12), 10000.0, 25000.0,
             25000.0, None, 'retard'],
            [2.0, 'MAKOSSO Blaise', dt.datetime(2026, 10, 15), 10000.0, 20000.0,
             'ok', None, ''],
            [3.0, None, None, None, None, None, None, None],
        ]

    def test_un_onglet_devient_un_bloc_repere(self):
        blocs = outils.decouper_blocs('Test', self.onglet)
        self.assertEqual(len(blocs), 1)
        bloc = blocs[0]
        self.assertEqual(bloc.colonnes['nom'], 1)
        self.assertEqual(sorted(bloc.mois.values()), [(11, 'Novembre'), (12, 'Décembre')])
        # La ligne vierge de séparation reste dans le tas : elle est écartée ligne par ligne.
        self.assertEqual(bloc.premiere_ligne, 1)

    def test_les_lignes_se_transforment_en_inscriptions(self):
        bloc = outils.decouper_blocs('Test', self.onglet)[0]
        premiere = outils.extraire_ligne(bloc, self.onglet[2], 3)
        self.assertEqual(premiere.nom, 'ENGOBA KELLY marcelle')
        self.assertEqual(premiere.date_inscription, dt.date(2026, 10, 12))
        self.assertEqual(premiere.frais_inscription, 10000)
        self.assertEqual(premiere.mois[0][2], 25000)
        self.assertEqual(premiere.annees, [2026])
        self.assertEqual(premiere.commentaire, 'retard')

        seconde = outils.extraire_ligne(bloc, self.onglet[3], 4)
        self.assertIn('montant_doutueux', [a[0] for a in seconde.anomalies])
        self.assertIsNone(outils.extraire_ligne(bloc, self.onglet[4], 5))

    def test_les_deux_tableaux_cote_a_cote_d_un_onglet_se_repèrent(self):
        onglet = [
            ['N°', 'NOM & Prénoms', "Date d'inscription", "Frais d'inscription", 'Frais mensuels',
             'Mai', 'Commentaire', '', 'N°', 'NOM & Prénoms', "Date d'inscription", 'Octobre'],
            [1.0, 'GNEKOUMOU LIBALA L', dt.datetime(2025, 10, 28), 10000.0, 20000.0,
             20000.0, '', '', 1.0, 'KISSITA Emmanuelle', dt.datetime(2026, 7, 23), 25000.0],
        ]
        blocs = outils.decouper_blocs('Anglais', onglet)
        self.assertEqual(len(blocs), 2)
        self.assertEqual(outils.extraire_ligne(blocs[0], onglet[1], 2).nom, 'GNEKOUMOU LIBALA L')
        self.assertEqual(outils.extraire_ligne(blocs[1], onglet[1], 2).nom, 'KISSITA Emmanuelle')

    def test_un_nom_eclate_se_reconstitue(self):
        onglet = [
            ['Nbre', "Date d'inscription", 'NOM & Prénoms', "Frais d'inscription", 'Frais mensuels',
             'Novembre', 'Décembre', 'Janvier', 'Commentaire'],
            ['', '', '', '', '', '', '', '', ''],
            [1.0, 'GANDZIEN BENDOLA', 'Whivine', dt.datetime(2025, 11, 26), 35000.0,
             0.0, 20000.0, '*', ''],
        ]
        bloc = outils.decouper_blocs('Sécretariat bilingue', onglet)[0]
        inscription = outils.extraire_ligne(bloc, onglet[2], 3)
        self.assertEqual(inscription.nom, 'GANDZIEN BENDOLA Whivine')
        self.assertEqual(inscription.date_inscription, dt.date(2025, 11, 26))
        self.assertIn('nom_eclate', [a[0] for a in inscription.anomalies])


class JournalTest(SimpleTestCase):
    def test_le_journal_de_caisse_se_lit(self):
        lignes = [
            [' v', '', 'ENREGISTREMENT DES OPERATIONS'],
            [],
            ['Date', 'Opération', 'Libellé', 'Intitulé', 'Mois payé', "De l'année", 'Montant',
             'Commentaires', 'Noms & Prénoms', 'Formation'],
            [dt.datetime(2025, 10, 2), 'Entrée', 'Frais Mensuel', 'Frais Mensuel Etudiant',
             'Octobre', 2026.0, 20000.0, '', 'Misnelle', 'Anglais'],
            [dt.datetime(2025, 10, 3), 'Sortie', 'Charges', 'Électricité', '', '', 15000.0,
             '', '', ''],
        ]
        ecritures, tete = outils.lire_journal('classeur.xlsx', lignes, 'Données')
        self.assertEqual(tete, 3)
        self.assertEqual(len(ecritures), 2)
        self.assertEqual(ecritures[0].montant, 20000)
        self.assertEqual(ecritures[0].personne, 'Misnelle')
        self.assertEqual(ecritures[0].mois_paye, 'Octobre')
        self.assertEqual(ecritures[1].sens, 'Sortie')
        self.assertNotEqual(ecritures[0].empreinte, ecritures[1].empreinte)
