"""Tests de la supervision financière et du journal d'audit du super admin."""
import uuid
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from core.models import (
    AuditLog, CashTransaction, Payment, TransactionCategory,
)

from .base import BusinessTestBase

SUPERVISION_URL = 'core:dashboard:finance-supervision'
DASHBOARD_URL = 'core:dashboard:super-admin-dashboard'
AUDIT_URL = 'core:dashboard:audit-log'


class FinanceSupervisionTests(BusinessTestBase):
    def setUp(self):
        self.salaries = TransactionCategory.objects.get(
            name='Salaires', direction=TransactionCategory.Direction.OUT,
        )
        self.income = self.make_tx(
            50000, counterparty='Aline Étudiante',
            category=self.income_category,
        )
        self.expense = self.make_tx(
            20000, tx_type=CashTransaction.Type.OUT, account=self.mobile,
            method=Payment.Method.MOBILE_MONEY, counterparty='Atelier Info',
            category=self.expense_category,
        )
        self.salary = self.make_tx(
            30000, tx_type=CashTransaction.Type.OUT,
            counterparty='Formateur Test', category=self.salaries,
        )
        self.draft = self.make_tx(
            15000, status=CashTransaction.Status.DRAFT,
            category=self.income_category,
        )
        self.cancelled = self.make_tx(
            7000, tx_type=CashTransaction.Type.OUT,
            status=CashTransaction.Status.CANCELLED,
            category=self.expense_category,
        )

    def make_tx(self, amount, *, tx_type=CashTransaction.Type.IN,
                account=None, category=None, method=Payment.Method.CASH,
                status=CashTransaction.Status.VALIDATED, counterparty=''):
        return CashTransaction.objects.create(
            tx_type=tx_type,
            amount=amount,
            account=account or self.cash,
            category=category,
            method=method,
            status=status,
            counterparty=counterparty,
            label=f'Opération {amount}',
            occurred_at=timezone.now(),
            created_by=self.comptable,
        )

    def test_supervision_is_reserved_to_elevated_roles(self):
        for user in (self.super_admin, self.admin):
            response = self.client_for(user).get(reverse(SUPERVISION_URL))
            self.assertEqual(response.status_code, 200, user.primary_role)
        for user in (
            self.comptable, self.direction, self.secretaire,
            self.formateur, self.etudiant, self.accueil,
        ):
            response = self.client_for(user).get(reverse(SUPERVISION_URL))
            self.assertEqual(response.status_code, 403, user.primary_role)

    def test_supervision_lists_every_transaction_and_totals(self):
        response = self.client_for(self.super_admin).get(
            reverse(SUPERVISION_URL)
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['totals']['incoming'], 50000)
        self.assertEqual(response.context['totals']['outgoing'], 50000)
        self.assertEqual(response.context['net_total'], 0)
        self.assertEqual(response.context['pending_count'], 1)
        self.assertEqual(response.context['cancelled_count'], 1)
        for tx in (self.income, self.expense, self.salary,
                   self.draft, self.cancelled):
            self.assertContains(response, tx.reference)

    def test_supervision_filters_and_search(self):
        client = self.client_for(self.super_admin)

        response = client.get(reverse(SUPERVISION_URL), {'type': 'OUT'})
        self.assertContains(response, self.expense.reference)
        self.assertNotContains(response, self.income.reference)

        response = client.get(reverse(SUPERVISION_URL), {'q': 'Atelier Info'})
        self.assertContains(response, self.expense.reference)
        self.assertNotContains(response, self.salary.reference)

        response = client.get(reverse(SUPERVISION_URL), {'status': 'DRAFT'})
        self.assertContains(response, self.draft.reference)
        self.assertNotContains(response, self.income.reference)

        response = client.get(
            reverse(SUPERVISION_URL), {'category': str(self.salaries.id)},
        )
        self.assertContains(response, self.salary.reference)
        self.assertNotContains(response, self.expense.reference)

        response = client.get(
            reverse(SUPERVISION_URL), {'method': Payment.Method.MOBILE_MONEY},
        )
        self.assertContains(response, self.expense.reference)
        self.assertNotContains(response, self.salary.reference)

    def test_supervision_csv_export(self):
        response = self.client_for(self.super_admin).get(
            reverse(SUPERVISION_URL), {'export': 'csv', 'type': 'OUT'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        content = response.content.decode('utf-8-sig')
        self.assertIn('Référence;Date effective', content)
        self.assertIn(self.expense.reference, content)
        self.assertNotIn(self.income.reference, content)
        self.assert_audited('FINANCE_EXPORT')

    def test_dashboard_shows_real_finance_indicators(self):
        response = self.client_for(self.super_admin).get(
            reverse(DASHBOARD_URL)
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['month_income'], 50000)
        self.assertEqual(response.context['month_expense'], 50000)
        self.assertEqual(response.context['month_salaries'], 30000)
        self.assertEqual(response.context['month_payment_total'], 0)
        self.assertEqual(response.context['pending_transactions'], 1)
        self.assertEqual(response.context['incomplete_enrollments'], 1)
        self.assertEqual(response.context['outstanding_amount'], 90000)
        self.assertEqual(response.context['cash_total'], 0)
        self.assertContains(response, 'Supervision financière')
        self.assertContains(response, self.income.reference)

    def test_transaction_detail_shows_audit_history(self):
        AuditLog.objects.create(
            actor=self.comptable,
            action='CASH_TRANSACTION_CANCEL',
            entity_type='CashTransaction',
            entity_id=str(self.expense.id),
            before_summary={'status': 'VALIDATED'},
            after_summary={'status': 'CANCELLED'},
        )
        response = self.client_for(self.super_admin).get(
            reverse('core:dashboard:transaction-detail', args=[self.expense.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Historique des modifications')
        self.assertContains(response, 'CASH_TRANSACTION_CANCEL')
        self.assertContains(response, 'VALIDATED')


class AuditLogTests(BusinessTestBase):
    def setUp(self):
        self.entry_payment = AuditLog.objects.create(
            actor=self.comptable,
            action='PAYMENT_CREATE',
            entity_type='Payment',
            entity_id=str(uuid.uuid4()),
            after_summary={'amount': 10000},
        )
        self.entry_student = AuditLog.objects.create(
            actor=self.secretaire,
            action='STUDENT_EDIT',
            entity_type='User',
            entity_id=str(self.etudiant.id),
            before_summary={'phone': '000'},
            after_summary={'phone': '111'},
        )
        self.entry_export = AuditLog.objects.create(
            actor=self.super_admin,
            action='JOURNAL_EXPORT',
            entity_type='CashTransaction',
            entity_id='csv',
        )

    def test_only_super_admin_and_admin_can_read_audit_log(self):
        for user in (self.super_admin, self.admin):
            self.assertEqual(
                self.client_for(user).get(reverse(AUDIT_URL)).status_code,
                200,
            )
        for user in (self.comptable, self.secretaire, self.formateur):
            self.assertEqual(
                self.client_for(user).get(reverse(AUDIT_URL)).status_code,
                403,
            )

    def test_audit_log_filters(self):
        client = self.client_for(self.super_admin)

        response = client.get(reverse(AUDIT_URL), {'action': 'STUDENT_EDIT'})
        self.assertEqual(
            {entry.action for entry in response.context['page']},
            {'STUDENT_EDIT'},
        )

        response = client.get(reverse(AUDIT_URL), {'entity': 'Payment'})
        self.assertEqual(
            {entry.entity_type for entry in response.context['page']},
            {'Payment'},
        )

        response = client.get(
            reverse(AUDIT_URL), {'actor': str(self.secretaire.id)},
        )
        self.assertEqual(
            {entry.actor for entry in response.context['page']},
            {self.secretaire},
        )

        response = client.get(reverse(AUDIT_URL), {'q': 'secretaire@test.local'})
        self.assertEqual(
            {entry.action for entry in response.context['page']},
            {'STUDENT_EDIT'},
        )

        today = timezone.localdate().strftime('%Y-%m-%d')
        tomorrow = (timezone.localdate() + timedelta(days=1)).strftime(
            '%Y-%m-%d'
        )
        response = client.get(
            reverse(AUDIT_URL), {'from': today, 'to': tomorrow},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context['page'].paginator.count, 3,
        )

    def test_audit_log_handles_entries_without_uuid_entity(self):
        response = self.client_for(self.super_admin).get(reverse(AUDIT_URL))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'JOURNAL_EXPORT')
        self.assertContains(response, 'Voir les valeurs')
