"""Bouton « Synchroniser les classeurs » du tableau de bord super administrateur.

La commande réelle n'est jamais lancée ici : on vérifie le garde-fou de rôle,
le verrou anti-chevauchement, le compte rendu et la trace d'audit.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.management.base import CommandError
from django.test import override_settings
from django.urls import reverse

from core.models import AuditLog, RoleKey
from core.tests.base import BusinessTestBase


class SynchronisationVueTests(BusinessTestBase):
    def setUp(self):
        self.dossier_verrou = tempfile.TemporaryDirectory(prefix='ua-sync-lock-')
        self.addCleanup(self.dossier_verrou.cleanup)
        override = override_settings(BASE_DIR=self.dossier_verrou.name)
        override.enable()
        self.addCleanup(override.disable)
        self.url = reverse('core:dashboard:synchronisation-classeurs')
        self.page_url = reverse('core:dashboard:synchronisation-page')

    def test_bouton_present_pour_le_super_admin(self):
        page = self.client_for(self.super_admin).get(
            reverse('core:dashboard:super-admin-dashboard'))
        self.assertContains(page, self.page_url)
        self.assertContains(page, 'Synchroniser les classeurs')

    def test_page_de_chargement_lance_le_post(self):
        page = self.client_for(self.super_admin).get(self.page_url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Synchronisation en cours')
        self.assertContains(page, 'Veuillez patienter')
        self.assertContains(page, self.url)
        self.assertContains(page, 'csrfmiddlewaretoken')

    def test_reserve_au_super_admin(self):
        client = self.client_for(self.admin)
        response = client.post(self.url)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(client.get(self.page_url).status_code, 403)
        self.assertFalse(AuditLog.objects.filter(
            action='SYNCHRONISATION_CLASSEURS').exists())

    def test_get_refuse(self):
        response = self.client_for(self.super_admin).get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_post_lance_la_commande_et_laisse_une_trace(self):
        appels = []

        def commande(nom, **kwargs):
            appels.append((nom, kwargs))
            kwargs['stdout'].write('Classeurs reçus : 2\nSynchronisation réussie.\n')

        client = self.client_for(self.super_admin)
        with patch('core.views_synchronisation.call_command', side_effect=commande):
            response = client.post(self.url, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(appels), 1)
        self.assertEqual(appels[0][0], 'synchroniser_classeurs')
        self.assertTrue(appels[0][1]['ecrire'])
        self.assertContains(response, 'Synchronisation terminée')
        trace = AuditLog.objects.get(action='SYNCHRONISATION_CLASSEURS')
        self.assertEqual(trace.actor, self.super_admin)
        self.assertIn('Synchronisation réussie', trace.after_summary)
        self.assertFalse(
            Path(self.dossier_verrou.name, '.synchronisation-classeurs.lock').exists())

    def test_echec_de_la_commande_est_affiche_sans_trace_de_succes(self):
        client = self.client_for(self.super_admin)
        with patch('core.views_synchronisation.call_command',
                   side_effect=CommandError(' feuille privée ')):
            response = client.post(self.url, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Synchronisation impossible')
        trace = AuditLog.objects.get(action='SYNCHRONISATION_CLASSEURS')
        self.assertIn('Échec', trace.after_summary)
        self.assertFalse(
            Path(self.dossier_verrou.name, '.synchronisation-classeurs.lock').exists())

    def test_verrou_deja_pris_bloque_le_lancement(self):
        verrou = Path(self.dossier_verrou.name, '.synchronisation-classeurs.lock')
        verrou.write_text('en cours', encoding='utf-8')
        client = self.client_for(self.super_admin)

        with patch('core.views_synchronisation.call_command') as commande:
            response = client.post(self.url, follow=True)

        commande.assert_not_called()
        self.assertContains(response, 'Une synchronisation est déjà en cours.')
        self.assertTrue(verrou.exists())
        self.assertFalse(AuditLog.objects.filter(
            action='SYNCHRONISATION_CLASSEURS').exists())
