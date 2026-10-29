"""Gestion des rôles et des accès depuis la fiche utilisateur du dashboard."""
from django.urls import reverse
from django.utils import timezone

from core.models import AccountStatus, AuditLog, RoleKey, UserRole
from core.views import _is_last_active_super_admin

from .base import BusinessTestBase

DETAIL_URL = 'core:dashboard:user-detail'
ROLES_URL = 'core:dashboard:user-role-assign'
STATUS_URL = 'core:dashboard:user-status-change'


class UserDetailAccessPanelTests(BusinessTestBase):
    """Affichage des contrôles : SUPER_ADMIN uniquement, jamais sur soi-même."""

    def detail_url(self, user):
        return reverse(DETAIL_URL, args=[user.id])

    def test_super_admin_sees_role_and_status_controls(self):
        response = self.client_for(self.super_admin).get(
            self.detail_url(self.secretaire))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rôles et accès')
        self.assertContains(response, reverse(ROLES_URL, args=[self.secretaire.id]))
        self.assertContains(response, reverse(STATUS_URL, args=[self.secretaire.id]))
        # Les rôles déjà attribués ne sont pas proposés une seconde fois.
        self.assertNotIn(
            RoleKey.SECRETAIRE,
            [role.key for role in response.context['available_roles']],
        )
        self.assertTrue(response.context['can_manage_access'])

    def test_super_admin_can_open_every_user_sheet(self):
        client = self.client_for(self.super_admin)
        for user in (self.admin, self.direction, self.formateur, self.etudiant):
            with self.subTest(email=user.email):
                self.assertEqual(
                    client.get(self.detail_url(user)).status_code, 200)

    def test_super_admin_gets_no_controls_on_own_sheet(self):
        response = self.client_for(self.super_admin).get(
            self.detail_url(self.super_admin))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_manage_access'])
        self.assertTrue(response.context['is_self'])
        self.assertNotContains(
            response, reverse(ROLES_URL, args=[self.super_admin.id]))
        self.assertNotContains(
            response, reverse(STATUS_URL, args=[self.super_admin.id]))
        self.assertContains(response, 'vos rôles et votre statut')

    def test_admin_sees_sheet_but_no_controls(self):
        response = self.client_for(self.admin).get(
            self.detail_url(self.secretaire))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_manage_access'])
        self.assertNotContains(response, 'Rôles et accès')
        self.assertNotContains(
            response, reverse(ROLES_URL, args=[self.secretaire.id]))
        self.assertNotContains(
            response, reverse(STATUS_URL, args=[self.secretaire.id]))

    def test_user_list_offers_access_shortcut_to_super_admin_only(self):
        listing = self.client_for(self.super_admin).get(
            reverse('core:dashboard:user-list'))
        self.assertContains(listing, '#acces')
        listing = self.client_for(self.admin).get(
            reverse('core:dashboard:user-list'))
        self.assertNotContains(listing, '#acces')


class RoleAssignmentTests(BusinessTestBase):
    def post_role(self, user, role_key, action='add'):
        return self.client_for(self.super_admin).post(
            reverse(ROLES_URL, args=[user.id]),
            {'role_key': role_key, 'action': action},
        )

    def test_super_admin_adds_role(self):
        response = self.post_role(self.secretaire, RoleKey.COMPTABLE)
        self.assertRedirects(
            response,
            reverse(DETAIL_URL, args=[self.secretaire.id]),
            fetch_redirect_response=False,
        )
        self.assertTrue(
            self.secretaire.roles.filter(key=RoleKey.COMPTABLE).exists())
        self.assert_audited('ROLE_ASSIGN', self.secretaire.id)

    def test_adding_an_existing_role_is_idempotent(self):
        RoleAssignmentTests.post_role(self, self.secretaire, RoleKey.SECRETAIRE)
        response = self.post_role(self.secretaire, RoleKey.SECRETAIRE)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            UserRole.objects.filter(
                user=self.secretaire, role__key=RoleKey.SECRETAIRE).count(),
            1,
        )

    def test_super_admin_removes_role(self):
        response = self.post_role(
            self.secretaire, RoleKey.SECRETAIRE, action='remove')
        self.assertRedirects(
            response,
            reverse(DETAIL_URL, args=[self.secretaire.id]),
            fetch_redirect_response=False,
        )
        self.assertFalse(
            self.secretaire.roles.filter(key=RoleKey.SECRETAIRE).exists())
        self.assert_audited('ROLE_REMOVE', self.secretaire.id)

    def test_unknown_role_is_rejected_without_change(self):
        before = AuditLog.objects.count()
        response = self.post_role(self.secretaire, 'NOT_A_ROLE')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            list(self.secretaire.roles.values_list('key', flat=True)),
            [RoleKey.SECRETAIRE],
        )
        self.assertEqual(AuditLog.objects.count(), before)

    def test_unknown_action_is_rejected_without_change(self):
        response = self.post_role(
            self.secretaire, RoleKey.COMPTABLE, action='promote')
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            self.secretaire.roles.filter(key=RoleKey.COMPTABLE).exists())

    def test_admin_cannot_assign_roles(self):
        response = self.client_for(self.admin).post(
            reverse(ROLES_URL, args=[self.secretaire.id]),
            {'role_key': RoleKey.COMPTABLE, 'action': 'add'},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            self.secretaire.roles.filter(key=RoleKey.COMPTABLE).exists())

    def test_cannot_change_own_roles(self):
        response = self.client_for(self.super_admin).post(
            reverse(ROLES_URL, args=[self.super_admin.id]),
            {'role_key': RoleKey.ADMIN, 'action': 'add'},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.super_admin.roles.filter(key=RoleKey.ADMIN).exists())

    def test_get_does_not_change_anything(self):
        response = self.client_for(self.super_admin).get(
            reverse(ROLES_URL, args=[self.secretaire.id]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            list(self.secretaire.roles.values_list('key', flat=True)),
            [RoleKey.SECRETAIRE],
        )


class AccountStatusChangeTests(BusinessTestBase):
    def post_status(self, user, status):
        return self.client_for(self.super_admin).post(
            reverse(STATUS_URL, args=[user.id]),
            {'account_status': status},
        )

    def test_super_admin_suspends_then_reactivates_account(self):
        self.assertIsNone(self.secretaire.disabled_at)

        response = self.post_status(self.secretaire, AccountStatus.SUSPENDED)
        self.assertRedirects(
            response,
            reverse(DETAIL_URL, args=[self.secretaire.id]),
            fetch_redirect_response=False,
        )
        self.secretaire.refresh_from_db()
        self.assertEqual(self.secretaire.account_status, AccountStatus.SUSPENDED)
        self.assertIsNotNone(self.secretaire.disabled_at)
        entry = self.assert_audited('USER_STATUS_CHANGE', self.secretaire.id)
        self.assertEqual(
            entry.before_summary, {'status': AccountStatus.ACTIVE})
        self.assertEqual(
            entry.after_summary, {'status': AccountStatus.SUSPENDED})

        response = self.post_status(self.secretaire, AccountStatus.ACTIVE)
        self.assertEqual(response.status_code, 302)
        self.secretaire.refresh_from_db()
        self.assertEqual(self.secretaire.account_status, AccountStatus.ACTIVE)
        self.assertIsNone(self.secretaire.disabled_at)

    def test_suspended_user_loses_back_office_access(self):
        self.post_status(self.secretaire, AccountStatus.DISABLED)
        client = self.client_for(self.secretaire)
        response = client.get(reverse('core:dashboard:secretaire-dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('core:access-denied'), response['Location'])

    def test_invalid_status_is_rejected(self):
        response = self.post_status(self.secretaire, 'SUPER_ACTIVE')
        self.assertEqual(response.status_code, 302)
        self.secretaire.refresh_from_db()
        self.assertEqual(self.secretaire.account_status, AccountStatus.ACTIVE)
        self.assertFalse(
            AuditLog.objects.filter(
                action='USER_STATUS_CHANGE',
                entity_id=str(self.secretaire.id),
            ).exists()
        )

    def test_unchanged_status_writes_no_audit(self):
        response = self.post_status(self.secretaire, AccountStatus.ACTIVE)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            AuditLog.objects.filter(
                action='USER_STATUS_CHANGE',
                entity_id=str(self.secretaire.id),
            ).exists()
        )

    def test_admin_cannot_change_status(self):
        response = self.client_for(self.admin).post(
            reverse(STATUS_URL, args=[self.secretaire.id]),
            {'account_status': AccountStatus.SUSPENDED},
        )
        self.assertEqual(response.status_code, 403)
        self.secretaire.refresh_from_db()
        self.assertEqual(self.secretaire.account_status, AccountStatus.ACTIVE)

    def test_cannot_change_own_status(self):
        response = self.client_for(self.super_admin).post(
            reverse(STATUS_URL, args=[self.super_admin.id]),
            {'account_status': AccountStatus.SUSPENDED},
        )
        self.assertEqual(response.status_code, 403)
        self.super_admin.refresh_from_db()
        self.assertEqual(self.super_admin.account_status, AccountStatus.ACTIVE)

    def test_get_does_not_change_status(self):
        response = self.client_for(self.super_admin).get(
            reverse(STATUS_URL, args=[self.secretaire.id]))
        self.assertEqual(response.status_code, 302)
        self.secretaire.refresh_from_db()
        self.assertEqual(self.secretaire.account_status, AccountStatus.ACTIVE)

    def test_edit_form_reactivation_clears_disabled_at(self):
        self.secretaire.account_status = AccountStatus.SUSPENDED
        self.secretaire.disabled_at = timezone.now()
        self.secretaire.save(update_fields=['account_status', 'disabled_at'])

        response = self.client_for(self.super_admin).post(
            reverse('core:dashboard:user-edit', args=[self.secretaire.id]),
            {
                'first_name': self.secretaire.first_name,
                'last_name': self.secretaire.last_name,
                'email': self.secretaire.email,
                'phone': '',
                'account_status': AccountStatus.ACTIVE,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.secretaire.refresh_from_db()
        self.assertEqual(self.secretaire.account_status, AccountStatus.ACTIVE)
        self.assertIsNone(self.secretaire.disabled_at)

    def test_last_active_super_admin_helper(self):
        """Garde-fou de verrouillage : seul un super admin actif compte."""
        other = self.make_user(RoleKey.SUPER_ADMIN, 'super2@test.local')
        self.assertFalse(_is_last_active_super_admin(self.super_admin))
        self.assertFalse(_is_last_active_super_admin(other))
        self.assertFalse(_is_last_active_super_admin(self.secretaire))

        other.account_status = AccountStatus.SUSPENDED
        other.save(update_fields=['account_status'])
        self.assertTrue(_is_last_active_super_admin(self.super_admin))

        self.super_admin.account_status = AccountStatus.SUSPENDED
        self.super_admin.save(update_fields=['account_status'])
        self.assertFalse(_is_last_active_super_admin(self.super_admin))
