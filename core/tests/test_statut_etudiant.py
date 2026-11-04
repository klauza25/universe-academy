"""Statut par défaut d'un étudiant, approbation et comptes sortis des classeurs."""
import io
from datetime import timedelta

from django.core.management import call_command
from django.urls import reverse

from core.forms import StudentPaymentForm
from core.models import (
    AccountStatus, CourseSession, Enrollment, Payment, RoleKey, User,
)

from .base import BusinessTestBase


def silence():
    return io.StringIO()


class CreationDuCompteTests(BusinessTestBase):
    """Le secrétariat ouvre un compte : l'approbation reste un acte distinct."""

    def setUp(self):
        self.client = self.client_for(self.secretaire)

    def payload(self, **modifications):
        base = {
            'first_name': 'Nouvelle', 'last_name': 'Inscrite',
            'email': 'nouvelle@test.local', 'phone': '+242060000501',
            'address': 'Brazzaville', 'birth_date': '2000-01-01',
            'password': 'NouvellePass123!', 'session': self.session.pk,
            'status': Enrollment.Status.PENDING,
            'start_date': self.local_date(), 'tariff_amount': '100000',
            'discount_amount': '0', 'payment_plan': '', 'notes': '',
        }
        base.update(modifications)
        return base

    def test_un_dossier_en_attente_laisse_le_compte_en_attente(self):
        self.client.post(reverse('core:dashboard:student-create'), self.payload())
        student = User.objects.get(email='nouvelle@test.local')
        self.assertEqual(student.account_status, AccountStatus.PENDING_APPROVAL)

    def test_un_dossier_active_vaut_approbation_immediate(self):
        self.client.post(reverse('core:dashboard:student-create'),
                         self.payload(status=Enrollment.Status.ACTIVE))
        student = User.objects.get(email='nouvelle@test.local')
        self.assertEqual(student.account_status, AccountStatus.ACTIVE)


class ValidationDuDossierTests(BusinessTestBase):
    def valider(self, dossier):
        self.client = self.client_for(self.direction)
        self.client.post(reverse('core:dashboard:enrollment-validate',
                                 args=[dossier.pk]))

    def test_valider_l_inscription_approuve_le_compte_etudiant(self):
        student = self.make_user(RoleKey.ETUDIANT, 'attente@test.local',
                                 status=AccountStatus.PENDING_APPROVAL)
        dossier = Enrollment.objects.create(
            student=student, session=self.session,
            status=Enrollment.Status.PENDING, net_amount=90000,
        )
        self.valider(dossier)
        dossier.refresh_from_db()
        student.refresh_from_db()
        self.assertEqual(dossier.status, Enrollment.Status.ACTIVE)
        self.assertEqual(student.account_status, AccountStatus.ACTIVE)
        self.assertTrue(self.assert_audited('ENROLLMENT_VALIDATE', dossier.pk)
                        .after_summary['compte_approuve'])

    def test_un_compte_deja_approuve_n_est_pas_rapprouve(self):
        groupe = CourseSession.objects.create(
            course=self.course, starts_at=self.today,
            ends_at=self.today + timedelta(days=90),
            status=CourseSession.Status.PLANNED,
        )
        dossier = Enrollment.objects.create(
            student=self.etudiant, session=groupe,
            status=Enrollment.Status.PENDING, net_amount=90000,
        )
        self.valider(dossier)
        self.assertFalse(self.assert_audited('ENROLLMENT_VALIDATE', dossier.pk)
                         .after_summary['compte_approuve'])


class ComptesSortisDesClasseursTests(BusinessTestBase):
    """La vague 2 ouvrait ses fiches « Actif » : elles doivent être en attente."""

    def setUp(self):
        # Fiche de classeur reprise par l'import : aucun login distribué.
        self.importe = User.objects.create_user(
            email='fiche@classeur.local', password=None, first_name='Brivah',
            last_name='Louamba', account_status=AccountStatus.ACTIVE,
        )
        self.importe.roles.add(self.roles[RoleKey.ETUDIANT.value])
        self.groupe_clos = CourseSession.objects.create(
            course=self.course,
            starts_at=self.today - timedelta(days=400),
            ends_at=self.today - timedelta(days=130),
            status=CourseSession.Status.COMPLETED,
        )
        self.dossier = Enrollment.objects.create(
            student=self.importe, session=self.groupe_clos,
            status=Enrollment.Status.ACTIVE, net_amount=90000,
        )
        Payment.objects.create(enrollment=self.dossier, amount=20000,
                               status=Payment.Status.COMPLETED)
        # Compte ouvert à la main, avec login : son approbation ne se discute pas.
        self.ouvert_a_la_main = self.make_user(RoleKey.ETUDIANT, 'main@test.local')

    def test_sans_ecrire_rien_ne_bouge(self):
        call_command('mettre_en_attente', stdout=silence())
        self.importe.refresh_from_db()
        self.assertEqual(self.importe.account_status, AccountStatus.ACTIVE)

    def test_seul_le_compte_sorti_d_un_classeur_est_mis_en_attente(self):
        call_command('mettre_en_attente', '--ecrire', stdout=silence())
        self.importe.refresh_from_db()
        self.ouvert_a_la_main.refresh_from_db()
        self.etudiant.refresh_from_db()
        self.assertEqual(self.importe.account_status, AccountStatus.PENDING_APPROVAL)
        self.assertEqual(self.ouvert_a_la_main.account_status, AccountStatus.ACTIVE)
        self.assertEqual(self.etudiant.account_status, AccountStatus.ACTIVE)

    def test_relancer_ne_remplace_rien_de_plus(self):
        call_command('mettre_en_attente', '--ecrire', stdout=silence())
        sortie = silence()
        call_command('mettre_en_attente', '--ecrire', stdout=sortie)
        self.assertIn('déjà en attente', sortie.getvalue())

    def test_le_compte_en_attente_garde_inscription_et_paiements(self):
        call_command('mettre_en_attente', '--ecrire', stdout=silence())
        self.client = self.client_for(self.secretaire)
        response = self.client.get(reverse('core:dashboard:student-list'))
        self.assertIn(self.importe, list(response.context['page'].object_list))
        self.assertEqual(Payment.objects.filter(enrollment=self.dossier).count(), 1)
        self.assertEqual(Enrollment.objects.filter(student=self.importe).count(), 1)

    def test_un_compte_en_attente_n_est_plus_propose_a_la_caisse(self):
        call_command('mettre_en_attente', '--ecrire', stdout=silence())
        candidats = [u.pk for u in StudentPaymentForm().fields['student'].queryset]
        self.assertIn(self.etudiant.pk, candidats)
        self.assertNotIn(self.importe.pk, candidats)

    def compte_de_classeur(self, email, **champs):
        """Une fiche reprise par l'import : aucun login distribué."""
        eleve = User.objects.create_user(
            email=email, password=None, first_name=champs.get('prenom', 'Brivah'),
            last_name=champs.get('nom', 'Louamba'),
            account_status=AccountStatus.ACTIVE,
        )
        eleve.roles.add(self.roles[RoleKey.ETUDIANT.value])
        return eleve

    def test_l_option_approuve_les_cohortes_en_cours(self):
        en_cours = self.compte_de_classeur('encours@classeur.local',
                                           prenom='Gaston', nom='Enfer')
        Enrollment.objects.create(student=en_cours, session=self.session,
                                  status=Enrollment.Status.ACTIVE, net_amount=90000)
        call_command('mettre_en_attente', '--ecrire', '--approuver-en-cours',
                     stdout=silence())
        self.importe.refresh_from_db()
        en_cours.refresh_from_db()
        self.assertEqual(self.importe.account_status, AccountStatus.PENDING_APPROVAL)
        self.assertEqual(en_cours.account_status, AccountStatus.ACTIVE)

    def test_une_relance_ne_revoque_pas_les_approbations_donnees(self):
        en_cours = self.compte_de_classeur('encours@classeur.local',
                                           prenom='Gaston', nom='Enfer')
        Enrollment.objects.create(student=en_cours, session=self.session,
                                  status=Enrollment.Status.ACTIVE, net_amount=90000)
        call_command('mettre_en_attente', '--ecrire', '--approuver-en-cours',
                     stdout=silence())
        sortie = silence()
        call_command('mettre_en_attente', '--ecrire', stdout=sortie)
        en_cours.refresh_from_db()
        self.assertEqual(en_cours.account_status, AccountStatus.ACTIVE)
        self.assertIn('réparation déjà appliquée', sortie.getvalue())
        self.assertIn('à mettre en attente d’approbation : 0', sortie.getvalue())

    def test_l_apercu_annonce_ce_qu_il_va_faire(self):
        sortie = silence()
        call_command('mettre_en_attente', stdout=sortie)
        self.assertIn('Prévisualisation', sortie.getvalue())
        self.assertIn('à mettre en attente d’approbation : 1 (0 déjà en attente)',
                      sortie.getvalue())
