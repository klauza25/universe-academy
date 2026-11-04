"""Photo de profil : elle doit se voir sur les listes et se poser par le personnel.

Un compte étudiant venu d'un classeur ne se connecte jamais. Si la photo ne
pouvait être posée que par l'intéressé, les listes resteraient en initiales :
d'où l'écran du secrétariat et la vignette partagée par tous les écrans.
"""
from io import BytesIO

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template import Context, Template
from django.urls import reverse
from PIL import Image

from core.models import AccountStatus, User

from .base import BusinessTestBase


def photo(nom='portrait.png', couleur=(200, 30, 30)):
    buffer = BytesIO()
    Image.new('RGB', (8, 8), couleur).save(buffer, format='PNG')
    return SimpleUploadedFile(nom, buffer.getvalue(), content_type='image/png')


def rendu_vignette(personne):
    return Template('{% load ui %}{% vignette personne %}').render(
        Context({'personne': personne}))


class VignetteTests(BusinessTestBase):
    """La même vignette partout : photo si elle existe, initiales sinon."""

    def setUp(self):
        self.eleve = User.objects.create_user(
            email='eleve-photo@test.local', password=None,
            first_name='Brivah', last_name='Louamba',
            account_status=AccountStatus.ACTIVE,
        )
        self.eleve.roles.add(self.roles['ETUDIANT'])

    def test_sans_photo_la_vignette_donne_les_initiales(self):
        rendu = rendu_vignette(self.eleve)
        self.assertIn('ua-avatar-sm', rendu)
        self.assertIn('BL', rendu)
        self.assertNotIn('<img', rendu)

    def test_avec_photo_la_vignette_donne_le_visage(self):
        self.eleve.poser_avatar(photo())
        self.eleve.refresh_from_db()
        rendu = rendu_vignette(self.eleve)
        self.assertIn('<img', rendu)
        self.assertIn(self.eleve.avatar.url, rendu)
        self.assertIn('Photo de Brivah Louamba', rendu)

    def test_la_liste_des_etudiants_affiche_les_visages(self):
        self.eleve.poser_avatar(photo())
        self.client = self.client_for(self.secretaire)
        contenu = self.client.get(
            reverse('core:dashboard:student-list')).content.decode()
        self.assertIn(f'src="{self.eleve.avatar.url}"', contenu)
        self.assertIn('Brivah', contenu)


class PhotoPoseeParLeSecretariatTests(BusinessTestBase):
    """Le personnel photographie un étudiant qui ne se connecte pas."""

    def setUp(self):
        self.client = self.client_for(self.secretaire)
        self.eleve = User.objects.create_user(
            email='eleve-caisse@test.local', password=None,
            first_name='Noellie', last_name='Etali',
            account_status=AccountStatus.PENDING_APPROVAL,
        )
        self.eleve.roles.add(self.roles['ETUDIANT'])
        self.url = reverse('core:dashboard:student-avatar',
                           args=[self.eleve.id])

    def test_le_secretaire_pose_la_photo_d_un_etudiant(self):
        reponse = self.client.post(self.url, {
            'action': 'avatar', 'avatar': photo(),
        })
        self.assertRedirects(
            reponse, reverse('core:dashboard:student-detail',
                             args=[self.eleve.id]),
            fetch_redirect_response=False)
        self.eleve.refresh_from_db()
        self.assertTrue(self.eleve.avatar)
        self.assert_audited('PROFILE_AVATAR', self.eleve.pk)

    def test_la_photo_en_attente_d_un_etudiant_ne_change_rien_au_dossier(self):
        """Reconnaître un élève par son visage n'approuve pas son compte."""
        self.client.post(self.url, {'action': 'avatar', 'avatar': photo()})
        self.eleve.refresh_from_db()
        self.assertEqual(self.eleve.account_status,
                         AccountStatus.PENDING_APPROVAL)

    def test_remplacer_efface_le_fichier_replaces(self):
        self.client.post(self.url, {'action': 'avatar', 'avatar': photo()})
        self.eleve.refresh_from_db()
        nom_avant = self.eleve.avatar.name
        self.client.post(self.url, {
            'action': 'avatar', 'avatar': photo('seconde.png', (30, 30, 200)),
        })
        self.eleve.refresh_from_db()
        self.assertNotEqual(self.eleve.avatar.name, nom_avant)
        self.assertFalse(default_storage.exists(nom_avant),
                         "l'ancienne photo est restée sur le disque")
        self.assertTrue(default_storage.exists(self.eleve.avatar.name))

    def test_sans_fichier_choisi_la_photo_reste_en_place(self):
        self.client.post(self.url, {'action': 'avatar', 'avatar': photo()})
        self.eleve.refresh_from_db()
        nom = self.eleve.avatar.name
        self.client.post(self.url, {'action': 'avatar'})
        self.eleve.refresh_from_db()
        self.assertEqual(self.eleve.avatar.name, nom)
        self.assertTrue(default_storage.exists(nom))

    def test_le_secretaire_retire_la_photo(self):
        self.client.post(self.url, {'action': 'avatar', 'avatar': photo()})
        self.eleve.refresh_from_db()
        nom = self.eleve.avatar.name
        self.client.post(self.url, {'action': 'avatar_delete'})
        self.eleve.refresh_from_db()
        self.assertFalse(self.eleve.avatar)
        self.assertFalse(default_storage.exists(nom))
        self.assert_audited('PROFILE_AVATAR_DELETE', self.eleve.pk)

    def test_un_assistant_admin_ne_pose_pas_de_photo(self):
        self.client = self.client_for(self.assistant)
        reponse = self.client.post(self.url, {
            'action': 'avatar', 'avatar': photo(),
        })
        self.assertEqual(reponse.status_code, 403)
        self.eleve.refresh_from_db()
        self.assertFalse(self.eleve.avatar)


class PhotoPoseeParLeSuperAdministrateurTests(BusinessTestBase):
    """Un compte d'administration se reconnaît aussi de visu."""

    def setUp(self):
        self.client = self.client_for(self.super_admin)

    def test_la_fiche_d_un_compte_porte_sa_photo(self):
        self.peda.poser_avatar(photo())
        contenu = self.client.get(
            reverse('core:dashboard:user-detail', args=[self.peda.id])
        ).content.decode()
        self.assertIn(f'src="{self.peda.avatar.url}"', contenu)
        self.assertIn(reverse('core:dashboard:user-avatar',
                              args=[self.peda.id]), contenu)

    def test_le_super_admin_pose_la_photo_d_un_compte(self):
        reponse = self.client.post(
            reverse('core:dashboard:user-avatar', args=[self.formateur.id]),
            {'action': 'avatar', 'avatar': photo()})
        self.assertRedirects(
            reponse, reverse('core:dashboard:user-detail',
                             args=[self.formateur.id]),
            fetch_redirect_response=False)
        self.formateur.refresh_from_db()
        self.assertTrue(self.formateur.avatar)

    def test_sa_propre_fiche_ne_propose_pas_la_carte_photo(self):
        """Sur sa propre fiche, pas de carte photo : l'écran « Mon profil » suffit."""
        contenu = self.client.get(
            reverse('core:dashboard:user-detail', args=[self.super_admin.id])
        ).content.decode()
        self.assertNotIn(reverse('core:dashboard:user-avatar',
                                 args=[self.super_admin.id]), contenu)
