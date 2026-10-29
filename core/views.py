import logging

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden, FileResponse, Http404
from django.db.models import Q, Sum, Count
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    User, Role, UserRole, AccessRequest, AccountStatus,
    ScholarshipApplication, ScholarshipDocument, Destination,
    Course, CourseSession, Enrollment, Attendance, Payment, Expense,
    AccessEvent, Notification, AuditLog, Certificate,
    ROLE_DASHBOARD_ROUTES, PRIVILEGED_ROLES, RoleKey,
    Visit, Prospect, ProspectFollowUp, Contact,
    Module, Lesson, SessionRecord, Resource, StudentDocument,
    CashAccount, CashTransaction, CashClosure, TransactionCategory,
)
from .forms import (
    LoginForm, RegisterForm, UserCreateForm, UserEditForm,
    ScholarshipApplicationForm, ScholarshipDocumentForm,
    PaymentForm, AccessEventForm
)
from .decorators import active_account_required, role_required, permission_required
from .utils import log_audit
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

            AccessRequest.objects.create(user=user)

            log_audit(request, 'REGISTER', 'User', str(user.id))
            login(request, user)
            return redirect('core:pending-approval')

    return render(request, 'public/register.html', {
        'form': form,
        'login_form': LoginForm(auto_id='login_%s'),
    })


def pending_approval(request):
    return render(request, 'public/pending_approval.html')


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


@role_required('SUPER_ADMIN')
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


@role_required('SUPER_ADMIN', 'ADMIN')
def user_detail(request, user_id):
    user = get_object_or_404(User, id=user_id)
    audit = AuditLog.objects.filter(
        entity_type='User', entity_id=str(user_id)
    )[:20]
    return render(request, 'dashboard/super_admin/user_detail.html', {
        'profile_user': user,
        'audit_entries': audit,
    })


@role_required('SUPER_ADMIN')
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


@role_required('SUPER_ADMIN')
def user_role_assign(request, user_id):
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id)
        role_key = request.POST.get('role_key')
        action = request.POST.get('action', 'add')

        role = get_object_or_404(Role, key=role_key)

        if role.is_privileged and not request.user.has_role('SUPER_ADMIN'):
            return HttpResponseForbidden("Impossible d'attribuer un rôle privilégié.")

        if action == 'add':
            UserRole.objects.get_or_create(
                user=user, role=role, defaults={'assigned_by': request.user}
            )
            log_audit(
                request, 'ROLE_ASSIGN', 'User', str(user.id),
                after={'role': role_key}
            )
        elif action == 'remove':
            UserRole.objects.filter(user=user, role=role).delete()
            log_audit(
                request, 'ROLE_REMOVE', 'User', str(user.id),
                after={'role': role_key}
            )

        messages.success(request, f"Rôle {role.label} {'ajouté' if action == 'add' else 'retiré'}.")
    return redirect('core:dashboard:user-detail', user_id=user_id)


@role_required('SUPER_ADMIN')
def access_requests_list(request):
    requests_list = AccessRequest.objects.filter(
        status=AccessRequest.Status.PENDING
    ).select_related('user')
    return render(request, 'dashboard/super_admin/access_requests.html', {
        'requests': requests_list,
        'role_choices': RoleKey.choices,
    })


@role_required('SUPER_ADMIN')
def access_request_review(request, request_id):
    ar = get_object_or_404(AccessRequest, id=request_id)

    if request.method == 'POST':
        decision = request.POST.get('decision')
        role_key = request.POST.get('role_key', 'ETUDIANT')
        note = request.POST.get('note', '')

        ar.reviewed_by = request.user
        ar.reviewed_at = timezone.now()
        ar.decision_note = note

        if decision == 'approve':
            ar.status = AccessRequest.Status.APPROVED
            ar.user.account_status = AccountStatus.ACTIVE
            ar.user.generate_internal_code(role_key)
            ar.user.save()

            role = Role.objects.get(key=role_key)
            UserRole.objects.get_or_create(
                user=ar.user, role=role, defaults={'assigned_by': request.user}
            )

            Notification.objects.create(
                user=ar.user,
                title="Compte approuvé",
                message=f"Votre compte a été approuvé. Votre code : {ar.user.internal_code}",
                notification_type=Notification.Type.ACCOUNT_APPROVED,
            )

            log_audit(
                request, 'ACCESS_APPROVE', 'AccessRequest', str(ar.id),
                after={'user': str(ar.user.id), 'role': role_key}
            )
            messages.success(request, f"Compte de {ar.user.get_full_name()} approuvé.")

        elif decision == 'reject':
            ar.status = AccessRequest.Status.REJECTED
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
                after={'user': str(ar.user.id)}
            )
            messages.info(request, "Demande refusée.")

        ar.save()
        return redirect('core:dashboard:access-requests')

    return render(request, 'dashboard/super_admin/access_requests.html', {
        'review_request': ar,
        'role_choices': RoleKey.choices,
    })


@role_required('SUPER_ADMIN')
def audit_log_view(request):
    entries = AuditLog.objects.select_related('actor').all()
    paginator = Paginator(entries, 50)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'dashboard/super_admin/audit_log.html', {'page': page})


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
    context = {
        'active_students': User.objects.filter(
            roles__key='ETUDIANT', account_status=AccountStatus.ACTIVE
        ).count(),
        'pending_requests': AccessRequest.objects.filter(
            status=AccessRequest.Status.PENDING
        ).count(),
        'total_trainers': User.objects.filter(
            roles__key='FORMATEUR', account_status=AccountStatus.ACTIVE
        ).count(),
        'active_courses': Course.objects.filter(active=True).count(),
        'recent_users': User.objects.prefetch_related('roles').order_by(
            '-date_joined'
        )[:6],
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
        'total_revenue': payments.aggregate(total=Sum('amount'))['total'] or 0,
        'total_students': User.objects.filter(
            roles__key='ETUDIANT', account_status=AccountStatus.ACTIVE
        ).count(),
        'active_sessions': CourseSession.objects.filter(
            status=CourseSession.Status.ACTIVE
        ).count(),
        'new_enrollments': Enrollment.objects.filter(
            enrolled_at__date__gte=month_start
        ).count(),
        'recent_payments': Payment.objects.select_related(
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
        'unpaid_enrollments': Enrollment.objects.filter(
            status=Enrollment.Status.ACTIVE
        ).count(),
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
    context = {
        'total_revenue_month': Payment.objects.filter(
            status=Payment.Status.COMPLETED,
            paid_at__month=today.month,
            paid_at__year=today.year,
        ).aggregate(total=Sum('amount'))['total'] or 0,
        'recent_payments': Payment.objects.select_related(
            'enrollment__student', 'recorded_by'
        ).order_by('-paid_at')[:10],
        'total_expenses_month': Expense.objects.filter(
            occurred_at__month=today.month,
            occurred_at__year=today.year,
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


@role_required('FORMATEUR')
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
        'balance': max(total_due - total_paid, 0),
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


@role_required('COMPTABLE', 'SUPER_ADMIN')
def payment_create(request):
    form = PaymentForm()
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.recorded_by = request.user
            payment.save()
            log_audit(
                request, 'PAYMENT_CREATE', 'Payment', str(payment.id),
                after={
                    'amount': payment.amount,
                    'reference': payment.reference,
                    'enrollment': str(payment.enrollment_id),
                }
            )
            messages.success(request, f"Paiement {payment.reference} enregistré.")
            return redirect('core:dashboard:comptabilite-dashboard')
    return render(request, 'dashboard/comptabilite/payment_form.html', {'form': form})


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
