"""Dashboard Accueil : visites au centre, prospects et suivi des relances."""
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .decorators import role_required
from .forms import ProspectFollowUpForm, ProspectForm, VisitForm, VisitReasonForm
from .models import (
    Contact, Prospect, ProspectFollowUp, Visit, VisitReason, RoleKey,
)
from .utils import log_audit

ACCUEIL_ROLES = ('ACCUEIL', 'SECRETAIRE', 'DIRECTION')


def _filter_visits(request):
    visits = Visit.objects.select_related(
        'contact', 'reason', 'agent'
    ).all()
    query = (request.GET.get('q') or '').strip()
    status = request.GET.get('status') or ''
    date_from = request.GET.get('from') or ''
    date_to = request.GET.get('to') or ''
    if query:
        visits = visits.filter(
            Q(reference__icontains=query) |
            Q(contact__first_name__icontains=query) |
            Q(contact__last_name__icontains=query) |
            Q(contact__phone__icontains=query) |
            Q(contact__email__icontains=query)
        )
    if status:
        visits = visits.filter(status=status)
    if date_from:
        visits = visits.filter(arrival_at__date__gte=date_from)
    if date_to:
        visits = visits.filter(arrival_at__date__lte=date_to)
    return visits.distinct(), {
        'query': query,
        'status_filter': status,
        'date_from': date_from,
        'date_to': date_to,
    }


@role_required(*ACCUEIL_ROLES)
def visit_list(request):
    visits, filters = _filter_visits(request)
    paginator = Paginator(visits, 20)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'dashboard/accueil/visits.html', {
        'page': page,
        'status_choices': Visit.Status.choices,
        **filters,
    })


@role_required(*ACCUEIL_ROLES)
def visit_create(request):
    form = VisitForm()
    if request.method == 'POST':
        form = VisitForm(request.POST)
        if form.is_valid():
            visit = form.save(commit=False)
            visit.agent = request.user
            visit.save()
            log_audit(
                request, 'VISIT_CREATE', 'Visit', str(visit.id),
                after={
                    'reference': visit.reference,
                    'contact': visit.contact.full_name,
                    'status': visit.status,
                },
            )
            messages.success(
                request, f"Visite {visit.reference} enregistrée."
            )
            return redirect('core:dashboard:visit-detail', visit_id=visit.id)
    return render(request, 'dashboard/accueil/visit_form.html', {'form': form})


@role_required(*ACCUEIL_ROLES)
def visit_detail(request, visit_id):
    visit = get_object_or_404(
        Visit.objects.select_related('contact', 'reason', 'agent'), id=visit_id
    )
    form = VisitForm(instance=visit)
    if request.method == 'POST':
        before = {'status': visit.status, 'departure_at': str(visit.departure_at)}
        form = VisitForm(request.POST, instance=visit)
        if form.is_valid():
            visit = form.save(commit=False)
            visit.agent = visit.agent or request.user
            visit.save()
            log_audit(
                request, 'VISIT_UPDATE', 'Visit', str(visit.id),
                before=before,
                after={'status': visit.status,
                       'departure_at': str(visit.departure_at)},
            )
            messages.success(request, "Visite mise à jour.")
            return redirect('core:dashboard:visit-detail', visit_id=visit.id)

    return render(request, 'dashboard/accueil/visit_detail.html', {
        'visit': visit,
        'form': form,
        'status_choices': Visit.Status.choices,
        'prospects': visit.prospects.all(),
    })


@role_required(*ACCUEIL_ROLES)
def visit_departure(request, visit_id):
    if request.method != 'POST':
        return redirect('core:dashboard:visit-detail', visit_id=visit_id)
    visit = get_object_or_404(Visit, id=visit_id)
    if visit.departure_at:
        messages.info(request, "Le départ de cette visite est déjà enregistré.")
    else:
        visit.departure_at = timezone.now()
        visit.status = Visit.Status.COMPLETED
        visit.save(update_fields=['departure_at', 'status', 'updated_at'])
        log_audit(
            request, 'VISIT_DEPARTURE', 'Visit', str(visit.id),
            after={'departure_at': str(visit.departure_at)},
        )
        messages.success(request, "Départ enregistré.")
    return redirect('core:dashboard:visit-detail', visit_id=visit.id)


@role_required(*ACCUEIL_ROLES)
def visit_to_prospect(request, visit_id):
    visit = get_object_or_404(Visit.objects.select_related('contact'), id=visit_id)
    if request.method != 'POST':
        return redirect('core:dashboard:visit-detail', visit_id=visit.id)
    existing = visit.prospects.first()
    if existing:
        messages.info(request, f"Cette visite est déjà liée au prospect {existing.reference}.")
        return redirect('core:dashboard:prospect-detail', prospect_id=existing.id)

    prospect = Prospect.objects.create(
        contact=visit.contact,
        source=Prospect.Source.VISIT,
        first_contact_at=visit.arrival_at.date(),
        agent=request.user,
        interest_reason=visit.request_description,
        status=Prospect.Status.TO_CONTACT,
        visit=visit,
    )
    log_audit(
        request, 'PROSPECT_FROM_VISIT', 'Prospect', str(prospect.id),
        after={'reference': prospect.reference, 'visit': visit.reference},
    )
    messages.success(request, f"Prospect {prospect.reference} créé depuis la visite.")
    return redirect('core:dashboard:prospect-detail', prospect_id=prospect.id)


def _filter_prospects(request):
    prospects = Prospect.objects.select_related(
        'contact', 'course', 'agent', 'converted_student'
    ).all()
    query = (request.GET.get('q') or '').strip()
    status = request.GET.get('status') or ''
    due = request.GET.get('due') or ''
    if query:
        prospects = prospects.filter(
            Q(reference__icontains=query) |
            Q(contact__first_name__icontains=query) |
            Q(contact__last_name__icontains=query) |
            Q(contact__phone__icontains=query) |
            Q(contact__email__icontains=query)
        )
    if status:
        prospects = prospects.filter(status=status)
    if due == 'today':
        prospects = prospects.filter(next_follow_up=timezone.localdate())
    elif due == 'overdue':
        prospects = prospects.filter(next_follow_up__lt=timezone.localdate())
    return prospects.distinct(), {
        'query': query,
        'status_filter': status,
        'due_filter': due,
    }


@role_required(*ACCUEIL_ROLES)
def prospect_list(request):
    prospects, filters = _filter_prospects(request)
    paginator = Paginator(prospects, 20)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'dashboard/accueil/prospects.html', {
        'page': page,
        'status_choices': Prospect.Status.choices,
        'today': timezone.localdate(),
        **filters,
    })


@role_required(*ACCUEIL_ROLES)
def prospect_create(request):
    form = ProspectForm()
    if request.method == 'POST':
        form = ProspectForm(request.POST)
        if form.is_valid():
            prospect = form.save(commit=False)
            prospect.agent = request.user
            prospect.save()
            log_audit(
                request, 'PROSPECT_CREATE', 'Prospect', str(prospect.id),
                after={'reference': prospect.reference,
                       'status': prospect.status},
            )
            messages.success(
                request, f"Prospect {prospect.reference} enregistré."
            )
            return redirect('core:dashboard:prospect-detail', prospect_id=prospect.id)
    return render(request, 'dashboard/accueil/prospect_form.html', {'form': form})


@role_required(*ACCUEIL_ROLES)
def prospect_detail(request, prospect_id):
    prospect = get_object_or_404(
        Prospect.objects.select_related('contact', 'course', 'agent',
                                        'converted_student'),
        id=prospect_id,
    )
    form = ProspectForm(instance=prospect)
    follow_form = ProspectFollowUpForm(initial={
        'phone_used': prospect.contact.phone,
        'course': prospect.course_id,
    })

    if request.method == 'POST':
        action = request.POST.get('action', 'edit')
        if action == 'follow_up':
            follow_form = ProspectFollowUpForm(request.POST)
            if follow_form.is_valid():
                follow = follow_form.save(commit=False)
                follow.prospect = prospect
                follow.agent = request.user
                follow.save()
                prospect.status = Prospect.Status.CONTACTED
                update_fields = ['status', 'updated_at']
                if follow.next_follow_up:
                    prospect.next_follow_up = follow.next_follow_up
                    update_fields.append('next_follow_up')
                prospect.save(update_fields=update_fields)
                log_audit(
                    request, 'PROSPECT_FOLLOW_UP', 'Prospect', str(prospect.id),
                    after={'contact_type': follow.contact_type,
                           'next_follow_up': str(follow.next_follow_up)},
                )
                messages.success(request, "Suivi enregistré.")
                return redirect('core:dashboard:prospect-detail',
                                prospect_id=prospect.id)
        else:
            form = ProspectForm(request.POST, instance=prospect)
            if form.is_valid():
                before = {'status': prospect.status,
                          'next_follow_up': str(prospect.next_follow_up)}
                prospect = form.save()
                log_audit(
                    request, 'PROSPECT_UPDATE', 'Prospect', str(prospect.id),
                    before=before,
                    after={'status': prospect.status,
                           'next_follow_up': str(prospect.next_follow_up)},
                )
                messages.success(request, "Prospect mis à jour.")
                return redirect('core:dashboard:prospect-detail',
                                prospect_id=prospect.id)

    return render(request, 'dashboard/accueil/prospect_detail.html', {
        'prospect': prospect,
        'form': form,
        'follow_form': follow_form,
        'follow_ups': prospect.follow_ups.select_related('agent', 'course'),
        'status_choices': Prospect.Status.choices,
        'can_convert': request.user.has_any_role(
            'SECRETAIRE', 'DIRECTION', 'SUPER_ADMIN', 'ACCUEIL'
        ),
        'can_manage_students': request.user.has_any_role(
            'SECRETAIRE', 'DIRECTION', 'SUPER_ADMIN'
        ),
    })


@role_required('ACCUEIL', 'SECRETAIRE', 'DIRECTION', 'SUPER_ADMIN')
def visit_reason_list(request):
    form = VisitReasonForm()
    if request.method == 'POST':
        form = VisitReasonForm(request.POST)
        if form.is_valid():
            reason = form.save()
            log_audit(request, 'VISIT_REASON_CREATE', 'VisitReason', str(reason.id),
                      after={'label': reason.label})
            messages.success(request, "Motif de visite ajouté.")
            return redirect('core:dashboard:visit-reasons')
    return render(request, 'dashboard/accueil/reasons.html', {
        'form': form,
        'reasons': VisitReason.objects.all(),
    })


@role_required('ACCUEIL', 'SECRETAIRE', 'DIRECTION', 'SUPER_ADMIN')
def visit_reason_toggle(request, reason_id):
    if request.method != 'POST':
        return redirect('core:dashboard:visit-reasons')
    reason = get_object_or_404(VisitReason, id=reason_id)
    reason.active = not reason.active
    reason.save(update_fields=['active'])
    log_audit(
        request, 'VISIT_REASON_TOGGLE', 'VisitReason', str(reason.id),
        after={'active': reason.active},
    )
    messages.success(
        request,
        f"Motif « {reason.label} » {'activé' if reason.active else 'désactivé'}.",
    )
    return redirect('core:dashboard:visit-reasons')


@role_required('ACCUEIL', 'SECRETAIRE', 'DIRECTION')
def contact_search(request):
    """Recherche AJAX simple pour réutiliser une fiche contact existante."""
    query = (request.GET.get('q') or '').strip()
    contacts = Contact.objects.none()
    if len(query) >= 3:
        contacts = Contact.objects.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(phone__icontains=query) |
            Q(email__icontains=query)
        )[:10]
    return render(request, 'dashboard/accueil/_contact_results.html', {
        'contacts': contacts,
    })
