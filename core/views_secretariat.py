"""Dashboard Secrétariat : étudiants, inscriptions, dossiers et documents."""
import mimetypes

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .decorators import business_write_required, role_required
from .forms import (
    EnrollmentForm, NewEnrollmentForm, StudentDocumentForm, StudentEditForm,
    StudentForm,
)
from .models import (
    Course, CourseSession, Enrollment, Payment, Role, StudentDocument, User,
    UserRole, AccountStatus, Prospect, RoleKey, AuditLog,
)
from .utils import log_audit

SECRETARIAT_ROLES = ('SECRETAIRE', 'DIRECTION')


def _students_queryset():
    return User.objects.filter(roles__key=RoleKey.ETUDIANT).distinct()


@role_required(*SECRETARIAT_ROLES)
def student_list(request):
    students = _students_queryset().prefetch_related('roles')
    query = (request.GET.get('q') or '').strip()
    status = request.GET.get('status') or ''
    course_id = request.GET.get('course') or ''
    if query:
        students = students.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query) |
            Q(internal_code__icontains=query)
        )
    if status:
        students = students.filter(account_status=status)
    if course_id:
        students = students.filter(enrollments__session__course_id=course_id)

    paginator = Paginator(students.order_by('last_name', 'first_name'), 20)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'dashboard/secretaire/students.html', {
        'page': page,
        'query': query,
        'status_filter': status,
        'course_filter': course_id,
        'status_choices': AccountStatus.choices,
        'courses': Course.objects.filter(active=True),
    })


@business_write_required(*SECRETARIAT_ROLES)
def student_create(request):
    prospect = None
    prospect_id = request.GET.get('prospect')
    if prospect_id:
        prospect = get_object_or_404(
            Prospect.objects.select_related('contact'), id=prospect_id
        )

    initial = {}
    if prospect:
        contact = prospect.contact
        initial = {
            'first_name': contact.first_name,
            'last_name': contact.last_name,
            'email': contact.email,
            'phone': contact.phone,
        }

    form = StudentForm(initial=initial)
    enroll_form = NewEnrollmentForm()

    if request.method == 'POST':
        form = StudentForm(request.POST)
        enroll_form = NewEnrollmentForm(request.POST)
        if form.is_valid() and enroll_form.is_valid():
            with transaction.atomic():
                student = form.save(commit=False)
                student.username = student.email
                student.account_status = AccountStatus.ACTIVE
                student.generate_internal_code(RoleKey.ETUDIANT)
                password = form.cleaned_data.get('password')
                if password:
                    student.set_password(password)
                else:
                    student.set_unusable_password()
                student.save()

                role = Role.objects.get(key=RoleKey.ETUDIANT)
                UserRole.objects.get_or_create(
                    user=student, role=role,
                    defaults={'assigned_by': request.user},
                )

                enrollment = Enrollment.objects.create(
                    student=student,
                    session=enroll_form.cleaned_data['session'],
                    status=enroll_form.cleaned_data['status'],
                    start_date=enroll_form.cleaned_data['start_date'],
                    tariff_amount=enroll_form.cleaned_data['tariff_amount'],
                    discount_amount=enroll_form.cleaned_data['discount_amount'] or 0,
                    net_amount=enroll_form.net_amount,
                    payment_plan=enroll_form.cleaned_data['payment_plan'],
                    notes=enroll_form.cleaned_data['notes'],
                    registered_by=request.user,
                )

                if prospect:
                    prospect.converted_student = student
                    prospect.converted_at = timezone.now()
                    prospect.status = Prospect.Status.ENROLLED
                    prospect.save(update_fields=[
                        'converted_student', 'converted_at', 'status', 'updated_at'
                    ])

            log_audit(
                request, 'STUDENT_CREATE', 'User', str(student.id),
                after={
                    'email': student.email,
                    'code': student.internal_code,
                    'enrollment': str(enrollment.id),
                    'prospect': prospect.reference if prospect else None,
                },
            )
            messages.success(
                request,
                f"Étudiant {student.get_full_name()} créé "
                f"({student.internal_code}) et inscrit à "
                f"{enrollment.session.course.title}.",
            )
            return redirect('core:dashboard:student-detail', student_id=student.id)

    return render(request, 'dashboard/secretaire/student_form.html', {
        'form': form,
        'enroll_form': enroll_form,
        'prospect': prospect,
        'creating': True,
    })


@role_required(*SECRETARIAT_ROLES)
def student_detail(request, student_id):
    student = get_object_or_404(
        User.objects.prefetch_related('roles'), id=student_id
    )
    enrollments = Enrollment.objects.filter(student=student).select_related(
        'session__course'
    ).order_by('-enrolled_at')
    payments = Payment.objects.filter(
        enrollment__student=student
    ).select_related('enrollment__session__course', 'transaction').order_by(
        '-paid_at'
    )
    attendances = student.enrollments.model.objects.none()  # placeholder
    from .models import Attendance

    attendances = Attendance.objects.filter(
        enrollment__student=student
    ).select_related('enrollment__session__course').order_by('-date')[:30]

    total_due = enrollments.aggregate(total=Sum('net_amount'))['total'] or 0
    total_paid = payments.filter(
        status=Payment.Status.COMPLETED
    ).aggregate(total=Sum('amount'))['total'] or 0

    return render(request, 'dashboard/secretaire/student_detail.html', {
        'student': student,
        'enrollments': enrollments,
        'payments': payments,
        'attendances': attendances,
        'documents': student.student_documents.all(),
        'total_due': total_due,
        'total_paid': total_paid,
        'balance': sum(e.balance_due for e in enrollments),
        'doc_form': StudentDocumentForm(),
        'audit_entries': AuditLog.objects.filter(
            entity_type='User', entity_id=str(student.id),
        ).select_related('actor').order_by('-created_at')[:20],
    })


@business_write_required(*SECRETARIAT_ROLES)
def student_edit(request, student_id):
    student = get_object_or_404(User, id=student_id)
    form = StudentEditForm(instance=student)
    if request.method == 'POST':
        before = {
            'first_name': student.first_name,
            'last_name': student.last_name,
            'phone': student.phone,
        }
        form = StudentEditForm(request.POST, instance=student)
        if form.is_valid():
            form.save()
            log_audit(
                request, 'STUDENT_EDIT', 'User', str(student.id),
                before=before,
                after={'first_name': student.first_name,
                       'last_name': student.last_name,
                       'phone': student.phone},
            )
            messages.success(request, "Fiche étudiant mise à jour.")
            return redirect('core:dashboard:student-detail', student_id=student.id)
    return render(request, 'dashboard/secretaire/student_edit.html', {
        'form': form, 'student': student,
    })


@business_write_required(*SECRETARIAT_ROLES)
def enrollment_create(request):
    initial = {}
    student_id = request.GET.get('student')
    if student_id:
        initial['student'] = student_id
    form = EnrollmentForm(initial=initial)
    if request.method == 'POST':
        form = EnrollmentForm(request.POST)
        if form.is_valid():
            enrollment = form.save(commit=False)
            enrollment.registered_by = request.user
            enrollment.save()
            log_audit(
                request, 'ENROLLMENT_CREATE', 'Enrollment', str(enrollment.id),
                after={'student': str(enrollment.student_id),
                       'session': str(enrollment.session_id),
                       'net': enrollment.net_amount},
            )
            messages.success(request, "Inscription enregistrée.")
            return redirect('core:dashboard:enrollment-detail',
                            enrollment_id=enrollment.id)
    return render(request, 'dashboard/secretaire/enrollment_form.html', {
        'form': form, 'creating': True,
    })


@business_write_required(*SECRETARIAT_ROLES)
def enrollment_edit(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment, id=enrollment_id)
    form = EnrollmentForm(instance=enrollment)
    if request.method == 'POST':
        before = {
            'status': enrollment.status,
            'net_amount': enrollment.net_amount,
            'session': str(enrollment.session_id),
        }
        form = EnrollmentForm(request.POST, instance=enrollment)
        if form.is_valid():
            enrollment = form.save(commit=False)
            enrollment.save()
            log_audit(
                request, 'ENROLLMENT_EDIT', 'Enrollment', str(enrollment.id),
                before=before,
                after={'status': enrollment.status,
                       'net_amount': enrollment.net_amount,
                       'session': str(enrollment.session_id)},
            )
            messages.success(request, "Inscription mise à jour.")
            return redirect('core:dashboard:enrollment-detail',
                            enrollment_id=enrollment.id)
    return render(request, 'dashboard/secretaire/enrollment_form.html', {
        'form': form, 'enrollment': enrollment, 'creating': False,
    })


@role_required(*SECRETARIAT_ROLES, 'COMPTABLE')
def enrollment_detail(request, enrollment_id):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related('student', 'session__course'),
        id=enrollment_id,
    )
    payments = enrollment.payments.select_related(
        'recorded_by', 'transaction'
    ).order_by('-paid_at')
    return render(request, 'dashboard/secretaire/enrollment_detail.html', {
        'enrollment': enrollment,
        'payments': payments,
        'documents': enrollment.documents.all(),
        'audit_entries': AuditLog.objects.filter(
            entity_type='Enrollment', entity_id=str(enrollment.id),
        ).select_related('actor').order_by('-created_at')[:20],
    })


@business_write_required(*SECRETARIAT_ROLES)
def student_document_upload(request, student_id):
    student = get_object_or_404(User, id=student_id)
    if request.method == 'POST':
        form = StudentDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.student = student
            uploaded = request.FILES['file']
            enrollment_id = request.POST.get('enrollment')
            if enrollment_id:
                document.enrollment = Enrollment.objects.filter(
                    id=enrollment_id, student=student
                ).first()
            document.original_name = uploaded.name
            document.mime_type = (
                getattr(uploaded, 'content_type', '')
                or mimetypes.guess_type(uploaded.name)[0]
                or 'application/octet-stream'
            )
            document.size_bytes = uploaded.size
            document.uploaded_by = request.user
            if uploaded.size > 10 * 1024 * 1024:
                messages.error(request, "Le document dépasse 10 Mo.")
            else:
                document.save()
                log_audit(
                    request, 'STUDENT_DOCUMENT_UPLOAD', 'StudentDocument',
                    str(document.id),
                    after={'student': str(student.id),
                           'type': document.doc_type},
                )
                messages.success(request, "Document ajouté au dossier.")
        else:
            messages.error(request, "Le document n'a pas pu être enregistré.")
    return redirect('core:dashboard:student-detail', student_id=student.id)


@role_required(*SECRETARIAT_ROLES, 'COMPTABLE', 'ETUDIANT')
def student_document_download(request, doc_id):
    document = get_object_or_404(StudentDocument, id=doc_id)
    user = request.user
    is_owner = document.student_id == user.id
    allowed = is_owner or user.has_any_role(
        'SECRETAIRE', 'DIRECTION', 'COMPTABLE', 'SUPER_ADMIN', 'ADMIN'
    )
    if not allowed:
        log_audit(request, 'UNAUTHORIZED_FILE_ACCESS', 'StudentDocument',
                  str(document.id))
        raise Http404
    log_audit(request, 'FILE_ACCESS', 'StudentDocument', str(document.id))
    try:
        return FileResponse(
            document.file.open('rb'),
            content_type=document.mime_type or 'application/octet-stream',
            as_attachment=True,
            filename=document.original_name,
        )
    except Exception:
        raise Http404
