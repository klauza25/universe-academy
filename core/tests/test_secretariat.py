"""Tests du dashboard Secrétariat : étudiants, inscriptions et documents."""
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.models import (
    Contact, CourseSession, Enrollment, Payment, Prospect, RoleKey,
    StudentDocument, User,
)

from .base import BusinessTestBase


class SecretariatTestBase(BusinessTestBase):
    def setUp(self):
        self.client = self.client_for(self.secretaire)

    def student_payload(self, **overrides):
        payload = {
            'first_name': 'Nouveau',
            'last_name': 'Étudiant',
            'email': 'nouveau@test.local',
            'phone': '+242060000501',
            'address': 'Brazzaville',
            'birth_date': '2000-01-01',
            'password': 'NouveauPass123!',
            'session': self.session.pk,
            'status': Enrollment.Status.ACTIVE,
            'start_date': self.local_date(),
            'tariff_amount': '100000',
            'discount_amount': '10000',
            'payment_plan': '2 versements',
            'notes': '',
        }
        payload.update(overrides)
        return payload

    def make_second_session(self):
        return CourseSession.objects.create(
            course=self.course,
            starts_at=self.today + timedelta(days=10),
            ends_at=self.today + timedelta(days=100),
            status=CourseSession.Status.PLANNED,
        )


class StudentManagementTests(SecretariatTestBase):
    def test_student_list_renders_and_filters(self):
        response = self.client.get(reverse('core:dashboard:student-list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            self.etudiant,
            list(response.context['page'].object_list),
        )

        response = self.client.get(
            reverse('core:dashboard:student-list'),
            {'q': self.etudiant.internal_code},
        )
        self.assertEqual(
            [u.pk for u in response.context['page'].object_list],
            [self.etudiant.pk],
        )

        response = self.client.get(
            reverse('core:dashboard:student-list'), {'q': 'inexistant-xyz'})
        self.assertEqual(len(response.context['page'].object_list), 0)

    def test_student_create_persists_account_and_enrollment(self):
        response = self.client.post(
            reverse('core:dashboard:student-create'),
            self.student_payload(),
        )
        student = User.objects.get(email='nouveau@test.local')
        self.assertRedirects(
            response,
            reverse('core:dashboard:student-detail', args=[student.pk]),
            fetch_redirect_response=False,
        )
        self.assertTrue(student.check_password('NouveauPass123!'))
        self.assertTrue(student.has_role(RoleKey.ETUDIANT))
        self.assertTrue(student.internal_code.startswith('UA-ETU'))
        enrollment = Enrollment.objects.get(student=student)
        self.assertEqual(enrollment.tariff_amount, 100000)
        self.assertEqual(enrollment.discount_amount, 10000)
        self.assertEqual(enrollment.net_amount, 90000)
        self.assertEqual(enrollment.registered_by, self.secretaire)
        self.assert_audited('STUDENT_CREATE', student.pk)

    def test_student_create_without_password_creates_invitation(self):
        self.client.post(
            reverse('core:dashboard:student-create'),
            self.student_payload(email='invite@test.local', password=''),
        )
        student = User.objects.get(email='invite@test.local')
        self.assertFalse(student.has_usable_password())

    def test_student_create_rejects_duplicate_email(self):
        response = self.client.post(
            reverse('core:dashboard:student-create'),
            self.student_payload(email=self.etudiant.email),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            User.objects.filter(email__iexact=self.etudiant.email).count(), 1
        )
        self.assertEqual(Enrollment.objects.count(), 1)

    def test_student_create_from_prospect_marks_it_converted(self):
        contact = Contact.objects.create(
            first_name='Prosper', last_name='Mavoungou',
            phone='+242060000777', email='prosper@test.local',
        )
        prospect = Prospect.objects.create(
            contact=contact,
            source=Prospect.Source.VISIT,
            first_contact_at=self.today,
            agent=self.accueil,
            status=Prospect.Status.INTERESTED,
        )
        url = reverse('core:dashboard:student-create') + f'?prospect={prospect.pk}'
        payload = self.student_payload(
            first_name=contact.first_name,
            last_name=contact.last_name,
            email=contact.email,
            phone=contact.phone,
        )
        response = self.client.post(url, payload)
        student = User.objects.get(email=contact.email)
        self.assertRedirects(
            response,
            reverse('core:dashboard:student-detail', args=[student.pk]),
            fetch_redirect_response=False,
        )
        prospect.refresh_from_db()
        self.assertEqual(prospect.converted_student, student)
        self.assertIsNotNone(prospect.converted_at)
        self.assertEqual(prospect.status, Prospect.Status.ENROLLED)

    def test_student_edit_persists_and_is_audited(self):
        response = self.client.post(
            reverse('core:dashboard:student-edit', args=[self.etudiant.pk]),
            {
                'first_name': 'Alicia',
                'last_name': 'Mabiala',
                'phone': '+242060000888',
                'address': 'Pointe-Noire',
                'birth_date': '1999-05-04',
            },
        )
        self.assertRedirects(
            response,
            reverse('core:dashboard:student-detail', args=[self.etudiant.pk]),
            fetch_redirect_response=False,
        )
        self.etudiant.refresh_from_db()
        self.assertEqual(self.etudiant.first_name, 'Alicia')
        self.assertEqual(self.etudiant.phone, '+242060000888')
        self.assert_audited('STUDENT_EDIT', self.etudiant.pk)

    def test_student_detail_computes_totals(self):
        Payment.objects.create(
            enrollment=self.enrollment,
            amount=30000,
            method=Payment.Method.CASH,
            recorded_by=self.comptable,
        )
        response = self.client.get(
            reverse('core:dashboard:student-detail', args=[self.etudiant.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_due'], 90000)
        self.assertEqual(response.context['total_paid'], 30000)
        self.assertEqual(response.context['balance'], 60000)


class EnrollmentManagementTests(SecretariatTestBase):
    def test_enrollment_create_computes_net_amount(self):
        student = self.make_user(RoleKey.ETUDIANT, 'etudiant3@test.local')
        response = self.client.post(
            reverse('core:dashboard:enrollment-create'),
            {
                'student': student.pk,
                'session': self.session.pk,
                'status': Enrollment.Status.ACTIVE,
                'start_date': self.local_date(),
                'tariff_amount': '120000',
                'discount_amount': '20000',
                'payment_plan': '',
                'notes': '',
            },
        )
        enrollment = Enrollment.objects.get(student=student)
        self.assertRedirects(
            response,
            reverse('core:dashboard:enrollment-detail',
                    args=[enrollment.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(enrollment.net_amount, 100000)
        self.assertEqual(enrollment.registered_by, self.secretaire)
        self.assert_audited('ENROLLMENT_CREATE', enrollment.pk)

    def test_enrollment_rejects_discount_above_tariff(self):
        student = self.make_user(RoleKey.ETUDIANT, 'etudiant4@test.local')
        response = self.client.post(
            reverse('core:dashboard:enrollment-create'),
            {
                'student': student.pk,
                'session': self.session.pk,
                'status': Enrollment.Status.ACTIVE,
                'start_date': self.local_date(),
                'tariff_amount': '50000',
                'discount_amount': '60000',
                'payment_plan': '',
                'notes': '',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Enrollment.objects.filter(student=student).exists())

    def test_enrollment_rejects_duplicate_student_session(self):
        response = self.client.post(
            reverse('core:dashboard:enrollment-create'),
            {
                'student': self.etudiant.pk,
                'session': self.session.pk,
                'status': Enrollment.Status.ACTIVE,
                'start_date': self.local_date(),
                'tariff_amount': '100000',
                'discount_amount': '0',
                'payment_plan': '',
                'notes': '',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Enrollment.objects.filter(
                student=self.etudiant, session=self.session).count(),
            1,
        )

    def test_enrollment_edit_updates_status_and_amount(self):
        response = self.client.post(
            reverse('core:dashboard:enrollment-edit',
                    args=[self.enrollment.pk]),
            {
                'student': self.etudiant.pk,
                'session': self.session.pk,
                'status': Enrollment.Status.COMPLETED,
                'start_date': self.local_date(),
                'tariff_amount': '120000',
                'discount_amount': '20000',
                'payment_plan': 'Soldé',
                'notes': 'Dossier clos',
            },
        )
        self.assertRedirects(
            response,
            reverse('core:dashboard:enrollment-detail',
                    args=[self.enrollment.pk]),
            fetch_redirect_response=False,
        )
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, Enrollment.Status.COMPLETED)
        self.assertEqual(self.enrollment.net_amount, 100000)
        self.assertEqual(self.enrollment.notes, 'Dossier clos')
        self.assert_audited('ENROLLMENT_EDIT', self.enrollment.pk)

    def test_enrollment_detail_lists_payments(self):
        payment = Payment.objects.create(
            enrollment=self.enrollment, amount=25000,
            method=Payment.Method.CASH, recorded_by=self.comptable,
        )
        response = self.client.get(
            reverse('core:dashboard:enrollment-detail',
                    args=[self.enrollment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn(payment, list(response.context['payments']))


class StudentDocumentTests(SecretariatTestBase):
    def test_document_upload_persists_metadata(self):
        upload = SimpleUploadedFile(
            'piece-identite.pdf', b'%PDF-1.4 contenu de test',
            content_type='application/pdf',
        )
        response = self.client.post(
            reverse('core:dashboard:student-document-upload',
                    args=[self.etudiant.pk]),
            {
                'doc_type': StudentDocument.DocType.IDENTITY,
                'file': upload,
                'enrollment': self.enrollment.pk,
            },
        )
        self.assertRedirects(
            response,
            reverse('core:dashboard:student-detail', args=[self.etudiant.pk]),
            fetch_redirect_response=False,
        )
        document = StudentDocument.objects.get(student=self.etudiant)
        self.assertEqual(document.original_name, 'piece-identite.pdf')
        self.assertEqual(document.doc_type, StudentDocument.DocType.IDENTITY)
        self.assertEqual(document.enrollment, self.enrollment)
        self.assertEqual(document.size_bytes, upload.size)
        self.assertEqual(document.uploaded_by, self.secretaire)
        self.assertTrue(document.file.storage.exists(document.file.name))
        self.assert_audited('STUDENT_DOCUMENT_UPLOAD', document.pk)

    def test_document_is_downloadable_by_owner_and_staff(self):
        document = StudentDocument.objects.create(
            student=self.etudiant,
            doc_type=StudentDocument.DocType.IDENTITY,
            file=SimpleUploadedFile('piece.pdf', b'contenu'),
            original_name='piece.pdf',
            mime_type='application/pdf',
            size_bytes=7,
            uploaded_by=self.secretaire,
        )
        url = reverse('core:dashboard:student-document-download',
                      args=[document.pk])

        owner_client = self.client_for(self.etudiant)
        response = owner_client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'contenu')

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_document_is_not_downloadable_by_another_student(self):
        document = StudentDocument.objects.create(
            student=self.etudiant,
            doc_type=StudentDocument.DocType.IDENTITY,
            file=SimpleUploadedFile('prive.pdf', b'secret'),
            original_name='prive.pdf',
            mime_type='application/pdf',
            size_bytes=6,
            uploaded_by=self.secretaire,
        )
        other = self.make_user(RoleKey.ETUDIANT, 'autre@test.local')
        client = self.client_for(other)
        response = client.get(
            reverse('core:dashboard:student-document-download',
                    args=[document.pk]))
        self.assertEqual(response.status_code, 404)
