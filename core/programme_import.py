"""Ce que l'import des classeurs doit produire, déclaré au seul endroit.

Les deux commandes — ``analyser_donnees`` (rapport) et ``importer_formations`` (vague 1) —
lisent ces tables : le rapport ne peut donc pas promettre une formation que l'import ne connaît pas.
"""
from __future__ import annotations

from collections import Counter

DUREE_MOIS = 9
FRAIS_INSCRIPTION = 10000

# Bande retenue par la direction : toute mensualité lue ou déclarée y est ramenée.
BORNE_MENSUELLE = (20000, 25000)

# Marque posée dans la description des lignes créées par l'import : elle permet de
# les reprendre sans jamais toucher une formation écrite à la main avant elles.
MARQUE = "d'après les classeurs"

# clé de l'intitulé observé -> (titre au catalogue, domaine, mensualité de repli si le classeur n'en dit rien)
FORMATIONS = {
    'anglais': ('Anglais', 'Langues', 25000),
    'italien': ('Italien', 'Langues', 20000),
    'chinois': ('Chinois', 'Langues', 25000),
    'bureautique': ('Bureautique', 'Informatique', 20000),
    'infographie': ('Infographie', 'Informatique', 20000),
    'a administratif': ('Assistanat administratif', 'Assistanat', 25000),
    'a comptable': ('Assistanat comptable', 'Assistanat', 25000),
    'a humaines ressources': ('Assistanat ressources humaines', 'Assistanat', 25000),
    'assistanat': ('Assistanat', 'Assistanat', 25000),
    'bilingue secretariat': ('Secrétariat bilingue', 'Assistanat', 25000),
    'caisse de gestion': ('Gestion de caisse', 'Gestion', 25000),
    'fiscalite': ('Fiscalité', 'Gestion', 25000),
    'des entreprises fiscalite': ('Fiscalité des entreprises', 'Gestion', 25000),
}

# « RH » est le même enseignement que « A. Ressources Humaines », écrit plus court.
FUSIONS = {'rh': 'a humaines ressources'}

# Un onglet de promotion n'est pas une formation : il renseigne la mensualité de sa parente
# et devient un groupe (CourseSession) à la vague des inscriptions.
PROMOTIONS = {
    'anglaisvague2': 'anglais',
    'bureautique2evague': 'bureautique',
    'italien oct2026': 'italien',
    'anciens etudiants': None,
}

# Registres et hors-formation : rien à créer, rien à rattacher.
HORS_CATALOGUE = {'anciens etudiants'}


def mensuel_observee(observees: dict, cle: str, repli: int) -> int:
    """La mensualité la plus souvent encaissée pour cette formation, promotions et alias inclus.

    Une valeur entrevue une seule fois est un à-compte ou une erreur de saisie : elle ne
    fait pas tarif. Sans montant répété deux fois, on reste sur le repli déclaré.
    Dans les deux cas, la bande voulue par la direction borne ce que le classeur avance.
    """
    compte: Counter = Counter(observees[cle]['mensualite']) if cle in observees else Counter()
    for promotion, parente in PROMOTIONS.items():
        if parente == cle and promotion in observees:
            compte.update(observees[promotion]['mensualite'])
    for alias, cible in FUSIONS.items():
        if cible == cle and alias in observees:
            compte.update(observees[alias]['mensualite'])
    repetees = [v for v, n in compte.items() if v and n >= 2]
    choix = max(repetees, key=lambda v: (compte[v], v)) if repetees else repli
    return min(max(choix, BORNE_MENSUELLE[0]), BORNE_MENSUELLE[1])
