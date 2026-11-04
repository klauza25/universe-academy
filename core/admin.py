from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import (
    User, Role, Permission, UserRole, RolePermission,
    AccessRequest, Course, CourseSession, Enrollment,
    Attendance, Payment, Expense,
    ScholarshipApplication, ScholarshipDocument, Destination,
    AccessEvent, Notification, AuditLog, Certificate, ResourceFeedback,
    CashAccount, CashClosure, CashTransaction, TransactionCategory,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'internal_code', 'get_full_name', 'account_status', 'date_joined')
    list_filter = ('account_status', 'roles')
    search_fields = ('email', 'first_name', 'last_name', 'internal_code', 'clerk_user_id')
    ordering = ('-date_joined',)
    readonly_fields = ('internal_code',)
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Univers Academy', {
            'fields': ('internal_code', 'account_status', 'phone', 'address',
                       'birth_date', 'clerk_user_id')
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
    list_display = ('title', 'domain', 'fee_amount', 'duration_months', 'active')
    list_filter = ('domain', 'active')


@admin.register(CourseSession)
class CourseSessionAdmin(admin.ModelAdmin):
    list_display = ('course', 'starts_at', 'ends_at', 'status', 'capacity')
    list_filter = ('status',)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'session', 'status', 'enrolled_at')
    list_filter = ('status',)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('reference', 'amount', 'currency', 'method', 'status', 'paid_at')
    list_filter = ('status', 'method')
    search_fields = ('reference',)


@admin.register(ScholarshipApplication)
class ScholarshipApplicationAdmin(admin.ModelAdmin):
    list_display = ('reference', 'last_name', 'first_name', 'destination', 'status', 'submitted_at')
    list_filter = ('status', 'destination')
    search_fields = ('reference', 'last_name', 'email')


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


class ConsultationSeule(admin.ModelAdmin):
    """Modèle financier consultable ici, mais écrit au tableau de bord.

    Une écriture de caisse se pose, se corrige et s'annule par le service
    d'écriture : c'est lui qui garde le solde, exige un motif et laisse sa
    ligne d'audit. Ouvrir une seconde porte d'écriture reviendrait à pouvoir
    déplacer un solde en silence.
    """

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


admin.site.register(UserRole)
admin.site.register(RolePermission)
admin.site.register(AccessRequest)
admin.site.register(ScholarshipDocument)
admin.site.register(Attendance)
admin.site.register(Expense)
admin.site.register(AccessEvent)
admin.site.register(Notification)
admin.site.register(Certificate)
admin.site.register(ResourceFeedback)
