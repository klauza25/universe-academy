"""Tests du rapport de cohérence financière (commande en lecture seule)."""
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.utils import timezone

from core.models import CashTransaction, Payment

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
            recorded_by=self.assistant,
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
            recorded_by=self.assistant,
        )
        output = self.run_command()
        self.assertIn("PAIEMENT SANS CAISSE", output)

    def test_une_ecriture_datee_dans_le_futur_se_signale(self):
        """Un règlement postérieur à aujourd'hui ne représente pas un argent reçu."""
        dans_un_mois = timezone.localtime() + timedelta(days=30)
        paiement = Payment.objects.create(
            enrollment=self.enrollment, amount=30000,
            method=Payment.Method.CASH, paid_at=dans_un_mois,
            recorded_by=self.assistant,
        )
        CashTransaction.objects.create(
            tx_type=CashTransaction.Type.IN, label='Entrée à venir',
            amount=30000, currency='XAF', occurred_at=dans_un_mois,
            account=self.cash, method=Payment.Method.CASH,
            status=CashTransaction.Status.VALIDATED, created_by=self.assistant,
        )
        output = self.run_command()
        self.assertIn("DATE FUTURE", output)
        self.assertIn(paiement.reference, output)
        self.assertIn("CAISSE FUTURE", output)
