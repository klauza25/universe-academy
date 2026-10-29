"""Tests du rapport de cohérence financière (commande en lecture seule)."""
from io import StringIO

from django.core.management import call_command

from core.models import Payment

from .base import BusinessTestBase


class AuditFinancesCommandTests(BusinessTestBase):
    def run_command(self, *args):
        out = StringIO()
        call_command('audit_finances', *args, stdout=out)
        return out.getvalue()

    def test_clean_database_reports_no_issue(self):
        output = self.run_command()
        self.assertIn("Aucune incohérence financière détectée", output)

    def test_overpayment_is_reported_and_can_fail_the_command(self):
        Payment.objects.create(
            enrollment=self.enrollment,
            amount=95000,
            method=Payment.Method.CASH,
            recorded_by=self.comptable,
        )
        output = self.run_command()
        self.assertIn("TROP-PERCU", output)
        self.assertIn("etudiant@test.local", output)
        with self.assertRaises(SystemExit):
            self.run_command('--fail-on-issue')

    def test_payment_without_cash_transaction_is_reported(self):
        Payment.objects.create(
            enrollment=self.enrollment,
            amount=1000,
            method=Payment.Method.CASH,
            recorded_by=self.comptable,
        )
        output = self.run_command()
        self.assertIn("PAIEMENT SANS CAISSE", output)
