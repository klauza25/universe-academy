"""Rapport en lecture seule des privilèges à vérifier.

Ne modifie aucune donnée : l'opérateur examine les comptes signalés puis,
après vérification d'identité, retire un rôle depuis la fiche utilisateur
(réservée au super administrateur) ou via le shell Django.
"""
from django.core.management.base import BaseCommand

from core.models import (
    AccessRequest, ELEVATED_ROLES, REQUESTABLE_ROLES, AccountStatus, RoleKey, User,
)


class Command(BaseCommand):
    help = "Signale les comptes dont les rôles méritent une vérification manuelle."

    def add_arguments(self, parser):
        parser.add_argument(
            '--fail-on-suspicious', action='store_true',
            help="Code de sortie 1 si au moins un compte est signalé.",
        )

    def handle(self, *args, **options):
        findings = []

        for user in User.objects.prefetch_related('roles').order_by('email'):
            roles = set(user.roles.values_list('key', flat=True))
            reasons = []

            if RoleKey.SUPER_ADMIN in roles and not user.is_superuser:
                reasons.append(
                    "SUPER_ADMIN sans is_superuser (attribution manuelle ?)"
                )
            if user.is_superuser and RoleKey.SUPER_ADMIN not in roles:
                reasons.append("is_superuser sans rôle SUPER_ADMIN")
            if user.account_status != AccountStatus.ACTIVE and (
                roles & set(ELEVATED_ROLES)
            ):
                reasons.append("Compte non actif avec un rôle administratif")
            if user.needs_access_request and roles:
                reasons.append(
                    "Compte en attente de rôle demandé mais déjà porteur d'un rôle"
                )
            if user.clerk_user_id and RoleKey.SUPER_ADMIN in roles:
                reasons.append(
                    "SUPER_ADMIN lié à Clerk : vérifier que l'attribution était "
                    "volontaire (jamais automatique)"
                )

            if reasons:
                findings.append((user, sorted(roles), reasons))

        for access_request in AccessRequest.objects.filter(
            status=AccessRequest.Status.APPROVED
        ).select_related('user', 'reviewed_by'):
            assigned = access_request.assigned_role
            if assigned and assigned not in REQUESTABLE_ROLES:
                findings.append((
                    access_request.user,
                    [assigned],
                    [
                        f"Demande {access_request.id} approuvée avec le rôle "
                        f"non demandable {assigned}"
                    ],
                ))

        super_admins = User.objects.filter(
            roles__key=RoleKey.SUPER_ADMIN,
            account_status=AccountStatus.ACTIVE,
        ).distinct().count()

        self.stdout.write(
            f"Super administrateurs actifs : {super_admins}"
        )
        if super_admins == 0:
            self.stdout.write(self.style.WARNING(
                "Aucun SUPER_ADMIN actif : utilisez create_superadmin avec le "
                "secret de déploiement."
            ))

        if not findings:
            self.stdout.write(self.style.SUCCESS(
                "Aucun compte ne nécessite de vérification."
            ))
            return

        self.stdout.write(self.style.WARNING(
            f"{len(findings)} compte(s) à vérifier (aucune modification effectuée) :"
        ))
        for user, roles, reasons in findings:
            self.stdout.write(
                f"  - {user.email} | statut={user.account_status} | "
                f"rôles={roles or 'aucun'} | clerk={'oui' if user.clerk_user_id else 'non'}"
            )
            for reason in reasons:
                self.stdout.write(f"      * {reason}")

        if options['fail_on_suspicious']:
            raise SystemExit(1)
