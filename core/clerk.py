"""Clerk authentication helpers.

Clerk verifies the identity in the browser (Google OAuth or email/password)
and hands us a short-lived session JWT. This module verifies that token with
the Clerk Backend API, then maps the Clerk user onto the local ``User`` model.

Nothing here trusts data coming from the browser: the token signature,
issuer, expiry and authorized party (``azp``) are all checked by the SDK.
"""
import logging

from django.conf import settings
from django.db import transaction

from clerk_backend_api import Clerk
from clerk_backend_api.security import VerifyTokenOptions, verify_token

from .models import AccessRequest, AccountStatus, User

logger = logging.getLogger(__name__)


class ClerkError(Exception):
    """Raised when a verified Clerk session cannot be linked to a local user."""


def get_clerk_client():
    return Clerk(bearer_auth=settings.CLERK_SECRET_KEY)


def verify_clerk_token(token):
    """Verify a Clerk session token and return its claims."""
    return verify_token(
        token,
        VerifyTokenOptions(
            secret_key=settings.CLERK_SECRET_KEY,
            authorized_parties=settings.CLERK_AUTHORIZED_PARTIES,
        ),
    )


def _is_verified_email(email):
    verification = getattr(email, 'verification', None)
    status = getattr(verification, 'status', None)
    return str(getattr(status, 'value', status) or '').lower() == 'verified'


def _primary_email(clerk_user):
    """Return ``(email, verified)`` for the best Clerk email address.

    The primary address is preferred when it is verified; otherwise the first
    verified address wins, and only as a last resort an unverified one is
    returned (with ``verified=False``) so callers can refuse to link it.
    """
    emails = [
        email for email in (getattr(clerk_user, 'email_addresses', None) or [])
        if (getattr(email, 'email_address', '') or '').strip()
    ]
    primary_id = getattr(clerk_user, 'primary_email_address_id', None)

    primary = next(
        (
            email for email in emails
            if primary_id and getattr(email, 'id', None) == primary_id
        ),
        None,
    )

    if primary is not None and _is_verified_email(primary):
        return primary.email_address.strip().lower(), True

    for email in emails:
        if _is_verified_email(email):
            return email.email_address.strip().lower(), True

    if primary is not None:
        return primary.email_address.strip().lower(), False

    if emails:
        return emails[0].email_address.strip().lower(), False

    return '', False


def _split_name(clerk_user):
    first = (getattr(clerk_user, 'first_name', '') or '').strip()
    last = (getattr(clerk_user, 'last_name', '') or '').strip()

    if not first and not last:
        full = (
            getattr(clerk_user, 'full_name', '')
            or getattr(clerk_user, 'username', '')
            or ''
        ).strip()
        parts = full.split(None, 1)
        first = parts[0] if parts else ''
        last = parts[1] if len(parts) > 1 else ''

    return first, last


def sync_clerk_user(payload):
    """Return ``(user, created)`` for a verified Clerk session payload.

    Linking rules:
    1. an existing local account already linked to this Clerk id wins;
    2. otherwise the account is matched by email (case-insensitive) and linked,
       but only when Clerk reports that email as verified (unknown status is
       tolerated when the Backend API is unreachable);
    3. otherwise a new account is created in ``PENDING_APPROVAL`` with an
       ``AccessRequest`` so the existing approval workflow still applies.
    """
    clerk_user_id = (payload or {}).get('sub')
    if not clerk_user_id:
        raise ClerkError("Jeton Clerk invalide : identifiant utilisateur absent.")

    email = (payload.get('email') or '').strip().lower()
    # ``None`` means "unknown" (Clerk API unreachable); ``False`` means Clerk
    # explicitly reported an unverified address.
    email_verified = None
    first_name = last_name = ''

    try:
        clerk_user = get_clerk_client().users.get(user_id=clerk_user_id)
        api_email, email_verified = _primary_email(clerk_user)
        email = api_email or email
        first_name, last_name = _split_name(clerk_user)
    except Exception as exc:  # network/API failure
        logger.warning(
            "Clerk API unavailable while fetching user %s: %s",
            clerk_user_id, exc,
        )
        if not email:
            raise ClerkError(
                "Impossible de recuperer votre profil Clerk. Reessayez."
            ) from exc

    if not email:
        raise ClerkError(
            "Votre compte Clerk ne possede pas d'adresse email exploitable."
        )

    with transaction.atomic():
        user = (
            User.objects.select_for_update()
            .filter(clerk_user_id=clerk_user_id)
            .first()
        )
        if user is None:
            user = (
                User.objects.select_for_update()
                .filter(email__iexact=email)
                .first()
            )
            if user is not None and email_verified is False:
                # Never attach an unverified Clerk address to an existing
                # account: that would allow account takeover by email.
                raise ClerkError(
                    "Votre adresse email n'est pas verifiee dans Clerk. "
                    "Verifiez-la avant de vous connecter."
                )

        if user is not None:
            changed = []
            if not user.clerk_user_id:
                user.clerk_user_id = clerk_user_id
                changed.append('clerk_user_id')
            if first_name and not user.first_name:
                user.first_name = first_name
                changed.append('first_name')
            if last_name and not user.last_name:
                user.last_name = last_name
                changed.append('last_name')
            if changed:
                user.save(update_fields=changed)
            return user, False

        user = User(
            email=email,
            username=email,
            first_name=first_name,
            last_name=last_name,
            account_status=AccountStatus.PENDING_APPROVAL,
            clerk_user_id=clerk_user_id,
        )
        user.set_unusable_password()
        user.save()
        AccessRequest.objects.create(user=user)
        return user, True
