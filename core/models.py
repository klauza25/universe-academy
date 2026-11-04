import uuid
import os
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.core.validators import (
    FileExtensionValidator, MaxValueValidator, MinValueValidator, RegexValidator
)
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class AccountStatus(models.TextChoices):
    PENDING_APPROVAL = 'PENDING_APPROVAL', _("En attente d'approbation")
    ACTIVE = 'ACTIVE', _("Actif")
    SUSPENDED = 'SUSPENDED', _("Suspendu")
    DISABLED = 'DISABLED', _("Désactivé")
    REJECTED = 'REJECTED', _("Refusé")


class RoleKey(models.TextChoices):
    SUPER_ADMIN = 'SUPER_ADMIN', _("Super Administrateur")
    ADMIN = 'ADMIN', _("Administrateur")
    DIRECTION = 'DIRECTION', _("Direction")
    ASSISTANT_ADMIN = 'ASSISTANT_ADMIN', _("Assistant administratif")
    SECRETAIRE = 'SECRETAIRE', _("Secrétaire")
    COMPTABLE = 'COMPTABLE', _("Comptable")
    RESPONSABLE_PEDAGOGIQUE = 'RESP_PEDA', _("Responsable pédagogique")
    FORMATEUR = 'FORMATEUR', _("Formateur")
    ETUDIANT = 'ETUDIANT', _("Étudiant")
    ACCUEIL = 'ACCUEIL', _("Accueil / Contrôle")


# Postes fusionnés dans ASSISTANT_ADMIN. Les lignes restent en base pour que
# l'historique (audit, paiements encaissés, demandes d'accès passées) garde son
# sens ; ils ne sont plus attribuables nulle part et n'ont plus de menu.
ROLES_DISSOUS = ('COMPTABLE', 'ACCUEIL')

ROLE_DASHBOARD_ROUTES = {
    'SUPER_ADMIN': 'core:dashboard:super-admin-dashboard',
    'ADMIN': 'core:dashboard:admin-dashboard',
    'DIRECTION': 'core:dashboard:direction-dashboard',
    'ASSISTANT_ADMIN': 'core:dashboard:comptabilite-dashboard',
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
    'ETUDIANT', 'FORMATEUR', 'SECRETAIRE', 'ASSISTANT_ADMIN', 'RESP_PEDA',
)
REQUESTABLE_ROLE_CHOICES = [
    (key, RoleKey(key).label) for key in REQUESTABLE_ROLES
]

# Les droits fins que l'éditeur « Permissions » case par case. Une seule liste :
# la commande de seed la lit pour créer les lignes, l'éditeur pour les nommer.
PERMISSIONS = [
    ('users.read', _("Lire les utilisateurs")),
    ('users.create', _("Créer des utilisateurs")),
    ('users.edit', _("Modifier des utilisateurs")),
    ('roles.manage', _("Gérer les rôles")),
    ('access_requests.review', _("Examiner les demandes d'accès")),
    ('students.read', _("Lire les dossiers étudiants")),
    ('students.write', _("Modifier les dossiers étudiants")),
    ('formations.read', _("Lire les formations")),
    ('formations.write', _("Modifier les formations")),
    ('attendance.read', _("Lire les présences")),
    ('attendance.write', _("Saisir les présences")),
    ('finance.read', _("Lire les données financières")),
    ('finance.write', _("Saisir des paiements")),
    ('scholarship.read', _("Lire les candidatures bourse")),
    ('scholarship.review', _("Examiner les candidatures bourse")),
    ('access_events.read', _("Lire le journal des entrées/sorties")),
    ('access_events.write', _("Enregistrer les entrées/sorties")),
    ('audit.read', _("Lire le journal d'audit")),
    ('certificates.issue', _("Délivrer des certificats")),
]
PERMISSION_LABELS = dict(PERMISSIONS)

INTERNAL_CODE_PREFIXES = {
    'SUPER_ADMIN': 'UA-ADM',
    'ADMIN': 'UA-ADM',
    'DIRECTION': 'UA-DIR',
    'ASSISTANT_ADMIN': 'UA-ASY',
    'SECRETAIRE': 'UA-SEC',
    'RESP_PEDA': 'UA-RPD',
    'FORMATEUR': 'UA-FRM',
    'ETUDIANT': 'UA-ETU',
    # repris des postes dissous : les codes déjà distribués gardent leur racine
    'COMPTABLE': 'UA-CPT',
    'ACCUEIL': 'UA-ACC',
}


def avatar_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower()
    return f"avatars/{instance.id}/{uuid.uuid4().hex}.{ext}"


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_("L'email est obligatoire"))
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
        role, _role_cree = Role.objects.using(self._db).get_or_create(
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
        help_text=_("Code interne ex: UA-ETU-0001")
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
        help_text=_("Identifiant utilisateur Clerk (user_...) lié à ce compte")
    )
    display_name = models.CharField(
        max_length=150, blank=True,
        help_text=_("Nom affiché dans l'interface (facultatif)")
    )
    avatar = models.ImageField(
        upload_to=avatar_path, null=True, blank=True,
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])],
        help_text=_("Photo de profil (JPG, PNG ou WebP, 2 Mo max)")
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
        return f"{self.get_full_name()} ({self.internal_code or self.email})"  # i18n-exempt: interpolation de données seule, aucun texte à traduire

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

    def poser_avatar(self, image):
        """Change la photo de profil et retire du disque celle qu'elle remplace.

        Sans ce nettoyage, chaque changement laisserait un fichier orphelin : la
        fiche ne montre que la photo en cours, l'ancienne n'est plus référencée
        nulle part.
        """
        ancienne = self.avatar.name if self.avatar else ''
        stockage = self.avatar.storage
        self.avatar = image
        self.save(update_fields=['avatar'])
        if ancienne:
            stockage.delete(ancienne)

    def retirer_avatar(self):
        """Rend la vignette aux initiales et débarrasse le fichier en cours."""
        if not self.avatar:
            return False
        self.avatar.delete(save=False)
        self.avatar = None
        self.save(update_fields=['avatar'])
        return True

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
        PENDING = 'PENDING', _("En attente")
        APPROVED = 'APPROVED', _("Approuvée")
        REJECTED = 'REJECTED', _("Refusée")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='access_requests')
    requested_role = models.CharField(max_length=20, choices=RoleKey.choices, blank=True)
    assigned_role = models.CharField(
        max_length=20, choices=RoleKey.choices, blank=True,
        help_text=_("Rôle effectif attribué lors de l'approbation"),
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
        help_text=_("Montant en FCFA"),
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
        PLANNED = 'PLANNED', _("Planifiée")
        ACTIVE = 'ACTIVE', _("En cours")
        COMPLETED = 'COMPLETED', _("Terminée")
        CANCELLED = 'CANCELLED', _("Annulée")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='sessions')
    starts_at = models.DateField()
    ends_at = models.DateField()
    schedule = models.CharField(
        max_length=100, blank=True,
        help_text=_("Ex: Lun-Ven 13h-15h")
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
        PENDING = 'PENDING', _("En attente")
        ACTIVE = 'ACTIVE', _("Active")
        COMPLETED = 'COMPLETED', _("Terminée")
        CANCELLED = 'CANCELLED', _("Annulée")
        SUSPENDED = 'SUSPENDED', _("Suspendue")

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
        default=0, help_text=_("Tarif catalogue appliqué (FCFA)")
    )
    discount_amount = models.PositiveIntegerField(
        default=0, help_text=_("Remise autorisée (FCFA)")
    )
    net_amount = models.PositiveIntegerField(
        default=0, help_text=_("Montant net dû (FCFA)")
    )
    payment_plan = models.CharField(
        max_length=200, blank=True,
        help_text=_("Ex: 2 versements — 50 % à l'inscription")
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
        PRESENT = 'PRESENT', _("Présent")
        ABSENT = 'ABSENT', _("Absent")
        LATE = 'LATE', _("En retard")
        EXCUSED = 'EXCUSED', _("Excusé")

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


class StudentSessionNote(models.Model):
    """Fiche de cours remplie par l'apprenant après chaque séance.

    Reprend les colonnes de la fiche papier remise aux étudiants : notions
    retenues, difficultés rencontrées et observations.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name='session_notes'
    )
    session_record = models.ForeignKey(
        'SessionRecord', on_delete=models.CASCADE, related_name='student_notes'
    )
    notions_learned = models.TextField(
        _("Notions retenues"),
        help_text=_("Ce que j'ai appris pendant cette séance"),
    )
    difficulties = models.TextField(_("Difficultés"), blank=True)
    observations = models.TextField(_("Observations"), blank=True)
    attended = models.BooleanField(
        _("J'étais présent à cette séance"), default=True,
    )
    followed_start = models.TimeField(
        _("Heure de début suivie"), null=True, blank=True,
    )
    followed_end = models.TimeField(
        _("Heure de fin suivie"), null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'student_session_notes'
        unique_together = ('enrollment', 'session_record')
        ordering = ['-session_record__date', '-created_at']  # i18n-exempt: lookup ORM

    def __str__(self):
        return f"{self.enrollment.student} — {self.session_record.date}"  # i18n-exempt: interpolation de données seule, aucun texte à traduire

    @property
    def student(self):
        return self.enrollment.student


MOIS = (
    (1, _('janvier')), (2, _('février')), (3, _('mars')), (4, _('avril')),
    (5, _('mai')), (6, _('juin')), (7, _('juillet')), (8, _('août')),
    (9, _('septembre')), (10, _('octobre')), (11, _('novembre')),
    (12, _('décembre')),
)


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = 'CASH', _("Espèces")
        MOBILE_MONEY = 'MOBILE_MONEY', _("Mobile Money")
        BANK_TRANSFER = 'BANK_TRANSFER', _("Virement bancaire")
        OTHER = 'OTHER', _("Autre")

    class Status(models.TextChoices):
        COMPLETED = 'COMPLETED', _("Effectué")
        PENDING = 'PENDING', _("En attente")
        CANCELLED = 'CANCELLED', _("Annulé")
        REFUNDED = 'REFUNDED', _("Remboursé")

    class Motif(models.TextChoices):
        MONTHLY = 'MONTHLY', _("Mensualité")
        ENROLLMENT = 'ENROLLMENT', _("Frais d'inscription")
        OTHER = 'OTHER', _("Autre paiement")

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
    motif = models.CharField(
        max_length=20, choices=Motif.choices, default=Motif.OTHER,
        verbose_name=_("Motif du paiement"),
    )
    # Le mois que ce règlement solde, distinct de la date d'encaissement :
    # l'assistant encaisse en février une mensualité de janvier.
    period_year = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("Année du mois réglé"))
    period_month = models.PositiveIntegerField(
        null=True, blank=True, choices=MOIS, verbose_name=_("Mois réglé"))
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
        constraints = [
            models.UniqueConstraint(
                fields=('enrollment', 'period_year', 'period_month'),
                condition=~models.Q(status__in=['CANCELLED', 'REFUNDED'])
                          & models.Q(period_month__isnull=False),
                name='payment_month_once_per_enrollment',
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"PAY-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    @property
    def period_label(self):
        if not self.period_month:
            return ''
        return dict(MOIS)[self.period_month]


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
        SUBMITTED = 'SUBMITTED', _("Soumise")
        UNDER_REVIEW = 'UNDER_REVIEW', _("En cours d'examen")
        DOCUMENTS_REQUESTED = 'DOCS_REQUESTED', _("Documents demandés")
        APPROVED = 'APPROVED', _("Approuvée")
        REJECTED = 'REJECTED', _("Rejetée")
        WITHDRAWN = 'WITHDRAWN', _("Retirée")

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
    program = models.CharField(max_length=200, help_text=_("Ex: Licence, Master"))
    study_domain = models.CharField(max_length=200, help_text=_("Ex: Informatique, Médecine"))
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
        IDENTITY = 'IDENTITY', _("Pièce d'identité")
        DIPLOMA = 'DIPLOMA', _("Diplômes")
        TRANSCRIPT = 'TRANSCRIPT', _("Relevés de notes")
        PHOTO = 'PHOTO', _("Photo d'identité")
        MOTIVATION = 'MOTIVATION', _("Lettre de motivation")

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
        ENTRY = 'ENTRY', _("Entrée")
        EXIT = 'EXIT', _("Sortie")

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
        ACCOUNT_APPROVED = 'ACCOUNT_APPROVED', _("Compte approuvé")
        ACCOUNT_REJECTED = 'ACCOUNT_REJECTED', _("Compte refusé")
        SCHOLARSHIP_STATUS = 'SCHOLARSHIP_STATUS', _("Statut bourse")
        PAYMENT_RECEIVED = 'PAYMENT_RECEIVED', _("Paiement reçu")
        GENERAL = 'GENERAL', _("Général")

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
        return f"{self.action} on {self.entity_type}:{self.entity_id}"  # i18n-exempt: contenu technique du journal d'audit


class Certificate(models.Model):
    class Status(models.TextChoices):
        ISSUED = 'ISSUED', _("Délivré")
        REVOKED = 'REVOKED', _("Révoqué")

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
        WAITING = 'WAITING', _("En attente")
        IN_PROGRESS = 'IN_PROGRESS', _("En cours")
        COMPLETED = 'COMPLETED', _("Terminée")
        CANCELLED = 'CANCELLED', _("Annulée")

    class VisitorType(models.TextChoices):
        PROSPECT = 'PROSPECT', _("Prospect")
        STUDENT = 'STUDENT', _("Étudiant")
        PARENT = 'PARENT', _("Parent / tuteur")
        PARTNER = 'PARTNER', _("Partenaire")
        OTHER = 'OTHER', _("Autre")

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
        NEW = 'NEW', _("Nouveau")
        TO_CONTACT = 'TO_CONTACT', _("À contacter")
        CONTACTED = 'CONTACTED', _("Contact établi")
        INFO_GIVEN = 'INFO_GIVEN', _("Renseignements fournis")
        FOLLOW_UP = 'FOLLOW_UP', _("Relance nécessaire")
        INTERESTED = 'INTERESTED', _("Intéressé")
        ENROLLING = 'ENROLLING', _("Inscription en cours")
        ENROLLED = 'ENROLLED', _("Inscrit")
        NOT_INTERESTED = 'NOT_INTERESTED', _("Non intéressé")
        UNREACHABLE = 'UNREACHABLE', _("Injoignable")
        ARCHIVED = 'ARCHIVED', _("Archivé")

    class Source(models.TextChoices):
        VISIT = 'VISIT', _("Visite au centre")
        CALL = 'CALL', _("Appel téléphonique")
        REFERRAL = 'REFERRAL', _("Recommandation")
        SOCIAL = 'SOCIAL', _("Réseaux sociaux")
        WEBSITE = 'WEBSITE', _("Site internet")
        OTHER = 'OTHER', _("Autre")

    class ContactMethod(models.TextChoices):
        PHONE = 'PHONE', _("Téléphone")
        EMAIL = 'EMAIL', _("Email")
        WHATSAPP = 'WHATSAPP', _("WhatsApp")
        VISIT = 'VISIT', _("Visite")

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
        CALL = 'CALL', _("Appel")
        MESSAGE = 'MESSAGE', _("Message")
        VISIT = 'VISIT', _("Visite")
        OTHER = 'OTHER', _("Autre")

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
        PLANNED = 'PLANNED', _("Planifiée")
        COMPLETED = 'COMPLETED', _("Réalisée")
        CANCELLED = 'CANCELLED', _("Annulée")
        POSTPONED = 'POSTPONED', _("Reportée")

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
    attendee_count = models.PositiveIntegerField(
        null=True, blank=True,
        help_text=_("Nombre d'apprenants présents relevé sur le cahier de texte"),
    )
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
        return f"{self.session.course.title} — {self.date}"  # i18n-exempt: interpolation de données seule, aucun texte à traduire

    @staticmethod
    def _minutes(start, end):
        # Une durée n'est connue que si les deux horaires sont renseignés :
        # à défaut elle reste vide (None) plutôt que comptée comme zéro.
        if not start or not end:
            return None
        return max(
            (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute), 0
        )

    @property
    def planned_minutes(self):
        return self._minutes(self.planned_start, self.planned_end)

    @property
    def actual_minutes(self):
        return self._minutes(self.actual_start, self.actual_end)

    # -- Cahier de texte -------------------------------------------------
    @property
    def attendance_count(self):
        """Apprenants pointés présents ou en retard sur la feuille de présence."""
        return self.attendances.exclude(
            status=Attendance.Status.ABSENT
        ).count()

    @property
    def displayed_attendee_count(self):
        """Nombre d'apprenants du cahier de texte.

        Le relevé manuscrit saisi par le formateur fait foi ; à défaut, le
        nombre est déduit de la feuille de présence (annotation
        ``present_count`` quand la liste est annotée).
        """
        if self.attendee_count is not None:
            return self.attendee_count
        if hasattr(self, 'present_count'):
            return self.present_count
        return self.attendance_count

    @property
    def display_start(self):
        return self.actual_start or self.planned_start

    @property
    def display_end(self):
        return self.actual_end or self.planned_end

    @property
    def display_minutes(self):
        return (
            self.actual_minutes
            if self.actual_minutes is not None
            else self.planned_minutes
        )


class Resource(models.Model):
    class Kind(models.TextChoices):
        COURSE = 'COURSE', _("Support de cours")
        EXERCISE = 'EXERCISE', _("Exercice")
        HOMEWORK = 'HOMEWORK', _("Devoir")
        RESOURCE = 'RESOURCE', _("Ressource")

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', _("Brouillon")
        PUBLISHED = 'PUBLISHED', _("Publié")
        ARCHIVED = 'ARCHIVED', _("Archivé")

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
        help_text=_("Groupe destinataire (facultatif)")
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
        blank=True, help_text=_("Contenu HTML optionnel (assaini à l'affichage)")
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


class ResourceFeedback(models.Model):
    """Retour d'un étudiant sur une ressource publiée par un formateur."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resource = models.ForeignKey(
        Resource, on_delete=models.CASCADE, related_name='feedback'
    )
    student = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='resource_feedback'
    )
    rating = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text=_("Note de 1 à 5")
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'resource_feedback'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['resource', 'student'],
                name='unique_feedback_per_student_resource',
            )
        ]

    def __str__(self):
        return f"{self.student} → {self.resource}"


def student_doc_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower()
    code = instance.student.internal_code or str(instance.student_id)
    return f"private/students/{code}/{uuid.uuid4().hex}.{ext}"


class StudentDocument(models.Model):
    class DocType(models.TextChoices):
        IDENTITY = 'IDENTITY', _("Pièce d'identité")
        DIPLOMA = 'DIPLOMA', _("Diplôme")
        TRANSCRIPT = 'TRANSCRIPT', _("Relevé de notes")
        PHOTO = 'PHOTO', _("Photo d'identité")
        CERTIFICATE = 'CERTIFICATE', _("Certificat")
        OTHER = 'OTHER', _("Autre document")

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
        CASH = 'CASH', _("Caisse (espèces)")
        MOBILE_MONEY = 'MOBILE_MONEY', _("Mobile Money")
        BANK = 'BANK', _("Compte bancaire")

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', _("Actif")
        INACTIVE = 'INACTIVE', _("Inactif")
        ARCHIVED = 'ARCHIVED', _("Archivé")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.CASH)
    currency = models.CharField(max_length=5, default='XAF')
    opening_balance = models.IntegerField(default=0)
    active = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    # Un découvert reste interdit tant que ce plafond vaut 0 : il ne se baisse
    # pas, il se lève compte par compte, par un super administrateur.
    overdraft_limit = models.PositiveIntegerField(default=0)
    archived_at = models.DateTimeField(null=True, blank=True)
    # Un compte archivé ne laisse pas un trou : le remplacement désigne la caisse
    # qui reprend la saisie, et l'écran le montre à qui consulte l'historique.
    replaced_by = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='remplacants'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cash_accounts'
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def status(self):
        """État du compte, lu de ses deux marqueurs : rien n'est stocké deux fois."""
        if self.archived_at:
            return self.Status.ARCHIVED
        return self.Status.ACTIVE if self.active else self.Status.INACTIVE

    @property
    def writable(self):
        """Un compte archivé ne reçoit plus d'écriture : son solde est figé."""
        return self.status != self.Status.ARCHIVED

    @property
    def status_label(self):
        """Le libellé de l'état, tel que l'écran doit le montrer."""
        return self.Status(self.status).label

    def movement_totals(self, start=None, end=None, ignored=()):
        """Entrées et sorties validées de cette caisse, bornes incluses.

        `ignored` exclut des écritures déjà en base : une ligne que l'on modifie
        ou que l'on annule ne doit pas compter deux fois dans le calcul.
        """
        base = CashTransaction.objects.filter(
            status=CashTransaction.Status.VALIDATED
        )
        if ignored:
            base = base.exclude(id__in=list(ignored))
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

    def balance_after(self, *, debited=0, credited=0, ignored=()):
        """Solde de la caisse une fois ce mouvement appliqué.

        Une caisse ne peut pas prêter l'argent qu'elle n'a pas : ce calcul sert
        de garde à toute écriture qui la débite — écran de caisse, annulation
        d'une entrée, reprise du journal.
        """
        incoming, outgoing = self.movement_totals(ignored=ignored)
        return self.opening_balance + incoming + credited - outgoing - debited

    def decouvert(self, *, debited=0, credited=0, ignored=()):
        """Le creux à combler si ce mouvement passait sous le plancher, sinon 0.

        Le plancher vaut −« découvert autorisé » : à 0, comme sur presque tous
        les comptes, la ligne ne descend jamais sous zéro. Une seule règle,
        appelée de l'écran, de l'annulation, de l'import et de `save()`.
        """
        projet = self.balance_after(debited=debited, credited=credited,
                                    ignored=ignored)
        return max(0, -self.overdraft_limit - projet)

    def disponible(self):
        """Ce que la caisse peut réellement débourser aujourd'hui."""
        return self.balance + self.overdraft_limit

    def totals(self):
        return self.movement_totals()

    @property
    def balance(self):
        return self.balance_at()


class TransactionCategory(models.Model):
    class Direction(models.TextChoices):
        IN = 'IN', _("Entrée")
        OUT = 'OUT', _("Sortie")
        TRANSFER = 'TRANSFER', _("Transfert")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    direction = models.CharField(max_length=10, choices=Direction.choices)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = 'transaction_categories'
        ordering = ['direction', 'name']
        unique_together = ('name', 'direction')

    def __str__(self):
        return f"{self.name} ({self.get_direction_display()})"  # i18n-exempt: nom stocké + libellé de choix déjà traduit


class CashTransaction(models.Model):
    class Type(models.TextChoices):
        IN = 'IN', _("Entrée")
        OUT = 'OUT', _("Sortie")
        TRANSFER = 'TRANSFER', _("Transfert")

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', _("En attente")
        VALIDATED = 'VALIDATED', _("Validée")
        CANCELLED = 'CANCELLED', _("Annulée")

    class Nature(models.TextChoices):
        NORMAL = 'NORMAL', _("Écriture ordinaire")
        ADJUSTMENT = 'ADJUSTMENT', _("Ajustement de solde")
        RESET = 'RESET', _("Réinitialisation")

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
    nature = models.CharField(
        max_length=12, choices=Nature.choices, default=Nature.NORMAL
    )
    # Une ligne corrigée ou régularisée reste en base : ce lien dit laquelle a
    # été remplacée, et l'écran peut montrer les deux côte à côte.
    replaces = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='replacements'
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
        self._verrou_solde()
        super().save(*args, **kwargs)

    def _effets(self):
        """Ce que cette écriture ajoute et retire, caisse par caisse.

        Une entrée ne touche que son compte ; un transfert retire d'un côté et
        ajoute de l'autre : la garde doit juger les deux.
        """
        if self.tx_type == self.Type.IN:
            return [(self.account, self.amount, 0)]
        if self.tx_type == self.Type.OUT:
            return [(self.account, 0, self.amount)]
        effets = [(self.account, 0, self.amount)]
        if self.destination_account_id:
            effets.append((self.destination_account, self.amount, 0))
        return effets

    def _verrou_solde(self):
        """Refuser ici, et pas seulement à l'écran, toute écriture à découvert.

        Un import, l'administration, le service d'ajustement ou un script
        passent tous par cette porte : le solde d'une caisse ne descend jamais
        sous son plancher, sauf découvert explicitement autorisé sur le compte.
        Le brouillon reste libre — il ne compte pas en caisse.
        """
        if self.status != self.Status.VALIDATED:
            return
        if self.account_id is None:
            # Une écriture sans compte n'est pas une écriture en difficulté :
            # c'est le champ obligatoire qui doit le dire, pas le solde.
            return
        ignorees = ([self.pk] if self.pk and
                    CashTransaction.objects.filter(pk=self.pk).exists() else [])
        for caisse, credite, debite in self._effets():
            if not debite:
                # Une recette ne peut pas creuser un trou : elle doit passer,
                # même sur un compte déjà en difficulté, qu'elle contribue à
                # combler.
                continue
            creux = caisse.decouvert(credited=credite, debited=debite,
                                     ignored=ignorees)
            if creux:
                raise ValidationError(_(
                    'Solde insuffisant sur « %(caisse)s » : cette écriture laisserait un découvert de %(creux)s %(devise)s (découvert autorisé : %(plafond)s). Enregistrez d’abord la recette qui alimente ce compte.') % {
                        'caisse': caisse.name,
                        'creux': f'{creux:,}'.replace(',', ' '),
                        'devise': caisse.currency,
                        'plafond': f'{caisse.overdraft_limit:,}'.replace(',', ' '),
                    })

    def clean(self):
        """Les contrôles du modèle valent aussi pour `full_clean()`."""
        super().clean()
        try:
            self._verrou_solde()
        except ValidationError as erreur:
            raise ValidationError({'amount': erreur.messages})
        if (self.tx_type == self.Type.TRANSFER and self.destination_account_id and
                self.destination_account_id == self.account_id):
            raise ValidationError({
                'destination_account': _("Un transfert doit changer de compte.")})

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
        return f"{self.account} — {self.date}"  # i18n-exempt: interpolation de données seule, aucun texte à traduire



