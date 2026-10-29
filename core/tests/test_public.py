"""Tests des pages publiques, de la connexion locale et de l'inscription."""
from django.test import override_settings
from django.urls import reverse

from core.models import (
    AccessRequest, AccountStatus, AuditLog, RoleKey, User,
)

from .base import BusinessTestBase, TEST_PASSWORD


class PublicPagesTests(BusinessTestBase):
    def test_landing_page_accessible_anonymously(self):
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)

    def test_login_page_contains_local_form(self):
        response = self.client.get(reverse('core:login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="identifier"')
        self.assertContains(response, 'name="password"')

    @override_settings(
        CLERK_ENABLED=True,
        CLERK_PUBLISHABLE_KEY='pk_test_univers',
        CLERK_SECRET_KEY='sk_test_univers',
        CLERK_FRONTEND_API='univers.clerk.accounts.dev',
        CLERK_JS_URL='https://univers.clerk.accounts.dev/clerk.browser.js',
        CLERK_UI_URL='https://univers.clerk.accounts.dev/ui.browser.js',
    )
    def test_local_form_precedes_clerk_widget(self):
        response = self.client.get(reverse('core:login'))
        html = response.content.decode()
        self.assertIn('id="clerk-sign-in"', html)
        self.assertIn('name="identifier"', html)
        self.assertLess(
            html.index('name="identifier"'), html.index('id="clerk-sign-in"'),
        )

    def test_register_page_contains_local_login_link(self):
        response = self.client.get(reverse('core:register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "J'ai déjà un compte")

    def test_scholarship_pages_are_public(self):
        self.assertEqual(
            self.client.get(reverse('core:bourses:scholarship-apply')).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse('core:bourses:scholarship-tracking')).status_code,
            200,
        )


class LocalLoginTests(BusinessTestBase):
    def test_login_with_email_redirects_to_dashboard(self):
        response = self.client.post(reverse('core:login'), {
            'identifier': self.secretaire.email,
            'password': TEST_PASSWORD,
        })
        self.assertRedirects(
            response, reverse('core:dashboard:dashboard-router'),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            self.client.session['_auth_user_id'], str(self.secretaire.pk)
        )
        self.assertTrue(AuditLog.objects.filter(
            action='LOGIN', actor=self.secretaire).exists())

    def test_login_with_internal_code(self):
        response = self.client.post(reverse('core:login'), {
            'identifier': self.etudiant.internal_code,
            'password': TEST_PASSWORD,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.client.session['_auth_user_id'], str(self.etudiant.pk)
        )

    def test_wrong_password_is_rejected(self):
        response = self.client.post(reverse('core:login'), {
            'identifier': self.secretaire.email,
            'password': 'MauvaisMotDePasse!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertFalse(AuditLog.objects.filter(action='LOGIN').exists())

    def test_suspended_account_cannot_stay_logged_in(self):
        suspended = self.make_user(
            RoleKey.ACCUEIL, 'suspendu@test.local',
            status=AccountStatus.SUSPENDED,
        )
        response = self.client.post(reverse('core:login'), {
            'identifier': suspended.email,
            'password': TEST_PASSWORD,
        })
        self.assertRedirects(
            response, reverse('core:login'), fetch_redirect_response=False,
        )
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_logout_requires_post(self):
        client = self.client_for(self.secretaire)
        response = client.get(reverse('core:logout'))
        self.assertRedirects(
            response, reverse('core:home'), fetch_redirect_response=False,
        )
        self.assertIn('_auth_user_id', client.session)
        response = client.post(reverse('core:logout'))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('_auth_user_id', client.session)


class RegistrationTests(BusinessTestBase):
    def test_register_creates_pending_account_and_access_request(self):
        response = self.client.post(reverse('core:register'), {
            'first_name': 'Nadia',
            'last_name': 'Moukoko',
            'email': 'nadia@test.local',
            'requested_role': RoleKey.FORMATEUR,
            'password': 'NadiaPass123!',
            'password_confirm': 'NadiaPass123!',
        })
        self.assertRedirects(
            response, reverse('core:pending-approval'),
            fetch_redirect_response=False,
        )
        user = User.objects.get(email='nadia@test.local')
        self.assertEqual(user.account_status, AccountStatus.PENDING_APPROVAL)
        self.assertTrue(user.check_password('NadiaPass123!'))
        self.assertFalse(user.roles.exists())
        access_request = AccessRequest.objects.get(user=user)
        self.assertEqual(access_request.requested_role, RoleKey.FORMATEUR)
        self.assertEqual(access_request.assigned_role, '')
        self.assertEqual(access_request.status, AccessRequest.Status.PENDING)
        self.assertTrue(AuditLog.objects.filter(
            action='REGISTER', entity_id=str(user.id)).exists())

    def test_register_rejects_super_admin_role_request(self):
        response = self.client.post(reverse('core:register'), {
            'first_name': 'Escalade',
            'last_name': 'Test',
            'email': 'escalade@test.local',
            'requested_role': RoleKey.SUPER_ADMIN,
            'password': 'EscaladePass123!',
            'password_confirm': 'EscaladePass123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email='escalade@test.local').exists())

    def test_register_rejects_mismatched_passwords(self):
        response = self.client.post(reverse('core:register'), {
            'first_name': 'Nadia',
            'last_name': 'Moukoko',
            'email': 'nadia2@test.local',
            'requested_role': RoleKey.ETUDIANT,
            'password': 'NadiaPass123!',
            'password_confirm': 'AutrePass123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email='nadia2@test.local').exists())

    def test_register_rejects_duplicate_email(self):
        response = self.client.post(reverse('core:register'), {
            'first_name': 'Doublon',
            'last_name': 'Test',
            'email': self.etudiant.email,
            'requested_role': RoleKey.ETUDIANT,
            'password': 'DoublonPass123!',
            'password_confirm': 'DoublonPass123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            User.objects.filter(email__iexact=self.etudiant.email).count(), 1
        )

    def test_pending_user_is_redirected_from_dashboard(self):
        pending = self.make_user(
            RoleKey.ETUDIANT, 'en-attente@test.local',
            status=AccountStatus.PENDING_APPROVAL,
        )
        client = self.client_for(pending)
        response = client.get(reverse('core:dashboard:dashboard-router'))
        self.assertRedirects(
            response, reverse('core:pending-approval'),
            fetch_redirect_response=False,
        )

    def test_suspended_user_is_redirected_to_access_denied(self):
        suspended = self.make_user(
            RoleKey.ETUDIANT, 'suspendu2@test.local',
            status=AccountStatus.SUSPENDED,
        )
        client = self.client_for(suspended)
        response = client.get(reverse('core:dashboard:dashboard-router'))
        self.assertRedirects(
            response, reverse('core:access-denied'),
            fetch_redirect_response=False,
        )
