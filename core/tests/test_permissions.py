"""Tests transverses des permissions et du routage des dashboards."""
from datetime import time as dt_time

from django.urls import reverse

from core.models import (
    AccessEvent, AccessRequest, AccountStatus, Attendance, AuditLog,
    CashAccount, CashTransaction, Contact, Destination, Enrollment, Module,
    Payment, Prospect, Resource, Role, RoleKey, ROLES_DISSOUS, ScholarshipApplication,
    SessionRecord, User, UserRole, Visit, VisitReason,
)

from core.taches import tableau_des_files

from .base import BusinessTestBase


class DashboardRoutingTests(BusinessTestBase):
    def test_dashboard_router_redirects_each_role(self):
        for user in (
            self.super_admin, self.admin, self.direction, self.secretaire,
            self.assistant, self.peda, self.formateur, self.etudiant,
            self.assistant,
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
            (self.assistant, 'core:dashboard:comptabilite-dashboard'),
            (self.peda, 'core:dashboard:resp-peda-dashboard'),
            (self.formateur, 'core:dashboard:formateur-dashboard'),
            (self.etudiant, 'core:dashboard:etudiant-dashboard'),
            (self.assistant, 'core:dashboard:accueil-dashboard'),
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
            (self.assistant, 'core:dashboard:programs'),
            (self.assistant, 'core:dashboard:audit-log'),
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
        user = self.make_user(RoleKey.ASSISTANT_ADMIN, 'sansrole@test.local')
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
    """L'ADMIN lit tous les modules et tient la caisse ; le reste est au SUPER_ADMIN."""

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
            recorded_by=self.assistant,
        )
        transaction = CashTransaction.objects.create(
            reference='TX-ADMIN-VISIBILITE',
            tx_type=CashTransaction.Type.IN,
            category=self.income_category,
            label='Paiement de test',
            amount=10000,
            account=self.cash,
            created_by=self.assistant,
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
            recorded_by=self.assistant,
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
            {'role_key': RoleKey.ASSISTANT_ADMIN, 'action': 'add'},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            self.secretaire.roles.filter(key=RoleKey.ASSISTANT_ADMIN).exists())

    def test_admin_can_review_access_request(self):
        pending = AccessRequest.objects.create(
            user=self.make_user(RoleKey.ETUDIANT, 'enattente@test.local'),
            requested_role=RoleKey.ETUDIANT,
        )
        client = self.client_for(self.admin)
        response = client.post(
            reverse('core:dashboard:access-request-review', args=[pending.id]),
            {'decision': 'approve', 'role_key': RoleKey.ETUDIANT,
             'session': self.session.pk},
        )
        self.assertRedirects(
            response, reverse('core:dashboard:access-requests'),
            fetch_redirect_response=False,
        )
        pending.refresh_from_db()
        self.assertEqual(pending.status, AccessRequest.Status.APPROVED)
        self.assertEqual(pending.assigned_role, RoleKey.ETUDIANT)
        self.assertEqual(pending.reviewed_by, self.admin)

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
        self.assertContains(
            reviews,
            reverse('core:dashboard:access-request-review', args=[pending.id]),
        )
        self.assertContains(reviews, 'Approuver')

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


class ElevatedBusinessAccessTests(BusinessTestBase):
    """SUPER_ADMIN et ADMIN tiennent la caisse ; le reste du métier reste en lecture.

    La direction a ouvert l'écriture financière aux deux rôles élevés : journal,
    encaissement, clôture, caisses et catégories — chaque geste est tracé dans
    l'audit. S'ajoute une exception assumée hors caisse : la modification de
    l'inscription d'un étudiant (formation, statut, montant). Étudiants,
    présences, visites, prospects et ressources restent en consultation seule,
    et la création d'une inscription au guichet aussi.
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
            agent=self.assistant,
            status=Visit.Status.IN_PROGRESS,
        )
        self.prospect = Prospect.objects.create(
            contact=self.contact,
            course=self.course,
            agent=self.assistant,
            status=Prospect.Status.NEW,
        )
        self.transaction = CashTransaction.objects.create(
            tx_type=CashTransaction.Type.IN,
            category=self.income_category,
            label='Encaissement test',
            amount=5000,
            account=self.cash,
            status=CashTransaction.Status.VALIDATED,
            created_by=self.assistant,
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

    def test_elevated_roles_open_the_cash_write_screens(self):
        """La caisse est ouverte aux rôles élevés, écran par écran."""
        for user in (self.super_admin, self.admin):
            for name, args in (
                ('transaction-create', []),
                ('transaction-detail', [self.transaction.id]),
                ('transaction-edit', [self.transaction.id]),
                ('payment-create', []),
                ('closure-create', []),
                ('accounts', []),
                ('account-update', [self.cash.id]),
                ('account-adjust', [self.cash.id]),
                ('account-reset', [self.cash.id]),
                ('categories', []),
                ('category-update', [self.income_category.id]),
            ):
                with self.subTest(role=user.primary_role, route=name):
                    self.assertEqual(
                        self.client_for(user).get(
                            reverse(f'core:dashboard:{name}', args=args)
                        ).status_code,
                        200,
                    )

    def test_elevated_roles_post_to_the_cash_and_are_audited(self):
        """Une écriture posée par un rôle élevé écrit, et laisse sa trace."""
        for user in (self.super_admin, self.admin):
            with self.subTest(role=user.primary_role):
                response = self.client_for(user).post(
                    reverse('core:dashboard:transaction-create'), {
                        'tx_type': CashTransaction.Type.IN,
                        'category': self.income_category.pk,
                        'label': 'Recette de supervision',
                        'description': 'Encaissement contrôlé',
                        'amount': '25000',
                        'occurred_at': self.local_datetime(),
                        'method': Payment.Method.CASH,
                        'account': self.cash.pk,
                        'destination_account': '',
                        'counterparty': 'Client test',
                        'status': CashTransaction.Status.VALIDATED,
                        'note': '',
                    })
                self.assertEqual(response.status_code, 302)
        self.assertEqual(
            CashTransaction.objects.filter(
                label='Recette de supervision').count(), 2)
        self.assert_audited('CASH_TRANSACTION_CREATE',
                            CashTransaction.objects.filter(
                                label='Recette de supervision').first().pk)

    def test_elevated_roles_can_edit_enrollment(self):
        """Exception assumée : les rôles élevés modifient l'inscription."""
        url = reverse('core:dashboard:enrollment-edit',
                      args=[self.enrollment.id])
        for user in (self.super_admin, self.admin):
            with self.subTest(role=user.primary_role):
                client = self.client_for(user)
                self.assertEqual(client.get(url).status_code, 200)
                response = client.post(url, {
                    'student': self.etudiant.pk,
                    'session': self.session.pk,
                    'status': Enrollment.Status.COMPLETED,
                    'start_date': self.local_date(),
                    'tariff_amount': '120000',
                    'discount_amount': '20000',
                    'payment_plan': 'Soldé',
                    'notes': 'Modifié par supervision',
                })
                self.assertRedirects(
                    response,
                    reverse('core:dashboard:enrollment-detail',
                            args=[self.enrollment.id]),
                    fetch_redirect_response=False,
                )
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, Enrollment.Status.COMPLETED)
        self.assertEqual(self.enrollment.net_amount, 100000)
        self.assertEqual(self.enrollment.notes, 'Modifié par supervision')
        self.assert_audited('ENROLLMENT_EDIT', self.enrollment.pk)

    def test_elevated_roles_cannot_post_mixed_views(self):
        cases = (
            ('visit-detail', [self.visit.id]),
            ('visit-departure', [self.visit.id]),
            ('visit-to-prospect', [self.visit.id]),
            ('prospect-detail', [self.prospect.id]),
            ('visit-reasons', []),
            ('visit-reason-toggle', [self.visit_reason.id]),
            ('accueil-dashboard', []),
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

    def test_business_screens_hide_write_controls_but_cash_shows_them(self):
        client = self.client_for(self.super_admin)

        transaction = client.get(reverse(
            'core:dashboard:transaction-detail', args=[self.transaction.id]))
        self.assertEqual(transaction.status_code, 200)
        self.assertNotContains(transaction, 'Consultation seule')
        self.assertContains(transaction, "Annuler l'opération")
        self.assertContains(transaction, "Corriger l'écriture")

        accounts = client.get(reverse('core:dashboard:accounts'))
        self.assertEqual(accounts.status_code, 200)
        self.assertNotContains(accounts, 'Consultation seule')
        self.assertContains(accounts, 'Nouvelle caisse / compte')

        enrollment = client.get(reverse(
            'core:dashboard:enrollment-detail', args=[self.enrollment.id]))
        self.assertEqual(enrollment.status_code, 200)
        self.assertContains(enrollment, 'Encaisser')

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
            agent=self.assistant,
            status=Visit.Status.IN_PROGRESS,
        )
        self.prospect = Prospect.objects.create(
            contact=self.contact,
            course=self.course,
            agent=self.assistant,
        )
        self.transaction = CashTransaction.objects.create(
            tx_type=CashTransaction.Type.IN,
            category=self.income_category,
            label='Encaissement test',
            amount=7000,
            account=self.cash,
            status=CashTransaction.Status.VALIDATED,
            created_by=self.assistant,
        )
        self.payment = Payment.objects.create(
            enrollment=self.enrollment,
            amount=7000,
            method=Payment.Method.CASH,
            recorded_by=self.assistant,
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


class ResponsablePedaPerimetreAccesTests(BusinessTestBase):
    """Le resp. pédagogue voit toutes les demandes mais ne statue que sur son équipe.

    La caisse, le secrétariat et le poste de resp. pédagogie lui-même restent
    tranchés par un super administrateur : sinon il fabriquerait ses propres
    pairs et les comptes financiers de l'établissement.
    """

    def setUp(self):
        self.demande_formateur = self._demande(RoleKey.FORMATEUR,
                                               'candidat-formateur@test.local')
        self.demande_assistant = self._demande(RoleKey.ASSISTANT_ADMIN,
                                               'candidat-caisse@test.local')
        self.demande_etudiante = self._demande(RoleKey.ETUDIANT,
                                               'candidat-etudiant@test.local')
        self.client = self.client_for(self.peda)

    @staticmethod
    def _demande(role_key, email):
        """Une demande en attente, posée par un compte qui n'a pas encore le rôle."""
        candidat = User.objects.create_user(
            email=email, password='TestPass123!',
            first_name='Candidat', last_name=role_key.title(),
            account_status=AccountStatus.PENDING_APPROVAL,
        )
        return AccessRequest.objects.create(user=candidat,
                                            requested_role=role_key)

    def test_le_resp_peda_ouvre_la_liste_de_toutes_les_demandes(self):
        response = self.client.get(reverse('core:dashboard:access-requests'))
        self.assertEqual(response.status_code, 200)
        for demande in (self.demande_formateur, self.demande_assistant,
                        self.demande_etudiante):
            with self.subTest(role=demande.requested_role):
                self.assertContains(response, demande.user.email)

    def test_une_demande_hors_perimetre_noffre_pas_de_formulaire(self):
        response = self.client.get(reverse('core:dashboard:access-requests'))
        self.assertContains(
            response,
            reverse('core:dashboard:access-request-review',
                    args=[self.demande_formateur.id]),
        )
        self.assertNotContains(
            response,
            reverse('core:dashboard:access-request-review',
                    args=[self.demande_assistant.id]),
        )
        self.assertContains(response, 'réservée à la supervision')

    def test_le_menu_des_rôles_propose_seulement_le_perimetre(self):
        response = self.client.get(reverse('core:dashboard:access-requests'))
        self.assertEqual(
            {choix[0] for choix in response.context['role_choices']},
            {'FORMATEUR', 'ETUDIANT'},
        )

    def test_le_resp_peda_approuve_une_demande_de_formateur(self):
        response = self.client.post(
            reverse('core:dashboard:access-request-review',
                    args=[self.demande_formateur.id]),
            {'decision': 'approve', 'role_key': RoleKey.FORMATEUR},
        )
        self.assertRedirects(
            response, reverse('core:dashboard:access-requests'),
            fetch_redirect_response=False,
        )
        self.demande_formateur.refresh_from_db()
        self.assertEqual(self.demande_formateur.status,
                         AccessRequest.Status.APPROVED)
        self.assertEqual(self.demande_formateur.reviewed_by, self.peda)
        compte = self.demande_formateur.user
        self.assertEqual(compte.account_status, AccountStatus.ACTIVE)
        self.assertTrue(compte.roles.filter(key=RoleKey.FORMATEUR).exists())

    def test_le_resp_peda_approuve_une_inscription_étudiante(self):
        response = self.client.post(
            reverse('core:dashboard:access-request-review',
                    args=[self.demande_etudiante.id]),
            {'decision': 'approve', 'role_key': RoleKey.ETUDIANT,
             'session': self.session.pk},
        )
        self.assertRedirects(
            response, reverse('core:dashboard:access-requests'),
            fetch_redirect_response=False,
        )
        self.demande_etudiante.refresh_from_db()
        self.assertEqual(self.demande_etudiante.status,
                         AccessRequest.Status.APPROVED)
        self.assertTrue(
            Enrollment.objects.filter(
                student=self.demande_etudiante.user,
                session=self.session,
            ).exists()
        )

    def test_le_resp_peda_refuse_une_demande_de_son_perimètre(self):
        response = self.client.post(
            reverse('core:dashboard:access-request-review',
                    args=[self.demande_etudiante.id]),
            {'decision': 'reject', 'note': 'Dossier incomplet'},
        )
        self.assertRedirects(
            response, reverse('core:dashboard:access-requests'),
            fetch_redirect_response=False,
        )
        self.demande_etudiante.refresh_from_db()
        self.assertEqual(self.demande_etudiante.status,
                         AccessRequest.Status.REJECTED)

    def test_le_resp_peda_ne_statue_pas_sur_une_demande_de_caisse(self):
        for decision in ('approve', 'reject'):
            with self.subTest(decision=decision):
                self.demande_assistant.status = AccessRequest.Status.PENDING
                self.demande_assistant.user.account_status = (
                    AccountStatus.PENDING_APPROVAL)
                self.demande_assistant.user.save()
                response = self.client.post(
                    reverse('core:dashboard:access-request-review',
                            args=[self.demande_assistant.id]),
                    {'decision': decision, 'role_key': RoleKey.ASSISTANT_ADMIN},
                )
                self.assertRedirects(
                    response, reverse('core:dashboard:access-requests'),
                    fetch_redirect_response=False,
                )
                self.demande_assistant.refresh_from_db()
                self.assertEqual(self.demande_assistant.status,
                                 AccessRequest.Status.PENDING)
                self.assertIsNone(self.demande_assistant.reviewed_at)
                self.assertEqual(
                    self.demande_assistant.user.account_status,
                    AccountStatus.PENDING_APPROVAL,
                )

    def test_le_resp_peda_ne_se_crée_pas_de_pair(self):
        demande = self._demande(RoleKey.RESPONSABLE_PEDAGOGIQUE,
                               'candidat-peda@test.local')
        response = self.client.post(
            reverse('core:dashboard:access-request-review', args=[demande.id]),
            {'decision': 'approve', 'role_key': RoleKey.RESPONSABLE_PEDAGOGIQUE},
        )
        self.assertRedirects(
            response, reverse('core:dashboard:access-requests'),
            fetch_redirect_response=False,
        )
        demande.refresh_from_db()
        self.assertEqual(demande.status, AccessRequest.Status.PENDING)

    def test_le_super_admin_statue_toujours_sur_la_caisse(self):
        client = self.client_for(self.super_admin)
        response = client.post(
            reverse('core:dashboard:access-request-review',
                    args=[self.demande_assistant.id]),
            {'decision': 'approve', 'role_key': RoleKey.ASSISTANT_ADMIN},
        )
        self.assertRedirects(
            response, reverse('core:dashboard:access-requests'),
            fetch_redirect_response=False,
        )
        self.demande_assistant.refresh_from_db()
        self.assertEqual(self.demande_assistant.status,
                         AccessRequest.Status.APPROVED)

    def test_le_secretaire_rest_extérieur_à_l_écran(self):
        self.assertEqual(
            self.client_for(self.secretaire).get(
                reverse('core:dashboard:access-requests')).status_code,
            403,
        )

    def test_la_navivation_pédagogique_mène_aux_demandes(self):
        self.assertContains(
            self.client.get(reverse('core:dashboard:resp-peda-dashboard')),
            reverse('core:dashboard:access-requests'),
        )

    def test_la_cloche_ne_compte_que_les_demandes_décidables(self):
        taches, _notifications, _total = tableau_des_files(self.peda)
        files = {t['nom']: t['nombre'] for t in taches}
        self.assertEqual(files["Demandes d'accès à approuver"], 2)

        taches, _notifications, _total = tableau_des_files(self.super_admin)
        files = {t['nom']: t['nombre'] for t in taches}
        self.assertEqual(files["Demandes d'accès à approuver"], 3)


class PostesDissousTests(BusinessTestBase):
    """« Accueil » et « Caisse » ont fusionné dans « Assistant administratif ».

    Les lignes de rôle restent en base pour que l'historique garde son sens ;
    aucun écran ne doit en revanche proposer un poste dissous à attribuer.
    """

    def test_aucun_menu_ne_propose_un_poste_dissous(self):
        client = self.client_for(self.super_admin)
        menus = {
            'liste des utilisateurs': {
                choix[0] for choix in
                client.get(reverse('core:dashboard:user-list')).context['role_choices']
                if choix[0]},
            'création d\'un compte': {
                choix[0] for choix in
                client.get(reverse('core:dashboard:user-create')).context['form']
                .fields['role'].choices if choix[0]},
            'fiche utilisateur': {
                role.key for role in
                client.get(reverse('core:dashboard:user-detail',
                                   args=[self.etudiant.id])).context['available_roles']},
            'demandes d\'accès': {
                choix[0] for choix in
                client.get(reverse('core:dashboard:access-requests')).context['role_choices']
                if choix[0]},
        }
        for ecran, cles in menus.items():
            self.assertEqual(cles & set(ROLES_DISSOUS), set(),
                             f'{ecran} propose encore un poste dissous')
            self.assertIn('ASSISTANT_ADMIN', cles,
                          f'{ecran} a perdu le poste qui les remplace')

    def test_attribuer_un_poste_dissous_est_refusé(self):
        for poste in ROLES_DISSOUS:
            with self.subTest(poste=poste):
                page = self.client_for(self.super_admin).post(
                    reverse('core:dashboard:user-role-assign',
                            args=[self.etudiant.id]),
                    {'role_key': poste, 'action': 'add'},
                    follow=True,
                )
                self.assertContains(page, 'Ce poste est dissous')
                self.assertFalse(
                    self.etudiant.roles.filter(key=poste).exists())

    def test_un_compte_marqué_dun_poste_dissous_reste_lisible(self):
        UserRole.objects.create(
            user=self.etudiant, role=Role.objects.get(key='COMPTABLE'))
        client = self.client_for(self.super_admin)
        fiche = client.get(
            reverse('core:dashboard:user-detail', args=[self.etudiant.id]))
        self.assertContains(fiche, 'Comptable')
        liste = client.get(reverse('core:dashboard:user-list'),
                           {'role': 'COMPTABLE'})
        self.assertContains(liste, self.etudiant.email)
