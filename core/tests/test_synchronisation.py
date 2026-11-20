"""Synchronisation Google Sheets et sauvegarde automatique de la base.

Rien ici ne touche au réseau : on vérifie le classement des classeurs reçus,
le nommage des fichiers et la copie de sécurité. Le téléchargement lui-même est
couvert par la commande, pas par un test qui dépendrait de Google.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings
from openpyxl import Workbook

from core import google_sheets
from core.sauvegarde import empreinte_base, sauvegarder_base


class NommageTest(SimpleTestCase):
    def test_slug_reduit_les_accents_et_les_espaces(self):
        self.assertEqual(
            google_sheets._slug('Gestion des étudiants'),
            'gestion_des_etudiants',
        )

    def test_titre_excel_borne_et_dedoublonne(self):
        utilises = set()
        premier = google_sheets._titre_excel('Un onglet très long ' * 4, utilises)
        second = google_sheets._titre_excel('Un onglet très long ' * 4, utilises)
        self.assertLessEqual(len(premier), 31)
        self.assertNotEqual(premier, second)
        self.assertIn('(2)', second)

    def test_titre_excel_remplace_les_caracteres_interdits(self):
        titre = google_sheets._titre_excel('Journal [2026] : test / oui', set())
        for interdit in '[]:*?/\\':
            self.assertNotIn(interdit, titre)


class ClassementTest(SimpleTestCase):
    def _classeur(self, dossier: Path, onglets: list[str]) -> Path:
        chemin = dossier / 'classeur.xlsx'
        classeur = Workbook()
        classeur.remove(classeur.active)
        for onglet in onglets:
            classeur.create_sheet(onglet)
        classeur.save(chemin)
        return chemin

    def test_classeur_des_eleves(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = self._classeur(Path(dossier), [
                'Base Etudiants', 'Janvier 2026', 'Février 2026'])
            self.assertEqual(
                google_sheets.classer_classeur(chemin), 'etudiants')

    def test_journal_de_caisse(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = self._classeur(Path(dossier), [
                'Enregistrement_Opérations', 'Octobre 2025', 'Novembre 2025'])
            self.assertEqual(google_sheets.classer_classeur(chemin), 'journal')

    def test_classeur_inconnu(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = self._classeur(Path(dossier), ['Feuille 1'])
            self.assertEqual(google_sheets.classer_classeur(chemin), 'inconnu')

    def test_liste_des_onglets(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = self._classeur(Path(dossier), ['Un', 'Deux'])
            self.assertEqual(google_sheets.onglets(chemin), ['Un', 'Deux'])


class TelechargementTest(SimpleTestCase):
    def test_acces_refuse_explique_les_deux_issues(self):
        from unittest.mock import patch

        def refuser(*args, **kwargs):
            raise google_sheets.AccesRefuse('feuille privée')

        with patch.object(google_sheets, '_telecharger_public', refuser), \
                patch.object(google_sheets, 'chemin_identifiants',
                             return_value=None):
            with self.assertRaises(google_sheets.AccesRefuse) as erreur:
                google_sheets.telecharger('identifiant', tempfile.gettempdir())

        message = str(erreur.exception)
        self.assertIn('Tout utilisateur disposant du lien', message)
        self.assertIn('service-account.json', message)

    def test_le_nom_de_fichier_ne_s_ecrase_pas(self):
        with tempfile.TemporaryDirectory() as dossier:
            premier = google_sheets._chemin_libre(Path(dossier), 'Journal')
            premier.write_bytes(b'x')
            second = google_sheets._chemin_libre(Path(dossier), 'Journal')
            self.assertNotEqual(premier, second)
            self.assertEqual(premier.read_bytes(), b'x')


class SauvegardeTest(SimpleTestCase):
    def test_copie_la_base_sqlite(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            source = racine / 'db.sqlite3'
            source.write_bytes(b'contenu de la base')
            with override_settings(DATABASES={
                'default': {
                    'ENGINE': 'django.db.backends.sqlite3',
                    'NAME': str(source),
                },
            }):
                copie = sauvegarder_base(racine / 'backups')

            self.assertIsNotNone(copie)
            self.assertTrue(copie.is_file())
            self.assertEqual(copie.read_bytes(), b'contenu de la base')
            self.assertTrue(copie.name.startswith('db_'))
            self.assertIn('_auto', copie.name)

    def test_base_postgresql_non_copiee(self):
        with override_settings(DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': 'univers_academy',
            },
        }):
            self.assertIsNone(sauvegarder_base())

    def test_base_absente_non_copiee(self):
        with tempfile.TemporaryDirectory() as dossier:
            with override_settings(DATABASES={
                'default': {
                    'ENGINE': 'django.db.backends.sqlite3',
                    'NAME': str(Path(dossier) / 'absente.sqlite3'),
                },
            }):
                self.assertIsNone(sauvegarder_base(Path(dossier) / 'backups'))

    def test_empreinte_change_quand_la_base_est_ecrite(self):
        with tempfile.TemporaryDirectory() as dossier:
            source = Path(dossier) / 'db.sqlite3'
            source.write_bytes(b'contenu')
            with override_settings(DATABASES={
                'default': {
                    'ENGINE': 'django.db.backends.sqlite3',
                    'NAME': str(source),
                },
            }):
                avant = empreinte_base()
                source.write_bytes(b'contenu plus long')
                apres = empreinte_base()

        self.assertIsNotNone(avant)
        self.assertNotEqual(avant, apres)

    def test_empreinte_absente_pour_postgresql(self):
        with override_settings(DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': 'univers_academy',
            },
        }):
            self.assertIsNone(empreinte_base())


class DescriptionIdentifiantsTest(SimpleTestCase):
    """Le rapport d'accès doit rester lisible même sans JSON valide."""

    def test_json_valide_expose_le_client_email(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / 'service-account.json'
            chemin.write_text(
                '{"type": "service_account", '
                '"client_email": "sync@academy.iam.gserviceaccount.com", '
                '"project_id": "academy-70"}',
                encoding='utf-8',
            )
            infos = google_sheets.description_identifiants(chemin)

        self.assertTrue(infos['valide'])
        self.assertEqual(
            infos['client_email'], 'sync@academy.iam.gserviceaccount.com')
        self.assertEqual(infos['project_id'], 'academy-70')

    def test_json_illisible_est_signale_sans_lever(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / 'service-account.json'
            chemin.write_text('{pas du json', encoding='utf-8')
            infos = google_sheets.description_identifiants(chemin)

        self.assertTrue(infos['existe'])
        self.assertFalse(infos['valide'])
        self.assertIn('illisible', infos['erreur'])

    def test_chemin_absent_est_signale_sans_lever(self):
        infos = google_sheets.description_identifiants(
            Path(tempfile.gettempdir()) / 'service-account-absent.json')

        self.assertFalse(infos['existe'])
        self.assertFalse(infos['valide'])

    def test_les_feuilles_viennent_de_l_argument_puis_de_l_environnement(self):
        from unittest.mock import patch

        self.assertEqual(
            google_sheets.identifiants_feuilles(['a', 'b']), ['a', 'b'])
        with patch.dict('os.environ', {'CLASSEURS_GOOGLE_IDS': ' x , y '}):
            self.assertEqual(
                google_sheets.identifiants_feuilles(), ['x', 'y'])
        with patch.dict('os.environ', {'CLASSEURS_GOOGLE_IDS': ''}):
            self.assertEqual(
                google_sheets.identifiants_feuilles(),
                list(google_sheets.FEUILLES_PAR_DEFAUT))


class EtatGoogleTest(SimpleTestCase):
    """Le diagnostic ne doit télécharger aucun classeur."""

    def _identifiants(self):
        return {
            'chemin': 'C:/tmp/service-account.json',
            'existe': True,
            'valide': True,
            'type': 'service_account',
            'client_email': 'sync@academy.iam.gserviceaccount.com',
            'project_id': 'academy-70',
        }

    def _appeler(self, public, compte=None, identifiants=None):
        from io import StringIO
        from unittest.mock import patch

        from django.core.management import call_command

        sortie = StringIO()
        with patch.object(
                google_sheets, 'description_identifiants',
                return_value=identifiants or self._identifiants()), \
                patch.object(
                    google_sheets, 'verifier_public', return_value=public), \
                patch.object(
                    google_sheets, 'verifier_compte_service',
                    return_value=compte) as service:
            call_command('etat_google', feuille=['feuille-1'], stdout=sortie)
        return sortie.getvalue(), service

    def test_feuille_publique_et_compte_affiches(self):
        texte, service = self._appeler(
            {'accessible': True, 'detail': 'HTTP 200'},
            {'drive': {'accessible': True, 'detail': 'OK', 'titre': 'Élèves'},
             'sheets': {'accessible': True, 'detail': 'OK', 'titre': 'Élèves'},
             'titre': 'Élèves'},
        )

        self.assertIn('sync@academy.iam.gserviceaccount.com', texte)
        self.assertIn('publique      : oui', texte)
        self.assertIn('Drive', texte)
        self.assertIn('accessible', texte)
        service.assert_called_once()

    def test_compte_de_service_suffit_quand_la_feuille_est_privee(self):
        texte, _ = self._appeler(
            {'accessible': False, 'detail': 'HTTP 401'},
            {'drive': {'accessible': False, 'detail': 'HTTP 403'},
             'sheets': {'accessible': True, 'detail': 'OK', 'titre': 'Caisse'},
             'titre': 'Caisse'},
        )

        self.assertIn('publique      : non', texte)
        self.assertIn('Sheets API', texte)
        self.assertIn('accessible', texte)

    def test_sans_identifiants_et_sans_acces_public_la_commande_echoue(self):
        from io import StringIO
        from unittest.mock import patch

        from django.core.management import call_command
        from django.core.management.base import CommandError

        sortie = StringIO()
        with patch.object(
                google_sheets, 'description_identifiants',
                return_value={'chemin': 'C:/tmp/absent.json',
                              'existe': False, 'valide': False}), \
                patch.object(
                    google_sheets, 'verifier_public',
                    return_value={'accessible': False,
                                  'detail': 'HTTP 401'}), \
                patch.object(google_sheets, 'verifier_compte_service') as service:
            with self.assertRaises(CommandError):
                call_command('etat_google', feuille=['feuille-1'],
                             stdout=sortie)

        service.assert_not_called()
        self.assertIn('compte service: non testé', sortie.getvalue())


class MigrerTest(TestCase):
    """Une tâche planifiée ne doit pas empiler des copies inutiles."""

    def test_schema_a_jour_ne_copie_pas(self):
        from io import StringIO
        from unittest.mock import patch

        from django.core.management import call_command

        sortie = StringIO()
        with patch('core.management.commands.migrer.migrations_en_attente',
                   return_value=[]), \
                patch('core.management.commands.migrer.sauvegarder_base') as copie:
            call_command('migrer', stdout=sortie)

        copie.assert_not_called()
        self.assertIn('Aucune migration en attente', sortie.getvalue())

    def test_migration_attente_copie_avant_de_migrer(self):
        from io import StringIO
        from unittest.mock import patch

        from django.core.management import call_command

        with patch('core.management.commands.migrer.migrations_en_attente',
                   return_value=[object()]), \
                patch('core.management.commands.migrer.sauvegarder_base',
                      return_value=Path('backups/db_auto.sqlite3')) as copie:
            call_command('migrer', stdout=StringIO())

        copie.assert_called_once()

    def test_plan_reel_est_vide_sur_base_de_test(self):
        from core.management.commands.migrer import migrations_en_attente

        self.assertEqual(migrations_en_attente(), [])


class PythonAnywhereSyncTest(SimpleTestCase):
    def test_synchronise_immediatement_et_persiste_apres_succes(self):
        from datetime import datetime, timezone
        from unittest.mock import patch

        from deploy.pythonanywhere_sync import PROJECT_DIR, run_sync

        maintenant = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as dossier:
            etat = Path(dossier) / 'last-success'
            with patch('deploy.pythonanywhere_sync.subprocess.run') as run:
                self.assertEqual(run_sync(etat, maintenant), 0)

            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args_list[0].args[0][-1], 'migrer')
            self.assertEqual(run.call_args_list[1].args[0][-2:],
                             ['synchroniser_classeurs', '--ecrire'])
            self.assertTrue(all(call.kwargs['cwd'] == PROJECT_DIR
                                for call in run.call_args_list))
            self.assertEqual(
                datetime.fromisoformat(etat.read_text(encoding='utf-8')),
                maintenant)

    def test_ne_synchronise_pas_avant_72_heures(self):
        from datetime import datetime, timedelta, timezone
        from unittest.mock import patch

        from deploy.pythonanywhere_sync import run_sync

        derniere = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as dossier:
            etat = Path(dossier) / 'last-success'
            etat.write_text(derniere.isoformat(), encoding='utf-8')
            with patch('deploy.pythonanywhere_sync.subprocess.run') as run:
                self.assertEqual(
                    run_sync(etat, derniere + timedelta(days=3) -
                             timedelta(seconds=1)), 0)

            run.assert_not_called()
            self.assertEqual(
                datetime.fromisoformat(etat.read_text(encoding='utf-8')),
                derniere)

    def test_synchronise_a_partir_de_72_heures(self):
        from datetime import datetime, timedelta, timezone
        from unittest.mock import patch

        from deploy.pythonanywhere_sync import run_sync

        derniere = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as dossier:
            etat = Path(dossier) / 'last-success'
            etat.write_text(derniere.isoformat(), encoding='utf-8')
            with patch('deploy.pythonanywhere_sync.subprocess.run') as run:
                self.assertEqual(
                    run_sync(etat, derniere + timedelta(days=3)), 0)

            self.assertEqual(run.call_count, 2)

    def test_echec_ne_met_pas_a_jour_la_derniere_reussite(self):
        from datetime import datetime, timezone
        import subprocess
        from unittest.mock import patch

        from deploy.pythonanywhere_sync import run_sync

        maintenant = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as dossier:
            etat = Path(dossier) / 'last-success'
            with patch('deploy.pythonanywhere_sync.subprocess.run',
                       side_effect=subprocess.CalledProcessError(1, 'sync')):
                with self.assertRaises(subprocess.CalledProcessError):
                    run_sync(etat, maintenant)

            self.assertFalse(etat.exists())
