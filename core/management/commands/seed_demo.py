import os
import secrets
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import (
    User, Role, UserRole, AccountStatus, RoleKey, Destination, Course,
    CourseSession, Enrollment, Payment, Attendance,
    ScholarshipApplication, AccessEvent,
)


DEMO_USERS = [
    ('formateur@univers.academy', 'Jean', 'Mbemba', RoleKey.FORMATEUR),
    ('etudiant@univers.academy', 'Alice', 'Mabiala', RoleKey.ETUDIANT),
    ('comptable@univers.academy', 'Paul', 'Ondongo', RoleKey.COMPTABLE),
    ('accueil@univers.academy', 'Sarah', 'Bikindou', RoleKey.ACCUEIL),
    ('peda@univers.academy', 'Luc', 'Mavoungou', RoleKey.RESPONSABLE_PEDAGOGIQUE),
]

DESTINATIONS = ['France', 'Canada', 'Belgique', 'Maroc', 'Chine']

COURSES = [
    ('Anglais B2', 'Langues', 3, 75000, True),
    ('Francais A2', 'Langues', 2, 50000, True),
    ('Espagnol A1', 'Langues', 3, 60000, True),
    ('Bureautique et Internet', 'Informatique', 1, 35000, False),
]


class Command(BaseCommand):
    help = 'Cree des donnees de demonstration (utilisateurs, formations, sessions, inscription, paiement, bourse)'

    @transaction.atomic
    def handle(self, *args, **options):
        for key in [RoleKey.FORMATEUR, RoleKey.ETUDIANT, RoleKey.COMPTABLE,
                    RoleKey.ACCUEIL, RoleKey.RESPONSABLE_PEDAGOGIQUE]:
            Role.objects.get_or_create(
                key=key.value,
                defaults={'label': key.label, 'is_privileged': False},
            )

        users = {}
        generated_passwords = {}
        # Aucun mot de passe n'est stocké dans le code. Par défaut, un mot de
        # passe aléatoire est généré et affiché une seule fois ; DEMO_PASSWORD
        # permet de le fixer pour un poste de démonstration.
        fixed_password = os.environ.get('DEMO_PASSWORD')
        for email, first, last, role_key in DEMO_USERS:
            password = fixed_password or secrets.token_urlsafe(12)
            generated_passwords[email] = password
            user = User.objects.filter(email=email).first()
            if not user:
                user = User.objects.create_user(
                    email=email, password=password,
                    first_name=first, last_name=last,
                )
                self.stdout.write(f'[OK] Utilisateur cree: {email}')
            else:
                user.set_password(password)
                self.stdout.write(f'[OK] Utilisateur existant: {email}')
            user.is_active = True
            user.account_status = AccountStatus.ACTIVE
            user.generate_internal_code(role_key.value)
            user.save()
            role = Role.objects.get(key=role_key.value)
            UserRole.objects.get_or_create(user=user, role=role)
            users[role_key.value] = user

        destination_objs = {}
        for name in DESTINATIONS:
            obj, _ = Destination.objects.get_or_create(name=name)
            destination_objs[name] = obj
        self.stdout.write(f'[OK] {len(destination_objs)} destinations')

        course_objs = {}
        for title, domain, months, fee, eligible in COURSES:
            course, _ = Course.objects.get_or_create(
                title=title,
                defaults={
                    'domain': domain,
                    'duration_months': months,
                    'fee_amount': fee,
                    'certificate_eligible': eligible,
                },
            )
            course_objs[title] = course
        self.stdout.write(f'[OK] {len(course_objs)} formations')

        formateur = users[RoleKey.FORMATEUR.value]
        session, _ = CourseSession.objects.get_or_create(
            course=course_objs['Anglais B2'],
            starts_at=date.today() - timedelta(days=14),
            defaults={
                'ends_at': date.today() + timedelta(days=76),
                'schedule': 'Lun-Ven 13h-15h',
                'capacity': 20,
                'status': CourseSession.Status.ACTIVE,
            },
        )
        session.formateurs.add(formateur)

        session2, _ = CourseSession.objects.get_or_create(
            course=course_objs['Bureautique et Internet'],
            starts_at=date.today() + timedelta(days=10),
            defaults={
                'ends_at': date.today() + timedelta(days=40),
                'schedule': 'Sam 09h-12h',
                'capacity': 15,
                'status': CourseSession.Status.PLANNED,
            },
        )
        session2.formateurs.add(formateur)
        self.stdout.write('[OK] 2 sessions de formation')

        student = users[RoleKey.ETUDIANT.value]
        enrollment, _ = Enrollment.objects.get_or_create(
            student=student, session=session,
            defaults={'status': Enrollment.Status.ACTIVE},
        )

        Payment.objects.get_or_create(
            enrollment=enrollment,
            amount=75000,
            defaults={
                'method': Payment.Method.MOBILE_MONEY,
                'status': Payment.Status.COMPLETED,
                'recorded_by': users[RoleKey.COMPTABLE.value],
            },
        )
        for i, status in enumerate(
            [Attendance.Status.PRESENT, Attendance.Status.PRESENT,
             Attendance.Status.LATE, Attendance.Status.ABSENT]
        ):
            Attendance.objects.get_or_create(
                enrollment=enrollment,
                date=date.today() - timedelta(days=7 * (i + 1)),
                defaults={'status': status, 'recorded_by': formateur},
            )
        self.stdout.write('[OK] 1 inscription, 1 paiement, 4 presences')

        ScholarshipApplication.objects.get_or_create(
            email='candidat@example.com',
            defaults={
                'last_name': 'Kimbembé',
                'first_name': 'Grace',
                'phone': '+242 06 555 44 33',
                'destination': destination_objs['France'],
                'program': 'Master',
                'study_domain': 'Informatique',
            },
        )
        self.stdout.write('[OK] 1 candidature bourse')

        AccessEvent.objects.get_or_create(
            person=student,
            event_type=AccessEvent.EventType.ENTRY,
            defaults={'recorded_by': users[RoleKey.ACCUEIL.value],
                      'reason': 'Cours du jour'},
        )
        self.stdout.write('[OK] 1 evenement d\'acces')

        self.stdout.write(self.style.SUCCESS('[OK] Donnees de demonstration pretes'))
        if fixed_password:
            self.stdout.write('Mot de passe commun : celui fourni via DEMO_PASSWORD.')
        else:
            self.stdout.write('Mots de passe generes (affiches une seule fois, non stockes) :')
            for email, password in generated_passwords.items():
                self.stdout.write(f'  {email} : {password}')
