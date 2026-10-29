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
    """Accès réservé aux rôles listés.

    Les rôles à accès transversal (``SUPER_ADMIN`` et ``ADMIN``) sont toujours
    autorisés : l'administrateur doit pouvoir consulter tous les modules.
    """
    def decorator(view_func):
        @wraps(view_func)
        @active_account_required
        def wrapper(request, *args, **kwargs):
            if not (request.user.is_elevated or
                    request.user.has_any_role(*role_keys)):
                return HttpResponseForbidden(
                    "Vous n'avez pas les permissions nécessaires."
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def business_write_required(*role_keys):
    """Écriture métier réservée aux rôles opérationnels.

    Les rôles transversaux (``SUPER_ADMIN`` et ``ADMIN``) conservent la
    consultation complète mais ne peuvent pas modifier les données métier :
    transactions, étudiants, inscriptions, présences, ressources.
    """
    def decorator(view_func):
        @wraps(view_func)
        @active_account_required
        def wrapper(request, *args, **kwargs):
            if request.user.is_elevated:
                return HttpResponseForbidden(
                    "Consultation seule : cette action relève du rôle métier."
                )
            if not request.user.has_any_role(*role_keys):
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
            if not (request.user.is_elevated or
                    request.user.has_perm_key(perm_key)):
                return HttpResponseForbidden("Permission refusée.")
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def super_admin_required(view_func):
    """Réservé au SUPER_ADMIN, y compris face à un ADMIN.

    Utilisé pour les opérations sensibles : création de comptes, attribution de
    rôles et validation des demandes d'accès.
    """
    @wraps(view_func)
    @active_account_required
    def wrapper(request, *args, **kwargs):
        if not request.user.has_role('SUPER_ADMIN'):
            return HttpResponseForbidden(
                "Cette action est réservée au super administrateur."
            )
        return view_func(request, *args, **kwargs)
    return wrapper
