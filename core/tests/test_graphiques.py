"""Tests des séries numériques des graphiques de tableau de bord.

Deux pièges sont verrouillés ici, parce qu'ils ne se voient pas à l'écran :
un mois doit apparier ses écritures même si ``TruncMonth`` rend un datetime, et
un trop-perçu sur une fiche ne doit jamais effacer la dette de la fiche voisine.
"""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from core import graphiques
from core.models import (
    Attendance, CashTransaction, Course, CourseSession, Enrollment, Payment,
)
from core.tests.base import BusinessTestBase


class EncaissementsTests(BusinessTestBase):
    """Entrées et sorties de caisse, mois par mois."""

    def setUp(self):
        super().setUp()
        self.jour_du_mois = timezone.localdate().replace(day=1)

    def ecriture(self, tx_type, montant, statut=CashTransaction.Status.VALIDATED, jour=0):
        return CashTransaction.objects.create(
            tx_type=tx_type, category=self.income_category, label='Test de caisse',
            amount=montant, account=self.cash, status=statut,
            occurred_at=timezone.localtime(
                timezone.now().replace(hour=16, minute=30)
            ) + timedelta(days=jour),
            created_by=self.comptable,
        )

    def test_truncmonth_apparie_le_malgre_un_champ_date_temps(self):
        # Sans la normalisation date()/datetime(), la série resterait à zéro.
        self.ecriture(CashTransaction.Type.IN, 40000)
        self.assertEqual(graphiques.encaissements_par_mois()['series'][0]['valeurs'][-1],
                         40000)

    def test_les_sorties_passent_en_negatif_et_le_solde_les_summe(self):
        self.ecriture(CashTransaction.Type.IN, 30000)
        self.ecriture(CashTransaction.Type.OUT, 12000)
        series = graphiques.encaissements_par_mois()['series']
        self.assertEqual([s['valeurs'][-1] for s in series], [30000, -12000, 18000])

    def test_une_ecriture_en_attente_ou_annulee_ne_compte_pas(self):
        self.ecriture(CashTransaction.Type.IN, 50000,
                      statut=CashTransaction.Status.DRAFT)
        self.ecriture(CashTransaction.Type.IN, 50000,
                      statut=CashTransaction.Status.CANCELLED)
        self.assertEqual(graphiques.encaissements_par_mois()['series'][0]['valeurs'][-1], 0)

    def test_un_transfert_n_est_ni_une_entree_ni_une_sortie(self):
        CashTransaction.objects.create(
            tx_type=CashTransaction.Type.TRANSFER, category=self.transfer_category,
            label='Alimentation de caisse', amount=80000, account=self.cash,
            destination_account=self.mobile, created_by=self.comptable,
        )
        total = sum(sum(s['valeurs']) for s in graphiques.encaissements_par_mois()['series'])
        self.assertEqual(total, 0)

    def test_une_base_vide_rend_douze_mois_et_des_zeros(self):
        graphique = graphiques.encaissements_par_mois(nombre=12)
        self.assertEqual(len(graphique['labels']), 12)
        for serie in graphique['series']:
            self.assertEqual(serie['valeurs'], [0] * 12)

    def test_le_mois_hors_fenetre_laisse_la_place_vide(self):
        self.ecriture(CashTransaction.Type.IN, 25000, jour=-400)
        self.assertEqual(sum(graphiques.encaissements_par_mois()['series'][0]['valeurs']), 0)


class EffectifsTests(BusinessTestBase):
    """Effectifs par formation, la queue des petites promotions étant regroupée."""

    def inscription_dans(self, titre, effectif):
        course = Course.objects.create(title=titre, domain='Informatique',
                                       duration_months=9, fee_amount=180000)
        session = CourseSession.objects.create(
            course=course, starts_at=self.today,
            ends_at=self.today + timedelta(days=270), schedule='Test',
            status=CourseSession.Status.ACTIVE,
        )
        for rang in range(effectif):
            eleve = self.make_user('ETUDIANT', f'{titre}-{rang}@test.local')
            Enrollment.objects.create(
                student=eleve, session=session, status=Enrollment.Status.ACTIVE,
                tariff_amount=180000, net_amount=180000, registered_by=self.secretaire,
            )

    def test_une_inscription_en_attente_n_est_pas_comptee(self):
        autre = self.make_user('ETUDIANT', 'eleve-attente@test.local')
        Enrollment.objects.create(
            student=autre, session=self.session, status=Enrollment.Status.PENDING,
            tariff_amount=100000, net_amount=100000, registered_by=self.secretaire,
        )
        self.assertEqual(graphiques.eleves_par_formation()['series'][0]['valeurs'], [1])

    def test_les_petites_formations_se_regroupent_sans_perdre_un_eleve(self):
        self.inscription_dans('Grosse promotion', 6)
        self.inscription_dans('Petite promotion', 1)
        graphique = graphiques.eleves_par_formation(limite=1)
        self.assertEqual(len(graphique['labels']), 2)
        self.assertIn('Autres', graphique['labels'][-1])
        self.assertEqual(
            sum(graphique['series'][0]['valeurs']),
            Enrollment.objects.filter(status__in=graphiques.INSCRITS).count())

    def test_une_base_vide_laisse_le_graphique_vide(self):
        Enrollment.objects.all().delete()
        graphique = graphiques.eleves_par_formation()
        self.assertEqual(graphique['labels'], [])
        self.assertEqual(graphique['series'][0]['valeurs'], [])


class RestesTests(BusinessTestBase):
    """Ce qui reste à réclamer, dossier par dossier avant regroupement."""

    def paiement(self, dossier, montant):
        Payment.objects.create(enrollment=dossier, amount=montant,
                               method=Payment.Method.CASH, recorded_by=self.comptable)

    def test_un_trop_percu_ne_reduit_pas_la_dette_d_un_voisin(self):
        self.paiement(self.enrollment, 95000)
        endette = self.make_user('ETUDIANT', 'eleve-endette@test.local')
        Enrollment.objects.create(
            student=endette, session=self.session, status=Enrollment.Status.ACTIVE,
            tariff_amount=90000, net_amount=90000, registered_by=self.secretaire,
        )
        graphique = graphiques.restes_par_formation()
        self.assertEqual(graphique['series'][0]['valeurs'], [90000])
        self.assertEqual(graphique['total'], 90000)

    def test_un_dossier_solde_quitte_le_graphique(self):
        self.paiement(self.enrollment, 90000)
        self.assertEqual(graphiques.restes_par_formation()['labels'], [])
        self.assertEqual(graphiques.restes_par_formation()['total'], 0)

    def test_un_paiement_en_attente_ne_paye_rien(self):
        Payment.objects.create(enrollment=self.enrollment, amount=90000,
                               method=Payment.Method.CASH, status=Payment.Status.PENDING,
                               recorded_by=self.comptable)
        self.assertEqual(graphiques.restes_par_formation()['total'], 90000)

    def test_le_total_cumule_meme_les_formations_hors_affichage(self):
        for rang in range(10):
            course = Course.objects.create(title=f'Formation {rang}', domain='Gestion',
                                           duration_months=9, fee_amount=180000)
            session = CourseSession.objects.create(
                course=course, starts_at=self.today,
                ends_at=self.today + timedelta(days=270), schedule='Test',
                status=CourseSession.Status.ACTIVE,
            )
            Enrollment.objects.create(
                student=self.make_user('ETUDIANT', f'reste-{rang}@test.local'),
                session=session, status=Enrollment.Status.ACTIVE,
                tariff_amount=180000, net_amount=180000, registered_by=self.secretaire,
            )
        graphique = graphiques.restes_par_formation(limite=3)
        self.assertEqual(len(graphique['labels']), 3)
        self.assertEqual(graphique['total'], 180000 * 10 + 90000)


class AssiduiteTests(BusinessTestBase):
    """Feuilles d'appel, mois par mois, avec le taux de présence."""

    def setUp(self):
        super().setUp()
        self.premier_du_mois = timezone.localdate().replace(day=1)

    def appel(self, statut, jour):
        Attendance.objects.create(enrollment=self.enrollment,
                                  date=self.premier_du_mois + timedelta(days=jour),
                                  status=statut, recorded_by=self.peda)

    def test_le_taux_compte_present_et_retard_contre_toutes_les_feuilles(self):
        self.appel(Attendance.Status.PRESENT, 0)
        self.appel(Attendance.Status.LATE, 1)
        self.appel(Attendance.Status.ABSENT, 2)
        graphique = graphiques.assiduite_par_mois()
        self.assertEqual([s['valeurs'][-1] for s in graphique['series'][:3]], [1, 1, 1])
        taux = graphique['series'][-1]
        self.assertEqual(taux['axe'], 'secondaire')
        self.assertEqual(taux['valeurs'][-1], 66.7)

    def test_un_mois_sans_feuille_d_appel_rend_zero_sans_diviser_par_zero(self):
        self.assertEqual(graphiques.assiduite_par_mois()['series'][-1]['valeurs'],
                         [0] * 6)

    def test_l_assiduite_porte_quatre_series_dont_une_courbe(self):
        graphique = graphiques.assiduite_par_mois()
        self.assertEqual([s['type'] for s in graphique['series'] if 'type' in s], ['line'])
        self.assertEqual(len(graphique['series']), 4)


class TableauDeBordGraphiqueTests(BusinessTestBase):
    """La vue pose les séries et les scripts : le rendu reste dans le navigateur."""

    def test_la_page_direction_porte_ses_quatre_graphiques(self):
        page = self.client_for(self.direction).get(
            reverse('core:dashboard:direction-dashboard'))
        self.assertEqual(page.status_code, 200)
        for identifiant in ('encaissements', 'effectifs', 'restes', 'assiduite'):
            self.assertContains(page, f'data-chart-source="{identifiant}"')
        self.assertContains(page, 'chart.umd.min.js')

    def test_la_page_comptable_ne_rend_pas_un_graphique_pedagogique(self):
        page = self.client_for(self.comptable).get(
            reverse('core:dashboard:comptabilite-dashboard'))
        self.assertContains(page, 'data-chart-source="restes"')
        self.assertNotContains(page, 'data-chart-source="assiduite"')

    def test_la_page_pedagogique_ignore_les_ecritures_de_caisse(self):
        page = self.client_for(self.peda).get(
            reverse('core:dashboard:resp-peda-dashboard'))
        self.assertContains(page, 'data-chart-source="assiduite"')
        self.assertNotContains(page, 'data-chart-source="encaissements"')
