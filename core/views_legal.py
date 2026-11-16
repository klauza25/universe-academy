from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.html import escape
from django.views.decorators.http import require_GET


@require_GET
def privacy_policy(request):
    return render(request, 'public/privacy.html')


@require_GET
def terms_of_service(request):
    return render(request, 'public/terms.html')


@require_GET
def robots_txt(request):
    sitemap_url = request.build_absolute_uri(reverse('core:sitemap'))
    content = '\n'.join((
        'User-agent: *',
        'Allow: /',
        'Disallow: /dashboard/',
        'Disallow: /admin/',
        f'Sitemap: {sitemap_url}',
        '',
    ))
    return HttpResponse(content, content_type='text/plain; charset=utf-8')


@require_GET
def sitemap_xml(request):
    public_pages = ('core:home', 'core:privacy', 'core:terms')
    locations = ''.join(
        f'<url><loc>{escape(request.build_absolute_uri(reverse(name)))}</loc></url>'
        for name in public_pages
    )
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f'{locations}'
        '</urlset>'
    )
    return HttpResponse(content, content_type='application/xml; charset=utf-8')


def custom_404(request, exception=None):
    return render(request, '404.html', status=404)
