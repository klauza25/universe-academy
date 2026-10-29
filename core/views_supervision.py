"""Supervision financière globale réservée au super administrateur.

Cet espace ne crée ni ne modifie aucune donnée : il agrège les opérations
enregistrées dans tous les modules (comptabilité, paiements étudiants,
dépenses) à partir des seules transactions validées de la base réelle.
"""
import csv

from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from .decorators import role_required
from .models import CashAccount, CashTransaction, TransactionCategory, User
from .utils import log_audit
from .views_comptabilite import accounts_with_balance

EXPORT_LIMIT = 5000


def _filtered_transactions(request):
    qs = CashTransaction.objects.select_related(
        'account', 'destination_account', 'category', 'created_by',
        'student_payment', 'expense_record',
    )
    query = (request.GET.get('q') or '').strip()
    tx_type = request.GET.get('type') or ''
    status = request.GET.get('status') or ''
    category_id = request.GET.get('category') or ''
    account_id = request.GET.get('account') or ''
    method = request.GET.get('method') or ''
    user_id = request.GET.get('user') or ''
    date_from = request.GET.get('from') or ''
    date_to = request.GET.get('to') or ''

    if query:
        qs = qs.filter(
            Q(reference__icontains=query) |
            Q(label__icontains=query) |
            Q(counterparty__icontains=query) |
            Q(description__icontains=query) |
            Q(note__icontains=query) |
            Q(category__name__icontains=query)
        )
    if tx_type:
        qs = qs.filter(tx_type=tx_type)
    if status:
        qs = qs.filter(status=status)
    if category_id:
        qs = qs.filter(category_id=category_id)
    if account_id:
        qs = qs.filter(
            Q(account_id=account_id) | Q(destination_account_id=account_id)
        )
    if method:
        qs = qs.filter(method=method)
    if user_id:
        qs = qs.filter(created_by_id=user_id)
    if date_from:
        qs = qs.filter(occurred_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(occurred_at__date__lte=date_to)

    filters = {
        'query': query,
        'type_filter': tx_type,
        'status_filter': status,
        'category_filter': category_id,
        'account_filter': account_id,
        'method_filter': method,
        'user_filter': user_id,
        'date_from': date_from,
        'date_to': date_to,
    }
    return qs.distinct(), filters


def _csv_row(tx):
    occurred = timezone.localtime(tx.occurred_at)
    created = timezone.localtime(tx.created_at)
    payment = getattr(tx, 'student_payment', None)
    expense = getattr(tx, 'expense_record', None)
    return [
        tx.reference,
        occurred.strftime('%d/%m/%Y'),
        occurred.strftime('%H:%M'),
        tx.get_tx_type_display(),
        tx.category.name if tx.category else '',
        tx.amount,
        tx.currency,
        tx.label,
        tx.description,
        tx.counterparty,
        tx.get_method_display(),
        tx.account.name,
        tx.destination_account.name if tx.destination_account else '',
        tx.created_by.display_label if tx.created_by else '',
        created.strftime('%d/%m/%Y'),
        created.strftime('%H:%M'),
        tx.get_status_display(),
        'Oui' if tx.receipt else 'Non',
        tx.note,
        payment.reference if payment else '',
        expense.category if expense else '',
    ]


@role_required('SUPER_ADMIN')
def finance_supervision(request):
    qs, filters = _filtered_transactions(request)

    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = (
            'attachment; filename="supervision-financiere.csv"'
        )
        response.write('\ufeff')
        writer = csv.writer(response, delimiter=';')
        writer.writerow([
            'Référence', 'Date effective', 'Heure effective', 'Type',
            'Catégorie', 'Montant', 'Devise', 'Libellé', 'Description',
            'Payeur / Bénéficiaire', 'Moyen de paiement', 'Caisse',
            'Compte destination', 'Auteur', 'Enregistrée le',
            'Enregistrée à', 'Statut', 'Justificatif', 'Commentaire',
            'Paiement étudiant', 'Dépense liée',
        ])
        rows = qs.order_by('-occurred_at', '-created_at')[:EXPORT_LIMIT]
        for tx in rows:
            writer.writerow(_csv_row(tx))
        log_audit(
            request, 'FINANCE_EXPORT', 'CashTransaction', 'csv',
            after={'rows': min(qs.count(), EXPORT_LIMIT), **filters},
        )
        return response

    validated = qs.filter(status=CashTransaction.Status.VALIDATED)
    totals = validated.aggregate(
        incoming=Sum('amount', filter=Q(tx_type=CashTransaction.Type.IN)),
        outgoing=Sum('amount', filter=Q(tx_type=CashTransaction.Type.OUT)),
    )

    out_by_category = (
        validated.filter(tx_type=CashTransaction.Type.OUT)
        .values('category_id', 'category__name')
        .annotate(total=Sum('amount'), rows=Count('id'))
        .order_by('-total')
    )

    paginator = Paginator(
        qs.order_by('-occurred_at', '-created_at'), 50
    )
    page = paginator.get_page(request.GET.get('page', 1))
    balances = accounts_with_balance()

    return render(request, 'dashboard/super_admin/supervision.html', {
        'page': page,
        'totals': totals,
        'net_total': (totals['incoming'] or 0) - (totals['outgoing'] or 0),
        'pending_count': qs.filter(
            status=CashTransaction.Status.DRAFT
        ).count(),
        'cancelled_count': qs.filter(
            status=CashTransaction.Status.CANCELLED
        ).count(),
        'out_by_category': out_by_category,
        'balances': balances,
        'balance_total': sum(row['balance'] for row in balances),
        'accounts': CashAccount.objects.filter(active=True),
        'categories': TransactionCategory.objects.filter(active=True),
        'method_choices': CashTransaction.Method.choices,
        'type_choices': CashTransaction.Type.choices,
        'status_choices': CashTransaction.Status.choices,
        'users': User.objects.filter(
            created_transactions__isnull=False
        ).distinct().order_by('last_name', 'first_name'),
        **filters,
    })
