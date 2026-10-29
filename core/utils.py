from .models import AuditLog


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
