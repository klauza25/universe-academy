from django.db import migrations


VISIT_REASONS = [
    "Demande de renseignements",
    "Inscription à une formation",
    "Demande de renseignements sur les tarifs",
    "Paiement ou question concernant un paiement",
    "Rencontre avec un formateur",
    "Demande de document administratif",
    "Renseignement concernant une bourse d'études",
    "Rendez-vous avec la Direction",
    "Rencontre avec un partenaire",
    "Dépôt ou retrait d'un document",
    "Autre motif",
]

INCOMES = [
    "Paiements des étudiants",
    "Autres recettes",
    "Subventions et dons",
]

EXPENSES = [
    "Salaires",
    "Paiements des formateurs",
    "Avances sur salaire",
    "Maintenance informatique",
    "Achat de matériel informatique",
    "Fournitures et consommables",
    "Déplacements et missions",
    "Charges de fonctionnement",
    "Entretien des locaux",
    "Dépenses administratives",
    "Autres dépenses",
]


def seed(apps, schema_editor):
    VisitReason = apps.get_model('core', 'VisitReason')
    TransactionCategory = apps.get_model('core', 'TransactionCategory')
    CashAccount = apps.get_model('core', 'CashAccount')
    CashTransaction = apps.get_model('core', 'CashTransaction')
    Payment = apps.get_model('core', 'Payment')
    Expense = apps.get_model('core', 'Expense')
    Enrollment = apps.get_model('core', 'Enrollment')

    for index, label in enumerate(VISIT_REASONS):
        VisitReason.objects.get_or_create(
            label=label, defaults={'order': index}
        )

    for label in INCOMES:
        TransactionCategory.objects.get_or_create(
            name=label, direction='IN'
        )
    for label in EXPENSES:
        TransactionCategory.objects.get_or_create(
            name=label, direction='OUT'
        )

    cash, _ = CashAccount.objects.get_or_create(
        name='Caisse principale',
        defaults={'kind': 'CASH', 'opening_balance': 0},
    )
    mobile, _ = CashAccount.objects.get_or_create(
        name='Mobile Money',
        defaults={'kind': 'MOBILE_MONEY', 'opening_balance': 0},
    )

    income_cat = TransactionCategory.objects.filter(
        name='Paiements des étudiants', direction='IN'
    ).first()
    other_out = TransactionCategory.objects.filter(
        name='Autres dépenses', direction='OUT'
    ).first()

    year = __import__('django.utils.timezone', fromlist=['timezone']).now().year
    counter = {'n': 0}

    def next_ref():
        counter['n'] += 1
        reference = f"TRX-{year}-{counter['n']:04d}"
        while CashTransaction.objects.filter(reference=reference).exists():
            counter['n'] += 1
            reference = f"TRX-{year}-{counter['n']:04d}"
        return reference

    for payment in Payment.objects.filter(status='COMPLETED', transaction__isnull=True):
        account = mobile if payment.method == 'MOBILE_MONEY' else cash
        student = payment.enrollment.student
        student_name = (
            f"{student.first_name} {student.last_name}".strip()
            or student.email
        )
        tx = CashTransaction.objects.create(
            reference=next_ref(),
            tx_type='IN',
            category=income_cat,
            label=f"Paiement étudiant {payment.reference}",
            amount=payment.amount,
            currency=payment.currency,
            occurred_at=payment.paid_at,
            account=account,
            method=payment.method,
            counterparty=student_name,
            status='VALIDATED',
            created_by=payment.recorded_by,
        )
        payment.transaction = tx
        payment.save(update_fields=['transaction'])

    for expense in Expense.objects.filter(transaction__isnull=True):
        tx = CashTransaction.objects.create(
            reference=next_ref(),
            tx_type='OUT',
            category=other_out,
            label=expense.category,
            description=expense.description,
            amount=expense.amount,
            currency=expense.currency,
            occurred_at=expense.created_at,
            account=cash,
            method='CASH',
            status='VALIDATED',
            created_by=expense.created_by,
        )
        expense.transaction = tx
        expense.save(update_fields=['transaction'])

    for enrollment in Enrollment.objects.select_related('session__course'):
        if enrollment.net_amount == 0 and enrollment.tariff_amount == 0:
            fee = enrollment.session.course.fee_amount or 0
            enrollment.tariff_amount = fee
            enrollment.net_amount = fee
            enrollment.save(update_fields=['tariff_amount', 'net_amount'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_cashaccount_visitreason_attendance_absence_reason_and_more'),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
