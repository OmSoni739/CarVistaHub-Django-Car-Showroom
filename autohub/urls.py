"""
AutoHub Project URL Configuration
Project-level routing delegating to the 6 application modules.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# CarVistaHub Django Admin Branding
admin.site.site_header = "CarVistaHub Administration"
admin.site.site_title = "CarVistaHub Admin"
admin.site.index_title = "Welcome to CarVistaHub Administration"

urlpatterns = [
    # Django Admin Interface
    path('admin/', admin.site.urls),
    
    # Core Application Routes
    path('', include('apps.cars.urls')),
    path('accounts/', include('apps.accounts.urls')),
    path('bookings/', include('apps.bookings.urls')),
    path('payments/', include('apps.payments.urls')),
    path('wishlist/', include('apps.interactions.urls')),
    path('dashboard/', include('apps.dashboard.urls')),
]

# Serve media & static files in development mode
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = 'apps.cars.views.custom_404_view'

