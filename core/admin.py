from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from . import groupes
from .models import (
    User, Role, Permission, UserRole, RolePermission,
    AccessRequest, Course, CourseSession, Enrollment, AcademicYear,
    Attendance, Payment, Expense,
    ScholarshipApplication, ScholarshipDocument, Destination,
    AccessEvent, Notification, AuditLog, Certificate, ResourceFeedback,
    CashAccount, CashClosure, CashTransaction, TransactionCategory,
    PlatformSetting,
)
from .utils import log_audit, notifier_changement_statut_bourse


class ConsultationSeule(admin.ModelAdmin):
    """Ligne consultable ici, mais écrite seulement au tableau de bord.

    Une écriture de caisse, un encaissement, une présence ou un certificat se
    posent par le service d'écriture : c'est lui qui garde le solde, exige un
    motif, rattache l'écriture de caisse et laisse sa ligne d'audit. Ouvrir une
    seconde porte d'écriture reviendrait à pouvoir déplacer un solde en silence
    ou créer un paiement qui n'est jamais rentré en caisse.
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'internal_code', 'get_full_name', 'account_status', 'date_joined')
    list_filter = ('account_status', 'roles')
    search_fields = ('email', 'first_name', 'last_name', 'internal_code')
    ordering = ('-date_joined',)
    readonly_fields = ('internal_code',)
    fieldsets = BaseUserAdmin.fieldsets + (
        (_('Compte et coordonnées'), {
            'fields': ('internal_code', 'account_status', 'phone', 'address',
                       'birth_date')
        }),
    )

    def save_model(self, request, obj, form, change):
        # Le code interne est toujours généré automatiquement, jamais saisi.
        if not obj.internal_code:
            obj.generate_internal_code(obj.primary_role)
        super().save_model(request, obj, form, change)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('key', 'label', 'is_privileged')


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ('key', 'description')


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    class CourseForm(forms.ModelForm):
        monthly_fee_amount = forms.IntegerField(
            min_value=0,
            label=_("Tarif mensuel"),
        )

        class Meta:
            model = Course
            fields = '__all__'

    form = CourseForm
    list_display = (
        'title', 'domain', 'monthly_fee_amount', 'fee_amount',
        'duration_months', 'active',
    )
    list_filter = ('domain', 'active')

class FormuleGroupeAdmin(forms.ModelForm):
    """La même règle que l'écran Groupes, appliquée ici aussi.

    Laisser cette porte ouverte sans elle reviendrait à créer ici un groupe
    qu'il est impossible de créer là.
    """

    class Meta:
        model = CourseSession
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance._state.adding:
            self.fields['name'].required = True

    def clean(self):
        cleaned = super().clean()
        groupes.applique_la_regle(self)
        return cleaned


@admin.register(CourseSession)
class CourseSessionAdmin(admin.ModelAdmin):
    form = FormuleGroupeAdmin
    list_display = ('name', 'course', 'starts_at', 'ends_at', 'status', 'capacity')
    list_filter = ('status',)


@admin.register(Enrollment)
class EnrollmentAdmin(ConsultationSeule):
    list_display = ('student', 'session', 'status', 'enrolled_at')
    list_filter = ('status',)


@admin.register(Payment)
class PaymentAdmin(ConsultationSeule):
    list_display = ('reference', 'amount', 'currency', 'method', 'status', 'paid_at')
    list_filter = ('status', 'method')
    search_fields = ('reference',)


@admin.register(ScholarshipApplication)
class ScholarshipApplicationAdmin(admin.ModelAdmin):
    list_display = ('reference', 'last_name', 'first_name', 'destination', 'status', 'submitted_at')
    list_filter = ('status', 'destination')
    search_fields = ('reference', 'last_name', 'email')

    def save_model(self, request, obj, form, change):
        statut_precedent = None
        if change and obj.pk:
            statut_precedent = ScholarshipApplication.objects.filter(
                pk=obj.pk
            ).values_list('status', flat=True).first()
        super().save_model(request, obj, form, change)
        if statut_precedent and statut_precedent != obj.status:
            log_audit(
                request, 'SCHOLARSHIP_REVIEW', 'ScholarshipApplication',
                str(obj.pk),
                before={'status': statut_precedent},
                after={'status': obj.status},
            )
            notifier_changement_statut_bourse(obj, statut_precedent, request)


@admin.register(Destination)
class DestinationAdmin(admin.ModelAdmin):
    list_display = ('name', 'active')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor', 'action', 'entity_type', 'entity_id')
    list_filter = ('action', 'entity_type')
    readonly_fields = ('id', 'actor', 'action', 'entity_type', 'entity_id',
                       'before_summary', 'after_summary', 'ip_address', 'created_at')
    search_fields = ('action', 'entity_id')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CashAccount)
class CashAccountAdmin(ConsultationSeule):
    list_display = ('name', 'kind', 'currency', 'opening_balance',
                    'solde', 'status_label', 'updated_at')
    list_filter = ('kind', 'active')
    search_fields = ('name', 'description')
    ordering = ('name',)

    @admin.display(description=_('Solde calculé'))
    def solde(self, obj):
        return f'{obj.balance:,}'.replace(',', ' ')


@admin.register(TransactionCategory)
class TransactionCategoryAdmin(ConsultationSeule):
    list_display = ('name', 'direction', 'active', 'ecritures')
    list_filter = ('direction', 'active')
    search_fields = ('name',)

    @admin.display(description=_('Écritures classées'))
    def ecritures(self, obj):
        return obj.transactions.count()


@admin.register(CashTransaction)
class CashTransactionAdmin(ConsultationSeule):
    list_display = ('reference', 'occurred_at', 'tx_type', 'nature', 'label',
                    'amount', 'account', 'status', 'created_by')
    list_filter = ('tx_type', 'status', 'nature', 'account')
    search_fields = ('reference', 'label', 'counterparty')
    ordering = ('-occurred_at',)
    date_hierarchy = 'occurred_at'
    list_select_related = ('account', 'category', 'created_by')


@admin.register(CashClosure)
class CashClosureAdmin(ConsultationSeule):
    list_display = ('account', 'date', 'counted_amount', 'theoretical_balance',
                    'difference', 'closed_by')
    list_filter = ('account',)
    ordering = ('-date',)
    list_select_related = ('account', 'closed_by')


@admin.register(AcademicYear)
class AcademicYearAdmin(ConsultationSeule):
    """Calendrier consultable ici : la direction pose les dates au tableau de bord.

    Écrire l'année depuis cet écran passerait devant l'audit et laisserait deux
    années cochées « en cours » : le geste garde sa porte unique, le réglage du
    calendrier académique.
    """
    list_display = ('label', 'start_date', 'end_date', 'is_current')
    list_filter = ('is_current',)
    search_fields = ('label',)
    ordering = ('-start_date',)


@admin.register(Attendance)
class AttendanceAdmin(ConsultationSeule):
    list_display = ('enrollment', 'date', 'status', 'recorded_by')
    list_filter = ('status',)
    search_fields = ('enrollment__student__last_name',)
    ordering = ('-date',)


@admin.register(Expense)
class ExpenseAdmin(ConsultationSeule):
    list_display = ('category', 'amount', 'currency', 'occurred_at', 'status')
    list_filter = ('status',)
    ordering = ('-occurred_at',)


@admin.register(Certificate)
class CertificateAdmin(ConsultationSeule):
    list_display = ('certificate_number', 'enrollment', 'status', 'issued_at')
    list_filter = ('status',)
    search_fields = ('certificate_number',)


@admin.register(PlatformSetting)
class PlatformSettingAdmin(ConsultationSeule):
    """Réglages consultés ici : la direction les écrit à l'écran des réglages.

    Le nom et les coordonnées signent documents et écrans ; les modifier ici se
    ferait sans motif et sans la ligne d'audit que l'écran de réglages laisse.
    """
    list_display = ('nom', 'telephone', 'email', 'devise', 'seuil_alerte',
                    'mise_a_jour_le')


admin.site.register(UserRole)
admin.site.register(RolePermission)
admin.site.register(AccessRequest)
admin.site.register(ScholarshipDocument)
admin.site.register(AccessEvent)
admin.site.register(Notification)
admin.site.register(ResourceFeedback)
