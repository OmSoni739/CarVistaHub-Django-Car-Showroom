"""
Razorpay Payment Gateway & Stock-Safe Transaction Service.
Encapsulates Razorpay Python SDK client initialization, order creation,
cryptographic HMAC-SHA256 signature verification, server-side capture validation,
and atomic stock management.
"""

import logging
from decimal import Decimal
import uuid
import razorpay
from django.conf import settings
from django.db import transaction, models
from django.utils import timezone

from apps.accounts.models import User
from apps.cars.models import Car
from apps.bookings.models import CarBooking, CustomerNotification
from apps.payments.models import Payment

logger = logging.getLogger(__name__)


class PaymentServiceError(Exception):
    """Base exception for payment service operations."""
    pass


class RazorpayConfigError(PaymentServiceError):
    """Raised when Razorpay credentials are missing or invalid in configuration."""
    pass


class StockUnavailableError(PaymentServiceError):
    """Raised when vehicle stock is exhausted or unavailable."""
    pass


class PaymentOwnershipError(PaymentServiceError):
    """Raised when an authenticated user attempts to access or verify another customer's payment."""
    pass


class PaymentVerificationError(PaymentServiceError):
    """Raised when cryptographic signature or gateway payment verification fails."""
    pass


def get_razorpay_client():
    """
    Initializes and returns the official Razorpay Python SDK client instance.
    Reads credentials strictly from Django settings and raises RazorpayConfigError if missing.
    Never exposes or logs secret credentials.
    """
    key_id = getattr(settings, 'RAZORPAY_KEY_ID', None)
    key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', None)
    if not key_id or not key_secret:
        raise RazorpayConfigError(
            "Razorpay API credentials (RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET) are missing or not configured."
        )
    return razorpay.Client(auth=(key_id, key_secret))


def initiate_car_booking_order(customer, car):
    """
    Step 1: Pre-order validation and Razorpay Order creation.

    Mandatory Rules:
    1. Verifies car.is_available=True and car.stock_quantity > 0.
    2. Does NOT deduct stock. Stock remains untouched.
    3. Converts car.booking_amount (₹) to integer paise using Decimal arithmetic.
    4. Handles existing pending bookings and payment retries safely.
    5. Prevents duplicate Payment records on OneToOneField.
    6. Calls Razorpay API before DB write; if gateway fails, leaves no orphan records.
    7. Creates/updates CarBooking (status: PENDING) and Payment (status: PENDING) in an atomic block.
    8. Returns safe public dictionary.
    """
    # 1. Authoritative server-side stock and availability check
    if not car.is_available or car.stock_quantity <= 0:
        raise StockUnavailableError(
            f"Vehicle '{car.title}' is currently out of stock or unavailable for reservation."
        )

    # 2. Currency conversion: rupees to paise using Decimal arithmetic
    amount_inr = car.booking_amount
    amount_paise = int(amount_inr * Decimal('100'))

    # 3. Locate existing pending or failed booking for safe retry without duplicates
    existing_booking = CarBooking.objects.filter(
        customer=customer,
        car=car,
        payment_status__in=[CarBooking.PaymentStatus.PENDING, CarBooking.PaymentStatus.FAILED],
        booking_status=CarBooking.BookingStatus.PENDING
    ).order_by('-created_at').first()

    receipt_id = existing_booking.booking_id if existing_booking else f"BK-{uuid.uuid4().hex[:8].upper()}"

    # 4. Initialize client and create Razorpay Order
    client = get_razorpay_client()
    order_payload = {
        'amount': amount_paise,
        'currency': 'INR',
        'receipt': receipt_id,
        'notes': {
            'booking_id': receipt_id,
            'car_id': str(car.id),
            'car_title': car.title,
            'customer_username': customer.username,
            'customer_email': customer.email,
        }
    }

    try:
        razorpay_order = client.order.create(data=order_payload)
    except Exception as exc:
        logger.error("Razorpay order creation failed for Car ID %s: %s", car.id, str(exc))
        raise PaymentServiceError(f"Payment gateway error while creating order: {str(exc)}")

    razorpay_order_id = razorpay_order.get('id')
    if not razorpay_order_id:
        raise PaymentServiceError("Gateway response did not contain a valid Razorpay Order ID.")

    # 5. Atomic database persistence after confirmed Razorpay order creation
    with transaction.atomic():
        if existing_booking:
            booking = existing_booking
            booking.booking_amount = amount_inr
            booking.payment_status = CarBooking.PaymentStatus.PENDING
            booking.save(update_fields=['booking_amount', 'payment_status'])
        else:
            booking = CarBooking.objects.create(
                booking_id=receipt_id,
                customer=customer,
                car=car,
                booking_amount=amount_inr,
                payment_status=CarBooking.PaymentStatus.PENDING,
                booking_status=CarBooking.BookingStatus.PENDING
            )

        Payment.objects.update_or_create(
            booking=booking,
            defaults={
                'razorpay_order_id': razorpay_order_id,
                'amount': amount_inr,
                'currency': 'INR',
                'payment_status': Payment.PaymentStatus.PENDING,
                'razorpay_payment_id': None,
                'razorpay_signature': None,
                'payment_method': None,
                'paid_at': None,
            }
        )

    logger.info(
        "Initiated Razorpay Order %s for Booking %s (Car: %s, Current Stock: %d)",
        razorpay_order_id, booking.booking_id, car.title, car.stock_quantity
    )

    return {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
        'amount_paise': amount_paise,
        'amount_inr': amount_inr,
        'currency': 'INR',
        'booking_id': booking.booking_id,
        'car_id': car.id,
        'car_title': car.title,
        'car_brand': car.brand.name,
    }


def verify_and_process_car_booking_payment(customer, razorpay_order_id, razorpay_payment_id, razorpay_signature):
    """
    Step 2: Cryptographic Signature Verification, Server-side Capture Confirmation,
    Idempotency Safeguard, and Atomic Stock Management.

    Mandatory Rules:
    1. Locates Payment by order ID.
    2. Validates payment belongs to the authenticated customer.
    3. Idempotency check: if already SUCCESS, returns success without deducting stock.
    4. Cryptographically verifies HMAC-SHA256 signature using official Razorpay SDK.
    5. Fetches payment from Razorpay and confirms:
       - Payment belongs to the same order.
       - Amount matches stored payment amount in paise.
       - Currency is INR.
       - Status is reported as 'captured'.
    6. Inside transaction.atomic():
       - Locks relevant records where supported (select_for_update).
       - Rechecks stock inside transaction.
       - If stock is 0 or unavailable:
         * Records genuine captured payment as SUCCESS.
         * Sets CarBooking payment status to PAID.
         * Keeps booking status PENDING (not CONFIRMED).
         * Does NOT decrement stock.
         * Creates customer and manager alert notifications.
         * Returns 'out_of_stock' status.
       - Conditional atomic update: decrements stock by exactly 1 where stock_quantity > 0 and is_available = True.
       - If stock reaches 0, sets is_available = False.
       - Sets Payment SUCCESS and CarBooking PAID + CONFIRMED.
    """
    # 1. Locate Payment record by supplied order ID
    payment = (
        Payment.objects
        .select_related('booking', 'booking__car', 'booking__customer')
        .filter(razorpay_order_id=razorpay_order_id)
        .first()
    )
    if not payment:
        raise PaymentVerificationError(f"No payment record found for Razorpay Order ID '{razorpay_order_id}'.")

    # 2. Ownership verification: ensure payment belongs to authenticated customer
    if payment.booking.customer_id != customer.id:
        logger.warning(
            "Unauthorized payment verification attempt: User %s tried to verify payment for Booking %s owned by User %s",
            customer.id, payment.booking.booking_id, payment.booking.customer_id
        )
        raise PaymentOwnershipError("You do not have permission to verify this booking payment.")

    # 3. Idempotency check: prevent duplicate processing or deductions
    if payment.payment_status == Payment.PaymentStatus.SUCCESS:
        logger.info("Payment %s has already been successfully verified and processed.", razorpay_order_id)
        return {
            'status': 'already_processed',
            'booking': payment.booking,
            'payment': payment,
            'message': 'Payment has already been verified and processed.'
        }

    client = get_razorpay_client()

    # 4. Cryptographic signature verification using official SDK
    verify_payload = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_payment_id': razorpay_payment_id,
        'razorpay_signature': razorpay_signature,
    }

    try:
        client.utility.verify_payment_signature(verify_payload)
    except razorpay.errors.SignatureVerificationError as exc:
        logger.warning("Razorpay signature verification failed for Order %s: %s", razorpay_order_id, str(exc))
        # Update records to FAILED without altering stock
        payment.payment_status = Payment.PaymentStatus.FAILED
        payment.razorpay_payment_id = razorpay_payment_id
        payment.razorpay_signature = razorpay_signature
        payment.save(update_fields=['payment_status', 'razorpay_payment_id', 'razorpay_signature'])

        payment.booking.payment_status = CarBooking.PaymentStatus.FAILED
        payment.booking.save(update_fields=['payment_status'])

        raise PaymentVerificationError("Invalid payment signature. Verification failed.")

    # 5. Fetch payment from Razorpay API to confirm capture, amount, currency and order ID
    try:
        rzp_payment = client.payment.fetch(razorpay_payment_id)
    except Exception as exc:
        logger.error("Failed to fetch payment %s from Razorpay: %s", razorpay_payment_id, str(exc))
        raise PaymentVerificationError(f"Unable to confirm payment status with gateway: {str(exc)}")

    # Verify order ID matches
    if rzp_payment.get('order_id') != razorpay_order_id:
        logger.warning(
            "Order ID mismatch: Gateway payment %s linked to order %s, expected %s",
            razorpay_payment_id, rzp_payment.get('order_id'), razorpay_order_id
        )
        raise PaymentVerificationError("Payment does not belong to the requested booking order ID.")

    # Verify amount matches stored payment amount in paise
    expected_paise = int(payment.amount * Decimal('100'))
    if rzp_payment.get('amount') != expected_paise:
        logger.warning(
            "Amount mismatch: Gateway reported %s paise, expected %s paise",
            rzp_payment.get('amount'), expected_paise
        )
        raise PaymentVerificationError("Payment amount mismatch against the vehicle advance booking amount.")

    # Verify currency is INR
    if rzp_payment.get('currency') != 'INR':
        logger.warning("Currency mismatch: Gateway reported %s, expected INR", rzp_payment.get('currency'))
        raise PaymentVerificationError("Payment currency must be INR.")

    # Verify status is captured
    if rzp_payment.get('status') != 'captured':
        logger.warning("Payment %s not captured: Status is '%s'", razorpay_payment_id, rzp_payment.get('status'))
        raise PaymentVerificationError(
            f"Payment is not captured. Current payment status is '{rzp_payment.get('status')}'."
        )

    payment_method = rzp_payment.get('method', '')

    # 6. Atomic Transaction: Concurrency-safe Stock Deduction & Status Updates
    with transaction.atomic():
        # Lock Payment and Car where supported
        payment = (
            Payment.objects
            .select_for_update()
            .select_related('booking', 'booking__car')
            .get(razorpay_order_id=razorpay_order_id)
        )
        booking = payment.booking

        # Secondary idempotency check inside transaction lock
        if payment.payment_status == Payment.PaymentStatus.SUCCESS:
            return {
                'status': 'already_processed',
                'booking': booking,
                'payment': payment,
                'message': 'Payment has already been processed.'
            }

        car = Car.objects.select_for_update().get(id=booking.car_id)

        # Recheck stock availability inside transaction
        if car.stock_quantity <= 0 or not car.is_available:
            return _handle_out_of_stock_captured(
                payment=payment,
                booking=booking,
                car=car,
                razorpay_payment_id=razorpay_payment_id,
                razorpay_signature=razorpay_signature,
                payment_method=payment_method
            )

        # Atomic conditional database update: guarantees safe deduction on SQLite & MySQL
        rows_updated = Car.objects.filter(
            id=car.id,
            stock_quantity__gt=0,
            is_available=True
        ).update(
            stock_quantity=models.F('stock_quantity') - 1,
            updated_at=timezone.now()
        )

        if rows_updated == 0:
            # Concurrent race caught at SQL level
            return _handle_out_of_stock_captured(
                payment=payment,
                booking=booking,
                car=car,
                razorpay_payment_id=razorpay_payment_id,
                razorpay_signature=razorpay_signature,
                payment_method=payment_method
            )

        # Refresh car from DB and auto-disable showroom availability if stock reached 0
        car.refresh_from_db()
        if car.stock_quantity == 0:
            car.is_available = False
            car.save(update_fields=['is_available', 'updated_at'])

        # Mark Payment as SUCCESS
        payment.razorpay_payment_id = razorpay_payment_id
        payment.razorpay_signature = razorpay_signature
        payment.payment_method = payment_method or payment.payment_method or ''
        payment.payment_status = Payment.PaymentStatus.SUCCESS
        payment.paid_at = timezone.now()
        payment.save(update_fields=['razorpay_payment_id', 'razorpay_signature', 'payment_method', 'payment_status', 'paid_at'])

        # Mark CarBooking as PAID and CONFIRMED
        booking.payment_status = CarBooking.PaymentStatus.PAID
        booking.booking_status = CarBooking.BookingStatus.CONFIRMED
        booking.save(update_fields=['payment_status', 'booking_status'])

        # Dispatch customer in-app notification (GENERAL notice to prevent triggering Test Drive appointment modals)
        CustomerNotification.objects.create(
            user=booking.customer,
            notification_type=CustomerNotification.NotificationType.GENERAL,
            title=f"Vehicle Advance Booking Confirmed ({booking.booking_id})",
            message=(
                f"Your advance payment of ₹{payment.amount} for {car.brand.name} {car.title} "
                f"has been confirmed (Transaction ID: {razorpay_payment_id}). "
                f"Showroom operations will contact you regarding delivery scheduling."
            ),
            booking_reference=booking.booking_id,
            car_title=car.title,
        )

        logger.info(
            "Booking %s CONFIRMED. Payment %s SUCCESS. Car '%s' stock deducted by 1. Remaining stock: %d",
            booking.booking_id, razorpay_order_id, car.title, car.stock_quantity
        )

        return {
            'status': 'success',
            'booking': booking,
            'payment': payment,
            'message': 'Advance booking payment confirmed and vehicle reserved successfully.'
        }


def _handle_out_of_stock_captured(payment, booking, car, razorpay_payment_id, razorpay_signature, payment_method):
    """
    Handles race condition when customer payment was captured by Razorpay,
    but stock became 0 before our decrement succeeded.

    Mandatory Rules:
    - Record genuine captured payment as SUCCESS.
    - Set CarBooking payment status to PAID.
    - Keep booking status PENDING (not CONFIRMED).
    - Do NOT decrement stock.
    - Create customer and manager notifications.
    - Return distinct 'out_of_stock' status.
    """
    payment.razorpay_payment_id = razorpay_payment_id
    payment.razorpay_signature = razorpay_signature
    payment.payment_method = payment_method or payment.payment_method or ''
    payment.payment_status = Payment.PaymentStatus.SUCCESS
    payment.paid_at = timezone.now()
    payment.save(update_fields=['razorpay_payment_id', 'razorpay_signature', 'payment_method', 'payment_status', 'paid_at'])

    booking.payment_status = CarBooking.PaymentStatus.PAID
    booking.booking_status = CarBooking.BookingStatus.PENDING  # Held pending stock review
    booking.save(update_fields=['payment_status', 'booking_status'])

    # Customer notification
    CustomerNotification.objects.create(
        user=booking.customer,
        notification_type=CustomerNotification.NotificationType.GENERAL,
        title=f"Vehicle Allocation In Progress ({booking.booking_id})",
        message=(
            f"Your advance payment of ₹{payment.amount} was captured successfully (ID: {razorpay_payment_id}). "
            f"However, vehicle '{car.title}' is currently out of showroom stock. "
            f"Our showroom operations team has been notified for priority inventory allocation or an instant refund upon request."
        ),
        booking_reference=booking.booking_id,
        car_title=car.title,
    )

    # Manager alert notification
    active_manager = User.get_active_manager()
    if active_manager:
        CustomerNotification.objects.create(
            user=active_manager,
            notification_type=CustomerNotification.NotificationType.GENERAL,
            title=f"ACTION REQUIRED: Stock Collision on Paid Booking {booking.booking_id}",
            message=(
                f"Customer {booking.customer.username} ({booking.customer.email}) completed advance payment of ₹{payment.amount} "
                f"for '{car.title}' (Payment ID: {razorpay_payment_id}), but vehicle stock is 0. "
                f"Please arrange priority dealer allocation or issue a refund via Razorpay."
            ),
            booking_reference=booking.booking_id,
            car_title=car.title,
        )

    logger.critical(
        "OUT_OF_STOCK_AFTER_PAYMENT: Booking %s, Car %s, Payment %s. Payment captured but stock unavailable.",
        booking.booking_id, car.id, razorpay_payment_id
    )

    return {
        'status': 'out_of_stock',
        'booking': booking,
        'payment': payment,
        'message': (
            f"Your advance payment of ₹{payment.amount} was captured successfully, but vehicle '{car.title}' "
            f"is currently out of stock. Our showroom team will contact you for priority allocation or full refund."
        )
    }
