"""Accès transversal du rôle ADMIN : tout consulter, mutations sensibles réservées.

Politique :
- l'ADMIN peut ouvrir chaque module (finances, étudiants, pédagogie,
  accueil/prospects, audit, utilisateurs…) en lecture ;
- les opérations les plus sensibles (créer un compte, attribuer un rôle,
  valider une demande d'accès) restent réservées au SUPER_ADMIN.
"""
from datetime import time as dt_time

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.models import (
    AccountStatus, AccessRequest, Payment, RoleKey, SessionRecord,
    StudentDocument,
)

from .base import BusinessTestBase


class AdminGlobalReadTests(BusinessTestBase):
    """L'ADMIN doit pouvoir visiter tous les modules."""

    def setUp(self):
        super().setUp()
        self.payment = Payment.objects.create(
            enrollment=self.enrollment,
            amount=7000,
            method=Payment.Method.CASH,
            recorded_by=self.comptable,
        )
        self.record = SessionRecord.objects.create(
            session=self.session,
            module=self.module,
            lesson=self.lesson,
            date=self.today,
            planned_start=dt_time(8, 0),
            planned_end=dt_time(10, 0),
            topic='Séance de test',
            status=SessionRecord.Status.PLANNED,
            recorded_by=self.formateur,
        )
        self.client = self.client_for(self.admin)

    def test_admin_reads_every_module(self):
        cases = (
            # Finances
            ('core:dashboard:comptabilite-dashboard', ()),
            ('core:dashboard:journal', ()),
            ('core:dashboard:accounts', ()),
            ('core:dashboard:closures', ()),
            # Étudiants / secrétariat
            ('core:dashboard:secretaire-dashboard', ()),
            ('core:dashboard:student-list', ()),
            ('core:dashboard:enrollment-detail', (self.enrollment.id,)),
            # Pédagogie
            ('core:dashboard:programs', ()),
            ('core:dashboard:session-records', ()),
            ('core:dashboard:attendance-history', ()),
            ('core:dashboard:progression', ()),
            ('core:dashboard:resources', ()),
            # Accueil / prospects
            ('core:dashboard:accueil-dashboard', ()),
            ('core:dashboard:visit-list', ()),
            ('core:dashboard:prospect-list', ()),
            ('core:dashboard:visit-reasons', ()),
            # Pilotage / supervision
            ('core:dashboard:direction-dashboard', ()),
            ('core:dashboard:user-list', ()),
            ('core:dashboard:user-detail', (self.etudiant.id,)),
            ('core:dashboard:access-requests', ()),
            ('core:dashboard:audit-log', ()),
            ('core:dashboard:scholarship-review-list', ()),
        )
        for name, args in cases:
            with self.subTest(route=name):
                response = self.client.get(reverse(name, args=args))
                self.assertEqual(
                    response.status_code, 200,
                    f"L'ADMIN ne peut pas ouvrir {name}",
                )

    def test_admin_views_payment_receipt(self):
        response = self.client.get(reverse(
            'core:dashboard:payment-receipt', args=[self.payment.id]))
        self.assertEqual(response.status_code, 200)

    def test_admin_downloads_student_document(self):
        document = StudentDocument.objects.create(
            student=self.etudiant,
            uploaded_by=self.secretaire,
            doc_type=StudentDocument.DocType.IDENTITY,
            file=SimpleUploadedFile('piece.pdf', b'contenu'),
        )
        response = self.client.get(reverse(
            'core:dashboard:student-document-download',
            args=[document.id]))
        self.assertEqual(response.status_code, 200)

    def test_admin_sees_full_resource_catalog(self):
        # L'admin est traité comme gestionnaire : il voit tous les fichiers
        # ( filtrage « mes cours » réservé aux formateurs ).
        response = self.client.get(reverse('core:dashboard:resources'))
        self.assertEqual(response.status_code, 200)


class AdminRestrictedWriteTests(BusinessTestBase):
    """Les mutations sensibles restent SUPER_ADMIN."""

    def setUp(self):
        self.client = self.client_for(self.admin)

    def test_admin_cannot_create_users(self):
        response = self.client.get(reverse('core:dashboard:user-create'))
        self.assertEqual(response.status_code, 403)

    def test_admin_cannot_edit_users(self):
        response = self.client.get(reverse(
            'core:dashboard:user-edit', args=[self.secretaire.id]))
        self.assertEqual(response.status_code, 403)

    def test_admin_cannot_assign_roles(self):
        response = self.client.post(reverse(
            'core:dashboard:user-role-assign', args=[self.secretaire.id]),
            {'role_key': RoleKey.COMPTABLE, 'action': 'add'},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.secretaire.has_role(RoleKey.COMPTABLE))

    def test_admin_can_review_access_requests(self):
        applicant = self.make_user(
            RoleKey.ETUDIANT, 'demande@test.local',
            status=AccountStatus.PENDING_APPROVAL,
        )
        access_request = AccessRequest.objects.create(
            user=applicant, requested_role=RoleKey.ETUDIANT,
        )
        response = self.client.post(reverse(
            'core:dashboard:access-request-review',
            args=[access_request.id]),
            {'decision': 'approve', 'role_key': RoleKey.ETUDIANT})
        self.assertRedirects(
            response, reverse('core:dashboard:access-requests'),
            fetch_redirect_response=False,
        )
        applicant.refresh_from_db()
        access_request.refresh_from_db()
        self.assertEqual(applicant.account_status, AccountStatus.ACTIVE)
        self.assertEqual(
            access_request.status, AccessRequest.Status.APPROVED)


class SuperAdminKeepsExclusiveActionsTests(BusinessTestBase):
    def test_super_admin_still_accredited_everywhere(self):
        client = self.client_for(self.super_admin)
        for route in (
            'core:dashboard:user-create',
            'core:dashboard:access-requests',
            'core:dashboard:audit-log',
            'core:dashboard:journal',
            'core:dashboard:student-list',
        ):
            with self.subTest(route=route):
                self.assertEqual(
                    client.get(reverse(route)).status_code, 200)
