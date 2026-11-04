"""Dashboard comptabilité : journal, opérations, caisses et clôtures."""
import csv
from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction as db_transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from . import programme_import as programme
from . import caisse
from .decorators import (
    cash_write_required, payment_write_required, role_required,
)
from .forms import (
    CashAccountAdminForm, CashAccountForm, CashAdjustForm, CashClosureForm,
    CashCorrectionForm, CashResetForm, CashTransactionForm,
    CounterEnrollmentForm, PaymentMonthsForm, StudentPaymentForm,
    TransactionCategoryAdminForm, TransactionCategoryForm, mensualite_attendue,
)
from .models import (
    AccountStatus, AuditLog, CashAccount, CashClosure, CashTransaction,
    Enrollment, MOIS, Payment, RoleKey, TransactionCategory, User,
)
from .utils import log_audit

FINANCE_ROLES = ('ASSISTANT_ADMIN', 'DIRECTION')


def account_balance(account, until_date=None):
    """Solde d'une caisse : ouverture + entrées validées − sorties validées."""
    return account.balance_at(until_date)


def accounts_with_balance():
    rows = []
    for account in CashAccount.objects.filter(active=True):
        rows.append({'account': account, 'balance': account_balance(account),
                     'disponible': account.disponible()})
    return rows


# ---------------------------------------------------------------------------
# Journal comptable
# ---------------------------------------------------------------------------

def _journal_queryset(request):
    qs = CashTransaction.objects.select_related(
        'account', 'destination_account', 'category', 'created_by'
    )
    query = (request.GET.get('q') or '').strip()
    tx_type = request.GET.get('type') or ''
    account_id = request.GET.get('account') or ''
    category_id = request.GET.get('category') or ''
    status = request.GET.get('status') or ''
    date_from = request.GET.get('from') or ''
    date_to = request.GET.get('to') or ''

    if query:
        qs = qs.filter(
            Q(reference__icontains=query) |
            Q(label__icontains=query) |
            Q(counterparty__icontains=query) |
            Q(description__icontains=query)
        )
    if tx_type:
        qs = qs.filter(tx_type=tx_type)
    if account_id:
        qs = qs.filter(
            Q(account_id=account_id) | Q(destination_account_id=account_id)
        )
    if category_id:
        qs = qs.filter(category_id=category_id)
    if status:
        qs = qs.filter(status=status)
    if date_from:
        qs = qs.filter(occurred_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(occurred_at__date__lte=date_to)
    return qs.distinct(), {
        'query': query,
        'type_filter': tx_type,
        'account_filter': account_id,
        'category_filter': category_id,
        'status_filter': status,
        'date_from': date_from,
        'date_to': date_to,
    }


@role_required(*FINANCE_ROLES)
def journal(request):
    qs, filters = _journal_queryset(request)

    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = (
            'attachment; filename="journal-comptable.csv"'  # i18n-exempt: en-tête HTTP, nom de fichier
        )
        response.write('\ufeff')
        writer = csv.writer(response, delimiter=';')
        writer.writerow([
            _('Référence'), _('Date effective'), _('Saisie'), _('Type'), _('Catégorie'),
            _('Libellé'), _('Bénéficiaire/Payeur'), _('Entrée'), _('Sortie'),
            _('Moyen'), _('Caisse'), _('Auteur'), _('Statut'),
        ])
        for tx in qs.order_by('-occurred_at')[:5000]:
            writer.writerow([
                tx.reference,
                timezone.localtime(tx.occurred_at).strftime('%d/%m/%Y %H:%M'),
                timezone.localtime(tx.created_at).strftime('%d/%m/%Y %H:%M'),
                tx.get_tx_type_display(),
                tx.category.name if tx.category else '',
                tx.label,
                tx.counterparty,
                tx.amount if tx.tx_type == CashTransaction.Type.IN else '',
                tx.amount if tx.tx_type == CashTransaction.Type.OUT else '',
                tx.get_method_display(),
                tx.account.name,
                tx.created_by.display_label if tx.created_by else '',
                tx.get_status_display(),
            ])
        log_audit(request, 'JOURNAL_EXPORT', 'CashTransaction', 'csv',
                  after={'rows': qs.count()})
        return response

    totals = qs.filter(status=CashTransaction.Status.VALIDATED).aggregate(
        incoming=Sum('amount', filter=Q(tx_type=CashTransaction.Type.IN)),
        outgoing=Sum('amount', filter=Q(tx_type=CashTransaction.Type.OUT)),
    )
    paginator = Paginator(qs.order_by('-occurred_at', '-created_at'), 30)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'dashboard/comptabilite/journal.html', {
        'page': page,
        'totals': totals,
        'accounts': CashAccount.objects.filter(active=True),
        'categories': TransactionCategory.objects.filter(active=True),
        'type_choices': CashTransaction.Type.choices,
        'status_choices': CashTransaction.Status.choices,
        **filters,
    })


@cash_write_required(*FINANCE_ROLES)
def transaction_create(request):
    tx_type = request.GET.get('type') or CashTransaction.Type.IN
    initial = {
        'tx_type': tx_type,
        'occurred_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
    }
    form = CashTransactionForm(initial=initial)
    if request.method == 'POST':
        form = CashTransactionForm(request.POST, request.FILES)
        if form.is_valid():
            donnees = form.cleaned_data
            try:
                tx = caisse.poster(
                    caisse=donnees['account'], montant=donnees['amount'],
                    sens=donnees['tx_type'], libelle=donnees['label'],
                    categorie=donnees['category'],
                    description=donnees['description'],
                    methode=donnees['method'],
                    contrepartie=donnees['counterparty'],
                    piece=donnees['receipt'], note=donnees['note'],
                    statut=donnees['status'], survenu=donnees['occurred_at'],
                    destination=donnees['destination_account'],
                    requete=request,
                )
            except ValidationError as refus:
                # Le service juge avant d'écrire : le refus dit pourquoi, et
                # rien n'a touché la base.
                messages.error(request, refus.messages[0])
            else:
                messages.success(
                    request, _("Opération %(reference)s enregistrée.") % {'reference': tx.reference}
                )
                return redirect('core:dashboard:transaction-detail', tx_id=tx.id)
    return render(request, 'dashboard/comptabilite/transaction_form.html', {
        'form': form,
        'tx_type': tx_type,
        'caisses': [
            {
                'nom': compte.name,
                'disponible': f'{compte.disponible():,}'.replace(',', ' '),
                'devise': compte.currency,
                'epuise': compte.disponible() <= 0,
            }
            for compte in CashAccount.objects.filter(active=True)
        ],
    })


@cash_write_required(*FINANCE_ROLES)
def transaction_detail(request, tx_id):
    tx = get_object_or_404(
        CashTransaction.objects.select_related(
            'account', 'destination_account', 'category', 'created_by'
        ),
        id=tx_id,
    )
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'cancel':
            reason = (request.POST.get('reason') or '').strip()
            annulee = None
            try:
                annulee = caisse.annuler(tx, motif=reason, requete=request)
            except ValidationError as refus:
                # Annuler une recette déjà dépendue creuserait le trou : la
                # régularisation passe par une écriture contraire, pas par
                # l'effacement de l'entrée d'origine. Le service le dit, et
                # rien n'est écrit.
                messages.error(request, refus.messages[0])
            else:
                if annulee is None:
                    messages.info(request, _("Cette opération est déjà annulée."))
                else:
                    messages.success(request, _("Opération annulée et historisée."))
            return redirect('core:dashboard:transaction-detail', tx_id=tx.id)

    return render(request, 'dashboard/comptabilite/transaction_detail.html', {
        'tx': tx,
        'student_payment': getattr(tx, 'student_payment', None),
        'expense': getattr(tx, 'expense_record', None),
        'audit_entries': AuditLog.objects.filter(
            entity_type='CashTransaction', entity_id=str(tx.id),
        ).select_related('actor').order_by('-created_at')[:20],
    })


@cash_write_required(*FINANCE_ROLES)
def transaction_edit(request, tx_id):
    """Corriger une écriture déjà enregistrée, sans la faire disparaître.

    Le montant, la catégorie, le libellé et la date se rectifient ici ; le
    compte et le sens ne se changent pas, ils s'annulent et se ressaisissent.
    La garde de solde rejoue avant l'écriture : une sortie corrigée à la hausse
    ne doit pas passer sous le plancher.
    """
    tx = get_object_or_404(CashTransaction, id=tx_id)
    if tx.status == CashTransaction.Status.CANCELLED:
        messages.info(
            request, _("Une écriture annulée ne se corrige pas : son historique est clos."))
        return redirect('core:dashboard:transaction-detail', tx_id=tx.pk)
    form = CashCorrectionForm(ecriture=tx)
    if request.method == 'POST':
        form = CashCorrectionForm(request.POST, ecriture=tx)
        if form.is_valid():
            donnees = form.cleaned_data
            try:
                caisse.corriger(
                    tx, montant=donnees['montant'], categorie=donnees['categorie'],
                    libelle=donnees['libelle'], survenu=donnees['survenu'],
                    motif=donnees['motif'], requete=request,
                )
            except ValidationError as refus:
                messages.error(request, refus.messages[0])
            else:
                messages.success(
                    request, _("Écriture %(reference)s corrigée.") % {'reference': tx.reference})
                return redirect('core:dashboard:transaction-detail', tx_id=tx.pk)
    return render(request, 'dashboard/comptabilite/transaction_edit.html', {
        'tx': tx,
        'form': form,
        'solde': account_balance(tx.account),
    })


@cash_write_required(*FINANCE_ROLES)
def account_list(request):
    form = CashAccountForm()
    if request.method == 'POST':
        form = CashAccountForm(request.POST)
        if form.is_valid():
            account = form.save()
            log_audit(request, 'CASH_ACCOUNT_CREATE', 'CashAccount',
                      str(account.id),
                      after={'name': account.name,
                             'kind': account.kind})
            messages.success(request, _("Caisse / compte créé."))
            return redirect('core:dashboard:accounts')
    return render(request, 'dashboard/comptabilite/accounts.html', {
        'rows': accounts_with_balance(),
        'form': form,
        'closed_accounts': CashAccount.objects.filter(active=False),
    })


def _etat_compte(compte):
    """Ce que l'audit retient d'un compte : ce qui se règle, pas ce qui se calcule."""
    return {
        'type': compte.kind,
        'devise': compte.currency,
        'description': compte.description,
        'decouvert_autorise': compte.overdraft_limit,
        'etat': compte.status,
        'remplacement': compte.replaced_by.name if compte.replaced_by else None,
    }


@cash_write_required(*FINANCE_ROLES)
def account_update(request, account_id):
    """Administration d'un compte : état, découvert, compte de remplacement, historique.

    Le nom et le solde d'ouverture restent hors d'atteinte une fois la caisse
    engagée : les reprises du journal désignent les comptes par leur nom, et une
    ouverture réécrite après coup ne laisse plus aucun journal fidèle. Ce qui
    doit changer se règle ici, et chaque réglage laisse sa ligne d'audit.
    """
    compte = get_object_or_404(CashAccount, id=account_id)
    form = CashAccountAdminForm(instance=compte, utilisateur=request.user)
    if request.method == 'POST':
        form = CashAccountAdminForm(
            request.POST, instance=compte, utilisateur=request.user)
        if form.is_valid():
            # Le formulaire écrit sur `compte` dès la validation : l'état d'avant
            # s'observe en base, pas sur l'objet en cours de modification.
            avant = _etat_compte(CashAccount.objects.get(pk=compte.pk))
            compte = form.save()
            log_audit(request, 'CASH_ACCOUNT_EDIT', 'CashAccount', str(compte.id),
                      before=avant, after=_etat_compte(compte))
            messages.success(
                request, _("Compte « %(nom)s » mis à jour.") % {'nom': compte.name}
            )
            return redirect('core:dashboard:accounts')
    return render(request, 'dashboard/comptabilite/account_form.html', {
        'compte': compte,
        'form': form,
        'solde': account_balance(compte),
        'disponible': compte.disponible(),
        'brouillons': CashTransaction.objects.filter(
            account=compte, status=CashTransaction.Status.DRAFT).count(),
        'operations': CashTransaction.objects.filter(
            account=compte).order_by('-occurred_at')[:10],
        'historique': AuditLog.objects.filter(
            entity_type='CashAccount', entity_id=str(compte.id),
        ).select_related('actor').order_by('-created_at')[:20],
    })


@cash_write_required(*FINANCE_ROLES)
def account_adjust(request, account_id):
    """Ajustement de solde : une écriture traçée, jamais un chiffre réécrit.

    Le solde d'une caisse se corrige par ce qu'il manque ou ce qu'elle a de
    trop, avec un motif ; l'écriture obtenue porte la nature « Ajustement » et
    passe par la même garde que n'importe quelle sortie.
    """
    compte = get_object_or_404(CashAccount, id=account_id)
    form = CashAdjustForm(compte=compte)
    if request.method == 'POST':
        form = CashAdjustForm(request.POST, compte=compte)
        if form.is_valid():
            avant = account_balance(compte)
            try:
                tx = caisse.ajuster(
                    compte, montant=form.cleaned_data['montant'],
                    sens=form.cleaned_data['sens'],
                    motif=form.cleaned_data['motif'],
                    auteur=request.user, requete=request,
                )
            except ValidationError as refus:
                messages.error(request, refus.messages[0])
            else:
                messages.success(
                    request, _("Ajustement %(reference)s enregistré : solde de %(avant)s à %(apres)s %(devise)s.") % {
                        'reference': tx.reference,
                        'avant': f'{avant:,}'.replace(',', ' '),
                        'apres': f'{tx.account.balance:,}'.replace(',', ' '),
                        'devise': compte.currency,
                    },
                )
                return redirect('core:dashboard:account-update', account_id=compte.pk)
    return render(request, 'dashboard/comptabilite/account_adjust.html', {
        'compte': compte,
        'form': form,
        'solde': account_balance(compte),
        'disponible': compte.disponible(),
        'brouillons': CashTransaction.objects.filter(
            account=compte, status=CashTransaction.Status.DRAFT).count(),
    })


@cash_write_required(*FINANCE_ROLES)
def account_reset(request, account_id):
    """Réinitialisation contrôlée : le solde repart à zéro, l'histoire reste.

    L'aperçu avant coup montre ce qui disparaît — le solde emporté et les
    brouillons qui n'ont pas été rapprochés. Rien n'efface une écriture : la
    remise à zéro est une écriture contraire, datée du jour.
    """
    compte = get_object_or_404(CashAccount, id=account_id)
    form = CashResetForm()
    if request.method == 'POST':
        form = CashResetForm(request.POST)
        if form.is_valid():
            try:
                tx, brouillons = caisse.reinitialiser(
                    compte, motif=form.cleaned_data['motif'],
                    confirme=True, auteur=request.user, requete=request,
                )
            except ValidationError as refus:
                messages.error(request, refus.messages[0])
            else:
                if tx is None:
                    messages.info(
                        request, _("Cette caisse est déjà à zéro : rien à réinitialiser."))
                else:
                    messages.success(
                        request, _("Réinitialisation %(reference)s enregistrée : %(solde)s %(devise)s emportés, %(brouillons)s brouillon(s) non rapproché(s).") % {
                            'reference': tx.reference,
                            'solde': f'{abs(tx.amount):,}'.replace(',', ' '),
                            'devise': compte.currency,
                            'brouillons': brouillons,
                        },
                    )
                return redirect('core:dashboard:account-update', account_id=compte.pk)
    return render(request, 'dashboard/comptabilite/account_reset.html', {
        'compte': compte,
        'form': form,
        'solde': account_balance(compte),
        'brouillons': CashTransaction.objects.filter(
            account=compte, status=CashTransaction.Status.DRAFT).count(),
        'attente': CashTransaction.objects.filter(
            account=compte, status=CashTransaction.Status.VALIDATED).count(),
        'derniere_cloture': CashClosure.objects.filter(
            account=compte).order_by('-date').first(),
    })


# ---------------------------------------------------------------------------
# Catégories d'écriture
# ---------------------------------------------------------------------------

def _etat_categorie(categorie):
    """Ce que l'audit retient d'une catégorie : nom, sens, état."""
    return {
        'nom': categorie.name,
        'sens': categorie.direction,
        'active': categorie.active,
    }


@cash_write_required(*FINANCE_ROLES)
def category_list(request):
    """Catégories du journal : les créer et les régler, jamais les effacer.

    Une catégorie porte le sens des montants qu'elle range. Supprimer la
    sienne effacerait le classement des écritures déjà comptabilisées : on la
    désactive, elle sort des listes de saisie et son passé reste en place.
    """
    form = TransactionCategoryForm()
    if request.method == 'POST':
        form = TransactionCategoryForm(request.POST)
        if form.is_valid():
            categorie = form.save()
            log_audit(request, 'TRANSACTION_CATEGORY_CREATE',
                      'TransactionCategory', str(categorie.id),
                      after=_etat_categorie(categorie))
            messages.success(
                request, _("Catégorie « %(nom)s » créée.") % {'nom': categorie.name})
            return redirect('core:dashboard:categories')
    return render(request, 'dashboard/comptabilite/categories.html', {
        'form': form,
        'lignes': TransactionCategory.objects.annotate(
            ecritures=Count('transactions')),
    })


@cash_write_required(*FINANCE_ROLES)
def category_update(request, category_id):
    """Régler une catégorie : le nom se corrige, le sens et le passé restent."""
    categorie = get_object_or_404(TransactionCategory, id=category_id)
    form = TransactionCategoryAdminForm(instance=categorie)
    if request.method == 'POST':
        form = TransactionCategoryAdminForm(request.POST, instance=categorie)
        if form.is_valid():
            # `instance` est touché dès la validation : l'état d'avant se relit en base.
            avant = _etat_categorie(TransactionCategory.objects.get(pk=categorie.pk))
            categorie = form.save()
            log_audit(request, 'TRANSACTION_CATEGORY_EDIT', 'TransactionCategory',
                      str(categorie.id), before=avant,
                      after=_etat_categorie(categorie))
            messages.success(
                request, _("Catégorie « %(nom)s » mise à jour.") % {'nom': categorie.name})
            return redirect('core:dashboard:categories')
    return render(request, 'dashboard/comptabilite/category_form.html', {
        'categorie': categorie,
        'form': form,
        'ecritures': categorie.transactions.count(),
        'historique': AuditLog.objects.filter(
            entity_type='TransactionCategory', entity_id=str(categorie.id),
        ).select_related('actor').order_by('-created_at')[:20],
    })


# ---------------------------------------------------------------------------
# Clôtures
# ---------------------------------------------------------------------------

@role_required(*FINANCE_ROLES)
def closure_list(request):
    closures = CashClosure.objects.select_related(
        'account', 'closed_by'
    )
    account_id = request.GET.get('account') or ''
    if account_id:
        closures = closures.filter(account_id=account_id)
    paginator = Paginator(closures, 30)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'dashboard/comptabilite/closures.html', {
        'page': page,
        'account_filter': account_id,
        'accounts': CashAccount.objects.filter(active=True),
    })


@cash_write_required(*FINANCE_ROLES)
def closure_create(request):
    form = CashClosureForm(initial={'date': timezone.localdate()})
    if request.method == 'POST':
        form = CashClosureForm(request.POST)
        if form.is_valid():
            account = form.cleaned_data['account']
            day = form.cleaned_data['date']
            if CashClosure.objects.filter(account=account, date=day).exists():
                form.add_error(None, _("Cette caisse est déjà clôturée pour cette date."))
            else:
                # Solde d'ouverture = solde avant la date clôturée.
                previous = CashClosure.objects.filter(
                    account=account, date__lt=day
                ).order_by('-date').first()
                if previous:
                    opening = previous.counted_amount
                else:
                    opening = account.balance_at(day - timedelta(days=1))

                incoming, outgoing = account.movement_totals(
                    start=day, end=day
                )
                theoretical = opening + incoming - outgoing

                closure = form.save(commit=False)
                closure.opening_balance = opening
                closure.theoretical_balance = theoretical
                closure.difference = (
                    closure.counted_amount - theoretical
                )
                closure.closed_by = request.user
                closure.save()
                log_audit(
                    request, 'CASH_CLOSURE', 'CashClosure', str(closure.id),
                    after={'account': account.name, 'date': str(day),
                           'theoretical': theoretical,
                           'counted': closure.counted_amount,
                           'difference': closure.difference},
                )
                messages.success(
                    request, _("Clôture enregistrée. Écart : %(ecart)s FCFA.") % {'ecart': closure.difference},
                )
                return redirect('core:dashboard:closures')
    return render(request, 'dashboard/comptabilite/closure_form.html', {
        'form': form,
    })


# ---------------------------------------------------------------------------
# Paiements étudiants
# ---------------------------------------------------------------------------

COUNTER_ENROLL_ROLES = ('ASSISTANT_ADMIN', 'DIRECTION')


def _student_from_id(value):
    """Étudiant désigné par l'URL, ``None`` si l'identifiant est invalide."""
    if not value:
        return None
    try:
        return User.objects.filter(id=value).first()
    except (ValueError, ValidationError):
        return None


def _encaisser(request, *, enrollment, amount, method, account, paid_at, note,
               motif, period_year=None, period_month=None):
    """Encaisse un paiement étudiant et pose l'écriture de caisse en vis-à-vis.

    Les deux écrans — un paiement, la grille des douze mois — passent par ici :
    une écriture, une caisse, une trace d'audit par règlement, jamais deux chemins
    qui pourraient diverger sur le même argent.
    """
    with db_transaction.atomic():
        payment = Payment.objects.create(
            enrollment=enrollment, amount=amount, method=method,
            paid_at=paid_at, recorded_by=request.user, note=note,
            status=Payment.Status.COMPLETED, motif=motif,
            period_year=period_year, period_month=period_month,
        )
        category, _unused = TransactionCategory.objects.get_or_create(
            name='Paiements des étudiants',  # i18n-exempt: nom stocké en base, clé de get_or_create
            direction=TransactionCategory.Direction.IN,
        )
        cash = caisse.poster(
            caisse=account, montant=amount, sens=CashTransaction.Type.IN,
            libelle=_("Paiement étudiant %(reference)s") % {'reference': payment.reference},
            categorie=category,
            description=(
                f"{enrollment.student.display_label} — "
                f"{enrollment.session.course.title}"
            ),
            methode=method, survenu=paid_at,
            contrepartie=enrollment.student.display_label,
            statut=CashTransaction.Status.VALIDATED, note=note,
            agent=request.user, requete=request,
        )
        payment.transaction = cash
        payment.save(update_fields=['transaction'])

    log_audit(
        request, 'PAYMENT_CREATE', 'Payment', str(payment.id),  # i18n-exempt: 'Payment' = nom de classe technique (audit)
        after={'amount': amount, 'reference': payment.reference,
               'enrollment': str(enrollment.id), 'transaction': cash.reference,
               'motif': motif, 'mois': period_month, 'annee': period_year,
               'balance_due': enrollment.balance_due},
    )
    return payment


@payment_write_required
def student_payment_create(request):
    student_param = (
        request.POST.get('student') if request.method == 'POST'
        else request.GET.get('student')
    ) or ''
    enrollment_param = request.GET.get('enrollment') or ''

    initial = {'paid_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M')}
    if enrollment_param:
        linked = (
            Enrollment.objects.select_related('student')
            .filter(id=enrollment_param).first()
        )
        if linked:
            initial['enrollment'] = linked.id
            initial['student'] = linked.student_id
            student_param = student_param or str(linked.student_id)
    if student_param:
        initial['student'] = student_param

    form = StudentPaymentForm(initial=initial)
    counter_form = CounterEnrollmentForm(
        prefix='inscription',
        initial={'student': student_param} if student_param else None,
    )

    if request.method == 'POST' and request.POST.get('form_kind') == 'enroll':
        counter_form = CounterEnrollmentForm(
            request.POST, prefix='inscription')
        if counter_form.is_valid():
            try:
                enrollment = counter_form.save(request.user)
            except IntegrityError:
                counter_form.add_error(
                    'session',
                    _("Cet étudiant est déjà inscrit à cette formation."),
                )
            else:
                log_audit(
                    request, 'ENROLLMENT_CREATE', 'Enrollment',
                    str(enrollment.id),
                    after={'student': str(enrollment.student_id),
                           'session': str(enrollment.session_id),
                           'net': enrollment.net_amount,
                           'status': enrollment.status,
                           'source': 'guichet'},
                )
                messages.success(
                    request, _("Inscription créée. Elle doit être validée par la direction avant tout encaissement."),
                )
                return redirect(
                    reverse('core:dashboard:payment-create')
                    + f"?student={enrollment.student_id}"
                )
    elif request.method == 'POST':
        form = StudentPaymentForm(request.POST)
        if form.is_valid():
            enrollment = form.cleaned_data['enrollment']
            amount = form.cleaned_data['amount']
            paid_at = form.cleaned_data['paid_at']

            # Anti double-soumission : même dossier, même montant, même minute.
            duplicate = Payment.objects.filter(
                enrollment=enrollment,
                amount=amount,
                recorded_by=request.user,
                paid_at__gte=paid_at - timedelta(minutes=2),
                paid_at__lte=paid_at + timedelta(minutes=2),
                status=Payment.Status.COMPLETED,
            ).exists()
            if duplicate:
                form.add_error(
                    None,
                    _("Un paiement identique vient d'être enregistré. Vérifiez le journal avant de réessayer."),
                )
            else:
                payment = _encaisser(
                    request, enrollment=enrollment, amount=amount,
                    method=form.cleaned_data['method'],
                    account=form.cleaned_data['account'], paid_at=paid_at,
                    note=form.cleaned_data['note'],
                    motif=form.cleaned_data['motif'],
                    period_year=form.cleaned_data['period_year'],
                    period_month=form.cleaned_data['period_month'],
                )

                messages.success(
                    request, _("Paiement %(reference)s enregistré. Reste à payer : %(reste)s FCFA.") % {'reference': payment.reference, 'reste': enrollment.balance_due},
                )
                return redirect('core:dashboard:payment-receipt',
                                payment_id=payment.id)

    enrolled_ids = Enrollment.objects.exclude(
        status=Enrollment.Status.CANCELLED,
    ).values_list('student_id', flat=True)
    selected_student = _student_from_id(student_param)
    pending_enrollments = Enrollment.objects.none()
    if selected_student:
        pending_enrollments = (
            selected_student.enrollments
            .filter(status=Enrollment.Status.PENDING)
            .select_related('session__course')
            .order_by('-enrolled_at')
        )
    return render(request, 'dashboard/comptabilite/payment_form.html', {
        'form': form,
        'counter_form': counter_form,
        'selected_student': selected_student,
        'pending_enrollments': pending_enrollments,
        'students_without_enrollment': User.objects.filter(
            roles__key=RoleKey.ETUDIANT,
            account_status=AccountStatus.ACTIVE,
        ).exclude(id__in=enrolled_ids).order_by('last_name', 'first_name'),
        'can_enroll': (
            not request.user.is_elevated
            and request.user.has_any_role(*COUNTER_ENROLL_ROLES)
        ),
    })


def _grille_des_mois(enrollment, annee):
    """Les douze mois de l'année, avec ce que la caisse a déjà encaissé.

    La mensualité proposée vient du dossier : net dû réparti sur la durée de la
    formation, donc la remise consentie est respectée. Un mois réglé en 2026 ne
    masque pas celui de 2027 — la grille est par année.
    """
    regles = {
        paiement.period_month: paiement
        for paiement in enrollment.payments.filter(
            period_month__isnull=False, period_year=annee,
        ).exclude(
            status__in=[Payment.Status.CANCELLED, Payment.Status.REFUNDED],
        )
    }
    suggestion = mensualite_attendue(enrollment)
    lignes = []
    for numero, libelle in MOIS:
        regle = regles.get(numero)
        lignes.append({
            'numero': numero,
            'libelle': libelle,
            'montant': (regle.amount if regle else suggestion),
            'paye': regle,
        })
    frais = (
        enrollment.payments.filter(motif=Payment.Motif.ENROLLMENT)
        .exclude(status__in=[Payment.Status.CANCELLED,
                             Payment.Status.REFUNDED])
        .first()
    )
    return lignes, frais


def _frais_inscription_pratiqués(enrollment):
    """Le montant d'entrée le plus souvent encaissé sur cette formation."""
    cours = enrollment.session.course
    pratique = (
        Payment.objects.filter(enrollment__session__course=cours,
                               motif=Payment.Motif.ENROLLMENT)
        .values('amount').annotate(n=Count('id')).order_by('-n', 'amount')
        .first()
    )
    return pratique['amount'] if pratique else programme.FRAIS_INSCRIPTION


@payment_write_required
def student_payment_months(request):
    """La grille : l'assistant coche les mois réglés et encaisse d'un coup."""
    etudiant_param = (
        request.POST.get('student') if request.method == 'POST'
        else request.GET.get('student')) or ''
    dossier_param = request.GET.get('enrollment') or ''
    brut_annee = request.GET.get('annee') or ''
    annee = int(brut_annee) if brut_annee.isdigit() else timezone.localdate().year

    initial = {'student': etudiant_param} if etudiant_param else {}
    dossier = None
    lignes = None
    frais = None

    if request.method == 'POST':
        form = PaymentMonthsForm(request.POST)
        if form.is_valid():
            dossier = form.cleaned_data['enrollment']
            annee = form.cleaned_data['annee']
            now = timezone.localtime()
            regles = []
            for ligne in form.lignes:
                # La recette se date au jour présent, jamais au premier jour du
                # mois réglé : cocher « janvier 2027 » en novembre signifie que
                # l'élève paie d'avance, pas que l'argent est entré en 2027. La
                # période réglée porte le mois couvert, paid_at porte la recette.
                regles.append(_encaisser(
                    request, enrollment=dossier, amount=ligne['montant'],
                    method=form.cleaned_data['method'],
                    account=form.cleaned_data['account'], paid_at=now,
                    note=form.cleaned_data['note'], motif=ligne['motif'],
                    period_year=ligne['annee'], period_month=ligne['mois'],
                ))
            total = sum(regle.amount for regle in regles)
            messages.success(
                request,
                _("%(nb)s paiement(s) enregistré(s) · %(total)s FCFA encaissés · reste %(reste)s FCFA.") % {
                    'nb': len(regles), 'total': total, 'reste': dossier.balance_due},
            )
            return redirect(
                reverse('core:dashboard:payment-months')
                + f"?student={dossier.student_id}&enrollment={dossier.id}&annee={annee}"  # i18n-exempt: paramètres d'URL
            )
        dossier = form.cleaned_data.get('enrollment')
        annee = form.cleaned_data.get('annee') or annee
    else:
        if dossier_param:
            dossier = (Enrollment.objects.select_related('student', 'session__course')
                       .filter(id=dossier_param).first())
            if dossier:
                etudiant_param = str(dossier.student_id)
                initial = {
                    'student': etudiant_param, 'enrollment': str(dossier.id),
                    'annee': annee,
                    'account': CashAccount.objects.filter(active=True).first(),
                }
        form = PaymentMonthsForm(initial=initial)

    if dossier:
        lignes, frais = _grille_des_mois(dossier, annee)
        frais_montant = (frais.amount if frais
                         else _frais_inscription_pratiqués(dossier))
    else:
        frais_montant = programme.FRAIS_INSCRIPTION

    enrolled_ids = Enrollment.objects.exclude(
        status=Enrollment.Status.CANCELLED,
    ).values_list('student_id', flat=True)
    selected_student = _student_from_id(etudiant_param)
    return render(request, 'dashboard/comptabilite/payment_months.html', {
        'form': form,
        'lignes': lignes,
        'frais': frais,
        'frais_montant': frais_montant,
        'dossier': dossier,
        'annee': annee,
        'selected_student': selected_student,
        'mensualite': mensualite_attendue(dossier) if dossier else 0,
        'students_without_enrollment': User.objects.filter(
            roles__key=RoleKey.ETUDIANT,
            account_status=AccountStatus.ACTIVE,
        ).exclude(id__in=enrolled_ids).order_by('last_name', 'first_name'),
    })


@role_required(*FINANCE_ROLES, 'ETUDIANT', 'SECRETAIRE')
def payment_receipt(request, payment_id):
    payment = get_object_or_404(
        Payment.objects.select_related(
            'enrollment__student', 'enrollment__session__course',
            'recorded_by', 'transaction__account',
        ),
        id=payment_id,
    )
    user = request.user
    if not (
        user.has_any_role('ASSISTANT_ADMIN', 'DIRECTION', 'SUPER_ADMIN', 'ADMIN',
                          'SECRETAIRE') or
        payment.enrollment.student_id == user.id
    ):
        return HttpResponseForbidden(_("Accès au reçu non autorisé."))
    log_audit(request, 'PAYMENT_RECEIPT', 'Payment', str(payment.id))  # i18n-exempt: 'Payment' = nom de classe technique (audit)
    return render(request, 'dashboard/comptabilite/receipt.html', {
        'payment': payment,
        'enrollment': payment.enrollment,
        'student': payment.enrollment.student,
        'printed_at': timezone.now(),
    })
