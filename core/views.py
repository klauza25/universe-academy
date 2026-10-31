import logging

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden, FileResponse, Http404
from django.db.models import (
    Q, Sum, Count, F, Case, When, IntegerField, OuterRef, Subquery,
)
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    User, Role, UserRole, AccessRequest, AccountStatus,
    ScholarshipApplication, ScholarshipDocument, Destination,
    Course, CourseSession, Enrollment, Attendance, Payment,
    AccessEvent, Notification, AuditLog, Certificate,
    ROLE_DASHBOARD_ROUTES, PRIVILEGED_ROLES, RoleKey,
    REQUESTABLE_ROLES, REQUESTABLE_ROLE_CHOICES,
    Visit, Prospect, ProspectFollowUp, Contact,
    Module, Lesson, SessionRecord, Resource, StudentDocument,
    CashAccount, CashTransaction, CashClosure, TransactionCategory,
)
from .forms import (
    LoginForm, RegisterForm, UserCreateForm, UserEditForm,
    AccessRequestCompletionForm,
    ScholarshipApplicationForm, ScholarshipDocumentForm,
    AccessEventForm
)
from .decorators import (
    active_account_required, business_write_required, permission_required,
    role_required, super_admin_required,
)
from .utils import log_audit, outstanding_receivables
from .clerk import ClerkError, sync_clerk_user, verify_clerk_token

logger = logging.getLogger(__name__)


def home(request):
    if request.user.is_authenticated and request.user.is_active_account:
        return redirect('core:dashboard:dashboard-router')
    return render(request, 'public/home.html')


def login_view(request):
    form = LoginForm()
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            identifier = form.cleaned_data['identifier']
            password = form.cleaned_data['password']

            user = None
            try:
                user_obj = User.objects.get(
                    Q(email__iexact=identifier) | Q(internal_code__iexact=identifier)
                )
                user = authenticate(request, username=user_obj.email, password=password)
            except User.DoesNotExist:
                pass

            if user is not None:
                login(request, user)
                log_audit(request, 'LOGIN', 'User', str(user.id))

                if user.account_status == AccountStatus.PENDING_APPROVAL:
                    if user.needs_access_request:
                        return redirect('core:complete-access-request')
                    return redirect('core:pending-approval')
                elif user.account_status != AccountStatus.ACTIVE:
                    logout(request)
                    messages.error(request, "Votre compte est désactivé ou suspendu.")
                    return redirect('core:login')

                return redirect('core:dashboard:dashboard-router')
            else:
                messages.error(request, "Identifiant ou mot de passe incorrect.")

    return render(request, 'public/login.html', {'form': form})


@require_POST
def clerk_session(request):
    """Exchange a verified Clerk session token for a Django session.

    The browser posts the JWT returned by Clerk JS in a CSRF-protected form.
    The token is verified server-side before any local account is touched.
    """
    if not settings.CLERK_ENABLED:
        return redirect('core:login')

    token = (request.POST.get('token') or '').strip()
    if not token:
        messages.error(request, "Connexion Clerk impossible : jeton manquant.")
        return redirect('/login/?clerk_error=1')

    try:
        payload = verify_clerk_token(token)
        user, created = sync_clerk_user(payload)
    except ClerkError as exc:
        messages.error(request, str(exc))
        return redirect('/login/?clerk_error=1')
    except Exception:
        logger.exception("Clerk authentication failed")
        messages.error(request, "Connexion Clerk impossible. Veuillez reessayer.")
        return redirect('/login/?clerk_error=1')

    if not user.is_active:
        messages.error(
            request, "Votre compte est desactive. Contactez l'administration."
        )
        return redirect('/login/?clerk_error=1')

    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    log_audit(
        request,
        'REGISTER_CLERK' if created else 'LOGIN_CLERK',
        'User',
        str(user.id),
        after={'email': user.email, 'clerk_user_id': user.clerk_user_id},
    )

    if user.account_status == AccountStatus.PENDING_APPROVAL:
        if user.needs_access_request:
            return redirect('core:complete-access-request')
        return redirect('core:pending-approval')

    if user.account_status != AccountStatus.ACTIVE:
        logout(request)
        messages.error(request, "Votre compte est desactive ou suspendu.")
        return redirect('/login/?clerk_error=1')

    return redirect('core:dashboard:dashboard-router')


def logout_view(request):
    if request.method != 'POST':
        return redirect('core:home')
    if request.user.is_authenticated:
        log_audit(request, 'LOGOUT', 'User', str(request.user.id))
    logout(request)
    if settings.CLERK_ENABLED:
        # The Clerk browser session must be closed too, otherwise the login
        # page would silently sign the user straight back in.
        return redirect('/login/?clerk_signed_out=1')
    return redirect('core:home')


def register_view(request):
    form = RegisterForm()
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.username = form.cleaned_data['email']
            user.account_status = AccountStatus.PENDING_APPROVAL
            user.set_password(form.cleaned_data['password'])
            user.save()

            # Le rôle choisi est une demande, jamais un rôle effectif.
            AccessRequest.objects.create(
                user=user,
                requested_role=form.cleaned_data['requested_role'],
            )

            log_audit(
                request, 'REGISTER', 'User', str(user.id),
                after={'requested_role': form.cleaned_data['requested_role']},
            )
            login(request, user)
            return redirect('core:pending-approval')

    return render(request, 'public/register.html', {
        'form': form,
        'login_form': LoginForm(auto_id='login_%s'),
    })


@login_required
def pending_approval(request):
    user = request.user
    if user.account_status != AccountStatus.PENDING_APPROVAL:
        if user.account_status == AccountStatus.ACTIVE:
            return redirect(user.dashboard_route)
        return redirect('core:access-denied')
    if user.needs_access_request:
        return redirect('core:complete-access-request')
    return render(request, 'public/pending_approval.html', {
        'access_request': user.pending_access_request,
    })


@login_required
def complete_access_request(request):
    """Complète la demande d'accès d'un compte en attente (notamment Clerk).

    Aucun rôle n'est attribué ici : le choix reste une demande soumise à la
    décision du super administrateur.
    """
    user = request.user
    if user.account_status != AccountStatus.PENDING_APPROVAL:
        if user.account_status == AccountStatus.ACTIVE:
            return redirect(user.dashboard_route)
        return redirect('core:access-denied')

    pending = user.pending_access_request
    form = AccessRequestCompletionForm(
        instance=user,
        initial={'requested_role': pending.requested_role if pending else ''},
    )
    if request.method == 'POST':
        form = AccessRequestCompletionForm(request.POST, instance=user)
        if form.is_valid():
            user = form.save()
            access_request = pending or AccessRequest.objects.create(user=user)
            access_request.requested_role = form.cleaned_data['requested_role']
            access_request.status = AccessRequest.Status.PENDING
            access_request.save(update_fields=['requested_role', 'status'])
            log_audit(
                request, 'ACCESS_REQUEST_SUBMIT', 'AccessRequest',
                str(access_request.id),
                after={
                    'user': str(user.id),
                    'requested_role': access_request.requested_role,
                },
            )
            messages.success(request, "Votre demande d'accès a été enregistrée.")
            return redirect('core:pending-approval')

    return render(request, 'public/access_request.html', {'form': form})


def access_denied(request):
    return render(request, 'public/access_denied.html')


def scholarship_apply(request):
    app_form = ScholarshipApplicationForm()
    doc_form = ScholarshipDocumentForm()

    if request.method == 'POST':
        app_form = ScholarshipApplicationForm(request.POST)
        doc_form = ScholarshipDocumentForm(request.POST, request.FILES)

        if app_form.is_valid() and doc_form.is_valid():
            application = app_form.save()

            doc_mapping = {
                'identity_doc': ScholarshipDocument.DocType.IDENTITY,
                'diplomas': ScholarshipDocument.DocType.DIPLOMA,
                'transcripts': ScholarshipDocument.DocType.TRANSCRIPT,
                'photo': ScholarshipDocument.DocType.PHOTO,
                'motivation_letter': ScholarshipDocument.DocType.MOTIVATION,
            }

            for field_name, doc_type in doc_mapping.items():
                file = request.FILES.get(field_name)
                if file:
                    if file.size > 10 * 1024 * 1024:
                        messages.error(request, f"Le fichier {file.name} est trop volumineux (max 10 Mo).")
                        continue

                    ScholarshipDocument.objects.create(
                        application=application,
                        document_type=doc_type,
                        file=file,
                        original_name=file.name,
                        mime_type=getattr(file, 'content_type', 'application/octet-stream'),
                        size_bytes=file.size,
                    )

            log_audit(
                request, 'SCHOLARSHIP_SUBMIT', 'ScholarshipApplication',
                str(application.id),
                after={'reference': application.reference, 'email': application.email}
            )

            return redirect('core:bourses:scholarship-confirmation', reference=application.reference)

    return render(request, 'bourses/candidature.html', {
        'app_form': app_form,
        'doc_form': doc_form,
    })


def scholarship_confirmation(request, reference):
    application = get_object_or_404(ScholarshipApplication, reference=reference)
    return render(request, 'bourses/confirmation.html', {
        'application': application,
    })


def scholarship_tracking(request):
    application = None
    if request.method == 'POST':
        ref = request.POST.get('reference', '').strip()
        token = request.POST.get('token', '').strip()
        try:
            application = ScholarshipApplication.objects.get(
                reference=ref, tracking_token=token
            )
        except (ScholarshipApplication.DoesNotExist, ValueError):
            messages.error(request, "Aucune candidature trouvée avec ces informations.")

    return render(request, 'bourses/suivi.html', {'application': application})


@login_required
@active_account_required
def dashboard_router(request):
    route = request.user.dashboard_route
    return redirect(route)


@role_required('SUPER_ADMIN')
def super_admin_dashboard(request):
    from .views_comptabilite import accounts_with_balance

    today = timezone.localdate()
    month_start = today.replace(day=1)
    month_transactions = CashTransaction.objects.filter(
        status=CashTransaction.Status.VALIDATED,
        occurred_at__date__gte=month_start,
        occurred_at__date__lte=today,
    )
    salaries_categories = (
        'Salaires', 'Paiements des formateurs', 'Avances sur salaire',
    )
    month_income = month_transactions.filter(
        tx_type=CashTransaction.Type.IN
    ).aggregate(total=Sum('amount'))['total'] or 0
    month_expense = month_transactions.filter(
        tx_type=CashTransaction.Type.OUT
    ).aggregate(total=Sum('amount'))['total'] or 0
    month_salaries = month_transactions.filter(
        tx_type=CashTransaction.Type.OUT,
        category__name__in=salaries_categories,
    ).aggregate(total=Sum('amount'))['total'] or 0

    paid_per_enrollment = Payment.objects.filter(
        enrollment=OuterRef('pk'),
        status=Payment.Status.COMPLETED,
    ).values('enrollment').annotate(total=Sum('amount')).values('total')
    incomplete_enrollments = Enrollment.objects.filter(
        status=Enrollment.Status.ACTIVE
    ).annotate(
        paid_total=Coalesce(
            Subquery(paid_per_enrollment, output_field=IntegerField()), 0
        )
    ).filter(net_amount__gt=F('paid_total')).count()

    cash_rows = accounts_with_balance()

    context = {
        'total_users': User.objects.count(),
        'pending_requests': AccessRequest.objects.filter(
            status=AccessRequest.Status.PENDING
        ).count(),
        'active_students': User.objects.filter(
            roles__key='ETUDIANT', account_status=AccountStatus.ACTIVE
        ).count(),
        'scholarship_pending': ScholarshipApplication.objects.filter(
            status=ScholarshipApplication.Status.SUBMITTED
        ).count(),
        'recent_audit': AuditLog.objects.select_related('actor')[:10],
        'recent_access_requests': AccessRequest.objects.select_related(
            'user'
        ).filter(status=AccessRequest.Status.PENDING)[:5],
        'recent_scholarships': ScholarshipApplication.objects.select_related(
            'destination'
        ).order_by('-submitted_at')[:5],
        # Contrôle financier global.
        'today': today,
        'month_start': month_start,
        'month_income': month_income,
        'month_expense': month_expense,
        'month_salaries': month_salaries,
        'month_payment_total': Payment.objects.filter(
            status=Payment.Status.COMPLETED,
            paid_at__date__gte=month_start,
            paid_at__date__lte=today,
        ).aggregate(total=Sum('amount'))['total'] or 0,
        'month_transaction_count': month_transactions.count(),
        'pending_transactions': CashTransaction.objects.filter(
            status=CashTransaction.Status.DRAFT
        ).count(),
        'cash_rows': cash_rows,
        'cash_total': sum(row['balance'] for row in cash_rows),
        'outstanding_amount': outstanding_receivables(),
        'incomplete_enrollments': incomplete_enrollments,
        'closure_gap_count': CashClosure.objects.exclude(
            difference=0
        ).count(),
        'recent_transactions': CashTransaction.objects.select_related(
            'account', 'category', 'created_by'
        ).order_by('-occurred_at', '-created_at')[:8],
    }
    return render(request, 'dashboard/super_admin/index.html', context)


@role_required('SUPER_ADMIN', 'ADMIN')
def user_list(request):
    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    role_filter = request.GET.get('role', '')

    users = User.objects.prefetch_related('roles').all()

    if query:
        users = users.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query) |
            Q(internal_code__icontains=query)
        )
    if status_filter:
        users = users.filter(account_status=status_filter)
    if role_filter:
        users = users.filter(roles__key=role_filter)

    paginator = Paginator(users.distinct(), 20)
    page = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'dashboard/super_admin/users.html', {
        'page': page,
        'query': query,
        'status_filter': status_filter,
        'role_filter': role_filter,
        'status_choices': AccountStatus.choices,
        'role_choices': RoleKey.choices,
    })


@super_admin_required
def user_create(request):
    form = UserCreateForm()
    if request.method == 'POST':
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.username = form.cleaned_data['email']
            user.account_status = AccountStatus.ACTIVE
            role_key = form.cleaned_data['role']
            user.generate_internal_code(role_key)

            password = form.cleaned_data.get('password')
            if password:
                user.set_password(password)
            else:
                user.set_unusable_password()
            user.save()

            role = Role.objects.get(key=role_key)
            UserRole.objects.create(
                user=user, role=role, assigned_by=request.user
            )

            log_audit(
                request, 'USER_CREATE', 'User', str(user.id),
                after={
                    'email': user.email,
                    'role': role_key,
                    'code': user.internal_code
                }
            )

            messages.success(request, f"Utilisateur {user.get_full_name()} créé avec succès.")
            return redirect('core:dashboard:user-list')

    return render(request, 'dashboard/super_admin/user_form.html', {'form': form})


def _is_last_active_super_admin(user):
    """Vrai si ``user`` est le dernier SUPER_ADMIN encore actif.

    Protège la plateforme d'un verrouillage : on refuse de retirer le rôle ou
    de suspendre le dernier super administrateur actif.
    """
    if not user.has_role(RoleKey.SUPER_ADMIN):
        return False
    if user.account_status != AccountStatus.ACTIVE:
        return False
    return not User.objects.filter(
        roles__key=RoleKey.SUPER_ADMIN,
        account_status=AccountStatus.ACTIVE,
    ).exclude(id=user.id).exists()


@role_required('SUPER_ADMIN', 'ADMIN')
def user_detail(request, user_id):
    user = get_object_or_404(User, id=user_id)
    audit = AuditLog.objects.filter(
        entity_type='User', entity_id=str(user_id)
    )[:20]
    held_keys = list(user.roles.values_list('key', flat=True))
    is_self = request.user.id == user.id
    can_manage = request.user.has_role(RoleKey.SUPER_ADMIN) and not is_self

    return render(request, 'dashboard/super_admin/user_detail.html', {
        'profile_user': user,
        'audit_entries': audit,
        'held_role_keys': held_keys,
        'available_roles': (
            Role.objects.exclude(key__in=held_keys).order_by('label')
            if can_manage else Role.objects.none()
        ),
        'status_choices': AccountStatus.choices,
        'can_manage_access': can_manage,
        'is_self': is_self,
    })


@super_admin_required
def user_edit(request, user_id):
    user = get_object_or_404(User, id=user_id)
    before = {
        'status': user.account_status,
        'email': user.email,
    }

    form = UserEditForm(instance=user)
    if request.method == 'POST':
        form = UserEditForm(request.POST, instance=user)
        if form.is_valid():
            updated_user = form.save(commit=False)
            if (updated_user.account_status == AccountStatus.SUSPENDED and
                    before['status'] != AccountStatus.SUSPENDED):
                updated_user.disabled_at = timezone.now()
            elif (updated_user.account_status == AccountStatus.DISABLED and
                  before['status'] != AccountStatus.DISABLED):
                updated_user.disabled_at = timezone.now()
            elif (updated_user.account_status == AccountStatus.ACTIVE and
                  updated_user.disabled_at is not None):
                updated_user.disabled_at = None
            updated_user.save()

            log_audit(
                request, 'USER_EDIT', 'User', str(user.id),
                before=before,
                after={
                    'status': updated_user.account_status,
                    'email': updated_user.email,
                }
            )
            messages.success(request, "Utilisateur modifié.")
            return redirect('core:dashboard:user-detail', user_id=user.id)

    return render(request, 'dashboard/super_admin/user_form.html', {
        'form': form, 'editing': True, 'profile_user': user
    })


@super_admin_required
def user_role_assign(request, user_id):
    redirect_to_detail = redirect(
        'core:dashboard:user-detail', user_id=user_id)
    if request.method != 'POST':
        return redirect_to_detail

    user = get_object_or_404(User, id=user_id)
    if user.id == request.user.id:
        return HttpResponseForbidden(
            "Vous ne pouvez pas modifier vos propres rôles."
        )

    role_key = request.POST.get('role_key')
    action = request.POST.get('action', 'add')
    if action not in {'add', 'remove'}:
        messages.error(request, "Action sur le rôle inconnue.")
        return redirect_to_detail

    role = Role.objects.filter(key=role_key).first()
    if role is None:
        messages.error(request, "Rôle inconnu.")
        return redirect_to_detail

    if role.is_privileged and not request.user.has_role('SUPER_ADMIN'):
        return HttpResponseForbidden("Impossible d'attribuer un rôle privilégié.")

    if action == 'add':
        _, created = UserRole.objects.get_or_create(
            user=user, role=role, defaults={'assigned_by': request.user}
        )
        if created:
            log_audit(
                request, 'ROLE_ASSIGN', 'User', str(user.id),
                after={'role': role_key}
            )
            messages.success(request, f"Rôle {role.label} ajouté.")
        else:
            messages.info(request, f"Le rôle {role.label} est déjà attribué.")
    else:
        if (role.key == RoleKey.SUPER_ADMIN and
                _is_last_active_super_admin(user)):
            messages.error(
                request,
                "Impossible de retirer le rôle SUPER_ADMIN au dernier "
                "super administrateur actif."
            )
            return redirect_to_detail
        removed, _ = UserRole.objects.filter(user=user, role=role).delete()
        if removed:
            log_audit(
                request, 'ROLE_REMOVE', 'User', str(user.id),
                after={'role': role_key}
            )
            messages.success(request, f"Rôle {role.label} retiré.")
        else:
            messages.info(request, f"Le rôle {role.label} n'était pas attribué.")

    return redirect_to_detail


@super_admin_required
def user_status_change(request, user_id):
    """Change le statut d'accès d'un compte depuis sa fiche (POST uniquement)."""
    redirect_to_detail = redirect(
        'core:dashboard:user-detail', user_id=user_id)
    if request.method != 'POST':
        return redirect_to_detail

    user = get_object_or_404(User, id=user_id)
    if user.id == request.user.id:
        return HttpResponseForbidden(
            "Vous ne pouvez pas modifier le statut de votre propre compte."
        )

    status = request.POST.get('account_status')
    valid_statuses = {choice for choice, _ in AccountStatus.choices}
    if status not in valid_statuses:
        messages.error(request, "Statut de compte invalide.")
        return redirect_to_detail

    before = user.account_status
    if before == status:
        messages.info(request, "Le compte a déjà ce statut.")
        return redirect_to_detail

    if status != AccountStatus.ACTIVE and _is_last_active_super_admin(user):
        messages.error(
            request,
            "Impossible de désactiver le dernier super administrateur actif."
        )
        return redirect_to_detail

    user.account_status = status
    if status == AccountStatus.ACTIVE:
        user.disabled_at = None
    else:
        user.disabled_at = timezone.now()
    user.save(update_fields=['account_status', 'disabled_at'])

    log_audit(
        request, 'USER_STATUS_CHANGE', 'User', str(user.id),
        before={'status': before}, after={'status': status},
    )
    messages.success(
        request,
        f"Statut du compte passé à « {user.get_account_status_display()} »."
    )
    return redirect_to_detail


@role_required('SUPER_ADMIN')
def access_requests_list(request):
    status_filter = request.GET.get('statut', 'all')
    if status_filter not in {'all', 'PENDING', 'APPROVED', 'REJECTED'}:
        status_filter = 'all'

    requests_qs = AccessRequest.objects.select_related('user', 'reviewed_by')
    if status_filter != 'all':
        requests_qs = requests_qs.filter(status=status_filter)
    requests_qs = requests_qs.annotate(
        pending_first=Case(
            When(status=AccessRequest.Status.PENDING, then=0),
            default=1,
            output_field=IntegerField(),
        )
    ).order_by('pending_first', '-created_at')

    return render(request, 'dashboard/super_admin/access_requests.html', {
        'requests': requests_qs,
        'role_choices': REQUESTABLE_ROLE_CHOICES,
        'status_filter': status_filter,
        'pending_count': AccessRequest.objects.filter(
            status=AccessRequest.Status.PENDING
        ).count(),
        'total_count': AccessRequest.objects.count(),
    })


@role_required('SUPER_ADMIN', 'ADMIN')
def access_request_review(request, request_id):
    ar = get_object_or_404(
        AccessRequest.objects.select_related('user'), id=request_id
    )

    if request.method != 'POST':
        return redirect('core:dashboard:access-requests')

    decision = request.POST.get('decision')
    role_key = (request.POST.get('role_key') or '').strip()
    note = (request.POST.get('note') or '').strip()

    if ar.status != AccessRequest.Status.PENDING:
        messages.error(request, "Cette demande a déjà été traitée.")
        return redirect('core:dashboard:access-requests')

    if ar.user_id == request.user.id:
        return HttpResponseForbidden(
            "Vous ne pouvez pas traiter votre propre demande d'accès."
        )

    before = {
        'request_status': ar.status,
        'assigned_role': ar.assigned_role,
        'account_status': ar.user.account_status,
    }
    ar.reviewed_by = request.user
    ar.reviewed_at = timezone.now()
    ar.decision_note = note

    if decision == 'approve':
        # Seuls les rôles demandables sont attribuables ici. Les rôles
        # d'administration passent par l'écran « Utilisateurs ».
        if role_key not in REQUESTABLE_ROLES:
            messages.error(
                request,
                "Rôle invalide : choisissez le rôle à attribuer dans la liste.",
            )
            return redirect('core:dashboard:access-requests')

        role = get_object_or_404(Role, key=role_key)
        ar.status = AccessRequest.Status.APPROVED
        ar.assigned_role = role_key
        ar.user.account_status = AccountStatus.ACTIVE
        ar.user.generate_internal_code(role_key)
        ar.user.save()
        UserRole.objects.get_or_create(
            user=ar.user, role=role, defaults={'assigned_by': request.user}
        )

        Notification.objects.create(
            user=ar.user,
            title="Compte approuvé",
            message=(
                f"Votre compte a été approuvé avec le rôle "
                f"{role.label}. Votre code : {ar.user.internal_code}"
            ),
            notification_type=Notification.Type.ACCOUNT_APPROVED,
        )

        log_audit(
            request, 'ACCESS_APPROVE', 'AccessRequest', str(ar.id),
            before=before,
            after={
                'request_status': ar.status,
                'requested_role': ar.requested_role,
                'assigned_role': role_key,
                'account_status': ar.user.account_status,
                'reviewed_by': str(request.user.id),
            },
        )
        messages.success(request, f"Compte de {ar.user.get_full_name()} approuvé.")

    elif decision == 'reject':
        ar.status = AccessRequest.Status.REJECTED
        ar.assigned_role = ''
        ar.user.account_status = AccountStatus.REJECTED
        ar.user.save()

        Notification.objects.create(
            user=ar.user,
            title="Demande refusée",
            message="Votre demande d'accès a été refusée.",
            notification_type=Notification.Type.ACCOUNT_REJECTED,
        )

        log_audit(
            request, 'ACCESS_REJECT', 'AccessRequest', str(ar.id),
            before=before,
            after={
                'request_status': ar.status,
                'assigned_role': '',
                'account_status': ar.user.account_status,
                'reviewed_by': str(request.user.id),
                'note': note,
            },
        )
        messages.info(request, "Demande refusée.")

    else:
        messages.error(request, "Décision invalide.")
        return redirect('core:dashboard:access-requests')

    ar.save()
    return redirect('core:dashboard:access-requests')


@role_required('SUPER_ADMIN')
def audit_log_view(request):
    entries = AuditLog.objects.select_related('actor').prefetch_related(
        'actor__roles'
    )
    query = (request.GET.get('q') or '').strip()
    action_filter = request.GET.get('action') or ''
    entity_filter = request.GET.get('entity') or ''
    actor_filter = request.GET.get('actor') or ''
    date_from = request.GET.get('from') or ''
    date_to = request.GET.get('to') or ''

    if query:
        entries = entries.filter(
            Q(action__icontains=query) |
            Q(entity_type__icontains=query) |
            Q(entity_id__icontains=query) |
            Q(actor__email__icontains=query) |
            Q(actor__first_name__icontains=query) |
            Q(actor__last_name__icontains=query)
        )
    if action_filter:
        entries = entries.filter(action=action_filter)
    if entity_filter:
        entries = entries.filter(entity_type=entity_filter)
    if actor_filter:
        entries = entries.filter(actor_id=actor_filter)
    if date_from:
        entries = entries.filter(created_at__date__gte=date_from)
    if date_to:
        entries = entries.filter(created_at__date__lte=date_to)

    paginator = Paginator(entries, 50)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'dashboard/super_admin/audit_log.html', {
        'page': page,
        'query': query,
        'action_filter': action_filter,
        'entity_filter': entity_filter,
        'actor_filter': actor_filter,
        'date_from': date_from,
        'date_to': date_to,
        'actions': AuditLog.objects.values_list(
            'action', flat=True
        ).distinct().order_by('action'),
        'entities': AuditLog.objects.values_list(
            'entity_type', flat=True
        ).distinct().order_by('entity_type'),
        'actors': User.objects.filter(
            audit_actions__isnull=False
        ).distinct().order_by('last_name', 'first_name'),
    })


@role_required('SUPER_ADMIN', 'ADMIN')
def scholarship_review_list(request):
    apps = ScholarshipApplication.objects.select_related('destination').all()
    status_filter = request.GET.get('status', '')
    if status_filter:
        apps = apps.filter(status=status_filter)
    paginator = Paginator(apps, 20)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'dashboard/super_admin/scholarship_review.html', {
        'page': page,
        'status_choices': ScholarshipApplication.Status.choices,
    })


@role_required('SUPER_ADMIN', 'ADMIN')
def scholarship_review_detail(request, app_id):
    app = get_object_or_404(
        ScholarshipApplication.objects.select_related('destination'),
        id=app_id
    )
    documents = app.documents.all()

    if request.method == 'POST':
        if not request.user.has_role('SUPER_ADMIN'):
            return HttpResponseForbidden(
                "La décision de bourse est réservée au super administrateur."
            )
        new_status = request.POST.get('status')
        note = request.POST.get('review_note', '')

        before = {'status': app.status}
        app.status = new_status
        app.reviewed_by = request.user
        app.reviewed_at = timezone.now()
        app.review_note = note
        app.save()

        log_audit(
            request, 'SCHOLARSHIP_REVIEW', 'ScholarshipApplication',
            str(app.id), before=before, after={'status': new_status}
        )
        messages.success(request, f"Statut mis à jour : {app.get_status_display()}")
        return redirect('core:dashboard:scholarship-review-list')

    return render(request, 'dashboard/super_admin/scholarship_review.html', {
        'app': app,
        'documents': documents,
        'status_choices': ScholarshipApplication.Status.choices,
        'detail': True,
    })


@role_required('ADMIN')
def admin_dashboard(request):
    today = timezone.localdate()
    month_start = today.replace(day=1)
    from .views_comptabilite import accounts_with_balance

    month_transactions = CashTransaction.objects.filter(
        status=CashTransaction.Status.VALIDATED,
        occurred_at__date__gte=month_start,
    )
    cash_rows = accounts_with_balance()

    context = {
        'active_students': User.objects.filter(
            roles__key='ETUDIANT', account_status=AccountStatus.ACTIVE
        ).count(),
        'pending_requests': AccessRequest.objects.filter(
            status=AccessRequest.Status.PENDING
        ).count(),
        'pending_access_requests': AccessRequest.objects.select_related(
            'user'
        ).filter(status=AccessRequest.Status.PENDING)[:5],
        'total_trainers': User.objects.filter(
            roles__key='FORMATEUR', account_status=AccountStatus.ACTIVE
        ).count(),
        'active_courses': Course.objects.filter(active=True).count(),
        'recent_users': User.objects.prefetch_related('roles').order_by(
            '-date_joined'
        )[:6],
        'month_income': month_transactions.filter(
            tx_type=CashTransaction.Type.IN
        ).aggregate(total=Sum('amount'))['total'] or 0,
        'month_expense': month_transactions.filter(
            tx_type=CashTransaction.Type.OUT
        ).aggregate(total=Sum('amount'))['total'] or 0,
        'cash_rows': cash_rows,
        'cash_total': sum(row['balance'] for row in cash_rows),
        'outstanding_amount': outstanding_receivables(),
        'new_enrollments': Enrollment.objects.filter(
            enrolled_at__date__gte=month_start
        ).count(),
    }
    return render(request, 'dashboard/admin/index.html', context)


@role_required('DIRECTION')
def direction_dashboard(request):
    today = timezone.localdate()
    month_start = today.replace(day=1)
    period = request.GET.get('period') or 'month'
    date_from = request.GET.get('from') or ''
    date_to = request.GET.get('to') or ''

    payments = Payment.objects.filter(status=Payment.Status.COMPLETED)
    transactions = CashTransaction.objects.filter(
        status=CashTransaction.Status.VALIDATED
    )
    if period == 'day':
        payments = payments.filter(paid_at__date=today)
        transactions = transactions.filter(occurred_at__date=today)
    elif period == 'week':
        from datetime import timedelta
        start = today - timedelta(days=7)
        payments = payments.filter(paid_at__date__gte=start)
        transactions = transactions.filter(occurred_at__date__gte=start)
    elif period == 'year':
        payments = payments.filter(paid_at__year=today.year)
        transactions = transactions.filter(occurred_at__year=today.year)
    elif period == 'custom' and date_from and date_to:
        payments = payments.filter(paid_at__date__gte=date_from,
                                   paid_at__date__lte=date_to)
        transactions = transactions.filter(
            occurred_at__date__gte=date_from,
            occurred_at__date__lte=date_to,
        )
    else:
        payments = payments.filter(paid_at__date__gte=month_start)
        transactions = transactions.filter(occurred_at__date__gte=month_start)

    from .views_comptabilite import accounts_with_balance

    context = {
        'period': period,
        'date_from': date_from,
        'date_to': date_to,
        'total_revenue': transactions.filter(
            tx_type=CashTransaction.Type.IN
        ).aggregate(total=Sum('amount'))['total'] or 0,
        'total_students': User.objects.filter(
            roles__key='ETUDIANT', account_status=AccountStatus.ACTIVE
        ).count(),
        'active_sessions': CourseSession.objects.filter(
            status=CourseSession.Status.ACTIVE
        ).count(),
        'new_enrollments': Enrollment.objects.filter(
            enrolled_at__date__gte=month_start
        ).count(),
        'recent_payments': payments.select_related(
            'enrollment__student'
        ).order_by('-paid_at')[:8],
        'visits_count': Visit.objects.filter(
            arrival_at__date__gte=month_start
        ).count(),
        'prospects_count': Prospect.objects.count(),
        'converted_count': Prospect.objects.filter(
            converted_student__isnull=False
        ).count(),
        'total_expenses': transactions.filter(
            tx_type=CashTransaction.Type.OUT
        ).aggregate(total=Sum('amount'))['total'] or 0,
        'cash_rows': accounts_with_balance(),
        'recent_transactions': transactions.select_related(
            'account', 'category'
        ).order_by('-occurred_at')[:8],
        'students_by_session': CourseSession.objects.filter(
            status=CourseSession.Status.ACTIVE
        ).annotate(effectif=Count('enrollments')).select_related('course')[:8],
        'attendance_stats': Attendance.objects.filter(
            date__gte=month_start
        ).aggregate(
            total=Count('id'),
            presents=Count('id', filter=Q(status='PRESENT')),
            absents=Count('id', filter=Q(status='ABSENT')),
        ),
        'records_stats': SessionRecord.objects.filter(
            date__gte=month_start
        ).aggregate(
            total=Count('id'),
            completed=Count('id', filter=Q(status='COMPLETED')),
        ),
    }
    return render(request, 'dashboard/direction/index.html', context)


@role_required('SECRETAIRE')
def secretaire_dashboard(request):
    context = {
        'pending_enrollments': Enrollment.objects.filter(
            status=Enrollment.Status.PENDING
        ).count(),
        'recent_enrollments': Enrollment.objects.select_related(
            'student', 'session__course'
        ).order_by('-enrolled_at')[:10],
        'total_enrollments': Enrollment.objects.count(),
        'total_students': User.objects.filter(
            roles__key='ETUDIANT'
        ).distinct().count(),
        'active_students': User.objects.filter(
            roles__key='ETUDIANT',
            account_status=AccountStatus.ACTIVE,
        ).distinct().count(),
        'documents_count': StudentDocument.objects.count(),
        'converted_prospects': Prospect.objects.filter(
            converted_student__isnull=False
        ).count(),
        'awaiting_prospects': Prospect.objects.filter(
            status__in=[
                Prospect.Status.NEW, Prospect.Status.TO_CONTACT,
                Prospect.Status.FOLLOW_UP, Prospect.Status.INTERESTED,
            ]
        ).count(),
    }
    return render(request, 'dashboard/secretaire/index.html', context)


@role_required('COMPTABLE')
def comptabilite_dashboard(request):
    today = timezone.localdate()
    from .views_comptabilite import accounts_with_balance

    validated = CashTransaction.objects.filter(
        status=CashTransaction.Status.VALIDATED
    )
    month_transactions = validated.filter(
        occurred_at__month=today.month,
        occurred_at__year=today.year,
    )
    context = {
        'total_revenue_month': month_transactions.filter(
            tx_type=CashTransaction.Type.IN,
        ).aggregate(total=Sum('amount'))['total'] or 0,
        'recent_payments': Payment.objects.select_related(
            'enrollment__student', 'recorded_by'
        ).order_by('-paid_at')[:10],
        'total_expenses_month': month_transactions.filter(
            tx_type=CashTransaction.Type.OUT,
        ).aggregate(total=Sum('amount'))['total'] or 0,
        'today_in': validated.filter(
            tx_type=CashTransaction.Type.IN,
            occurred_at__date=today,
        ).aggregate(total=Sum('amount'))['total'] or 0,
        'today_out': validated.filter(
            tx_type=CashTransaction.Type.OUT,
            occurred_at__date=today,
        ).aggregate(total=Sum('amount'))['total'] or 0,
        'pending_transactions': CashTransaction.objects.filter(
            status=CashTransaction.Status.DRAFT
        ).count(),
        'cash_rows': accounts_with_balance(),
        'recent_transactions': CashTransaction.objects.select_related(
            'account', 'category'
        ).order_by('-occurred_at')[:10],
        'closure_today': CashClosure.objects.filter(date=today).count(),
        'total_balance': sum(row['balance'] for row in accounts_with_balance()),
    }
    context['net_month'] = (
        context['total_revenue_month'] - context['total_expenses_month']
    )
    return render(request, 'dashboard/comptabilite/index.html', context)


@role_required('RESP_PEDA')
def responsable_pedagogique_dashboard(request):
    today = timezone.localdate()
    records = SessionRecord.objects.select_related(
        'session__course', 'module', 'lesson'
    )
    attendance = Attendance.objects.all()
    context = {
        'courses': Course.objects.filter(active=True),
        'active_sessions': CourseSession.objects.filter(
            status=CourseSession.Status.ACTIVE
        ).select_related('course').prefetch_related('formateurs'),
        'modules_count': Module.objects.count(),
        'lessons_count': Lesson.objects.count(),
        'records_count': records.count(),
        'records_completed': records.filter(
            status=SessionRecord.Status.COMPLETED
        ).count(),
        'upcoming_records': records.filter(
            date__gte=today,
            status=SessionRecord.Status.PLANNED,
        ).order_by('date')[:8],
        'recent_records': records.filter(
            status=SessionRecord.Status.COMPLETED
        ).order_by('-date')[:8],
        'hours_planned': round(
            sum(r.planned_minutes for r in records) / 60, 2
        ),
        'hours_actual': round(
            sum(r.actual_minutes for r in records) / 60, 2
        ),
        'attendance_totals': attendance.aggregate(
            total=Count('id'),
            presents=Count('id', filter=Q(status='PRESENT')),
            absents=Count('id', filter=Q(status='ABSENT')),
            late=Count('id', filter=Q(status='LATE')),
        ),
        'published_resources': Resource.objects.filter(
            status=Resource.Status.PUBLISHED
        ).count(),
    }
    return render(request, 'dashboard/responsable_pedagogique/index.html', context)


@role_required('FORMATEUR')
def formateur_dashboard(request):
    today = timezone.localdate()
    sessions = CourseSession.objects.filter(
        formateurs=request.user,
        status__in=[CourseSession.Status.ACTIVE, CourseSession.Status.PLANNED]
    ).select_related('course')
    student_count = Enrollment.objects.filter(
        session__in=sessions,
        status=Enrollment.Status.ACTIVE,
    ).count()

    records = SessionRecord.objects.filter(
        session__in=sessions
    ).select_related('session__course', 'module', 'lesson', 'recorded_by')
    today_records = records.filter(date=today).order_by('planned_start')
    upcoming_records = records.filter(
        date__gt=today, status=SessionRecord.Status.PLANNED
    ).order_by('date', 'planned_start')[:8]
    recent_records = records.filter(
        status=SessionRecord.Status.COMPLETED
    ).order_by('-date')[:8]

    planned_minutes = sum(r.planned_minutes for r in records)
    actual_minutes = sum(r.actual_minutes for r in records)

    recent_absences = Attendance.objects.filter(
        enrollment__session__in=sessions,
        status__in=[Attendance.Status.ABSENT, Attendance.Status.LATE],
    ).select_related(
        'enrollment__student', 'enrollment__session__course'
    ).order_by('-date')[:10]

    return render(request, 'dashboard/formateur/index.html', {
        'sessions': sessions,
        'student_count': student_count,
        'today_records': today_records,
        'upcoming_records': upcoming_records,
        'recent_records': recent_records,
        'hours_planned': round(planned_minutes / 60, 2),
        'hours_actual': round(actual_minutes / 60, 2),
        'hours_remaining': round(max(planned_minutes - actual_minutes, 0) / 60, 2),
        'recent_absences': recent_absences,
        'published_resources': Resource.objects.filter(
            author=request.user,
            status=Resource.Status.PUBLISHED,
        ).count(),
    })


@business_write_required('FORMATEUR')
def formateur_attendance(request, session_id):
    session = get_object_or_404(CourseSession, id=session_id)
    if not session.formateurs.filter(id=request.user.id).exists():
        return HttpResponseForbidden("Vous n'êtes pas affecté à cette session.")

    enrollments = Enrollment.objects.filter(
        session=session, status=Enrollment.Status.ACTIVE
    ).select_related('student')

    if request.method == 'POST':
        date_str = request.POST.get('date')
        for enrollment in enrollments:
            status = request.POST.get(f'status_{enrollment.id}')
            if status:
                Attendance.objects.update_or_create(
                    enrollment=enrollment,
                    date=date_str,
                    defaults={
                        'status': status,
                        'recorded_by': request.user,
                    }
                )
        log_audit(
            request, 'ATTENDANCE_RECORD', 'CourseSession', str(session_id),
            after={'date': date_str}
        )
        messages.success(request, "Présences enregistrées.")

    return render(request, 'dashboard/formateur/attendance.html', {
        'session': session,
        'enrollments': enrollments,
        'attendance_choices': Attendance.Status.choices,
    })


@role_required('ETUDIANT')
def etudiant_dashboard(request):
    today = timezone.localdate()
    enrollments = Enrollment.objects.filter(
        student=request.user
    ).select_related('session__course')

    payments = Payment.objects.filter(
        enrollment__student=request.user
    ).order_by('-paid_at')

    attendances = Attendance.objects.filter(
        enrollment__student=request.user
    ).order_by('-date')[:20]

    course_ids = [e.session.course_id for e in enrollments]
    session_ids = [e.session_id for e in enrollments]
    resources = Resource.objects.filter(
        status=Resource.Status.PUBLISHED,
        course_id__in=course_ids,
    ).filter(
        Q(session__isnull=True) | Q(session_id__in=session_ids)
    ).select_related('course', 'module', 'author').order_by(
        '-published_at'
    )[:10]

    total_due = sum(e.net_amount for e in enrollments)
    total_paid = sum(
        p.amount for p in payments if p.status == Payment.Status.COMPLETED
    )
    return render(request, 'dashboard/etudiant/index.html', {
        'enrollments': enrollments,
        'payments': payments,
        'attendances': attendances,
        'resources': resources,
        'today': today,
        'attendance_totals': Attendance.objects.filter(
            enrollment__student=request.user
        ).aggregate(
            total=Count('id'),
            presents=Count('id', filter=Q(status='PRESENT')),
            absents=Count('id', filter=Q(status='ABSENT')),
            late=Count('id', filter=Q(status='LATE')),
        ),
        'total_due': total_due,
        'total_paid': total_paid,
        'balance': sum(e.balance_due for e in enrollments),
        'upcoming_records': SessionRecord.objects.filter(
            session_id__in=session_ids,
            date__gte=today,
            status=SessionRecord.Status.PLANNED,
        ).select_related('session__course').order_by('date')[:8],
    })


@role_required('ACCUEIL')
def accueil_dashboard(request):
    form = AccessEventForm()
    if request.method == 'POST':
        if request.user.is_elevated:
            return HttpResponseForbidden(
                "Consultation seule : cette action relève du rôle métier."
            )
        form = AccessEventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.recorded_by = request.user
            event.save()
            log_audit(
                request, 'ACCESS_EVENT', 'AccessEvent', str(event.id),
                after={'type': event.event_type}
            )
            messages.success(request, "Événement enregistré.")
            form = AccessEventForm()

    recent_events = AccessEvent.objects.select_related(
        'person', 'recorded_by'
    )[:20]

    today = timezone.localdate()
    visits_today = Visit.objects.filter(
        arrival_at__date=today
    ).select_related('contact', 'reason', 'agent')
    return render(request, 'dashboard/accueil/index.html', {
        'form': form,
        'recent_events': recent_events,
        'entries_today': AccessEvent.objects.filter(
            event_type=AccessEvent.EventType.ENTRY,
            occurred_at__date=today,
        ).count(),
        'exits_today': AccessEvent.objects.filter(
            event_type=AccessEvent.EventType.EXIT,
            occurred_at__date=today,
        ).count(),
        'visits_today': visits_today,
        'visits_today_count': visits_today.count(),
        'present_count': Visit.objects.filter(
            status=Visit.Status.IN_PROGRESS, departure_at__isnull=True
        ).count(),
        'open_prospects': Prospect.objects.filter(
            status__in=[
                Prospect.Status.NEW, Prospect.Status.TO_CONTACT,
                Prospect.Status.CONTACTED, Prospect.Status.INFO_GIVEN,
                Prospect.Status.FOLLOW_UP, Prospect.Status.INTERESTED,
                Prospect.Status.ENROLLING,
            ]
        ).count(),
        'follow_ups_today': Prospect.objects.filter(
            next_follow_up__lte=today
        ).exclude(
            status__in=[Prospect.Status.ENROLLED,
                        Prospect.Status.NOT_INTERESTED,
                        Prospect.Status.ARCHIVED]
        ).select_related('contact', 'course')[:8],
        'recent_prospects': Prospect.objects.select_related(
            'contact', 'course', 'agent'
        )[:8],
    })


@login_required
def serve_private_file(request, doc_id):
    doc = get_object_or_404(ScholarshipDocument, id=doc_id)
    app = doc.application

    is_owner = (
        request.user.is_authenticated and
        app.applicant_user_id == request.user.id
    )
    is_admin = request.user.has_any_role('SUPER_ADMIN', 'ADMIN')

    if not is_owner and not is_admin:
        log_audit(
            request, 'UNAUTHORIZED_FILE_ACCESS', 'ScholarshipDocument',
            str(doc.id)
        )
        raise Http404

    log_audit(
        request, 'FILE_ACCESS', 'ScholarshipDocument', str(doc.id),
        after={'document_type': doc.document_type}
    )

    try:
        return FileResponse(
            doc.file.open('rb'),
            content_type=doc.mime_type,
            as_attachment=True,
            filename=doc.original_name
        )
    except Exception:
        raise Http404
