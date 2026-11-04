"""Les files que la cloche de la barre supérieure doit rappeler.

Deux règles commandent tout le module : une tâche ne s’affiche que si l’écran
pointé sait la traiter, et le rôle appelé est celui que cet écran admet déjà.
Les compteurs sont repris des tableaux de bord — le module n’invente aucune
règle métier nouvelle, sinon la cloche annoncerait du travail impossible à faire.
"""

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .decorators import ENROLLMENT_VALIDATION_ROLES, roles_attribuables
from .models import (
    AccessRequest, CashTransaction, Enrollment, Notification,
    ROLE_DASHBOARD_ROUTES, ScholarshipApplication, SessionRecord,
)

# Public de chaque écran de traitement, tel que son propre décorateur l'admet.
ECRAN_ACCES_ROLES = ('SUPER_ADMIN', 'ADMIN', 'RESP_PEDA')
ECRAN_BOURSE_ROLES = ('SUPER_ADMIN', 'ADMIN')
ECRAN_JOURNAL_ROLES = ('ASSISTANT_ADMIN', 'DIRECTION', 'SUPER_ADMIN')
ECRAN_SEANCES_ROLES = ('RESP_PEDA',)

MAXI_NOTIFICATIONS = 5


def tableau_des_files(user):
    """Renvoie (tâches à traiter, notifications non lues, total compté).

    La pastille reste allumée tant que le total est positif : c’est le travail
    qui l’éteint, pas le temps. Les notifications au-delà de cinq ne sont plus
    listées dans le panneau mais restent comptées.
    """
    roles = set(user.roles.values_list('key', flat=True))
    attribuables = roles_attribuables(user)
    taches = []

    def retenir(libelle, nombre, url):
        if nombre:
            taches.append({'nom': libelle, 'nombre': nombre, 'url': url})

    if roles & set(ENROLLMENT_VALIDATION_ROLES):
        retenir(
            _("Inscriptions en attente de validation"),
            Enrollment.objects.filter(
                status=Enrollment.Status.PENDING).count(),
            reverse(ROLE_DASHBOARD_ROUTES.get(
                user.primary_role, 'core:dashboard:dashboard-router')),
        )
    if roles & set(ECRAN_ACCES_ROLES):
        retenir(
            _("Demandes d'accès à approuver"),
            AccessRequest.objects.filter(
                status=AccessRequest.Status.PENDING,
                requested_role__in=attribuables,
            ).count(),
            reverse('core:dashboard:access-requests'),
        )
    if roles & set(ECRAN_BOURSE_ROLES):
        retenir(
            _("Candidatures de bourse à instruire"),
            ScholarshipApplication.objects.filter(
                status=ScholarshipApplication.Status.SUBMITTED).count(),
            reverse('core:dashboard:scholarship-review-list'),
        )
    if roles & set(ECRAN_JOURNAL_ROLES):
        retenir(
            _("Écritures de caisse en brouillon"),
            CashTransaction.objects.filter(
                status=CashTransaction.Status.DRAFT).count(),
            reverse('core:dashboard:journal'),
        )
    if roles & set(ECRAN_SEANCES_ROLES):
        retenir(
            _("Séances planifiées à saisir"),
            SessionRecord.objects.filter(
                status=SessionRecord.Status.PLANNED,
                date__gte=timezone.localdate(),
            ).count(),
            reverse('core:dashboard:session-records'),
        )

    non_lues = Notification.objects.filter(user=user, is_read=False)
    total = sum(t['nombre'] for t in taches) + non_lues.count()
    return taches, non_lues[:MAXI_NOTIFICATIONS], total
