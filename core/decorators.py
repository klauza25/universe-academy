from functools import wraps
from django.shortcuts import redirect
from django.http import HttpResponseForbidden
from django.utils.translation import gettext_lazy as _
from .models import AccountStatus, REQUESTABLE_ROLES


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
                    _("Vous n'avez pas les permissions nécessaires.")
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
                    _("Consultation seule : cette action relève du rôle métier.")
                )
            if not request.user.has_any_role(*role_keys):
                return HttpResponseForbidden(
                    _("Vous n'avez pas les permissions nécessaires.")
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def cash_write_required(*role_keys):
    """Écriture comptable : les rôles de la caisse et l'administration, à égalité.

    La direction a demandé que le super administrateur puisse aussi bien poser
    qu'annuler une écriture et administrer les comptes : la caisse fait
    exception à la consultation seule des rôles transversaux. Rien n'est
    silencieux pour autant — le service d'écriture laisse sa ligne d'audit.
    """
    def decorator(view_func):
        @wraps(view_func)
        @active_account_required
        def wrapper(request, *args, **kwargs):
            if not (request.user.is_elevated or
                    request.user.has_any_role(*role_keys)):
                return HttpResponseForbidden(
                    _("Vous n'avez pas les permissions nécessaires.")
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


ENROLLMENT_VALIDATION_ROLES = ('DIRECTION', 'SUPER_ADMIN', 'ASSISTANT_ADMIN', 'RESP_PEDA')

# Rôles qu'un responsable pédagogique a le droit d'attribuer en approuvant une
# demande d'accès : son équipe (formateurs) et les étudiants. L'assistant
# administratif porte la caisse, le secrétariat et le poste de resp. pédagogie
# lui-même restent décidés par un super administrateur — sinon un resp. peda
# fabriquerait ses pairs et les comptes financiers de l'établissement.
RESP_PEDA_ROLES_ATTRIBUABLES = ('FORMATEUR', 'ETUDIANT')


def roles_attribuables(user):
    """Rôles que cet appelant peut attribuer depuis l'écran des demandes d'accès."""
    if user.is_elevated:
        return set(REQUESTABLE_ROLES)
    if user.has_role('RESP_PEDA'):
        return set(RESP_PEDA_ROLES_ATTRIBUABLES)
    return set()


def enrollment_validation_required(view_func):
    """Validation d'un dossier d'inscription.

    Quatre rôles peuvent valider depuis leur propre tableau de bord : la
    direction (référente), l'assistant administratif, la supervision
    pédagogique et le super administrateur. La chaîne « inscription au guichet →
    validation → encaissement » ne doit jamais s'arrêter faute de valideur
    disponible. L'ADMIN reste en consultation seule (politique transversale) et
    chaque validation laisse sa trace dans l'audit (ENROLLMENT_VALIDATE).
    """
    @wraps(view_func)
    @active_account_required
    def wrapper(request, *args, **kwargs):
        if request.user.has_any_role(*ENROLLMENT_VALIDATION_ROLES):
            return view_func(request, *args, **kwargs)
        return HttpResponseForbidden(
            _("La validation d'une inscription est réservée à la direction, à l'assistant administratif, à la supervision pédagogique et au super administrateur.")
        )
    return wrapper


def payment_write_required(view_func):
    """Encaissement d'un paiement étudiant : la matrice « Permissions » décide.

    Le droit « finance.write » remplace la liste de rôles écrite dans le code :
    l'éditeur de permissions ouvre et ferme cette porte, poste par poste. Les
    rôles transversaux y ont accès comme en caisse — la direction a demandé que
    le super administrateur puisse encaisser aussi ; l'écriture reste jugée par
    le service de caisse et laisse sa ligne d'audit.
    """
    @wraps(view_func)
    @active_account_required
    def wrapper(request, *args, **kwargs):
        if request.user.is_elevated:
            return view_func(request, *args, **kwargs)
        if not request.user.has_perm_key('finance.write'):
            return HttpResponseForbidden(
                _("Encaisser un paiement étudiant demande le droit « Saisir des paiements » : un super administrateur peut l'accorder à votre poste.")
            )
        return view_func(request, *args, **kwargs)
    return wrapper


def permission_required(perm_key):
    def decorator(view_func):
        @wraps(view_func)
        @active_account_required
        def wrapper(request, *args, **kwargs):
            if not (request.user.is_elevated or
                    request.user.has_perm_key(perm_key)):
                return HttpResponseForbidden(_("Permission refusée."))
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def super_admin_required(view_func):
    """Réservé au SUPER_ADMIN, y compris face à un ADMIN.

    Utilisé pour les opérations sensibles : création de comptes et attribution
    de rôles depuis l'écran « Utilisateurs ».
    """
    @wraps(view_func)
    @active_account_required
    def wrapper(request, *args, **kwargs):
        if not request.user.has_role('SUPER_ADMIN'):
            return HttpResponseForbidden(
                _("Cette action est réservée au super administrateur.")
            )
        return view_func(request, *args, **kwargs)
    return wrapper
