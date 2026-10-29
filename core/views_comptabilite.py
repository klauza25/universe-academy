"""Dashboard comptabilité : journal, opérations, caisses et clôtures."""
import csv
from datetime import datetime, time, timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction as db_transaction
from django.db.models import Q, Sum
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .decorators import role_required
from .forms import (
    CashAccountForm, CashClosureForm, CashTransactionForm, StudentPaymentForm,
)
from .models import (
    CashAccount, CashClosure, CashTransaction, Enrollment, Payment,
    TransactionCategory, User,
)
from .utils import log_audit

FINANCE_ROLES = ('COMPTABLE', 'DIRECTION')


def _validated():
    return CashTransaction.objects.filter(
        status=CashTransaction.Status.VALIDATED
    )


def account_balance(account, until_date=None):
    """Solde d'une caisse : ouverture + entrées validées − sorties validées."""
    qs = _validated()
    if until_date:
        qs = qs.filter(occurred_at__date__lte=until_date)
    incoming = qs.filter(
        Q(tx_type=CashTransaction.Type.IN, account=account) |
        Q(tx_type=CashTransaction.Type.TRANSFER, destination_account=account)
    ).aggregate(total=Sum('amount'))['total'] or 0
    outgoing = qs.filter(
        Q(tx_type=CashTransaction.Type.OUT, account=account) |
        Q(tx_type=CashTransaction.Type.TRANSFER, account=account)
    ).aggregate(total=Sum('amount'))['total'] or 0
    return account.opening_balance + incoming - outgoing


def accounts_with_balance():
    rows = []
    for account in CashAccount.objects.filter(active=True):
        rows.append({'account': account, 'balance': account_balance(account)})
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
            'attachment; filename="journal-comptable.csv"'
        )
        response.write('\ufeff')
        writer = csv.writer(response, delimiter=';')
        writer.writerow([
            'Référence', 'Date effective', 'Saisie', 'Type', 'Catégorie',
            'Libellé', 'Bénéficiaire/Payeur', 'Entrée', 'Sortie',
            'Moyen', 'Caisse', 'Auteur', 'Statut',
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


@role_required(*FINANCE_ROLES)
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
            tx = form.save(commit=False)
            tx.created_by = request.user
            tx.save()
            log_audit(
                request, 'CASH_TRANSACTION_CREATE', 'CashTransaction',
                str(tx.id),
                after={
                    'reference': tx.reference,
                    'type': tx.tx_type,
                    'amount': tx.amount,
                    'account': tx.account.name,
                    'status': tx.status,
                },
            )
            messages.success(
                request, f"Opération {tx.reference} enregistrée."
            )
            return redirect('core:dashboard:transaction-detail', tx_id=tx.id)
    return render(request, 'dashboard/comptabilite/transaction_form.html', {
        'form': form,
        'tx_type': tx_type,
    })


@role_required(*FINANCE_ROLES)
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
            if not reason:
                messages.error(request, "Un motif est obligatoire pour annuler.")
            elif tx.status == CashTransaction.Status.CANCELLED:
                messages.info(request, "Cette opération est déjà annulée.")
            else:
                before = {'status': tx.status}
                tx.status = CashTransaction.Status.CANCELLED
                tx.note = (tx.note + '\n' if tx.note else '') + (
                    f"Annulation : {reason}"
                )
                tx.save(update_fields=['status', 'note', 'updated_at'])
                log_audit(
                    request, 'CASH_TRANSACTION_CANCEL', 'CashTransaction',
                    str(tx.id), before=before,
                    after={'status': tx.status, 'reason': reason},
                )
                messages.success(request, "Opération annulée et historisée.")
            return redirect('core:dashboard:transaction-detail', tx_id=tx.id)

    return render(request, 'dashboard/comptabilite/transaction_detail.html', {
        'tx': tx,
        'student_payment': getattr(tx, 'student_payment', None),
    })


@role_required(*FINANCE_ROLES)
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
            messages.success(request, "Caisse / compte créé.")
            return redirect('core:dashboard:accounts')
    return render(request, 'dashboard/comptabilite/accounts.html', {
        'rows': accounts_with_balance(),
        'form': form,
        'closed_accounts': CashAccount.objects.filter(active=False),
    })


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


@role_required(*FINANCE_ROLES)
def closure_create(request):
    form = CashClosureForm(initial={'date': timezone.localdate()})
    if request.method == 'POST':
        form = CashClosureForm(request.POST)
        if form.is_valid():
            account = form.cleaned_data['account']
            day = form.cleaned_data['date']
            if CashClosure.objects.filter(account=account, date=day).exists():
                form.add_error(None, "Cette caisse est déjà clôturée pour cette date.")
            else:
                # Solde d'ouverture = solde avant la date clôturée.
                previous = CashClosure.objects.filter(
                    account=account, date__lt=day
                ).order_by('-date').first()
                if previous:
                    opening = previous.counted_amount
                else:
                    opening = account.opening_balance
                    movements = _validated().filter(
                        account=account, occurred_at__date__lt=day
                    )
                    incoming = movements.filter(
                        tx_type=CashTransaction.Type.IN
                    ).aggregate(total=Sum('amount'))['total'] or 0
                    incoming += movements.filter(
                        tx_type=CashTransaction.Type.TRANSFER,
                        destination_account=account,
                    ).aggregate(total=Sum('amount'))['total'] or 0
                    outgoing = movements.filter(
                        tx_type=CashTransaction.Type.OUT
                    ).aggregate(total=Sum('amount'))['total'] or 0
                    outgoing += movements.filter(
                        tx_type=CashTransaction.Type.TRANSFER,
                        account=account,
                    ).aggregate(total=Sum('amount'))['total'] or 0
                    opening += incoming - outgoing

                end_of_day = datetime.combine(day, time.max)
                end_of_day = timezone.make_aware(end_of_day)
                theoretical = opening
                movements = _validated().filter(
                    account=account,
                    occurred_at__gte=timezone.make_aware(
                        datetime.combine(day, time.min)),
                    occurred_at__lte=end_of_day,
                )
                incoming = movements.filter(
                    tx_type=CashTransaction.Type.IN
                ).aggregate(total=Sum('amount'))['total'] or 0
                incoming += movements.filter(
                    tx_type=CashTransaction.Type.TRANSFER,
                    destination_account=account,
                ).aggregate(total=Sum('amount'))['total'] or 0
                outgoing = movements.filter(
                    tx_type=CashTransaction.Type.OUT
                ).aggregate(total=Sum('amount'))['total'] or 0
                outgoing += movements.filter(
                    tx_type=CashTransaction.Type.TRANSFER,
                    account=account,
                ).aggregate(total=Sum('amount'))['total'] or 0
                theoretical += incoming - outgoing

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
                    request,
                    f"Clôture enregistrée. Écart : {closure.difference} FCFA.",
                )
                return redirect('core:dashboard:closures')
    return render(request, 'dashboard/comptabilite/closure_form.html', {
        'form': form,
    })


# ---------------------------------------------------------------------------
# Paiements étudiants
# ---------------------------------------------------------------------------

@role_required(*FINANCE_ROLES)
def student_payment_create(request):
    initial = {'paid_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M')}
    enrollment_id = request.GET.get('enrollment')
    if enrollment_id:
        initial['enrollment'] = enrollment_id
    form = StudentPaymentForm(initial=initial)

    if request.method == 'POST':
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
                    "Un paiement identique vient d'être enregistré. "
                    "Vérifiez le journal avant de réessayer.",
                )
            else:
                with db_transaction.atomic():
                    payment = Payment.objects.create(
                        enrollment=enrollment,
                        amount=amount,
                        method=form.cleaned_data['method'],
                        paid_at=paid_at,
                        recorded_by=request.user,
                        note=form.cleaned_data['note'],
                        status=Payment.Status.COMPLETED,
                    )
                    category, _ = TransactionCategory.objects.get_or_create(
                        name='Paiements des étudiants',
                        direction=TransactionCategory.Direction.IN,
                    )
                    cash = CashTransaction.objects.create(
                        tx_type=CashTransaction.Type.IN,
                        category=category,
                        label=f"Paiement étudiant {payment.reference}",
                        description=(
                            f"{enrollment.student.display_label} — "
                            f"{enrollment.session.course.title}"
                        ),
                        amount=amount,
                        currency=enrollment.session.course.currency,
                        occurred_at=paid_at,
                        account=form.cleaned_data['account'],
                        method=payment.method,
                        counterparty=enrollment.student.display_label,
                        status=CashTransaction.Status.VALIDATED,
                        created_by=request.user,
                        note=form.cleaned_data['note'],
                    )
                    payment.transaction = cash
                    payment.save(update_fields=['transaction'])

                log_audit(
                    request, 'PAYMENT_CREATE', 'Payment', str(payment.id),
                    after={'amount': amount, 'reference': payment.reference,
                           'enrollment': str(enrollment.id),
                           'transaction': cash.reference,
                           'balance_due': enrollment.balance_due},
                )
                messages.success(
                    request,
                    f"Paiement {payment.reference} enregistré. "
                    f"Reste à payer : {enrollment.balance_due} FCFA.",
                )
                return redirect('core:dashboard:payment-receipt',
                                payment_id=payment.id)

    return render(request, 'dashboard/comptabilite/payment_form.html', {
        'form': form,
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
        user.has_any_role('COMPTABLE', 'DIRECTION', 'SUPER_ADMIN',
                          'SECRETAIRE') or
        payment.enrollment.student_id == user.id
    ):
        return HttpResponseForbidden("Accès au reçu non autorisé.")
    log_audit(request, 'PAYMENT_RECEIPT', 'Payment', str(payment.id))
    return render(request, 'dashboard/comptabilite/receipt.html', {
        'payment': payment,
        'enrollment': payment.enrollment,
        'student': payment.enrollment.student,
        'printed_at': timezone.now(),
    })
