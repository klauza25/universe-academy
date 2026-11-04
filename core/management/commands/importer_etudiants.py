"""Vague 2 de l'import : les élèves du classeur de gestion des étudiants.

Relit ``docs/donnees`` avec les règles de ``analyser_donnees``, prépare les lignes avec
``core.eleves_import`` puis écrit : comptes étudiants, groupes par onglet, inscriptions au
tarif du catalogue, paiements lus dans les cases (frais d'inscription et mensualités) et leur
écriture de caisse. Les décisions sont dans ``core/eleves_import.py``, pas ici.

    python manage.py importer_etudiants                       # prévisualisation, rien n'est écrit
    python manage.py importer_etudiants --efface              # montre aussi ce que « effacer » couvre
    python manage.py importer_etudiants --ecrire --efface     # après copie de db.sqlite3 dans backups/

Gardes : sans ``--efface``, une inscription déjà saisie dans l'application fait refuser l'écriture —
rien n'est supprimé en douce ; les lignes posées par une importation marquée se retrouvent sous
leur marque et ne se dupliquent pas ; un doublon du classeur est signalé, jamais écrit ; un
intitulé de formation seulement ressemblant est écarté.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify
from django.utils import timezone

from core import eleves_import as import_eleves
from core.models import (
    AccountStatus, Attendance, CashAccount, CashTransaction, Course, CourseSession,
    Enrollment, Payment, Role, RoleKey, TransactionCategory, User, UserRole,
)
from .analyser_donnees import Command as Analyseur

CLASSEUR_PAR_DEFAUT = 'Gestion des étudiants.xlsx'
CATEGORIE_ETUDIANTS = 'Paiements des étudiants'
MARQUE = import_eleves.MARQUE
MIDI = dt.time(12, 0)


class Command(BaseCommand):
    help = ('Importe les élèves, les groupes, les inscriptions et les encaissements du '
            'classeur déposé (comptes et paiements marqués « d\'après les classeurs »)')

    def add_arguments(self, parser):
        parser.add_argument('--repertoire', default=None, help='Dossier des classeurs')
        parser.add_argument('--classeur', default=CLASSEUR_PAR_DEFAUT,
                            help='Classeur dont on importe les onglets de suivi (vide : tous)')
        parser.add_argument('--agent', default='secretaire@univers.academy',
                            help='Compte qui apparaît comme auteur des lignes importées')
        parser.add_argument('--caisse', default='Caisse principale',
                            help='Compte de caisse des encaissements importés')
        parser.add_argument('--details', type=int, default=20,
                            help='Nombre de lignes affichées par liste de contrôle')
        parser.add_argument('--ecrire', action='store_true',
                            help='Écrire en base (sans cette option, simple prévisualisation)')
        parser.add_argument('--efface', action='store_true',
                            help='Supprimer d\'abord les inscriptions, paiements et écritures de '
                                 'caisse saisis dans l\'application — jamais ceux posés par '
                                 'l\'import ; les sorties de caisse et les comptes restent')

    # ------------------------------------------------------------------
    @transaction.atomic
    def handle(self, *args, **options):
        dossier = Path(options['repertoire'] or Path(settings.BASE_DIR) / 'docs' / 'donnees')
        analyseur = Analyseur()
        analyseur.details = 5
        analyseur.collecter(dossier)
        if analyseur.inaccessibles:
            raise CommandError('Classeur ouvert dans Excel, donc illisible : '
                               f'{", ".join(analyseur.inaccessibles)}. Fermez-le et relancez.')
        classeur = options['classeur']
        if classeur and classeur not in analyseur.contenu:
            raise CommandError(f'Classeur introuvable dans {dossier} : {classeur}')

        plan = import_eleves.preparer(
            analyseur, self._tarifs(), self._comptes_existants(),
            analyseur._appariement(), classeur)
        self._decrire(plan, classeur, options)

        purge = self._inventaire_effacement()
        if purge['inscriptions'] or purge['importees']:
            self._afficher_effacement(purge, options)
        if not options['ecrire']:
            self.stdout.write(self.style.WARNING(
                '\nPrévisualisation : rien n\'a été écrit. Sauvegardez db.sqlite3 dans backups/, '
                'puis relancez avec --ecrire' + (' --efface' if purge['inscriptions'] else '')
                + '.'))
            return
        if purge['inscriptions'] and not options['efface']:
            raise CommandError(
                f'{purge["inscriptions"]} inscription(s) et {purge["paiements"]} paiement(s) '
                'saisis dans l\'application sont repris par le classeur. Ils ne se fusionnent '
                'pas : relancez avec --efface pour les supprimer, ou changez de classeur.')

        ecrits = self._ecrire(plan, options)
        self.stdout.write(self.style.SUCCESS(
            f'\nÉcrit : {ecrits["comptes"]} compte(s) étudiant(s) créé(s), '
            f'{ecrits["comptes_repris"]} repris, {ecrits["groupes"]} groupe(s), '
            f'{ecrits["inscriptions"]} inscription(s), {ecrits["paiements"]} paiement(s) '
            f'({self._fcfa(ecrits["montant"])}), {ecrits["caisse"]} écriture(s) de caisse.'))
        if ecrits['sutes']:
            self.stdout.write(self.style.WARNING(
                f'{ecrits["sutes"]} ligne(s) déjà en base, non touchée(s) : une écriture '
                'existante ne se réécrit pas.'))
        if ecrits['roles_a_trancher']:
            self.stdout.write(self.style.WARNING(
                f'{ecrits["roles_a_trancher"]} compte(s) retrouvé(s) sans rôle étudiant : '
                'le secrétariat décide, l\'import ne requalifie personne.'))

    # ------------------------------------------------------------------
    # Ce que la base contient déjà
    # ------------------------------------------------------------------
    @staticmethod
    def _tarifs() -> dict:
        return {
            cours.title: {'frais': cours.fee_amount, 'duree': cours.duration_months,
                          'mensuel': cours.fee_amount // max(cours.duration_months, 1)}
            for cours in Course.objects.all()
        }

    @staticmethod
    def _comptes_existants() -> list:
        return [
            {'id': str(user['id']), 'email': user['email'], 'telephone': user['phone'],
             'nom': user['last_name'], 'prenom': user['first_name']}
            for user in User.objects.values('id', 'email', 'phone', 'last_name', 'first_name')
        ]

    @staticmethod
    def _saisies_dans_l_app():
        """Les inscriptions que l'import n'a pas posées lui-même : saisies à la main, ou démonstration.

        La marque de l'import est dans ``notes`` ; une ligne sans marque est une écriture
        engagée dont personne ne décide à la place du secrétariat.
        """
        return Enrollment.objects.exclude(notes__contains=MARQUE)

    @classmethod
    def _inventaire_effacement(cls) -> dict:
        """Ce que « efface » couvre : l'argent des élèves saisi dans l'app, pas les sorties de caisse."""
        pk_saisies = list(cls._saisies_dans_l_app().values_list('id', flat=True))
        paiements = Payment.objects.filter(enrollment_id__in=pk_saisies)
        caisses = CashTransaction.objects.filter(student_payment__enrollment_id__in=pk_saisies)
        return {
            'inscriptions': len(pk_saisies),
            'paiements': paiements.count(),
            'caisses': list(caisses),
            'entrees': sum(c.amount for c in caisses),
            'presences': Attendance.objects.filter(enrollment_id__in=pk_saisies).count(),
            'importees': Enrollment.objects.filter(notes__contains=MARQUE).count(),
            'groupes_vides': CourseSession.objects.exclude(enrollments__isnull=False).count(),
            'sorties': [f'{t.reference} — {t.label} {t.amount:,} FCFA'.replace(',', ' ')
                        for t in CashTransaction.objects.filter(tx_type=CashTransaction.Type.OUT)],
            'dossier': [
                f'{e.student.display_label} — {e.session.course.title} — net '
                f'{e.net_amount:,}, payé {e.total_paid:,}'.replace(',', ' ')
                for e in cls._saisies_dans_l_app().select_related('student', 'session__course')[:8]
            ],
        }

    def _afficher_effacement(self, purge: dict, options) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING('\n— Ce que « efface » supprimerait'))
        self.stdout.write(
            f'  {purge["inscriptions"]} inscription(s) saisie(s) dans l\'application, '
            f'{purge["paiements"]} paiement(s), {len(purge["caisses"])} écriture(s) de caisse '
            f'd\'entrée « {CATEGORIE_ETUDIANTS} » ({self._fcfa(purge["entrees"])}), '
            f'{purge["presences"]} feuille(s) de présence rattachée(s).')
        self.stdout.write(f'  Les sorties de caisse restent : {", ".join(purge["sorties"]) or "aucune"}.')
        self.stdout.write('  Les comptes utilisateurs, le catalogue et les groupes ne bougent pas.')
        if purge['importees']:
            self.stdout.write(self.style.WARNING(
                f'  {purge["importees"]} inscription(s) déjà posées par l\'import ne sont pas '
                'effacées : elles se retrouvent sous la même marque.'))
        if purge['groupes_vides']:
            self.stdout.write(f'  {purge["groupes_vides"]} groupe(s) resteraient sans inscription '
                              "(les groupes ne se suppriment pas ici).")
        for ligne in purge['dossier'][:options['details']]:
            self.stdout.write(f'    · {ligne}')

    @classmethod
    def _executer_effacement(cls, purge: dict) -> None:
        """Payment.enrollment est PROTECT : écritures de caisse et paiements partent avant les dossiers."""
        CashTransaction.objects.filter(
            pk__in=[t.pk for t in purge['caisses']]).delete()
        Payment.objects.filter(
            enrollment_id__in=list(cls._saisies_dans_l_app().values_list('id', flat=True)),
        ).delete()
        cls._saisies_dans_l_app().delete()

    # ------------------------------------------------------------------
    def _ecrire(self, plan, options) -> Counter:
        agent = User.objects.filter(email__iexact=options['agent']).first()
        caisse = CashAccount.objects.filter(name=options['caisse']).first()
        if caisse is None:
            raise CommandError(f'Compte de caisse introuvable : {options["caisse"]}. '
                               'Le créer depuis le tableau de bord comptable avant d\'écrire.')
        categorie, _creee = TransactionCategory.objects.get_or_create(
            name=CATEGORIE_ETUDIANTS,  # i18n-exempt: nom stocké en base, clé de get_or_create
            direction=TransactionCategory.Direction.IN,
        )
        if options['efface']:
            self._executer_effacement(self._inventaire_effacement())

        ecrits = Counter()
        role = Role.objects.get(key=RoleKey.ETUDIANT)
        par_cle = {compte.cle: self._ecrire_compte(compte, role, ecrits)
                   for compte in plan.comptes}
        sessions = {groupe.cle: self._ecrire_groupe(groupe, ecrits) for groupe in plan.groupes}
        dossiers = {id(i): self._ecrire_inscription(i, par_cle, sessions, agent, ecrits)
                    for i in plan.inscriptions}
        for paiement in plan.paiements:
            dossier = dossiers.get(id(paiement.inscription))
            if dossier is not None:
                self._ecrire_paiement(paiement, dossier, agent, caisse, categorie, ecrits)
        return ecrits

    def _ecrire_compte(self, compte, role, ecrits) -> User:
        """Le compte déjà ouvert garde son identifiant de connexion ; on ne complète que le vide."""
        if compte.identifiant:
            user = User.objects.get(pk=compte.identifiant)
            for champ, valeur in (('phone', compte.telephone), ('address', compte.adresse),
                                  ('first_name', compte.prenom), ('last_name', compte.nom)):
                if valeur and not getattr(user, champ):
                    setattr(user, champ, valeur)
            if not user.internal_code:
                user.generate_internal_code(RoleKey.ETUDIANT.value)
            user.save()
            if not user.has_role(RoleKey.ETUDIANT):
                ecrits['roles_a_trancher'] += 1
            else:
                ecrits['comptes_repris'] += 1
            return user
        email = (compte.email if import_eleves.adresse_valide(compte.email)
                 else self._adresse_de_repli(compte))
        user = User.objects.create_user(
            email=email, password=None, first_name=compte.prenom, last_name=compte.nom,
            phone=compte.telephone, address=compte.adresse,
            account_status=AccountStatus.PENDING_APPROVAL,
        )
        user.generate_internal_code(RoleKey.ETUDIANT.value)
        user.save()
        UserRole.objects.get_or_create(user=user, role=role)
        ecrits['comptes'] += 1
        return user

    @staticmethod
    def _adresse_de_repli(compte) -> str:
        """Une adresse de connexion pour une fiche qui n'en a pas : à remplacer par le secrétariat."""
        base = slugify(f'{compte.prenom} {compte.nom}', allow_unicode=True) or 'eleve'
        index = 1
        email = f'{base}-{index}{import_eleves.SUFFIXE_SANSDRESSE}'
        while User.objects.filter(email=email).exists():
            index += 1
            email = f'{base}-{index}{import_eleves.SUFFIXE_SANSDRESSE}'
        return email

    @staticmethod
    def _ecrire_groupe(groupe, ecrits) -> CourseSession:
        cours = Course.objects.get(title=groupe.titre)
        session = CourseSession.objects.filter(
            course=cours, starts_at=groupe.debut,
            schedule__startswith=f'{groupe.onglet} —').first()
        if session:
            return session
        session = CourseSession.objects.create(
            course=cours, starts_at=groupe.debut, ends_at=groupe.fin,
            schedule=f'{groupe.onglet} — {MARQUE}', capacity=max(groupe.effectif, 10),
            status=groupe.statut,
        )
        ecrits['groupes'] += 1
        return session

    @staticmethod
    def _ecrire_inscription(inscription, par_cle, sessions, agent, ecrits) -> Enrollment | None:
        student = par_cle.get(inscription.compte.cle)
        session = sessions.get(inscription.groupe.cle)
        if not student or not session:
            return None
        existante = Enrollment.objects.filter(student=student, session=session).first()
        if existante:
            # Une inscription déjà là est une écriture engagée : ses paiements ne se rejouent pas.
            ecrits['sutes'] += 1
            return None
        ecrits['inscriptions'] += 1
        return Enrollment.objects.create(
            student=student, session=session, status=inscription.statut,
            start_date=inscription.date_debut, tariff_amount=inscription.tarif,
            net_amount=inscription.net, registered_by=agent, notes=inscription.note,
            payment_plan=f'{MARQUE} : {inscription.groupe.mensuelle} FCFA par mois',
        )

    @staticmethod
    def _ecrire_paiement(paiement, dossier, agent, caisse, categorie, ecrits) -> None:
        instants = timezone.make_aware(dt.datetime.combine(paiement.jour, MIDI))
        if Payment.objects.filter(enrollment=dossier, amount=paiement.montant,
                                  paid_at__date=paiement.jour,
                                  note__startswith=MARQUE).exists():
            ecrits['sutes'] += 1
            return
        paye = Payment.objects.create(
            enrollment=dossier, amount=paiement.montant, method=Payment.Method.CASH,
            status=Payment.Status.COMPLETED, paid_at=instants, recorded_by=agent,
            note=f'{paiement.motif} — {paiement.note}',
        )
        cash = CashTransaction.objects.create(
            tx_type=CashTransaction.Type.IN, category=categorie,
            label=f'{paiement.motif} {dossier.student.display_label}',
            description=f'{dossier.session.course.title} — {paiement.note}',
            amount=paiement.montant, currency='XAF', occurred_at=instants, account=caisse,
            method=Payment.Method.CASH, counterparty=dossier.student.display_label,
            status=CashTransaction.Status.VALIDATED, created_by=agent, note=paiement.note,
        )
        paye.transaction = cash
        paye.save(update_fields=['transaction'])
        ecrits['paiements'] += 1
        ecrits['caisse'] += 1
        ecrits['montant'] += paiement.montant

    # ------------------------------------------------------------------
    def _decrire(self, plan, classeur, options) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'\n— Ce que « {classeur or "les classeurs"} » apporte à la base'))
        a_creer = [c for c in plan.comptes if c.a_creer]
        self.stdout.write(
            f'  {len(plan.comptes)} élève(s) rencontré(s) : {len(a_creer)} compte(s) à créer, '
            f'{len(plan.comptes) - len(a_creer)} retrouvé(s) sous un compte déjà ouvert.')
        self.stdout.write(
            f'  {len(plan.groupes)} groupe(s) de {sum(g.effectif for g in plan.groupes)} places, '
            f'{len(plan.inscriptions)} inscription(s), {len(plan.paiements)} paiement(s) '
            f'pour {self._fcfa(plan.montant_total)}.')
        sans_adresse = [c for c in plan.comptes if c.sans_adresse]
        if sans_adresse:
            self.stdout.write(f'  {len(sans_adresse)} élève(s) sans adresse : une adresse de '
                              'repli sera posée, à remplacer par le secrétariat.')
        par_type = defaultdict(list)
        for type_, ou, qui in plan.ecarts:
            par_type[type_].append((ou, qui))
        if par_type:
            self.stdout.write(self.style.MIGRATE_HEADING('\n— Signalé, importable quand même'))
            for type_, items in sorted(par_type.items()):
                self.stdout.write(f'  {type_} : {len(items)}')
                for ou, qui in items[:max(3, options['details'] // 4)]:
                    self.stdout.write(f'    · {ou} — {qui}')
        if plan.ecartes:
            self.stdout.write(self.style.MIGRATE_HEADING('\n— Écartés faute de décision'))
            for type_, ou, qui in plan.ecartes[:options['details']]:
                self.stdout.write(f'  {type_} — {ou} : {qui}')
            if len(plan.ecartes) > options['details']:
                self.stdout.write(f'  … {len(plan.ecartes) - options["details"]} autres')

    @staticmethod
    def _fcfa(montant) -> str:
        return f'{int(montant or 0):,} FCFA'.replace(',', ' ')
