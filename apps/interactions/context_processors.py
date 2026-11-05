"""
Context processors for CarVistaHub Wishlist.
Exposes the authenticated customer's saved car IDs and total wishlist count.
"""
from .models import Wishlist


def wishlist_data(request):
    """
    Exposes customer's wishlisted car IDs (as a set) and count to all templates.
    Allows car cards in listing, home, and detail views to render the heart state
    without additional database queries.
    Strictly isolated to request.user. Returns empty set and 0 for guests.
    """
    if not request.user.is_authenticated:
        return {
            'user_wishlist_car_ids': set(),
            'wishlist_count': 0,
        }

    car_ids = set(
        Wishlist.objects.filter(user=request.user).values_list('car_id', flat=True)
    )
    return {
        'user_wishlist_car_ids': car_ids,
        'wishlist_count': len(car_ids),
    }

