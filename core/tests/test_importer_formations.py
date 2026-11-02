"""Tests du tarif lu dans les classeurs et du portique de la vague 1.

Aucun accès en base, aucun fichier : les règles sont des tableaux purs dans
``core.programme_import``, et le portique ne regarde que des dictionnaires.
"""
from collections import Counter

from django.core.management.base import CommandError
from django.test import SimpleTestCase

from core import programme_import as programme
from core.management.commands.importer_formations import Command


def vu(mensualites_par_intitule: dict) -> dict:
    return {cle: {'mensualite': Counter(valeurs)}
            for cle, valeurs in mensualites_par_intitule.items()}


class MensuelObserveTests(SimpleTestCase):
    def test_la_mensualite_la_plus_encaissee_gagne(self):
        observees = vu({'anglais': [25000] * 25 + [20000] * 8 + [15000] * 2})
        self.assertEqual(programme.mensuel_observee(observees, 'anglais', 25000), 25000)

    def test_un_montant_vu_une_fois_ne_fait_pas_tarif(self):
        observees = vu({'bureautique': [20000, 25000, 550000]})
        self.assertEqual(programme.mensuel_observee(observees, 'bureautique', 20000), 20000)

    def test_un_montant_plus_eleve_que_les_autres_ne_simpose_pas(self):
        observees = vu({'anglais': [25000] * 25 + [250000] * 1})
        self.assertEqual(programme.mensuel_observee(observees, 'anglais', 20000), 25000)

    def test_l_onglet_de_promotion_renseigne_sa_parente(self):
        observees = vu({'italien': {20000: 1}, 'italien oct2026': [25000] * 5})
        self.assertEqual(programme.mensuel_observee(observees, 'italien', 20000), 25000)

    def test_l_alias_fondu_donne_son_tarif(self):
        observees = vu({'a humaines ressources': [], 'rh': [25000] * 3})
        self.assertEqual(
            programme.mensuel_observee(observees, 'a humaines ressources', 20000), 25000)

    def test_un_intitule_sans_encaissement_garde_le_repli(self):
        self.assertEqual(
            programme.mensuel_observee(vu({'chinois': []}), 'chinois', 25000), 25000)

    def test_la_bande_20_a_25_encadre_meme_un_tarif_repete(self):
        observees = vu({'anglais': [30000] * 20})
        self.assertEqual(programme.mensuel_observee(observees, 'anglais', 25000), 25000)

    def test_la_bande_encadre_aussi_le_repli_declare(self):
        observees = vu({'bilingue secretariat': [35000] * 4})
        self.assertEqual(
            programme.mensuel_observee(observees, 'bilingue secretariat', 35000), 25000)

    def test_une_mensualite_minuscule_ne_descend_pas_sous_la_bande(self):
        observees = vu({'infographie': [5000] * 9})
        self.assertEqual(programme.mensuel_observee(observees, 'infographie', 5000), 20000)


class DeclarationTests(SimpleTestCase):
    def test_deux_intitules_ne_visent_pas_le_meme_titre(self):
        titres = [titre for titre, _domaine, _repli in programme.FORMATIONS.values()]
        self.assertEqual(len(titres), len(set(titres)))

    def test_toute_promotion_a_une_parente_declaree_ou_rien(self):
        for cle, parente in programme.PROMOTIONS.items():
            if parente is not None:
                self.assertIn(parente, programme.FORMATIONS, f'{cle} vise une inconnue')
            else:
                self.assertIn(cle, programme.HORS_CATALOGUE, f'{cle} n\'est une formation de personne')

    def test_tout_alias_fond_dans_une_formation_declaree(self):
        for alias, cible in programme.FUSIONS.items():
            self.assertIn(cible, programme.FORMATIONS, f'« {alias} » fond dans une inconnue')

    def test_le_portique_refuse_un_intitule_non_declare(self):
        observees = {cle: {'mensualite': Counter()} for cle in programme.FORMATIONS}
        observees['gestion de projet'] = {'mensualite': Counter()}
        appariees = {cle: (None, None) for cle in observees}
        with self.assertRaisesMessage(CommandError, 'gestion de projet'):
            Command._controler(appariees, observees)

    def test_le_portique_refuse_un_classeur_qui_noffre_plus_rien(self):
        with self.assertRaisesMessage(CommandError, 'introuvable'):
            Command._controler({'anglais': ('Anglais', 'exact')}, {})

    def test_le_portique_se_tait_quand_tout_est_declare(self):
        observees = {cle: {'mensualite': Counter()} for cle in programme.FORMATIONS}
        observees.update({cle: {'mensualite': Counter()}
                          for cle in programme.PROMOTIONS if cle not in observees})
        observees['seminaire blanc'] = {'mensualite': Counter()}
        appariees = {cle: (None, None) for cle in observees}
        appariees['seminaire blanc'] = ('Les langues étrangères', 'exact')
        Command._controler(appariees, observees)
