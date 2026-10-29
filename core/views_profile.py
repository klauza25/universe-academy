"""Profil utilisateur : informations, photo, changement d'email vérifié."""
import logging
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.static import serve

from .decorators import active_account_required
from .forms import AvatarForm, EmailChangeForm, ProfileForm
from .models import AccountStatus, User
from .utils import log_audit

logger = logging.getLogger(__name__)

EMAIL_TOKEN_SALT = 'univers-academy.email-change'
EMAIL_TOKEN_MAX_AGE = 60 * 60 * 24  # 24 h


@login_required
@active_account_required
def profile_view(request):
    user = request.user
    profile_form = ProfileForm(instance=user)
    avatar_form = AvatarForm()
    email_form = EmailChangeForm(user=user)

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
                messages.success(request, "Votre profil a été mis à jour.")
                return redirect('core:dashboard:profile')

        elif action == 'avatar':
            avatar_form = AvatarForm(request.POST, request.FILES)
            if avatar_form.is_valid():
                user.avatar = avatar_form.cleaned_data['avatar']
                user.save(update_fields=['avatar'])
                log_audit(request, 'PROFILE_AVATAR', 'User', str(user.id))
                messages.success(request, "Photo de profil enregistrée.")
                return redirect('core:dashboard:profile')

        elif action == 'avatar_delete':
            if user.avatar:
                user.avatar.delete(save=False)
                user.avatar = None
                user.save(update_fields=['avatar'])
                log_audit(request, 'PROFILE_AVATAR_DELETE', 'User', str(user.id))
                messages.success(request, "Photo supprimée, avatar par défaut rétabli.")
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
                subject = "Confirmation de votre nouvelle adresse — Univers Academy"
                body = (
                    "Bonjour,\n\n"
                    "Vous avez demandé à utiliser cette adresse pour votre compte "
                    "Univers Academy.\n"
                    f"Confirmez le changement en ouvrant ce lien :\n{confirm_url}\n\n"
                    "Ce lien expire dans 24 heures. Si vous n'êtes pas à l'origine "
                    "de cette demande, ignorez ce message.\n"
                )
                try:
                    sent = send_mail(
                        subject, body, None, [new_email], fail_silently=False
                    )
                except Exception:
                    logger.exception("Envoi du mail de vérification impossible")
                    sent = 0
                if sent:
                    log_audit(
                        request, 'PROFILE_EMAIL_REQUEST', 'User', str(user.id),
                        after={'new_email': new_email},
                    )
                    messages.success(
                        request,
                        "Un lien de confirmation a été envoyé à la nouvelle adresse.",
                    )
                    return redirect('core:dashboard:profile')
                email_form.add_error(
                    None,
                    "L'email de vérification n'a pas pu être envoyé. "
                    "Le changement n'a pas été appliqué.",
                )

    return render(request, 'dashboard/profile/index.html', {
        'profile_form': profile_form,
        'avatar_form': avatar_form,
        'email_form': email_form,
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
        messages.error(request, "Ce lien de confirmation a expiré.")
        return redirect('core:dashboard:profile')
    except signing.BadSignature:
        messages.error(request, "Lien de confirmation invalide.")
        return redirect('core:dashboard:profile')

    if data.get('uid') != str(request.user.id):
        messages.error(request, "Ce lien ne correspond pas à votre compte.")
        return redirect('core:dashboard:profile')

    new_email = (data.get('email') or '').strip().lower()
    if not new_email:
        messages.error(request, "Lien de confirmation invalide.")
        return redirect('core:dashboard:profile')

    if User.objects.filter(email__iexact=new_email).exclude(
            id=request.user.id).exists():
        messages.error(request, "Cette adresse est déjà utilisée par un autre compte.")
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
    messages.success(request, "Votre adresse e-mail a été mise à jour.")
    return redirect('core:dashboard:profile')


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
