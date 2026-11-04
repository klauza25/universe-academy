"""Lecture des classeurs Excel déposés dans ``docs/donnees``.

Fonctions pures, sans accès à la base : la commande ``analyser_donnees`` s'en
sert pour produire le rapport préalable à toute importation.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import dataclass, field


MOIS_FR = (
    'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
    'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre',
)


def normaliser_texte(valeur: object) -> str:
    """Rend une cellule comparable : dates en ISO, entiers sans ``.0``, espaces propres."""
    if valeur is None:
        return ''
    if isinstance(valeur, dt.datetime):
        return valeur.date().isoformat()
    if isinstance(valeur, dt.date):
        return valeur.isoformat()
    if isinstance(valeur, bool):
        return str(valeur)
    if isinstance(valeur, float) and valeur.is_integer():
        return str(int(valeur))
    return str(valeur).replace('\u00a0', ' ').replace('\u202f', ' ').strip()


def sans_accents(valeur: object) -> str:
    decompose = unicodedata.normalize('NFKD', normaliser_texte(valeur))
    return ''.join(c for c in decompose if not unicodedata.combining(c)).strip()


MOIS_SANS_ACCENT = {sans_accents(m): i + 1 for i, m in enumerate(MOIS_FR)}

CLE_NETTOYEE = re.compile(r'[^a-z0-9]+')


def tokens_personne(valeur: object) -> frozenset[str]:
    """Jetons comparables d'un nom : sans accent, sans casse, sans ponctuation."""
    return frozenset(t for t in CLE_NETTOYEE.split(sans_accents(valeur).lower()) if t)


def cle_personne(valeur: object) -> str:
    return ' '.join(sorted(tokens_personne(valeur)))


def niveau_ressemblance(gauche: object, droite: object) -> str | None:
    """``'exact'`` si les jetons coïncident, ``'probable'`` si l'un des noms est inclus
    dans l'autre (le classeur mélange « GNEKOUMOU LIBALA L » et « GNEKOUMOU » +
    « LIBALA Landry »), ``None`` sinon. Les jetons de moins de quatre lettres
    (initiales, particules) ne prouvent rien et sont ignorés.
    """
    a, b = tokens_personne(gauche), tokens_personne(droite)
    if not a or not b:
        return None
    if a == b:
        return 'exact'
    a_forts = {t for t in a if len(t) >= 4}
    b_forts = {t for t in b if len(t) >= 4}
    if a_forts and b_forts and (a_forts <= b_forts or b_forts <= a_forts):
        return 'probable'
    return None


# ---------------------------------------------------------------------------
# Montants
# ---------------------------------------------------------------------------
UNITE_MONETAIRE = re.compile(r'(fcfa|cfa|xaf|francs?)', re.I)
MARQUE_SECHE = re.compile(r'[*\-–—x×./]+$')
NOMBRE = re.compile(r'\d+(?:[.,]\d+)?')
DIGITES = re.compile(r'[\d.,]+')


def _nombre_vers_montant(fragment: str) -> int:
    """« 150,000 » → 150000 ; « 20000.0 » → 20000 ; « 20,5 » → 20."""
    if ',' in fragment:
        entier, _, decimale = fragment.partition(',')
        if len(decimale) == 3:
            return int(entier) * 1000
        return int(float(f'{entier}.{decimale}'))
    return int(round(float(fragment)))


def parse_montant(valeur: object) -> tuple[int | None, str, str]:
    """→ ``(montant, statut, brut)``.

    Statuts : ``vide``, ``nul`` (un 0 saisi = mois non payé), ``ok`` (nombre),
    ``ok_texte`` (nombre écrit avec unité ou espacement, ex. « 20 000FCFA »),
    ``marque`` (``*``, « - »…), ``texte`` (un mot, aucun chiffre),
    ``ambigu`` (plusieurs chiffres ou des lettres collées au montant).
    """
    brut = normaliser_texte(valeur)
    if brut == '':
        return None, 'vide', brut
    if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
        montant = int(round(float(valeur)))
        return (montant, 'ok', brut) if montant else (None, 'nul', brut)

    compacte = re.sub(r'\s+', '', UNITE_MONETAIRE.sub(' ', brut))
    fragments = NOMBRE.findall(compacte)
    lettres_restantes = DIGITES.sub('', compacte)
    if not fragments:
        return None, ('marque' if MARQUE_SECHE.match(compacte) else 'texte'), brut
    if len(fragments) == 1 and not lettres_restantes:
        montant = _nombre_vers_montant(fragments[0])
        return (montant, 'ok_texte', brut) if montant else (None, 'nul', brut)
    if len(fragments) == 1 and sans_accents(lettres_restantes).lower() in MOIS_SANS_ACCENT:
        return _nombre_vers_montant(fragments[0]), 'ok_texte', brut
    return None, 'ambigu', brut


# ---------------------------------------------------------------------------
# Dates et mois
# ---------------------------------------------------------------------------
FORMATS_DATE = (
    '%d/%m/%Y', '%d.%m.%Y', '%d-%m-%Y', '%Y-%m-%d',
    '%d/%m/%y', '%d-%m-%y', '%d %B %Y', '%d %b %Y',
)
SERIE_EXCEL_PLANCHER = 20000  # ≈ 1954 : en dessous, un nombre n'est pas une date
ANNEE_ECOLE_MIN = 2015
ANNEE_ECOLE_MAX = dt.date.today().year + 2
SEUIL_PAIEMENT_MIN = 500  # en dessous, la case est un compteur de lignes, pas un montant


def date_serie_excel(valeur: float) -> dt.date | None:
    if SERIE_EXCEL_PLANCHER <= valeur < 60000:
        return dt.date(1899, 12, 30) + dt.timedelta(days=int(valeur))
    return None


def parse_date(valeur: object) -> tuple[dt.date | None, str]:
    """→ ``(date, statut)`` ; statut dans ``ok``, ``serie``, ``texte``, ``vide``, ``inconnu``."""
    if valeur is None or normaliser_texte(valeur) == '':
        return None, 'vide'
    if isinstance(valeur, dt.datetime):
        return valeur.date(), 'ok'
    if isinstance(valeur, dt.date):
        return valeur, 'ok'
    if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
        date = date_serie_excel(float(valeur))
        return (date, 'serie') if date else (None, 'inconnu')
    brut = normaliser_texte(valeur)
    for format_date in FORMATS_DATE:
        try:
            return dt.datetime.strptime(brut, format_date).date(), 'texte'
        except ValueError:
            continue
    return None, 'inconnu'


def date_verossemblable(date: dt.date | None) -> bool:
    """Filtre les fausses dates : une mensualité de 25 000 FCFA est aussi un n° de série Excel."""
    return date is not None and ANNEE_ECOLE_MIN <= date.year <= ANNEE_ECOLE_MAX


def numero_mois(valeur: object) -> int | None:
    """En-tête de colonne de paiement : nom de mois ou date.

    Un nombre nu n'est jamais un mois : dans « bureautique2evague », la case
    « 7 » de la ligne d'en-tête est un compteur de lignes, et le lire comme
    juillet transforme chaque numéro d'élève en paiement de 1 à 14 FCFA.
    """
    if isinstance(valeur, (dt.datetime, dt.date)):
        return valeur.month
    return MOIS_SANS_ACCENT.get(sans_accents(valeur).lower())


def colonne_excel(index: int) -> str:
    lettres = ''
    index += 1
    while index:
        index, reste = divmod(index - 1, 26)
        lettres = chr(65 + reste) + lettres
    return lettres


def ligne_utile(ligne) -> bool:
    return any(normaliser_texte(c) != '' for c in ligne)


def lire_lignes(feuille) -> list[list]:
    """Lignes brutes, vidées de leurs lignes finales vides et tronquées à la dernière colonne remplie."""
    lignes = [list(ligne) for ligne in feuille.iter_rows(values_only=True)]
    while lignes and not ligne_utile(lignes[-1]):
        lignes.pop()
    if not lignes:
        return []
    derniere = max(
        (i for ligne in lignes for i, valeur in enumerate(ligne)
         if normaliser_texte(valeur) != ''), default=0
    )
    return [ligne[:derniere + 1] for ligne in lignes]


# ---------------------------------------------------------------------------
# Onglets de suivi par formation
# ---------------------------------------------------------------------------
ROLE_PAR_EN_TETE = (
    ('date', re.compile(r"date\s+d['’.]?\s*inscri", re.I)),
    ('frais_inscription', re.compile(r"frais\s+d['’.]?\s*inscri", re.I)),
    ('frais_mensuels', re.compile(r'frais\s+mensuel', re.I)),
    ('commentaire', re.compile(r'commentai', re.I)),
    ('option', re.compile(r'^(option|formation)$', re.I)),
    ('duree', re.compile(r'dur[ée]e', re.I)),
    ('cout', re.compile(r'co[ûu]t', re.I)),
    ('training', re.compile(r'training', re.I)),
    ('nom', re.compile(r'(nom|prenoms?)', re.I)),
)


def role_de_en_tete(valeur: object) -> str | None:
    for role, motif in ROLE_PAR_EN_TETE:
        if motif.search(normaliser_texte(valeur)):
            return role
    return None


@dataclass
class Bloc:
    """Un tableau d'inscriptions repéré dans un onglet.

    Certains onglets empilent deux tableaux côte à côte (ancienne et nouvelle
    promotion) : ``Anglais``, ``anglaisvague2``, ``Bureautique``.
    """
    onglet: str
    debut_colonne: int
    fin_colonne: int
    premiere_ligne: int
    lignes_donnees: list = field(default_factory=list)
    colonnes: dict = field(default_factory=dict)
    mois: dict = field(default_factory=dict)

    @property
    def libelle(self) -> str:
        return f'{self.onglet} !{colonne_excel(self.debut_colonne)}'


def _en_tete_fusionne(lignes: list[list], index: int) -> tuple[list, int]:
    """Fusionne l'en-tête avec la ligne suivante quand les mois se lisent sur deux lignes."""
    if index + 1 >= len(lignes):
        return list(lignes[index]), 1
    suivante = lignes[index + 1]
    if any(role_de_en_tete(v) == 'nom' for v in suivante):
        return list(lignes[index]), 1
    fusion = list(lignes[index])
    while len(fusion) < len(suivante):
        fusion.append(None)
    remplie = False
    for colonne, valeur in enumerate(suivante):
        if normaliser_texte(valeur) != '' and normaliser_texte(fusion[colonne]) == '':
            fusion[colonne] = valeur
            remplie = True
    return fusion, (2 if remplie else 1)


def decouper_blocs(onglet: str, lignes: list[list]) -> list[Bloc]:
    if not lignes:
        return []
    ligne_en_tete = None
    for index in range(min(4, len(lignes))):
        en_tete_brut = lignes[index]
        colonnes_nom = [c for c, v in enumerate(en_tete_brut) if role_de_en_tete(v) == 'nom']
        payees = [c for c, v in enumerate(en_tete_brut)
                  if role_de_en_tete(v) in ('date', 'frais_inscription', 'frais_mensuels')]
        if colonnes_nom and payees:
            ligne_en_tete = index
            break
    if ligne_en_tete is None:
        return []

    en_tete, nb_lignes = _en_tete_fusionne(lignes, ligne_en_tete)
    debuts = [c for c, v in enumerate(en_tete) if role_de_en_tete(v) == 'nom']
    blocs: list[Bloc] = []
    for position, colonne_nom in enumerate(debuts):
        debut = 0 if position == 0 else blocs[-1].fin_colonne
        fin = debuts[position + 1] if position + 1 < len(debuts) else len(en_tete)
        bloc = Bloc(onglet=onglet, debut_colonne=debut, fin_colonne=fin,
                    premiere_ligne=ligne_en_tete + nb_lignes)
        for colonne in range(debut, fin):
            valeur = en_tete[colonne] if colonne < len(en_tete) else None
            role = role_de_en_tete(valeur)
            if role and role not in bloc.colonnes:
                bloc.colonnes[role] = colonne
            else:
                numero = numero_mois(valeur)
                if numero:
                    bloc.mois[colonne] = (numero, normaliser_texte(valeur))
        bloc.lignes_donnees = lignes[bloc.premiere_ligne:]
        blocs.append(bloc)
    return blocs


VALEURS_NON_NOM = {
    'entree', 'sortie', 'ok', 'oui', 'non', 'total', 'totaux', 'neant',
    'formation terminee', 'inscription', 'semestre', 'colonne',
}


def ressemble_a_un_nom(valeur: object) -> bool:
    brut = normaliser_texte(valeur)
    if len(brut) < 3 or parse_date(valeur)[0] is not None:
        return False
    propre = sans_accents(brut).lower()
    if propre in VALEURS_NON_NOM or propre in MOIS_SANS_ACCENT:
        return False
    if UNITE_MONETAIRE.search(brut) or MARQUE_SECHE.match(brut.replace(' ', '')):
        return False
    return bool(re.fullmatch(r"[A-Za-zÀ-ÿ'()\-., ]+", brut))


@dataclass
class LigneInscription:
    onglet: str
    bloc: str
    ligne: int
    nom: str
    cle: str
    date_inscription: dt.date | None
    date_statut: str
    frais_inscription: int | None
    frais_statut: str
    mensuel_prevu: int | None
    mois: list
    commentaire: str
    annees: list
    anomalies: list


def _cellule(ligne: list, colonne):
    return ligne[colonne] if colonne is not None and colonne < len(ligne) else None


def extraire_ligne(bloc: Bloc, ligne: list, numero_ligne: int) -> LigneInscription | None:
    """Transforme une ligne d'onglet en inscription, en signalant les décalages de saisie."""
    anomalies: list[tuple[str, str]] = []
    colonne_nom = bloc.colonnes.get('nom')
    if colonne_nom is None:
        return None
    nom = normaliser_texte(_cellule(ligne, colonne_nom))

    # « Sécretariat bilingue » : le nom est éclaté de part et d'autre de la colonne repérée.
    for voisine in (colonne_nom - 1, colonne_nom + 1):
        if voisine < bloc.debut_colonne or voisine >= bloc.fin_colonne:
            continue
        valeur = normaliser_texte(_cellule(ligne, voisine))
        if valeur and ressemble_a_un_nom(valeur):
            nom = f'{valeur} {nom}'.strip() if voisine < colonne_nom else f'{nom} {valeur}'.strip()
            anomalies.append((
                'nom_eclate',
                f'colonnes {colonne_excel(voisine)} et {colonne_excel(colonne_nom)}',
            ))

    date, statut_date = parse_date(_cellule(ligne, bloc.colonnes.get('date')))
    if date is not None and not date_verossemblable(date):
        anomalies.append(('date_hors_plage', f'{date:%d/%m/%Y} (statut {statut_date})'))
        date, statut_date = None, 'hors_plage'
    if date is None:
        for colonne in range(bloc.debut_colonne, bloc.fin_colonne):
            if colonne == colonne_nom or colonne in bloc.mois or colonne == bloc.colonnes.get('date'):
                continue
            candidate, statut = parse_date(_cellule(ligne, colonne))
            # Seules les cellules réellement formatées en date sont crédibles :
            # un montant de 25 000 est aussi un numéro de série Excel.
            if candidate and statut in ('ok', 'texte') and date_verossemblable(candidate):
                date, statut_date = candidate, statut
                anomalies.append(('date_decalee', f'colonne {colonne_excel(colonne)}'))
                break
        else:
            anomalies.append(('sans_date_inscription', ''))
    elif statut_date == 'serie':
        anomalies.append(('date_reformatee',
                          f'« {normaliser_texte(_cellule(ligne, bloc.colonnes.get("date")))} » lu en date'))

    frais, statut_frais, brut_frais = parse_montant(_cellule(ligne, bloc.colonnes.get('frais_inscription')))
    mensuel, statut_mensuel, brut_mensuel = parse_montant(_cellule(ligne, bloc.colonnes.get('frais_mensuels')))

    mois = []
    annees = set()
    for colonne in sorted(bloc.mois):
        numero, libelle = bloc.mois[colonne]
        montant, statut, brut = parse_montant(_cellule(ligne, colonne))
        if montant and montant < SEUIL_PAIEMENT_MIN:
            anomalies.append(('montant_improbable',
                              f'{colonne_excel(colonne)} « {libelle} » = « {brut} »'))
            montant = None
        mois.append((numero, libelle, montant, statut, brut))
        if montant:
            annees.add(annee_du_mois(numero, date))
        if statut not in ('vide', 'ok', 'nul', 'ok_texte'):
            anomalies.append(('montant_doutueux', f'{colonne_excel(colonne)} « {libelle} » = « {brut} »'))

    commentaire = normaliser_texte(_cellule(ligne, bloc.colonnes.get('commentaire')))
    option = normaliser_texte(_cellule(ligne, bloc.colonnes.get('option')))
    if option:
        commentaire = f'{commentaire} | {option}'.strip(' |')

    if not nom or not re.search(r'[A-Za-zÀ-ÿ]{2}', nom):
        return None
    if statut_frais not in ('vide', 'ok', 'nul', 'ok_texte'):
        anomalies.append(('frais_inscription_douteux', f'« {brut_frais} »'))
    if statut_mensuel not in ('vide', 'ok', 'nul', 'ok_texte'):
        anomalies.append(('frais_mensuel_douteux', f'« {brut_mensuel} »'))

    return LigneInscription(
        onglet=bloc.onglet, bloc=bloc.libelle, ligne=numero_ligne, nom=nom,
        cle=cle_personne(f'{nom} {option}' if option else nom),
        date_inscription=date, date_statut=statut_date,
        frais_inscription=frais, frais_statut=statut_frais,
        mensuel_prevu=mensuel, mois=mois, commentaire=commentaire,
        annees=sorted(a for a in annees if a), anomalies=anomalies,
    )


def annee_du_mois(numero_mois_: int, reference: dt.date | None) -> int | None:
    """Les en-têtes ne portent que le nom du mois : l'année est déduite de la date d'inscription.

    Un mois antérieur au mois d'inscription appartient à l'année suivante (promotion
    ouverte en octobre avec une colonne « janvier »).
    """
    if reference is None:
        return None
    annee = reference.year
    if numero_mois_ < reference.month:
        annee += 1
    return annee


# ---------------------------------------------------------------------------
# Journal de caisse
# ---------------------------------------------------------------------------
@dataclass
class EcritureCaisse:
    classeur: str
    onglet: str
    ligne: int
    date: dt.date | None
    sens: str
    libelle: str
    intitule: str
    mois_paye: str
    annee: str
    montant: int | None
    statut_montant: str
    personne: str
    formation: str
    commentaire: str

    @property
    def empreinte(self) -> tuple:
        return (
            self.date.isoformat() if self.date else '', self.sens.lower(),
            self.montant or 0, cle_personne(self.personne), cle_personne(self.formation),
            self.mois_paye.lower(),
        )


JOURNAL_COLONNES = {
    'date': re.compile(r'^date$', re.I),
    'sens': re.compile(r'entr[ée]e\s*/?\s*sortie?|op[ée]ration', re.I),
    'libelle': re.compile(r'^libell[ée]$|^motifs?$|^activit[ée]', re.I),
    'intitule': re.compile(r'intitul[ée]', re.I),
    'mois': re.compile(r'mois\s+pay[ée]|^mois$', re.I),
    'annee': re.compile(r"ann[ée]e", re.I),
    'montant': re.compile(r'montant|^honoraires$', re.I),
    'commentaire': re.compile(r'commentai|remarque', re.I),
    'personne': re.compile(r'nom.*pr[ée]nom|pr[ée]nom.*nom|noms?\s*et', re.I),
    'formation': re.compile(r'^formation$|^option$', re.I),
}


def indexer_en_tete(ligne: list) -> dict:
    index = {}
    for colonne, valeur in enumerate(ligne):
        brut = normaliser_texte(valeur)
        if not brut:
            continue
        for role, motif in JOURNAL_COLONNES.items():
            if role not in index and motif.search(brut):
                index[role] = colonne
                break
    return index


def lire_journal(classeur_nom: str, lignes: list[list], onglet: str = '') -> tuple[list, int]:
    """Lit un tableau plat dont l'en-tête est cherché dans les cinq premières lignes."""
    for index, ligne in enumerate(lignes[:8]):
        index_colonnes = indexer_en_tete(ligne)
        if 'montant' in index_colonnes and ('date' in index_colonnes or 'sens' in index_colonnes):
            break
    else:
        return [], 0
    ecritures = []
    for numero, ligne in enumerate(lignes[index + 1:], start=index + 2):
        if not ligne_utile(ligne):
            continue
        def valeur(role):
            colonne = index_colonnes.get(role)
            return normaliser_texte(ligne[colonne]) if colonne is not None and colonne < len(ligne) else ''
        montant, statut, _ = parse_montant(ligne[index_colonnes['montant']]) \
            if index_colonnes.get('montant') is not None and index_colonnes['montant'] < len(ligne) else (None, 'vide', '')
        date, _ = parse_date(ligne[index_colonnes['date']]) \
            if index_colonnes.get('date') is not None and index_colonnes['date'] < len(ligne) else (None, 'vide')
        ecritures.append(EcritureCaisse(
            classeur=classeur_nom, onglet=onglet, ligne=numero, date=date,
            sens=valeur('sens'), libelle=valeur('libelle'), intitule=valeur('intitule'),
            mois_paye=valeur('mois'), annee=valeur('annee'), montant=montant,
            statut_montant=statut, personne=valeur('personne'),
            formation=valeur('formation'), commentaire=valeur('commentaire'),
        ))
    return ecritures, index + 1
