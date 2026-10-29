"""Tests du dashboard Accueil : visites, prospects et relances."""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from core.models import Contact, Prospect, ProspectFollowUp, Visit, VisitReason

from .base import BusinessTestBase


class AccueilTestBase(BusinessTestBase):
    @classmethod
    def make_contact(cls, first='Alice', last='Mabiala',
                     phone='+242060000001', email=''):
        return Contact.objects.create(
            first_name=first, last_name=last, phone=phone, email=email,
        )

    @classmethod
    def make_visit(cls, contact=None, status=Visit.Status.IN_PROGRESS,
                   arrival_at=None):
        contact = contact or cls.make_contact()
        return Visit.objects.create(
            contact=contact,
            visitor_type=Visit.VisitorType.PROSPECT,
            reason=cls.visit_reason,
            request_description='Demande de renseignements',
            arrival_at=arrival_at or timezone.now(),
            status=status,
            agent=cls.accueil,
        )

    @classmethod
    def make_prospect(cls, contact=None, **kwargs):
        contact = contact or cls.make_contact()
        defaults = {
            'contact': contact,
            'source': Prospect.Source.VISIT,
            'first_contact_at': timezone.localdate(),
            'agent': cls.accueil,
            'status': Prospect.Status.NEW,
        }
        defaults.update(kwargs)
        return Prospect.objects.create(**defaults)

    def setUp(self):
        self.client = self.client_for(self.accueil)

    def visit_payload(self, **overrides):
        payload = {
            'visitor_type': Visit.VisitorType.PROSPECT,
            'reason': self.visit_reason.pk,
            'request_description': 'Je souhaite des informations',
            'host_service': 'Accueil',
            'host_person': 'Sarah',
            'arrival_at': self.local_datetime(),
            'departure_at': '',
            'status': Visit.Status.IN_PROGRESS,
            'notes': '',
            'first_name': 'Alice',
            'last_name': 'Mabiala',
            'phone': '+242060000001',
            'secondary_phone': '',
            'email': 'alice@test.local',
        }
        payload.update(overrides)
        return payload

    def prospect_payload(self, **overrides):
        payload = {
            'course': self.course.pk,
            'domain': 'Informatique',
            'level': 'Débutant',
            'language_program': '',
            'desired_start': 'janvier 2027',
            'preferred_contact': Prospect.ContactMethod.PHONE,
            'source': Prospect.Source.CALL,
            'first_contact_at': self.local_date(),
            'interest_reason': 'Développement web',
            'comments': '',
            'status': Prospect.Status.TO_CONTACT,
            'next_follow_up': '',
            'first_name': 'Bertrand',
            'last_name': 'Okemba',
            'phone': '+242060000002',
            'secondary_phone': '',
            'email': 'bertrand@test.local',
        }
        payload.update(overrides)
        return payload


class VisitTests(AccueilTestBase):
    def test_visit_list_renders(self):
        self.make_visit()
        response = self.client.get(reverse('core:dashboard:visit-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['page'].object_list), 1)

    def test_visit_list_search_and_status_filter(self):
        alice = self.make_contact('Alice', 'Mabiala', '+242060000001')
        bruno = self.make_contact('Bruno', 'Nkodia', '+242060000099')
        self.make_visit(contact=alice)
        self.make_visit(contact=bruno, status=Visit.Status.COMPLETED)

        response = self.client.get(
            reverse('core:dashboard:visit-list'), {'q': 'Alice'})
        self.assertEqual(
            [v.contact.first_name for v in response.context['page'].object_list],
            ['Alice'],
        )
        response = self.client.get(
            reverse('core:dashboard:visit-list'),
            {'status': Visit.Status.COMPLETED},
        )
        self.assertEqual(
            [v.contact.first_name for v in response.context['page'].object_list],
            ['Bruno'],
        )

    def test_visit_create_persists_contact_and_visit(self):
        response = self.client.post(
            reverse('core:dashboard:visit-create'), self.visit_payload()
        )
        visit = Visit.objects.get()
        self.assertRedirects(
            response,
            reverse('core:dashboard:visit-detail', args=[visit.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(visit.contact.first_name, 'Alice')
        self.assertEqual(visit.contact.phone, '+242060000001')
        self.assertEqual(visit.agent, self.accueil)
        self.assert_audited('VISIT_CREATE', visit.pk)

    def test_visit_create_reuses_existing_contact_by_phone(self):
        existing = self.make_contact('Alice', 'Mabiala', '+242060000001')
        self.client.post(
            reverse('core:dashboard:visit-create'), self.visit_payload())
        self.client.post(
            reverse('core:dashboard:visit-create'),
            self.visit_payload(request_description='Deuxième visite'),
        )
        self.assertEqual(Contact.objects.count(), 1)
        self.assertEqual(Visit.objects.count(), 2)
        self.assertTrue(Visit.objects.filter(contact=existing).exists())

    def test_visit_create_rejects_departure_before_arrival(self):
        payload = self.visit_payload(
            arrival_at='2026-10-29T10:00',
            departure_at='2026-10-29T09:00',
        )
        response = self.client.post(
            reverse('core:dashboard:visit-create'), payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Visit.objects.count(), 0)

    def test_visit_departure_is_recorded_once(self):
        visit = self.make_visit()
        response = self.client.post(
            reverse('core:dashboard:visit-departure', args=[visit.pk]))
        self.assertRedirects(
            response,
            reverse('core:dashboard:visit-detail', args=[visit.pk]),
            fetch_redirect_response=False,
        )
        visit.refresh_from_db()
        self.assertIsNotNone(visit.departure_at)
        self.assertEqual(visit.status, Visit.Status.COMPLETED)
        first_departure = visit.departure_at
        self.assert_audited('VISIT_DEPARTURE', visit.pk)

        self.client.post(
            reverse('core:dashboard:visit-departure', args=[visit.pk]))
        visit.refresh_from_db()
        self.assertEqual(visit.departure_at, first_departure)

    def test_visit_is_converted_to_prospect_only_once(self):
        visit = self.make_visit()
        response = self.client.post(
            reverse('core:dashboard:visit-to-prospect', args=[visit.pk]))
        prospect = Prospect.objects.get()
        self.assertRedirects(
            response,
            reverse('core:dashboard:prospect-detail', args=[prospect.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(prospect.contact_id, visit.contact_id)
        self.assertEqual(prospect.visit_id, visit.pk)
        self.assertEqual(prospect.source, Prospect.Source.VISIT)
        self.assertEqual(prospect.status, Prospect.Status.TO_CONTACT)
        self.assert_audited('PROSPECT_FROM_VISIT', prospect.pk)

        self.client.post(
            reverse('core:dashboard:visit-to-prospect', args=[visit.pk]))
        self.assertEqual(Prospect.objects.count(), 1)

    def test_visit_detail_update_persists(self):
        visit = self.make_visit()
        payload = self.visit_payload(
            request_description='Demande mise à jour',
            status=Visit.Status.COMPLETED,
            notes='Traité',
        )
        response = self.client.post(
            reverse('core:dashboard:visit-detail', args=[visit.pk]), payload)
        self.assertRedirects(
            response,
            reverse('core:dashboard:visit-detail', args=[visit.pk]),
            fetch_redirect_response=False,
        )
        visit.refresh_from_db()
        self.assertEqual(visit.request_description, 'Demande mise à jour')
        self.assertEqual(visit.status, Visit.Status.COMPLETED)
        self.assert_audited('VISIT_UPDATE', visit.pk)


class ProspectTests(AccueilTestBase):
    def test_prospect_list_search_and_due_filter(self):
        overdue = self.make_prospect(
            contact=self.make_contact('Céline', 'Bantsimba', '+242060000010'),
            next_follow_up=timezone.localdate() - timedelta(days=3),
        )
        today = self.make_prospect(
            contact=self.make_contact('David', 'Loemba', '+242060000011'),
            next_follow_up=timezone.localdate(),
        )
        response = self.client.get(reverse('core:dashboard:prospect-list'))
        self.assertEqual(len(response.context['page'].object_list), 2)

        response = self.client.get(
            reverse('core:dashboard:prospect-list'),
            {'due': 'overdue'},
        )
        self.assertEqual(
            [p.pk for p in response.context['page'].object_list], [overdue.pk]
        )
        response = self.client.get(
            reverse('core:dashboard:prospect-list'),
            {'due': 'today'},
        )
        self.assertEqual(
            [p.pk for p in response.context['page'].object_list], [today.pk]
        )
        response = self.client.get(
            reverse('core:dashboard:prospect-list'),
            {'q': 'Céline'},
        )
        self.assertEqual(
            [p.pk for p in response.context['page'].object_list], [overdue.pk]
        )

    def test_prospect_create_persists(self):
        response = self.client.post(
            reverse('core:dashboard:prospect-create'),
            self.prospect_payload(),
        )
        prospect = Prospect.objects.get()
        self.assertRedirects(
            response,
            reverse('core:dashboard:prospect-detail', args=[prospect.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(prospect.contact.last_name, 'Okemba')
        self.assertEqual(prospect.course, self.course)
        self.assertEqual(prospect.agent, self.accueil)
        self.assertTrue(prospect.reference.startswith('PRO-'))
        self.assert_audited('PROSPECT_CREATE', prospect.pk)

    def test_prospect_edit_updates_status(self):
        prospect = self.make_prospect()
        payload = self.prospect_payload(
            first_name=prospect.contact.first_name,
            last_name=prospect.contact.last_name,
            phone=prospect.contact.phone,
            email=prospect.contact.email,
            status=Prospect.Status.INTERESTED,
            comments='Très motivé',
        )
        response = self.client.post(
            reverse('core:dashboard:prospect-detail', args=[prospect.pk]),
            payload,
        )
        self.assertRedirects(
            response,
            reverse('core:dashboard:prospect-detail', args=[prospect.pk]),
            fetch_redirect_response=False,
        )
        prospect.refresh_from_db()
        self.assertEqual(prospect.status, Prospect.Status.INTERESTED)
        self.assertEqual(prospect.comments, 'Très motivé')
        self.assert_audited('PROSPECT_UPDATE', prospect.pk)

    def test_prospect_follow_up_updates_status_and_next_date(self):
        prospect = self.make_prospect()
        next_date = timezone.localdate() + timedelta(days=7)
        response = self.client.post(
            reverse('core:dashboard:prospect-detail', args=[prospect.pk]),
            {
                'action': 'follow_up',
                'occurred_at': self.local_datetime(),
                'contact_type': ProspectFollowUp.ContactType.CALL,
                'phone_used': prospect.contact.phone,
                'summary': 'Appel effectué, document envoyé',
                'info_given': 'Programme et tarifs',
                'course': self.course.pk,
                'outcome': 'Intéressé',
                'next_action': 'Rappeler',
                'next_follow_up': next_date.strftime('%Y-%m-%d'),
            },
        )
        self.assertRedirects(
            response,
            reverse('core:dashboard:prospect-detail', args=[prospect.pk]),
            fetch_redirect_response=False,
        )
        prospect.refresh_from_db()
        self.assertEqual(prospect.status, Prospect.Status.CONTACTED)
        self.assertEqual(prospect.next_follow_up, next_date)
        follow_up = ProspectFollowUp.objects.get(prospect=prospect)
        self.assertEqual(follow_up.agent, self.accueil)
        self.assertEqual(follow_up.summary, 'Appel effectué, document envoyé')
        self.assert_audited('PROSPECT_FOLLOW_UP', prospect.pk)

    def test_visit_reason_can_be_created_and_toggled(self):
        response = self.client.post(
            reverse('core:dashboard:visit-reasons'),
            {'label': 'Nouveau motif', 'order': 5, 'active': 'on'},
        )
        self.assertRedirects(
            response, reverse('core:dashboard:visit-reasons'),
            fetch_redirect_response=False,
        )
        reason = VisitReason.objects.get(label='Nouveau motif')
        self.assertTrue(reason.active)
        self.assert_audited('VISIT_REASON_CREATE', reason.pk)

        self.client.post(
            reverse('core:dashboard:visit-reason-toggle', args=[reason.pk]))
        reason.refresh_from_db()
        self.assertFalse(reason.active)
        self.assert_audited('VISIT_REASON_TOGGLE', reason.pk)

    def test_contact_search_requires_three_characters(self):
        contact = self.make_contact('Recherche', 'Contact', '+242060000123')
        response = self.client.get(
            reverse('core:dashboard:contact-search'), {'q': 'Re'})
        self.assertEqual(len(response.context['contacts']), 0)
        response = self.client.get(
            reverse('core:dashboard:contact-search'), {'q': 'Reche'})
        self.assertEqual(
            [c.pk for c in response.context['contacts']], [contact.pk]
        )
