"""Tests de la comptabilité : journal, caisses, clôtures et paiements."""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from core.models import (
    CashAccount, CashClosure, CashTransaction, Enrollment, Expense, Payment,
    RoleKey,
)
from core.views_comptabilite import account_balance

from .base import BusinessTestBase


class AccountingTestBase(BusinessTestBase):
    def setUp(self):
        self.client = self.client_for(self.comptable)

    def make_tx(self, tx_type=CashTransaction.Type.IN, amount=10000,
                account=None, destination=None, status=CashTransaction.Status.VALIDATED,
                occurred_at=None, label='Opération de test', **kwargs):
        if tx_type == CashTransaction.Type.IN:
            category = self.income_category
        elif tx_type == CashTransaction.Type.OUT:
            category = self.expense_category
        else:
            category = self.transfer_category
        return CashTransaction.objects.create(
            tx_type=tx_type,
            category=kwargs.pop('category', category),
            label=label,
            amount=amount,
            occurred_at=occurred_at or timezone.now(),
            account=account or self.cash,
            destination_account=destination,
            method=Payment.Method.CASH,
            status=status,
            created_by=self.comptable,
            **kwargs,
        )

    def tx_payload(self, **overrides):
        payload = {
            'tx_type': CashTransaction.Type.IN,
            'category': self.income_category.pk,
            'label': 'Recette diverse',
            'description': 'Encaissement de test',
            'amount': '25000',
            'occurred_at': self.local_datetime(),
            'method': Payment.Method.CASH,
            'account': self.cash.pk,
            'destination_account': '',
            'counterparty': 'Client test',
            'status': CashTransaction.Status.VALIDATED,
            'note': '',
        }
        payload.update(overrides)
        return payload

    def payment_payload(self, **overrides):
        payload = {
            'enrollment': self.enrollment.pk,
            'amount': '30000',
            'method': Payment.Method.CASH,
            'account': self.cash.pk,
            'paid_at': self.local_datetime(),
            'note': '',
        }
        payload.update(overrides)
        return payload


class JournalTests(AccountingTestBase):
    def test_journal_lists_validated_operations(self):
        incoming = self.make_tx(label='Entrée A')
        outgoing = self.make_tx(
            tx_type=CashTransaction.Type.OUT, amount=4000, label='Sortie B')
        response = self.client.get(reverse('core:dashboard:journal'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {tx.pk for tx in response.context['page'].object_list},
            {incoming.pk, outgoing.pk},
        )

    def test_journal_filters_by_type_and_search(self):
        incoming = self.make_tx(label='Paiement special')
        self.make_tx(
            tx_type=CashTransaction.Type.OUT, amount=4000, label='Achat stylos')
        response = self.client.get(
            reverse('core:dashboard:journal'), {'type': 'OUT'})
        self.assertEqual(
            [tx.label for tx in response.context['page'].object_list],
            ['Achat stylos'],
        )
        response = self.client.get(
            reverse('core:dashboard:journal'), {'q': 'special'})
        self.assertEqual(
            [tx.pk for tx in response.context['page'].object_list],
            [incoming.pk],
        )

    def test_journal_totals_ignore_cancelled_operations(self):
        self.make_tx(amount=10000)
        self.make_tx(
            tx_type=CashTransaction.Type.OUT, amount=3000,
            status=CashTransaction.Status.CANCELLED,
        )
        response = self.client.get(reverse('core:dashboard:journal'))
        self.assertEqual(response.context['totals']['incoming'], 10000)
        self.assertIsNone(response.context['totals']['outgoing'])

    def test_journal_csv_export(self):
        tx = self.make_tx(label='Ligne exportée')
        response = self.client.get(
            reverse('core:dashboard:journal'), {'export': 'csv'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        content = response.content.decode('utf-8-sig')
        self.assertIn('Référence', content)
        self.assertIn(tx.reference, content)
        self.assertIn('Ligne exportée', content)
        self.assert_audited('JOURNAL_EXPORT')


class CashTransactionTests(AccountingTestBase):
    def test_create_incoming_transaction(self):
        response = self.client.post(
            reverse('core:dashboard:transaction-create'),
            self.tx_payload(),
        )
        tx = CashTransaction.objects.get(label='Recette diverse')
        self.assertRedirects(
            response,
            reverse('core:dashboard:transaction-detail', args=[tx.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(tx.tx_type, CashTransaction.Type.IN)
        self.assertEqual(tx.amount, 25000)
        self.assertEqual(tx.created_by, self.comptable)
        self.assertTrue(tx.reference.startswith('TRX-'))
        self.assertEqual(account_balance(self.cash), 25000)
        self.assert_audited('CASH_TRANSACTION_CREATE', tx.pk)

    def test_transfer_requires_distinct_destination(self):
        response = self.client.post(
            reverse('core:dashboard:transaction-create'),
            self.tx_payload(
                tx_type=CashTransaction.Type.TRANSFER,
                category=self.transfer_category.pk,
                account=self.cash.pk,
                destination_account='',
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CashTransaction.objects.count(), 0)

        response = self.client.post(
            reverse('core:dashboard:transaction-create'),
            self.tx_payload(
                tx_type=CashTransaction.Type.TRANSFER,
                category=self.transfer_category.pk,
                account=self.cash.pk,
                destination_account=self.cash.pk,
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CashTransaction.objects.count(), 0)

    def test_category_direction_must_match_type(self):
        response = self.client.post(
            reverse('core:dashboard:transaction-create'),
            self.tx_payload(category=self.expense_category.pk),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CashTransaction.objects.count(), 0)

    def test_cancellation_requires_a_reason(self):
        tx = self.make_tx()
        url = reverse('core:dashboard:transaction-detail', args=[tx.pk])
        response = self.client.post(url, {'action': 'cancel', 'reason': ''})
        self.assertRedirects(response, url, fetch_redirect_response=False)
        tx.refresh_from_db()
        self.assertEqual(tx.status, CashTransaction.Status.VALIDATED)

        response = self.client.post(
            url, {'action': 'cancel', 'reason': 'Erreur de saisie'})
        self.assertRedirects(response, url, fetch_redirect_response=False)
        tx.refresh_from_db()
        self.assertEqual(tx.status, CashTransaction.Status.CANCELLED)
        self.assertIn('Erreur de saisie', tx.note)
        self.assert_audited('CASH_TRANSACTION_CANCEL', tx.pk)
        self.assertEqual(account_balance(self.cash), 0)


class AccountAndBalanceTests(AccountingTestBase):
    def test_account_balances(self):
        self.make_tx(amount=50000)
        self.make_tx(tx_type=CashTransaction.Type.OUT, amount=20000)
        self.make_tx(
            tx_type=CashTransaction.Type.TRANSFER, amount=10000,
            account=self.cash, destination=self.mobile,
        )
        self.assertEqual(account_balance(self.cash), 20000)
        self.assertEqual(account_balance(self.mobile), 10000)

    def test_transfer_is_neutral_globally(self):
        self.make_tx(amount=50000)
        self.make_tx(
            tx_type=CashTransaction.Type.TRANSFER, amount=30000,
            account=self.cash, destination=self.mobile,
        )
        total = account_balance(self.cash) + account_balance(self.mobile)
        self.assertEqual(total, 50000)
        self.assertEqual(account_balance(self.cash), 20000)
        self.assertEqual(account_balance(self.mobile), 30000)

    def test_account_list_creates_account(self):
        response = self.client.get(reverse('core:dashboard:accounts'))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse('core:dashboard:accounts'),
            {
                'name': 'Caisse secondaire',
                'kind': CashAccount.Kind.CASH,
                'currency': 'XAF',
                'opening_balance': '15000',
                'active': 'on',
            },
        )
        self.assertRedirects(
            response, reverse('core:dashboard:accounts'),
            fetch_redirect_response=False,
        )
        account = CashAccount.objects.get(name='Caisse secondaire')
        self.assertEqual(account.opening_balance, 15000)
        self.assertEqual(account_balance(account), 15000)
        self.assert_audited('CASH_ACCOUNT_CREATE', account.pk)

    def test_account_page_shows_balances(self):
        self.make_tx(amount=12000)
        response = self.client.get(reverse('core:dashboard:accounts'))
        rows = {row['account'].pk: row['balance']
                for row in response.context['rows']}
        self.assertEqual(rows[self.cash.pk], 12000)


class ClosureTests(AccountingTestBase):
    def test_closure_computes_theoretical_balance_and_difference(self):
        self.make_tx(amount=30000)
        response = self.client.post(
            reverse('core:dashboard:closure-create'),
            {
                'account': self.cash.pk,
                'date': self.local_date(),
                'counted_amount': '28000',
                'note': 'Manque 2000',
            },
        )
        self.assertRedirects(
            response, reverse('core:dashboard:closures'),
            fetch_redirect_response=False,
        )
        closure = CashClosure.objects.get(account=self.cash)
        self.assertEqual(closure.opening_balance, 0)
        self.assertEqual(closure.theoretical_balance, 30000)
        self.assertEqual(closure.counted_amount, 28000)
        self.assertEqual(closure.difference, -2000)
        self.assertEqual(closure.closed_by, self.comptable)
        self.assert_audited('CASH_CLOSURE', closure.pk)

    def test_duplicate_closure_is_rejected(self):
        self.make_tx(amount=5000)
        payload = {
            'account': self.cash.pk,
            'date': self.local_date(),
            'counted_amount': '5000',
            'note': '',
        }
        self.client.post(reverse('core:dashboard:closure-create'), payload)
        response = self.client.post(
            reverse('core:dashboard:closure-create'), payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            CashClosure.objects.filter(
                account=self.cash, date=self.today).count(),
            1,
        )

    def test_next_closure_starts_from_previous_counted_amount(self):
        yesterday = self.today - timedelta(days=1)
        self.client.post(
            reverse('core:dashboard:closure-create'),
            {
                'account': self.cash.pk,
                'date': yesterday.strftime('%Y-%m-%d'),
                'counted_amount': '10000',
                'note': '',
            },
        )
        self.make_tx(amount=5000)
        self.client.post(
            reverse('core:dashboard:closure-create'),
            {
                'account': self.cash.pk,
                'date': self.local_date(),
                'counted_amount': '15000',
                'note': '',
            },
        )
        today_closure = CashClosure.objects.get(
            account=self.cash, date=self.today)
        self.assertEqual(today_closure.opening_balance, 10000)
        self.assertEqual(today_closure.theoretical_balance, 15000)
        self.assertEqual(today_closure.difference, 0)


class StudentPaymentTests(AccountingTestBase):
    def test_partial_payment_creates_linked_cash_transaction(self):
        response = self.client.post(
            reverse('core:dashboard:payment-create'), self.payment_payload())
        payment = Payment.objects.get()
        self.assertRedirects(
            response,
            reverse('core:dashboard:payment-receipt', args=[payment.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(payment.amount, 30000)
        self.assertEqual(payment.status, Payment.Status.COMPLETED)
        self.assertEqual(payment.recorded_by, self.comptable)
        self.assertIsNotNone(payment.transaction)
        self.assertEqual(payment.transaction.tx_type, CashTransaction.Type.IN)
        self.assertEqual(payment.transaction.amount, 30000)
        self.assertEqual(payment.transaction.account, self.cash)
        self.assertEqual(payment.transaction.status,
                         CashTransaction.Status.VALIDATED)

        enrollment = Enrollment.objects.get(pk=self.enrollment.pk)
        self.assertEqual(enrollment.total_paid, 30000)
        self.assertEqual(enrollment.balance_due, 60000)
        self.assertEqual(enrollment.payment_state, 'PARTIEL')
        self.assert_audited('PAYMENT_CREATE', payment.pk)

    def test_full_payment_settles_the_enrollment(self):
        self.client.post(
            reverse('core:dashboard:payment-create'),
            self.payment_payload())
        self.client.post(
            reverse('core:dashboard:payment-create'),
            self.payment_payload(
                amount='60000', paid_at=self.local_datetime(minutes=5)),
        )
        enrollment = Enrollment.objects.get(pk=self.enrollment.pk)
        self.assertEqual(enrollment.total_paid, 90000)
        self.assertEqual(enrollment.balance_due, 0)
        self.assertEqual(enrollment.payment_state, 'SOLDE')
        self.assertEqual(Payment.objects.count(), 2)

    def test_overpayment_is_rejected(self):
        response = self.client.post(
            reverse('core:dashboard:payment-create'),
            self.payment_payload(amount='100000'),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(CashTransaction.objects.count(), 0)

    def test_duplicate_submission_is_blocked(self):
        payload = self.payment_payload(amount='10000')
        self.client.post(reverse('core:dashboard:payment-create'), payload)
        response = self.client.post(
            reverse('core:dashboard:payment-create'), payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(CashTransaction.objects.count(), 1)

    def test_second_identical_amount_after_delay_is_allowed(self):
        first = self.payment_payload(
            amount='10000', paid_at=self.local_datetime(minutes=-10))
        second = self.payment_payload(amount='10000')
        self.client.post(reverse('core:dashboard:payment-create'), first)
        self.client.post(reverse('core:dashboard:payment-create'), second)
        self.assertEqual(Payment.objects.count(), 2)

    def test_receipt_access_rules(self):
        self.client.post(
            reverse('core:dashboard:payment-create'), self.payment_payload())
        payment = Payment.objects.get()
        url = reverse('core:dashboard:payment-receipt', args=[payment.pk])

        owner_client = self.client_for(self.etudiant)
        self.assertEqual(owner_client.get(url).status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 200)

        other = self.make_user(RoleKey.ETUDIANT, 'autre-recu@test.local')
        other_client = self.client_for(other)
        self.assertEqual(other_client.get(url).status_code, 403)

        trainer_client = self.client_for(self.formateur)
        self.assertEqual(trainer_client.get(url).status_code, 403)
        self.assert_audited('PAYMENT_RECEIPT', payment.pk)


class AccountingPermissionTests(AccountingTestBase):
    def test_secretary_and_accueil_cannot_read_journal(self):
        for user in (self.secretaire, self.accueil):
            client = self.client_for(user)
            response = client.get(reverse('core:dashboard:journal'))
            self.assertEqual(response.status_code, 403)

    def test_direction_can_read_journal(self):
        client = self.client_for(self.direction)
        self.assertEqual(
            client.get(reverse('core:dashboard:journal')).status_code, 200)

    def test_student_cannot_create_transaction(self):
        client = self.client_for(self.etudiant)
        response = client.get(reverse('core:dashboard:transaction-create'))
        self.assertEqual(response.status_code, 403)


class SingleSourceOfTruthTests(AccountingTestBase):
    """Les soldes et indicateurs ne doivent exister qu'en un seul calcul."""

    def test_account_balance_property_matches_the_shared_helper(self):
        self.make_tx(amount=10000, account=self.cash)
        self.make_tx(amount=4000, account=self.mobile)
        self.make_tx(
            tx_type=CashTransaction.Type.OUT, amount=3000, account=self.cash)
        self.make_tx(
            tx_type=CashTransaction.Type.TRANSFER, amount=2000,
            account=self.cash, destination=self.mobile)

        self.assertEqual(self.cash.balance, 5000)
        self.assertEqual(self.mobile.balance, 6000)
        for account in (self.cash, self.mobile):
            with self.subTest(account=account.name):
                self.assertEqual(account.balance, account_balance(account))
                self.assertEqual(
                    account.totals(),
                    account.movement_totals(),
                )

    def test_balance_at_ignores_movements_after_the_cutoff(self):
        self.make_tx(
            amount=10000, occurred_at=timezone.now() - timedelta(days=2))
        self.make_tx(amount=5000)
        cutoff = self.today - timedelta(days=1)

        self.assertEqual(self.cash.balance_at(cutoff), 10000)
        self.assertEqual(self.cash.balance_at(self.today), 15000)

    def test_comptabilite_dashboard_ignores_unlinked_payment_and_expense(self):
        self.make_tx(amount=10000)
        self.make_tx(tx_type=CashTransaction.Type.OUT, amount=3000)
        Payment.objects.create(
            enrollment=self.enrollment,
            amount=5000,
            method=Payment.Method.CASH,
            status=Payment.Status.COMPLETED,
            recorded_by=self.comptable,
        )
        Expense.objects.create(
            category='Fournitures',
            amount=7000,
            occurred_at=self.today,
            description='Dépense hors caisse',
            created_by=self.comptable,
        )

        response = self.client.get(
            reverse('core:dashboard:comptabilite-dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_revenue_month'], 10000)
        self.assertEqual(response.context['total_expenses_month'], 3000)
        self.assertEqual(response.context['net_month'], 7000)

    def test_direction_dashboard_revenue_comes_from_cash_transactions(self):
        self.make_tx(amount=10000)
        Payment.objects.create(
            enrollment=self.enrollment,
            amount=5000,
            method=Payment.Method.CASH,
            status=Payment.Status.COMPLETED,
            recorded_by=self.comptable,
        )

        client = self.client_for(self.direction)
        response = client.get(reverse('core:dashboard:direction-dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_revenue'], 10000)


class ComptableStudentListTests(BusinessTestBase):
    """La comptable consulte la liste des inscrits, sans écriture."""

    def test_comptable_sees_students_list(self):
        client = self.client_for(self.comptable)
        response = client.get(reverse('core:dashboard:student-list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.etudiant.get_full_name())
        self.assertContains(
            response, reverse('core:dashboard:student-list'))
        self.assertNotContains(
            response, reverse('core:dashboard:student-create'))

    def test_comptable_reads_student_detail_without_write_controls(self):
        client = self.client_for(self.comptable)
        response = client.get(reverse(
            'core:dashboard:student-detail', args=[self.etudiant.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            reverse('core:dashboard:student-edit', args=[self.etudiant.id]))
        self.assertNotContains(
            response, reverse('core:dashboard:enrollment-create'))
        self.assertNotContains(
            response,
            reverse('core:dashboard:student-document-upload',
                    args=[self.etudiant.id]))
        self.assertContains(response, 'relève du secrétariat')

    def test_secretary_gets_the_document_form(self):
        response = self.client_for(self.secretaire).get(reverse(
            'core:dashboard:student-detail', args=[self.etudiant.id]))
        self.assertContains(
            response,
            reverse('core:dashboard:student-document-upload',
                    args=[self.etudiant.id]))

    def test_comptable_cannot_write_student_records(self):
        client = self.client_for(self.comptable)
        self.assertEqual(
            client.get(reverse('core:dashboard:student-create')).status_code,
            403,
        )
        self.assertEqual(
            client.post(reverse(
                'core:dashboard:student-edit', args=[self.etudiant.id]),
                {}).status_code,
            403,
        )


class StudentWithoutEnrollmentNoticeTests(BusinessTestBase):
    """Un compte étudiant validé reste visible sur l'écran d'encaissement."""

    def make_silent_student(self, email):
        student = self.make_user(RoleKey.ETUDIANT, email)
        student.first_name = 'Zorro'
        student.last_name = 'Nsimbe'
        student.save(update_fields=['first_name', 'last_name'])
        return student

    def test_the_account_is_listed_on_the_payment_screen(self):
        self.make_silent_student('silent1@test.local')
        page = self.client_for(self.comptable).get(
            reverse('core:dashboard:payment-create'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Comptes étudiants sans inscription')
        self.assertContains(page, 'Zorro Nsimbe')
        self.assertContains(page, 'Inscrire')

    def test_a_direction_member_can_enroll_from_that_screen(self):
        student = self.make_silent_student('silent2@test.local')
        page = self.client_for(self.direction).get(
            reverse('core:dashboard:payment-create'))
        self.assertContains(page, 'Inscrire')
        self.assertContains(page, f'?student={student.id}')

    def test_the_comptable_can_also_enroll_from_that_screen(self):
        student = self.make_silent_student('silent3@test.local')
        page = self.client_for(self.comptable).get(
            reverse('core:dashboard:payment-create'))
        self.assertContains(page, f'?student={student.id}#inscription')
        self.assertContains(page, 'Inscrire un étudiant')

    def test_enrolled_student_is_not_listed(self):
        page = self.client_for(self.comptable).get(
            reverse('core:dashboard:payment-create'))
        self.assertNotContains(page, 'Comptes étudiants sans inscription')
        self.assertContains(page, self.etudiant.get_full_name())


class PaymentEnrollmentFlowTests(AccountingTestBase):
    """Étudiant → inscription : création au guichet puis validation.

    La validation est ouverte à la direction, la caisse, la supervision
    pédagogique et au super administrateur ; l'ADMIN et les rôles opérationnels
    (formateur, secrétariat, accueil, étudiant) restent exclus.
    """

    def counter_payload(self, student, **overrides):
        payload = {
            'inscription-student': student.pk,
            'inscription-session': self.session.pk,
            'inscription-start_date': self.local_date(),
            'inscription-tariff_amount': '',
            'inscription-discount_amount': '0',
            'inscription-payment_plan': '',
            'inscription-notes': '',
        }
        payload.update(overrides)
        return payload

    def make_student(self, email='nouveau.guichet@test.local'):
        student = self.make_user(RoleKey.ETUDIANT, email)
        student.first_name = 'Nouveau'
        student.last_name = 'Guichet'
        student.save(update_fields=['first_name', 'last_name'])
        return student

    def test_student_field_lists_every_active_student(self):
        other = self.make_student('autre.actif@test.local')
        page = self.client.get(reverse('core:dashboard:payment-create'))
        self.assertEqual(page.status_code, 200)
        queryset = page.context['form'].fields['student'].queryset
        self.assertIn(self.etudiant, queryset)
        self.assertIn(other, queryset)
        self.assertContains(page, 'Choisir un étudiant')
        self.assertContains(page, self.etudiant.get_full_name())
        self.assertContains(page, 'Nouveau Guichet')

    def test_enrollment_choices_are_filtered_by_student(self):
        other = self.make_student('autre.dossier@test.local')
        page = self.client.get(
            reverse('core:dashboard:payment-create'),
            {'student': other.pk},
        )
        self.assertEqual(page.status_code, 200)
        queryset = page.context['form'].fields['enrollment'].queryset
        self.assertEqual(list(queryset), [])

        page = self.client.get(
            reverse('core:dashboard:payment-create'),
            {'student': self.etudiant.pk},
        )
        self.assertEqual(
            [e.pk for e in page.context['form'].fields['enrollment'].queryset],
            [self.enrollment.pk],
        )

    def test_enrollment_choices_show_the_remaining_balance(self):
        page = self.client.get(reverse('core:dashboard:payment-create'))
        self.assertContains(page, 'reste 90000 FCFA')
        self.assertContains(page, f'data-balance="90000"')

    def test_enrollment_choice_label_names_the_student(self):
        page = self.client.get(reverse('core:dashboard:payment-create'))
        self.assertContains(
            page,
            f'{self.etudiant.display_label} — {self.course.title} '
            f'(reste 90000 FCFA)',
        )

    def test_empty_enrollment_choice_is_explained(self):
        other = self.make_student('sans.dossier@test.local')
        page = self.client.get(
            reverse('core:dashboard:payment-create'),
            {'student': other.pk},
        )
        self.assertContains(page, 'Choisir un dossier')
        self.assertContains(page, 'Aucune inscription pour cet étudiant')

    def test_pending_enrollment_explains_the_validation_wait(self):
        student = self.make_student('en.attente@test.local')
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        page = self.client.get(
            reverse('core:dashboard:payment-create'),
            {'student': student.pk},
        )
        self.assertContains(page, 'il attend une validation')

    def test_counter_enrollment_is_created_pending_without_payment(self):
        student = self.make_student()
        response = self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        enrollment = Enrollment.objects.get(student=student)
        self.assertRedirects(
            response,
            f"{reverse('core:dashboard:payment-create')}"
            f"?student={student.pk}",
            fetch_redirect_response=False,
        )
        self.assertEqual(enrollment.status, Enrollment.Status.PENDING)
        self.assertEqual(enrollment.net_amount, self.course.fee_amount)
        self.assertEqual(enrollment.registered_by, self.comptable)
        self.assertEqual(Payment.objects.count(), 0)
        self.assert_audited('ENROLLMENT_CREATE', enrollment.pk)

    def test_counter_enrollment_keeps_the_net_amount_from_tariff(self):
        student = self.make_student()
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(
                student,
                **{'inscription-tariff_amount': '120000',
                   'inscription-discount_amount': '20000'})},
        )
        enrollment = Enrollment.objects.get(student=student)
        self.assertEqual(enrollment.net_amount, 100000)

    def test_a_pending_enrollment_cannot_be_paid(self):
        student = self.make_student()
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        enrollment = Enrollment.objects.get(student=student)
        response = self.client.post(
            reverse('core:dashboard:payment-create'),
            self.payment_payload(
                student=student.pk, enrollment=enrollment.pk, amount='10000'),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(
            Enrollment.objects.get(pk=enrollment.pk).status,
            Enrollment.Status.PENDING,
        )

    def test_direction_validates_the_counter_enrollment(self):
        student = self.make_student()
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        enrollment = Enrollment.objects.get(student=student)

        refused = self.client_for(self.formateur).post(reverse(
            'core:dashboard:enrollment-validate', args=[enrollment.pk]))
        self.assertEqual(refused.status_code, 403)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.PENDING)

        response = self.client_for(self.direction).post(reverse(
            'core:dashboard:enrollment-validate', args=[enrollment.pk]))
        self.assertRedirects(
            response,
            reverse('core:dashboard:enrollment-detail', args=[enrollment.pk]),
            fetch_redirect_response=False,
        )
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)
        self.assert_audited('ENROLLMENT_VALIDATE', enrollment.pk)

    def test_super_admin_can_validate_while_admin_stays_read_only(self):
        student = self.make_student('relais.direction@test.local')
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        enrollment = Enrollment.objects.get(student=student)
        url = reverse('core:dashboard:enrollment-validate', args=[enrollment.pk])

        self.assertEqual(
            self.client_for(self.admin).post(url).status_code, 403)

        response = self.client_for(self.super_admin).post(url)
        self.assertRedirects(
            response,
            reverse('core:dashboard:enrollment-detail', args=[enrollment.pk]),
            fetch_redirect_response=False,
        )
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)

    def test_comptable_valide_depuis_sa_caisse(self):
        student = self.make_student()
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        enrollment = Enrollment.objects.get(student=student)
        url = reverse('core:dashboard:enrollment-validate', args=[enrollment.pk])

        page = self.client.get(reverse('core:dashboard:comptabilite-dashboard'))
        self.assertContains(page, 'Inscriptions en attente de validation')
        self.assertContains(page, url)

        response = self.client.post(url)
        self.assertRedirects(
            response,
            reverse('core:dashboard:enrollment-detail', args=[enrollment.pk]),
            fetch_redirect_response=False,
        )
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)
        self.assert_audited('ENROLLMENT_VALIDATE', enrollment.pk)

    def test_responsable_pedagogique_valide_depuis_son_tableau_de_bord(self):
        student = self.make_student()
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        enrollment = Enrollment.objects.get(student=student)
        url = reverse('core:dashboard:enrollment-validate', args=[enrollment.pk])
        peta = self.client_for(self.peda)

        page = peta.get(reverse('core:dashboard:resp-peda-dashboard'))
        self.assertContains(page, 'Inscriptions en attente de validation')
        self.assertContains(page, url)

        response = peta.post(url)
        self.assertRedirects(
            response,
            reverse('core:dashboard:enrollment-detail', args=[enrollment.pk]),
            fetch_redirect_response=False,
        )
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)
        self.assertContains(
            peta.get(reverse(
                'core:dashboard:enrollment-detail', args=[enrollment.pk])),
            'Solde restant',
        )

    def test_panel_de_validation_present_sur_les_tableaux_habilites(self):
        student = self.make_student()
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        for user, route in (
            (self.super_admin, 'core:dashboard:super-admin-dashboard'),
            (self.direction, 'core:dashboard:direction-dashboard'),
            (self.comptable, 'core:dashboard:comptabilite-dashboard'),
            (self.peda, 'core:dashboard:resp-peda-dashboard'),
        ):
            page = self.client_for(user).get(reverse(route))
            self.assertEqual(page.status_code, 200, route)
            self.assertContains(page, 'Inscriptions en attente de validation')

    def test_validated_enrollment_becomes_payable(self):
        student = self.make_student()
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        enrollment = Enrollment.objects.get(student=student)
        self.client_for(self.direction).post(reverse(
            'core:dashboard:enrollment-validate', args=[enrollment.pk]))

        response = self.client.post(
            reverse('core:dashboard:payment-create'),
            self.payment_payload(
                student=student.pk, enrollment=enrollment.pk, amount='10000'),
        )
        payment = Payment.objects.get()
        self.assertRedirects(
            response,
            reverse('core:dashboard:payment-receipt', args=[payment.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(payment.enrollment_id, enrollment.pk)

    def test_enrollment_from_another_student_is_refused(self):
        other = self.make_user(RoleKey.ETUDIANT, 'autre.etudiant@test.local')
        response = self.client.post(
            reverse('core:dashboard:payment-create'),
            self.payment_payload(student=other.pk),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Payment.objects.count(), 0)
        errors = response.context['form'].errors.get('enrollment', [])
        self.assertTrue(
            any('appartient pas' in str(error) for error in errors), errors)

    def test_sold_out_enrollment_has_an_explicit_message(self):
        self.client.post(
            reverse('core:dashboard:payment-create'),
            self.payment_payload(amount='90000'),
        )
        response = self.client.post(
            reverse('core:dashboard:payment-create'),
            self.payment_payload(
                amount='1000', paid_at=self.local_datetime(minutes=5)),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertContains(response, 'Ce dossier est soldé')

    def test_cancelled_enrollment_is_not_offered(self):
        self.enrollment.status = Enrollment.Status.CANCELLED
        self.enrollment.save(update_fields=['status'])
        page = self.client.get(reverse('core:dashboard:payment-create'))
        self.assertEqual(
            list(page.context['form'].fields['enrollment'].queryset), [])

    def test_pending_enrollment_warning_is_displayed(self):
        student = self.make_student()
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        page = self.client.get(
            reverse('core:dashboard:payment-create'),
            {'student': student.pk},
        )
        self.assertContains(page, 'Inscriptions en attente de validation')
        self.assertContains(page, 'en attente de validation')

    def test_direction_dashboard_lists_pending_enrollments(self):
        student = self.make_student('tableau.direction@test.local')
        self.client.post(
            reverse('core:dashboard:payment-create'),
            {'form_kind': 'enroll', **self.counter_payload(student)},
        )
        enrollment = Enrollment.objects.get(student=student)
        page = self.client_for(self.direction).get(
            reverse('core:dashboard:direction-dashboard'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Inscriptions en attente de validation')
        self.assertContains(page, enrollment.student.get_full_name())
        self.assertContains(page, reverse(
            'core:dashboard:enrollment-validate', args=[enrollment.pk]))
