"""Séries numériques des graphiques de tableau de bord — les chiffres, jamais le rendu.

Chaque fonction renvoie un dictionnaire que le gabarit passe à ``json_script`` et que
``static/js/graphiques.js`` transforme en Chart.js. Les libellés sont résolus ici, à la
langue de la requête : le graphique anglais porte des étiquettes anglaises sans que
JavaScript ait à traduire quoi que ce soit.

Deux règles de prudence, alignées sur ``core.utils.outstanding_receivables`` :

- un trop-perçu sur un dossier ne réduit pas la dette du voisin ;
- une écriture en attente ou annulée n'entre dans aucun total.
"""
from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Count, IntegerField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from .models import Attendance, CashTransaction, Enrollment, Payment

INSCRITS = (Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED)
PAIEMENTS_ENCAISSES = (Payment.Status.COMPLETED,)
ECRITURES_VALIDEES = (CashTransaction.Status.VALIDATED,)
DEPLACEMENTS = (CashTransaction.Type.IN, CashTransaction.Type.OUT)


def premiers_du_mois(nombre: int) -> list[date]:
    """Le premier de chaque mois, du plus ancien au plus récent, mois courant inclus."""
    reference = timezone.localdate().replace(day=1)
    mois = []
    for _ in range(nombre):
        mois.append(reference)
        reference = (reference - timedelta(days=1)).replace(day=1)
    return mois[::-1]


def libelle_mois(premier: date) -> str:
    """« jan. 2026 » en français, « Jan. 2026 » en anglais : la date suit la langue.

    ``N`` est préféré à ``b`` : sous babel, « b » tronque à trois lettres et rend
    « jui » pour juin comme « jul » pour juillet, deux mois difficiles à distinguer.
    """
    return date_format(premier, 'N Y')


def encaissements_par_mois(nombre: int = 6) -> dict:
    """Entrées et sorties de caisse validées, mois par mois."""
    mois = premiers_du_mois(nombre)
    montants: dict = {}
    lignes = (
        CashTransaction.objects
        .filter(status__in=ECRITURES_VALIDEES, tx_type__in=DEPLACEMENTS,
                occurred_at__date__gte=mois[0])
        .annotate(mois=TruncMonth('occurred_at'))
        .values('mois', 'tx_type')
        .annotate(total=Sum('amount'))
    )
    for ligne in lignes:
        # TruncMonth sur un DateTimeField rend un datetime : seul le jour compte pour appairer.
        jour = ligne['mois'].date() if hasattr(ligne['mois'], 'date') else ligne['mois']
        montants.setdefault(jour, {})[ligne['tx_type']] = ligne['total'] or 0

    entrees = [montants.get(m, {}).get(CashTransaction.Type.IN, 0) for m in mois]
    sorties = [-montants.get(m, {}).get(CashTransaction.Type.OUT, 0) for m in mois]
    soldes = [e + s for e, s in zip(entrees, sorties)]
    return {
        'id': 'encaissements',
        'type': 'bar',
        'titre': _('Encaissements par mois'),
        'note': _('Écritures validées, sur %(n)s mois.') % {'n': nombre},
        'unite': 'fcfa',
        'labels': [libelle_mois(m) for m in mois],
        'series': [
            {'nom': _('Entrées'), 'valeurs': entrees, 'couleur': 'green'},
            {'nom': _('Sorties'), 'valeurs': sorties, 'couleur': 'rose'},
            {'nom': _('Solde'), 'valeurs': soldes, 'couleur': 'indigo', 'type': 'line'},
        ],
    }


def eleves_par_formation(limite: int = 8) -> dict:
    """Effectif inscrit par formation, les plus petits regroupés sous « Autres »."""
    lignes = (
        Enrollment.objects.filter(status__in=INSCRITS)
        .values('session__course__title')
        .annotate(effectif=Count('id'))
        .order_by('-effectif', 'session__course__title')
    )
    rangee = [(l['session__course__title'], l['effectif']) for l in lignes
              if l['session__course__title']]
    tete, queue = rangee[:limite], rangee[limite:]
    libelles = [t for t, _ in tete]
    effectifs = [e for _, e in tete]
    if queue:
        libelles.append(_('Autres (%(n)s formations)') % {'n': len(queue)})
        effectifs.append(sum(e for _, e in queue))
    return {
        'id': 'effectifs',
        'type': 'bar',
        'titre': _('Élèves par formation'),
        'note': _('Inscriptions actives et terminées.'),
        'unite': 'personnes',
        'labels': libelles,
        'series': [{'nom': _('Élèves'), 'valeurs': effectifs, 'couleur': 'indigo'}],
        'horizontal': True,
    }


def restes_par_formation(limite: int = 8) -> dict:
    """Ce qui reste à réclamer, formation par formation.

    Le reste se calcule dossier par dossier avant regroupement : un solde créditeur
    sur une fiche n'efface pas la dette de la voisine.
    """
    paye = (Payment.objects.filter(enrollment=OuterRef('pk'), status__in=PAIEMENTS_ENCAISSES)
            .values('enrollment').annotate(total=Sum('amount')).values('total'))
    dossiers = (
        Enrollment.objects.filter(status=Enrollment.Status.ACTIVE)
        .select_related('session__course')
        .annotate(paye=Coalesce(Subquery(paye, output_field=IntegerField()), Value(0)))
    )
    par_formation: dict = {}
    for dossier in dossiers:
        reste = max(dossier.net_amount - (dossier.paye or 0), 0)
        if not reste:
            continue
        titre = dossier.session.course.title if dossier.session_id else _('Sans groupe')
        par_formation[titre] = par_formation.get(titre, 0) + reste

    rangee = sorted(par_formation.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        'id': 'restes',
        'type': 'bar',
        'titre': _('Restes à recouvrer'),
        'note': _('Tarif dû moins sommes encaissées, dossier par dossier.'),
        'unite': 'fcfa',
        'labels': [t for t, _ in rangee[:limite]],
        'series': [{'nom': _('Reste dû'), 'valeurs': [m for _, m in rangee[:limite]],
                    'couleur': 'amber'}],
        'horizontal': True,
        'total': sum(m for _, m in rangee),
    }


def assiduite_par_mois(nombre: int = 6) -> dict:
    """Présences, retards et absences, mois par mois, avec le taux de présence en courbe."""
    mois = premiers_du_mois(nombre)
    lignes = (
        Attendance.objects.filter(date__gte=mois[0])
        .annotate(mois=TruncMonth('date'))
        .values('mois', 'status')
        .annotate(total=Count('id'))
    )
    cases: dict = {m: {} for m in mois}
    for ligne in lignes:
        cases.setdefault(ligne['mois'], {})[ligne['status']] = ligne['total']

    def colonne(statut):
        return [cases.get(m, {}).get(statut, 0) for m in mois]

    presents = colonne(Attendance.Status.PRESENT)
    retards = colonne(Attendance.Status.LATE)
    absents = colonne(Attendance.Status.ABSENT)
    excuses = colonne(Attendance.Status.EXCUSED)
    taux = []
    for p, r, a, e in zip(presents, retards, absents, excuses):
        reels, total = p + r, p + r + a + e
        taux.append(round(100 * reels / total, 1) if total else 0)
    return {
        'id': 'assiduite',
        'type': 'bar',
        'titre': _('Assiduité par mois'),
        'note': _('Taux = présents et retards face aux feuilles d’appel remplies.'),
        'unite': 'personnes',
        'labels': [libelle_mois(m) for m in mois],
        'series': [
            {'nom': _('Présents'), 'valeurs': presents, 'couleur': 'green'},
            {'nom': _('Retards'), 'valeurs': retards, 'couleur': 'amber'},
            {'nom': _('Absents'), 'valeurs': absents, 'couleur': 'rose'},
            {'nom': _('Taux de présence (%)'), 'valeurs': taux, 'couleur': 'indigo',
             'type': 'line', 'axe': 'secondaire'},
        ],
    }


def pour_direction() -> list:
    return [encaissements_par_mois(), eleves_par_formation(),
            restes_par_formation(), assiduite_par_mois()]


def pour_comptabilite() -> list:
    return [encaissements_par_mois(), restes_par_formation()]


def pour_pedagogie() -> list:
    return [assiduite_par_mois(), eleves_par_formation()]
