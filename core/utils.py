from django.db.models import F, IntegerField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce, Greatest

from .models import AuditLog, Enrollment, Payment


def outstanding_receivables():
    """Somme des restes à payer, dossier par dossier.

    Un trop-perçu sur un dossier ne doit pas réduire la dette d'un autre :
    on additionne donc ``max(net - payé, 0)`` pour chaque inscription active.
    """
    paid = Payment.objects.filter(
        enrollment=OuterRef('pk'),
        status=Payment.Status.COMPLETED,
    ).values('enrollment').annotate(total=Sum('amount')).values('total')

    return Enrollment.objects.filter(
        status=Enrollment.Status.ACTIVE
    ).annotate(
        paid_total=Coalesce(
            Subquery(paid, output_field=IntegerField()), Value(0)
        )
    ).aggregate(
        total=Sum(Greatest(F('net_amount') - F('paid_total'), Value(0)))
    )['total'] or 0


def get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_audit(request, action, entity_type, entity_id,
              before=None, after=None):
    actor = request.user if request and hasattr(request, 'user') and request.user.is_authenticated else None
    ip = get_client_ip(request) if request else None
    AuditLog.objects.create(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        before_summary=before,
        after_summary=after,
        ip_address=ip,
    )
