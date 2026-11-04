"""Préparation de la vague 2 : les élèves du classeur, leurs dossiers, leurs groupes et leurs encaissements.

Fonctions pures — aucune écriture, aucun accès à la base. La commande ``importer_etudiants``
lit les classeurs avec ``analyser_donnees``, appelle ``preparer()`` puis pose les lignes.
Ce module décide aussi ce qui ne doit surtout pas être écrit : doublons, intitulés seulement
ressemblants, cases de mois douteuses.

Règles validées par la direction (rapport ``docs/donnees``, section 10) : une fiche = un compte ;
un onglet, ou un de ses blocs, = un groupe ; le tarif vient du catalogue posé par la vague 1 ;
l'argent vient des cases remplies, jamais d'une moyenne.
"""
from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict
from dataclasses import dataclass, field

from core import data_tools as outils
from core import programme_import as programme

MARQUE = programme.MARQUE

# Un intitulé d'onglet n'est retenu que s'il désigne une formation du catalogue sans aucun
# doute. « probable » (FRANCAIS ≈ « Francais A2 ») reste à trancher par la direction.
NIVEAUX_RETENUS = ('exact', 'importee', 'fondu', 'promotion')

MOTIF_ADRESSE = re.compile(r'^[^\s@]+@[^\s@]+\.[A-Za-z]{2,}$')
MOTIF_LETTRE = re.compile(r'[A-Za-zÀ-Þ]')
MOTIF_TERME = re.compile(r'(termin|fini|diplome|gradue|abandon|arre)', re.I)

# L'e-mail sert d'identifiant de connexion : une fiche sans adresse en reçoit une de repli,
# dont le suffixe signale au secrétariat qu'elle reste à remplacer.
SUFFIXE_SANSDRESSE = '@sans-adresse.local'


# ---------------------------------------------------------------------------
# Lectures du classeur
# ---------------------------------------------------------------------------
def adresse_valide(valeur: object) -> bool:
    return bool(MOTIF_ADRESSE.match(outils.normaliser_texte(valeur).lower()))


def normaliser_telephone(valeur: object) -> str:
    """« +242 06 78 13 74 0 », « 00242067813740 » et « 067813740 » rendent la même clé.

    Huit chiffres minimum : un numéro tronqué rapprocherait deux élèves qui n'ont rien
    en commun.
    """
    chiffres = re.sub(r'\D', '', outils.normaliser_texte(valeur))
    for indice in ('00242', '242'):
        if chiffres.startswith(indice) and len(chiffres) - len(indice) >= 8:
            return chiffres[len(indice):]
    return chiffres if len(chiffres) >= 8 else ''


def decouper_nom(complet: object) -> tuple[str, str]:
    """« LOUAMBA Brivah » → ('LOUAMBA', 'Brivah').

    Le classeur écrit le nom de famille en majuscules et les prénoms derrière : la casse
    fait la coupure, rien n'est deviné. Sans césure lisible, tout part dans le nom et le
    secrétariat complète le prénom.
    """
    jetons = [jeton for jeton in re.split(r'\s+', outils.normaliser_texte(complet)) if jeton]
    fin = 0
    while fin < len(jetons) and jetons[fin].isupper() and MOTIF_LETTRE.search(jetons[fin]):
        fin += 1
    if not jetons or fin == 0 or fin == len(jetons):
        return ' '.join(jetons), ''
    return ' '.join(jetons[:fin]), ' '.join(jetons[fin:])


def ajouter_mois(jour: dt.date, nombre: int) -> dt.date:
    total = jour.month - 1 + nombre
    annee = jour.year + total // 12
    mois = total % 12 + 1
    trente_et_un = {1, 3, 5, 7, 8, 10, 12}
    dernier = 31 if mois in trente_et_un else (30 if mois in {4, 6, 9, 11} else
                                               29 if annee % 4 == 0 and
                                               (annee % 100 != 0 or annee % 400 == 0) else 28)
    return dt.date(annee, mois, min(jour.day, dernier))


# ---------------------------------------------------------------------------
# Ce que l'import s'apprête à écrire
# ---------------------------------------------------------------------------
@dataclass
class Compte:
    """Un élève rencontré dans le classeur, rapproché ou non d'un compte déjà ouvert."""
    cle: str
    nom: str
    prenom: str
    email: str = ''
    telephone: str = ''
    adresse: str = ''
    identifiant: str | None = None
    correspondance: str = ''
    origines: list = field(default_factory=list)

    @property
    def a_creer(self) -> bool:
        return self.identifiant is None

    @property
    def affiche(self) -> str:
        return ' '.join(part for part in (self.prenom, self.nom) if part).strip()

    @property
    def sans_adresse(self) -> bool:
        return not adresse_valide(self.email)


@dataclass
class Groupe:
    """Un onglet, ou un bloc d'un onglet, devient une promotion rattachée au catalogue."""
    cle: str
    onglet: str
    classeur: str
    titre: str
    debut: dt.date
    fin: dt.date
    statut: str
    mensuelle: int
    effectif: int
    debut_deduit: bool = False


@dataclass
class Inscription:
    compte: Compte
    groupe: Groupe
    date_debut: dt.date | None
    tarif: int
    net: int
    statut: str
    note: str


@dataclass
class Paiement:
    inscription: Inscription
    montant: int
    jour: dt.date
    motif: str
    note: str


@dataclass
class Plan:
    comptes: list = field(default_factory=list)
    groupes: list = field(default_factory=list)
    inscriptions: list = field(default_factory=list)
    paiements: list = field(default_factory=list)
    ecarts: list = field(default_factory=list)
    ecartes: list = field(default_factory=list)
    fiches: int = 0

    @property
    def montant_total(self) -> int:
        return sum(p.montant for p in self.paiements)

    def compte_de(self, cle: str) -> Compte:
        return next(c for c in self.comptes if c.cle == cle)


# ---------------------------------------------------------------------------
# Fiches individuelles et rapprochement des identités
# ---------------------------------------------------------------------------
def souche_fiches(base_lignes: list) -> dict[str, dict]:
    """Une entrée par élève : les lignes répétées de « Base Etudiants » fusionnent."""
    par_cle: dict[str, dict] = {}
    for fiche in base_lignes:
        cle = outils.cle_personne(fiche.get('complet'))
        if not cle:
            continue
        accumulee = par_cle.setdefault(cle, {
            'cle': cle, 'nom': fiche.get('nom') or '', 'prenom': fiche.get('prenom') or '',
            'emails': [], 'telephones': [], 'adresses': [], 'date': None, 'lignes': 0,
        })
        accumulee['lignes'] += 1
        for champ, source in (('emails', 'email'), ('telephones', 'telephone'),
                              ('adresses', 'adresse')):
            valeur = outils.normaliser_texte(fiche.get(source))
            # Deux adresses collées dans une même case : chacune est jugée pour soi.
            fragments = valeur.split() if champ == 'emails' and valeur else [valeur]
            for fragment in fragments:
                if fragment and fragment not in accumulee[champ]:
                    accumulee[champ].append(fragment)
        date = fiche.get('date')
        if date and (accumulee['date'] is None or date < accumulee['date']):
            accumulee['date'] = date
    return par_cle


def index_des_comptes(existants: list) -> dict:
    """Trois index de rapprochement, garnis seulement quand la clé est portante."""
    index = {'email': {}, 'telephone': {}, 'nom': {}}
    for compte in existants:
        email = outils.normaliser_texte(compte.get('email')).lower()
        if adresse_valide(email):
            index['email'].setdefault(email, compte)
        telephone = normaliser_telephone(compte.get('telephone'))
        if telephone:
            index['telephone'].setdefault(telephone, compte)
        cle = outils.cle_personne(f"{compte.get('prenom') or ''} {compte.get('nom') or ''}")
        if cle:
            index['nom'].setdefault(cle, compte)
    return index


def _rapprocher(cle: str, email: str, telephone: str, index: dict, pris: set) -> tuple:
    """Le compte déjà ouvert qui correspond, ou rien. Un compte ne sert qu'une seule fois."""
    for motif, table, valeur in (('email', index['email'], email.lower()),
                                 ('telephone', index['telephone'], telephone),
                                 ('nom', index['nom'], cle)):
        if not valeur:
            continue
        compte = table.get(valeur)
        if compte is not None and compte['id'] not in pris:
            pris.add(compte['id'])
            return compte['id'], motif
    return None, ''


def comptes_a_poser(fiches: dict, eleves: dict, index: dict, ecarts: list) -> list:
    """Un Compte par élève, rapproché d'un compte existant seulement si l'identité est certaine.

    Une ressemblance « probable » ne suffit pas : LOUAMBA Brivah et LOUAMBA severdy sont
    deux élèves, et un compte déjà ouvert ne se rebaptise pas.
    """
    par_cle: dict[str, Compte] = {}
    pris: set = set()

    def loger(cle, nom, prenom, email, telephone, adresse, origine) -> Compte:
        compte = par_cle.get(cle)
        if compte is None:
            compte = par_cle[cle] = Compte(cle=cle, nom=nom, prenom=prenom, email=email,
                                           telephone=telephone, adresse=adresse)
            compte.identifiant, compte.correspondance = _rapprocher(
                cle, email, telephone, index, pris)
        if origine not in compte.origines:
            compte.origines.append(origine)
        return compte

    for cle, fiche in fiches.items():
        email = next((e for e in fiche['emails'] if adresse_valide(e)), '')
        telephone = normaliser_telephone(
            next((t for t in fiche['telephones'] if normaliser_telephone(t)), ''))
        compte = loger(cle, fiche['nom'], fiche['prenom'], email, telephone,
                       next(iter(fiche['adresses']), ''),
                       f'fiche « Base Etudiants » × {fiche["lignes"]}')
        if fiche['emails'] and not email:
            ecarts.append(('adresse qui n\'est pas une e-mail', 'Base Etudiants',
                           ', '.join(fiche['emails'])))
        if len({normaliser_telephone(t) for t in fiche['telephones'] if t}) > 1:
            ecarts.append(('numéros multiples pour un même nom', compte.affiche,
                           ', '.join(fiche['telephones'])))
        if compte.correspondance == 'nom' and fiche['emails']:
            # Le compte est retrouvé par le nom seul : sa ligne de connexion ne se
            # rebaptise pas, le secrétariat tranche.
            ecarts.append(('compte retrouvé par le nom seul', compte.affiche,
                           f'fiche : {email or fiche["emails"][0]}'))

    for cle, ligne in eleves.items():
        nom, prenom = decouper_nom(ligne.nom)
        loger(cle, nom or outils.normaliser_texte(ligne.nom), prenom, '', '', '',
              f'onglet {ligne.onglet}')
        if cle not in fiches:
            ecarts.append(('élève sans fiche individuelle', ligne.onglet, ligne.nom))

    # Deux fiches avec le même numéro sont deux orthographes possibles d'une même personne,
    # ou deux élèves d'une même famille : le classeur ne tranche pas, le secrétariat si.
    par_telephone: dict[str, list] = defaultdict(list)
    for compte in par_cle.values():
        for numero in {normaliser_telephone(t) for t in
                       (fiches.get(compte.cle, {}).get('telephones') or []) if t}:
            if numero:
                par_telephone[numero].append(compte)
    for numero, concernes in sorted(par_telephone.items()):
        if len(concernes) > 1:
            ecarts.append(('même numéro pour deux fiches', numero,
                           ' | '.join(c.affiche or c.cle for c in concernes)))
    return list(par_cle.values())


# ---------------------------------------------------------------------------
# Le plan
# ---------------------------------------------------------------------------
def preparer(analyse, tarifs: dict, existants: list, appariement: dict, classeur: str = '',
             aujourd_hui: dt.date | None = None) -> Plan:
    """Transforme l'analyse des classeurs en lignes prête à écrire, avec ses listes de contrôle.

    ``tarifs`` : titre du catalogue -> {'frais': net dû, 'duree': mois, 'mensuel': mensualité}.
    ``existants`` : comptes déjà ouverts, sous forme de dicts id / email / telephone / nom / prenom.
    """
    aujourd_hui = aujourd_hui or dt.date.today()
    plan = Plan()
    ecarts = plan.ecarts

    classeur_par_onglet = {onglet: nom for nom, onglet, *_ in analyse.suivis['stats']}
    lignes = [l for l in analyse.suivis['inscriptions']
              if not classeur or classeur_par_onglet.get(l.onglet) == classeur]

    retenues = []
    for ligne in lignes:
        cle_onglet = outils.cle_personne(ligne.onglet)
        titre, niveau = appariement.get(cle_onglet, (None, None))
        if niveau == 'registre':
            plan.ecartes.append(('registre d\'anciens, pas une formation', ligne.onglet, ligne.nom))
            continue
        if titre is None or niveau not in NIVEAUX_RETENUS:
            plan.ecartes.append(('formation non confirmée', ligne.onglet,
                                 f'{ligne.nom} — appariement « {niveau or "aucun"} »'))
            continue
        if titre not in tarifs:
            plan.ecartes.append(('formation absente du catalogue', ligne.onglet, ligne.nom))
            continue
        retenues.append((ligne, titre, cle_onglet))

    une_ligne_par_eleve: dict[str, object] = {}
    for ligne, _titre, _cle in retenues:
        une_ligne_par_eleve.setdefault(ligne.cle, ligne)
    fiches = souche_fiches(analyse.base['lignes'])
    plan.fiches = len(fiches)
    plan.comptes = comptes_a_poser(fiches, une_ligne_par_eleve,
                                   index_des_comptes(existants), ecarts)

    groupes: dict[str, Groupe] = {}
    for ligne, titre, cle_onglet in retenues:
        cle = f'{cle_onglet}|{ligne.bloc}'
        if cle in groupes:
            continue
        dates = [l.date_inscription for l, t, c in retenues if f'{c}|{l.bloc}' == cle
                 if l.date_inscription]
        tarif = tarifs[titre]
        if dates:
            debut, déduit = min(dates), False
        else:
            debut, déduit = aujourd_hui.replace(day=1), True
            ecarts.append(('aucune date dans l\'onglet', ligne.onglet,
                           f'début posé au {debut:%d/%m/%Y} faute de date d\'inscription'))
        fin = ajouter_mois(debut, tarif['duree'])
        groupes[cle] = Groupe(
            cle=cle, onglet=ligne.onglet, classeur=classeur_par_onglet.get(ligne.onglet, classeur),
            titre=titre, debut=debut, fin=fin, mensuelle=tarif['mensuel'],
            statut='COMPLETED' if fin < aujourd_hui else 'ACTIVE',
            effectif=sum(1 for l, t, c in retenues if f'{c}|{l.bloc}' == cle),
            debut_deduit=déduit,
        )

    par_dossier: dict[tuple, Inscription] = {}
    for ligne, titre, cle_onglet in retenues:
        groupe = groupes[f'{cle_onglet}|{ligne.bloc}']
        compte = plan.compte_de(ligne.cle)
        dossier = (compte.cle, groupe.cle)
        if dossier in par_dossier:
            inscription = par_dossier[dossier]
            ecarts.append(('élève en double dans le même groupe', groupe.onglet,
                           f'{ligne.nom} — ligne {ligne.ligne} ignorée, '
                           f'{len([m for m in ligne.mois if m[2]])} mensualité(s) non reprise(s)'))
            continue
        inscription = Inscription(
            compte=compte, groupe=groupe, date_debut=ligne.date_inscription,
            tarif=tarifs[titre]['frais'], net=tarifs[titre]['frais'],
            statut='COMPLETED' if MOTIF_TERME.search(ligne.commentaire) else 'ACTIVE',
            note=(f'{MARQUE} — {groupe.classeur}, onglet {groupe.onglet}, ligne {ligne.ligne}'
                  + (f' | {ligne.commentaire}' if ligne.commentaire else '')),
        )
        par_dossier[dossier] = inscription
        plan.inscriptions.append(inscription)

        if ligne.frais_inscription:
            plan.paiements.append(Paiement(
                inscription=inscription, montant=ligne.frais_inscription,
                jour=ligne.date_inscription or groupe.debut, motif='Frais d\'inscription',
                note=f'{MARQUE} — {groupe.onglet} ligne {ligne.ligne}'))
        for numero, libelle, montant, statut_montant, brut in ligne.mois:
            if montant is None:
                if statut_montant in ('ambigu', 'texte') and brut:
                    ecarts.append(('case de mois non chiffrée', groupe.onglet,
                                   f'{ligne.nom} — {libelle} = « {brut} »'))
                continue
            annee = (outils.annee_du_mois(numero, ligne.date_inscription)
                     or outils.annee_du_mois(numero, groupe.debut)
                     or groupe.debut.year)
            jour = dt.date(annee, numero, 1)
            if jour > aujourd_hui:
                # Une case chiffrée pour un mois qui n'est pas encore commencé
                # annonce le plan de la promotion, elle ne prouve pas que
                # l'argent est entré. Rien n'est porté en paiement : la ligne est
                # signalée et la direction dira s'il s'agit d'une avance.
                ecarts.append(('mensualité d\'un mois non encore commencé',
                               groupe.onglet,
                               f'{ligne.nom} — {libelle} {annee} : '
                               f'{montant:,} FCFA'.replace(',', ' ')
                               + ' ne sont pas encore encaissés'))
                continue
            plan.paiements.append(Paiement(
                inscription=inscription, montant=montant, jour=jour,
                motif='Mensualité',
                note=f'{MARQUE} — {libelle} {annee} — {groupe.onglet} ligne {ligne.ligne}'))

        if ligne.mensuel_prevu and not (programme.BORNE_MENSUELLE[0]
                                        <= ligne.mensuel_prevu <= programme.BORNE_MENSUELLE[1]):
            ecarts.append(('mensualité annoncée hors de la bande', groupe.onglet,
                           f'{ligne.nom} — {ligne.mensuel_prevu:,} FCFA'.replace(',', ' ')))
        if not ligne.date_inscription:
            ecarts.append(('date d\'inscription absente', groupe.onglet, ligne.nom))

    groupe_cles = list(groupes)
    plan.groupes = [groupes[cle] for cle in groupe_cles]

    paye_par_dossier = defaultdict(int)
    for paiement in plan.paiements:
        paye_par_dossier[id(paiement.inscription)] += paiement.montant
    par_inscription = {id(i): i for i in plan.inscriptions}
    for cle_inscription, total in paye_par_dossier.items():
        inscription = par_inscription[cle_inscription]
        if total > inscription.net:
            ecarts.append(('trop-perçu', inscription.groupe.onglet,
                           f'{inscription.compte.affiche} — {total:,} FCFA encaissés pour '
                           f'{inscription.net:,} FCFA dus'.replace(',', ' ')))
    return plan
