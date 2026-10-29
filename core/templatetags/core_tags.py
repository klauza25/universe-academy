import json
import uuid

from django import template
from django.urls import NoReverseMatch, reverse

register = template.Library()

# Entité audit → route de fiche consultable (paramètre d'URL).
AUDIT_ENTITY_ROUTES = {
    'CashTransaction': ('core:dashboard:transaction-detail', 'tx_id'),
    'User': ('core:dashboard:user-detail', 'user_id'),
    'Payment': ('core:dashboard:payment-receipt', 'payment_id'),
    'Enrollment': ('core:dashboard:enrollment-detail', 'enrollment_id'),
    'Visit': ('core:dashboard:visit-detail', 'visit_id'),
    'Prospect': ('core:dashboard:prospect-detail', 'prospect_id'),
    'SessionRecord': ('core:dashboard:session-record-detail', 'record_id'),
    'Resource': ('core:dashboard:resource-view', 'resource_id'),
    'ScholarshipApplication': (
        'core:dashboard:scholarship-review-detail', 'app_id'
    ),
}


@register.simple_tag
def audit_entity_url(entity_type, entity_id):
    """URL de fiche pour une entité d'audit, ou chaîne vide si non résolvable."""
    route = AUDIT_ENTITY_ROUTES.get(entity_type)
    if not route or not is_uuid(entity_id):
        return ''
    try:
        return reverse(route[0], kwargs={route[1]: str(entity_id)})
    except NoReverseMatch:
        return ''


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def pretty_json(value):
    """Affiche un résumé JSON d'audit de façon lisible dans un <pre>."""
    if value in (None, '', {}, []):
        return ''
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        return str(value)


@register.filter
def is_uuid(value):
    """Vrai si la valeur peut servir d'identifiant dans une URL <uuid:…>."""
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


@register.simple_tag(takes_context=True)
def query_replace(context, **kwargs):
    """Renvoie la query string courante en remplaçant les paramètres donnés."""
    request = context.get('request')
    if not request:
        return ''
    query = request.GET.copy()
    for key, value in kwargs.items():
        if value is None or value == '':
            query.pop(key, None)
        else:
            query[key] = value
    return query.urlencode()
