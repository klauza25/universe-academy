"""Tests de la comptabilité : journal, caisses, clôtures et paiements."""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from core.models import (
    CashAccount, CashClosure, CashTransaction, Enrollment, Payment,
    RoleKey, TransactionCategory,
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
