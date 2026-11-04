"""Mettre en attente d'approbation les comptes ouverts par l'import des classeurs.

    python manage.py mettre_en_attente                       # aperçu, rien n'est écrit
    python manage.py mettre_en_attente --ecrire              # 193 comptes en attente
    python manage.py mettre_en_attente --ecrire --approuver-en-cours
        # puis approuve ceux inscrits dans un groupe en cours ou planifié

Un compte ouvert par une fiche de classeur n'a jamais reçu de login : son mot de
passe est vide. C'est le seul signe distinctif, et il protège les comptes ouverts
à la main — ceux-là gardent l'approbation qu'on leur a donnée.

La commande ne change aucun statut d'office : elle replace en « en attente
d'approbation » les compteurs d'un import qui, avant la règle par défaut,
naissaient « Actifs ». Dès que cette réparation a servi — un seul compte du
classeur est en attente — la commande ne remplace plus rien : les comptes encore
actifs sont des approbations données après coup et elles ne se révoquent pas.
`--approuver-en-cours` est le geste inverse, explicitement demandé par la
direction pour que les cohortes en cours retrouvent un effectif ; il est
relançable à volonté. Aucune inscription, aucun paiement, aucune pièce n'est
touché.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import AccountStatus, CourseSession, Enrollment, RoleKey, User

GROUPS_NON_CLOS = (CourseSession.Status.ACTIVE, CourseSession.Status.PLANNED)


def comptes_importes():
    """Les comptes étudiants sortis d'un classeur : aucun login distribué."""
    return (User.objects.filter(roles__key=RoleKey.ETUDIANT, password='')
            .order_by('last_name', 'first_name'))


def ids_en_formation():
    """Identifiants des étudiants d'un groupe qui n'est pas terminé."""
    return set(Enrollment.objects.filter(
        session__status__in=GROUPS_NON_CLOS,
        session__ends_at__gte=timezone.localdate(),
    ).values_list('student_id', flat=True))


class Command(BaseCommand):
    help = ('Replace en attente d\'approbation les comptes etudiants ouverts par '
            'l\'import des classeurs, sans toucher aux comptes ouverts a la main.')

    def add_arguments(self, parser):
        parser.add_argument('--details', type=int, default=12,
                            help='Nombre de noms affiches pour chaque liste')
        parser.add_argument('--approuver-en-cours', action='store_true',
                            help='Approuver ensuite les comptes importes inscrits '
                                 'dans un groupe en cours ou planifie')
        parser.add_argument('--ecrire', action='store_true',
                            help='Ecrire en base (sans cette option, simple preview)')

    def handle(self, *args, **options):
        comptes = list(comptes_importes())
        en_formation = ids_en_formation()
        deja_ranges = [c for c in comptes
                       if c.account_status == AccountStatus.PENDING_APPROVAL]
        # Dès qu'un compte du classeur est en attente, la réparation a servi :
        # les comptes encore actifs sont des approbations données après coup.
        a_remplacer = [] if deja_ranges else [
            c for c in comptes if c.account_status != AccountStatus.PENDING_APPROVAL]
        a_approuver = [c for c in comptes if c.pk in en_formation]

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'\n— {len(comptes)} compte(s) ouvert(s) par les classeurs'))
        self.stdout.write(
            f'  à mettre en attente d’approbation : {len(a_remplacer)} '
            f'({len(deja_ranges)} déjà en attente)')
        if deja_ranges and not a_remplacer:
            self.stdout.write(
                f'  réparation déjà appliquée : les '
                f'{len(comptes) - len(deja_ranges)} compte(s) encore actifs sont '
                'des approbations données après coup — ils ne se révoquent pas.')
        self.stdout.write(
            f'  inscrits dans un groupe en cours ou planifié : {len(a_approuver)}'
            + (', à approuver' if options['approuver_en_cours']
               else ' (à approuver avec --approuver-en-cours)'))
        if a_remplacer:
            noms = ', '.join((c.display_label or c.email)
                             for c in a_remplacer[:options['details']])
            reste = (f' … +{len(a_remplacer) - options["details"]}'
                     if len(a_remplacer) > options['details'] else '')
            self.stdout.write(f'  comptes : {noms}{reste}')

        if not options['ecrire']:
            self.stdout.write(self.style.WARNING(
                'Prévisualisation : rien n’a été écrit. Sauvegardez db.sqlite3 dans '
                f'backups/, puis relancez avec --ecrire pour mettre '
                f'{len(a_remplacer)} compte(s) en attente d’approbation.'))
            return

        ecrits = self._ecrire(a_remplacer, a_approuver, options['approuver_en_cours'])
        if not any(ecrits.values()):
            self.stdout.write(self.style.SUCCESS(
                'Rien à écrire : les comptes importés sont déjà en attente.'))
            return
        self.stdout.write(self.style.SUCCESS(
            f'Mis en attente d’approbation : {ecrits["attente"]} compte(s) ; '
            f'approuvés : {ecrits["approuves"]} compte(s). Aucune inscription, '
            'aucun paiement touché. Les comptes ouverts à la main gardent leur '
            'approbation.'))

    @staticmethod
    def _ecrire(a_remplacer, a_approuver, approuver_en_cours):
        ecrits = {'attente': 0, 'approuves': 0}
        if a_remplacer:
            with transaction.atomic():
                User.objects.filter(pk__in=[c.pk for c in a_remplacer]).update(
                    account_status=AccountStatus.PENDING_APPROVAL)
            ecrits['attente'] = len(a_remplacer)
        if approuver_en_cours and a_approuver:
            with transaction.atomic():
                User.objects.filter(pk__in=[c.pk for c in a_approuver]).update(
                    account_status=AccountStatus.ACTIVE)
            ecrits['approuves'] = len(a_approuver)
        return ecrits
