"""Gestion des rôles et des accès depuis la fiche utilisateur du dashboard."""
from django.urls import reverse
from django.utils import timezone

from core.models import (
    AccountStatus, AuditLog, Enrollment, RoleKey, User, UserRole,
)
from core.views import _is_last_active_super_admin

from .base import BusinessTestBase

DETAIL_URL = 'core:dashboard:user-detail'
ROLES_URL = 'core:dashboard:user-role-assign'
STATUS_URL = 'core:dashboard:user-status-change'
USER_EDIT_URL = 'core:dashboard:user-edit'


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

    def test_role_assignment_generates_internal_code(self):
        user = self.make_user(RoleKey.ACCUEIL, 'sanscode@test.local')
        self.assertIsNone(user.internal_code)

        response = self.post_role(user, RoleKey.ETUDIANT)
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.internal_code.startswith('UA-ETU'))
        self.assert_audited('ROLE_ASSIGN', user.id)

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


class StudentAccountEnrollmentTests(BusinessTestBase):
    """Un compte étudiant est créé inscrit : il apparaît dans les formulaires."""

    def payload(self, **overrides):
        data = {
            'first_name': 'Nouvelle',
            'last_name': 'Promo',
            'email': 'nouvelle.promo@test.local',
            'phone': '+242060000001',
            'role': RoleKey.ETUDIANT,
            'session': self.session.pk,
            'password': 'PromoPass123!',
        }
        data.update(overrides)
        return data

    def create_client(self):
        return self.client_for(self.super_admin)

    def test_student_account_without_group_is_refused(self):
        before = User.objects.count()
        response = self.create_client().post(
            reverse('core:dashboard:user-create'), self.payload(session=''))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), before)

    def test_student_account_is_enrolled_on_creation(self):
        response = self.create_client().post(
            reverse('core:dashboard:user-create'), self.payload())
        self.assertRedirects(
            response, reverse('core:dashboard:user-list'),
            fetch_redirect_response=False,
        )
        student = User.objects.get(email='nouvelle.promo@test.local')
        self.assertTrue(student.internal_code.startswith('UA-ETU'))

        enrollment = Enrollment.objects.get(student=student)
        self.assertEqual(enrollment.session, self.session)
        self.assertEqual(enrollment.net_amount, self.course.fee_amount)
        self.assert_audited('ENROLLMENT_CREATE', enrollment.id)

        payment_form = self.client_for(self.comptable).get(
            reverse('core:dashboard:payment-create'))
        self.assertContains(payment_form, 'Nouvelle Promo')

    def test_non_student_account_needs_no_group(self):
        response = self.create_client().post(
            reverse('core:dashboard:user-create'),
            self.payload(role=RoleKey.ACCUEIL,
                         email='accueil2@test.local', session=''))
        self.assertRedirects(
            response, reverse('core:dashboard:user-list'),
            fetch_redirect_response=False,
        )
        self.assertEqual(Enrollment.objects.count(), 1)

    def test_role_assignment_without_enrollment_is_flagged(self):
        user = self.make_user(RoleKey.ACCUEIL, 'sansinscription@test.local')
        response = self.create_client().post(
            reverse(ROLES_URL, args=[user.id]),
            {'role_key': RoleKey.ETUDIANT, 'action': 'add'},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "aucune inscription")

    def test_reactivation_without_enrollment_is_flagged(self):
        student = self.make_user(
            RoleKey.ETUDIANT, 'suspendu@test.local',
            status=AccountStatus.SUSPENDED,
        )
        response = self.create_client().post(
            reverse(USER_EDIT_URL, args=[student.id]),
            {
                'first_name': student.first_name,
                'last_name': student.last_name,
                'email': student.email,
                'phone': student.phone,
                'account_status': AccountStatus.ACTIVE,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        student.refresh_from_db()
        self.assertEqual(student.account_status, AccountStatus.ACTIVE)
        self.assertContains(response, "sans inscription")

    def test_reactivation_of_enrolled_student_is_not_flagged(self):
        self.etudiant.account_status = AccountStatus.SUSPENDED
        self.etudiant.save(update_fields=['account_status'])
        response = self.create_client().post(
            reverse(USER_EDIT_URL, args=[self.etudiant.id]),
            {
                'first_name': self.etudiant.first_name,
                'last_name': self.etudiant.last_name,
                'email': self.etudiant.email,
                'phone': self.etudiant.phone,
                'account_status': AccountStatus.ACTIVE,
            },
            follow=True,
        )
        self.assertNotContains(response, "sans inscription")

    def test_status_change_without_enrollment_is_flagged(self):
        student = self.make_user(
            RoleKey.ETUDIANT, 'rehabilitation@test.local',
            status=AccountStatus.SUSPENDED,
        )
        response = self.create_client().post(
            reverse(STATUS_URL, args=[student.id]),
            {'account_status': AccountStatus.ACTIVE},
            follow=True,
        )
        self.assertContains(response, "sans inscription")
