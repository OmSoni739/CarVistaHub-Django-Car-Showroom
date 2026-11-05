from django.urls import path
from .views import (
    wishlist_view,
    toggle_wishlist_api,
    remove_wishlist_api,
    wishlist_status_api,
)

app_name = 'interactions'

urlpatterns = [
    # Dedicated Customer Wishlist Page
    path('', wishlist_view, name='wishlist'),
    
    # Wishlist AJAX APIs
    path('api/toggle/', toggle_wishlist_api, name='api_toggle'),
    path('api/remove/<int:car_id>/', remove_wishlist_api, name='api_remove'),
    path('api/status/', wishlist_status_api, name='api_status'),
]
