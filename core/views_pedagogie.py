"""Dashboard pédagogie : programmes, séances, présences et ressources."""
from datetime import date

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .decorators import role_required
from .forms import (
    LessonForm, ModuleForm, ResourceForm, SessionRecordForm,
)
from .models import (
    Attendance, Course, CourseSession, Enrollment, Lesson, Module, Resource,
    RoleKey, SessionRecord,
)
from .utils import log_audit

PEDAGOGY_ROLES = ('FORMATEUR', 'RESP_PEDA', 'DIRECTION', 'SECRETAIRE')
MANAGE_ROLES = ('FORMATEUR', 'RESP_PEDA', 'DIRECTION')


def _is_manager(user):
    return user.has_any_role('SUPER_ADMIN', 'RESP_PEDA', 'DIRECTION')


def _can_access_session(user, session):
    if _is_manager(user) or user.has_role('SECRETAIRE'):
        return True
    return session.formateurs.filter(id=user.id).exists()


def _my_sessions(user):
    if _is_manager(user) or user.has_role('SECRETAIRE'):
        return CourseSession.objects.all()
    return CourseSession.objects.filter(formateurs=user)


def _can_manage_record(user, record):
    if _is_manager(user):
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
        'can_manage': request.user.has_any_role(
            'RESP_PEDA', 'DIRECTION', 'SUPER_ADMIN'
        ),
    })


@role_required('RESP_PEDA', 'DIRECTION')
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


@role_required('RESP_PEDA', 'DIRECTION')
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


@role_required('RESP_PEDA', 'DIRECTION')
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


@role_required('RESP_PEDA', 'DIRECTION')
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


@role_required(*MANAGE_ROLES)
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
    if user.has_any_role('SUPER_ADMIN', 'RESP_PEDA', 'DIRECTION'):
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


@role_required(*MANAGE_ROLES)
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


@role_required(*MANAGE_ROLES)
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
    return render(request, 'dashboard/pedagogie/resource_view.html', {
        'resource': resource,
    })


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
