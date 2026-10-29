from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


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
