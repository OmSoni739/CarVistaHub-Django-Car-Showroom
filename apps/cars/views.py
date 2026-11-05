from decimal import Decimal, InvalidOperation
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from .models import Car, Brand
from .templatetags.currency_tags import indian_currency


def home_view(request):
    """
    Home view for CarVistaHub.
    Retrieves featured and available cars from SQLite to populate the Featured New Cars section.
    Also retrieves available brands for the hero search widget.
    """
    featured_cars = Car.objects.filter(
        is_available=True,
        is_featured=True
    ).select_related('brand').prefetch_related('images')
    brands = Brand.objects.all()
    return render(request, 'pages/home.html', {
        'featured_cars': featured_cars,
        'brands': brands,
    })


def car_list_view(request):
    """
    Dynamic Car Listing view for CarVistaHub with search and multi-facet filtering.
    Filters by brand, budget, fuel type, body type, and keyword search.
    Preserves existing query parameter names ('brand', 'budget', 'fuel') and validates all inputs safely.
    """
    cars = Car.objects.filter(is_available=True).select_related('brand').prefetch_related('images')
    brands = Brand.objects.all()

    is_filtered = False
    active_brand_name = None

    # 1. Brand filtering (by slug, name, prefix, or ID)
    brand_param = request.GET.get('brand', '').strip()
    if brand_param:
        brand_q = (
            Q(brand__slug__iexact=brand_param) |
            Q(brand__name__iexact=brand_param) |
            Q(brand__slug__istartswith=brand_param) |
            Q(brand__name__icontains=brand_param)
        )
        if brand_param.isdigit():
            brand_q |= Q(brand__id=int(brand_param))
        cars = cars.filter(brand_q)
        is_filtered = True

        matched_brand = brands.filter(
            Q(slug__iexact=brand_param) | Q(name__iexact=brand_param) | Q(slug__istartswith=brand_param)
        ).first()
        active_brand_name = matched_brand.name if matched_brand else brand_param.title()

    # 2. Budget / price filtering
    budget_param = request.GET.get('budget', '').strip().lower()
    if budget_param:
        if budget_param == 'under-15l':
            cars = cars.filter(price__lte=1500000)
            is_filtered = True
        elif budget_param == '15l-35l':
            cars = cars.filter(price__gte=1500000, price__lte=3500000)
            is_filtered = True
        elif budget_param == '35l-75l':
            cars = cars.filter(price__gte=3500000, price__lte=7500000)
            is_filtered = True
        elif budget_param == 'above-75l':
            cars = cars.filter(price__gt=7500000)
            is_filtered = True
        # If budget_param is an unrecognized string, safely ignore

    # Min/max custom price support
    min_price = request.GET.get('min_price', '').strip()
    max_price = request.GET.get('max_price', '').strip()
    if min_price:
        try:
            val = Decimal(min_price)
            if val >= 0:
                cars = cars.filter(price__gte=val)
                is_filtered = True
        except (InvalidOperation, ValueError):
            pass
    if max_price:
        try:
            val = Decimal(max_price)
            if val >= 0:
                cars = cars.filter(price__lte=val)
                is_filtered = True
        except (InvalidOperation, ValueError):
            pass

    # 3. Fuel type filtering
    fuel_raw = (request.GET.get('fuel') or request.GET.get('fuel_type') or '').strip()
    fuel_param = fuel_raw.upper()
    if fuel_raw:
        valid_fuels = [choice[0] for choice in Car.FuelType.choices]
        if fuel_param in valid_fuels:
            cars = cars.filter(fuel_type=fuel_param)
            is_filtered = True
        else:
            cars = cars.none()
            is_filtered = True

    # 4. Body type filtering
    body_type_raw = request.GET.get('body_type', '').strip()
    body_type_param = body_type_raw.upper()
    if body_type_raw:
        valid_body_types = [choice[0] for choice in Car.BodyType.choices]
        if body_type_param in valid_body_types:
            cars = cars.filter(body_type=body_type_param)
            is_filtered = True
        else:
            cars = cars.none()
            is_filtered = True

    # 5. Keyword search (title, brand name, description)
    q = request.GET.get('q', '').strip()
    if q:
        cars = cars.filter(
            Q(title__icontains=q) |
            Q(brand__name__icontains=q) |
            Q(description__icontains=q)
        )
        is_filtered = True

    context = {
        'cars': cars,
        'brands': brands,
        'selected_brand': brand_param,
        'active_brand_name': active_brand_name,
        'selected_budget': budget_param,
        'selected_fuel': fuel_raw.lower(),
        'selected_body_type': body_type_param,
        'search_query': q,
        'is_filtered': is_filtered,
        'body_type_choices': Car.BodyType.choices,
        'fuel_choices': Car.FuelType.choices,
    }
    return render(request, 'pages/car_list.html', context)


def car_detail_view(request, slug):
    """
    Detailed showroom profile view for an individual Car.
    Retrieves the car by slug, eager-loading brand, images, and feature mappings.
    Handles unknown car slugs with Http404.
    """
    car = get_object_or_404(
        Car.objects.select_related('brand').prefetch_related('images', 'feature_mappings__feature'),
        slug=slug
    )

    # Similar / recommended cars (from same brand or body type)
    similar_cars = Car.objects.filter(
        is_available=True
    ).exclude(
        id=car.id
    ).filter(
        Q(brand=car.brand) | Q(body_type=car.body_type)
    ).select_related('brand').prefetch_related('images')[:3]

    return render(request, 'pages/car_detail.html', {
        'car': car,
        'similar_cars': similar_cars,
    })


def custom_404_view(request, exception=None):
    """
    Site-wide 404 handler rendering a CarVistaHub branded error page.
    """
    return render(request, '404.html', status=404)


# ==============================================================================
# Compare Cars Feature Views & APIs
# ==============================================================================

def _build_car_summary(car, min_price=None, prices_count=1):
    """
    Helper to serialize a single car into a clean summary dictionary for compare slots and modal.
    """
    primary_img = car.images.filter(is_primary=True).first() or car.images.first()
    is_lowest = False
    if min_price is not None and prices_count > 1 and car.price == min_price:
        is_lowest = True

    return {
        'id': car.id,
        'slug': car.slug,
        'title': car.title,
        'brand_name': car.brand.name,
        'price': str(car.price),
        'formatted_price': f"₹{indian_currency(car.price)}",
        'booking_amount': str(car.booking_amount),
        'formatted_booking_amount': f"₹{indian_currency(car.booking_amount)}",
        'is_lowest_price': is_lowest,
        'image_url': primary_img.image.url if primary_img else '',
        'body_type': car.get_body_type_display(),
        'fuel_type': car.get_fuel_type_display(),
        'transmission': car.get_transmission_display(),
        'is_available': car.is_available,
        'stock_quantity': car.stock_quantity,
        'stock_status': f"In Stock ({car.stock_quantity} Unit{'s' if car.stock_quantity != 1 else ''})" if car.is_available and car.stock_quantity > 0 else "Currently Unavailable",
        'detail_url': reverse('cars:car_detail', kwargs={'slug': car.slug}),
    }


def _build_comparison_payload(ordered_cars):
    """
    Builds the full side-by-side comparison payload conforming to 6 standardized categories:
    1. Price & Overview
    2. Engine & Performance
    3. Fuel & Transmission
    4. Dimensions & Capacity
    5. Safety
    6. Entertainment & Communication
    """
    prices = [c.price for c in ordered_cars]
    min_price = min(prices)
    distinct_prices_count = len(set(prices))

    car_summaries = [
        _build_car_summary(c, min_price=min_price, prices_count=distinct_prices_count)
        for c in ordered_cars
    ]

    def make_field(label, values, is_price=False):
        normalized = [str(v).strip().lower() for v in values if str(v).strip() not in ('', '—', 'not available', 'none', 'unknown')]
        is_diff = len(set(normalized)) > 1 if normalized else False
        return {
            'label': label,
            'values': values,
            'is_different': is_diff,
            'is_price': is_price,
        }

    # Map pre-loaded feature mappings into a fast lookup: car_id -> {feature_name: is_available}
    car_feature_status = {}
    for c in ordered_cars:
        car_feature_status[c.id] = {
            m.feature.name: m.is_available for m in c.feature_mappings.all()
        }

    def get_feature_val(car, feat_name):
        mapping = car_feature_status.get(car.id, {})
        if feat_name in mapping:
            return 'Yes' if mapping[feat_name] else 'No'
        return '—'

    groups = [
        {
            'name': '1. Price & Overview',
            'fields': [
                make_field('Brand', [c.brand.name for c in ordered_cars]),
                make_field('Model', [c.title for c in ordered_cars]),
                make_field('Ex-Showroom Price', [f"₹{indian_currency(c.price)}" for c in ordered_cars], is_price=True),
                make_field('Advance Booking Fee', [f"₹{indian_currency(c.booking_amount)}" for c in ordered_cars]),
                make_field('Body Type', [c.get_body_type_display() for c in ordered_cars]),
                make_field('Availability', [
                    f"In Stock ({c.stock_quantity} Unit{'s' if c.stock_quantity != 1 else ''})" if c.is_available and c.stock_quantity > 0 else "Currently Unavailable"
                    for c in ordered_cars
                ]),
            ]
        },
        {
            'name': '2. Engine & Performance',
            'fields': [
                make_field('Engine / Motor Specs', [c.engine_capacity or '—' for c in ordered_cars]),
                make_field('Maximum Power', [c.power or '—' for c in ordered_cars]),
                make_field('Maximum Torque', [c.torque or '—' for c in ordered_cars]),
                make_field('Mileage / Driving Range', [c.mileage or '—' for c in ordered_cars]),
            ]
        },
        {
            'name': '3. Fuel & Transmission',
            'fields': [
                make_field('Fuel Type', [c.get_fuel_type_display() for c in ordered_cars]),
                make_field('Transmission', [c.get_transmission_display() for c in ordered_cars]),
            ]
        },
        {
            'name': '4. Dimensions & Capacity',
            'fields': [
                make_field('Length', [f"{c.length} mm" if c.length else '—' for c in ordered_cars]),
                make_field('Width', [f"{c.width} mm" if c.width else '—' for c in ordered_cars]),
                make_field('Height', [f"{c.height} mm" if c.height else '—' for c in ordered_cars]),
                make_field('Wheelbase', [f"{c.wheelbase} mm" if c.wheelbase else '—' for c in ordered_cars]),
                make_field('Ground Clearance', [f"{c.ground_clearance} mm" if c.ground_clearance else '—' for c in ordered_cars]),
                make_field('Seating Capacity', [f"{c.seating_capacity} Persons" if c.seating_capacity else '—' for c in ordered_cars]),
                make_field('Boot Space', [f"{c.boot_space} Litres" if c.boot_space else '—' for c in ordered_cars]),
            ]
        },
        {
            'name': '5. Safety',
            'fields': [
                make_field('Number of Airbags', [str(c.airbag_count) if c.airbag_count is not None else '—' for c in ordered_cars]),
                make_field('Driver Airbag', [get_feature_val(c, 'Driver Airbag') for c in ordered_cars]),
                make_field('Passenger Airbag', [get_feature_val(c, 'Passenger Airbag') for c in ordered_cars]),
                make_field('Front Side Airbags', [get_feature_val(c, 'Front Side Airbags') for c in ordered_cars]),
                make_field('Curtain Airbags', [get_feature_val(c, 'Curtain Airbags') for c in ordered_cars]),
                make_field('Driver Knee Airbag', [get_feature_val(c, 'Driver Knee Airbag') for c in ordered_cars]),
                make_field('Anti-lock Braking System (ABS)', [get_feature_val(c, 'Anti-lock Braking System (ABS)') for c in ordered_cars]),
                make_field('Central Locking', [get_feature_val(c, 'Central Locking') for c in ordered_cars]),
                make_field('Child Safety Locks', [get_feature_val(c, 'Child Safety Locks') for c in ordered_cars]),
                make_field('Anti-theft Alarm', [get_feature_val(c, 'Anti-theft Alarm') for c in ordered_cars]),
                make_field('Electronic Stability Control (ESC)', [get_feature_val(c, 'Electronic Stability Control (ESC)') for c in ordered_cars]),
                make_field('Rear Parking Sensors', [get_feature_val(c, 'Rear Parking Sensors') for c in ordered_cars]),
                make_field('Rear Parking Camera', [get_feature_val(c, 'Rear Parking Camera') for c in ordered_cars]),
                make_field('360-degree Camera', [get_feature_val(c, '360-degree Camera') for c in ordered_cars]),
                make_field('Hill Assist', [get_feature_val(c, 'Hill Assist') for c in ordered_cars]),
                make_field('Advanced Driver Assistance Systems (ADAS)', [get_feature_val(c, 'Advanced Driver Assistance Systems (ADAS)') for c in ordered_cars]),
            ]
        },
        {
            'name': '6. Entertainment & Communication',
            'fields': [
                make_field('Touchscreen Display', [get_feature_val(c, 'Touchscreen Display') for c in ordered_cars]),
                make_field('Touchscreen Size', [f"{str(c.touchscreen_size).rstrip('0').rstrip('.')} inches" if c.touchscreen_size else '—' for c in ordered_cars]),
                make_field('Number of Speakers', [f"{c.speaker_count} Speakers" if c.speaker_count else '—' for c in ordered_cars]),
                make_field('USB Ports', [f"{c.usb_port_count} Ports ({c.usb_details})" if c.usb_port_count and c.usb_details else (f"{c.usb_port_count} Ports" if c.usb_port_count else '—') for c in ordered_cars]),
                make_field('Wireless Phone Charging', [get_feature_val(c, 'Wireless Phone Charging') for c in ordered_cars]),
                make_field('Bluetooth Connectivity', [get_feature_val(c, 'Bluetooth Connectivity') for c in ordered_cars]),
                make_field('Radio', [get_feature_val(c, 'Radio') for c in ordered_cars]),
            ]
        },
    ]

    return {
        'status': 'success',
        'cars': car_summaries,
        'groups': groups
    }


def compare_view(request):
    """
    Public Compare Cars page allowing guests and authenticated users to
    select and compare 2 or 3 cars side-by-side.
    """
    raw_cars = request.GET.getlist('cars') or request.GET.getlist('car')
    if len(raw_cars) == 1 and ',' in raw_cars[0]:
        raw_cars = [x.strip() for x in raw_cars[0].split(',') if x.strip()]

    initial_cars = []
    initial_car_ids = []
    if raw_cars:
        cleaned = list(dict.fromkeys(raw_cars))[:3]
        q = Q()
        numeric = [int(x) for x in cleaned if x.isdigit()]
        slugs = [x for x in cleaned if not x.isdigit()]
        if numeric:
            q |= Q(id__in=numeric)
        if slugs:
            q |= Q(slug__in=slugs)
        found = list(Car.objects.filter(q).select_related('brand').prefetch_related('images'))
        lookup = {str(c.id): c for c in found}
        lookup.update({c.slug: c for c in found})
        for item in cleaned:
            c = lookup.get(item)
            if c and c.id not in [x.id for x in initial_cars]:
                initial_cars.append(c)
                initial_car_ids.append(c.id)

    return render(request, 'pages/compare.html', {
        'initial_cars': initial_cars,
        'initial_car_ids': initial_car_ids,
    })


def api_compare_search(request):
    """
    Searchable car endpoint for the Compare selection modal.
    Returns available cars matching keyword 'q' (title or brand name).
    If 'q' is empty, returns all available cars.
    """
    q = request.GET.get('q', '').strip()
    cars_qs = Car.objects.filter(is_available=True).select_related('brand').prefetch_related('images')

    if q:
        cars_qs = cars_qs.filter(
            Q(title__icontains=q) |
            Q(brand__name__icontains=q) |
            Q(slug__iexact=q)
        )

    cars_qs = cars_qs.order_by('-is_featured', 'brand__name', 'title')

    results = []
    for car in cars_qs:
        results.append(_build_car_summary(car))

    return JsonResponse({
        'status': 'success',
        'count': len(results),
        'cars': results
    })


def api_compare_details(request):
    """
    Validates selected car IDs/slugs and returns full side-by-side comparison payload.
    Supports comparing 2 or 3 cars.
    """
    raw_identifiers = (
        request.GET.getlist('ids') or
        request.GET.getlist('id') or
        request.GET.getlist('car') or
        request.GET.getlist('cars')
    )
    if len(raw_identifiers) == 1 and ',' in raw_identifiers[0]:
        raw_identifiers = [item.strip() for item in raw_identifiers[0].split(',') if item.strip()]

    unique_identifiers = list(dict.fromkeys(item.strip() for item in raw_identifiers if item.strip()))[:3]

    numeric_ids = [int(x) for x in unique_identifiers if x.isdigit()]
    slug_ids = [x for x in unique_identifiers if not x.isdigit()]

    query = Q()
    if numeric_ids:
        query |= Q(id__in=numeric_ids)
    if slug_ids:
        query |= Q(slug__in=slug_ids)

    if not query:
        return JsonResponse({
            'status': 'error',
            'message': 'Please select at least two different cars to compare.',
            'cars': [],
            'groups': []
        }, status=400)

    cars = list(Car.objects.filter(query).select_related('brand').prefetch_related('images', 'feature_mappings__feature', 'spec_sources'))
    lookup = {}
    for c in cars:
        lookup[str(c.id)] = c
        lookup[c.slug] = c

    ordered_cars = []
    seen = set()
    for item in unique_identifiers:
        c = lookup.get(item)
        if c and c.id not in seen:
            seen.add(c.id)
            ordered_cars.append(c)

    if len(ordered_cars) < 2:
        return JsonResponse({
            'status': 'error',
            'message': 'Please select at least two different valid cars to compare.',
            'cars': [],
            'groups': []
        }, status=400)

    payload = _build_comparison_payload(ordered_cars)
    return JsonResponse(payload)


