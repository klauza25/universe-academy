"""Aucun mélange de langue : rendu anglais contrôlé page par page.

`verifier_i18n` garantit que le code est balisé et traduit ; ce test garantit le
rendu. Il parcourt les neuf tableaux de bord et les pages publiques en anglais,
puis refuse toute chrome française encore visible. Le contenu saisi par les
agents (intitulés d'inscription, caisses, catégories, motifs de visite, libellés
de rôles stockés en base) reste en français : il est retiré du texte analysé.
"""

import re

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from core.models import (
    CashAccount, CashTransaction, Course, CourseSession, Lesson, Module,
    Payment, Role, RoleKey, ROLES_DISSOUS, TransactionCategory, VisitReason,
)
from core.tests.base import BusinessTestBase

User = get_user_model()

COMMENTAIRE_RE = re.compile(r'<!--.*?-->', re.DOTALL)
STYLE_RE = re.compile(r'<style.*?</style>', re.DOTALL | re.IGNORECASE)

MOTS_FRANCAIS = (
    'Enregistrer', 'Rechercher', 'Valider', 'Annuler', 'Précédent', 'Suivant',
    'Se déconnecter', 'Déconnexion', 'Tableau de bord', 'Retour', 'Filtrer',
    'Aucun', 'Aucune', 'Inscription', 'Formations', 'Séances', 'Leçons',
    'Présence', 'Absents', 'Utilisateurs', 'Rôles', 'Profil', 'Visites',
    'Bourses', 'Candidature', 'Recettes', 'Dépenses', 'Solde', 'Clôture',
    'Motif', 'Montant', 'Libellé', 'Statut', 'Étudiant', 'Caisse',
    'Encaissable', 'Toutes', 'Tous', 'Voir', 'Ajouter', 'Modifier',
    'Supprimer', 'Choisir', 'Créer', 'Nouveau', 'Nouvelle',
)

# Contenu de base de données, volontairement en français : la plateforme ne
# traduit pas ce que les agents saisissent ou ce que les migrations sèment.
# Cette liste ne couvre que le jeu d'essai ; le reste est dérivé de la base.
DONNEES = (
    'Développement Web', 'Module HTML', 'Les bases du HTML', 'Cours de test',
    'Caisse principale', 'Lun-Ven 08h-10h', 'Nouveau Guichet', 'Univers Academy',
)


class RenduAnglaisSansMelangeTest(BusinessTestBase):
    @property
    def users_by_role(self):
        return {
            'SUPER_ADMIN': self.super_admin,
            'ADMIN': self.admin,
            'DIRECTION': self.direction,
            'ASSISTANT_ADMIN': self.assistant,
            'SECRETAIRE': self.secretaire,
            'RESP_PEDA': self.peda,
            'FORMATEUR': self.formateur,
            'ETUDIANT': self.etudiant,
        }

    def client_en_anglais(self, user=None):
        """Client dont la session est verrouillée sur l'anglais."""
        client = Client()
        if user is not None:
            client.force_login(user)
        client.post(reverse('set_language'), {'language': 'en', 'next': '/'})
        return client

    def _donnees(self):
        """Toute chaîne stockée en base : rôles, catégories, motifs, intitulés."""
        chaines = set(DONNEES)
        sources = (
            (Role, 'label'),
            (TransactionCategory, 'name'),
            (VisitReason, 'label'),
            (CashAccount, 'name'),
            (Course, 'title'),
            (Course, 'domain'),
            (Course, 'description'),
            (CourseSession, 'schedule'),
            (Module, 'title'),
            (Lesson, 'title'),
        )
        for modele, champ in sources:
            chaines.update(
                valeur for valeur in
                modele.objects.values_list(champ, flat=True) if valeur)
        for user in User.objects.all():
            chaines.update(valeur for valeur in
                           (user.first_name, user.last_name) if valeur)
        return sorted(chaines, key=len, reverse=True)

    def _fuites(self, page, etiquette):
        texte = page.content.decode('utf-8')
        texte = COMMENTAIRE_RE.sub(' ', texte)
        texte = STYLE_RE.sub(' ', texte)
        for donnee in self._donnees():
            texte = texte.replace(donnee, '·')
        vues = []
        # Sensible à la casse : le « document » du JavaScript n'est pas de la chrome.
        for mot in MOTS_FRANCAIS:
            for match in list(re.finditer(r'\b' + re.escape(mot) + r'\b', texte))[:2]:
                debut = max(match.start() - 70, 0)
                vues.append(f'{mot} … {texte[debut:match.end() + 40]!r}')
        self.assertEqual(vues, [], f'chrome française visible sur {etiquette}')

    def test_chaque_tableau_de_bord_se_peint_en_anglais(self):
        self.assertEqual(
            set(self.users_by_role),
            {membre.value for membre in RoleKey} - set(ROLES_DISSOUS),
            'un poste actif sans compte de test, ou un poste dissous encore proposé',
        )
        for cle, user in self.users_by_role.items():
            page = self.client_en_anglais(user).get(
                reverse('core:dashboard:dashboard-router'), follow=True)
            self.assertEqual(page.status_code, 200, cle)
            self.assertContains(page, '<html lang="en"')
            self._fuites(page, f'tableau de bord {cle}')

    def test_pages_publiques_en_anglais(self):
        client = self.client_en_anglais()
        for route in ('core:login', 'core:home'):
            page = client.get(reverse(route), follow=True)
            self.assertEqual(page.status_code, 200, route)
            self._fuites(page, route)

    def test_listes_et_formulaires_se_peignent_en_anglais(self):
        ecriture = CashTransaction.objects.create(
            tx_type=CashTransaction.Type.IN, category=self.income_category,
            label='Recette de test', amount=5000, occurred_at=timezone.now(),
            account=self.cash, method=Payment.Method.CASH,
            status=CashTransaction.Status.VALIDATED, created_by=self.assistant,
        )
        pages = (
            (self.secretaire, 'core:dashboard:student-list'),
            (self.assistant, 'core:dashboard:journal'),
            (self.assistant, 'core:dashboard:transaction-detail', ecriture.pk),
            (self.assistant, 'core:dashboard:transaction-edit', ecriture.pk),
            (self.assistant, 'core:dashboard:accounts'),
            (self.assistant, 'core:dashboard:account-update', self.cash.pk),
            (self.assistant, 'core:dashboard:account-adjust', self.cash.pk),
            (self.assistant, 'core:dashboard:account-reset', self.cash.pk),
            (self.assistant, 'core:dashboard:categories'),
            (self.assistant, 'core:dashboard:category-update',
             self.income_category.pk),
            (self.assistant, 'core:dashboard:closures'),
            (self.assistant, 'core:dashboard:payment-create'),
            (self.assistant, 'core:dashboard:payment-months'),
            (self.peda, 'core:dashboard:programs'),
            (self.peda, 'core:dashboard:course-sessions'),
            (self.peda, 'core:dashboard:resources'),
            (self.peda, 'core:dashboard:attendance-history'),
            (self.peda, 'core:dashboard:access-requests'),
            (self.assistant, 'core:dashboard:visit-list'),
            (self.assistant, 'core:dashboard:prospect-list'),
            (self.assistant, 'core:dashboard:visit-reasons'),
            (self.super_admin, 'core:dashboard:user-list'),
            (self.super_admin, 'core:dashboard:role-permissions'),
            (self.super_admin, 'core:dashboard:access-requests'),
            (self.super_admin, 'core:dashboard:audit-log'),
            (self.super_admin, 'core:dashboard:scholarship-review-list'),
            (self.super_admin, 'core:dashboard:finance-supervision'),
            (self.direction, 'core:dashboard:enrollment-detail', self.enrollment.pk),
            (self.secretaire, 'core:dashboard:student-detail', self.etudiant.pk),
            (self.etudiant, 'core:dashboard:student-course-sheet', self.session.pk),
        )
        for page_def in pages:
            user, route = page_def[0], page_def[1]
            url = reverse(route, args=page_def[2:])
            page = self.client_en_anglais(user).get(url, follow=True)
            self.assertEqual(page.status_code, 200, route)
            self._fuites(page, route)

    def test_la_grille_des_mois_et_le_recu_se_peignent_en_anglais(self):
        client = self.client_en_anglais(self.assistant)
        grille = client.get(reverse('core:dashboard:payment-months'),
                            {'enrollment': self.enrollment.pk}, follow=True)
        self.assertEqual(grille.status_code, 200)
        self._fuites(grille, 'grille des douze mois')
        self.assertContains(grille, 'Monthly payment of January')

        annee = timezone.localdate().year
        paiement = Payment.objects.create(
            enrollment=self.enrollment, amount=25000,
            method=Payment.Method.CASH, motif=Payment.Motif.MONTHLY,
            period_year=annee, period_month=1, recorded_by=self.assistant,
        )
        recu = client.get(reverse('core:dashboard:payment-receipt', args=[paiement.pk]))
        self.assertEqual(recu.status_code, 200)
        self._fuites(recu, 'reçu de paiement')
        self.assertContains(recu, 'Settled month')
        self.assertContains(recu, f'January {annee}')
