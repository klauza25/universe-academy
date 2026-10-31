"""Tests de l'inscription, de l'approbation et de l'attribution des rôles.

Scénarios de la spécification : aucun compte créé via Clerk ou via le
formulaire public ne reçoit de rôle effectif, et les rôles d'administration ne
peuvent être obtenus ni par défaut ni par manipulation de requête.
"""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse

from core.clerk import sync_clerk_user
from core.models import (
    AccessRequest, AccountStatus, AuditLog, Notification, RoleKey, User,
)

from .base import BusinessTestBase, TEST_PASSWORD


def fake_clerk_user(email, *, verified=True, first='Clerk', last='Signup'):
    status = SimpleNamespace(value='verified' if verified else 'unverified')
    email_obj = SimpleNamespace(
        id='email_primary', email_address=email,
        verification=SimpleNamespace(status=status),
    )
    return SimpleNamespace(
        id='user_fake',
        email_addresses=[email_obj],
        primary_email_address_id='email_primary',
        first_name=first,
        last_name=last,
        full_name=f'{first} {last}',
        username='',
    )


class ClerkSignupTests(BusinessTestBase):
    def test_clerk_signup_creates_pending_account_without_role(self):
        payload = {
            'sub': 'user_clerk_1',
            'email': 'clerk1@test.local',
            # Des métadonnées de rôle ne doivent jamais faire autorité.
            'role': 'SUPER_ADMIN',
            'metadata': {'role': 'SUPER_ADMIN'},
            'unsafe_metadata': {'role': 'SUPER_ADMIN'},
        }
        with patch('core.clerk.get_clerk_client') as get_client:
            get_client.return_value.users.get.return_value = fake_clerk_user(
                'clerk1@test.local'
            )
            user, created = sync_clerk_user(payload)

        self.assertTrue(created)
        self.assertEqual(user.account_status, AccountStatus.PENDING_APPROVAL)
        self.assertFalse(user.roles.exists())
        self.assertFalse(user.is_superuser)
        access_request = user.pending_access_request
        self.assertIsNotNone(access_request)
        self.assertEqual(access_request.requested_role, '')
        self.assertEqual(access_request.assigned_role, '')

    @override_settings(CLERK_ENABLED=True)
    def test_clerk_session_redirects_new_account_to_access_request(self):
        with patch(
            'core.views.verify_clerk_token',
            return_value={'sub': 'user_clerk_2', 'email': 'clerk2@test.local'},
        ), patch('core.clerk.get_clerk_client') as get_client:
            get_client.return_value.users.get.return_value = fake_clerk_user(
                'clerk2@test.local'
            )
            response = self.client.post(
                reverse('core:clerk-session'), {'token': 'session-token'}
            )

        self.assertRedirects(
            response, reverse('core:complete-access-request'),
            fetch_redirect_response=False,
        )
        user = User.objects.get(email='clerk2@test.local')
        self.assertFalse(user.roles.exists())
        self.assertEqual(user.account_status, AccountStatus.PENDING_APPROVAL)

    def test_pending_clerk_account_cannot_open_dashboards(self):
        with patch('core.clerk.get_clerk_client') as get_client:
            get_client.return_value.users.get.return_value = fake_clerk_user(
                'clerk3@test.local'
            )
            user, _ = sync_clerk_user(
                {'sub': 'user_clerk_3', 'email': 'clerk3@test.local'}
            )

        client = self.client_for(user)
        for route in (
            'core:dashboard:formateur-dashboard',
            'core:dashboard:comptabilite-dashboard',
            'core:dashboard:super-admin-dashboard',
        ):
            with self.subTest(route=route):
                response = client.get(reverse(route))
                self.assertRedirects(
                    response, reverse('core:pending-approval'),
                    fetch_redirect_response=False,
                )

    def test_completion_records_requested_role_without_assigning_it(self):
        with patch('core.clerk.get_clerk_client') as get_client:
            get_client.return_value.users.get.return_value = fake_clerk_user(
                'clerk4@test.local'
            )
            user, _ = sync_clerk_user(
                {'sub': 'user_clerk_4', 'email': 'clerk4@test.local'}
            )

        client = self.client_for(user)
        pending_page = client.get(reverse('core:pending-approval'))
        self.assertRedirects(
            pending_page, reverse('core:complete-access-request'),
            fetch_redirect_response=False,
        )

        response = client.post(reverse('core:complete-access-request'), {
            'first_name': 'Clerk',
            'last_name': 'Signup',
            'phone': '+242060000099',
            'requested_role': RoleKey.COMPTABLE,
        })
        self.assertRedirects(
            response, reverse('core:pending-approval'),
            fetch_redirect_response=False,
        )

        user.refresh_from_db()
        access_request = user.pending_access_request
        self.assertEqual(access_request.requested_role, RoleKey.COMPTABLE)
        self.assertEqual(access_request.assigned_role, '')
        self.assertFalse(user.roles.exists())
        self.assertEqual(user.account_status, AccountStatus.PENDING_APPROVAL)
        self.assertTrue(AuditLog.objects.filter(
            action='ACCESS_REQUEST_SUBMIT', entity_id=str(access_request.id)
        ).exists())

    def test_completion_refuses_privileged_role_from_browser(self):
        with patch('core.clerk.get_clerk_client') as get_client:
            get_client.return_value.users.get.return_value = fake_clerk_user(
                'clerk5@test.local'
            )
            user, _ = sync_clerk_user(
                {'sub': 'user_clerk_5', 'email': 'clerk5@test.local'}
            )

        client = self.client_for(user)
        response = client.post(reverse('core:complete-access-request'), {
            'first_name': 'Clerk',
            'last_name': 'Signup',
            'requested_role': RoleKey.SUPER_ADMIN,
        })
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.pending_access_request.requested_role, '')
        self.assertFalse(user.roles.exists())


class RegistrationTests(BusinessTestBase):
    def test_registered_user_has_no_effective_role_and_no_access(self):
        response = self.client.post(reverse('core:register'), {
            'first_name': 'Paul',
            'last_name': 'Mpassi',
            'email': 'paul@test.local',
            'requested_role': RoleKey.FORMATEUR,
            'password': 'PaulPass123!',
            'password_confirm': 'PaulPass123!',
        })
        self.assertRedirects(
            response, reverse('core:pending-approval'),
            fetch_redirect_response=False,
        )
        user = User.objects.get(email='paul@test.local')
        self.assertFalse(user.roles.exists())
        self.assertEqual(
            user.pending_access_request.requested_role, RoleKey.FORMATEUR
        )

        for route in (
            'core:dashboard:formateur-dashboard',
            'core:dashboard:comptabilite-dashboard',
            'core:dashboard:super-admin-dashboard',
        ):
            with self.subTest(route=route):
                self.assertRedirects(
                    self.client.get(reverse(route)),
                    reverse('core:pending-approval'),
                    fetch_redirect_response=False,
                )

    def test_registration_requires_a_role(self):
        response = self.client.post(reverse('core:register'), {
            'first_name': 'Sans',
            'last_name': 'Role',
            'email': 'sansrole@test.local',
            'password': 'SansRolePass123!',
            'password_confirm': 'SansRolePass123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email='sansrole@test.local').exists())


class AccessApprovalTests(BusinessTestBase):
    def setUp(self):
        self.pending = User.objects.create_user(
            email='postulant@test.local',
            password='Postulant123!',
            first_name='Postulant',
            last_name='Test',
            clerk_user_id='user_pending_123',
        )
        self.access_request = AccessRequest.objects.create(
            user=self.pending, requested_role=RoleKey.FORMATEUR,
        )

    def approve(self, role_key, note='Dossier conforme'):
        return self.client_for(self.super_admin).post(
            reverse('core:dashboard:access-request-review',
                    args=[self.access_request.id]),
            {'decision': 'approve', 'role_key': role_key, 'note': note},
        )

    def test_review_screen_never_defaults_to_super_admin(self):
        response = self.client_for(self.super_admin).get(
            reverse('core:dashboard:access-requests'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'value="SUPER_ADMIN"')
        self.assertNotContains(response, 'value="ADMIN"')
        self.assertContains(response, 'value="FORMATEUR" selected')
        self.assertContains(response, 'user_pending_123')

    def test_approval_assigns_only_the_selected_role(self):
        response = self.approve(RoleKey.FORMATEUR)
        self.assertRedirects(
            response, reverse('core:dashboard:access-requests'),
            fetch_redirect_response=False,
        )

        self.access_request.refresh_from_db()
        self.pending.refresh_from_db()
        self.assertEqual(
            self.access_request.status, AccessRequest.Status.APPROVED
        )
        self.assertEqual(self.access_request.assigned_role, RoleKey.FORMATEUR)
        self.assertEqual(self.access_request.reviewed_by, self.super_admin)
        self.assertIsNotNone(self.access_request.reviewed_at)
        self.assertEqual(self.pending.account_status, AccountStatus.ACTIVE)
        self.assertTrue(self.pending.has_role(RoleKey.FORMATEUR))
        self.assertFalse(self.pending.has_role(RoleKey.SUPER_ADMIN))
        self.assertFalse(self.pending.has_role(RoleKey.ADMIN))
        self.assertTrue(self.pending.internal_code.startswith('UA-FRM'))
        self.assertTrue(Notification.objects.filter(
            user=self.pending,
            notification_type=Notification.Type.ACCOUNT_APPROVED,
        ).exists())

        audit = AuditLog.objects.get(
            action='ACCESS_APPROVE', entity_id=str(self.access_request.id)
        )
        self.assertEqual(audit.after_summary['assigned_role'], RoleKey.FORMATEUR)
        self.assertEqual(
            audit.after_summary['requested_role'], RoleKey.FORMATEUR
        )
        self.assertEqual(audit.after_summary['request_status'], 'APPROVED')

    def test_approved_teacher_reaches_only_teacher_dashboard(self):
        self.approve(RoleKey.FORMATEUR)
        client = self.client_for(self.pending)
        self.assertEqual(
            client.get(reverse('core:dashboard:formateur-dashboard')).status_code,
            200,
        )
        self.assertEqual(
            client.get(reverse(
                'core:dashboard:comptabilite-dashboard')).status_code,
            403,
        )
        self.assertEqual(
            client.get(reverse(
                'core:dashboard:super-admin-dashboard')).status_code,
            403,
        )

    def test_approval_refuses_privileged_roles_from_post(self):
        for role_key in (RoleKey.SUPER_ADMIN, RoleKey.ADMIN, ''):
            with self.subTest(role_key=role_key):
                response = self.approve(role_key)
                self.assertRedirects(
                    response, reverse('core:dashboard:access-requests'),
                    fetch_redirect_response=False,
                )
                self.access_request.refresh_from_db()
                self.pending.refresh_from_db()
                self.assertEqual(
                    self.access_request.status, AccessRequest.Status.PENDING
                )
                self.assertEqual(self.access_request.assigned_role, '')
                self.assertFalse(self.pending.roles.exists())
                self.assertEqual(
                    self.pending.account_status,
                    AccountStatus.PENDING_APPROVAL,
                )
                self.assertFalse(AuditLog.objects.filter(
                    action='ACCESS_APPROVE',
                    entity_id=str(self.access_request.id),
                ).exists())

    def test_admin_can_approve_with_suggested_role(self):
        response = self.client_for(self.admin).post(
            reverse('core:dashboard:access-request-review',
                    args=[self.access_request.id]),
            {'decision': 'approve', 'role_key': RoleKey.FORMATEUR},
        )
        self.assertRedirects(
            response, reverse('core:dashboard:access-requests'),
            fetch_redirect_response=False,
        )
        self.access_request.refresh_from_db()
        self.assertEqual(
            self.access_request.status, AccessRequest.Status.APPROVED
        )
        self.assertEqual(self.access_request.reviewed_by, self.admin)

    def test_admin_can_modify_suggested_role_on_approval(self):
        response = self.client_for(self.admin).post(
            reverse('core:dashboard:access-request-review',
                    args=[self.access_request.id]),
            {'decision': 'approve', 'role_key': RoleKey.COMPTABLE},
        )
        self.assertRedirects(
            response, reverse('core:dashboard:access-requests'),
            fetch_redirect_response=False,
        )
        self.access_request.refresh_from_db()
        self.pending.refresh_from_db()
        self.assertEqual(self.access_request.assigned_role, RoleKey.COMPTABLE)
        self.assertTrue(self.pending.has_role(RoleKey.COMPTABLE))
        self.assertTrue(self.pending.internal_code.startswith('UA-CPT'))

    def test_admin_review_refuses_privileged_roles(self):
        response = self.client_for(self.admin).post(
            reverse('core:dashboard:access-request-review',
                    args=[self.access_request.id]),
            {'decision': 'approve', 'role_key': RoleKey.ADMIN},
        )
        self.assertRedirects(
            response, reverse('core:dashboard:access-requests'),
            fetch_redirect_response=False,
        )
        self.access_request.refresh_from_db()
        self.assertEqual(
            self.access_request.status, AccessRequest.Status.PENDING
        )
        self.assertFalse(self.pending.roles.exists())

    def test_admin_sees_suggested_role_on_review_list(self):
        response = self.client_for(self.admin).get(
            reverse('core:dashboard:access-requests'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="FORMATEUR" selected')
        self.assertContains(response, 'Approuver')

    def test_approved_student_appears_in_inscrits_for_comptable(self):
        self.access_request.requested_role = RoleKey.ETUDIANT
        self.access_request.save(update_fields=['requested_role'])
        self.approve(RoleKey.ETUDIANT)
        self.pending.refresh_from_db()
        response = self.client_for(self.comptable).get(
            reverse('core:dashboard:student-list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Postulant Test')
        self.assertTrue(
            self.pending.internal_code.startswith('UA-ETU'))

    def test_rejection_blocks_access_and_keeps_trace(self):
        response = self.client_for(self.super_admin).post(
            reverse('core:dashboard:access-request-review',
                    args=[self.access_request.id]),
            {'decision': 'reject', 'note': 'Dossier incomplet'},
        )
        self.assertRedirects(
            response, reverse('core:dashboard:access-requests'),
            fetch_redirect_response=False,
        )
        self.access_request.refresh_from_db()
        self.pending.refresh_from_db()
        self.assertEqual(
            self.access_request.status, AccessRequest.Status.REJECTED
        )
        self.assertEqual(self.access_request.assigned_role, '')
        self.assertEqual(self.access_request.decision_note, 'Dossier incomplet')
        self.assertEqual(self.pending.account_status, AccountStatus.REJECTED)
        self.assertFalse(self.pending.roles.exists())

        client = self.client_for(self.pending)
        self.assertRedirects(
            client.get(reverse('core:dashboard:formateur-dashboard')),
            reverse('core:access-denied'),
            fetch_redirect_response=False,
        )
        audit = AuditLog.objects.get(
            action='ACCESS_REJECT', entity_id=str(self.access_request.id)
        )
        self.assertEqual(audit.after_summary['request_status'], 'REJECTED')
        self.assertEqual(audit.after_summary['note'], 'Dossier incomplet')

    def test_processed_request_cannot_be_approved_again(self):
        self.approve(RoleKey.FORMATEUR)
        response = self.approve(RoleKey.COMPTABLE)
        self.assertRedirects(
            response, reverse('core:dashboard:access-requests'),
            fetch_redirect_response=False,
        )
        self.pending.refresh_from_db()
        self.access_request.refresh_from_db()
        self.assertEqual(self.access_request.assigned_role, RoleKey.FORMATEUR)
        self.assertEqual(
            list(self.pending.roles.values_list('key', flat=True)),
            [RoleKey.FORMATEUR],
        )

    def test_super_admin_cannot_review_own_request(self):
        own = AccessRequest.objects.create(
            user=self.super_admin, requested_role=RoleKey.FORMATEUR,
        )
        response = self.client_for(self.super_admin).post(
            reverse('core:dashboard:access-request-review', args=[own.id]),
            {'decision': 'approve', 'role_key': RoleKey.FORMATEUR},
        )
        self.assertEqual(response.status_code, 403)
        own.refresh_from_db()
        self.assertEqual(own.status, AccessRequest.Status.PENDING)

    def test_non_super_admin_cannot_review_requests(self):
        response = self.client_for(self.formateur).post(
            reverse('core:dashboard:access-request-review',
                    args=[self.access_request.id]),
            {'decision': 'approve', 'role_key': RoleKey.SUPER_ADMIN},
        )
        self.assertEqual(response.status_code, 403)
        self.access_request.refresh_from_db()
        self.assertEqual(
            self.access_request.status, AccessRequest.Status.PENDING
        )
        self.assertFalse(self.pending.roles.exists())


class RoleTamperingTests(BusinessTestBase):
    def test_regular_user_cannot_assign_roles(self):
        client = self.client_for(self.formateur)
        response = client.post(
            reverse('core:dashboard:user-role-assign',
                    args=[self.formateur.id]),
            {'role_key': RoleKey.SUPER_ADMIN, 'action': 'add'},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.formateur.has_role(RoleKey.SUPER_ADMIN))

    def test_super_admin_cannot_change_own_roles(self):
        client = self.client_for(self.super_admin)
        response = client.post(
            reverse('core:dashboard:user-role-assign',
                    args=[self.super_admin.id]),
            {'role_key': RoleKey.SUPER_ADMIN, 'action': 'remove'},
        )
        self.assertEqual(response.status_code, 403)
        self.super_admin.refresh_from_db()
        self.assertTrue(self.super_admin.has_role(RoleKey.SUPER_ADMIN))

    def test_profile_form_cannot_change_role_or_status(self):
        client = self.client_for(self.formateur)
        response = client.post(reverse('core:dashboard:profile'), {
            'action': 'profile',
            'first_name': 'Formateur',
            'last_name': 'Modifie',
            'display_name': '',
            'phone': '',
            'address': '',
            'roles': [RoleKey.SUPER_ADMIN],
            'role_key': RoleKey.SUPER_ADMIN,
            'account_status': AccountStatus.SUSPENDED,
            'is_superuser': 'on',
        })
        self.assertRedirects(
            response, reverse('core:dashboard:profile'),
            fetch_redirect_response=False,
        )
        self.formateur.refresh_from_db()
        self.assertFalse(self.formateur.has_role(RoleKey.SUPER_ADMIN))
        self.assertEqual(self.formateur.account_status, AccountStatus.ACTIVE)
        self.assertFalse(self.formateur.is_superuser)

    def test_pending_rejected_and_suspended_accounts_are_blocked(self):
        cases = (
            (AccountStatus.PENDING_APPROVAL, 'core:pending-approval'),
            (AccountStatus.SUSPENDED, 'core:access-denied'),
            (AccountStatus.REJECTED, 'core:access-denied'),
            (AccountStatus.DISABLED, 'core:access-denied'),
        )
        for index, (status, destination) in enumerate(cases):
            user = self.make_user(
                RoleKey.FORMATEUR, f'bloque{index}@test.local', status=status,
            )
            with self.subTest(status=status):
                response = self.client_for(user).get(
                    reverse('core:dashboard:formateur-dashboard'))
                self.assertRedirects(
                    response, reverse(destination),
                    fetch_redirect_response=False,
                )

    def test_open_session_is_rechecked_after_suspension(self):
        client = self.client_for(self.formateur)
        self.assertEqual(
            client.get(reverse('core:dashboard:formateur-dashboard')).status_code,
            200,
        )
        self.formateur.account_status = AccountStatus.SUSPENDED
        self.formateur.save(update_fields=['account_status'])
        self.assertRedirects(
            client.get(reverse('core:dashboard:formateur-dashboard')),
            reverse('core:access-denied'),
            fetch_redirect_response=False,
        )

    def test_approval_takes_effect_without_relogin(self):
        pending = User.objects.create_user(
            email='sansrelogin@test.local',
            password=TEST_PASSWORD,
        )
        access_request = AccessRequest.objects.create(
            user=pending, requested_role=RoleKey.ETUDIANT,
        )
        client = self.client_for(pending)
        self.assertRedirects(
            client.get(reverse('core:dashboard:etudiant-dashboard')),
            reverse('core:pending-approval'),
            fetch_redirect_response=False,
        )

        self.client_for(self.super_admin).post(
            reverse('core:dashboard:access-request-review',
                    args=[access_request.id]),
            {'decision': 'approve', 'role_key': RoleKey.ETUDIANT},
        )
        self.assertEqual(
            client.get(reverse('core:dashboard:etudiant-dashboard')).status_code,
            200,
        )

    def test_genuine_super_admin_keeps_full_access(self):
        client = self.client_for(self.super_admin)
        for route in (
            'core:dashboard:super-admin-dashboard',
            'core:dashboard:user-list',
            'core:dashboard:access-requests',
            'core:dashboard:audit-log',
        ):
            with self.subTest(route=route):
                self.assertEqual(client.get(reverse(route)).status_code, 200)
