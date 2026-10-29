"""Rapport en lecture seule des incohérences financières.

Ne corrige rien : l'opérateur examine les lignes signalées puis régularise
depuis l'interface métier (annulation, remboursement, correction de dossier).

Utilisation :
    python manage.py audit_finances
    python manage.py audit_finances --fail-on-issue   # code 1 si anomalie
"""
from django.core.management.base import BaseCommand

from core.models import CashAccount, Enrollment, Payment


class Command(BaseCommand):
    help = "Signale les incohérences financières sans modifier les données."

    def add_arguments(self, parser):
        parser.add_argument(
            '--fail-on-issue', action='store_true',
            help="Code de sortie 1 si au moins une anomalie est détectée.",
        )

    def handle(self, *args, **options):
        findings = []

        # 1. Trop-perçus : un paiement validé ne doit jamais dépasser le net dû.
        for enrollment in Enrollment.objects.select_related(
                'student', 'session__course'):
            paid = enrollment.total_paid
            if paid > enrollment.net_amount:
                findings.append(
                    f"TROP-PERCU {enrollment.student.email} / "
                    f"{enrollment.session.course.title} : payé={paid} "
                    f"net={enrollment.net_amount} "
                    f"excédent={paid - enrollment.net_amount} FCFA"
                )

        # 2. Paiements encaissés sans mouvement de caisse associé.
        orphans = Payment.objects.filter(
            status=Payment.Status.COMPLETED, transaction__isnull=True,
        ).select_related('enrollment__student')
        for payment in orphans:
            findings.append(
                f"PAIEMENT SANS CAISSE {payment.reference} "
                f"({payment.enrollment.student.email}) : {payment.amount} FCFA"
            )

        # 3. Montant du paiement différent du mouvement de caisse lié.
        for payment in Payment.objects.filter(
                status=Payment.Status.COMPLETED,
                transaction__isnull=False,
        ).select_related('transaction'):
            if payment.transaction.amount != payment.amount:
                findings.append(
                    f"MONTANT DIVERGENT {payment.reference} : paiement="
                    f"{payment.amount} caisse={payment.transaction.amount}"
                )

        # 4. Caisses dont le solde calculé est négatif.
        for account in CashAccount.objects.all():
            if account.balance < 0:
                findings.append(
                    f"SOLDE NEGATIF {account.name} : {account.balance} "
                    f"{account.currency}"
                )

        payment_total = Payment.objects.filter(
            status=Payment.Status.COMPLETED
        ).count()
        self.stdout.write(
            f"Paiements validés : {payment_total} | "
            f"Inscriptions : {Enrollment.objects.count()} | "
            f"Caisses : {CashAccount.objects.count()}"
        )

        if not findings:
            self.stdout.write(self.style.SUCCESS(
                "Aucune incohérence financière détectée."
            ))
            return

        self.stdout.write(self.style.WARNING(
            f"{len(findings)} anomalie(s) détectée(s) (aucune modification) :"
        ))
        for finding in findings:
            self.stdout.write(f"  - {finding}")

        if options['fail_on_issue']:
            raise SystemExit(1)
