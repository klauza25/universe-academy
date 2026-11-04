"""Reprise des mois déjà encaissés : la note le disait, le champ le porte.

Les 268 mensualités importées portent la date du mois réglé dans ``paid_at`` et
le motif en tête de ``note`` ; les 170 frais d'inscription portent le même
préfixe sans mois. La reprise lit ces deux marques — elle ne devine jamais un
mois, et ne touche ni montant, ni statut, ni référence.
"""
from django.db import migrations
from django.utils import timezone

MENSUALITE = 'Mensualité'
FRAIS = "Frais d'inscription"


def reprise(apps, schema_editor):
    Payment = apps.get_model('core', 'Payment')
    for paiement in Payment.objects.iterator():
        note = paiement.note or ''
        if note.startswith(MENSUALITE):
            regle = timezone.localtime(paiement.paid_at)
            paiement.motif = 'MONTHLY'
            paiement.period_year = regle.year
            paiement.period_month = regle.month
        elif note.startswith(FRAIS):
            paiement.motif = 'ENROLLMENT'
        else:
            continue
        paiement.save(update_fields=['motif', 'period_year', 'period_month'])


def retour_arriere(apps, schema_editor):
    Payment = apps.get_model('core', 'Payment')
    Payment.objects.all().update(motif='OTHER', period_year=None,
                                 period_month=None)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_payment_motif_payment_period_month_and_more'),
    ]

    operations = [
        migrations.RunPython(reprise, retour_arriere),
    ]
