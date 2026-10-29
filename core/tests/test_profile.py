"""Tests du profil : informations, avatar et changement d'email vérifié."""
import re
from io import BytesIO
from unittest import mock

from django.core import mail, signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image

from core.models import AuditLog, User
from core.views_profile import EMAIL_TOKEN_SALT

from .base import BusinessTestBase, TEST_PASSWORD


def png_upload(name='avatar.png', size=(4, 4)):
    buffer = BytesIO()
    Image.new('RGB', size, (200, 30, 30)).save(buffer, format='PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'
)
class ProfileTests(BusinessTestBase):
    def setUp(self):
        self.client = self.client_for(self.secretaire)

    # -- Informations -------------------------------------------------------

    def test_profile_page_renders(self):
        response = self.client.get(reverse('core:dashboard:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['profile_user'], self.secretaire)

    def test_profile_update_persists_and_is_audited(self):
        response = self.client.post(reverse('core:dashboard:profile'), {
            'action': 'profile',
            'first_name': 'Clarisse',
            'last_name': 'Nkounkou',
            'display_name': 'Clarisse N.',
            'phone': '+242 06 111 22 33',
            'address': 'Brazzaville',
        })
        self.assertRedirects(
            response, reverse('core:dashboard:profile'),
            fetch_redirect_response=False,
        )
        self.secretaire.refresh_from_db()
        self.assertEqual(self.secretaire.first_name, 'Clarisse')
        self.assertEqual(self.secretaire.display_name, 'Clarisse N.')
        self.assertEqual(self.secretaire.phone, '+242 06 111 22 33')
        self.assert_audited('PROFILE_UPDATE', self.secretaire.pk)

    # -- Avatar -------------------------------------------------------------

    def test_avatar_upload_and_delete(self):
        response = self.client.post(reverse('core:dashboard:profile'), {
            'action': 'avatar',
            'avatar': png_upload(),
        })
        self.assertRedirects(
            response, reverse('core:dashboard:profile'),
            fetch_redirect_response=False,
        )
        self.secretaire.refresh_from_db()
        self.assertTrue(self.secretaire.avatar)
        self.assertTrue(self.secretaire.avatar.storage.exists(
            self.secretaire.avatar.name))
        self.assert_audited('PROFILE_AVATAR', self.secretaire.pk)

        response = self.client.post(reverse('core:dashboard:profile'), {
            'action': 'avatar_delete',
        })
        self.assertRedirects(
            response, reverse('core:dashboard:profile'),
            fetch_redirect_response=False,
        )
        self.secretaire.refresh_from_db()
        self.assertFalse(self.secretaire.avatar)
        self.assert_audited('PROFILE_AVATAR_DELETE', self.secretaire.pk)

    def test_avatar_file_is_served_to_authenticated_users_only(self):
        self.secretaire.avatar = png_upload(name='portrait.png')
        self.secretaire.save(update_fields=['avatar'])
        url = self.secretaire.avatar.url

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')

        anonymous = self.client_class()
        response = anonymous.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('core:login'), response['Location'])

    def test_missing_avatar_file_returns_404(self):
        self.secretaire.avatar = png_upload(name='absent.png')
        self.secretaire.save(update_fields=['avatar'])
        url = self.secretaire.avatar.url
        self.secretaire.avatar.delete(save=False)
        self.assertEqual(self.client.get(url).status_code, 404)

    # -- Changement d'email -------------------------------------------------

    def test_email_change_request_sends_link_without_changing_email(self):
        old_email = self.secretaire.email
        response = self.client.post(reverse('core:dashboard:profile'), {
            'action': 'email',
            'new_email': 'nouvelle.adresse@test.local',
            'password': TEST_PASSWORD,
        })
        self.assertRedirects(
            response, reverse('core:dashboard:profile'),
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('nouvelle.adresse@test.local', mail.outbox[0].to)
        self.secretaire.refresh_from_db()
        self.assertEqual(self.secretaire.email, old_email)
        self.assert_audited('PROFILE_EMAIL_REQUEST', self.secretaire.pk)

    def test_email_change_confirmation_applies_new_address(self):
        old_email = self.secretaire.email
        self.client.post(reverse('core:dashboard:profile'), {
            'action': 'email',
            'new_email': 'confirmee@test.local',
            'password': TEST_PASSWORD,
        })
        self.assertEqual(len(mail.outbox), 1)
        match = re.search(
            r'/dashboard/profil/email/([^/\s]+)/', mail.outbox[0].body
        )
        self.assertIsNotNone(match, "Le lien de confirmation est absent du mail")
        response = self.client.get(
            reverse('core:dashboard:profile-email-confirm',
                    args=[match.group(1)])
        )
        self.assertRedirects(
            response, reverse('core:dashboard:profile'),
            fetch_redirect_response=False,
        )
        self.secretaire.refresh_from_db()
        self.assertEqual(self.secretaire.email, 'confirmee@test.local')
        self.assertEqual(self.secretaire.username, 'confirmee@test.local')
        self.assert_audited('PROFILE_EMAIL_CONFIRM', self.secretaire.pk)
        self.assertEqual(AuditLog.objects.filter(
            action='PROFILE_EMAIL_REQUEST').count(), 1)

    def test_email_change_rejects_wrong_password(self):
        response = self.client.post(reverse('core:dashboard:profile'), {
            'action': 'email',
            'new_email': 'autre@test.local',
            'password': 'MauvaisMotDePasse!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        self.secretaire.refresh_from_db()
        self.assertNotEqual(self.secretaire.email, 'autre@test.local')
        self.assertFalse(AuditLog.objects.filter(
            action='PROFILE_EMAIL_REQUEST').exists())

    def test_email_change_rejects_address_already_used(self):
        response = self.client.post(reverse('core:dashboard:profile'), {
            'action': 'email',
            'new_email': self.etudiant.email,
            'password': TEST_PASSWORD,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        self.secretaire.refresh_from_db()
        self.assertNotEqual(self.secretaire.email, self.etudiant.email)

    @mock.patch('core.views_profile.send_mail',
                side_effect=Exception('SMTP indisponible'))
    def test_email_is_not_changed_when_sending_fails(self, send_mail_mock):
        old_email = self.secretaire.email
        response = self.client.post(reverse('core:dashboard:profile'), {
            'action': 'email',
            'new_email': 'echec@test.local',
            'password': TEST_PASSWORD,
        })
        self.assertEqual(response.status_code, 200)
        send_mail_mock.assert_called_once()
        self.secretaire.refresh_from_db()
        self.assertEqual(self.secretaire.email, old_email)
        self.assertFalse(AuditLog.objects.filter(
            action='PROFILE_EMAIL_REQUEST').exists())

    def test_confirmation_token_for_another_user_is_rejected(self):
        token = signing.dumps(
            {'uid': str(self.etudiant.id), 'email': 'pirate@test.local'},
            salt=EMAIL_TOKEN_SALT,
        )
        response = self.client.get(
            reverse('core:dashboard:profile-email-confirm', args=[token])
        )
        self.assertRedirects(
            response, reverse('core:dashboard:profile'),
            fetch_redirect_response=False,
        )
        self.secretaire.refresh_from_db()
        self.assertNotEqual(self.secretaire.email, 'pirate@test.local')
        self.assertFalse(User.objects.filter(
            email='pirate@test.local').exists())

    def test_invalid_token_is_rejected(self):
        response = self.client.get(
            reverse('core:dashboard:profile-email-confirm',
                    args=['jeton-invalide'])
        )
        self.assertRedirects(
            response, reverse('core:dashboard:profile'),
            fetch_redirect_response=False,
        )
        self.assertFalse(AuditLog.objects.filter(
            action='PROFILE_EMAIL_CONFIRM').exists())

    def test_expired_token_is_rejected(self):
        token = signing.dumps(
            {'uid': str(self.secretaire.id), 'email': 'expire@test.local'},
            salt=EMAIL_TOKEN_SALT,
        )
        with mock.patch('core.views_profile.EMAIL_TOKEN_MAX_AGE', -1):
            response = self.client.get(
                reverse('core:dashboard:profile-email-confirm', args=[token])
            )
        self.assertRedirects(
            response, reverse('core:dashboard:profile'),
            fetch_redirect_response=False,
        )
        self.secretaire.refresh_from_db()
        self.assertNotEqual(self.secretaire.email, 'expire@test.local')
