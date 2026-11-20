import logging

from django.core.mail import send_mail
from django.db.models import IntegerField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from . import parametres
from .models import (
    AccountStatus, AuditLog, Enrollment, Notification, Payment,
    RoleKey, ScholarshipApplication, User,
)

logger = logging.getLogger(__name__)

# Tout rôle autre qu'étudiant désigne un membre du staff. La liste est dérivée
# de l'énumération pour qu'un rôle ajouté plus tard soit compté sans retouche.
STAFF_ROLE_KEYS = tuple(
    key for key in RoleKey.values if key != RoleKey.ETUDIANT
)


def students_count(*, only_active: bool = False):
    """Le nombre de comptes portant le rôle étudiant.

    Un compte qui cumule étudiant et encadrement ne compte qu'une fois : la
    jointure sur les rôles multiplierait sinon les lignes. « only_active »
    restreint aux comptes approuvés, ce que les tableaux de bord appellent
    « étudiants actifs ».
    """
    comptes = User.objects.filter(roles__key=RoleKey.ETUDIANT)
    if only_active:
        comptes = comptes.filter(account_status=AccountStatus.ACTIVE)
    return comptes.distinct().count()


def platform_counts():
    """Les trois nombres affichés en tête des tableaux de bord.

    « Utilisateurs » compte tous les comptes, y compris ceux en attente
    d'approbation. « Étudiants » ne retient que les comptes portant le rôle
    étudiant. « Staff » retient tout compte portant au moins un autre rôle :
    un compte sans rôle n'est donc ni étudiant ni staff.
    """
    return {
        'total_users': User.objects.count(),
        'total_students': students_count(),
        'total_staff': User.objects.filter(
            roles__key__in=STAFF_ROLE_KEYS
        ).distinct().count(),
    }


def outstanding_receivables():
    """Somme des restes à payer, dossier par dossier.

    Un trop-perçu sur un dossier ne doit pas réduire la dette d'un autre :
    on additionne donc ``max(total dû - payé, 0)`` pour chaque inscription active.
    """
    paid = Payment.objects.filter(
        enrollment=OuterRef('pk'),
        status=Payment.Status.COMPLETED,
    ).values('enrollment').annotate(total=Sum('amount')).values('total')

    dossiers = Enrollment.objects.filter(
        status=Enrollment.Status.ACTIVE
    ).select_related(
        'session__course'
    ).annotate(
        paid_total=Coalesce(
            Subquery(paid, output_field=IntegerField()), Value(0)
        )
    )
    return sum(
        max(dossier.total_due - dossier.paid_total, 0)
        for dossier in dossiers
    )


def enrollments_waiting_validation(limit=10):
    """Inscriptions ouvertes au guichet, en attente d'une validation.

    La file est la même sur chaque tableau de bord habilité à valider :
    direction, caisse, supervision pédagogique, super administrateur.
    """
    return (
        Enrollment.objects.filter(status=Enrollment.Status.PENDING)
        .select_related('student', 'session__course')
        .order_by('enrolled_at')[:limit]
    )


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


def notifier_changement_statut_bourse(application, statut_precedent,
                                      request=None):
    """Notifie le candidat d'un changement de statut, dans l'application et par e-mail.

    La notification interne est écrite même si le courrier échoue : le candidat
    la retrouvera dans son espace. ``sent_at`` n'est renseigné que si l'e-mail
    est effectivement parti, pour ne pas laisser croire à un envoi réussi.
    """
    destinataire = (
        application.applicant_user.email
        if application.applicant_user else application.email
    )
    if not destinataire:
        return False

    libelles = dict(ScholarshipApplication.Status.choices)
    contexte = {
        'reference': application.reference,
        'avant': libelles.get(statut_precedent, statut_precedent),
        'apres': application.get_status_display(),
        'nom': parametres.nom(),
    }
    titre = _("Décision sur votre candidature de bourse")
    message = _(
        "Le statut de votre candidature %(reference)s est passé de %(avant)s à %(apres)s."
    ) % contexte

    suivi = reverse('core:bourses:scholarship-tracking')
    if request is not None:
        suivi = request.build_absolute_uri(suivi)
    corps = "\n\n".join(str(partie) for partie in [
        _("Bonjour,"),
        message,
        _("Vous pouvez suivre votre dossier à l’adresse %(url)s avec la référence %(reference)s et le jeton %(jeton)s.") % {
            'url': suivi,
            'reference': application.reference,
            'jeton': application.tracking_token,
        },
        _("Cordialement,"),
        contexte['nom'],
    ])

    notification = Notification.objects.create(
        user=application.applicant_user,
        email=destinataire,
        title=str(titre),
        message=message,
        notification_type=Notification.Type.SCHOLARSHIP_STATUS,
    )
    try:
        envoye = send_mail(
            _("%(reference)s — %(statut)s — %(nom)s") % {
                'reference': application.reference,
                'statut': contexte['apres'],
                'nom': contexte['nom'],
            },
            corps,
            None,
            [destinataire],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Envoi du mail de décision de bourse impossible")  # i18n-exempt: ligne de log interne, jamais affichée
        envoye = 0
    if envoye:
        notification.sent_at = timezone.now()
        notification.save(update_fields=['sent_at'])
    return bool(envoye)
