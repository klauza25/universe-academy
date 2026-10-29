"""Tests transverses des permissions et du routage des dashboards."""
from datetime import time as dt_time

from django.urls import reverse

from core.models import (
    AccessEvent, AccessRequest, Attendance, AuditLog, CashAccount,
    CashTransaction, Contact, Destination, Module, Payment, Prospect,
    Resource, RoleKey, ScholarshipApplication, SessionRecord, Visit,
    VisitReason,
)

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


class AdminTransversalAccessTests(BusinessTestBase):
    """L'ADMIN lit tous les modules ; les actes sensibles restent au SUPER_ADMIN."""

    MODULE_ROUTES = (
        'core:dashboard:journal',
        'core:dashboard:accounts',
        'core:dashboard:student-list',
        'core:dashboard:programs',
        'core:dashboard:visit-list',
        'core:dashboard:audit-log',
        'core:dashboard:access-requests',
        'core:dashboard:scholarship-review-list',
        'core:dashboard:direction-dashboard',
        'core:dashboard:secretaire-dashboard',
        'core:dashboard:comptabilite-dashboard',
        'core:dashboard:accueil-dashboard',
    )

    def test_admin_can_read_every_module(self):
        client = self.client_for(self.admin)
        for route in self.MODULE_ROUTES:
            with self.subTest(route=route):
                self.assertEqual(client.get(reverse(route)).status_code, 200)

    def test_admin_reads_student_and_finance_records(self):
        payment = Payment.objects.create(
            enrollment=self.enrollment,
            amount=10000,
            method=Payment.Method.CASH,
            recorded_by=self.comptable,
        )
        transaction = CashTransaction.objects.create(
            reference='TX-ADMIN-VISIBILITE',
            tx_type=CashTransaction.Type.IN,
            category=self.income_category,
            label='Paiement de test',
            amount=10000,
            account=self.cash,
            created_by=self.comptable,
        )
        client = self.client_for(self.admin)
        read_routes = (
            ('student-detail', [self.etudiant.id]),
            ('enrollment-detail', [self.enrollment.id]),
            ('transaction-detail', [transaction.id]),
            ('payment-receipt', [payment.id]),
        )
        for name, args in read_routes:
            with self.subTest(route=name):
                response = client.get(
                    reverse(f'core:dashboard:{name}', args=args))
                self.assertEqual(response.status_code, 200)
        receipt = client.get(reverse('core:dashboard:payment-receipt',
                                     args=[payment.id]))
        self.assertContains(receipt, payment.reference)

    def test_admin_cannot_open_business_write_forms(self):
        client = self.client_for(self.admin)
        write_routes = (
            ('student-edit', [self.etudiant.id]),
            ('enrollment-edit', [self.enrollment.id]),
            ('payment-create', []),
            ('transaction-create', []),
            ('closure-create', []),
            ('student-create', []),
            ('enrollment-create', []),
            ('visit-create', []),
            ('prospect-create', []),
            ('module-create', []),
            ('lesson-create', []),
            ('resource-create', []),
        )
        for name, args in write_routes:
            with self.subTest(route=name):
                response = client.get(
                    reverse(f'core:dashboard:{name}', args=args))
                self.assertEqual(response.status_code, 403)

    def test_admin_dashboard_exposes_finance_and_students(self):
        Payment.objects.create(
            enrollment=self.enrollment,
            amount=25000,
            method=Payment.Method.CASH,
            recorded_by=self.comptable,
        )
        for account in (self.admin, self.super_admin):
            with self.subTest(role=account.primary_role):
                response = self.client_for(account).get(
                    reverse('core:dashboard:admin-dashboard'))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Solde des caisses')
                self.assertContains(response, 'Reste à recouvrer')
                self.assertContains(response, 'Étudiants actifs')

    def test_admin_cannot_create_or_edit_users(self):
        client = self.client_for(self.admin)
        self.assertEqual(
            client.get(reverse('core:dashboard:user-create')).status_code, 403)
        self.assertEqual(
            client.get(reverse(
                'core:dashboard:user-edit', args=[self.secretaire.id]
            )).status_code,
            403,
        )

    def test_admin_cannot_assign_roles(self):
        client = self.client_for(self.admin)
        response = client.post(
            reverse('core:dashboard:user-role-assign',
                    args=[self.secretaire.id]),
            {'role_key': RoleKey.COMPTABLE, 'action': 'add'},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            self.secretaire.roles.filter(key=RoleKey.COMPTABLE).exists())

    def test_admin_cannot_review_access_request(self):
        pending = AccessRequest.objects.create(
            user=self.make_user(RoleKey.ETUDIANT, 'enattente@test.local'),
            requested_role=RoleKey.ETUDIANT,
        )
        client = self.client_for(self.admin)
        response = client.post(
            reverse('core:dashboard:access-request-review', args=[pending.id]),
            {'decision': 'approve', 'role_key': RoleKey.ETUDIANT},
        )
        self.assertEqual(response.status_code, 403)
        pending.refresh_from_db()
        self.assertEqual(pending.status, AccessRequest.Status.PENDING)

    def test_admin_user_screens_hide_super_admin_actions(self):
        client = self.client_for(self.admin)
        listing = client.get(reverse('core:dashboard:user-list'))
        self.assertNotContains(
            listing, reverse('core:dashboard:user-create'))
        self.assertNotContains(
            listing, reverse('core:dashboard:user-edit',
                             args=[self.secretaire.id]))
        detail = client.get(
            reverse('core:dashboard:user-detail', args=[self.secretaire.id]))
        self.assertNotContains(
            detail, reverse('core:dashboard:user-edit',
                            args=[self.secretaire.id]))
        pending = AccessRequest.objects.create(
            user=self.make_user(RoleKey.ETUDIANT, 'enattente2@test.local'),
            requested_role=RoleKey.ETUDIANT,
        )
        reviews = client.get(reverse('core:dashboard:access-requests'))
        self.assertNotContains(
            reviews,
            reverse('core:dashboard:access-request-review', args=[pending.id]),
        )
        self.assertContains(reviews, 'Validation réservée au super administrateur')

    def test_super_admin_keeps_sensitive_actions(self):
        client = self.client_for(self.super_admin)
        self.assertEqual(
            client.get(reverse('core:dashboard:user-create')).status_code, 200)
        listing = client.get(reverse('core:dashboard:user-list'))
        self.assertContains(listing, reverse('core:dashboard:user-create'))

    def test_admin_user_screens_expose_module_navigation(self):
        response = self.client_for(self.admin).get(
            reverse('core:dashboard:user-list'))
        self.assertContains(response, reverse('core:dashboard:journal'))
        self.assertContains(response, reverse('core:dashboard:programs'))


class ElevatedReadOnlyBusinessTests(BusinessTestBase):
    """SUPER_ADMIN et ADMIN voient tout sans écrire dans le métier.

    Seuls les comptes, rôles, demandes d'accès et bourses restent
    administrables : transactions, étudiants, inscriptions, présences,
    visites, prospects et ressources sont en consultation seule.
    """

    CONSULTATION_ONLY = (
        'Consultation seule : cette action relève du rôle métier.'
    )

    def setUp(self):
        self.contact = Contact.objects.create(
            first_name='Awa', last_name='Diallo', phone='+221770000000',
        )
        self.visit = Visit.objects.create(
            contact=self.contact,
            reason=self.visit_reason,
            agent=self.accueil,
            status=Visit.Status.IN_PROGRESS,
        )
        self.prospect = Prospect.objects.create(
            contact=self.contact,
            course=self.course,
            agent=self.accueil,
            status=Prospect.Status.NEW,
        )
        self.transaction = CashTransaction.objects.create(
            tx_type=CashTransaction.Type.IN,
            category=self.income_category,
            label='Encaissement test',
            amount=5000,
            account=self.cash,
            status=CashTransaction.Status.VALIDATED,
            created_by=self.comptable,
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
        self.resource = Resource.objects.create(
            title='Support de test',
            course=self.course,
            kind=Resource.Kind.COURSE,
            status=Resource.Status.PUBLISHED,
            author=self.formateur,
            html_content='<p>Contenu</p>',
        )

    def test_elevated_roles_cannot_open_business_write_forms(self):
        cases = (
            ('student-create', []),
            ('student-edit', [self.etudiant.id]),
            ('enrollment-create', []),
            ('enrollment-edit', [self.enrollment.id]),
            ('payment-create', []),
            ('transaction-create', []),
            ('closure-create', []),
            ('visit-create', []),
            ('prospect-create', []),
            ('module-create', []),
            ('module-edit', [self.module.id]),
            ('lesson-create', []),
            ('lesson-edit', [self.lesson.id]),
            ('resource-create', []),
            ('resource-edit', [self.resource.id]),
            ('session-record-create', [self.session.id]),
        )
        for user in (self.super_admin, self.admin):
            for name, args in cases:
                with self.subTest(role=user.primary_role, route=name):
                    response = self.client_for(user).post(
                        reverse(f'core:dashboard:{name}', args=args), {})
                    self.assertEqual(response.status_code, 403)
                    self.assertContains(
                        response, self.CONSULTATION_ONLY, status_code=403,
                    )

    def test_elevated_roles_cannot_post_mixed_views(self):
        cases = (
            ('visit-detail', [self.visit.id]),
            ('visit-departure', [self.visit.id]),
            ('visit-to-prospect', [self.visit.id]),
            ('prospect-detail', [self.prospect.id]),
            ('visit-reasons', []),
            ('visit-reason-toggle', [self.visit_reason.id]),
            ('accueil-dashboard', []),
            ('accounts', []),
            ('transaction-detail', [self.transaction.id]),
            ('formateur-attendance', [self.session.id]),
        )
        for user in (self.super_admin, self.admin):
            for name, args in cases:
                with self.subTest(role=user.primary_role, route=name):
                    response = self.client_for(user).post(
                        reverse(f'core:dashboard:{name}', args=args), {})
                    self.assertEqual(response.status_code, 403)
                    self.assertContains(
                        response, self.CONSULTATION_ONLY, status_code=403,
                    )

    def test_elevated_roles_cannot_record_attendance(self):
        for user in (self.super_admin, self.admin):
            with self.subTest(role=user.primary_role):
                response = self.client_for(user).post(
                    reverse('core:dashboard:session-record-attendance',
                            args=[self.record.id]),
                    {f'status_{self.enrollment.id}': 'PRESENT'},
                )
                self.assertEqual(response.status_code, 403)

    def test_denied_actions_leave_business_data_untouched(self):
        payload_cases = (
            ('transaction-detail', [self.transaction.id],
             {'action': 'cancel', 'reason': 'Erreur de saisie'}),
            ('accounts', [],
             {'name': 'Caisse pirate', 'kind': CashAccount.Kind.CASH}),
            ('visit-detail', [self.visit.id],
             {'status': Visit.Status.COMPLETED}),
            ('prospect-detail', [self.prospect.id],
             {'action': 'follow_up', 'contact_type': 'PHONE',
              'phone_used': self.contact.phone}),
            ('visit-reasons', [], {'label': 'Motif pirate'}),
            ('accueil-dashboard', [], {}),
            ('module-create', [], {'title': 'Module pirate',
                                   'course': self.course.pk, 'order': 9}),
        )
        before = {
            'accounts': CashAccount.objects.count(),
            'reasons': VisitReason.objects.count(),
            'modules': Module.objects.count(),
            'attendance': Attendance.objects.count(),
        }
        for user in (self.super_admin, self.admin):
            for name, args, payload in payload_cases:
                with self.subTest(role=user.primary_role, route=name):
                    self.client_for(user).post(
                        reverse(f'core:dashboard:{name}', args=args), payload)

        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.status,
                         CashTransaction.Status.VALIDATED)
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.status, Visit.Status.IN_PROGRESS)
        self.assertFalse(self.visit.departure_at)
        self.prospect.refresh_from_db()
        self.assertEqual(self.prospect.status, Prospect.Status.NEW)
        self.assertFalse(self.prospect.follow_ups.exists())
        self.assertEqual(CashAccount.objects.count(), before['accounts'])
        self.assertEqual(VisitReason.objects.count(), before['reasons'])
        self.assertEqual(Module.objects.count(), before['modules'])
        self.assertEqual(Attendance.objects.count(), before['attendance'])
        self.assertFalse(AccessEvent.objects.exists())

    def test_business_screens_hide_write_controls_for_elevated(self):
        client = self.client_for(self.super_admin)

        transaction = client.get(reverse(
            'core:dashboard:transaction-detail', args=[self.transaction.id]))
        self.assertEqual(transaction.status_code, 200)
        self.assertContains(
            transaction,
            "Consultation seule : l'annulation d'une opération relève de "
            "la comptabilité.",
        )
        self.assertNotContains(transaction, "Annuler l'opération")

        enrollment = client.get(reverse(
            'core:dashboard:enrollment-detail', args=[self.enrollment.id]))
        self.assertEqual(enrollment.status_code, 200)
        self.assertNotContains(enrollment, 'Encaisser')
        self.assertNotContains(
            enrollment, reverse('core:dashboard:payment-create'))

        resources = client.get(reverse('core:dashboard:resources'))
        self.assertNotContains(
            resources, reverse('core:dashboard:resource-create'))

        programs = client.get(reverse('core:dashboard:programs'))
        self.assertNotContains(
            programs, reverse('core:dashboard:module-create'))

        reasons = client.get(reverse('core:dashboard:visit-reasons'))
        self.assertContains(reasons, 'Consultation seule')

    def test_elevated_keeps_administration_writes(self):
        client = self.client_for(self.super_admin)
        self.assertEqual(
            client.get(reverse('core:dashboard:user-create')).status_code, 200)
        self.assertContains(
            client.get(reverse('core:dashboard:user-list')),
            reverse('core:dashboard:user-create'),
        )
        pending = AccessRequest.objects.create(
            user=self.make_user(RoleKey.ETUDIANT, 'bourse@test.local'),
            requested_role=RoleKey.ETUDIANT,
        )
        self.assertContains(
            client.get(reverse('core:dashboard:access-requests')),
            reverse('core:dashboard:access-request-review', args=[pending.id]),
        )


class ScholarshipDecisionTests(BusinessTestBase):
    """La décision de bourse reste réservée au SUPER_ADMIN."""

    def setUp(self):
        destination = Destination.objects.create(name='France')
        self.application = ScholarshipApplication.objects.create(
            last_name='Nkodia',
            first_name='Sarah',
            email='sarah@test.local',
            phone='+242060000009',
            destination=destination,
            program='Master',
            study_domain='Informatique',
        )

    def test_admin_sees_application_but_cannot_decide(self):
        client = self.client_for(self.admin)
        detail = client.get(reverse(
            'core:dashboard:scholarship-review-detail',
            args=[self.application.id]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(
            detail,
            'Consultation seule : la décision de bourse est réservée au '
            'super administrateur.',
        )

        response = client.post(
            reverse('core:dashboard:scholarship-review-detail',
                    args=[self.application.id]),
            {'status': ScholarshipApplication.Status.APPROVED,
             'review_note': 'Décision ADMIN'},
        )
        self.assertEqual(response.status_code, 403)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status,
                         ScholarshipApplication.Status.SUBMITTED)

    def test_super_admin_decides_and_it_is_audited(self):
        response = self.client_for(self.super_admin).post(
            reverse('core:dashboard:scholarship-review-detail',
                    args=[self.application.id]),
            {'status': ScholarshipApplication.Status.APPROVED,
             'review_note': 'Dossier conforme'},
        )
        self.assertRedirects(
            response, reverse('core:dashboard:scholarship-review-list'),
            fetch_redirect_response=False,
        )
        self.application.refresh_from_db()
        self.assertEqual(self.application.status,
                         ScholarshipApplication.Status.APPROVED)
        self.assertEqual(self.application.reviewed_by, self.super_admin)
        self.assert_audited('SCHOLARSHIP_REVIEW', self.application.id)


class PerRecordHistoryTests(BusinessTestBase):
    """Chaque fiche métier expose qui a fait quoi et quand."""

    def setUp(self):
        self.contact = Contact.objects.create(
            first_name='Ibrahim', last_name='Samba', phone='+242060000011',
        )
        self.visit = Visit.objects.create(
            contact=self.contact,
            reason=self.visit_reason,
            agent=self.accueil,
            status=Visit.Status.IN_PROGRESS,
        )
        self.prospect = Prospect.objects.create(
            contact=self.contact,
            course=self.course,
            agent=self.accueil,
        )
        self.transaction = CashTransaction.objects.create(
            tx_type=CashTransaction.Type.IN,
            category=self.income_category,
            label='Encaissement test',
            amount=7000,
            account=self.cash,
            status=CashTransaction.Status.VALIDATED,
            created_by=self.comptable,
        )
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

    def _log(self, action, entity_type, entity_id):
        return AuditLog.objects.create(
            actor=self.secretaire,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            before_summary={'status': 'AVANT'},
            after_summary={'status': 'APRES'},
        )

    def test_detail_pages_render_history(self):
        cases = (
            ('student-detail', [self.etudiant.id], 'STUDENT_EDIT', 'User',
             self.etudiant.id),
            ('enrollment-detail', [self.enrollment.id], 'ENROLLMENT_EDIT',
             'Enrollment', self.enrollment.id),
            ('session-record-detail', [self.record.id], 'ATTENDANCE_RECORD',
             'SessionRecord', self.record.id),
            ('visit-detail', [self.visit.id], 'VISIT_UPDATE', 'Visit',
             self.visit.id),
            ('prospect-detail', [self.prospect.id], 'PROSPECT_UPDATE',
             'Prospect', self.prospect.id),
            ('transaction-detail', [self.transaction.id],
             'CASH_TRANSACTION_CANCEL', 'CashTransaction',
             self.transaction.id),
        )
        for name, args, action, entity_type, entity_id in cases:
            with self.subTest(route=name):
                self._log(action, entity_type, entity_id)
                response = self.client_for(self.super_admin).get(
                    reverse(f'core:dashboard:{name}', args=args))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, action)
                self.assertContains(
                    response, self.secretaire.display_label)

    def test_global_audit_log_links_to_records(self):
        entries = (
            ('User', self.etudiant.id, 'user-detail'),
            ('Enrollment', self.enrollment.id, 'enrollment-detail'),
            ('SessionRecord', self.record.id, 'session-record-detail'),
            ('Visit', self.visit.id, 'visit-detail'),
            ('Prospect', self.prospect.id, 'prospect-detail'),
            ('CashTransaction', self.transaction.id, 'transaction-detail'),
            ('Payment', self.payment.id, 'payment-receipt'),
        )
        for entity_type, entity_id, _route in entries:
            self._log('NAVIGATION_TEST', entity_type, entity_id)

        response = self.client_for(self.super_admin).get(
            reverse('core:dashboard:audit-log'))
        self.assertEqual(response.status_code, 200)
        for entity_type, entity_id, route in entries:
            with self.subTest(entity=entity_type):
                self.assertContains(
                    response,
                    reverse(f'core:dashboard:{route}', args=[entity_id]),
                )
