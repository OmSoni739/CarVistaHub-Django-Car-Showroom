import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.db import transaction

from apps.cars.models import Car
from .models import Wishlist


@login_required(login_url='accounts:login')
def wishlist_view(request):
    """
    Renders the authenticated customer's dedicated Wishlist page.
    Displays all saved cars with full specifications, images, and prices.
    Strictly isolated to the request.user.
    """
    wishlist_items = (
        Wishlist.objects.filter(user=request.user)
        .select_related('car', 'car__brand')
        .prefetch_related('car__images')
        .order_by('-added_at')
    )
    
    return render(request, 'pages/wishlist.html', {
        'wishlist_items': wishlist_items,
        'total_count': wishlist_items.count(),
        'page_title': 'My Wishlist | CarVistaHub',
    })


@require_POST
def toggle_wishlist_api(request):
    """
    AJAX endpoint to add or remove a car from the customer's wishlist.
    Enforces authentication and CSRF protection.
    Returns JSON state update and customer-isolated wishlist count.
    """
    if not request.user.is_authenticated:
        # Determine redirect target from referer or default to car list
        referer = request.META.get('HTTP_REFERER', '')
        login_target = referer if referer else '/cars/'
        return JsonResponse({
            'status': 'unauthenticated',
            'login_url': f'/accounts/login/?next={login_target}',
            'message': 'Please sign in to save vehicles to your wishlist.'
        }, status=401)

    # Extract car_id from POST or JSON body
    car_id = request.POST.get('car_id')
    if not car_id and request.content_type == 'application/json':
        try:
            body_data = json.loads(request.body.decode('utf-8'))
            car_id = body_data.get('car_id')
        except (ValueError, TypeError, UnicodeDecodeError):
            pass

    if not car_id:
        return JsonResponse({
            'status': 'error',
            'message': 'Car ID parameter is required.'
        }, status=400)

    try:
        car = Car.objects.select_related('brand').get(id=car_id, is_available=True)
    except (Car.DoesNotExist, ValueError):
        return JsonResponse({
            'status': 'error',
            'message': 'The requested car is not available.'
        }, status=404)

    with transaction.atomic():
        wishlist_entry = Wishlist.objects.filter(user=request.user, car=car).first()
        if wishlist_entry:
            wishlist_entry.delete()
            action = 'removed'
            is_wishlisted = False
            message = f"{car.brand.name} {car.title} removed from your wishlist."
        else:
            Wishlist.objects.create(user=request.user, car=car)
            action = 'added'
            is_wishlisted = True
            message = f"{car.brand.name} {car.title} added to your wishlist."

        total_count = Wishlist.objects.filter(user=request.user).count()

    return JsonResponse({
        'status': 'success',
        'action': action,
        'is_wishlisted': is_wishlisted,
        'car_id': car.id,
        'car_title': f"{car.brand.name} {car.title}",
        'wishlist_count': total_count,
        'message': message
    })


@require_POST
def remove_wishlist_api(request, car_id):
    """
    Explicit removal API endpoint for removing an item from the Wishlist.
    """
    if not request.user.is_authenticated:
        return JsonResponse({
            'status': 'unauthenticated',
            'message': 'Authentication required.'
        }, status=401)

    car = get_object_or_404(Car, id=car_id)
    with transaction.atomic():
        Wishlist.objects.filter(user=request.user, car=car).delete()
        total_count = Wishlist.objects.filter(user=request.user).count()

    return JsonResponse({
        'status': 'success',
        'action': 'removed',
        'is_wishlisted': False,
        'car_id': car.id,
        'wishlist_count': total_count,
        'message': f"{car.brand.name} {car.title} removed from your wishlist."
    })


@require_GET
def wishlist_status_api(request):
    """
    Returns the list of car IDs currently in the authenticated user's wishlist
    and the total count. Returns empty list for anonymous guests.
    """
    if not request.user.is_authenticated:
        return JsonResponse({
            'status': 'unauthenticated',
            'count': 0,
            'car_ids': []
        })

    car_ids = list(Wishlist.objects.filter(user=request.user).values_list('car_id', flat=True))
    return JsonResponse({
        'status': 'success',
        'count': len(car_ids),
        'car_ids': car_ids
    })
