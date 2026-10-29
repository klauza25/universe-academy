"""Tests de la pédagogie : programmes, séances, présences et ressources."""
from datetime import time as dt_time, timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from core.forms import SessionRecordForm
from core.models import (
    Attendance, Course, CourseSession, Enrollment, Lesson, Module, Resource,
    RoleKey, SessionRecord,
)

from .base import BusinessTestBase


class PedagogyTestBase(BusinessTestBase):
    def setUp(self):
        self.trainer_client = self.client_for(self.formateur)
        self.manager_client = self.client_for(self.peda)

    def record_payload(self, **overrides):
        payload = {
            'date': self.local_date(),
            'planned_start': '08:00',
            'planned_end': '10:00',
            'actual_start': '',
            'actual_end': '',
            'module': self.module.pk,
            'lesson': self.lesson.pk,
            'topic': 'Introduction au HTML',
            'objectives': 'Comprendre les balises',
            'content_covered': '',
            'content_remaining': '',
            'next_content': '',
            'exercises_done': '',
            'difficulties': '',
            'notes': '',
            'status': SessionRecord.Status.PLANNED,
        }
        payload.update(overrides)
        return payload

    def make_record(self, **kwargs):
        defaults = {
            'session': self.session,
            'module': self.module,
            'lesson': self.lesson,
            'date': self.today,
            'planned_start': dt_time(8, 0),
            'planned_end': dt_time(10, 0),
            'topic': 'Séance de test',
            'status': SessionRecord.Status.PLANNED,
            'recorded_by': self.formateur,
        }
        defaults.update(kwargs)
        return SessionRecord.objects.create(**defaults)

    def make_resource(self, **kwargs):
        defaults = {
            'title': 'Support de cours',
            'course': self.course,
            'kind': Resource.Kind.COURSE,
            'status': Resource.Status.PUBLISHED,
            'author': self.formateur,
            'html_content': '<p>Contenu</p>',
        }
        defaults.update(kwargs)
        return Resource.objects.create(**defaults)


class ProgramTests(PedagogyTestBase):
    def test_manager_can_create_module_and_lesson(self):
        response = self.manager_client.post(
            reverse('core:dashboard:module-create'),
            {
                'course': self.course.pk,
                'title': 'Module CSS',
                'description': 'Mise en forme',
                'order': 2,
                'planned_hours': 15,
            },
        )
        self.assertRedirects(
            response, reverse('core:dashboard:programs'),
            fetch_redirect_response=False,
        )
        module = Module.objects.get(title='Module CSS')
        self.assert_audited('MODULE_CREATE', module.pk)

        response = self.manager_client.post(
            reverse('core:dashboard:lesson-create'),
            {
                'module': module.pk,
                'title': 'Sélecteurs CSS',
                'objectives': 'Savoir cibler les éléments',
                'order': 1,
                'planned_hours': 3,
            },
        )
        self.assertRedirects(
            response, reverse('core:dashboard:programs'),
            fetch_redirect_response=False,
        )
        lesson = Lesson.objects.get(title='Sélecteurs CSS')
        self.assert_audited('LESSON_CREATE', lesson.pk)

    def test_trainer_cannot_create_module(self):
        response = self.trainer_client.get(
            reverse('core:dashboard:module-create'))
        self.assertEqual(response.status_code, 403)


class SessionRecordTests(PedagogyTestBase):
    def test_trainer_can_create_record_for_his_session(self):
        response = self.trainer_client.post(
            reverse('core:dashboard:session-record-create',
                    args=[self.session.pk]),
            self.record_payload(),
        )
        record = SessionRecord.objects.get()
        self.assertRedirects(
            response,
            reverse('core:dashboard:session-record-detail',
                    args=[record.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(record.session, self.session)
        self.assertEqual(record.recorded_by, self.formateur)
        self.assert_audited('SESSION_CREATE', record.pk)

    def test_trainer_cannot_create_record_for_another_session(self):
        other_session = CourseSession.objects.create(
            course=self.course,
            starts_at=self.today,
            ends_at=self.today + timedelta(days=30),
            status=CourseSession.Status.ACTIVE,
        )
        response = self.trainer_client.get(
            reverse('core:dashboard:session-record-create',
                    args=[other_session.pk]))
        self.assertEqual(response.status_code, 403)

    def test_record_detail_is_reserved_to_assigned_trainer(self):
        record = self.make_record()
        response = self.trainer_client.get(
            reverse('core:dashboard:session-record-detail',
                    args=[record.pk]))
        self.assertEqual(response.status_code, 200)

        other = self.make_user(RoleKey.FORMATEUR, 'formateur2@test.local')
        other_client = self.client_for(other)
        response = other_client.get(
            reverse('core:dashboard:session-record-detail',
                    args=[record.pk]))
        self.assertEqual(response.status_code, 403)

    def test_completed_record_requires_actual_start(self):
        form = SessionRecordForm(
            data=self.record_payload(
                status=SessionRecord.Status.COMPLETED,
                actual_start='',
                actual_end='10:00',
            ),
            session=self.session,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('actual_start', form.errors)

    def test_planned_end_must_follow_start(self):
        form = SessionRecordForm(
            data=self.record_payload(planned_end='07:00'),
            session=self.session,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('planned_end', form.errors)

    def test_lesson_must_belong_to_selected_module(self):
        other_module = Module.objects.create(
            course=self.course, title='Module JavaScript', order=3,
        )
        form = SessionRecordForm(
            data=self.record_payload(module=other_module.pk),
            session=self.session,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('lesson', form.errors)

    def test_record_update_is_audited(self):
        record = self.make_record()
        payload = self.record_payload(
            topic='Séance réalisée',
            status=SessionRecord.Status.COMPLETED,
            actual_start='08:05',
            actual_end='09:50',
            content_covered='Balises de base',
        )
        response = self.trainer_client.post(
            reverse('core:dashboard:session-record-detail',
                    args=[record.pk]),
            payload,
        )
        self.assertRedirects(
            response,
            reverse('core:dashboard:session-record-detail',
                    args=[record.pk]),
            fetch_redirect_response=False,
        )
        record.refresh_from_db()
        self.assertEqual(record.status, SessionRecord.Status.COMPLETED)
        self.assertEqual(record.topic, 'Séance réalisée')
        self.assert_audited('SESSION_UPDATE', record.pk)


class AttendanceTests(PedagogyTestBase):
    def test_attendance_sheet_records_presence(self):
        record = self.make_record()
        response = self.trainer_client.post(
            reverse('core:dashboard:session-record-attendance',
                    args=[record.pk]),
            {
                f'status_{self.enrollment.pk}': Attendance.Status.LATE,
                f'arrival_{self.enrollment.pk}': '08:15',
                f'reason_{self.enrollment.pk}': '',
                f'note_{self.enrollment.pk}': 'Retard de transport',
            },
        )
        self.assertRedirects(
            response,
            reverse('core:dashboard:session-record-attendance',
                    args=[record.pk]),
            fetch_redirect_response=False,
        )
        attendance = Attendance.objects.get(enrollment=self.enrollment)
        self.assertEqual(attendance.status, Attendance.Status.LATE)
        self.assertEqual(attendance.arrival_time.strftime('%H:%M'), '08:15')
        self.assertEqual(attendance.session_record, record)
        self.assertEqual(attendance.recorded_by, self.formateur)
        self.assert_audited('ATTENDANCE_RECORD', record.pk)

    def test_invalid_status_is_ignored(self):
        record = self.make_record()
        self.trainer_client.post(
            reverse('core:dashboard:session-record-attendance',
                    args=[record.pk]),
            {f'status_{self.enrollment.pk}': 'INVENTE'},
        )
        self.assertEqual(Attendance.objects.count(), 0)

    def test_attendance_from_another_session_is_not_overwritten(self):
        day = self.today
        first = self.make_record(
            date=day,
            planned_start=dt_time(8, 0),
            planned_end=dt_time(10, 0),
        )
        second = self.make_record(
            date=day,
            planned_start=dt_time(10, 0),
            planned_end=dt_time(12, 0),
        )
        attendance = Attendance.objects.create(
            enrollment=self.enrollment,
            session_record=first,
            date=day,
            status=Attendance.Status.PRESENT,
            recorded_by=self.formateur,
        )
        self.trainer_client.post(
            reverse('core:dashboard:session-record-attendance',
                    args=[second.pk]),
            {f'status_{self.enrollment.pk}': Attendance.Status.ABSENT},
        )
        attendance.refresh_from_db()
        self.assertEqual(attendance.status, Attendance.Status.PRESENT)
        self.assertEqual(attendance.session_record, first)
        self.assertEqual(Attendance.objects.count(), 1)

    def test_secretary_can_read_but_not_edit_attendance(self):
        record = self.make_record()
        secretary_client = self.client_for(self.secretaire)
        url = reverse('core:dashboard:session-record-attendance',
                      args=[record.pk])
        response = secretary_client.get(url)
        self.assertEqual(response.status_code, 200)
        response = secretary_client.post(
            url, {f'status_{self.enrollment.pk}': Attendance.Status.PRESENT})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Attendance.objects.count(), 0)

    def test_attendance_history_filters(self):
        record = self.make_record()
        Attendance.objects.create(
            enrollment=self.enrollment, session_record=record,
            date=record.date, status=Attendance.Status.ABSENT,
            absence_reason='Maladie', recorded_by=self.formateur,
        )
        response = self.manager_client.get(
            reverse('core:dashboard:attendance-history'),
            {'status': Attendance.Status.ABSENT, 'q': 'Utilisateur'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['totals']['total'], 1)
        self.assertEqual(response.context['totals']['absents'], 1)

    def test_progression_page_supports_empty_session(self):
        response = self.manager_client.get(reverse('core:dashboard:progression'))
        self.assertEqual(response.status_code, 200)

    def test_progression_page_computes_hours(self):
        self.make_record(
            status=SessionRecord.Status.COMPLETED,
            actual_start=dt_time(8, 5),
            actual_end=dt_time(9, 55),
        )
        response = self.manager_client.get(reverse('core:dashboard:progression'))
        row = response.context['rows'][0]
        self.assertEqual(row['records'], 1)
        self.assertEqual(row['completed'], 1)
        self.assertEqual(row['planned_hours'], 2.0)
        self.assertAlmostEqual(row['actual_hours'], 1.83, places=2)
        self.assertIsNotNone(row['last_record'])


class ResourceTests(PedagogyTestBase):
    def test_published_resource_sets_publication_date(self):
        response = self.manager_client.post(
            reverse('core:dashboard:resource-create'),
            {
                'title': 'Introduction HTML',
                'description': 'Support du premier cours',
                'course': self.course.pk,
                'module': self.module.pk,
                'lesson': self.lesson.pk,
                'session': '',
                'kind': Resource.Kind.COURSE,
                'html_content': '<h1>Bonjour</h1>',
                'due_date': '',
                'status': Resource.Status.PUBLISHED,
            },
        )
        self.assertRedirects(
            response, reverse('core:dashboard:resources'),
            fetch_redirect_response=False,
        )
        resource = Resource.objects.get(title='Introduction HTML')
        self.assertEqual(resource.author, self.peda)
        self.assertIsNotNone(resource.published_at)
        self.assert_audited('RESOURCE_CREATE', resource.pk)

    def test_resource_requires_file_or_html(self):
        response = self.manager_client.post(
            reverse('core:dashboard:resource-create'),
            {
                'title': 'Ressource vide',
                'description': '',
                'course': self.course.pk,
                'module': '',
                'lesson': '',
                'session': '',
                'kind': Resource.Kind.COURSE,
                'html_content': '',
                'due_date': '',
                'status': Resource.Status.DRAFT,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Resource.objects.filter(title='Ressource vide').exists())

    def test_student_sees_only_published_resources_of_his_course(self):
        published = self.make_resource(title='Publié')
        self.make_resource(title='Brouillon', status=Resource.Status.DRAFT)
        other_course = Course.objects.create(
            title='Anglais', domain='Langues', fee_amount=50000,
        )
        self.make_resource(title='Autre cours', course=other_course)

        student_client = self.client_for(self.etudiant)
        response = student_client.get(reverse('core:dashboard:student-resources'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [r.pk for r in response.context['page'].object_list],
            [published.pk],
        )

    def test_student_can_download_published_resource(self):
        resource = self.make_resource(
            title='Support PDF',
            file=SimpleUploadedFile('support.pdf', b'%PDF-1.4 contenu'),
        )
        student_client = self.client_for(self.etudiant)
        response = student_client.get(
            reverse('core:dashboard:resource-download', args=[resource.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            b''.join(response.streaming_content), b'%PDF-1.4 contenu')
        self.assert_audited('FILE_ACCESS', resource.pk)

    def test_student_cannot_download_draft_resource(self):
        resource = self.make_resource(
            title='Brouillon privé',
            status=Resource.Status.DRAFT,
            file=SimpleUploadedFile('brouillon.pdf', b'secret'),
        )
        student_client = self.client_for(self.etudiant)
        response = student_client.get(
            reverse('core:dashboard:resource-download', args=[resource.pk]))
        self.assertEqual(response.status_code, 404)

    def test_student_cannot_view_draft_resource(self):
        resource = self.make_resource(
            title='Brouillon HTML', status=Resource.Status.DRAFT)
        student_client = self.client_for(self.etudiant)
        response = student_client.get(
            reverse('core:dashboard:resource-view', args=[resource.pk]))
        self.assertEqual(response.status_code, 404)
        published = self.make_resource(title='Publié HTML')
        response = student_client.get(
            reverse('core:dashboard:resource-view', args=[published.pk]))
        self.assertEqual(response.status_code, 200)

    def test_trainer_only_sees_his_own_or_session_resources(self):
        own = self.make_resource(title='Mon support', author=self.formateur)
        self.make_resource(title='Support du responsable', author=self.peda)
        response = self.trainer_client.get(reverse('core:dashboard:resources'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [r.pk for r in response.context['page'].object_list], [own.pk]
        )

    def test_other_trainer_cannot_edit_resource(self):
        resource = self.make_resource(title='Protégé', author=self.formateur)
        other = self.make_user(RoleKey.FORMATEUR, 'formateur3@test.local')
        other_client = self.client_for(other)
        response = other_client.get(
            reverse('core:dashboard:resource-edit', args=[resource.pk]))
        self.assertEqual(response.status_code, 403)

    def test_student_attendance_lists_only_his_records(self):
        record = self.make_record()
        Attendance.objects.create(
            enrollment=self.enrollment, session_record=record,
            date=record.date, status=Attendance.Status.PRESENT,
            recorded_by=self.formateur,
        )
        other_student = self.make_user(
            RoleKey.ETUDIANT, 'etudiant5@test.local')
        other_enrollment = Enrollment.objects.create(
            student=other_student, session=self.session,
            status=Enrollment.Status.ACTIVE, net_amount=50000,
        )
        Attendance.objects.create(
            enrollment=other_enrollment, session_record=record,
            date=record.date, status=Attendance.Status.ABSENT,
            recorded_by=self.formateur,
        )
        student_client = self.client_for(self.etudiant)
        response = student_client.get(reverse('core:dashboard:student-attendance'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [a.enrollment_id for a in response.context['page'].object_list],
            [self.enrollment.pk],
        )
        self.assertEqual(response.context['totals']['total'], 1)
