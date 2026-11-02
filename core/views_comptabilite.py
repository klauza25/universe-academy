"""Dashboard comptabilité : journal, opérations, caisses et clôtures."""
import csv
from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction as db_transaction
from django.db.models import Q, Sum
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .decorators import business_write_required, role_required
from .forms import (
    CashAccountForm, CashClosureForm, CashTransactionForm, CounterEnrollmentForm,
    StudentPaymentForm,
)
from .models import (
    AccountStatus, AuditLog, CashAccount, CashClosure, CashTransaction,
    Enrollment, Payment, RoleKey, TransactionCategory, User,
)
from .utils import log_audit

FINANCE_ROLES = ('COMPTABLE', 'DIRECTION')


def account_balance(account, until_date=None):
    """Solde d'une caisse : ouverture + entrées validées − sorties validées."""
    return account.balance_at(until_date)


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


@business_write_required(*FINANCE_ROLES)
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
                request, _("Opération %(reference)s enregistrée.") % {'reference': tx.reference}
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
        if request.user.is_elevated:
            return HttpResponseForbidden(
                _("Consultation seule : cette action relève du rôle métier.")
            )
        action = request.POST.get('action')
        if action == 'cancel':
            reason = (request.POST.get('reason') or '').strip()
            if not reason:
                messages.error(request, _("Un motif est obligatoire pour annuler."))
            elif tx.status == CashTransaction.Status.CANCELLED:
                messages.info(request, _("Cette opération est déjà annulée."))
            else:
                before = {'status': tx.status}
                tx.status = CashTransaction.Status.CANCELLED
                tx.note = (tx.note + '\n' if tx.note else '') + (
                    _("Annulation : %(motif)s") % {'motif': reason}
                )
                tx.save(update_fields=['status', 'note', 'updated_at'])
                log_audit(
                    request, 'CASH_TRANSACTION_CANCEL', 'CashTransaction',
                    str(tx.id), before=before,
                    after={'status': tx.status, 'reason': reason},
                )
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


@role_required(*FINANCE_ROLES)
def account_list(request):
    form = CashAccountForm()
    if request.method == 'POST':
        if request.user.is_elevated:
            return HttpResponseForbidden(
                _("Consultation seule : cette action relève du rôle métier.")
            )
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


@business_write_required(*FINANCE_ROLES)
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

COUNTER_ENROLL_ROLES = ('COMPTABLE', 'DIRECTION')


def _student_from_id(value):
    """Étudiant désigné par l'URL, ``None`` si l'identifiant est invalide."""
    if not value:
        return None
    try:
        return User.objects.filter(id=value).first()
    except (ValueError, ValidationError):
        return None


@business_write_required(*FINANCE_ROLES)
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
                    category, _unused = TransactionCategory.objects.get_or_create(
                        name='Paiements des étudiants',  # i18n-exempt: nom stocké en base, clé de get_or_create
                        direction=TransactionCategory.Direction.IN,
                    )
                    cash = CashTransaction.objects.create(
                        tx_type=CashTransaction.Type.IN,
                        category=category,
                        label=_("Paiement étudiant %(reference)s") % {'reference': payment.reference},
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
                    request, 'PAYMENT_CREATE', 'Payment', str(payment.id),  # i18n-exempt: 'Payment' = nom de classe technique (audit)
                    after={'amount': amount, 'reference': payment.reference,
                           'enrollment': str(enrollment.id),
                           'transaction': cash.reference,
                           'balance_due': enrollment.balance_due},
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
        user.has_any_role('COMPTABLE', 'DIRECTION', 'SUPER_ADMIN', 'ADMIN',
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
