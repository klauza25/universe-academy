"""Éditeur de permissions : la matrice postes × droits, et son effet réel.

Un droit coché ou décoché ici doit ouvrir ou fermer l'écran correspondant ;
les rôles transversaux restent hors d'atteinte de l'éditeur.
"""
from django.urls import reverse

from core.models import (
    AuditLog, ELEVATED_ROLES, Permission, Role, RolePermission, ROLES_DISSOUS,
)

from .base import BusinessTestBase


class EditeurDePermissionsTests(BusinessTestBase):
    def setUp(self):
        self.editeur = reverse('core:dashboard:role-permissions')
        self.super_client = self.client_for(self.super_admin)
        self.droits = {permission.key: permission
                       for permission in Permission.objects.all()}
        self.postes_editables = [
            role for role in Role.objects.exclude(key__in=ROLES_DISSOUS)
            if role.key not in ELEVATED_ROLES
        ]

    def cases(self, sans=(), ajoute=()):
        """Le formulaire tel qu'il est soumis : les cases cochées aujourd'hui,
        moins celles que l'on retire, plus celles que l'on accorde."""
        cochees = {
            (str(rolperm.role_id), str(rolperm.permission_id))
            for rolperm in RolePermission.objects.filter(role__in=self.postes_editables)
        }
        for role_cle, droit_cle in sans:
            cochees.discard((str(self.roles[role_cle].id),
                             str(self.droits[droit_cle].id)))
        for role_cle, droit_cle in ajoute:
            cochees.add((str(self.roles[role_cle].id),
                         str(self.droits[droit_cle].id)))
        return [f'{role_id}:{permission_id}'
                for role_id, permission_id in sorted(cochees)]

    def test_la_matrice_affiche_les_postes_actifs_et_le_droit_de_caisse(self):
        page = self.super_client.get(self.editeur)
        self.assertEqual(page.status_code, 200)
        for role in self.postes_editables:
            self.assertContains(page, role.label)
        self.assertContains(page, 'finance.write')
        for poste in ROLES_DISSOUS:
            self.assertNotContains(page, Role.objects.get(key=poste).label)

        cases_editables = sum(1 for ligne in page.context['lignes']
                              for case in ligne['cases'] if case['editable'])
        self.assertEqual(cases_editables,
                         Permission.objects.count() * len(self.postes_editables))
        self.assertEqual(page.content.count(b'name="grant"'), cases_editables)

    def test_les_roles_transversaux_restent_hors_de_ledition(self):
        page = self.super_client.get(self.editeur)
        self.assertContains(page, 'accès complet')
        transversaux = {str(self.roles[clee].id) for clee in ELEVATED_ROLES}
        for ligne in page.context['lignes']:
            for case in ligne['cases']:
                if case['valeur'].split(':')[0] in transversaux:
                    self.assertFalse(case['editable'])

    def test_decocher_un_droit_ferme_lecran_dencaissement(self):
        self.super_client.post(self.editeur, {
            'grant': self.cases(sans=[('ASSISTANT_ADMIN', 'finance.write')]),
        })
        self.assertFalse(self.assistant.has_perm_key('finance.write'))
        for route in ('core:dashboard:payment-create',
                      'core:dashboard:payment-months'):
            self.assertEqual(
                self.client_for(self.assistant).get(reverse(route)).status_code,
                403, route)

    def test_cocher_un_droit_ouvre_lecran_dencaissement(self):
        formateur = self.client_for(self.formateur)
        self.assertEqual(
            formateur.get(reverse('core:dashboard:payment-create')).status_code,
            403)
        self.super_client.post(self.editeur, {
            'grant': self.cases(ajoute=[('FORMATEUR', 'finance.write')]),
        })
        self.assertTrue(self.formateur.has_perm_key('finance.write'))
        self.assertEqual(
            formateur.get(reverse('core:dashboard:payment-create')).status_code,
            200)

    def test_lediteur_est_reserve_au_super_administrateur(self):
        for user in (self.admin, self.direction, self.secretaire,
                     self.peda, self.etudiant):
            self.assertEqual(
                self.client_for(user).get(self.editeur).status_code, 403,
                user.primary_role)

    def test_le_bouton_encaisser_suivit_la_matrice(self):
        dossier = reverse('core:dashboard:enrollment-detail',
                          args=[self.enrollment.pk])
        caisse = self.client_for(self.secretaire)
        self.assertContains(caisse.get(dossier), 'Encaisser</a>', html=False)

        self.super_client.post(self.editeur, {
            'grant': self.cases(sans=[('SECRETAIRE', 'finance.write')]),
        })
        self.assertNotContains(caisse.get(dossier), 'Encaisser</a>', html=False)

    def test_un_POST_ne_peut_ni_toucher_un_role_transversal_ni_inventer_un_droit(self):
        transversal = self.roles['SUPER_ADMIN']
        avant_transversal = RolePermission.objects.filter(role=transversal).count()
        page = self.super_client.post(self.editeur, {'grant': self.cases() + [
            f'{transversal.id}:{self.droits["finance.write"].id}',
            f'00000000-0000-0000-0000-000000000000:{self.droits["finance.write"].id}',
        ]})
        self.assertEqual(page.status_code, 302)
        self.assertEqual(
            RolePermission.objects.filter(role=transversal).count(),
            avant_transversal)
        self.assertFalse(
            RolePermission.objects.filter(role_id='00000000-0000-0000-0000-000000000000').exists())

    def test_chaque_sauvegarde_laisse_sa_trace_dans_le_journal(self):
        self.super_client.post(self.editeur, {
            'grant': self.cases(sans=[('SECRETAIRE', 'finance.write')]),
        })
        entree = AuditLog.objects.get(action='ROLE_PERMISSIONS_UPDATE')
        self.assertEqual(entree.actor, self.super_admin)
        self.assertEqual(entree.before_summary['retirees'],
                         [['SECRETAIRE', 'finance.write']])

    def test_une_sauvegarde_sans_changement_ne_journalise_rien(self):
        page = self.super_client.post(self.editeur, {'grant': self.cases()},
                                      follow=True)
        self.assertContains(page, 'déjà à jour')
        self.assertFalse(AuditLog.objects.filter(
            action='ROLE_PERMISSIONS_UPDATE').exists())

    def test_le_menu_ne_propose_lediteur_quau_super_administrateur(self):
        self.assertContains(
            self.super_client.get(
                reverse('core:dashboard:super-admin-dashboard')), self.editeur)
        self.assertNotContains(
            self.client_for(self.admin).get(
                reverse('core:dashboard:admin-dashboard')), self.editeur)
