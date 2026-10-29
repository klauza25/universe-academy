from django.utils import timezone


def _greeting():
    hour = timezone.localtime().hour
    if hour < 12:
        return "Bonjour"
    if hour < 18:
        return "Bon après-midi"
    return "Bonsoir"


def _initials(user):
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    if first or last:
        return f"{first[:1]}{last[:1]}".upper() or "?"
    email = (user.email or "").strip()
    return email[:2].upper() or "?"


def user_profile_context(request):
    ctx = {}
    if request.user.is_authenticated:
        from .models import RoleKey

        primary = request.user.primary_role
        try:
            primary_label = RoleKey(primary).label if primary else ""
        except ValueError:
            primary_label = primary or ""

        ctx['user_roles'] = list(
            request.user.roles.values_list('key', flat=True)
        )
        ctx['user_primary_role'] = primary
        ctx['user_primary_role_label'] = primary_label
        ctx['user_internal_code'] = request.user.internal_code
        ctx['user_initials'] = _initials(request.user)
        ctx['user_display_name'] = request.user.display_label
        ctx['user_avatar_url'] = (
            request.user.avatar.url if request.user.avatar else ''
        )
        ctx['greeting'] = _greeting()
        ctx['can_manage_users'] = request.user.has_any_role(
            'SUPER_ADMIN', 'ADMIN'
        )
        try:
            ctx['unread_notifications'] = (
                request.user.notifications.filter(is_read=False).count()
            )
        except Exception:
            ctx['unread_notifications'] = 0
    return ctx


def clerk_context(request):
    from django.conf import settings

    if not getattr(settings, 'CLERK_ENABLED', False):
        return {'clerk_enabled': False}

    return {
        'clerk_enabled': True,
        'clerk_publishable_key': settings.CLERK_PUBLISHABLE_KEY,
        'clerk_frontend_api': settings.CLERK_FRONTEND_API,
        'clerk_js_url': settings.CLERK_JS_URL,
        'clerk_ui_url': settings.CLERK_UI_URL,
    }
