"""Base commune aux tests métier d'Univers Academy.

Les tests s'exécutent sur une base de test créée par Django : les données de
production (``db.sqlite3``) ne sont jamais touchées. Les migrations sont
appliquées, y compris la migration de données ``0005`` qui crée les motifs de
visite, les catégories comptables et les deux caisses par défaut.
"""
import shutil
import tempfile
from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from core.models import (
    AccountStatus, AuditLog, CashAccount, Course, CourseSession, Enrollment,
    Lesson, Module, Role, RoleKey, TransactionCategory, User, UserRole,
    VisitReason,
)

TEST_PASSWORD = 'TestPass123!'


@override_settings(
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
)
class BusinessTestBase(TestCase):
    """Jeu de données minimal partagé par les tests métier."""

    @classmethod
    def setUpClass(cls):
        cls._media_dir = tempfile.mkdtemp(prefix='ua-tests-media-')
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_dir)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media_dir, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()

        # Rôles : le projet ne les crée pas par migration (commande seed_roles).
        cls.roles = {}
        for member in RoleKey:
            role, _ = Role.objects.get_or_create(
                key=member.value,
                defaults={
                    'label': member.label,
                    'is_privileged': member.value in (
                        'SUPER_ADMIN', 'ADMIN', 'DIRECTION'
                    ),
                },
            )
            cls.roles[member.value] = role

        cls.super_admin = cls.make_user(RoleKey.SUPER_ADMIN, 'superadmin@test.local')
        cls.admin = cls.make_user(RoleKey.ADMIN, 'admin@test.local')
        cls.direction = cls.make_user(RoleKey.DIRECTION, 'direction@test.local')
        cls.secretaire = cls.make_user(RoleKey.SECRETAIRE, 'secretaire@test.local')
        cls.comptable = cls.make_user(RoleKey.COMPTABLE, 'comptable@test.local')
        cls.peda = cls.make_user(RoleKey.RESPONSABLE_PEDAGOGIQUE, 'peda@test.local')
        cls.formateur = cls.make_user(RoleKey.FORMATEUR, 'formateur@test.local')
        cls.etudiant = cls.make_user(RoleKey.ETUDIANT, 'etudiant@test.local')
        cls.accueil = cls.make_user(RoleKey.ACCUEIL, 'accueil@test.local')

        cls.etudiant.generate_internal_code(RoleKey.ETUDIANT)
        cls.etudiant.save(update_fields=['internal_code'])

        cls.course = Course.objects.create(
            title='Développement Web',
            domain='Informatique',
            description='Cours de test',
            duration_months=3,
            fee_amount=100000,
            certificate_eligible=True,
        )
        cls.session = CourseSession.objects.create(
            course=cls.course,
            starts_at=cls.today - timedelta(days=30),
            ends_at=cls.today + timedelta(days=60),
            schedule='Lun-Ven 08h-10h',
            capacity=30,
            status=CourseSession.Status.ACTIVE,
        )
        cls.session.formateurs.add(cls.formateur)

        cls.module = Module.objects.create(
            course=cls.course, title='Module HTML', order=1, planned_hours=20,
        )
        cls.lesson = Lesson.objects.create(
            module=cls.module, title='Les bases du HTML', order=1,
            planned_hours=5,
        )

        cls.enrollment = Enrollment.objects.create(
            student=cls.etudiant,
            session=cls.session,
            status=Enrollment.Status.ACTIVE,
            start_date=cls.today,
            tariff_amount=100000,
            discount_amount=10000,
            net_amount=90000,
            registered_by=cls.secretaire,
        )

        cls.cash = CashAccount.objects.get_or_create(
            name='Caisse principale',
            defaults={'kind': CashAccount.Kind.CASH, 'opening_balance': 0},
        )[0]
        cls.mobile = CashAccount.objects.get_or_create(
            name='Mobile Money',
            defaults={'kind': CashAccount.Kind.MOBILE_MONEY,
                      'opening_balance': 0},
        )[0]
        for account in (cls.cash, cls.mobile):
            account.opening_balance = 0
            account.save(update_fields=['opening_balance'])

        cls.income_category = TransactionCategory.objects.get(
            name='Paiements des étudiants',
            direction=TransactionCategory.Direction.IN,
        )
        cls.expense_category = TransactionCategory.objects.get(
            name='Autres dépenses',
            direction=TransactionCategory.Direction.OUT,
        )
        cls.transfer_category, _ = TransactionCategory.objects.get_or_create(
            name='Transfert interne',
            direction=TransactionCategory.Direction.TRANSFER,
        )
        cls.visit_reason = VisitReason.objects.create(
            label='Motif de test', order=99,
        )

    # ------------------------------------------------------------------
    # Fabriques
    # ------------------------------------------------------------------

    @classmethod
    def make_user(cls, role_key, email, *, password=TEST_PASSWORD,
                  status=AccountStatus.ACTIVE):
        key = getattr(role_key, 'value', role_key)
        user = User.objects.create_user(
            email=email,
            password=password,
            first_name='Utilisateur',
            last_name=key.title(),
            account_status=status,
        )
        UserRole.objects.create(user=user, role=cls.roles[key])
        return user

    @staticmethod
    def client_for(user):
        client = Client()
        client.force_login(user)
        return client

    @staticmethod
    def local_datetime(minutes=0):
        value = timezone.localtime() + timedelta(minutes=minutes)
        return value.strftime('%Y-%m-%dT%H:%M')

    @staticmethod
    def local_date(days=0):
        return (timezone.localdate() + timedelta(days=days)).strftime('%Y-%m-%d')

    # ------------------------------------------------------------------
    # Assertions
    # ------------------------------------------------------------------

    def assert_audited(self, action, entity_id=None):
        qs = AuditLog.objects.filter(action=action)
        if entity_id is not None:
            qs = qs.filter(entity_id=str(entity_id))
        self.assertTrue(
            qs.exists(),
            f"Aucune entrée d'audit « {action} » pour {entity_id}",
        )
        return qs.order_by('-created_at').first()
