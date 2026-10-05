from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    path('', include('core.urls')),
    path('', include('clinic.urls')),
    path('accounts/', include('accounts.urls')),
    path('inventory/', include('inventory.urls')),
    path('reports/', include('reports.urls')),
    path('django-admin/', admin.site.urls),
    # Uploaded files (center logo). The system runs on a local machine, so
    # Django serves them directly instead of a separate web server.
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

handler403 = 'core.views.permission_denied'
handler404 = 'core.views.page_not_found'
