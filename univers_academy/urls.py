from django.contrib import admin
from django.urls import path, include

# NOTE: MEDIA_URL is intentionally NOT served by Django, even in DEBUG.
# Scholarship documents and expense receipts live under media/private/ and
# must only be reachable through the authenticated serve_private_file view.
urlpatterns = [
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),
    path('', include('core.urls')),
]
