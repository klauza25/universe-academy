import os
from django.core.management.base import BaseCommand, CommandError
from core.models import User, Role, UserRole, AccountStatus


class Command(BaseCommand):
    help = 'Crée le premier Super Administrateur'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True)
        parser.add_argument('--password', required=True)
        parser.add_argument('--first-name', default='Super')
        parser.add_argument('--last-name', default='Admin')
        parser.add_argument('--secret', required=True,
                            help='Secret de setup (SUPERADMIN_SETUP_SECRET)')

    def handle(self, *args, **options):
        expected_secret = os.getenv('SUPERADMIN_SETUP_SECRET', '')
        if not expected_secret or options['secret'] != expected_secret:
            raise CommandError("Secret de setup invalide.")

        if User.objects.filter(email=options['email']).exists():
            raise CommandError("Un utilisateur avec cet email existe déjà.")

        user = User.objects.create_user(
            email=options['email'],
            password=options['password'],
            first_name=options['first_name'],
            last_name=options['last_name'],
            account_status=AccountStatus.ACTIVE,
            is_staff=True,
            is_superuser=True,
        )
        user.generate_internal_code('SUPER_ADMIN')
        user.save()

        role = Role.objects.get(key='SUPER_ADMIN')
        UserRole.objects.create(user=user, role=role)

        self.stdout.write(self.style.SUCCESS(
            f"[OK] Super Admin créé : {user.email} (code: {user.internal_code})"
        ))
