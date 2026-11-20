"""Lancement de la synchronisation des classeurs depuis le back-office.

Un seul clic déclenche la même commande que la tâche planifiée. Un verrou fichier
empêche deux lancements simultanés ; la commande pose elle-même une copie de
sécurité avant d'écrire, et son rapport sert de compte rendu à l'écran.
"""
from __future__ import annotations

import io
import os
import time
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.core.management import call_command
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from .decorators import super_admin_required
from .utils import log_audit

VERROU_NOM = '.synchronisation-classeurs.lock'  # i18n-exempt : nom de fichier technique
DELAI_VERROU = 15 * 60


def _chemin_verrou() -> Path:
    return Path(settings.BASE_DIR) / VERROU_NOM


def _resumer(sortie: str) -> str:
    """Les dernières lignes du rapport tiennent lieu de compte rendu court."""
    lignes = [ligne.strip() for ligne in sortie.splitlines() if ligne.strip()]
    return ' '.join(lignes[-3:])[:400]


@super_admin_required
def page_synchronisation(request):
    """Affiche la page de chargement qui précède le lancement de la commande."""
    return render(request, 'dashboard/super_admin/synchronisation.html')


@super_admin_required
@require_POST
def synchroniser_classeurs(request):
    """Lance la synchronisation en écriture puis revient au tableau de bord."""
    verrou = _chemin_verrou()
    try:
        if verrou.exists() and time.time() - verrou.stat().st_mtime > DELAI_VERROU:
            verrou.unlink()
        fd = os.open(verrou, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        messages.warning(request, _("Une synchronisation est déjà en cours."))
        return redirect('core:dashboard:super-admin-dashboard')

    sortie = io.StringIO()
    try:
        with os.fdopen(fd, 'w', encoding='utf-8'):
            pass
        call_command('synchroniser_classeurs', ecrire=True,
                     stdout=sortie, stderr=sortie)
    except Exception as erreur:
        detail = str(erreur)[:300]
        log_audit(request, 'SYNCHRONISATION_CLASSEURS', 'System', 'google-sheets',
                  after=f'Échec : {detail}')
        messages.error(
            request, _("Synchronisation impossible : %(detail)s") % {'detail': detail})
    else:
        resume = _resumer(sortie.getvalue())
        log_audit(request, 'SYNCHRONISATION_CLASSEURS', 'System', 'google-sheets',
                  after=resume)
        messages.success(
            request, _("Synchronisation terminée : %(resume)s") % {'resume': resume})
    finally:
        try:
            verrou.unlink()
        except FileNotFoundError:
            pass

    return redirect('core:dashboard:super-admin-dashboard')
