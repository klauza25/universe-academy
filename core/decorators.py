from functools import wraps
from django.shortcuts import redirect
from django.http import HttpResponseForbidden
from .models import AccountStatus


def active_account_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('core:login')
        if request.user.account_status == AccountStatus.PENDING_APPROVAL:
            return redirect('core:pending-approval')
        if request.user.account_status != AccountStatus.ACTIVE:
            return redirect('core:access-denied')
        return view_func(request, *args, **kwargs)
    return wrapper


def role_required(*role_keys):
    def decorator(view_func):
        @wraps(view_func)
        @active_account_required
        def wrapper(request, *args, **kwargs):
            if not (request.user.has_role('SUPER_ADMIN') or
                    request.user.has_any_role(*role_keys)):
                return HttpResponseForbidden(
                    "Vous n'avez pas les permissions nécessaires."
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def permission_required(perm_key):
    def decorator(view_func):
        @wraps(view_func)
        @active_account_required
        def wrapper(request, *args, **kwargs):
            if not (request.user.has_role('SUPER_ADMIN') or
                    request.user.has_perm_key(perm_key)):
                return HttpResponseForbidden("Permission refusée.")
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
