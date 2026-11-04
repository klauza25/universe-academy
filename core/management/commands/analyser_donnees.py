"""Rapport en lecture seule des classeurs déposés dans ``docs/donnees``.

Aucune écriture en base : cette commande prépare la validation préalable à l'import.

    python manage.py analyser_donnees
    python manage.py analyser_donnees --details 25 --complet
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core import data_tools as outils
from core import programme_import as programme
from core.models import Course, Enrollment, Payment, User

ONGLETS_HORS_SUIVI = {'Base Etudiants', 'Réponses au formulaire 1'}
MOTIF_MOIS_ANNEE = re.compile(
    r'^(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)'
    r'\s+\d{4}$', re.I)
MOTIF_JOURNAL = re.compile(r'enregistrement|donnees|feuille 2', re.I)
MOTIF_SALARIE = re.compile(r'salari', re.I)
MOTIF_BOURSE = re.compile(r'maroc', re.I)


class Command(BaseCommand):
    help = ("Inventorie docs/donnees, croise les classeurs entre eux et avec la base, "
            "puis rend le rapport d'import.")

    def add_arguments(self, parser):
        parser.add_argument('--repertoire', default=None, help='Dossier des classeurs')
        parser.add_argument('--sortie', default=None,
                            help='Fichier markdown du rapport (défaut : docs/donnees/RAPPORT_ANALYSE.md)')
        parser.add_argument('--details', type=int, default=12,
                            help="Nombre d'exemples par catégorie de doute")
        parser.add_argument('--complet', action='store_true',
                            help='Affiche tout le rapport dans la console')

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        dossier = Path(options['repertoire'] or Path(settings.BASE_DIR) / 'docs' / 'donnees')
        if not dossier.is_dir():
            self.stderr.write(self.style.ERROR(f'Dossier introuvable : {dossier}'))
            return
        chemins = sorted(dossier.glob('*.xlsx'))
        if not chemins:
            self.stderr.write(self.style.ERROR(f'Aucun fichier .xlsx dans {dossier}'))
            return

        self.details = max(1, options['details'])
        self.collecter(dossier)

        sections = [
            self._section_fichiers(),
            self._section_journal(),
            self._section_suivis(),
            self._section_base(),
            self._section_croisement(),
            self._section_formations(),
            self._section_etat_base(),
            self._section_annexes(),
            self._section_doutes(),
            self._section_decisions(),
        ]
        en_tete = [
            "# Rapport d'analyse des classeurs déposés dans `docs/donnees`",
            '',
            f"Généré le {dt.datetime.now():%d/%m/%Y à %H:%M} par `manage.py analyser_donnees`. "
            "**Lecture seule : cette commande n'écrit rien en base.**",
            '',
        ]
        rapport = '\n'.join(en_tete + sections) + '\n'
        destination = Path(options['sortie'] or dossier / 'RAPPORT_ANALYSE.md')
        destination.write_text(rapport, encoding='utf-8')

        self.stdout.write(rapport if options['complet'] else self._resume())
        self.stdout.write(self.style.SUCCESS(f'\nRapport complet : {destination}'))

    def collecter(self, dossier: Path) -> None:
        """Charge les classeurs et mène toutes les analyses ; ne écrit rien, nulle part.

        Réutilisable par les commandes d'import, qui ont besoin des mêmes constats
        (intitulés rencontrés, mensualités pratiquées) sans repasser par le rapport.
        """
        chemins = [c for c in sorted(dossier.glob('*.xlsx')) if not c.name.startswith('~$')]
        if not chemins:
            raise CommandError(f'Aucun fichier .xlsx exploitable dans {dossier}')
        self.contenu, self.tailles, self.inaccessibles = {}, {}, []
        for chemin in chemins:
            try:
                self.contenu[chemin.name] = self._charger(chemin)
            except PermissionError:
                # Classeur ouvert dans Excel pendant l'analyse : la copie sera faite après fermeture.
                self.inaccessibles.append(chemin.name)
                continue
            self.tailles[chemin.name] = chemin.stat().st_size

        self.empreintes, self.retenus, self.doublons = self._empreintes()
        self.suivis = self._analyser_suivis()
        self.base = self._analyser_base()
        self.journal = self._analyser_journal()
        self.annexes = self._analyser_annexes()
        self.catalogue = self._formations_observees()

    def _resume(self):
        inscriptions = self.suivis['inscriptions']
        mois_payes = [m for i in inscriptions for m in i.mois if m[2]]
        ecritures = self.journal['ecritures']
        entrees = sum(e.montant or 0 for e in ecritures if 'entr' in outils.sans_accents(e.sens).lower())
        appariees = self._appariement()
        a_creer = [cle for cle, (titre, niveau) in appariees.items()
                   if titre is None and niveau != 'registre']
        rattaches = sum(1 for _t, niveau in appariees.values()
                        if niveau in ('promotion', 'fondu', 'registre'))
        importees = sum(1 for _t, niveau in appariees.values() if niveau == 'importee')
        return '\n'.join([
            '## Résumé',
            '',
            f'- Classeurs : {len(self.contenu)} reçus, {len(self.retenus)} sources distinctes, '
            f'{len(self.doublons)} doublons écartés.',
            f'- Journal de caisse : {len(ecritures)} {self._q(len(ecritures), "écriture")} unique'
            f'{"" if len(ecritures) == 1 else "s"}, '
            f'{self._fcfa(entrees)} d\'entrées déclarées.',
            f'- Tableaux de suivi : {len(inscriptions)} lignes nommées dans '
            f'{len(self.suivis["stats"])} onglets, {len(mois_payes)} mensualités chiffrées '
            f'({self._fcfa(sum(m[2] for m in mois_payes))}).',
            f'- Base Étudiants : {len(self.base["lignes"])} fiches.',
            f'- Formations rencontrées : {len(self.catalogue)} intitulés — {importees} titres posés '
            f'par la vague 1, {rattaches} promotions ou alias rattachés à une formation, '
            f'{len(a_creer)} encore sans titre.',
            f'- Points douteux : {len(self.suivis["anomalies"]) + len(self.journal["doutes"])}.',
            '',
            'Les décisions attendues sont listées en section 10 du rapport.',
        ] + ([
            '',
            f'- Classeurs ouverts dans Excel au moment de l\'analyse, donc non lus : '
            f'{", ".join(self.inaccessibles)}. Fermez-les et relancez avant l\'import.',
        ] if self.inaccessibles else []))

    @staticmethod
    def _titres_catalogue():
        return Course.objects.values_list('title', flat=True)

    # ------------------------------------------------------------------
    # Chargement et dédoublonnage
    # ------------------------------------------------------------------
    def _charger(self, chemin: Path) -> dict:
        classeur = openpyxl.load_workbook(chemin, data_only=True, read_only=True)
        lignes = {nom: outils.lire_lignes(classeur[nom]) for nom in classeur.sheetnames}
        classeur.close()
        return lignes

    def _empreintes(self):
        """Deux classeurs dont le contenu cellule par cellule est identique sont un seul apport."""
        empreintes = {}
        for nom, feuilles in self.contenu.items():
            signature = '|'.join(
                f'{onglet}#{self._hache(feuilles[onglet])}'
                for onglet in sorted(feuilles) if feuilles[onglet]
            )
            empreintes[nom] = hashlib.md5(signature.encode('utf-8')).hexdigest()[:10]
        par_empreinte = defaultdict(list)
        for nom, empreinte in empreintes.items():
            par_empreinte[empreinte].append(nom)
        retenus, doublons = [], {}
        for noms in par_empreinte.values():
            ordonnes = sorted(noms, key=lambda n: (len(n), n.lower()))
            retenus.append(ordonnes[0])
            for redondant in ordonnes[1:]:
                doublons[redondant] = ordonnes[0]
        return empreintes, sorted(retenus), doublons

    @staticmethod
    def _hache(lignes) -> str:
        rendu = '\n'.join(
            ';'.join(outils.normaliser_texte(valeur) for valeur in ligne) for ligne in lignes
        )
        return hashlib.md5(rendu.encode('utf-8')).hexdigest()[:10]

    @staticmethod
    def _lignes_utililes(lignes) -> int:
        return sum(1 for ligne in lignes if outils.ligne_utile(ligne))

    @staticmethod
    def _fcfa(montant) -> str:
        return f'{int(montant or 0):,} FCFA'.replace(',', ' ')

    @staticmethod
    def _q(total, singulier, pluriel=None) -> str:
        """« 1 écriture » et non « 1 écritures »."""
        if total == 1:
            return singulier
        return pluriel or f'{singulier}s'

    # ------------------------------------------------------------------
    def _section_fichiers(self):
        lignes = [
            '## 1. Fichiers reçus',
            '',
            f'{len(self.contenu)} classeurs déposés : **{len(self.retenus)} apports distincts** '
            f'et {len(self.doublons)} exports redondants (même contenu, repris à chaque export '
            'Google Sheets).',
            '',
            '| Classeur | Onglets | Lignes | Taille | Statut |',
            '| --- | ---: | ---: | ---: | --- |',
        ]
        for nom in sorted(self.contenu, key=lambda n: (n not in self.retenus, n.lower())):
            feuilles = self.contenu[nom]
            utiles = sum(self._lignes_utililes(l) for l in feuilles.values())
            statut = ('source retenue' if nom in self.retenus
                      else f'**doublon** de {self.doublons[nom]}')
            lignes.append(f'| {nom} | {len(feuilles)} | {utiles} | '
                          f'{self.tailles[nom] / 1024:.0f} Ko | {statut} |')
        lignes += ['', 'Les doublons sont écartés de toute la suite de l'
                         '\'analyse : les totaux ci-dessous ne comptent pas deux fois le même argent.', '']
        return '\n'.join(lignes)

    # ------------------------------------------------------------------
    # Journal de caisse
    # ------------------------------------------------------------------
    def _analyser_journal(self):
        lus = []
        for nom in sorted(self.retenus):
            for onglet, lignes in self.contenu[nom].items():
                if not lignes or not MOTIF_JOURNAL.search(outils.sans_accents(onglet).lower()):
                    continue
                lecture, tete = outils.lire_journal(f'{nom} → {onglet}', lignes, onglet)
                if lecture:
                    lus.append({'nom': nom, 'onglet': onglet, 'tete': tete,
                                'ecritures': lecture,
                                'empreintes': {e.empreinte for e in lecture}})
        connues, sources = set(), []
        for index, source in enumerate(lus):
            recoupees = len(source['empreintes'] & connues)
            part = recoupees / len(source['empreintes'])
            if part >= 0.8:
                source['statut'] = (f'**copie** — {recoupees} {self._q(recoupees, "écriture")} sur '
                                    f'{len(source["empreintes"])} déjà vues ailleurs')
            else:
                source['statut'] = 'source retenue'
                connues |= source['empreintes']
            sources.append(source)

        ecritures = [e for s in sources if s['statut'] == 'source retenue' for e in s['ecritures']]
        doutes = []
        for ecriture in ecritures:
            ou = f'{ecriture.onglet} ligne {ecriture.ligne}'
            if ecriture.statut_montant not in ('ok', 'vide', 'nul'):
                doutes.append(('montant_lecture', ou, ecriture.statut_montant))
            if ecriture.date is None and ecriture.montant:
                doutes.append(('date_lecture', ou, 'écriture chiffrée sans date'))
        return {'ecritures': ecritures, 'doutes': doutes, 'sources': sources}

    def _section_journal(self):
        ecritures = self.journal['ecritures']
        lignes = ['## 2. Journal de caisse — la source des paiements', '']
        if not ecritures:
            return '\n'.join(lignes + ['Aucune écriture de caisse lue.', ''])
        lignes += [
            '| Classeur → onglet | En-tête | Lignes lues | Écritures uniques retenues | Statut |',
            '| --- | ---: | ---: | ---: | --- |',
        ]
        for source in self.journal['sources']:
            lignes.append(
                f'| {source["nom"]} → {source["onglet"]} | ligne {source["tete"] + 1} | '
                f'{len(source["ecritures"])} | '
                f'{len(source["empreintes"]) if source["statut"] == "source retenue" else 0} | '
                f'{source["statut"]} |'
            )

        sens = [outils.sans_accents(e.sens).lower() for e in ecritures]
        entrees = [e for e, s in zip(ecritures, sens) if 'entr' in s]
        sorties = [e for e, s in zip(ecritures, sens) if 'sorti' in s]
        sans_sens = [e for e, s in zip(ecritures, sens) if 'entr' not in s and 'sorti' not in s]
        lignes += [
            '',
            f'- **{len(ecritures)} {self._q(len(ecritures), "écriture")}** des journaux non copiés : '
            f'{len(entrees)} entrées pour '
            f'{self._fcfa(sum(e.montant or 0 for e in entrees))}, {len(sorties)} sorties pour '
            f'{self._fcfa(sum(e.montant or 0 for e in sorties))}'
            + (f', {len(sans_sens)} sans sens lisible.' if sans_sens else '.'),
            '',
            'Nature des opérations :',
            '',
            '| Libellé saisi | Écritures | Entrées | Sorties |',
            '| --- | ---: | ---: | ---: |',
        ]
        par_libelle = defaultdict(list)
        for ecriture in ecritures:
            par_libelle[ecriture.libelle or '(sans libellé)'].append(ecriture)
        for libelle, groupe in sorted(par_libelle.items(), key=lambda kv: -len(kv[1])):
            entrees_groupe = [e for e in groupe if 'entr' in outils.sans_accents(e.sens).lower()]
            sorties_groupe = [e for e in groupe if 'sorti' in outils.sans_accents(e.sens).lower()]
            lignes.append(
                f'| {libelle} | {len(groupe)} | '
                f'{self._fcfa(sum(e.montant or 0 for e in entrees_groupe))} | '
                f'{self._fcfa(sum(e.montant or 0 for e in sorties_groupe))} |'
            )
        periodes = Counter((e.mois_paye, e.annee) for e in entrees if e.mois_paye)
        if periodes:
            lignes += ['', 'Périodes facturées (« Mois payé » × « De l\'année ») :', '']
            lignes += [f'- {mois} {annee} : {total} {self._q(total, "écriture")}'
                       for (mois, annee), total in sorted(periodes.items(), key=lambda kv: str(kv[0][1]) + kv[0][0])]
        dates = [e.date for e in ecritures if e.date]
        if dates:
            lignes += ['', f'Plage de dates couverte : **{min(dates):%d/%m/%Y} → {max(dates):%d/%m/%Y}**.']
        personnes = {outils.cle_personne(e.personne) for e in ecritures if e.personne}
        formations = {outils.cle_personne(e.formation) for e in ecritures if e.formation}
        lignes += [
            f'Personnes nommées dans le journal : {len(personnes)}. '
            f'Formations nommées : {len(formations)}.',
            '',
        ]
        return '\n'.join(lignes)

    # ------------------------------------------------------------------
    # Tableaux de suivi par formation
    # ------------------------------------------------------------------
    def _analyser_suivis(self):
        inscriptions, anomalies, stats, ignores = [], [], [], []
        sans_nom = 0
        for nom in sorted(self.retenus):
            for onglet, lignes in self.contenu[nom].items():
                if not lignes or onglet in ONGLETS_HORS_SUIVI:
                    continue
                sans_accents = outils.sans_accents(onglet).lower()
                if MOTIF_JOURNAL.search(sans_accents) or MOTIF_MOIS_ANNEE.match(onglet.strip()) \
                        or MOTIF_SALARIE.search(sans_accents) or MOTIF_BOURSE.search(nom.lower()):
                    continue
                blocs = outils.decouper_blocs(onglet, lignes)
                if not blocs:
                    ignores.append((nom, onglet, self._lignes_utililes(lignes)))
                    continue
                retenues, mois_vus = 0, set()
                for bloc in blocs:
                    mois_vus.update(libelle.strip().lower() for _, libelle in bloc.mois.values())
                    for decalage, ligne in enumerate(bloc.lignes_donnees):
                        ligne_no = bloc.premiere_ligne + decalage + 1
                        troncon = ligne[bloc.debut_colonne:bloc.fin_colonne]
                        if not outils.ligne_utile(troncon):
                            continue
                        extraction = outils.extraire_ligne(bloc, ligne, ligne_no)
                        if extraction is None:
                            # Une ligne qui ne porte qu'un numéro de ligne n'est pas un élève oublié.
                            if any(outils.parse_montant(ligne[c])[0]
                                   for c in range(bloc.debut_colonne, min(bloc.fin_colonne, len(ligne)))):
                                sans_nom += 1
                            continue
                        retenues += 1
                        inscriptions.append(extraction)
                        ou = f'{onglet} ligne {ligne_no}'
                        for type_, detail in extraction.anomalies:
                            anomalies.append((type_, ou, detail))
                if retenues:
                    stats.append((nom, onglet, len(blocs), retenues, sorted(mois_vus)))
                else:
                    # Un onglet de promotion sans aucun nom lisible reste un onglet traité, pas une annexe.
                    ignores.append((nom, onglet, self._lignes_utililes(lignes)))
        return {'inscriptions': inscriptions, 'anomalies': anomalies,
                'stats': stats, 'ignores': ignores, 'sans_nom': sans_nom}

    def _section_suivis(self):
        lignes = ['## 3. Tableaux de suivi par formation', '']
        if not self.suivis['stats']:
            return '\n'.join(lignes + ['Aucun tableau d\'inscription reconnu.', ''])
        par_onglet = defaultdict(list)
        for inscription in self.suivis['inscriptions']:
            par_onglet[inscription.onglet].append(inscription)
        lignes += [
            '| Onglet | Blocs | Lignes nommées | Mensualités encaissées | Total encaissé | '
            'Mensualité pratiquée |',
            '| --- | ---: | ---: | ---: | ---: | --- |',
        ]
        for _, onglet, nb_blocs, retenues, _mois in sorted(self.suivis['stats'],
                                                           key=lambda s: s[1].lower()):
            groupe = par_onglet[onglet]
            mois = [m for i in groupe for m in i.mois if m[2]]
            pratiquee = Counter(i.mensuel_prevu for i in groupe if i.mensuel_prevu).most_common(1)
            lignes.append(
                f'| {onglet} | {nb_blocs} | {retenues} | {len(mois)} | '
                f'{self._fcfa(sum(m[2] for m in mois))} | '
                f'{self._fcfa(pratiquee[0][0]) if pratiquee else "—"} |'
            )
        totales = self.suivis['inscriptions']
        mensuels = [m for i in totales for m in i.mois if m[2]]
        lignes += [
            '',
            f'- **{len(totales)} lignes d\'inscription nommées** dans {len(self.suivis["stats"])} '
            f'onglets ; {self.suivis["sans_nom"]} lignes chiffrées sans nom laissées de côté.',
            f'- {len(mensuels)} mensualités chiffrées pour un total de '
            f'{self._fcfa(sum(m[2] for m in mensuels))}.',
            '- Frais d\'inscription rencontrés : '
            + ', '.join(f'{v:,} FCFA × {n}'.replace(',', ' ')
                        for v, n in Counter(i.frais_inscription for i in totales
                                            if i.frais_inscription).most_common()),
            '- Mensualités annoncées en tête de ligne : '
            + ', '.join(f'{v:,} × {n}'.replace(',', ' ')
                        for v, n in Counter(i.mensuel_prevu for i in totales
                                            if i.mensuel_prevu).most_common()),
        ]
        annees = sorted({a for i in totales for a in i.annees if a})
        lignes += [f'- Années rendues par les colonnes de mois (déduites des dates d\'inscription) : '
                   f'{", ".join(str(a) for a in annees) or "aucune"}.', '']
        if self.suivis['ignores']:
            lignes += ['Onglets ouverts sans aucune ligne d\'élève exploitée :', '']
            lignes += [f'- {nom} → {onglet} ({total} lignes)'
                       for nom, onglet, total in self.suivis['ignores']]
            lignes += ['']
        return '\n'.join(lignes)

    # ------------------------------------------------------------------
    # Feuille « Base Etudiants »
    # ------------------------------------------------------------------
    def _analyser_base(self):
        fiches = []
        for nom in sorted(self.retenus):
            for onglet, lignes in self.contenu[nom].items():
                if outils.sans_accents(onglet).lower() != 'base etudiants':
                    continue
                tete = next((i for i, ligne in enumerate(lignes[:8])
                             if any('prenom' in outils.sans_accents(v).lower() for v in ligne)), None)
                if tete is None:
                    continue
                entete = [outils.sans_accents(v).lower() for v in lignes[tete]]

                def colonne(*mots):
                    return next((c for c, libelle in enumerate(entete)
                                 if any(m in libelle for m in mots)), None)

                colonnes = {
                    'nom': next((c for c, l in enumerate(entete) if l.startswith('nom')), None),
                    'prenom': colonne('prenom'),
                    'telephone': colonne('teleph'),
                    'email': colonne('mail'),
                    'formation': colonne('formation'),
                    'adresse': next((c for c, l in enumerate(entete)
                                     if l.startswith('adresse')), None),
                    'date': colonne('inscription'),
                }

                def cellule(ligne, cle):
                    c = colonnes.get(cle)
                    return ligne[c] if c is not None and c < len(ligne) else None

                for ligne_no, ligne in enumerate(lignes[tete + 1:], start=tete + 2):
                    complet = f'{outils.normaliser_texte(cellule(ligne, "nom"))} ' \
                              f'{outils.normaliser_texte(cellule(ligne, "prenom"))}'.strip()
                    if not complet and not outils.ligne_utile(ligne):
                        continue
                    date, statut = outils.parse_date(cellule(ligne, 'date'))
                    fiches.append({
                        'classeur': nom, 'ligne': ligne_no, 'complet': complet,
                        'nom': outils.normaliser_texte(cellule(ligne, 'nom')),
                        'prenom': outils.normaliser_texte(cellule(ligne, 'prenom')),
                        'cle': outils.cle_personne(complet),
                        'telephone': outils.normaliser_texte(cellule(ligne, 'telephone')),
                        'email': outils.normaliser_texte(cellule(ligne, 'email')),
                        'adresse': outils.normaliser_texte(cellule(ligne, 'adresse')),
                        'formation': outils.normaliser_texte(cellule(ligne, 'formation')),
                        'date': date, 'date_statut': statut,
                    })
        return {'lignes': fiches}

    def _section_base(self):
        fiches = [f for f in self.base['lignes']
                  if f['complet'] or f['email'] or f['telephone']]
        lignes = ['## 4. Feuille « Base Etudiants » — les fiches individuelles', '']
        if not fiches:
            return '\n'.join(lignes + ['Feuille non trouvée ou vide.', ''])
        lignes += [
            f'- **{len(fiches)} fiches**, {len({f["cle"] for f in fiches})} noms distincts.',
            f'- Téléphone renseigné : {sum(1 for f in fiches if f["telephone"])} ; '
            f'e-mail : {sum(1 for f in fiches if f["email"])} ; '
            f'adresse : {sum(1 for f in fiches if f["adresse"])} ; '
            f'date d\'inscription datée : {sum(1 for f in fiches if f["date"])}.',
            '',
            '| Formation citée | Fiches |',
            '| --- | ---: |',
        ]
        for formation, total in Counter(f['formation'] or '(vide)' for f in fiches).most_common():
            lignes.append(f'| {formation} | {total} |')
        lignes.append('')
        partages = [
            ('numéros de téléphone partagés par deux fiches ou plus',
             Counter(f['telephone'] for f in fiches if f['telephone'])),
            ('e-mails partagés par deux fiches ou plus',
             Counter(f['email'].lower() for f in fiches if f['email'])),
            ('noms identiques', Counter(f['cle'] for f in fiches if f['cle'])),
        ]
        for libelle, compteur in partages:
            redondants = {v: n for v, n in compteur.items() if n > 1}
            exemples = ', '.join(f'{v} × {n}' for v, n in list(redondants.items())[:6]) or 'aucun'
            lignes.append(f'- {libelle} : {len(redondants)} — {exemples}.')
        hors_format = [f['email'] for f in fiches if f['email'] and '@' not in f['email']]
        lignes.append(f'- « e-mail » qui n\'est pas une adresse : {len(hors_format)}'
                      + (f' ({", ".join(hors_format[:4])})' if hors_format else ''))
        lignes.append('')
        return '\n'.join(lignes)

    # ------------------------------------------------------------------
    # Recoupement
    # ------------------------------------------------------------------
    def _section_croisement(self):
        fiches = [f for f in self.base['lignes'] if f['complet']]
        inscriptions = self.suivis['inscriptions']
        par_premier_jeton = defaultdict(list)
        for fiche in fiches:
            jetons = sorted(outils.tokens_personne(fiche['complet']))
            if jetons:
                par_premier_jeton[jetons[0]].append(fiche)

        niveau = Counter()
        absents = []
        for inscription in inscriptions:
            jetons = sorted(outils.tokens_personne(inscription.nom))
            candidates = par_premier_jeton.get(jetons[0], []) if jetons else []
            meilleure = None
            for fiche in candidates:
                valeur = outils.niveau_ressemblance(inscription.nom, fiche['complet'])
                if valeur == 'exact':
                    meilleure = 'exact'
                    break
                if valeur == 'probable':
                    meilleure = 'probable'
            niveau[meilleure or 'aucun'] += 1
            if not meilleure:
                absents.append(f'{inscription.nom} — {inscription.onglet}')

        par_personne = defaultdict(set)
        for inscription in inscriptions:
            par_personne[inscription.cle].add(outils.sans_accents(inscription.onglet).lower())
        plurielles = {cle: v for cle, v in par_personne.items() if len(v) > 1}
        cles_journal = {outils.cle_personne(e.personne) for e in self.journal['ecritures'] if e.personne}
        dans_journal = sum(1 for i in inscriptions if i.cle in cles_journal)

        lignes = [
            '## 5. Recoupement des trois sources',
            '',
            f'- Suivi ↔ fiches individuelles : **{niveau["exact"]} correspondances exactes**, '
            f'{niveau["probable"]} probables, {niveau["aucun"]} sans fiche.',
            f'- Suivi ↔ journal de caisse : {dans_journal} lignes de suivi sur '
            f'{len(inscriptions)} retrouvent au moins une écriture de caisse à leur nom.',
            f'- Élèves suivis dans plusieurs formations : {len(plurielles)} '
            '(plusieurs dossiers pour un même compte).',
            '',
        ]
        if absents:
            lignes += ['Élèves des onglets sans fiche individuelle (échantillon) :', '']
            lignes += [f'- {item}' for item in sorted(set(absents))[:self.details]]
            if len(set(absents)) > self.details:
                lignes.append(f'- … {len(set(absents)) - self.details} autres')
            lignes.append('')
        return '\n'.join(lignes)

    # ------------------------------------------------------------------
    # Formations
    # ------------------------------------------------------------------
    def _formations_observees(self):
        observees = {}

        def entree(nom):
            cle = outils.cle_personne(nom)
            if not cle:
                return None
            donnees = observees.get(cle)
            if donnees is None:
                donnees = observees[cle] = {
                    'label': nom.strip(), 'suivi': 0, 'caisse': 0, 'fiches': 0,
                    'inscription': Counter(), 'mensualite': Counter(),
                }
            # Le plus long des intitulés croisés sert d'étiquette : « Gestion informatique »
            # plutôt que la clé triée « informatique de gestion ».
            if len(nom.strip()) > len(donnees['label']):
                donnees['label'] = nom.strip()
            return donnees

        for inscription in self.suivis['inscriptions']:
            donnees = entree(inscription.onglet)
            if donnees:
                donnees['suivi'] += 1
                if inscription.frais_inscription:
                    donnees['inscription'][inscription.frais_inscription] += 1
                if inscription.mensuel_prevu:
                    donnees['mensualite'][inscription.mensuel_prevu] += 1
        for ecriture in self.journal['ecritures']:
            donnees = entree(ecriture.formation)
            if donnees:
                donnees['caisse'] += 1
        for fiche in self.base['lignes']:
            donnees = entree(fiche['formation'])
            if donnees:
                donnees['fiches'] += 1
        return observees

    def _appariement(self):
        """Pour chaque intitulé observé, la formation du catalogue à laquelle il ressemble ou qu'il vise."""
        resultat = {}
        catalogue = list(self._titres_catalogue())
        connus = {titre.lower(): titre for titre in catalogue}
        for cle, donnees in self.catalogue.items():
            declare = self._appariement_declare(cle, connus)
            if declare != (None, None):
                # Une décision de la direction passe avant une ressemblance de chaîne.
                resultat[cle] = declare
                continue
            for titre in catalogue:
                niveau = outils.niveau_ressemblance(donnees['label'], titre)
                if niveau:
                    resultat[cle] = (titre, niveau)
                    break
            else:
                resultat[cle] = (None, None)
        return resultat

    @staticmethod
    def _appariement_declare(cle: str, connus: dict) -> tuple:
        """Ce que le programme d'import décide pour un intitulé que le catalogue ne reconnaît pas."""
        declaree = programme.FORMATIONS.get(cle)
        if declaree and declaree[0].lower() in connus:
            return (declaree[0], 'importee')
        fusion = programme.FUSIONS.get(cle)
        if fusion:
            return (programme.FORMATIONS[fusion][0], 'fondu')
        parente = programme.PROMOTIONS.get(cle)
        if parente:
            return (programme.FORMATIONS[parente][0], 'promotion')
        if cle in programme.HORS_CATALOGUE:
            return (None, 'registre')
        return (None, None)

    def _section_formations(self):
        appariees = self._appariement()
        a_creer = [c for c, (titre, niveau) in appariees.items()
                   if titre is None and niveau != 'registre']
        lignes = [
            '## 6. Formations : ce que disent les classeurs, ce que contient le catalogue',
            '',
            f'{len(self.catalogue)} intitulés rencontrés dans les classeurs (onglets, fiches, '
            f'journal). **{len(a_creer)} ne correspondent à aucune formation du catalogue.**',
            '',
            '| Intitulé observé | Lignes de suivi | Écritures de caisse | Fiches | '
            'Frais d\'inscription vus | Mensualités vues | Correspondance au catalogue |',
            '| --- | ---: | ---: | ---: | --- | --- | --- |',
        ]
        for cle, donnees in sorted(self.catalogue.items(),
                                   key=lambda kv: -(kv[1]['suivi'] + kv[1]['caisse'])):
            titre, niveau = appariees[cle]
            if titre is None:
                correspondence = ('**registre d\'anciens, pas une formation**'
                                  if niveau == 'registre' else '**à créer**')
            elif niveau == 'exact':
                correspondence = f'« {titre} »'
            elif niveau == 'importee':
                correspondence = f'« {titre} » (vague 1 importée)'
            elif niveau == 'fondu':
                correspondence = f'« {titre} » (même enseignement, écrit court)'
            elif niveau == 'promotion':
                correspondence = f'« {titre} » — promotion : devient un groupe, pas une formation'
            else:
                correspondence = f'proche de « {titre} » (à confirmer)'
            lignes.append(
                f'| {donnees["label"]} | {donnees["suivi"]} | {donnees["caisse"]} | {donnees["fiches"]} | '
                + (', '.join(f'{v:,}'.replace(',', ' ') for v in sorted(donnees['inscription'])) or '—') + ' | '
                + (', '.join(f'{v:,}'.replace(',', ' ') for v in sorted(donnees['mensualite'])) or '—') + ' | '
                + correspondence + ' |'
            )
        promot = sorted({
            donnees['label'] for cle, donnees in self.catalogue.items()
            if appariees[cle][1] == 'promotion'
        })
        if promot:
            lignes += [
                '',
                'Ces intitulés sont des **onglets de promotion**, pas des formations nouvelles : '
                f'{", ".join(promot)}. Chacun devient un groupe (`CourseSession`) rattaché à sa '
                'formation, et leurs encaissements ont servi à fixer le tarif de la formation '
                'parente.',
            ]
        lignes += [
            '',
            'Les classeurs encaissent **10 000 FCFA à l\'inscription puis 20 000 à 25 000 FCFA '
            'par mois**. Règle retenue : '
            f'{programme.DUREE_MOIS} mois par formation, frais = mensualité pratiquée × durée, '
            + (f'et une bande de {programme.BORNE_MENSUELLE[0]:,} à '
               f'{programme.BORNE_MENSUELLE[1]:,} FCFA : un tarif lu hors de cette plage y est '
               'ramené. ').replace(',', ' ')
            + 'Le catalogue posé par `seed_demo` suivait déjà cette logique — 60 000 = 3 × 20 000, '
              '120 000 = 6 × 20 000, 50 000 = 2 × 25 000. Aucune de ces lignes n\'a été retouchée. '
            'Les nouvelles formations viennent d\'être créées par `manage.py importer_formations`, '
            'qui lit la mensualité dans les encaissements de l\'onglet plutôt que de l\'inventer.',
            '',
        ]
        return '\n'.join(lignes)

    # ------------------------------------------------------------------
    def _section_etat_base(self):
        cours = ', '.join(self._titres_catalogue())
        importees = Enrollment.objects.filter(notes__contains=programme.MARQUE)
        paye = sum(p.amount for p in Payment.objects.filter(
            enrollment__in=importees))
        saisies = Enrollment.objects.count() - importees.count()
        return '\n'.join([
            '## 7. Ce que contient déjà l\'application',
            '',
            f'- Catalogue : {Course.objects.count()} formations — {cours}.',
            f'- Comptes : {User.objects.count()} utilisateurs, dont '
            f'{User.objects.filter(roles__key="ETUDIANT").distinct().count()} étudiants.',
            f'- {importees.count()} inscriptions venues des classeurs, '
            f'{f"{paye:,} FCFA".replace(",", " ")} encaissés, marquées « {programme.MARQUE} ».',
            (f'- {saisies} inscription(s) restée(s) saisie(s) dans l\'application.'
             if saisies else
             '- Rien de ce qui avait été saisi dans l\'application avant les classeurs n\'est resté.'),
            '',
            'Les lignes venues des classeurs se reconnaissent à leur marque : une commande '
            '`importer_etudiants` relancée les retrouve et ne les duplique pas. Une ligne sans '
            'marque est une écriture de l\'application : elle ne bouge que si l\'opérateur donne '
            '`--efface`, après une copie de `db.sqlite3` dans `backups/`.',
            '',
        ])

    # ------------------------------------------------------------------
    # Annexes
    # ------------------------------------------------------------------
    def _analyser_annexes(self):
        controles, salaries, autres = [], [], []
        bourses = {'lignes': 0, 'paye': 0, 'reste': 0, 'statuts': Counter()}
        feuilles_journal = {s['onglet'] for s in self.journal['sources']}
        feuilles_vuees = {onglet for _, onglet, *_ in self.suivis['stats']} | \
                         {onglet for _, onglet, _ in self.suivis['ignores']}
        for nom in sorted(self.retenus):
            if MOTIF_BOURSE.search(nom.lower()):
                for lignes in self.contenu[nom].values():
                    self._lire_bourses(lignes, bourses)
                continue
            for onglet, lignes in self.contenu[nom].items():
                if not lignes or onglet in feuilles_journal or onglet in feuilles_vuees \
                        or onglet in ONGLETS_HORS_SUIVI:
                    continue
                sans_accents = outils.sans_accents(onglet).lower()
                if MOTIF_MOIS_ANNEE.match(onglet.strip()):
                    controles.append((nom, onglet, self._lignes_utililes(lignes)))
                elif MOTIF_SALARIE.search(sans_accents):
                    salaries.append((nom, onglet, self._lignes_utililes(lignes)))
                else:
                    autres.append((nom, onglet, self._lignes_utililes(lignes)))
        return {'controles': controles, 'salaries': salaries,
                'bourses': bourses, 'autres': autres}

    @staticmethod
    def _lire_bourses(lignes, bourses):
        tete = next((i for i, ligne in enumerate(lignes[:5])
                     if any('statut' in outils.sans_accents(v).lower() for v in ligne)), None)
        if tete is None:
            return

        def colonne(*mots):
            return next((c for c, v in enumerate(lignes[tete])
                         if all(outils.sans_accents(m).lower() in
                                outils.sans_accents(v).lower() for m in mots)), None)

        paye, reste, statut = colonne('montant', 'pay'), colonne('reste'), colonne('statut')
        for ligne in lignes[tete + 1:]:
            if not outils.ligne_utile(ligne):
                continue
            bourses['lignes'] += 1
            for index, cle in ((paye, 'paye'), (reste, 'reste')):
                if index is not None and index < len(ligne):
                    montant, _statut, _brut = outils.parse_montant(ligne[index])
                    bourses[cle] += montant or 0
            if statut is not None and statut < len(ligne):
                valeur = outils.sans_accents(ligne[statut]).lower()
                if valeur:
                    bourses['statuts'][valeur] += 1

    def _section_annexes(self):
        annexes = self.annexes
        bourses = annexes['bourses']
        lignes = ['## 8. Les autres feuilles déposées', '']
        if annexes['controles']:
            lignes += [
                f'- **Contrôles mensuels de caisse** : {len(annexes["controles"])} feuilles de mois '
                f'({", ".join(o for _, o, _ in annexes["controles"][:6])}…). Même argent que le '
                'journal, présentation différente : une seule des deux sources sera importée.',
            ]
        if annexes['salaries']:
            lignes += [f'- **Fiche des salariés** : {annexes["salaries"][0][2]} lignes '
                       '(formateurs et personnel, honoraires par mois). Ce sont des dépenses de '
                       'caisse, pas des paiements d\'élèves.']
        if bourses['lignes']:
            lignes += [
                f'- **Procédure d\'étude au Maroc** : {bourses["lignes"]} dossiers de bourse, '
                f'{self._fcfa(bourses["paye"])} déjà payés, {self._fcfa(bourses["reste"])} restants'
                + (f' ; statuts : {", ".join(f"{k}×{v}" for k, v in bourses["statuts"].most_common())}'
                   if bourses['statuts'] else '') + '.',
            ]
        lignes += [
            '- **Rapport de boost** : grille de prospection commerciale, sans données d\'élèves '
            'exploitables telles quelles.',
            '- **Equipe Romard** : suivi d\'une équipe de vente à l\'étranger (intitulés en turc, '
            'ex. « Sayfa2 »), sans lien avec l\'école. Je propose de ne pas l\'importer.',
            '',
        ]
        if annexes['autres']:
            lignes += ['Feuilles non classées :', '']
            lignes += [f'- {nom} → {onglet} ({total} lignes)' for nom, onglet, total in annexes['autres']]
            lignes += ['']
        return '\n'.join(lignes)

    # ------------------------------------------------------------------
    def _section_doutes(self):
        groupes = defaultdict(list)
        for type_, ou, detail in self.suivis['anomalies'] + self.journal['doutes']:
            groupes[type_].append(f'{ou} : {detail}' if detail else ou)
        lignes = [
            '## 9. Cellules douteuses à trancher',
            '',
            f'{sum(len(v) for v in groupes.values())} points relevés. Les formations et les '
            'élèves sont importables malgré eux ; les montants ne le sont pas tous.',
            '',
        ]
        libelles = {
            'montant_doutueux': 'cases de mois remplies d\'autre chose qu\'un montant (« * », '
                                '« ok », « 550000 AVI et assu »)',
            'sans_date_inscription': 'lignes sans date d\'inscription exploitable',
            'date_decalee': 'date d\'inscription saisie hors de sa colonne',
            'date_hors_plage': 'date impossible lue dans une case d\'inscription '
                               '(montant pris pour un numéro de série Excel)',
            'date_reformatee': 'date d\'inscription stockée comme un nombre, à convertir',
            'nom_eclate': 'nom réparti sur deux colonnes',
            'montant_improbable': 'case de mois remplie par un numéro de ligne, pas un montant',
            'frais_inscription_douteux': 'frais d\'inscription non chiffrés',
            'frais_mensuel_douteux': 'mensualité prévue non chiffrée',
            'montant_lecture': 'montants de caisse non chiffrés',
            'date_lecture': 'écritures de caisse chiffrées sans date',
        }
        for type_ in sorted(groupes, key=lambda t: -len(groupes[t])):
            lignes += [f'### {libelles.get(type_, type_)} — {len(groupes[type_])} cas', '']
            lignes += [f'- {item}' for item in groupes[type_][:self.details]]
            if len(groupes[type_]) > self.details:
                lignes.append(f'- … {len(groupes[type_]) - self.details} autres du même type')
            lignes.append('')
        return '\n'.join(lignes)

    def _section_decisions(self):
        appariees = self._appariement()
        a_creer = sorted({
            donnees['label'] for cle, donnees in self.catalogue.items()
            if appariees[cle][0] is None and appariees[cle][1] != 'registre'
        })
        fiches = [f for f in self.base['lignes'] if f['complet']]
        return '\n'.join([
            '## 10. Décisions, vague par vague',
            '',
            f'1. **Démonstration en base** : accord du 02/11/2026 pour effacer ce que l\'application '
            'contenait avant les classeurs. `manage.py importer_etudiants --ecrire --efface` supprime '
            'les dossiers, paiements et entrées de caisse qui ne portent pas la marque de l\'import ; '
            'les sorties de caisse, les comptes et le catalogue restent. Une copie de `db.sqlite3` '
            'dans `backups/` est exigée avant l\'écriture.',
            (f'2. **{len(a_creer)} formations à créer** : {", ".join(a_creer)}. Rien n\'a été '
             'écrit pour elles.' if a_creer else
             '2. **Formations** : acquises — 13 lignes créées le 02/11/2026 par '
             '`manage.py importer_formations` (9 mois, mensualité lue dans les encaissements de '
             'l\'onglet, bornée à la bande 20 000–25 000 FCFA). Les intitulés de promotion deviennent '
             'des groupes (`CourseSession`) à la vague des inscriptions.'),
            (f'3. **Identité des élèves** : {len(fiches)} lignes de fiches individuelles pour les '
             'noms des onglets ; les comptes sans adresse reçoivent une adresse de repli '
             '« @sans-adresse.local » que le secrétariat remplace. Aucun mot de passe : '
             'la connexion reste à ouvrir par l\'école.'
             if Enrollment.objects.filter(notes__contains=programme.MARQUE).exists() else
             '3. **Identité des élèves** : les fiches individuelles ne couvrent '
             'pas tous les noms des onglets. Les comptes manquants seraient créés sans e-mail '
             'ni mot de passe, marqués « dossier incomplet », à finir par le secrétariat.'),
            '4. **Un élève, plusieurs formations** : une inscription par onglet, donc plusieurs '
            "dossiers pour un même compte ; aucun tarif déjà encaissé n'est retouché.",
            '5. **Source des paiements** : la vague 2 retient les cases des onglets de suivi '
            '(frais d\'inscription et mensualités réellement saisis). Le journal de caisse '
            '(section 2) sera comparé à part : les feuilles de contrôle mensuel (section 8) sont '
            'le même argent et ne seront pas repassées. Les cases ambiguës restent non saisies, '
            'avec une liste à régulariser.',
            '6. **Mois et années** : dans les onglets, les colonnes ne portent que le nom du '
            'mois ; l\'année est déduite de la date d\'inscription. Le journal, lui, indique '
            '« Mois payé » et « De l\'année » : c\'est lui qui fera foi à la réconciliation.',
            '7. **Orthographe de la marque** : les documents écrivent « UNIVERSE ACADEMY », '
            'l\'interface « Univers Academy ». Confirmer le nom à afficher.',
            '8. **Equipe Romard** : sans lien avec l\'école ; à écarter.',
            '9. **Registre des anciens et « FRANCAIS »** : 26 lignes du registre des anciens et '
            'l\'onglet FRANCAIS sont écartés faute d\'appariement certain avec le catalogue ; '
            'une décision de la direction les ferait entrer.',
            '',
            'Import par vagues, une copie de `db.sqlite3` dans `backups/` avant chacune. '
            '**Vague 1 (formations) et vague 2 (élèves, groupes, inscriptions, encaissements) '
            'écrites le 02/11/2026.** Reste : la réconciliation avec le journal de caisse. Les '
            'points 1 à 3 et 9 sont tranchés côté écriture ; les points 5, 6, 7 et 8 attendent '
            'une réponse de la direction.',
            '',
        ])
