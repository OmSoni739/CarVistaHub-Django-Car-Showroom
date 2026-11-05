"""
Razorpay Payment API Views for Car Booking Advance Payments.
Enforces authentication, Customer role verification, server-side pricing authority,
CSRF protection, and secure JSON response contracts.
"""

import json
import logging
from decimal import Decimal
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from apps.accounts.models import User
from apps.cars.models import Car
from apps.bookings.models import CarBooking
from .services import (
    initiate_car_booking_order,
    verify_and_process_car_booking_payment,
    RazorpayConfigError,
    StockUnavailableError,
    PaymentOwnershipError,
    PaymentVerificationError,
    PaymentServiceError,
)

logger = logging.getLogger(__name__)


def _parse_request_payload(request):
    """
    Helper to extract parameters from JSON body or standard form POST data.
    """
    if request.content_type and 'application/json' in request.content_type:
        try:
            return json.loads(request.body.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            return {}
    return request.POST


@login_required(login_url='accounts:login')
@require_POST
def create_booking_payment_order(request):
    """
    POST /payments/api/create-order/

    Generates a secure Razorpay Order for a car advance booking fee.
    Enforces customer authentication, Customer role check, server-side
    stock/availability validation, and server-side pricing lookup.
    """
    # 1. Enforce Customer role strictly
    if getattr(request.user, 'user_type', None) != User.UserType.CUSTOMER:
        return JsonResponse(
            {'error': 'Only customer accounts are permitted to book vehicles.'},
            status=403
        )

    # 2. Extract and validate car_id
    payload = _parse_request_payload(request)
    car_id = payload.get('car_id')

    if not car_id:
        return JsonResponse(
            {'error': 'Missing required parameter: car_id.'},
            status=400
        )

    try:
        car_id = int(car_id)
    except (ValueError, TypeError):
        return JsonResponse(
            {'error': 'Invalid car_id format. Must be an integer.'},
            status=400
        )

    # 3. Fetch car directly from DB (never trust browser-submitted prices)
    try:
        car = Car.objects.select_related('brand').get(pk=car_id)
    except Car.DoesNotExist:
        return JsonResponse(
            {'error': 'Selected vehicle does not exist or has been removed.'},
            status=404
        )

    # 4. Pre-check stock & availability
    if not car.is_available or car.stock_quantity <= 0:
        return JsonResponse(
            {'error': f"'{car.title}' is currently out of stock or unavailable for reservation."},
            status=400
        )

    # 5. Initiate order via payment service
    try:
        order_data = initiate_car_booking_order(customer=request.user, car=car)
    except StockUnavailableError as err:
        return JsonResponse({'error': str(err)}, status=400)
    except RazorpayConfigError as err:
        logger.critical("Razorpay configuration error: %s", str(err))
        return JsonResponse(
            {'error': 'Payment service is temporarily unavailable due to configuration.'},
            status=500
        )
    except PaymentServiceError as err:
        logger.error("Order creation failed: %s", str(err))
        return JsonResponse(
            {'error': 'Unable to initialize payment order with gateway. Please try again.'},
            status=500
        )

    # 6. Return public order payload for Razorpay Standard Checkout modal
    return JsonResponse({
        'success': True,
        'razorpay_order_id': order_data['razorpay_order_id'],
        'razorpay_key_id': order_data['razorpay_key_id'],
        'amount': order_data['amount_paise'],
        'amount_inr': str(order_data['amount_inr']),
        'currency': order_data['currency'],
        'booking_id': order_data['booking_id'],
        'car_id': car.id,
        'car_title': car.title,
        'car_brand': car.brand.name,
        'customer_name': request.user.get_full_name() or request.user.username,
        'customer_email': request.user.email,
        'customer_phone': getattr(request.user, 'phone_number', ''),
    })


@login_required(login_url='accounts:login')
@require_POST
def verify_payment_callback(request):
    """
    POST /payments/api/verify-payment/

    Receives payment credentials from Razorpay Standard Checkout callback,
    validates cryptographic signature, validates server-side capture status,
    and performs concurrency-safe stock deduction.
    """
    # 1. Enforce Customer role
    if getattr(request.user, 'user_type', None) != User.UserType.CUSTOMER:
        return JsonResponse(
            {'error': 'Only customer accounts are permitted to verify booking payments.'},
            status=403
        )

    payload = _parse_request_payload(request)
    razorpay_order_id = payload.get('razorpay_order_id', '').strip()
    razorpay_payment_id = payload.get('razorpay_payment_id', '').strip()
    razorpay_signature = payload.get('razorpay_signature', '').strip()

    if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
        return JsonResponse(
            {'error': 'Missing required verification fields: razorpay_order_id, razorpay_payment_id, and razorpay_signature.'},
            status=400
        )

    # 2. Execute verification and atomic stock processing service
    try:
        result = verify_and_process_car_booking_payment(
            customer=request.user,
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_signature=razorpay_signature
        )
    except PaymentOwnershipError as err:
        return JsonResponse({'error': str(err)}, status=403)
    except PaymentVerificationError as err:
        return JsonResponse({'error': str(err)}, status=400)
    except PaymentServiceError as err:
        logger.error("Payment processing error: %s", str(err))
        return JsonResponse(
            {'error': 'A processing error occurred during payment verification. Please contact support.'},
            status=500
        )

    booking = result['booking']
    payment = result['payment']
    redirect_url = reverse('payments:booking_success', kwargs={'booking_id': booking.booking_id})

    return JsonResponse({
        'success': True,
        'status': result['status'],
        'message': result['message'],
        'booking_id': booking.booking_id,
        'payment_id': payment.razorpay_payment_id,
        'car_id': booking.car_id,
        'payment_status': payment.payment_status,
        'booking_status': booking.booking_status,
        'redirect_url': redirect_url,
    })


@login_required(login_url='accounts:login')
@require_GET
def booking_success_view(request, booking_id):
    """
    GET /payments/success/<booking_id>/

    Renders the official vehicle reservation confirmation receipt.
    Validates ownership server-side: only the customer who booked or staff can view.
    """
    booking = get_object_or_404(
        CarBooking.objects.select_related('car', 'car__brand', 'customer').prefetch_related('car__images'),
        booking_id=booking_id
    )

    if booking.customer_id != request.user.id and not request.user.is_staff:
        return render(request, '404.html', status=403)

    payment = getattr(booking, 'payment', None)
    primary_image = booking.car.images.filter(is_primary=True).first() or booking.car.images.first()

    balance_amount = None
    if booking.car and booking.car.price and booking.booking_amount:
        balance_amount = max(Decimal('0.00'), booking.car.price - booking.booking_amount)

    is_allocation_pending = (
        booking.booking_status == CarBooking.BookingStatus.PENDING and 
        booking.payment_status == CarBooking.PaymentStatus.PAID
    )

    context = {
        'page_title': f'Booking Receipt — {booking.booking_id}',
        'booking': booking,
        'payment': payment,
        'car': booking.car,
        'primary_image': primary_image,
        'balance_amount': balance_amount,
        'is_allocation_pending': is_allocation_pending,
        'customer_unread_notification': None,  # Strictly suppress test drive appointment modals on receipt page
    }
    return render(request, 'payments/booking_success.html', context)


@login_required(login_url='accounts:login')
@require_GET
def booking_status_api(request, booking_id):
    """
    GET /payments/api/booking-status/<booking_id>/

    Returns real-time status of a car advance booking and associated payment.
    Enforces customer ownership or staff permissions.
    """
    booking = get_object_or_404(
        CarBooking.objects.select_related('car', 'car__brand'),
        booking_id=booking_id
    )

    # Ownership check
    if booking.customer_id != request.user.id and not request.user.is_staff:
        return JsonResponse({'error': 'Permission denied.'}, status=403)

    payment = getattr(booking, 'payment', None)

    return JsonResponse({
        'booking_id': booking.booking_id,
        'car_title': booking.car.title,
        'car_brand': booking.car.brand.name,
        'booking_amount': str(booking.booking_amount),
        'booking_status': booking.booking_status,
        'payment_status': booking.payment_status,
        'razorpay_order_id': payment.razorpay_order_id if payment else None,
        'razorpay_payment_id': payment.razorpay_payment_id if payment else None,
        'paid_at': payment.paid_at.isoformat() if payment and payment.paid_at else None,
        'created_at': booking.created_at.isoformat(),
    })

