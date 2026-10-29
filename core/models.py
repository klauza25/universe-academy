import uuid
import os
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import (
    FileExtensionValidator, MinValueValidator, RegexValidator
)
from django.utils import timezone


class AccountStatus(models.TextChoices):
    PENDING_APPROVAL = 'PENDING_APPROVAL', 'En attente d\'approbation'
    ACTIVE = 'ACTIVE', 'Actif'
    SUSPENDED = 'SUSPENDED', 'Suspendu'
    DISABLED = 'DISABLED', 'Désactivé'
    REJECTED = 'REJECTED', 'Refusé'


class RoleKey(models.TextChoices):
    SUPER_ADMIN = 'SUPER_ADMIN', 'Super Administrateur'
    ADMIN = 'ADMIN', 'Administrateur'
    DIRECTION = 'DIRECTION', 'Direction'
    SECRETAIRE = 'SECRETAIRE', 'Secrétaire'
    COMPTABLE = 'COMPTABLE', 'Comptable'
    RESPONSABLE_PEDAGOGIQUE = 'RESP_PEDA', 'Responsable pédagogique'
    FORMATEUR = 'FORMATEUR', 'Formateur'
    ETUDIANT = 'ETUDIANT', 'Étudiant'
    ACCUEIL = 'ACCUEIL', 'Accueil / Contrôle'


ROLE_DASHBOARD_ROUTES = {
    'SUPER_ADMIN': 'core:dashboard:super-admin-dashboard',
    'ADMIN': 'core:dashboard:admin-dashboard',
    'DIRECTION': 'core:dashboard:direction-dashboard',
    'SECRETAIRE': 'core:dashboard:secretaire-dashboard',
    'COMPTABLE': 'core:dashboard:comptabilite-dashboard',
    'RESP_PEDA': 'core:dashboard:resp-peda-dashboard',
    'FORMATEUR': 'core:dashboard:formateur-dashboard',
    'ETUDIANT': 'core:dashboard:etudiant-dashboard',
    'ACCUEIL': 'core:dashboard:accueil-dashboard',
}

PRIVILEGED_ROLES = {'SUPER_ADMIN', 'ADMIN', 'DIRECTION'}

# Rôles disposant d'un accès transversal en lecture à l'ensemble des modules.
# Les opérations les plus sensibles (création de comptes, attribution de rôles,
# validation des demandes d'accès) restent réservées au SUPER_ADMIN.
ELEVATED_ROLES = ('SUPER_ADMIN', 'ADMIN')

# Rôles qu'un demandeur peut solliciter et qu'un SUPER_ADMIN peut attribuer
# lors de l'approbation d'une demande d'accès. Les rôles d'administration
# (SUPER_ADMIN, ADMIN) et la direction restent attribués depuis l'écran
# « Utilisateurs » par un SUPER_ADMIN, jamais par un formulaire public.
REQUESTABLE_ROLES = (
    'ETUDIANT', 'FORMATEUR', 'SECRETAIRE', 'COMPTABLE', 'RESP_PEDA', 'ACCUEIL',
)
REQUESTABLE_ROLE_CHOICES = [
    (key, RoleKey(key).label) for key in REQUESTABLE_ROLES
]

INTERNAL_CODE_PREFIXES = {
    'SUPER_ADMIN': 'UA-ADM',
    'ADMIN': 'UA-ADM',
    'DIRECTION': 'UA-DIR',
    'SECRETAIRE': 'UA-SEC',
    'COMPTABLE': 'UA-CPT',
    'RESP_PEDA': 'UA-RPD',
    'FORMATEUR': 'UA-FRM',
    'ETUDIANT': 'UA-ETU',
    'ACCUEIL': 'UA-ACC',
}


def avatar_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower()
    return f"avatars/{instance.id}/{uuid.uuid4().hex}.{ext}"


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("L'email est obligatoire")
        email = self.normalize_email(email)
        extra_fields.setdefault('username', email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('account_status', AccountStatus.ACTIVE)
        user = self.create_user(email, password, **extra_fields)
        role, _ = Role.objects.using(self._db).get_or_create(
            key=RoleKey.SUPER_ADMIN,
            defaults={
                'label': RoleKey.SUPER_ADMIN.label,
                'is_privileged': True,
            },
        )
        UserRole.objects.using(self._db).get_or_create(user=user, role=role)
        return user


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    internal_code = models.CharField(
        max_length=20, unique=True, null=True, blank=True,
        db_index=True,
        help_text="Code interne ex: UA-ETU-0001"
    )
    account_status = models.CharField(
        max_length=20,
        choices=AccountStatus.choices,
        default=AccountStatus.PENDING_APPROVAL,
        db_index=True,
    )
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    birth_date = models.DateField(null=True, blank=True)
    disabled_at = models.DateTimeField(null=True, blank=True)
    clerk_user_id = models.CharField(
        max_length=64, unique=True, null=True, blank=True, db_index=True,
        help_text="Identifiant utilisateur Clerk (user_...) lié à ce compte"
    )
    display_name = models.CharField(
        max_length=150, blank=True,
        help_text="Nom affiché dans l'interface (facultatif)"
    )
    avatar = models.ImageField(
        upload_to=avatar_path, null=True, blank=True,
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])],
        help_text="Photo de profil (JPG, PNG ou WebP, 2 Mo max)"
    )

    roles = models.ManyToManyField(
        'Role', through='UserRole', through_fields=('user', 'role'),
        related_name='users', blank=True
    )

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        db_table = 'users'
        ordering = ['-date_joined']

    def __str__(self):
        return f"{self.get_full_name()} ({self.internal_code or self.email})"

    @property
    def is_active_account(self):
        return self.account_status == AccountStatus.ACTIVE

    @property
    def display_label(self):
        """Nom à afficher dans l'interface."""
        return (self.display_name or self.get_full_name() or self.email).strip()

    @property
    def initials(self):
        first = (self.first_name or '').strip()
        last = (self.last_name or '').strip()
        if first or last:
            return f"{first[:1]}{last[:1]}".upper() or '?'
        return (self.email or '?')[:2].upper()

    @property
    def primary_role(self):
        role_priority = list(RoleKey.values)
        user_roles = self.roles.all()
        for rk in role_priority:
            if user_roles.filter(key=rk).exists():
                return rk
        return None

    @property
    def dashboard_route(self):
        role = self.primary_role
        return ROLE_DASHBOARD_ROUTES.get(role, 'core:home')

    def has_role(self, role_key):
        return self.roles.filter(key=role_key).exists()

    def has_any_role(self, *role_keys):
        return self.roles.filter(key__in=role_keys).exists()

    def has_perm_key(self, perm_key):
        return Permission.objects.filter(
            rolepermission__role__userrole__user=self,
            key=perm_key
        ).exists()

    @property
    def is_elevated(self):
        """Vrai pour les rôles à accès transversal (super admin, admin)."""
        return self.roles.filter(key__in=ELEVATED_ROLES).exists()

    @property
    def pending_access_request(self):
        """Dernière demande d'accès encore en attente, s'il y en a une."""
        return self.access_requests.filter(
            status=AccessRequest.Status.PENDING
        ).order_by('-created_at').first()

    @property
    def needs_access_request(self):
        """Compte en attente qui doit encore choisir son rôle demandé."""
        if self.account_status != AccountStatus.PENDING_APPROVAL:
            return False
        pending = self.pending_access_request
        return pending is None or not pending.requested_role

    def generate_internal_code(self, role_key=None):
        if self.internal_code:
            return self.internal_code
        prefix = INTERNAL_CODE_PREFIXES.get(role_key, 'UA-USR')
        last = User.objects.filter(
            internal_code__startswith=prefix
        ).order_by('-internal_code').first()
        if last and last.internal_code:
            try:
                num = int(last.internal_code.split('-')[-1]) + 1
            except (ValueError, IndexError):
                num = 1
        else:
            num = 1
        self.internal_code = f"{prefix}-{num:04d}"
        return self.internal_code


class Role(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=20, unique=True, choices=RoleKey.choices)
    label = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    is_privileged = models.BooleanField(default=False)

    class Meta:
        db_table = 'roles'

    def __str__(self):
        return self.label


class Permission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=200)

    class Meta:
        db_table = 'permissions'

    def __str__(self):
        return self.key


class UserRole(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    assigned_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='assigned_roles'
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_roles'
        unique_together = ('user', 'role')


class RolePermission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)

    class Meta:
        db_table = 'role_permissions'
        unique_together = ('role', 'permission')


class AccessRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'En attente'
        APPROVED = 'APPROVED', 'Approuvée'
        REJECTED = 'REJECTED', 'Refusée'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='access_requests')
    requested_role = models.CharField(max_length=20, choices=RoleKey.choices, blank=True)
    assigned_role = models.CharField(
        max_length=20, choices=RoleKey.choices, blank=True,
        help_text="Rôle effectif attribué lors de l'approbation",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_requests'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'access_requests'
        ordering = ['-created_at']


class Course(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    domain = models.CharField(max_length=100, db_index=True)
    description = models.TextField(blank=True)
    duration_months = models.PositiveIntegerField(default=3)
    fee_amount = models.PositiveIntegerField(
        help_text="Montant en FCFA",
        validators=[MinValueValidator(0)]
    )
    currency = models.CharField(max_length=5, default='XAF')
    certificate_eligible = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'courses'
        ordering = ['domain', 'title']

    def __str__(self):
        return f"{self.title} ({self.domain})"


class CourseSession(models.Model):
    class Status(models.TextChoices):
        PLANNED = 'PLANNED', 'Planifiée'
        ACTIVE = 'ACTIVE', 'En cours'
        COMPLETED = 'COMPLETED', 'Terminée'
        CANCELLED = 'CANCELLED', 'Annulée'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='sessions')
    starts_at = models.DateField()
    ends_at = models.DateField()
    schedule = models.CharField(
        max_length=100, blank=True,
        help_text="Ex: Lun-Ven 13h-15h"
    )
    capacity = models.PositiveIntegerField(default=30)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PLANNED
    )
    formateurs = models.ManyToManyField(
        User, related_name='sessions_taught', blank=True,
        limit_choices_to={'roles__key': 'FORMATEUR'}
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'course_sessions'
        ordering = ['-starts_at']

    def __str__(self):
        return f"{self.course.title} — {self.starts_at}"

    @property
    def enrolled_count(self):
        return self.enrollments.filter(
            status__in=['ACTIVE', 'COMPLETED']
        ).count()

    @property
    def is_full(self):
        return self.enrolled_count >= self.capacity


class Enrollment(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'En attente'
        ACTIVE = 'ACTIVE', 'Active'
        COMPLETED = 'COMPLETED', 'Terminée'
        CANCELLED = 'CANCELLED', 'Annulée'
        SUSPENDED = 'SUSPENDED', 'Suspendue'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='enrollments',
        limit_choices_to={'roles__key': 'ETUDIANT'}
    )
    session = models.ForeignKey(
        CourseSession, on_delete=models.CASCADE, related_name='enrollments'
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # --- Dossier administratif et financier (secrétariat) -------------------
    start_date = models.DateField(null=True, blank=True)
    tariff_amount = models.PositiveIntegerField(
        default=0, help_text="Tarif catalogue appliqué (FCFA)"
    )
    discount_amount = models.PositiveIntegerField(
        default=0, help_text="Remise autorisée (FCFA)"
    )
    net_amount = models.PositiveIntegerField(
        default=0, help_text="Montant net dû (FCFA)"
    )
    payment_plan = models.CharField(
        max_length=200, blank=True,
        help_text="Ex: 2 versements — 50 % à l'inscription"
    )
    registered_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='registered_enrollments'
    )
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'enrollments'
        unique_together = ('student', 'session')

    def __str__(self):
        return f"{self.student} → {self.session}"

    @property
    def total_paid(self):
        return self.payments.filter(
            status=Payment.Status.COMPLETED
        ).aggregate(total=models.Sum('amount'))['total'] or 0

    @property
    def balance_due(self):
        return max(self.net_amount - self.total_paid, 0)

    @property
    def payment_state(self):
        if self.net_amount <= 0:
            return 'NON_DEFINI'
        if self.total_paid <= 0:
            return 'IMPAYE'
        if self.total_paid >= self.net_amount:
            return 'SOLDE'
        return 'PARTIEL'


class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = 'PRESENT', 'Présent'
        ABSENT = 'ABSENT', 'Absent'
        LATE = 'LATE', 'En retard'
        EXCUSED = 'EXCUSED', 'Excusé'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name='attendances'
    )
    session_record = models.ForeignKey(
        'SessionRecord', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='attendances'
    )
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices)
    arrival_time = models.TimeField(null=True, blank=True)
    absence_reason = models.CharField(max_length=200, blank=True)
    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='recorded_attendances'
    )
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'attendances'
        unique_together = ('enrollment', 'date')
        ordering = ['-date']


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = 'CASH', 'Espèces'
        MOBILE_MONEY = 'MOBILE_MONEY', 'Mobile Money'
        BANK_TRANSFER = 'BANK_TRANSFER', 'Virement bancaire'
        OTHER = 'OTHER', 'Autre'

    class Status(models.TextChoices):
        COMPLETED = 'COMPLETED', 'Effectué'
        PENDING = 'PENDING', 'En attente'
        CANCELLED = 'CANCELLED', 'Annulé'
        REFUNDED = 'REFUNDED', 'Remboursé'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.PROTECT, related_name='payments'
    )
    amount = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    currency = models.CharField(max_length=5, default='XAF')
    method = models.CharField(max_length=20, choices=Method.choices)
    reference = models.CharField(max_length=50, unique=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.COMPLETED
    )
    paid_at = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='recorded_payments'
    )
    note = models.TextField(blank=True)
    transaction = models.OneToOneField(
        'CashTransaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='student_payment'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'payments'
        ordering = ['-paid_at']

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"PAY-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)


class Expense(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.CharField(max_length=100)
    amount = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    currency = models.CharField(max_length=5, default='XAF')
    occurred_at = models.DateField()
    description = models.TextField()
    receipt = models.FileField(
        upload_to='private/expenses/', blank=True,
        validators=[FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png'])]
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='created_expenses'
    )
    status = models.CharField(max_length=20, default='ACTIVE')
    transaction = models.OneToOneField(
        'CashTransaction', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='expense_record'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'expenses'
        ordering = ['-occurred_at']


class Destination(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = 'destinations'
        ordering = ['name']

    def __str__(self):
        return self.name


class ScholarshipApplication(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = 'SUBMITTED', 'Soumise'
        UNDER_REVIEW = 'UNDER_REVIEW', 'En cours d\'examen'
        DOCUMENTS_REQUESTED = 'DOCS_REQUESTED', 'Documents demandés'
        APPROVED = 'APPROVED', 'Approuvée'
        REJECTED = 'REJECTED', 'Rejetée'
        WITHDRAWN = 'WITHDRAWN', 'Retirée'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=30, unique=True, db_index=True)
    applicant_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='scholarship_applications'
    )
    last_name = models.CharField(max_length=100)
    first_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    destination = models.ForeignKey(
        Destination, on_delete=models.PROTECT, related_name='applications'
    )
    program = models.CharField(max_length=200, help_text="Ex: Licence, Master")
    study_domain = models.CharField(max_length=200, help_text="Ex: Informatique, Médecine")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SUBMITTED
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_applications'
    )
    review_note = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    tracking_token = models.UUIDField(default=uuid.uuid4, unique=True)

    class Meta:
        db_table = 'scholarship_applications'
        ordering = ['-submitted_at']

    def save(self, *args, **kwargs):
        if not self.reference:
            year = timezone.now().year
            count = ScholarshipApplication.objects.filter(
                submitted_at__year=year
            ).count() + 1
            self.reference = f"BRS-{year}-{count:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.reference} — {self.last_name} {self.first_name}"


def scholarship_doc_path(instance, filename):
    ext = filename.split('.')[-1]
    safe_name = f"{uuid.uuid4().hex}.{ext}"
    return f"private/scholarships/{instance.application.reference}/{safe_name}"


class ScholarshipDocument(models.Model):
    class DocType(models.TextChoices):
        IDENTITY = 'IDENTITY', 'Pièce d\'identité'
        DIPLOMA = 'DIPLOMA', 'Diplômes'
        TRANSCRIPT = 'TRANSCRIPT', 'Relevés de notes'
        PHOTO = 'PHOTO', 'Photo d\'identité'
        MOTIVATION = 'MOTIVATION', 'Lettre de motivation'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        ScholarshipApplication, on_delete=models.CASCADE, related_name='documents'
    )
    document_type = models.CharField(max_length=20, choices=DocType.choices)
    file = models.FileField(
        upload_to=scholarship_doc_path,
        validators=[FileExtensionValidator(
            ['pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx']
        )]
    )
    original_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=100)
    size_bytes = models.PositiveIntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'scholarship_documents'

    def __str__(self):
        return f"{self.get_document_type_display()} — {self.application.reference}"


class AccessEvent(models.Model):
    class EventType(models.TextChoices):
        ENTRY = 'ENTRY', 'Entrée'
        EXIT = 'EXIT', 'Sortie'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    person = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='access_events'
    )
    visitor_label = models.CharField(max_length=200, blank=True)
    event_type = models.CharField(max_length=10, choices=EventType.choices)
    occurred_at = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='recorded_access_events'
    )
    reason = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = 'access_events'
        ordering = ['-occurred_at']


class Notification(models.Model):
    class Type(models.TextChoices):
        ACCOUNT_APPROVED = 'ACCOUNT_APPROVED', 'Compte approuvé'
        ACCOUNT_REJECTED = 'ACCOUNT_REJECTED', 'Compte refusé'
        SCHOLARSHIP_STATUS = 'SCHOLARSHIP_STATUS', 'Statut bourse'
        PAYMENT_RECEIVED = 'PAYMENT_RECEIVED', 'Paiement reçu'
        GENERAL = 'GENERAL', 'Général'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True,
        related_name='notifications'
    )
    email = models.EmailField(blank=True)
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=30, choices=Type.choices)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='audit_actions'
    )
    action = models.CharField(max_length=100, db_index=True)
    entity_type = models.CharField(max_length=50)
    entity_id = models.CharField(max_length=50)
    before_summary = models.JSONField(null=True, blank=True)
    after_summary = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'audit_log'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action} on {self.entity_type}:{self.entity_id}"


class Certificate(models.Model):
    class Status(models.TextChoices):
        ISSUED = 'ISSUED', 'Délivré'
        REVOKED = 'REVOKED', 'Révoqué'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enrollment = models.OneToOneField(
        Enrollment, on_delete=models.PROTECT, related_name='certificate'
    )
    certificate_number = models.CharField(max_length=30, unique=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    issued_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='issued_certificates'
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ISSUED
    )

    class Meta:
        db_table = 'certificates'


# ===========================================================================
# Profil / accueil / prospects
# ===========================================================================


def _next_reference(model, prefix, field='reference'):
    """Génère une référence lisible et unique : PREFIX-ANNEE-0001."""
    year = timezone.now().year
    base = f"{prefix}-{year}-"
    last = (
        model.objects.filter(**{f'{field}__startswith': base})
        .order_by(f'-{field}')
        .first()
    )
    number = 1
    if last:
        try:
            number = int(getattr(last, field).split('-')[-1]) + 1
        except (ValueError, IndexError):
            number = model.objects.filter(
                **{f'{field}__startswith': base}
            ).count() + 1
    candidate = f"{base}{number:04d}"
    while model.objects.filter(**{field: candidate}).exists():
        number += 1
        candidate = f"{base}{number:04d}"
    return candidate


class VisitReason(models.Model):
    """Motif de visite, enrichissable par les personnes autorisées."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    label = models.CharField(max_length=120, unique=True)
    active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'visit_reasons'
        ordering = ['order', 'label']

    def __str__(self):
        return self.label


class Contact(models.Model):
    """Personne physique : visiteur, prospect, ou les deux."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=30, db_index=True)
    secondary_phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True, db_index=True)
    city = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_contacts'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'contacts'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip() or self.phone

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


class Visit(models.Model):
    class Status(models.TextChoices):
        WAITING = 'WAITING', 'En attente'
        IN_PROGRESS = 'IN_PROGRESS', 'En cours'
        COMPLETED = 'COMPLETED', 'Terminée'
        CANCELLED = 'CANCELLED', 'Annulée'

    class VisitorType(models.TextChoices):
        PROSPECT = 'PROSPECT', 'Prospect'
        STUDENT = 'STUDENT', 'Étudiant'
        PARENT = 'PARENT', 'Parent / tuteur'
        PARTNER = 'PARTNER', 'Partenaire'
        OTHER = 'OTHER', 'Autre'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=30, unique=True, db_index=True)
    contact = models.ForeignKey(
        Contact, on_delete=models.PROTECT, related_name='visits'
    )
    visitor_type = models.CharField(
        max_length=20, choices=VisitorType.choices, default=VisitorType.PROSPECT
    )
    reason = models.ForeignKey(
        VisitReason, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='visits'
    )
    request_description = models.TextField(blank=True)
    host_service = models.CharField(max_length=120, blank=True)
    host_person = models.CharField(max_length=120, blank=True)
    arrival_at = models.DateTimeField(default=timezone.now)
    departure_at = models.DateTimeField(null=True, blank=True)
    agent = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='handled_visits'
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.IN_PROGRESS
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'visits'
        ordering = ['-arrival_at']

    def __str__(self):
        return f"{self.reference} — {self.contact}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = _next_reference(Visit, 'VIS')
        super().save(*args, **kwargs)

    @property
    def is_present(self):
        return self.status == self.Status.IN_PROGRESS and not self.departure_at


class Prospect(models.Model):
    class Status(models.TextChoices):
        NEW = 'NEW', 'Nouveau'
        TO_CONTACT = 'TO_CONTACT', 'À contacter'
        CONTACTED = 'CONTACTED', 'Contact établi'
        INFO_GIVEN = 'INFO_GIVEN', 'Renseignements fournis'
        FOLLOW_UP = 'FOLLOW_UP', 'Relance nécessaire'
        INTERESTED = 'INTERESTED', 'Intéressé'
        ENROLLING = 'ENROLLING', 'Inscription en cours'
        ENROLLED = 'ENROLLED', 'Inscrit'
        NOT_INTERESTED = 'NOT_INTERESTED', 'Non intéressé'
        UNREACHABLE = 'UNREACHABLE', 'Injoignable'
        ARCHIVED = 'ARCHIVED', 'Archivé'

    class Source(models.TextChoices):
        VISIT = 'VISIT', 'Visite au centre'
        CALL = 'CALL', 'Appel téléphonique'
        REFERRAL = 'REFERRAL', 'Recommandation'
        SOCIAL = 'SOCIAL', 'Réseaux sociaux'
        WEBSITE = 'WEBSITE', 'Site internet'
        OTHER = 'OTHER', 'Autre'

    class ContactMethod(models.TextChoices):
        PHONE = 'PHONE', 'Téléphone'
        EMAIL = 'EMAIL', 'Email'
        WHATSAPP = 'WHATSAPP', 'WhatsApp'
        VISIT = 'VISIT', 'Visite'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=30, unique=True, db_index=True)
    contact = models.ForeignKey(
        Contact, on_delete=models.PROTECT, related_name='prospects'
    )
    course = models.ForeignKey(
        Course, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='prospects'
    )
    domain = models.CharField(max_length=120, blank=True)
    level = models.CharField(max_length=120, blank=True)
    language_program = models.CharField(max_length=120, blank=True)
    desired_start = models.CharField(max_length=100, blank=True)
    preferred_contact = models.CharField(
        max_length=20, choices=ContactMethod.choices,
        default=ContactMethod.PHONE
    )
    source = models.CharField(
        max_length=20, choices=Source.choices, default=Source.VISIT
    )
    first_contact_at = models.DateField(default=timezone.localdate)
    agent = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='prospects'
    )
    interest_reason = models.TextField(blank=True)
    comments = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NEW
    )
    next_follow_up = models.DateField(null=True, blank=True)
    converted_student = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='converted_from_prospects'
    )
    converted_at = models.DateTimeField(null=True, blank=True)
    visit = models.ForeignKey(
        Visit, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='prospects'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'prospects'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reference} — {self.contact}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = _next_reference(Prospect, 'PRO')
        super().save(*args, **kwargs)

    @property
    def last_follow_up(self):
        return self.follow_ups.order_by('-occurred_at').first()

    @property
    def is_open(self):
        return self.status not in (
            Prospect.Status.ENROLLED,
            Prospect.Status.NOT_INTERESTED,
            Prospect.Status.ARCHIVED,
        )


class ProspectFollowUp(models.Model):
    class ContactType(models.TextChoices):
        CALL = 'CALL', 'Appel'
        MESSAGE = 'MESSAGE', 'Message'
        VISIT = 'VISIT', 'Visite'
        OTHER = 'OTHER', 'Autre'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    prospect = models.ForeignKey(
        Prospect, on_delete=models.CASCADE, related_name='follow_ups'
    )
    occurred_at = models.DateTimeField(default=timezone.now)
    contact_type = models.CharField(
        max_length=20, choices=ContactType.choices, default=ContactType.CALL
    )
    phone_used = models.CharField(max_length=30, blank=True)
    summary = models.TextField()
    info_given = models.TextField(blank=True)
    course = models.ForeignKey(
        Course, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='follow_ups'
    )
    outcome = models.CharField(max_length=200, blank=True)
    next_action = models.CharField(max_length=200, blank=True)
    next_follow_up = models.DateField(null=True, blank=True)
    agent = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='prospect_follow_ups'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'prospect_follow_ups'
        ordering = ['-occurred_at']


# ===========================================================================
# Pédagogie : modules, leçons, séances, ressources
# ===========================================================================


class Module(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name='modules'
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    planned_hours = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'modules'
        ordering = ['course', 'order', 'title']
        unique_together = ('course', 'title')

    def __str__(self):
        return f"{self.course.title} — {self.title}"


class Lesson(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module = models.ForeignKey(
        Module, on_delete=models.CASCADE, related_name='lessons'
    )
    title = models.CharField(max_length=200)
    objectives = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    planned_hours = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'lessons'
        ordering = ['module', 'order', 'title']
        unique_together = ('module', 'title')

    def __str__(self):
        return self.title


class SessionRecord(models.Model):
    """Séance planifiée puis réalisée (compte rendu pédagogique)."""

    class Status(models.TextChoices):
        PLANNED = 'PLANNED', 'Planifiée'
        COMPLETED = 'COMPLETED', 'Réalisée'
        CANCELLED = 'CANCELLED', 'Annulée'
        POSTPONED = 'POSTPONED', 'Reportée'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        CourseSession, on_delete=models.CASCADE, related_name='records'
    )
    module = models.ForeignKey(
        Module, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='session_records'
    )
    lesson = models.ForeignKey(
        Lesson, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='session_records'
    )
    date = models.DateField()
    planned_start = models.TimeField(null=True, blank=True)
    planned_end = models.TimeField(null=True, blank=True)
    actual_start = models.TimeField(null=True, blank=True)
    actual_end = models.TimeField(null=True, blank=True)
    topic = models.CharField(max_length=200, blank=True)
    objectives = models.TextField(blank=True)
    content_covered = models.TextField(blank=True)
    content_remaining = models.TextField(blank=True)
    next_content = models.TextField(blank=True)
    exercises_done = models.TextField(blank=True)
    difficulties = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PLANNED
    )
    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='recorded_sessions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'session_records'
        ordering = ['-date', '-planned_start']
        unique_together = ('session', 'date', 'planned_start')

    def __str__(self):
        return f"{self.session.course.title} — {self.date}"

    @staticmethod
    def _minutes(start, end):
        if not start or not end:
            return 0
        return max(
            (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute), 0
        )

    @property
    def planned_minutes(self):
        return self._minutes(self.planned_start, self.planned_end)

    @property
    def actual_minutes(self):
        return self._minutes(self.actual_start, self.actual_end)

    @property
    def planned_hours(self):
        return round(self.planned_minutes / 60, 2)

    @property
    def actual_hours(self):
        return round(self.actual_minutes / 60, 2)


class Resource(models.Model):
    class Kind(models.TextChoices):
        COURSE = 'COURSE', 'Support de cours'
        EXERCISE = 'EXERCISE', 'Exercice'
        HOMEWORK = 'HOMEWORK', 'Devoir'
        RESOURCE = 'RESOURCE', 'Ressource'

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Brouillon'
        PUBLISHED = 'PUBLISHED', 'Publié'
        ARCHIVED = 'ARCHIVED', 'Archivé'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name='resources'
    )
    module = models.ForeignKey(
        Module, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='resources'
    )
    lesson = models.ForeignKey(
        Lesson, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='resources'
    )
    session = models.ForeignKey(
        CourseSession, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='resources',
        help_text="Groupe destinataire (facultatif)"
    )
    kind = models.CharField(
        max_length=20, choices=Kind.choices, default=Kind.COURSE
    )
    file = models.FileField(
        upload_to='private/resources/', null=True, blank=True,
        validators=[FileExtensionValidator(
            ['pdf', 'doc', 'docx', 'html', 'htm', 'ppt', 'pptx', 'xls', 'xlsx', 'zip']
        )]
    )
    html_content = models.TextField(
        blank=True, help_text="Contenu HTML optionnel (assaini à l'affichage)"
    )
    published_at = models.DateTimeField(null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    author = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='authored_resources'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'resources'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def is_published(self):
        return self.status == self.Status.PUBLISHED


def student_doc_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower()
    code = instance.student.internal_code or str(instance.student_id)
    return f"private/students/{code}/{uuid.uuid4().hex}.{ext}"


class StudentDocument(models.Model):
    class DocType(models.TextChoices):
        IDENTITY = 'IDENTITY', "Pièce d'identité"
        DIPLOMA = 'DIPLOMA', 'Diplôme'
        TRANSCRIPT = 'TRANSCRIPT', 'Relevé de notes'
        PHOTO = 'PHOTO', "Photo d'identité"
        CERTIFICATE = 'CERTIFICATE', 'Certificat'
        OTHER = 'OTHER', 'Autre document'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='student_documents'
    )
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='documents'
    )
    doc_type = models.CharField(max_length=20, choices=DocType.choices)
    file = models.FileField(
        upload_to=student_doc_path,
        validators=[FileExtensionValidator(
            ['pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx']
        )]
    )
    original_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='uploaded_student_documents'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'student_documents'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.get_doc_type_display()} — {self.student}"


# ===========================================================================
# Comptabilité : caisses, catégories, opérations, clôtures
# ===========================================================================


class CashAccount(models.Model):
    class Kind(models.TextChoices):
        CASH = 'CASH', 'Caisse (espèces)'
        MOBILE_MONEY = 'MOBILE_MONEY', 'Mobile Money'
        BANK = 'BANK', 'Compte bancaire'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.CASH)
    currency = models.CharField(max_length=5, default='XAF')
    opening_balance = models.IntegerField(default=0)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cash_accounts'
        ordering = ['name']

    def __str__(self):
        return self.name

    def movement_totals(self, start=None, end=None):
        """Entrées et sorties validées de cette caisse, bornes incluses."""
        base = CashTransaction.objects.filter(
            status=CashTransaction.Status.VALIDATED
        )
        if start:
            base = base.filter(occurred_at__date__gte=start)
        if end:
            base = base.filter(occurred_at__date__lte=end)
        incoming = base.filter(
            models.Q(tx_type=CashTransaction.Type.IN, account=self) |
            models.Q(tx_type=CashTransaction.Type.TRANSFER,
                     destination_account=self)
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        outgoing = base.filter(
            models.Q(tx_type=CashTransaction.Type.OUT, account=self) |
            models.Q(tx_type=CashTransaction.Type.TRANSFER, account=self)
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        return incoming, outgoing

    def balance_at(self, until_date=None):
        incoming, outgoing = self.movement_totals(end=until_date)
        return self.opening_balance + incoming - outgoing

    def totals(self):
        return self.movement_totals()

    @property
    def balance(self):
        return self.balance_at()


class TransactionCategory(models.Model):
    class Direction(models.TextChoices):
        IN = 'IN', 'Entrée'
        OUT = 'OUT', 'Sortie'
        TRANSFER = 'TRANSFER', 'Transfert'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    direction = models.CharField(max_length=10, choices=Direction.choices)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = 'transaction_categories'
        ordering = ['direction', 'name']
        unique_together = ('name', 'direction')

    def __str__(self):
        return f"{self.name} ({self.get_direction_display()})"


class CashTransaction(models.Model):
    class Type(models.TextChoices):
        IN = 'IN', 'Entrée'
        OUT = 'OUT', 'Sortie'
        TRANSFER = 'TRANSFER', 'Transfert'

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'En attente'
        VALIDATED = 'VALIDATED', 'Validée'
        CANCELLED = 'CANCELLED', 'Annulée'

    Method = Payment.Method

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=30, unique=True, db_index=True)
    tx_type = models.CharField(max_length=10, choices=Type.choices)
    category = models.ForeignKey(
        TransactionCategory, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='transactions'
    )
    label = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    amount = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    currency = models.CharField(max_length=5, default='XAF')
    occurred_at = models.DateTimeField(default=timezone.now)
    account = models.ForeignKey(
        CashAccount, on_delete=models.PROTECT, related_name='transactions'
    )
    destination_account = models.ForeignKey(
        CashAccount, on_delete=models.PROTECT, null=True, blank=True,
        related_name='incoming_transfers'
    )
    method = models.CharField(
        max_length=20, choices=Payment.Method.choices,
        default=Payment.Method.CASH
    )
    counterparty = models.CharField(max_length=200, blank=True)
    receipt = models.FileField(
        upload_to='private/transactions/', blank=True,
        validators=[FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png'])]
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.VALIDATED
    )
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_transactions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cash_transactions'
        ordering = ['-occurred_at', '-created_at']

    def __str__(self):
        return f"{self.reference} — {self.label}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = _next_reference(CashTransaction, 'TRX')
        super().save(*args, **kwargs)

    @property
    def signed_amount(self):
        if self.status != self.Status.VALIDATED:
            return 0
        if self.tx_type == self.Type.IN:
            return self.amount
        if self.tx_type == self.Type.OUT:
            return -self.amount
        return 0


class CashClosure(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        CashAccount, on_delete=models.CASCADE, related_name='closures'
    )
    date = models.DateField(default=timezone.localdate)
    opening_balance = models.IntegerField(default=0)
    theoretical_balance = models.IntegerField(default=0)
    counted_amount = models.IntegerField(default=0)
    difference = models.IntegerField(default=0)
    note = models.TextField(blank=True)
    closed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cash_closures'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cash_closures'
        ordering = ['-date', 'account']
        unique_together = ('account', 'date')

    def __str__(self):
        return f"{self.account} — {self.date}"



