"""La coquille doit suivre la langue choisie et rester neutre côté thème."""

from django.urls import reverse

from core.models import Enrollment, RoleKey
from core.tests.base import BusinessTestBase


class BasculeDeLangueTest(BusinessTestBase):
    def test_la_langue_par_defaut_reste_le_francais(self):
        page = self.client_for(self.direction).get(reverse('core:dashboard:dashboard-router'), follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Déconnexion')
        self.assertNotContains(page, '>Sign out<')

    def test_le_selecteur_de_langue_affiche_les_deux_options(self):
        page = self.client_for(self.direction).get(reverse('core:dashboard:dashboard-router'), follow=True)
        self.assertContains(page, 'name="language" value="fr"')
        self.assertContains(page, 'name="language" value="en"')
        self.assertContains(page, 'action="/i18n/setlang/"')

    def test_changer_de_langue_traduit_la_coquille(self):
        client = self.client_for(self.direction)
        reponse = client.post(
            reverse('set_language'),
            {'language': 'en', 'next': reverse('core:dashboard:dashboard-router')},
        )
        self.assertEqual(reponse.status_code, 302)

        page = client.get(reverse('core:dashboard:dashboard-router'), follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, '<html lang="en"')
        self.assertContains(page, 'Sign out')
        self.assertContains(page, 'Main navigation')
        self.assertNotContains(page, 'Déconnexion')

    def test_le_guichet_de_validation_se_traduit_aussi(self):
        student = self.make_user(RoleKey.ETUDIANT, 'guichet.en@test.local')
        dossier = Enrollment.objects.create(
            student=student,
            session=self.session,
            status=Enrollment.Status.PENDING,
            tariff_amount=self.course.fee_amount,
            discount_amount=0,
            net_amount=self.course.fee_amount,
            registered_by=self.secretaire,
        )
        client = self.client_for(self.direction)
        client.post(reverse('set_language'), {'language': 'en', 'next': '/'})

        page = client.get(reverse('core:dashboard:direction-dashboard'))
        self.assertContains(page, 'Enrollments awaiting validation')
        self.assertContains(page, 'Validate</button>')
        self.assertNotContains(page, 'Inscriptions en attente de validation')
        self.assertEqual(
            Enrollment.objects.get(pk=dossier.pk).status,
            Enrollment.Status.PENDING,
        )


class ThemeSombreTest(BusinessTestBase):
    def test_le_theme_est_resolu_avant_la_peinture(self):
        page = self.client_for(self.direction).get(reverse('core:dashboard:dashboard-router'), follow=True)
        self.assertContains(page, 'data-theme="light"')
        self.assertContains(page, "localStorage.getItem('ua-theme')")

    def test_le_bouton_de_theme_est_present_et_accessible(self):
        page = self.client_for(self.direction).get(reverse('core:dashboard:dashboard-router'), follow=True)
        self.assertContains(page, 'id="ua-theme-btn"')
        self.assertContains(page, 'Changer de thème')

    def test_la_feuille_compilee_porte_le_theme_sombre(self):
        from pathlib import Path
        from django.conf import settings

        css = Path(settings.STATICFILES_DIRS[0]) / 'css' / 'output.css'
        contenu = css.read_text(encoding='utf-8', errors='replace').replace('"', '')
        self.assertIn('data-theme=dark', contenu)
        self.assertIn('--ua-surface', contenu)
