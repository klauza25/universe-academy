"""Profil utilisateur : informations, photo, mot de passe et changement d'email vérifié."""
import logging
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.static import serve

from .decorators import active_account_required
from .forms import (
    AvatarForm, EmailChangeForm, PasswordChangeForm, ProfileForm,
)
from .models import AccountStatus, Notification, ROLE_DASHBOARD_ROUTES, User
from .utils import log_audit

logger = logging.getLogger(__name__)

EMAIL_TOKEN_SALT = 'univers-academy.email-change'
EMAIL_TOKEN_MAX_AGE = 60 * 60 * 24  # 24 h


def changer_avatar(request, personne):
    """Pose ou retire la photo de profil d'une personne.

    Un seul chemin pour les deux cas : l'intéressé écran « Mon profil », un
    membre du personnel depuis la fiche de la personne. Le nettoyage du
    fichier remplacé et la trace d'audit sont les mêmes dans les deux cas, et
    le résultat se lit dans la notification.
    """
    if request.POST.get('action') == 'avatar_delete':
        if personne.retirer_avatar():
            log_audit(request, 'PROFILE_AVATAR_DELETE', 'User', str(personne.id))
            messages.success(request, _("Photo supprimée, avatar par défaut rétabli."))
        return
    formulaire = AvatarForm(request.POST, request.FILES)
    if formulaire.is_valid():
        personne.poser_avatar(formulaire.cleaned_data['avatar'])
        log_audit(request, 'PROFILE_AVATAR', 'User', str(personne.id))
        messages.success(request, _("Photo de profil enregistrée."))
        return
    erreurs = ' '.join(str(e) for liste in formulaire.errors.values() for e in liste)
    messages.error(request,
                   _("Photo non enregistrée : %(erreur)s") % {'erreur': erreurs})


@login_required
@active_account_required
def profile_view(request):
    user = request.user
    profile_form = ProfileForm(instance=user)
    avatar_form = AvatarForm()
    email_form = EmailChangeForm(user=user)
    password_form = PasswordChangeForm(user=user)

    if request.method == 'POST':
        action = request.POST.get('action', 'profile')

        if action == 'profile':
            profile_form = ProfileForm(request.POST, instance=user)
            if profile_form.is_valid():
                before = {
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'display_name': user.display_name,
                    'phone': user.phone,
                }
                profile_form.save()
                log_audit(
                    request, 'PROFILE_UPDATE', 'User', str(user.id),
                    before=before,
                    after={
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'display_name': user.display_name,
                        'phone': user.phone,
                    },
                )
                messages.success(request, _("Votre profil a été mis à jour."))
                return redirect('core:dashboard:profile')

        elif action in ('avatar', 'avatar_delete'):
            changer_avatar(request, user)
            return redirect('core:dashboard:profile')

        elif action == 'email':
            email_form = EmailChangeForm(request.POST, user=user)
            if email_form.is_valid():
                new_email = email_form.cleaned_data['new_email']
                token = signing.dumps(
                    {'uid': str(user.id), 'email': new_email},
                    salt=EMAIL_TOKEN_SALT,
                )
                confirm_url = request.build_absolute_uri(
                    reverse('core:dashboard:profile-email-confirm', args=[token])
                )
                subject = _("Confirmation de votre nouvelle adresse — Univers Academy")
                body = (
                    _("Bonjour,") + "\n\n"
                    + _("Vous avez demandé à utiliser cette adresse pour votre compte Univers Academy.") + "\n"
                    + _("Confirmez le changement en ouvrant ce lien :") + f"\n{confirm_url}\n\n"
                    + _("Ce lien expire dans 24 heures. Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.") + "\n"
                )
                try:
                    sent = send_mail(
                        subject, body, None, [new_email], fail_silently=False
                    )
                except Exception:
                    logger.exception("Envoi du mail de vérification impossible")  # i18n-exempt: ligne de log interne, jamais affichée
                    sent = 0
                if sent:
                    log_audit(
                        request, 'PROFILE_EMAIL_REQUEST', 'User', str(user.id),
                        after={'new_email': new_email},
                    )
                    messages.success(
                        request, _("Un lien de confirmation a été envoyé à la nouvelle adresse."),
                    )
                    return redirect('core:dashboard:profile')
                email_form.add_error(
                    None,
                    _("L'email de vérification n'a pas pu être envoyé. Le changement n'a pas été appliqué."),
                )

        elif action == 'password':
            password_form = PasswordChangeForm(request.POST, user=user)
            if password_form.is_valid():
                avant = user.has_usable_password()
                user.set_password(password_form.cleaned_data['new_password'])
                user.save(update_fields=['password'])
                # Sans ceci, Django invalide la session au changement de
                # hachage et la personne est éjectée de son propre écran.
                update_session_auth_hash(request, user)
                log_audit(
                    request, 'PROFILE_PASSWORD', 'User', str(user.id),
                    before={'mot_de_passe_defini': avant},
                    after={'mot_de_passe_defini': True},
                )
                messages.success(request, _("Mot de passe modifié."))
                return redirect('core:dashboard:profile')

    return render(request, 'dashboard/profile/index.html', {
        'profile_form': profile_form,
        'avatar_form': avatar_form,
        'email_form': email_form,
        'password_form': password_form,
        'account_since': user.date_joined,
        'profile_user': user,
    })


@login_required
@active_account_required
def profile_email_confirm(request, token):
    try:
        data = signing.loads(
            token, salt=EMAIL_TOKEN_SALT, max_age=EMAIL_TOKEN_MAX_AGE
        )
    except signing.SignatureExpired:
        messages.error(request, _("Ce lien de confirmation a expiré."))
        return redirect('core:dashboard:profile')
    except signing.BadSignature:
        messages.error(request, _("Lien de confirmation invalide."))
        return redirect('core:dashboard:profile')

    if data.get('uid') != str(request.user.id):
        messages.error(request, _("Ce lien ne correspond pas à votre compte."))
        return redirect('core:dashboard:profile')

    new_email = (data.get('email') or '').strip().lower()
    if not new_email:
        messages.error(request, _("Lien de confirmation invalide."))
        return redirect('core:dashboard:profile')

    if User.objects.filter(email__iexact=new_email).exclude(
            id=request.user.id).exists():
        messages.error(request, _("Cette adresse est déjà utilisée par un autre compte."))
        return redirect('core:dashboard:profile')

    user = request.user
    old_email = user.email
    user.email = new_email
    user.username = new_email
    user.save(update_fields=['email', 'username'])
    log_audit(
        request, 'PROFILE_EMAIL_CONFIRM', 'User', str(user.id),
        before={'email': old_email}, after={'email': new_email},
    )
    messages.success(request, _("Votre adresse e-mail a été mise à jour."))
    return redirect('core:dashboard:profile')


@login_required
@active_account_required
@require_POST
def notifications_marquer_lues(request):
    """Éteint la pastille de la cloche pour les notifications lues.

    Seules les notifications du compte connecté sont marquées : la cloche d’un
    compte ne peut jamais vider la file d’un autre. Le renvoi se fait sur le
    tableau de bord du rôle, jamais sur une adresse passée par le formulaire.
    """
    lues = Notification.objects.filter(
        user=request.user, is_read=False).update(is_read=True)
    if lues:
        messages.success(request, _("Notification(s) marquée(s) comme lue(s)."))
    return redirect(ROLE_DASHBOARD_ROUTES.get(
        request.user.primary_role, 'core:dashboard:dashboard-router'))


@login_required
@active_account_required
def serve_avatar(request, path):
    """Sert les photos de profil aux utilisateurs connectés.

    ``MEDIA_URL`` n'est volontairement pas exposé (les pièces justificatives
    vivent sous ``media/private/``). Seul le sous-dossier public des avatars
    est servi, et uniquement à un compte actif.
    """
    root = os.path.join(settings.MEDIA_ROOT, 'avatars')
    return serve(request, path, document_root=root)
