"""Dashboard pédagogie : programmes, séances, présences et ressources."""
from datetime import date

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .decorators import business_write_required, role_required
from .forms import (
    CourseSessionForm, LessonForm, ModuleForm, ResourceFeedbackForm,
    ResourceForm, SessionRecordForm, StudentSessionNoteForm, TextbookEntryForm,
)
from .models import (
    Attendance, AuditLog, Course, CourseSession, Enrollment, Lesson, Module,
    Resource, ResourceFeedback, RoleKey, SessionRecord, StudentSessionNote,
)
from .utils import log_audit

PEDAGOGY_ROLES = ('FORMATEUR', 'RESP_PEDA', 'DIRECTION', 'SECRETAIRE')
MANAGE_ROLES = ('FORMATEUR', 'RESP_PEDA', 'DIRECTION')


def _is_manager(user):
    return user.has_any_role('SUPER_ADMIN', 'ADMIN', 'RESP_PEDA', 'DIRECTION')


def _can_access_session(user, session):
    if _is_manager(user) or user.has_role('SECRETAIRE'):
        return True
    return session.formateurs.filter(id=user.id).exists()


def _my_sessions(user):
    if _is_manager(user) or user.has_role('SECRETAIRE'):
        return CourseSession.objects.all()
    return CourseSession.objects.filter(formateurs=user)


def _can_manage_record(user, record):
    if user.is_elevated:
        return False
    if user.has_any_role('RESP_PEDA', 'DIRECTION'):
        return True
    if user.has_role('FORMATEUR'):
        return record.session.formateurs.filter(id=user.id).exists()
    return False


def _record_queryset():
    return SessionRecord.objects.select_related(
        'session__course', 'module', 'lesson', 'recorded_by'
    )


# ---------------------------------------------------------------------------
# Programmes : modules et leçons
# ---------------------------------------------------------------------------

@role_required(*PEDAGOGY_ROLES)
def program_list(request):
    sessions = _my_sessions(request.user).select_related('course').distinct()
    courses = Course.objects.filter(
        id__in=sessions.values_list('course_id', flat=True)
    ).prefetch_related('modules__lessons')
    if _is_manager(request.user):
        courses = Course.objects.filter(active=True).prefetch_related(
            'modules__lessons'
        )
    return render(request, 'dashboard/pedagogie/programs.html', {
        'courses': courses,
        'can_manage': not request.user.is_elevated and request.user.has_any_role(
            'FORMATEUR', 'RESP_PEDA', 'DIRECTION'
        ),
    })


@business_write_required('FORMATEUR', 'RESP_PEDA', 'DIRECTION')
def module_create(request):
    form = ModuleForm()
    if request.method == 'POST':
        form = ModuleForm(request.POST)
        if form.is_valid():
            module = form.save()
            log_audit(request, 'MODULE_CREATE', 'Module', str(module.id),
                      after={'title': module.title,
                             'course': str(module.course_id)})
            messages.success(request, "Module créé.")
            return redirect('core:dashboard:programs')
    return render(request, 'dashboard/pedagogie/module_form.html', {
        'form': form, 'creating': True,
    })


@business_write_required('FORMATEUR', 'RESP_PEDA', 'DIRECTION')
def module_edit(request, module_id):
    module = get_object_or_404(Module, id=module_id)
    form = ModuleForm(instance=module)
    if request.method == 'POST':
        form = ModuleForm(request.POST, instance=module)
        if form.is_valid():
            module = form.save()
            log_audit(request, 'MODULE_EDIT', 'Module', str(module.id),
                      after={'title': module.title})
            messages.success(request, "Module mis à jour.")
            return redirect('core:dashboard:programs')
    return render(request, 'dashboard/pedagogie/module_form.html', {
        'form': form, 'module': module, 'creating': False,
    })


@business_write_required('FORMATEUR', 'RESP_PEDA', 'DIRECTION')
def lesson_create(request):
    form = LessonForm()
    module_id = request.GET.get('module')
    if module_id:
        form.initial['module'] = module_id
    if request.method == 'POST':
        form = LessonForm(request.POST)
        if form.is_valid():
            lesson = form.save()
            log_audit(request, 'LESSON_CREATE', 'Lesson', str(lesson.id),
                      after={'title': lesson.title,
                             'module': str(lesson.module_id)})
            messages.success(request, "Leçon créée.")
            return redirect('core:dashboard:programs')
    return render(request, 'dashboard/pedagogie/lesson_form.html', {
        'form': form, 'creating': True,
    })


@business_write_required('FORMATEUR', 'RESP_PEDA', 'DIRECTION')
def lesson_edit(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    form = LessonForm(instance=lesson)
    if request.method == 'POST':
        form = LessonForm(request.POST, instance=lesson)
        if form.is_valid():
            lesson = form.save()
            log_audit(request, 'LESSON_EDIT', 'Lesson', str(lesson.id),
                      after={'title': lesson.title})
            messages.success(request, "Leçon mise à jour.")
            return redirect('core:dashboard:programs')
    return render(request, 'dashboard/pedagogie/lesson_form.html', {
        'form': form, 'lesson': lesson, 'creating': False,
    })


# ---------------------------------------------------------------------------
# Groupes de formation (CourseSession)
# ---------------------------------------------------------------------------

@role_required(*PEDAGOGY_ROLES)
def course_session_list(request):
    sessions = _my_sessions(request.user).select_related(
        'course'
    ).prefetch_related('formateurs')

    status = request.GET.get('status') or ''
    query = (request.GET.get('q') or '').strip()
    if status:
        sessions = sessions.filter(status=status)
    if query:
        sessions = sessions.filter(
            Q(course__title__icontains=query) | Q(schedule__icontains=query)
        )

    paginator = Paginator(sessions.distinct(), 20)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'dashboard/pedagogie/course_session_list.html', {
        'page': page,
        'query': query,
        'status_filter': status,
        'status_choices': CourseSession.Status.choices,
        'can_manage': not request.user.is_elevated and request.user.has_any_role(
            'RESP_PEDA', 'DIRECTION'
        ),
    })


@business_write_required('RESP_PEDA', 'DIRECTION')
def course_session_create(request):
    form = CourseSessionForm()
    if request.method == 'POST':
        form = CourseSessionForm(request.POST)
        if form.is_valid():
            session = form.save()
            log_audit(
                request, 'COURSE_SESSION_CREATE', 'CourseSession',
                str(session.id),
                after={'course': str(session.course_id),
                       'starts_at': str(session.starts_at),
                       'ends_at': str(session.ends_at),
                       'status': session.status,
                       'formateurs': [str(f.id) for f in session.formateurs.all()]},
            )
            messages.success(request, "Groupe créé.")
            return redirect('core:dashboard:course-sessions')
    return render(request, 'dashboard/pedagogie/course_session_form.html', {
        'form': form, 'creating': True,
    })


@business_write_required('RESP_PEDA', 'DIRECTION')
def course_session_edit(request, session_id):
    session = get_object_or_404(
        CourseSession.objects.select_related('course'), id=session_id
    )
    form = CourseSessionForm(instance=session)
    if request.method == 'POST':
        before = {
            'course': str(session.course_id),
            'starts_at': str(session.starts_at),
            'ends_at': str(session.ends_at),
            'status': session.status,
            'formateurs': [str(f.id) for f in session.formateurs.all()],
        }
        form = CourseSessionForm(request.POST, instance=session)
        if form.is_valid():
            session = form.save()
            log_audit(
                request, 'COURSE_SESSION_EDIT', 'CourseSession',
                str(session.id),
                before=before,
                after={'course': str(session.course_id),
                       'starts_at': str(session.starts_at),
                       'ends_at': str(session.ends_at),
                       'status': session.status,
                       'formateurs': [str(f.id) for f in session.formateurs.all()]},
            )
            messages.success(request, "Groupe mis à jour.")
            return redirect('core:dashboard:course-sessions')
    return render(request, 'dashboard/pedagogie/course_session_form.html', {
        'form': form, 'session': session, 'creating': False,
    })


# ---------------------------------------------------------------------------
# Séances
# ---------------------------------------------------------------------------

@role_required(*PEDAGOGY_ROLES)
def session_record_list(request):
    records = _record_queryset()
    if not (_is_manager(request.user) or request.user.has_role('SECRETAIRE')):
        records = records.filter(session__formateurs=request.user)

    query = (request.GET.get('q') or '').strip()
    status = request.GET.get('status') or ''
    session_id = request.GET.get('session') or ''
    if query:
        records = records.filter(
            Q(topic__icontains=query) |
            Q(session__course__title__icontains=query) |
            Q(content_covered__icontains=query)
        )
    if status:
        records = records.filter(status=status)
    if session_id:
        records = records.filter(session_id=session_id)

    paginator = Paginator(records.distinct(), 20)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'dashboard/pedagogie/sessions.html', {
        'page': page,
        'query': query,
        'status_filter': status,
        'session_filter': session_id,
        'status_choices': SessionRecord.Status.choices,
        'sessions': _my_sessions(request.user).select_related('course').distinct(),
    })


@business_write_required(*MANAGE_ROLES)
def session_record_create(request, session_id):
    session = get_object_or_404(
        CourseSession.objects.select_related('course'), id=session_id
    )
    if not _can_access_session(request.user, session):
        return render(request, 'dashboard/403.html', status=403)

    initial = {'date': timezone.localdate(), 'status': SessionRecord.Status.PLANNED}
    form = SessionRecordForm(session=session, initial=initial)
    if request.method == 'POST':
        form = SessionRecordForm(request.POST, session=session)
        if form.is_valid():
            record = form.save(commit=False)
            record.session = session
            record.recorded_by = request.user
            record.save()
            log_audit(
                request, 'SESSION_CREATE', 'SessionRecord', str(record.id),
                after={'session': str(session.id), 'date': str(record.date),
                       'status': record.status},
            )
            messages.success(request, "Séance enregistrée.")
            return redirect('core:dashboard:session-record-detail',
                            record_id=record.id)
    return render(request, 'dashboard/pedagogie/session_form.html', {
        'form': form, 'session': session, 'creating': True,
    })


@role_required(*PEDAGOGY_ROLES)
def session_record_detail(request, record_id):
    record = get_object_or_404(_record_queryset(), id=record_id)
    if not _can_access_session(request.user, record.session):
        return render(request, 'dashboard/403.html', status=403)

    can_manage = _can_manage_record(request.user, record)
    form = SessionRecordForm(session=record.session, instance=record)

    if request.method == 'POST':
        if not can_manage:
            return render(request, 'dashboard/403.html', status=403)
        before = {
            'date': str(record.date),
            'status': record.status,
            'actual_start': str(record.actual_start),
            'actual_end': str(record.actual_end),
        }
        form = SessionRecordForm(
            request.POST, session=record.session, instance=record
        )
        if form.is_valid():
            record = form.save(commit=False)
            record.recorded_by = request.user
            record.save()
            log_audit(
                request, 'SESSION_UPDATE', 'SessionRecord', str(record.id),
                before=before,
                after={'date': str(record.date), 'status': record.status,
                       'actual_start': str(record.actual_start),
                       'actual_end': str(record.actual_end)},
            )
            messages.success(request, "Compte rendu de séance mis à jour.")
            return redirect('core:dashboard:session-record-detail',
                            record_id=record.id)

    attendances = record.attendances.select_related(
        'enrollment__student'
    ).order_by('enrollment__student__last_name')
    summary = {
        'total': attendances.count(),
        'present': attendances.filter(
            status=Attendance.Status.PRESENT).count(),
        'absent': attendances.filter(
            status=Attendance.Status.ABSENT).count(),
        'late': attendances.filter(status=Attendance.Status.LATE).count(),
        'excused': attendances.filter(
            status=Attendance.Status.EXCUSED).count(),
    }
    return render(request, 'dashboard/pedagogie/session_detail.html', {
        'record': record,
        'form': form,
        'can_manage': can_manage,
        'attendances': attendances,
        'summary': summary,
        'student_notes': record.student_notes.select_related(
            'enrollment__student'
        ).order_by('enrollment__student__last_name'),
        'audit_entries': AuditLog.objects.filter(
            entity_type='SessionRecord', entity_id=str(record.id),
        ).select_related('actor').order_by('-created_at')[:20],
    })


@role_required(*MANAGE_ROLES, 'SECRETAIRE')
def attendance_sheet(request, record_id):
    record = get_object_or_404(_record_queryset(), id=record_id)
    if not _can_access_session(request.user, record.session):
        return render(request, 'dashboard/403.html', status=403)

    enrollments = Enrollment.objects.filter(
        session=record.session,
        status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED],
    ).select_related('student').order_by('student__last_name')

    can_edit = _can_manage_record(request.user, record)

    if request.method == 'POST':
        if not can_edit:
            return render(request, 'dashboard/403.html', status=403)
        saved = 0
        for enrollment in enrollments:
            raw_status = request.POST.get(f'status_{enrollment.id}')
            if not raw_status:
                continue
            valid = {choice for choice, _ in Attendance.Status.choices}
            if raw_status not in valid:
                continue
            arrival = request.POST.get(f'arrival_{enrollment.id}') or None
            reason = (request.POST.get(f'reason_{enrollment.id}') or '').strip()
            note = (request.POST.get(f'note_{enrollment.id}') or '').strip()
            existing = Attendance.objects.filter(
                enrollment=enrollment, date=record.date
            ).first()
            if existing and existing.session_record_id not in (
                None, record.id
            ):
                # Une autre séance a déjà figé la présence du jour :
                # correction explicite requise, on ne l'écrase pas en silence.
                continue
            Attendance.objects.update_or_create(
                enrollment=enrollment,
                date=record.date,
                defaults={
                    'session_record': record,
                    'status': raw_status,
                    'arrival_time': arrival if raw_status == 'LATE' else None,
                    'absence_reason': reason if raw_status in (
                        'ABSENT', 'EXCUSED'
                    ) else '',
                    'note': note,
                    'recorded_by': request.user,
                },
            )
            saved += 1
        log_audit(
            request, 'ATTENDANCE_RECORD', 'SessionRecord', str(record.id),
            after={'date': str(record.date), 'count': saved},
        )
        messages.success(request, f"{saved} présence(s) enregistrée(s).")
        return redirect('core:dashboard:session-record-attendance',
                        record_id=record.id)

    existing = {
        a.enrollment_id: a
        for a in Attendance.objects.filter(
            session_record=record
        ) | Attendance.objects.filter(
            enrollment__in=enrollments, date=record.date
        )
    }
    rows = []
    for enrollment in enrollments:
        rows.append({
            'enrollment': enrollment,
            'student': enrollment.student,
            'attendance': existing.get(enrollment.id),
        })
    summary = {
        'inscrits': enrollments.count(),
        'presents': sum(1 for r in rows if r['attendance'] and
                        r['attendance'].status == 'PRESENT'),
        'absents': sum(1 for r in rows if r['attendance'] and
                       r['attendance'].status == 'ABSENT'),
        'retards': sum(1 for r in rows if r['attendance'] and
                       r['attendance'].status == 'LATE'),
        'excuses': sum(1 for r in rows if r['attendance'] and
                       r['attendance'].status == 'EXCUSED'),
    }
    return render(request, 'dashboard/pedagogie/attendance_sheet.html', {
        'record': record,
        'rows': rows,
        'summary': summary,
        'can_edit': can_edit,
        'attendance_choices': Attendance.Status.choices,
    })


# ---------------------------------------------------------------------------
# Historique des absences / statistiques
# ---------------------------------------------------------------------------

@role_required(*PEDAGOGY_ROLES)
def attendance_history(request):
    attendances = Attendance.objects.select_related(
        'enrollment__student', 'enrollment__session__course', 'session_record'
    )
    if not (_is_manager(request.user) or request.user.has_role('SECRETAIRE')):
        attendances = attendances.filter(
            enrollment__session__formateurs=request.user
        )

    query = (request.GET.get('q') or '').strip()
    status = request.GET.get('status') or ''
    course_id = request.GET.get('course') or ''
    session_id = request.GET.get('session') or ''
    date_from = request.GET.get('from') or ''
    date_to = request.GET.get('to') or ''

    if query:
        attendances = attendances.filter(
            Q(enrollment__student__first_name__icontains=query) |
            Q(enrollment__student__last_name__icontains=query) |
            Q(enrollment__student__internal_code__icontains=query)
        )
    if status:
        attendances = attendances.filter(status=status)
    if course_id:
        attendances = attendances.filter(
            enrollment__session__course_id=course_id
        )
    if session_id:
        attendances = attendances.filter(
            enrollment__session_id=session_id
        )
    if date_from:
        attendances = attendances.filter(date__gte=date_from)
    if date_to:
        attendances = attendances.filter(date__lte=date_to)

    totals = attendances.aggregate(
        total=Count('id'),
        presents=Count('id', filter=Q(status='PRESENT')),
        absents=Count('id', filter=Q(status='ABSENT')),
        retards=Count('id', filter=Q(status='LATE')),
        excuses=Count('id', filter=Q(status='EXCUSED')),
    )

    recurrent = (
        attendances
        .filter(status__in=['ABSENT', 'LATE', 'EXCUSED'])
        .values('enrollment__student__id',
                'enrollment__student__first_name',
                'enrollment__student__last_name',
                'enrollment__student__internal_code')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )

    paginator = Paginator(attendances.order_by('-date'), 30)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'dashboard/pedagogie/attendance_history.html', {
        'page': page,
        'totals': totals,
        'recurrent': recurrent,
        'query': query,
        'status_filter': status,
        'course_filter': course_id,
        'session_filter': session_id,
        'date_from': date_from,
        'date_to': date_to,
        'status_choices': Attendance.Status.choices,
        'courses': Course.objects.filter(active=True),
        'sessions': _my_sessions(request.user).select_related('course').distinct(),
    })


@role_required(*PEDAGOGY_ROLES)
def progression_overview(request):
    sessions = _my_sessions(request.user).select_related('course').distinct()
    course_id = request.GET.get('course') or ''
    if course_id:
        sessions = sessions.filter(course_id=course_id)

    rows = []
    for session in sessions:
        records = session.records.all()
        planned = sum(r.planned_minutes for r in records) / 60
        actual = sum(r.actual_minutes for r in records) / 60
        completed_lessons = records.filter(
            status=SessionRecord.Status.COMPLETED
        ).values('lesson').distinct().count()
        rows.append({
            'session': session,
            'records': records.count(),
            'completed': records.filter(
                status=SessionRecord.Status.COMPLETED).count(),
            'planned_hours': round(planned, 2),
            'actual_hours': round(actual, 2),
            'remaining_hours': round(max(planned - actual, 0), 2),
            'lessons_done': completed_lessons,
            'last_record': records.filter(
                status=SessionRecord.Status.COMPLETED
            ).order_by('-date').first(),
        })

    return render(request, 'dashboard/pedagogie/progression.html', {
        'rows': rows,
        'courses': Course.objects.filter(active=True),
        'course_filter': course_id,
    })


# ---------------------------------------------------------------------------
# Ressources pédagogiques
# ---------------------------------------------------------------------------

def _resource_access(user, resource, student=False):
    if user.has_any_role('SUPER_ADMIN', 'ADMIN', 'RESP_PEDA', 'DIRECTION'):
        return True
    if user.has_role('FORMATEUR'):
        return resource.author_id == user.id or (
            resource.session and resource.session.formateurs.filter(
                id=user.id).exists()
        )
    if user.has_role('ETUDIANT'):
        if resource.status != Resource.Status.PUBLISHED:
            return False
        enrollments = Enrollment.objects.filter(
            student=user,
            session__course=resource.course,
        )
        if resource.session_id:
            enrollments = enrollments.filter(session_id=resource.session_id)
        return enrollments.exists()
    return False


@role_required('FORMATEUR', 'RESP_PEDA', 'DIRECTION')
def resource_list(request):
    resources = Resource.objects.select_related(
        'course', 'module', 'lesson', 'session', 'author'
    ).annotate(feedback_count=Count('feedback', distinct=True)).order_by(
        '-published_at', '-created_at'
    )
    if not _is_manager(request.user):
        resources = resources.filter(
            Q(author=request.user) |
            Q(session__formateurs=request.user)
        ).distinct()

    query = (request.GET.get('q') or '').strip()
    kind = request.GET.get('kind') or ''
    status = request.GET.get('status') or ''
    if query:
        resources = resources.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )
    if kind:
        resources = resources.filter(kind=kind)
    if status:
        resources = resources.filter(status=status)

    paginator = Paginator(resources, 20)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'dashboard/pedagogie/resources.html', {
        'page': page,
        'query': query,
        'kind_filter': kind,
        'status_filter': status,
        'kind_choices': Resource.Kind.choices,
        'status_choices': Resource.Status.choices,
    })


@business_write_required(*MANAGE_ROLES)
def resource_create(request):
    course = None
    course_id = request.GET.get('course')
    if course_id:
        course = Course.objects.filter(id=course_id).first()
    if not course and not _is_manager(request.user):
        session = _my_sessions(request.user).select_related('course').first()
        course = session.course if session else None

    form = ResourceForm(course=course)
    if request.method == 'POST':
        form = ResourceForm(request.POST, request.FILES, course=course)
        if form.is_valid():
            resource = form.save(commit=False)
            resource.author = request.user
            if resource.status == Resource.Status.PUBLISHED:
                resource.published_at = timezone.now()
            resource.save()
            log_audit(request, 'RESOURCE_CREATE', 'Resource', str(resource.id),
                      after={'title': resource.title,
                             'status': resource.status,
                             'kind': resource.kind})
            messages.success(request, "Ressource enregistrée.")
            return redirect('core:dashboard:resources')
    return render(request, 'dashboard/pedagogie/resource_form.html', {
        'form': form, 'creating': True,
    })


@business_write_required(*MANAGE_ROLES)
def resource_edit(request, resource_id):
    resource = get_object_or_404(Resource, id=resource_id)
    if not _resource_access(request.user, resource):
        return render(request, 'dashboard/403.html', status=403)
    form = ResourceForm(instance=resource, course=resource.course)
    if request.method == 'POST':
        before = {'title': resource.title, 'status': resource.status}
        form = ResourceForm(
            request.POST, request.FILES, instance=resource,
            course=resource.course,
        )
        if form.is_valid():
            resource = form.save(commit=False)
            if resource.status == Resource.Status.PUBLISHED and not resource.published_at:
                resource.published_at = timezone.now()
            resource.save()
            log_audit(request, 'RESOURCE_EDIT', 'Resource', str(resource.id),
                      before=before,
                      after={'title': resource.title, 'status': resource.status})
            messages.success(request, "Ressource mise à jour.")
            return redirect('core:dashboard:resources')
    return render(request, 'dashboard/pedagogie/resource_form.html', {
        'form': form, 'resource': resource, 'creating': False,
    })


@role_required('FORMATEUR', 'RESP_PEDA', 'DIRECTION', 'ETUDIANT', 'SECRETAIRE')
def resource_download(request, resource_id):
    resource = get_object_or_404(Resource, id=resource_id)
    if not _resource_access(request.user, resource, student=True):
        log_audit(request, 'UNAUTHORIZED_FILE_ACCESS', 'Resource',
                  str(resource.id))
        raise Http404
    if not resource.file:
        raise Http404
    log_audit(request, 'FILE_ACCESS', 'Resource', str(resource.id))
    try:
        return FileResponse(
            resource.file.open('rb'),
            as_attachment=True,
            filename=resource.file.name.rsplit('/', 1)[-1],
        )
    except Exception:
        raise Http404


@role_required('FORMATEUR', 'RESP_PEDA', 'DIRECTION', 'ETUDIANT')
def resource_view(request, resource_id):
    resource = get_object_or_404(Resource, id=resource_id)
    if not _resource_access(request.user, resource, student=True):
        raise Http404
    is_student = (
        request.user.has_role('ETUDIANT') and not request.user.is_elevated
    )
    feedback = resource.feedback.select_related('student')
    my_feedback = None
    if is_student:
        my_feedback = feedback.filter(student=request.user).first()
    return render(request, 'dashboard/pedagogie/resource_view.html', {
        'resource': resource,
        'feedback': feedback,
        'my_feedback': my_feedback,
        'is_student': is_student,
        'feedback_form': ResourceFeedbackForm(),
    })


@role_required('ETUDIANT')
def resource_feedback(request, resource_id):
    if request.user.is_elevated:
        return HttpResponseForbidden(
            "Consultation seule : cette action relève du rôle métier."
        )
    resource = get_object_or_404(Resource, id=resource_id)
    if not _resource_access(request.user, resource, student=True):
        raise Http404
    if request.method != 'POST':
        return redirect('core:dashboard:resource-view', resource_id=resource.id)
    form = ResourceFeedbackForm(request.POST)
    if form.is_valid():
        rating = form.cleaned_data.get('rating')
        ResourceFeedback.objects.update_or_create(
            resource=resource,
            student=request.user,
            defaults={
                'rating': int(rating) if rating else None,
                'comment': (form.cleaned_data.get('comment') or '').strip(),
            },
        )
        log_audit(
            request, 'RESOURCE_FEEDBACK', 'Resource', str(resource.id),
            after={
                'student': str(request.user.id),
                'rating': rating or None,
                'comment': (form.cleaned_data.get('comment') or '')[:200],
            },
        )
        messages.success(request, "Merci, votre retour a été enregistré.")
        return redirect('core:dashboard:resource-view', resource_id=resource.id)
    is_student = True
    feedback = resource.feedback.select_related('student')
    my_feedback = feedback.filter(student=request.user).first()
    return render(request, 'dashboard/pedagogie/resource_view.html', {
        'resource': resource,
        'feedback': feedback,
        'my_feedback': my_feedback,
        'is_student': is_student,
        'feedback_form': form,
    }, status=400)


# ---------------------------------------------------------------------------
# Espace étudiant
# ---------------------------------------------------------------------------

@role_required('ETUDIANT')
def student_resources(request):
    enrollments = Enrollment.objects.filter(
        student=request.user
    ).select_related('session__course')
    courses = [e.session.course_id for e in enrollments]
    session_ids = [e.session_id for e in enrollments]

    resources = Resource.objects.filter(
        status=Resource.Status.PUBLISHED,
        course_id__in=courses,
    ).filter(
        Q(session__isnull=True) | Q(session_id__in=session_ids)
    ).select_related('course', 'module', 'lesson', 'session', 'author')

    course_id = request.GET.get('course') or ''
    kind = request.GET.get('kind') or ''
    query = (request.GET.get('q') or '').strip()
    if course_id:
        resources = resources.filter(course_id=course_id)
    if kind:
        resources = resources.filter(kind=kind)
    if query:
        resources = resources.filter(title__icontains=query)

    paginator = Paginator(resources.order_by('-published_at', '-created_at'), 20)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'dashboard/etudiant/resources.html', {
        'page': page,
        'enrollments': enrollments,
        'query': query,
        'kind_filter': kind,
        'course_filter': course_id,
        'kind_choices': Resource.Kind.choices,
        'today': timezone.localdate(),
    })


@role_required('ETUDIANT')
def student_attendance(request):
    attendances = Attendance.objects.filter(
        enrollment__student=request.user
    ).select_related(
        'enrollment__session__course', 'session_record'
    )
    status = request.GET.get('status') or ''
    date_from = request.GET.get('from') or ''
    date_to = request.GET.get('to') or ''
    if status:
        attendances = attendances.filter(status=status)
    if date_from:
        attendances = attendances.filter(date__gte=date_from)
    if date_to:
        attendances = attendances.filter(date__lte=date_to)

    totals = attendances.aggregate(
        total=Count('id'),
        presents=Count('id', filter=Q(status='PRESENT')),
        absents=Count('id', filter=Q(status='ABSENT')),
        retards=Count('id', filter=Q(status='LATE')),
        excuses=Count('id', filter=Q(status='EXCUSED')),
    )
    paginator = Paginator(attendances.order_by('-date'), 30)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'dashboard/etudiant/attendance.html', {
        'page': page,
        'totals': totals,
        'status_filter': status,
        'date_from': date_from,
        'date_to': date_to,
        'status_choices': Attendance.Status.choices,
    })


# ---------------------------------------------------------------------------
# Cahier de texte du formateur et fiches de cours des apprenants
# ---------------------------------------------------------------------------

def _can_write_session(user, session):
    """Écriture pédagogique : formateur affecté, responsable ou direction."""
    if user.is_elevated:
        return False
    if user.has_any_role('RESP_PEDA', 'DIRECTION'):
        return True
    return (
        user.has_role('FORMATEUR')
        and session.formateurs.filter(id=user.id).exists()
    )


def _textbook_records(session):
    """Lignes du cahier de texte, dans l'ordre chronologique."""
    return SessionRecord.objects.filter(session=session).select_related(
        'module', 'lesson', 'recorded_by'
    ).annotate(
        present_count=Count(
            'attendances',
            filter=~Q(attendances__status=Attendance.Status.ABSENT),
        )
    ).order_by('date', 'planned_start')


def _textbook_header(session):
    formateurs = ', '.join(
        f.display_label for f in session.formateurs.all()
    ) or '—'
    return {
        'formateur': formateurs,
        'filiere': session.course.domain or session.course.title,
        'classe': (
            f"{session.course.title} — du "
            f"{session.starts_at:%d/%m/%Y} au {session.ends_at:%d/%m/%Y}"
        ),
    }


def _textbook_context(request, session, form=None):
    records = list(_textbook_records(session))
    return {
        'session': session,
        'records': records,
        'can_edit': _can_write_session(request.user, session),
        'form': form or TextbookEntryForm(
            session=session,
            initial={
                'date': timezone.localdate(),
                'status': SessionRecord.Status.COMPLETED,
            },
        ),
        'header': _textbook_header(session),
        'totals': {
            'seances': len(records),
            'heures': round(sum(r.display_hours for r in records), 2),
            'apprenants': sum(r.displayed_attendee_count for r in records),
            'notions': sum(1 for r in records if r.content_covered.strip()),
        },
    }


@role_required(*PEDAGOGY_ROLES)
def textbook_index(request):
    sessions = _my_sessions(request.user).select_related(
        'course'
    ).prefetch_related('formateurs').annotate(
        record_count=Count('records', distinct=True)
    )
    query = (request.GET.get('q') or '').strip()
    if query:
        sessions = sessions.filter(
            Q(course__title__icontains=query) |
            Q(course__domain__icontains=query)
        )
    return render(request, 'dashboard/pedagogie/textbook_index.html', {
        'sessions': sessions.order_by('-starts_at', 'course__title'),
        'query': query,
    })


@role_required(*PEDAGOGY_ROLES)
def textbook_session(request, session_id):
    session = get_object_or_404(
        CourseSession.objects.select_related('course'), id=session_id
    )
    if not _can_access_session(request.user, session):
        return render(request, 'dashboard/403.html', status=403)
    return render(
        request, 'dashboard/pedagogie/textbook_session.html',
        _textbook_context(request, session),
    )


@business_write_required(*MANAGE_ROLES)
def textbook_create(request, session_id):
    session = get_object_or_404(
        CourseSession.objects.select_related('course'), id=session_id
    )
    if not _can_write_session(request.user, session):
        return render(request, 'dashboard/403.html', status=403)

    if request.method != 'POST':
        return redirect('core:dashboard:textbook-session',
                        session_id=session.id)

    form = TextbookEntryForm(request.POST, session=session)
    if form.is_valid():
        record = form.save(commit=False)
        record.session = session
        record.recorded_by = request.user
        if record.status == SessionRecord.Status.COMPLETED:
            record.actual_start = record.actual_start or record.planned_start
            record.actual_end = record.actual_end or record.planned_end
        if not record.topic and record.content_covered:
            record.topic = record.content_covered.strip()[:200]
        record.save()
        log_audit(
            request, 'SESSION_CREATE', 'SessionRecord', str(record.id),
            after={
                'source': 'cahier_de_texte',
                'session': str(session.id),
                'date': str(record.date),
                'status': record.status,
                'attendee_count': record.attendee_count,
            },
        )
        messages.success(request, "Séance enregistrée dans le cahier de texte.")
        return redirect('core:dashboard:textbook-session',
                        session_id=session.id)

    return render(
        request, 'dashboard/pedagogie/textbook_session.html',
        _textbook_context(request, session, form=form),
    )


@business_write_required(*MANAGE_ROLES)
def textbook_edit(request, record_id):
    record = get_object_or_404(_record_queryset(), id=record_id)
    if not _can_manage_record(request.user, record):
        return render(request, 'dashboard/403.html', status=403)

    form = TextbookEntryForm(session=record.session, instance=record)
    if request.method == 'POST':
        before = {
            'date': str(record.date),
            'content_covered': record.content_covered,
            'attendee_count': record.attendee_count,
            'notes': record.notes,
        }
        form = TextbookEntryForm(
            request.POST, session=record.session, instance=record
        )
        if form.is_valid():
            record = form.save(commit=False)
            record.recorded_by = request.user
            if record.status == SessionRecord.Status.COMPLETED:
                record.actual_start = record.actual_start or record.planned_start
                record.actual_end = record.actual_end or record.planned_end
            record.save()
            log_audit(
                request, 'SESSION_UPDATE', 'SessionRecord', str(record.id),
                before=before,
                after={
                    'source': 'cahier_de_texte',
                    'date': str(record.date),
                    'content_covered': record.content_covered,
                    'attendee_count': record.attendee_count,
                    'notes': record.notes,
                },
            )
            messages.success(request, "Ligne du cahier de texte mise à jour.")
            return redirect('core:dashboard:textbook-session',
                            session_id=record.session_id)

    return render(request, 'dashboard/pedagogie/textbook_form.html', {
        'form': form,
        'record': record,
        'session': record.session,
    })


@role_required(*PEDAGOGY_ROLES)
def textbook_print(request, session_id):
    session = get_object_or_404(
        CourseSession.objects.select_related('course'), id=session_id
    )
    if not _can_access_session(request.user, session):
        return render(request, 'dashboard/403.html', status=403)
    context = _textbook_context(request, session)
    context['today'] = timezone.localdate()
    return render(
        request, 'dashboard/pedagogie/textbook_print.html', context
    )


def _student_sessions(user):
    return Enrollment.objects.filter(
        student=user,
        status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED],
    ).select_related('session__course')


@role_required('ETUDIANT')
def student_notebook(request):
    if request.user.is_elevated:
        return render(request, 'dashboard/403.html', status=403)

    enrollments = list(_student_sessions(request.user))
    by_session = {e.session_id: e for e in enrollments}
    today = timezone.localdate()

    records = SessionRecord.objects.filter(
        session_id__in=list(by_session),
        status=SessionRecord.Status.COMPLETED,
        date__lte=today,
    ).select_related('session__course', 'module', 'lesson').order_by(
        '-date', '-planned_start'
    )

    query = (request.GET.get('q') or '').strip()
    session_filter = request.GET.get('session') or ''
    state = request.GET.get('etat') or ''
    if query:
        records = records.filter(
            Q(topic__icontains=query) |
            Q(content_covered__icontains=query) |
            Q(session__course__title__icontains=query)
        )
    if session_filter:
        records = records.filter(session_id=session_filter)

    notes = {
        note.session_record_id: note
        for note in StudentSessionNote.objects.filter(
            enrollment__student=request.user
        )
    }
    record_list = list(records)
    attendance_by_date = {
        attendance.date: attendance
        for attendance in Attendance.objects.filter(
            enrollment__student=request.user,
            date__in=[record.date for record in record_list],
        )
    }
    all_rows = [
        {'record': record, 'note': notes.get(record.id),
         'enrollment': by_session.get(record.session_id),
         'attendance': attendance_by_date.get(record.date)}
        for record in record_list
    ]
    stats = {
        'total': len(all_rows),
        'filled': sum(1 for row in all_rows if row['note']),
        'missing': sum(1 for row in all_rows if not row['note']),
    }

    rows = all_rows
    if state == 'a_remplir':
        rows = [row for row in rows if row['note'] is None]
    elif state == 'remplies':
        rows = [row for row in rows if row['note'] is not None]

    return render(request, 'dashboard/etudiant/notebook.html', {
        'rows': rows,
        'stats': stats,
        'enrollments': enrollments,
        'query': query,
        'session_filter': session_filter,
        'state_filter': state,
    })


@role_required('ETUDIANT')
def student_note_form(request, record_id):
    if request.user.is_elevated:
        return render(request, 'dashboard/403.html', status=403)

    record = get_object_or_404(
        SessionRecord.objects.select_related(
            'session__course', 'module', 'lesson'
        ),
        id=record_id,
    )
    enrollment = Enrollment.objects.filter(
        student=request.user, session=record.session
    ).first()
    if enrollment is None:
        raise Http404("Séance hors de votre parcours.")

    if record.status != SessionRecord.Status.COMPLETED:
        messages.error(
            request, "Cette séance n'est pas encore réalisée."
        )
        return redirect('core:dashboard:student-notebook')

    note = StudentSessionNote.objects.filter(
        enrollment=enrollment, session_record=record
    ).first()
    created = note is None
    form = StudentSessionNoteForm(instance=note)

    if request.method == 'POST':
        form = StudentSessionNoteForm(request.POST, instance=note)
        if form.is_valid():
            note = form.save(commit=False)
            note.enrollment = enrollment
            note.session_record = record
            note.save()
            log_audit(
                request,
                'STUDENT_NOTE_CREATE' if created else 'STUDENT_NOTE_UPDATE',
                'StudentSessionNote', str(note.id),
                after={
                    'record': str(record.id),
                    'notions_learned': note.notions_learned[:200],
                },
            )
            messages.success(
                request, "Votre fiche de cours a été enregistrée.")
            return redirect('core:dashboard:student-notebook')

    return render(request, 'dashboard/etudiant/notebook_form.html', {
        'form': form,
        'record': record,
        'note': note,
        'enrollment': enrollment,
        'attendance': Attendance.objects.filter(
            enrollment=enrollment, date=record.date
        ).first(),
    })



@role_required('ETUDIANT')
def student_course_sheet(request, session_id):
    """Feuille de suivi imprimable de l'apprenant pour une formation."""
    enrollment = get_object_or_404(
        Enrollment.objects.select_related(
            'session__course', 'student'
        ).prefetch_related('session__formateurs'),
        student=request.user,
        session_id=session_id,
    )
    notes = list(
        StudentSessionNote.objects.filter(enrollment=enrollment)
        .select_related('session_record')
        .order_by('session_record__date', 'session_record__planned_start')
    )
    return render(request, 'dashboard/etudiant/course_sheet.html', {
        'enrollment': enrollment,
        'notes': notes,
        'today': timezone.localdate(),
    })
