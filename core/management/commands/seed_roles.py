from django.core.management.base import BaseCommand
from core.models import Role, Permission, RolePermission, RoleKey, PRIVILEGED_ROLES


PERMISSIONS = [
    ('users.read', 'Lire les utilisateurs'),
    ('users.create', 'Créer des utilisateurs'),
    ('users.edit', 'Modifier des utilisateurs'),
    ('roles.manage', 'Gérer les rôles'),
    ('access_requests.review', 'Examiner les demandes d\'accès'),
    ('students.read', 'Lire les dossiers étudiants'),
    ('students.write', 'Modifier les dossiers étudiants'),
    ('formations.read', 'Lire les formations'),
    ('formations.write', 'Modifier les formations'),
    ('attendance.read', 'Lire les présences'),
    ('attendance.write', 'Saisir les présences'),
    ('finance.read', 'Lire les données financières'),
    ('finance.write', 'Saisir des paiements'),
    ('scholarship.read', 'Lire les candidatures bourse'),
    ('scholarship.review', 'Examiner les candidatures bourse'),
    ('access_events.read', 'Lire le journal des entrées/sorties'),
    ('access_events.write', 'Enregistrer les entrées/sorties'),
    ('audit.read', 'Lire le journal d\'audit'),
    ('certificates.issue', 'Délivrer des certificats'),
]

ROLE_PERMISSIONS = {
    'SUPER_ADMIN': [p[0] for p in PERMISSIONS],
    'ADMIN': [
        'users.read', 'users.create', 'users.edit',
        'students.read', 'students.write',
        'formations.read', 'formations.write',
        'attendance.read', 'finance.read',
        'scholarship.read', 'scholarship.review',
        'access_events.read',
    ],
    'DIRECTION': [
        'users.read', 'students.read', 'formations.read',
        'attendance.read', 'finance.read',
        'scholarship.read',
    ],
    'SECRETAIRE': [
        'students.read', 'students.write',
        'formations.read', 'attendance.read',
    ],
    'COMPTABLE': [
        'finance.read', 'finance.write', 'students.read',
    ],
    'RESP_PEDA': [
        'formations.read', 'formations.write',
        'attendance.read', 'attendance.write',
        'students.read', 'certificates.issue',
    ],
    'FORMATEUR': [
        'attendance.read', 'attendance.write',
        'students.read',
    ],
    'ETUDIANT': [],
    'ACCUEIL': [
        'access_events.read', 'access_events.write',
    ],
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
