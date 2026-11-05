"""
Views for CarVistaHub Customer & Manager Dashboards (Phase 2 & Phase 3).
Provides the Manager Showroom Calendar and Audit Records views with role-based access restrictions.
"""

import datetime
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.models import TestDriveBooking, CarBooking, BookingActivity, CustomerNotification
from apps.bookings.services import is_manager, expire_stale_pending_reservations
from apps.payments.models import Payment


@login_required(login_url='accounts:login')
def manager_calendar_view(request):
    """
    Manager Showroom Calendar View.
    Strictly restricted to the active Showroom Manager (user_type == 'MANAGER').
    Administrators and ordinary customers receive a 403 Forbidden.
    """
    if not is_manager(request.user):
        raise PermissionDenied("Only authorized Showroom Managers can access the Showroom Manager Calendar.")

    active_manager = User.get_active_manager()
    today = timezone.localdate()

    context = {
        'page_title': 'Showroom Calendar & Test Drive Availability',
        'active_manager': active_manager,
        'today': today.isoformat(),
        'is_manager': True,
        'is_admin': False,
    }
    return render(request, 'dashboard/manager_calendar.html', context)


@login_required(login_url='accounts:login')
def manager_records_view(request):
    """
    Manager Test Drive Records & Audit Logs View.
    Maintains a complete chronological history of all customer test-drive requests
    and showroom Manager actions with dynamic summary cards, filters, and timeline inspection.
    Strictly restricted to authorized Showroom Managers and Administrators.
    """
    if not is_manager(request.user) and not request.user.is_staff and not request.user.is_superuser:
        raise PermissionDenied("Only authorized Showroom Managers can access Test Drive Records & Audit Logs.")

    # Execute system expiry process to keep logs up to date
    expire_stale_pending_reservations()

    # 1. Dynamically calculated summary counts from actual database records
    total_activities = BookingActivity.objects.count()
    total_requests = TestDriveBooking.objects.count()
    confirmed_bookings = TestDriveBooking.objects.filter(status=TestDriveBooking.Status.CONFIRMED).count()
    rejected_bookings = TestDriveBooking.objects.filter(status=TestDriveBooking.Status.REJECTED).count()
    cancelled_bookings = TestDriveBooking.objects.filter(status=TestDriveBooking.Status.CANCELLED).count()
    completed_test_drives = TestDriveBooking.objects.filter(status=TestDriveBooking.Status.COMPLETED).count()

    summary_stats = {
        'total_activities': total_activities,
        'total_requests': total_requests,
        'confirmed_bookings': confirmed_bookings,
        'rejected_bookings': rejected_bookings,
        'cancelled_bookings': cancelled_bookings,
        'completed_test_drives': completed_test_drives,
    }

    # 2. Base Queryset for Audit Logs
    activities = BookingActivity.objects.select_related(
        'booking',
        'booking__customer',
        'booking__car',
        'booking__car__brand',
        'actor',
    ).order_by('-created_at', '-id')

    # 3. Filters
    search_query = request.GET.get('q', '').strip()
    if search_query:
        activities = activities.filter(
            Q(booking__booking_number__icontains=search_query) |
            Q(booking__customer__username__icontains=search_query) |
            Q(booking__customer__first_name__icontains=search_query) |
            Q(booking__customer__last_name__icontains=search_query) |
            Q(booking__customer__email__icontains=search_query) |
            Q(booking__car__title__icontains=search_query) |
            Q(booking__car__brand__name__icontains=search_query) |
            Q(notes__icontains=search_query)
        )

    activity_type = request.GET.get('activity_type', '').strip()
    if activity_type:
        if activity_type == 'LICENSE_VERIFIED':
            activities = activities.filter(
                Q(action=BookingActivity.Action.LICENSE_VERIFIED) |
                (Q(action=BookingActivity.Action.NOTE_ADDED) & Q(notes__icontains='verified'))
            )
        elif activity_type == 'LICENSE_REJECTED':
            activities = activities.filter(
                Q(action=BookingActivity.Action.LICENSE_REJECTED) |
                (Q(action=BookingActivity.Action.REJECTED) & (Q(notes__icontains='document') | Q(notes__icontains='licence'))) |
                (Q(action=BookingActivity.Action.NOTE_ADDED) & Q(notes__icontains='rejected'))
            )
        elif activity_type in ('TEST_DRIVE_REQUESTED', BookingActivity.Action.REQUEST_SUBMITTED):
            activities = activities.filter(action__in=[BookingActivity.Action.REQUEST_SUBMITTED, 'TEST_DRIVE_REQUESTED'])
        elif activity_type in ('TEST_DRIVE_CONFIRMED', BookingActivity.Action.CONFIRMED):
            activities = activities.filter(action__in=[BookingActivity.Action.CONFIRMED, 'TEST_DRIVE_CONFIRMED'])
        elif activity_type in ('TEST_DRIVE_CANCELLED', BookingActivity.Action.CANCELLED):
            activities = activities.filter(action__in=[BookingActivity.Action.CANCELLED, 'TEST_DRIVE_CANCELLED'])
        elif activity_type in ('TEST_DRIVE_COMPLETED', BookingActivity.Action.COMPLETED):
            activities = activities.filter(action__in=[BookingActivity.Action.COMPLETED, 'TEST_DRIVE_COMPLETED'])
        elif activity_type in ('TEST_DRIVE_REJECTED',):
            activities = activities.filter(action__in=[BookingActivity.Action.REJECTED, 'TEST_DRIVE_REJECTED'])
        elif activity_type in ('BOOKING_EXPIRED', BookingActivity.Action.EXPIRED):
            activities = activities.filter(action__in=[BookingActivity.Action.EXPIRED, 'BOOKING_EXPIRED'])
        elif activity_type == BookingActivity.Action.SLOT_RESERVATION_RELEASED:
            activities = activities.filter(
                Q(action=BookingActivity.Action.SLOT_RESERVATION_RELEASED) |
                Q(notes__icontains='slot released')
            )
        else:
            activities = activities.filter(action=activity_type)

    booking_status = request.GET.get('booking_status', '').strip()
    if booking_status:
        activities = activities.filter(booking__status=booking_status)

    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    if date_from:
        try:
            d_from = datetime.date.fromisoformat(date_from)
            activities = activities.filter(created_at__date__gte=d_from)
        except ValueError:
            pass
    if date_to:
        try:
            d_to = datetime.date.fromisoformat(date_to)
            activities = activities.filter(created_at__date__lte=d_to)
        except ValueError:
            pass

    actor_filter = request.GET.get('actor', '').strip()
    if actor_filter == 'system':
        activities = activities.filter(actor__isnull=True)
    elif actor_filter == 'manager':
        activities = activities.filter(actor__user_type='MANAGER')
    elif actor_filter == 'customer':
        activities = activities.filter(actor__user_type='CUSTOMER')

    # 4. Pagination (15 activities per page)
    paginator = Paginator(activities, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Clean query string for pagination links
    params = request.GET.copy()
    if 'page' in params:
        del params['page']
    filter_querystring = params.urlencode()

    active_manager = User.get_active_manager()

    context = {
        'page_title': 'Test Drive Records & Audit Logs',
        'subtitle': 'Complete history of customer test-drive requests and showroom Manager actions.',
        'summary_stats': summary_stats,
        'page_obj': page_obj,
        'activities': page_obj.object_list,
        'filter_querystring': filter_querystring,
        'current_filters': {
            'q': search_query,
            'activity_type': activity_type,
            'booking_status': booking_status,
            'date_from': date_from,
            'date_to': date_to,
            'actor': actor_filter,
        },
        'booking_status_choices': TestDriveBooking.Status.choices,
        'active_manager': active_manager,
    }
    return render(request, 'dashboard/manager_records.html', context)


@login_required(login_url='accounts:login')
def manager_booking_timeline_api(request, booking_id):
    """
    JSON API providing the complete chronological activity timeline
    for a specific booking reference. Strictly manager-only.
    """
    if not is_manager(request.user) and not request.user.is_staff and not request.user.is_superuser:
        return JsonResponse({'error': 'Access denied. Showroom Manager authorization required.'}, status=403)

    booking = get_object_or_404(
        TestDriveBooking.objects.select_related('customer', 'car', 'car__brand', 'assigned_manager'),
        pk=booking_id
    )

    activities = booking.activities.select_related('actor').order_by('created_at', 'id')

    car_name = f"{booking.car.brand.name} {booking.car.title}" if getattr(booking.car, 'brand', None) else booking.car.title
    slot_time_str = f"{booking.start_time.strftime('%H:%M')} - {booking.end_time.strftime('%H:%M')}" if booking.start_time and booking.end_time else booking.time_slot

    timeline_data = []
    for act in activities:
        timeline_data.append({
            'id': act.id,
            'action': act.action,
            'action_label': act.activity_type_label,
            'badge_class': act.badge_class,
            'icon': act.timeline_icon,
            'actor_name': act.actor_display_name,
            'actor_role': act.actor_role,
            'notes': act.notes,
            'previous_status': act.display_previous_status,
            'new_status': act.display_new_status,
            'timestamp': act.created_at.strftime('%d %b %Y, %I:%M %p'),
            'timestamp_iso': act.created_at.isoformat(),
        })

    return JsonResponse({
        'success': True,
        'booking': {
            'id': booking.id,
            'booking_number': booking.booking_number,
            'customer_name': booking.customer.get_full_name() or booking.customer.username,
            'customer_email': booking.customer.email,
            'customer_phone': booking.contact_phone or getattr(booking.customer, 'phone_number', '') or 'Not provided',
            'car_title': car_name,
            'preferred_date': booking.preferred_date.strftime('%d %b %Y'),
            'slot_time': slot_time_str,
            'showroom_location': 'CarVistaHub Showroom',
            'status': booking.status,
            'status_display': booking.get_status_display(),
            'license_status': booking.license_verification_status,
            'license_display': booking.get_license_verification_status_display(),
            'rejection_reason': booking.rejection_reason or '',
            'cancellation_reason': booking.cancellation_reason or '',
            'created_at': booking.created_at.strftime('%d %b %Y, %I:%M %p') if booking.created_at else '—',
            'confirmed_at': booking.confirmed_at.strftime('%d %b %Y, %I:%M %p') if booking.confirmed_at else '—',
            'completed_at': booking.completed_at.strftime('%d %b %Y, %I:%M %p') if booking.completed_at else '—',
            'cancelled_at': booking.cancelled_at.strftime('%d %b %Y, %I:%M %p') if booking.cancelled_at else '—',
            'rejected_at': booking.rejected_at.strftime('%d %b %Y, %I:%M %p') if booking.rejected_at else '—',
        },
        'timeline': timeline_data
    })


@login_required(login_url='accounts:login')
@require_GET
def manager_vehicle_reservations_view(request):
    """
    Manager Vehicle Reservation Records View (Strictly Read-Only).
    Allows the authorized Showroom Manager to view, search, filter, and inspect
    all customer online vehicle advance reservations and Razorpay payment records.
    Strictly restricted to the active Showroom Manager.
    Strictly read-only: no reservation editing, allocation mutation, or payment status mutation actions.
    """
    if not is_manager(request.user):
        raise PermissionDenied("Only authorized Showroom Managers can access Manager Vehicle Reservation Records.")

    # 1. Base queryset with eager joins
    reservations = CarBooking.objects.select_related(
        'car', 'car__brand', 'customer', 'payment'
    ).prefetch_related('car__images').order_by('-created_at')

    # 2. Dynamically calculated summary counts from actual database records
    total_count = reservations.count()
    confirmed_count = CarBooking.objects.filter(booking_status=CarBooking.BookingStatus.CONFIRMED).count()
    pending_alloc_count = CarBooking.objects.filter(
        booking_status=CarBooking.BookingStatus.PENDING,
        payment_status=CarBooking.PaymentStatus.PAID
    ).count()
    pending_payment_count = CarBooking.objects.filter(payment_status=CarBooking.PaymentStatus.PENDING).count()
    cancelled_count = CarBooking.objects.filter(booking_status=CarBooking.BookingStatus.CANCELLED).count()

    total_advance_collected = Payment.objects.filter(
        payment_status=Payment.PaymentStatus.SUCCESS
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    summary_stats = {
        'total_reservations': total_count,
        'confirmed_reservations': confirmed_count,
        'pending_allocations': pending_alloc_count,
        'pending_payments': pending_payment_count,
        'cancelled_reservations': cancelled_count,
        'total_advance_collected': total_advance_collected,
    }

    # 3. Search query filter
    search_query = request.GET.get('q', '').strip()
    if search_query:
        reservations = reservations.filter(
            Q(booking_id__icontains=search_query) |
            Q(customer__first_name__icontains=search_query) |
            Q(customer__last_name__icontains=search_query) |
            Q(customer__username__icontains=search_query) |
            Q(customer__email__icontains=search_query) |
            Q(customer__phone_number__icontains=search_query) |
            Q(car__title__icontains=search_query) |
            Q(car__brand__name__icontains=search_query) |
            Q(payment__razorpay_order_id__icontains=search_query) |
            Q(payment__razorpay_payment_id__icontains=search_query)
        )

    # 4. Filter by Payment Status
    payment_status = request.GET.get('payment_status', '').strip()
    if payment_status:
        reservations = reservations.filter(payment_status=payment_status)

    # 5. Filter by Booking Status
    booking_status = request.GET.get('booking_status', '').strip()
    if booking_status:
        reservations = reservations.filter(booking_status=booking_status)

    # 6. Filter by Date range
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    if date_from:
        try:
            d_from = datetime.date.fromisoformat(date_from)
            reservations = reservations.filter(created_at__date__gte=d_from)
        except ValueError:
            pass
    if date_to:
        try:
            d_to = datetime.date.fromisoformat(date_to)
            reservations = reservations.filter(created_at__date__lte=d_to)
        except ValueError:
            pass

    # 7. Pagination (15 reservations per page)
    paginator = Paginator(reservations, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Clean query string for pagination links
    params = request.GET.copy()
    if 'page' in params:
        del params['page']
    filter_querystring = params.urlencode()

    active_manager = User.get_active_manager()

    context = {
        'page_title': 'Vehicle Reservation Records | Manager Portal',
        'subtitle': 'Read-only audit register of all online car reservations and verified Razorpay advance payments.',
        'summary_stats': summary_stats,
        'page_obj': page_obj,
        'reservations': page_obj.object_list,
        'filter_querystring': filter_querystring,
        'current_filters': {
            'q': search_query,
            'payment_status': payment_status,
            'booking_status': booking_status,
            'date_from': date_from,
            'date_to': date_to,
        },
        'payment_status_choices': CarBooking.PaymentStatus.choices,
        'booking_status_choices': CarBooking.BookingStatus.choices,
        'active_manager': active_manager,
    }
    return render(request, 'dashboard/manager_vehicle_reservations.html', context)


@login_required(login_url='accounts:login')
def vehicle_reservations_view(request):
    """
    Customer Vehicle Reservations View.
    Displays only CarBooking records (advance payments, reservation status, receipts)
    belonging to the authenticated customer. Strictly isolated to the customer.
    """
    car_bookings = CarBooking.objects.filter(
        customer=request.user
    ).select_related('car', 'car__brand', 'payment').prefetch_related('car__images').order_by('-created_at')

    context = {
        'page_title': 'My Vehicle Reservations | CarVistaHub',
        'car_bookings': car_bookings,
        'customer_unread_notification': None,  # Suppress test drive popups on vehicle reservation page
    }
    return render(request, 'dashboard/vehicle_reservations.html', context)


@login_required(login_url='accounts:login')
def test_drive_appointments_view(request):
    """
    Customer Test Drive Appointments View.
    Displays only TestDriveBooking records (appointment dates/times, licence verification status,
    confirmation status, manager rejection reasons) belonging to the authenticated customer.
    """
    bookings = TestDriveBooking.objects.filter(
        customer=request.user
    ).select_related('car', 'car__brand').order_by('-created_at')

    # Automatically mark unread test drive notifications as read when customer views their appointment history
    CustomerNotification.objects.filter(
        user=request.user,
        is_read=False
    ).update(is_read=True, read_at=timezone.now())

    context = {
        'page_title': 'My Test Drive Appointments | CarVistaHub',
        'bookings': bookings,
    }
    return render(request, 'dashboard/test_drive_appointments.html', context)


@login_required(login_url='accounts:login')
def customer_bookings_view(request):
    """
    Backward-compatible alias for Test Drive Appointments View.
    Maintains compatibility with existing tests and legacy links.
    """
    return test_drive_appointments_view(request)



