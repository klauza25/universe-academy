from django.db import migrations


def repair_counterparty(apps, schema_editor):
    CashTransaction = apps.get_model('core', 'CashTransaction')
    Payment = apps.get_model('core', 'Payment')

    bogus = CashTransaction.objects.filter(
        counterparty__startswith='User object ('
    )
    for tx in bogus:
        student = Payment.objects.filter(
            transaction_id=tx.pk
        ).values_list(
            'enrollment__student__first_name',
            'enrollment__student__last_name',
            'enrollment__student__email',
        ).first()
        if student is None:
            continue
        first, last, email = student
        name = f'{first or ""} {last or ""}'.strip() or email
        if name:
            tx.counterparty = name
            tx.save(update_fields=['counterparty'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_seed_business_defaults'),
    ]

    operations = [
        migrations.RunPython(
            repair_counterparty, migrations.RunPython.noop,
        ),
    ]
