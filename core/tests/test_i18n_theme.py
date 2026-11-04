"""La coquille doit suivre la langue choisie, rester neutre côté thème et
empiler ses notifications hors du fil de la page."""

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import (
    AccessRequest, CashTransaction, Enrollment, Notification, RoleKey,
)
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


# Par défaut, FallbackStorage lit le cookie avant la session et s'arrête dès que
# le cookie est absent : les messages préparés ci-dessous passent donc par le
# magasin de session, seul endroit que la vue acceptera de relire ici.
@override_settings(
    MESSAGE_STORAGE='django.contrib.messages.storage.session.SessionStorage')
class NotificationFlottanteTest(BusinessTestBase):
    """Un message de l'application devient une carte empilée, plus un bloc dans la page."""

    def empiler(self, client, niveau, texte):
        from django.contrib.messages.storage.base import Message
        from django.contrib.messages.storage.cookie import MessageEncoder

        session = client.session
        session['_messages'] = MessageEncoder().encode([Message(niveau, texte, '')])
        session.modified = True
        session.save()

    def page_coquille(self, client):
        return client.get(reverse('core:dashboard:dashboard-router'), follow=True)

    def test_un_message_sempile_en_carte_flottante(self):
        client = self.client_for(self.direction)
        self.empiler(client, 25, 'Paiement enregistré')
        page = self.page_coquille(client)

        self.assertContains(page, 'id="ua-toasts"')
        self.assertContains(page, 'ua-toast--success')
        self.assertContains(page, 'Paiement enregistré')
        self.assertContains(page, 'ua-toast-fermer')
        self.assertContains(page, 'js/notifications.js')

    def test_le_bloc_inline_a_disparu_du_fil_de_la_page(self):
        client = self.client_for(self.direction)
        self.empiler(client, 40, 'Encaissement refusé')
        page = self.page_coquille(client)

        self.assertContains(page, 'ua-toast--error')
        self.assertNotContains(page, 'space-y-2 mb-5')

    def test_le_bouton_de_son_est_dans_la_barre(self):
        page = self.page_coquille(self.client_for(self.direction))
        self.assertContains(page, 'id="ua-son-btn"')
        self.assertContains(page, 'Sons de notification')
        self.assertContains(page, 'data-son="on"')
        self.assertContains(page, "localStorage.getItem('ua-son')")

    def test_la_coquille_de_notification_se_traduit(self):
        client = self.client_for(self.direction)
        client.post(reverse('set_language'), {'language': 'en', 'next': '/'})
        self.empiler(client, 20, 'Dossier déposé')
        page = self.page_coquille(client)

        self.assertContains(page, 'Notification sounds')
        self.assertContains(page, 'Dismiss this notification')


class ClocheRappelTest(BusinessTestBase):
    """Le rappel persistant : c'est le travail qui l'éteint, jamais le temps."""

    def setUp(self):
        self.route = reverse('core:dashboard:dashboard-router')

    def brouillon_de_caisse(self):
        return CashTransaction.objects.create(
            tx_type=CashTransaction.Type.IN,
            category=self.income_category,
            label='Encaissement à valider',
            amount=25000,
            account=self.cash,
            status=CashTransaction.Status.DRAFT,
            occurred_at=timezone.localtime(timezone.now()),
            created_by=self.assistant,
        )

    def notification(self, user):
        return Notification.objects.create(
            user=user,
            title='Compte approuvé',
            message='Votre compte vient d’être activé.',
            notification_type=Notification.Type.ACCOUNT_APPROVED,
        )

    def page(self, user):
        return self.client_for(user).get(self.route, follow=True)

    def test_une_file_non_vide_allume_la_pastille(self):
        self.brouillon_de_caisse()
        page = self.page(self.assistant)

        self.assertContains(page, 'id="ua-cloche"')
        self.assertContains(page, 'class="ua-cloche-pastille">1<')
        self.assertContains(page, 'Écritures de caisse en brouillon')
        self.assertContains(page, reverse('core:dashboard:journal'))

    def test_la_pastille_compte_taches_et_notifications_non_lues(self):
        self.brouillon_de_caisse()
        self.notification(self.assistant)
        page = self.page(self.assistant)

        self.assertContains(page, 'class="ua-cloche-pastille">2<')
        self.assertContains(page, 'Compte approuvé')

    def test_la_file_vide_etaint_la_pastille(self):
        page = self.page(self.etudiant)

        self.assertContains(page, 'id="ua-cloche"')
        self.assertNotContains(page, 'ua-cloche-pastille')
        self.assertContains(page, 'Rien à traiter')

    def test_marquer_lues_eteint_le_rappel(self):
        note = self.notification(self.etudiant)
        client = self.client_for(self.etudiant)

        self.assertContains(client.get(self.route, follow=True), 'ua-cloche-pastille')
        self.assertEqual(client.get(reverse('core:dashboard:notifications-lire')).status_code, 405)

        reponse = client.post(reverse('core:dashboard:notifications-lire'))
        self.assertEqual(reponse.status_code, 302)
        note.refresh_from_db()
        self.assertTrue(note.is_read)
        self.assertNotContains(client.get(self.route, follow=True), 'ua-cloche-pastille')

    def test_le_rappel_ne_pointe_jamais_une_porte_fermee(self):
        AccessRequest.objects.create(
            user=self.etudiant, requested_role=RoleKey.FORMATEUR)
        self.brouillon_de_caisse()

        client = self.client_for(self.super_admin)
        page = client.get(self.route, follow=True)
        self.assertContains(page, 'class="ua-cloche-pastille">2<')
        self.assertContains(page, reverse('core:dashboard:access-requests'))
        for url in (reverse('core:dashboard:access-requests'),
                    reverse('core:dashboard:journal')):
            self.assertEqual(client.get(url).status_code, 200, url)

    def test_le_panneau_de_rappel_se_traduit(self):
        self.brouillon_de_caisse()
        client = self.client_for(self.assistant)
        client.post(reverse('set_language'), {'language': 'en', 'next': '/'})
        page = client.get(self.route, follow=True)

        self.assertContains(page, 'Draft cash entries to post')
        self.assertContains(page, 'To process')
