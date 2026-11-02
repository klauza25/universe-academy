"""Outils d'extraction et d'audit des chaînes traduisibles.

Le poste de développement n'a pas les binaires gettext (xgettext/msgfmt), donc
l'extraction est faite ici : `extraire_gabarit` et `extraire_python` renvoient
les msgid réellement balisés, et `litteraux_francophone` signale le français qui
n'a pas encore été balisé. `core/management/commands/` s'en sert pour compiler
les catalogues et pour refuser une livraison incomplète.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from django.conf import settings

BASE_DIR = Path(settings.BASE_DIR)

# Motif des msgid {% trans "…" %} / {% translate '…' %}, avec l'optionnel
# « trimmed » et la forme « as variable ».
TRANS_RE = re.compile(
    r"""{%\s*(?:trans|translate)\s+(?:'(?P<single>[^'\\]*)'|"(?P<double>[^"\\]*)")"""
    r"""\s*(?:as\s+\w+)?\s*%}""",
    re.VERBOSE,
)
BLOCKTRANS_RE = re.compile(
    r"""{%\s*blocktrans(?P<options>[^%]*)%}\s*(?P<body>.*?)\s*{%\s*endblocktrans\s*%}""",
    re.DOTALL,
)
VARIABLE_RE = re.compile(r"{{\s*(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\s*}}")
GETTEXT_RE = re.compile(
    r"""(?:\b_\b|gettext|gettext_lazy|ngettext|ngettext_lazy)\s*\(\s*"""
    r"""(?P<quote>['"])(?P<text>(?:(?!\1).)*)(?P=quote)"""
)
DJANGO_COMMENT_RE = re.compile(r"{#.*?#}", re.DOTALL)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
ATTRIBUTE_RE = re.compile(
    r"""(?P<name>placeholder|title|aria-label|alt|content|label)\s*=\s*"""
    r"""(?P<quote>["'])(?P<value>(?:(?!\1).)*)(?P=quote)""",
    re.DOTALL,
)
TEXT_NODE_RE = re.compile(r">(?P<text>[^<>]+)<")
PYTHON_STRING_RE = re.compile(
    r"""(?P<quote>['"])(?P<text>(?:(?!\1)[^\n]|\\.)+)(?P=quote)"""
)

# Le français sans accent est fréquent (« Accueil », « Caisse », « Valider ») :
# les seuls caractères accentués ne suffisent pas à détecter une chaîne non
# balisée. Cette liste sert de garde, les faux positifs sont acceptés tant
# qu'ils sont revus à la main par la zone en cours.
MOTS_FR = {
    'a', 'au', 'aux', 'avec', 'bonjour', 'cadre', 'caisse', 'charger', 'compte',
    'comptes', 'consulter', 'contre', 'cours', 'creer', 'créer', 'dans', 'de',
    'declaration', 'delai', 'depuis', 'des', 'designation', 'desormais', 'detail',
    'developpeur', 'direction', 'données', 'donnees', 'dont', 'dos', 'dossier',
    'dossiers', 'douance', 'du', 'ecole', 'effectue', 'envoi', 'envoyer', 'est',
    'et', 'etat', 'etape', 'feuille', 'file', 'fois', 'font', 'hors', 'ici', 'il',
    'inscription', 'inscriptions', 'jamais', 'le', 'les', 'lui', 'maintenant',
    'mais', 'mes', 'mise', 'mise', 'mon', 'motif', 'n\'est', 'ne', 'non', 'notre',
    'nouveau', 'nouvelle', 'octobre', 'on', 'ou', 'où', 'par', 'parmi', 'paye',
    'payees', 'payment', 'personne', 'peu', 'planned', 'plus', 'pour', 'pourquoi',
    'pres', 'present', 'presentes', 'pret', 'puis', 'quand', 'qui', 'recu',
    'recus', 'refus', 'refuse', 'reste', 'retour', 'sa', 'sans', 'ses', 'se',
    'secrétariat', 'secretariat', 'sedans', 'son', 'sont', 'sur', 'tableau',
    'tes', 'total', 'toujours', 'tres', 'trop', 'tu', 'un', 'une', 'vaille',
    'valeur', 'valider', 'vendredi', 'via', 'voir', 'voici', 'voila', 'votre',
    'vous', 'vos', 'en', 'est', 'fait', 'faire', 'date', 'nom', 'prenom',
    'email', 'telephone', 'montant', 'recherche', 'rechercher', 'ajouter',
    'modifier', 'supprimer', 'annuler', 'enregistrer', 'suivant', 'precedent',
    'accueil', 'etudiant', 'etudiantes', 'etudiants', 'formation', 'formations',
    'seance', 'seances', 'module', 'modules', 'lecon', 'lecons', 'ressource',
    'ressources', 'presence', 'presences', 'absent', 'absente', 'valide',
    'encaisser', 'encaisse', 'encaissee', 'recu', 'impaye', 'impayees', 'solde',
    'remise', 'tarif', 'budget', 'depense', 'depenses', 'recette', 'recettes',
    'journal', 'cloture', 'compte', 'libelle', 'statut', 'filtre', 'tri',
    'total', 'detail', 'aperçu', 'apercu', 'envoyer', 'telecharger', 'imprimer',
    'sombre', 'clair', 'automatique', 'selectionner', 'choisir', 'aucun',
    'aucune', 'tous', 'tout', 'bienvenue', 'navigation', 'profil',
    'deconnexion', 'langue', 'theme',
}

ACCENTS = set('àâäéèêëîïôöùûüçœæñÀÂÄÉÈÊËÎÏÔÖÙÛÜÇÆÑ')

# Les identifiants Django (noms de champs, clés de queryset, routes, chemins)
# ressemblent à du français sans en être : « student_payment », « date_from »,
# « core:dashboard:payment-create ». Une chaîne entièrement minuscule, sans
# espace ni accent, et découpée par des séparateurs de programme n'est jamais
# destinée à l'écran — on l'écarte pour que le compteur reste crédible. Les
# constantes en MAJUSCULES soulignées (codes d'audit, rôles) n'y vont pas non
# plus, mais « Non » ou « Référence » restent comptés.
FORME_PROGRAMMATIQUE = re.compile(r'\A[-+]?[a-z0-9]+(?:[_./:+-][a-z0-9]+)*\Z')
FORME_CONSTANTE = re.compile(r'\A[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*\Z')


def est_programmatique(texte: str) -> bool:
    if ' ' in texte:
        return False
    return bool(FORME_PROGRAMMATIQUE.match(texte) or FORME_CONSTANTE.match(texte))


# Chaîne française assumée non visible pour un usager (ligne de log, message
# interne, contenu d'un mail technique) : le portique l'ignore quand la ligne
# porte la marque, qui doit être accompagnée du motif.
EXEMPTION_RE = re.compile(r'#\s*i18n-exempt\s*:.+')


def sortie_utf8() -> None:
    """Windows rend la console en cp1252 : les accents et « ← » plantent l'affichage."""
    for flux in (sys.stdout, sys.stderr):
        if hasattr(flux, 'reconfigure'):
            flux.reconfigure(encoding='utf-8', errors='replace')


def gabarits() -> list[Path]:
    return sorted((BASE_DIR / 'templates').rglob('*.html'))


def sources_python() -> list[Path]:
    core = BASE_DIR / 'core'
    exclus = {'tests', 'migrations', '__pycache__'}
    fichiers = [core / 'models.py', core / 'forms.py', core / 'decorators.py',
                core / 'utils.py', core / 'context_processors.py', core / 'admin.py',
                core / 'graphiques.py']
    fichiers += sorted(core.glob('views*.py'))
    return sorted({f for f in fichiers if f.exists() and not f.is_dir()})


def _msgid_blocktrans(options: str, body: str) -> str:
    """Reproduit la conversion de Django : {{ prenom }} devient %(prenom)s."""
    msgid = VARIABLE_RE.sub(lambda m: '%(' + m.group('name') + ')s', body)
    msgid = re.sub(r'\s+', ' ', msgid).strip()
    return msgid


def extraire(source: str, *, python: bool = False) -> tuple[list[str], str]:
    """Renvoie (msgid balisés, source débarrassée de ces msgid)."""
    msgids: list[str] = []
    nettoye = source

    if python:
        for match in GETTEXT_RE.finditer(source):
            msgids.append(match.group('text'))
        nettoye = GETTEXT_RE.sub(
            lambda m: m.group(0).replace(m.group('text'), ''), source)
    else:
        for match in BLOCKTRANS_RE.finditer(source):
            msgids.append(_msgid_blocktrans(match.group('options'), match.group('body')))
        for match in TRANS_RE.finditer(source):
            msgids.append(match.group('single') or match.group('double'))
        nettoye = BLOCKTRANS_RE.sub(' ', nettoye)
        nettoye = TRANS_RE.sub(' ', nettoye)
        nettoye = DJANGO_COMMENT_RE.sub(' ', nettoye)
        nettoye = HTML_COMMENT_RE.sub(' ', nettoye)

    return msgids, nettoye


def est_francophone(texte: str) -> bool:
    if any(c in ACCENTS for c in texte):
        return True
    mots = set(re.split(r"[^0-9A-Za-z'À-ÿ]+", texte.lower()))
    return bool(mots & MOTS_FR)


def litteraux_francophone(source: str, *, python: bool = False) -> list[tuple[int, str]]:
    """Littéraux visiblement français qui ne sont pas balisés."""
    _, nettoye = extraire(source, python=python)
    trouves: list[tuple[int, str]] = []

    if python:
        for ligne_no, ligne in enumerate(nettoye.splitlines(), start=1):
            strip = ligne.strip()
            if strip.startswith('#') or strip.startswith('"""') or strip.startswith("'''"):
                continue
            if 'verbose_name' in strip and not GETTEXT_RE.search(strip):
                continue
            if EXEMPTION_RE.search(ligne):
                continue
            for match in PYTHON_STRING_RE.finditer(ligne):
                texte = match.group('text')
                if len(texte) > 1 and not est_programmatique(texte) and est_francophone(texte):
                    trouves.append((ligne_no, texte[:70]))
        return trouves

    for match in ATTRIBUTE_RE.finditer(nettoye):
        valeur = match.group('value')
        if '{{' in valeur or '{%' in valeur:
            continue
        if est_francophone(valeur):
            ligne_no = nettoye[:match.start()].count('\n') + 1
            trouves.append((ligne_no, f'{match.group("name")}="{valeur[:60]}"'))

    for match in TEXT_NODE_RE.finditer(nettoye):
        texte = re.sub(r'\s+', ' ', match.group('text')).strip()
        if not texte or est_balise(texte):
            continue
        ligne_no = nettoye[:match.start()].count('\n') + 1
        trouves.append((ligne_no, texte[:70]))
    return trouves


def est_balise(texte: str) -> bool:
    """Vrai si le nœud de texte ne contient que des balises Django/variables."""
    sans_tags = re.sub(r'{%.*?%}', '', texte, flags=re.DOTALL)
    sans_tags = re.sub(r'{{.*?}}', '', sans_tags).strip()
    if not sans_tags:
        return True
    return not est_francophone(sans_tags)
