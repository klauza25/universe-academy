"""Tests transverses des permissions et du routage des dashboards."""
from django.urls import reverse

from core.models import RoleKey

from .base import BusinessTestBase


class DashboardRoutingTests(BusinessTestBase):
    def test_dashboard_router_redirects_each_role(self):
        for user in (
            self.super_admin, self.admin, self.direction, self.secretaire,
            self.comptable, self.peda, self.formateur, self.etudiant,
            self.accueil,
        ):
            with self.subTest(role=user.primary_role):
                client = self.client_for(user)
                response = client.get(
                    reverse('core:dashboard:dashboard-router'))
                self.assertRedirects(
                    response, reverse(user.dashboard_route),
                    fetch_redirect_response=False,
                )

    def test_each_role_dashboard_renders(self):
        pairs = (
            (self.super_admin, 'core:dashboard:super-admin-dashboard'),
            (self.admin, 'core:dashboard:admin-dashboard'),
            (self.direction, 'core:dashboard:direction-dashboard'),
            (self.secretaire, 'core:dashboard:secretaire-dashboard'),
            (self.comptable, 'core:dashboard:comptabilite-dashboard'),
            (self.peda, 'core:dashboard:resp-peda-dashboard'),
            (self.formateur, 'core:dashboard:formateur-dashboard'),
            (self.etudiant, 'core:dashboard:etudiant-dashboard'),
            (self.accueil, 'core:dashboard:accueil-dashboard'),
        )
        for user, route in pairs:
            with self.subTest(role=user.primary_role):
                client = self.client_for(user)
                response = client.get(reverse(route))
                self.assertEqual(response.status_code, 200)


class PermissionBoundaryTests(BusinessTestBase):
    def test_cross_role_access_is_forbidden(self):
        cases = (
            (self.formateur, 'core:dashboard:journal'),
            (self.secretaire, 'core:dashboard:accounts'),
            (self.etudiant, 'core:dashboard:student-list'),
            (self.accueil, 'core:dashboard:programs'),
            (self.comptable, 'core:dashboard:audit-log'),
            (self.direction, 'core:dashboard:audit-log'),
            (self.formateur, 'core:dashboard:visit-list'),
        )
        for user, route in cases:
            with self.subTest(role=user.primary_role, route=route):
                client = self.client_for(user)
                response = client.get(reverse(route))
                self.assertEqual(response.status_code, 403)

    def test_super_admin_has_access_everywhere(self):
        client = self.client_for(self.super_admin)
        for route in (
            'core:dashboard:audit-log',
            'core:dashboard:journal',
            'core:dashboard:accounts',
            'core:dashboard:student-list',
            'core:dashboard:programs',
            'core:dashboard:visit-list',
        ):
            with self.subTest(route=route):
                self.assertEqual(
                    client.get(reverse(route)).status_code, 200)

    def test_super_admin_and_admin_can_list_users(self):
        for user in (self.super_admin, self.admin):
            client = self.client_for(user)
            self.assertEqual(
                client.get(reverse('core:dashboard:user-list')).status_code,
                200,
            )
        client = self.client_for(self.secretaire)
        self.assertEqual(
            client.get(reverse('core:dashboard:user-list')).status_code, 403)

    def test_profile_requires_authentication(self):
        response = self.client.get(reverse('core:dashboard:profile'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('core:login'), response['Location'])

    def test_student_sees_his_own_dashboard_only(self):
        client = self.client_for(self.etudiant)
        self.assertEqual(
            client.get(reverse('core:dashboard:student-resources')).status_code,
            200,
        )
        self.assertEqual(
            client.get(reverse('core:dashboard:student-attendance')).status_code,
            200,
        )
        self.assertEqual(
            client.get(reverse('core:dashboard:programs')).status_code, 403)
        self.assertEqual(
            client.get(reverse('core:dashboard:payment-create')).status_code,
            403,
        )

    def test_new_user_without_role_has_no_dashboard_access(self):
        user = self.make_user(RoleKey.ACCUEIL, 'sansrole@test.local')
        # On retire le rôle pour simuler un compte sans habilitation.
        user.roles.clear()
        client = self.client_for(user)
        response = client.get(reverse('core:dashboard:dashboard-router'))
        self.assertRedirects(
            response, reverse('core:home'), fetch_redirect_response=False,
        )
        self.assertEqual(
            client.get(reverse('core:dashboard:accueil-dashboard')).status_code,
            403,
        )
