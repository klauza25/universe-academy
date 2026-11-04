from django.core.management.base import BaseCommand
from core.models import (
    Role, Permission, RolePermission, RoleKey, PRIVILEGED_ROLES, PERMISSIONS,
)


ROLE_PERMISSIONS = {
    'SUPER_ADMIN': [p[0] for p in PERMISSIONS],
    'ADMIN': [p[0] for p in PERMISSIONS],
    # La direction valide les inscriptions et encaisse : « finance.write » lui
    # laisse les écrans de paiement étudiant ouverts, comme avant la matrice.
    'DIRECTION': [
        'users.read', 'students.read', 'formations.read',
        'attendance.read', 'finance.read', 'finance.write',
        'scholarship.read',
    ],
    # Le guichet encaisse : inscription du visiteur, dossier étudiant, paiement.
    'ASSISTANT_ADMIN': [
        'students.read', 'students.write',
        'formations.read', 'attendance.read',
        'finance.read', 'finance.write',
        'access_events.read', 'access_events.write',
    ],
    'SECRETAIRE': [
        'students.read', 'students.write',
        'formations.read', 'attendance.read',
        'finance.read', 'finance.write',
    ],
    'RESP_PEDA': [
        'formations.read', 'formations.write',
        'attendance.read', 'attendance.write',
        'students.read', 'certificates.issue',
        'finance.read', 'finance.write',
    ],
    'FORMATEUR': [
        'attendance.read', 'attendance.write',
        'students.read',
    ],
    'ETUDIANT': [],
}


class Command(BaseCommand):
    help = 'Initialise les rôles et permissions'

    def handle(self, *args, **options):
        for key, desc in PERMISSIONS:
            Permission.objects.get_or_create(key=key, defaults={'description': desc})
        self.stdout.write(f"[OK] {len(PERMISSIONS)} permissions creees/verifiees")

        for role_key in RoleKey:
            role, created = Role.objects.get_or_create(
                key=role_key.value,
                defaults={
                    'label': role_key.label,
                    'is_privileged': role_key.value in PRIVILEGED_ROLES,
                }
            )
            perm_keys = ROLE_PERMISSIONS.get(role_key.value, [])
            for pkey in perm_keys:
                perm = Permission.objects.get(key=pkey)
                RolePermission.objects.get_or_create(role=role, permission=perm)

            status = "cree" if created else "existant"
            self.stdout.write(f"  {role.label}: {status} ({len(perm_keys)} permissions)")

        self.stdout.write(self.style.SUCCESS("[OK] Seed termine"))
