"""
Core Business Services for CarVistaHub Showroom Bookings & Scheduling.
Provides Manager assignment resolution, schedule calculation, dynamic slot generation,
and comprehensive calendar availability engine with role-based privacy sanitization.
"""

import datetime
import re
import zoneinfo
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from .models import (
    ShowroomSchedule,
    ShowroomClosure,
    ActiveSlotReservation,
    TestDriveBooking,
    BookingActivity,
    CustomerNotification,
)

User = get_user_model()


class ManagerNotConfiguredError(ValidationError):
    """Raised when an operation requires an active Showroom Manager, but none exists."""
    pass


class SlotUnavailableError(ValidationError):
    """Raised when an appointment slot is already reserved or unavailable."""
    pass


def is_manager(user):
    """
    Returns True strictly if the authenticated user is an active Showroom Manager.
    Admins, regular customers, and guests return False.
    """
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'user_type', None) == User.UserType.MANAGER and user.is_active


def is_manager_or_admin(user):
    """
    Returns True if the authenticated user is an authorized Showroom Manager or Administrator.
    Ensures authorization is strictly derived from the authenticated Django user model.
    """
    if not user or not user.is_authenticated:
        return False
    return (
        getattr(user, 'user_type', None) in [User.UserType.MANAGER, User.UserType.ADMIN]
        or user.is_staff
        or user.is_superuser
    )


def get_assigned_manager():
    """
    Retrieves the single active Showroom Manager account.
    Enforces the single-manager business rule: test drives must be assigned
    to the active Manager, and never silently reassigned to Admins or customers.

    Raises:
        ManagerNotConfiguredError: If no active Showroom Manager account exists.
    """
    manager = User.get_active_manager()
    if not manager:
        raise ManagerNotConfiguredError(
            "No active Showroom Manager account is currently configured. "
            "An administrator must create or activate a Manager account before "
            "test drives can be assigned."
        )
    return manager


ACTIVE_BOOKING_STATUSES = [
    TestDriveBooking.Status.PENDING,
    TestDriveBooking.Status.PROPOSED,
    TestDriveBooking.Status.CUSTOMER_ACCEPTED,
    TestDriveBooking.Status.CONFIRMED,
    TestDriveBooking.Status.APPROVED,
    TestDriveBooking.Status.NO_SHOW,
]


def get_customer_active_booking(customer):
    """
    Returns the customer's current active test drive booking if one exists, else None.
    Blocking statuses: PENDING, PROPOSED, CUSTOMER_ACCEPTED, CONFIRMED, APPROVED, NO_SHOW.
    Terminal non-blocking statuses: COMPLETED, CANCELLED, REJECTED, EXPIRED.
    """
    if not customer or not customer.is_authenticated:
        return None
    return TestDriveBooking.objects.filter(
        customer=customer,
        status__in=ACTIVE_BOOKING_STATUSES
    ).select_related('car', 'car__brand').first()


def validate_customer_has_no_active_booking(customer):
    """
    Enforces the single-active-booking business rule:
    A customer may have only ONE active test-drive booking at a time across all cars and dates.
    Raises ValidationError with dynamic car name, date, and time if an active booking exists.
    """
    active = get_customer_active_booking(customer)
    if active:
        car_name = f"{active.car.brand.name} {active.car.title}" if getattr(active.car, 'brand', None) else active.car.title
        date_str = active.preferred_date.strftime('%d %b %Y')
        time_str = active.start_time.strftime('%H:%M') if active.start_time else active.get_time_slot_display()
        raise ValidationError(
            f"You already have an active test-drive appointment for {car_name} on {date_str} at {time_str}. "
            "You can book another test drive after this appointment is completed or cancelled."
        )


def get_rolling_booking_window():
    """
    Returns the dynamic 7-day rolling appointment booking window (window_start, window_end)
    based on the current showroom-local calendar date.
    Window encompasses today through today + 6 calendar days (7 calendar days total).
    Example:
      On 1 Nov: 1 Nov - 7 Nov
      On 2 Nov: 2 Nov - 8 Nov
      On 3 Nov: 3 Nov - 9 Nov
    """
    today = timezone.localdate()
    max_date = today + datetime.timedelta(days=6)
    return today, max_date


def validate_date_in_rolling_window(target_date):
    """
    Validates that target_date falls within the customer rolling 7-day window.
    Raises ValidationError if target_date is in the past or beyond today + 6 calendar days.
    """
    if isinstance(target_date, str):
        try:
            target_date = datetime.date.fromisoformat(target_date.strip())
        except (ValueError, TypeError):
            raise ValidationError({'preferred_date': "Invalid appointment date format. Expected YYYY-MM-DD."})
    elif isinstance(target_date, datetime.datetime):
        target_date = target_date.date()

    today, max_date = get_rolling_booking_window()

    if target_date < today:
        raise ValidationError({
            'preferred_date': (
                f"Requested appointment date ({target_date.strftime('%Y-%m-%d')}) cannot be in the past. "
                f"Test drive bookings are only available for the next 7 days ({today.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')})."
            )
        })
    if target_date > max_date:
        raise ValidationError({
            'preferred_date': (
                f"Requested appointment date ({target_date.strftime('%Y-%m-%d')}) is outside the 7-day booking window. "
                f"Test drive bookings are only available for the next 7 days ({today.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')})."
            )
        })
    return True


def generate_showroom_daily_slots(target_date):
    """
    Generates candidate 1-hour appointment slots for a given date based on:
      1. ShowroomSchedule for the day of the week (operating hours)
      2. ShowroomClosure exclusions (recurring breaks, full-day holidays, partial closures)

    Returns a list of dicts:
        [
            {
                'date': target_date,
                'start_time': datetime.time(9, 0),
                'end_time': datetime.time(10, 0),
                'slot_key': 'YYYY-MM-DD_09:00',
            },
            ...
        ]
    """
    if isinstance(target_date, datetime.datetime):
        target_date = target_date.date()

    weekday = target_date.weekday()

    # 1. Lookup operating schedule for this weekday
    try:
        schedule = ShowroomSchedule.objects.get(day_of_week=weekday, is_active=True)
    except ShowroomSchedule.DoesNotExist:
        return []

    if not schedule.is_open:
        return []

    # 2. Check for full-day holiday / closure on this specific date
    holiday = ShowroomClosure.objects.filter(
        closure_type=ShowroomClosure.ClosureType.HOLIDAY,
        specific_date=target_date,
        is_active=True
    ).exists()
    if holiday:
        return []

    # 3. Retrieve breaks and partial closures affecting this date
    closures = ShowroomClosure.objects.filter(
        is_active=True
    ).filter(
        models_q_break(weekday) | models_q_partial(target_date)
    )

    break_intervals = []
    for c in closures:
        if c.start_time and c.end_time:
            break_intervals.append((c.start_time, c.end_time))

    # 4. Generate candidate 1-hour slots from open_time to close_time
    duration_minutes = schedule.slot_duration_minutes or 60
    slot_delta = datetime.timedelta(minutes=duration_minutes)

    open_dt = datetime.datetime.combine(target_date, schedule.open_time)
    close_dt = datetime.datetime.combine(target_date, schedule.close_time)

    slots = []
    current_dt = open_dt

    while current_dt + slot_delta <= close_dt:
        slot_start_time = current_dt.time()
        slot_end_time = (current_dt + slot_delta).time()

        # Check if this slot overlaps any break interval
        overlaps_break = False
        for b_start, b_end in break_intervals:
            if slot_start_time < b_end and slot_end_time > b_start:
                overlaps_break = True
                break

        if not overlaps_break:
            slot_key = ActiveSlotReservation.generate_slot_key(target_date, slot_start_time)
            slots.append({
                'date': target_date,
                'start_time': slot_start_time,
                'end_time': slot_end_time,
                'slot_key': slot_key,
            })

        current_dt += slot_delta

    return slots


def get_showroom_calendar_availability(start_date, end_date, user=None, car_id=None):
    """
    Computes date-wise availability for the shared showroom calendar within [start_date, end_date].
    Integrates ShowroomSchedule, ShowroomClosure (breaks & holidays), past slot checks,
    and ActiveSlotReservation locks with role-based data sanitization.
    """
    if isinstance(start_date, datetime.datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime.datetime):
        end_date = end_date.date()

    now = timezone.now()
    tz = zoneinfo.ZoneInfo(settings.TIME_ZONE)
    manager_view = is_manager(user)
    is_authenticated = bool(user and user.is_authenticated)

    # 1. Fetch operating schedules mapped by weekday (0..6)
    schedules = {
        s.day_of_week: s
        for s in ShowroomSchedule.objects.filter(is_active=True)
    }

    # For unauthenticated guests: return locked preview slots without querying
    # active reservations or exposing actual booking availability / PII.
    if not is_authenticated:
        days_data = []
        curr_date = start_date
        delta_day = datetime.timedelta(days=1)

        while curr_date <= end_date:
            weekday = curr_date.weekday()
            schedule = schedules.get(weekday)

            if schedule and schedule.open_time and schedule.close_time:
                open_time = schedule.open_time
                close_time = schedule.close_time
                duration_minutes = schedule.slot_duration_minutes or 60
            else:
                open_time = datetime.time(9, 0)
                close_time = datetime.time(18, 0)
                duration_minutes = 60

            slot_delta = datetime.timedelta(minutes=duration_minutes)
            open_dt = datetime.datetime.combine(curr_date, open_time)
            close_dt = datetime.datetime.combine(curr_date, close_time)

            current_slot_dt = open_dt
            slots = []
            while current_slot_dt + slot_delta <= close_dt:
                slot_start = current_slot_dt.time()
                slot_end = (current_slot_dt + slot_delta).time()
                slot_key = ActiveSlotReservation.generate_slot_key(curr_date, slot_start)
                slots.append({
                    'date': curr_date.strftime('%Y-%m-%d'),
                    'start_time': slot_start.strftime('%H:%M'),
                    'end_time': slot_end.strftime('%H:%M'),
                    'slot_key': slot_key,
                    'status': 'LOCKED',
                    'is_past': False,
                    'reason': 'Sign up or log in to view availability',
                    'booking_details': None,
                })
                current_slot_dt += slot_delta

            days_data.append({
                'date': curr_date.strftime('%Y-%m-%d'),
                'weekday': weekday,
                'weekday_name': curr_date.strftime('%A'),
                'is_open': True,
                'closure_reason': None,
                'slots': slots,
            })
            curr_date += delta_day

        return {
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'is_manager_view': False,
            'is_guest_view': True,
            'days': days_data,
        }

    # 2. Fetch closures affecting the date range
    closures_qs = ShowroomClosure.objects.filter(is_active=True)

    # Recurring breaks (daily or day_of_week specific)
    recurring_breaks = list(closures_qs.filter(
        closure_type=ShowroomClosure.ClosureType.BREAK,
        is_recurring=True,
    ))

    # Date-specific full-day holidays
    holidays_by_date = {
        c.specific_date: c
        for c in closures_qs.filter(
            closure_type=ShowroomClosure.ClosureType.HOLIDAY,
            specific_date__gte=start_date,
            specific_date__lte=end_date,
        )
    }

    # Date-specific partial closures or exceptions
    partials_by_date = {}
    for c in closures_qs.filter(
        closure_type__in=[ShowroomClosure.ClosureType.PARTIAL, ShowroomClosure.ClosureType.EXCEPTION],
        specific_date__gte=start_date,
        specific_date__lte=end_date,
    ):
        partials_by_date.setdefault(c.specific_date, []).append(c)

    # 3. Fetch active reservations across date range in a single query
    reservations_qs = ActiveSlotReservation.objects.filter(
        slot_date__gte=start_date,
        slot_date__lte=end_date,
    ).select_related(
        'booking',
        'booking__customer',
        'booking__car',
        'booking__car__brand',
        'booking__assigned_manager',
        'proposal',
    )

    # Active reservations map: slot_key -> ActiveSlotReservation
    # Safe interpretation of expiration timestamps:
    # A reservation is active if CONFIRMED, or if unexpired (expires_at is None or expires_at > now)
    active_reservations = {}
    for res in reservations_qs:
        if res.reservation_type == ActiveSlotReservation.ReservationType.CONFIRMED:
            active_reservations[res.slot_key] = res
        elif res.expires_at is None or res.expires_at > now:
            active_reservations[res.slot_key] = res

    # 4. Generate day-by-day availability slots
    days_data = []
    curr_date = start_date
    delta_day = datetime.timedelta(days=1)

    while curr_date <= end_date:
        weekday = curr_date.weekday()
        schedule = schedules.get(weekday)
        holiday = holidays_by_date.get(curr_date)

        is_open = bool(schedule and schedule.is_open and not holiday)
        closure_reason = None
        if holiday:
            closure_reason = holiday.title
        elif not schedule or not schedule.is_open:
            closure_reason = "Showroom Closed on this day"

        day_dict = {
            'date': curr_date.strftime('%Y-%m-%d'),
            'weekday': weekday,
            'weekday_name': curr_date.strftime('%A'),
            'is_open': is_open,
            'closure_reason': closure_reason,
            'slots': []
        }

        if is_open and schedule:
            duration_minutes = schedule.slot_duration_minutes or 60
            slot_delta = datetime.timedelta(minutes=duration_minutes)

            # Collect breaks affecting this weekday/date
            break_intervals = []
            for rb in recurring_breaks:
                if rb.day_of_week is None or rb.day_of_week == weekday:
                    if rb.start_time and rb.end_time:
                        break_intervals.append((rb.start_time, rb.end_time, rb.title))

            for pb in partials_by_date.get(curr_date, []):
                if pb.start_time and pb.end_time:
                    break_intervals.append((pb.start_time, pb.end_time, pb.title))

            open_dt = datetime.datetime.combine(curr_date, schedule.open_time)
            close_dt = datetime.datetime.combine(curr_date, schedule.close_time)

            current_slot_dt = open_dt
            while current_slot_dt + slot_delta <= close_dt:
                slot_start = current_slot_dt.time()
                slot_end = (current_slot_dt + slot_delta).time()
                slot_key = ActiveSlotReservation.generate_slot_key(curr_date, slot_start)

                # Check if slot overlaps break
                break_title = None
                for b_start, b_end, b_title in break_intervals:
                    if slot_start < b_end and slot_end > b_start:
                        break_title = b_title
                        break

                # Check if slot is in the past (Asia/Kolkata timezone)
                slot_tz_dt = datetime.datetime.combine(curr_date, slot_start).replace(tzinfo=tz)
                is_past = slot_tz_dt <= now

                res = active_reservations.get(slot_key)

                if break_title:
                    status = 'CLOSED'
                    reason = f"Break ({break_title})"
                    res = None
                elif not manager_view and is_past:
                    status = 'CLOSED'
                    reason = "Past Appointment Time"
                    res = None
                elif res:
                    reason = None
                    if res.reservation_type == ActiveSlotReservation.ReservationType.CONFIRMED:
                        status = 'BOOKED'
                    elif res.reservation_type == ActiveSlotReservation.ReservationType.PROPOSED:
                        status = 'PROPOSED'
                    else:  # PENDING or CUSTOMER_ACCEPTED
                        status = 'PENDING'
                elif is_past:
                    status = 'CLOSED'
                    reason = "Past Appointment Time"
                    res = None
                else:
                    status = 'AVAILABLE'
                    reason = None

                # Format role-appropriate booking details
                booking_details = None
                if res and res.booking:
                    if manager_view:
                        car_display = f"{res.booking.car.brand.name} {res.booking.car.title}" if getattr(res.booking.car, 'brand', None) else res.booking.car.title
                        has_license = bool(res.booking.driving_license_image)
                        from django.urls import reverse
                        try:
                            license_image_url = reverse('bookings:secure_license_image', kwargs={'booking_id': res.booking.id}) if has_license else None
                        except Exception:
                            license_image_url = f"/bookings/secure-document/{res.booking.id}/license/" if has_license else None

                        v_status = res.booking.license_verification_status
                        if v_status == TestDriveBooking.LicenseVerificationStatus.VERIFIED:
                            v_display = "Document Verified by Manager"
                        elif v_status == TestDriveBooking.LicenseVerificationStatus.REJECTED:
                            v_display = "Document Rejected"
                        else:
                            v_display = "Pending Review"

                        can_confirm = bool(
                            res.booking.license_verification_status == TestDriveBooking.LicenseVerificationStatus.VERIFIED
                            and res.booking.status == TestDriveBooking.Status.PENDING
                            and res.reservation_type in [
                                ActiveSlotReservation.ReservationType.PENDING,
                                ActiveSlotReservation.ReservationType.CUSTOMER_ACCEPTED
                            ]
                        )
                        tz_slot = zoneinfo.ZoneInfo(settings.TIME_ZONE)
                        slot_end_dt = datetime.datetime.combine(curr_date, slot_end).replace(tzinfo=tz_slot)
                        can_complete = bool(res.booking.status == TestDriveBooking.Status.CONFIRMED and now >= slot_end_dt)

                        booking_details = {
                            'booking_id': res.booking.id,
                            'booking_number': res.booking.booking_number,
                            'customer_name': res.booking.customer.get_full_name() or res.booking.customer.username,
                            'customer_email': res.booking.customer.email,
                            'customer_phone': getattr(res.booking.customer, 'phone_number', '') or '',
                            'driving_license_number': res.booking.driving_license_number,
                            'has_license_image': has_license,
                            'license_image_url': license_image_url,
                            'license_verification_status': v_status,
                            'license_verification_display': v_display,
                            'can_confirm': can_confirm,
                            'can_complete': can_complete,
                            'car_id': res.booking.car.id,
                            'car_title': car_display,
                            'status': res.booking.status,
                            'reservation_type': res.reservation_type,
                            'customer_notes': res.booking.customer_notes,
                            'manager_notes': res.booking.manager_notes,
                            'rejection_reason': res.booking.rejection_reason,
                            'expires_at': res.expires_at.isoformat() if res.expires_at else None,
                            'created_at': res.booking.created_at.isoformat() if res.booking.created_at else None,
                        }
                        if res.proposal:
                            booking_details['proposal'] = {
                                'id': res.proposal.id,
                                'proposed_date': res.proposal.proposed_date.strftime('%Y-%m-%d'),
                                'proposed_start_time': res.proposal.proposed_start_time.strftime('%H:%M'),
                                'proposed_end_time': res.proposal.proposed_end_time.strftime('%H:%M'),
                                'status': res.proposal.status,
                                'expires_at': res.proposal.expires_at.isoformat() if res.proposal.expires_at else None,
                            }
                    else:
                        # For regular customer or anonymous: NO OTHER CUSTOMER DATA
                        is_mine = bool(
                            user
                            and user.is_authenticated
                            and res.booking.customer_id == user.id
                        )
                        booking_details = {
                            'is_my_booking': is_mine,
                        }
                        if is_mine:
                            car_display = f"{res.booking.car.brand.name} {res.booking.car.title}" if getattr(res.booking.car, 'brand', None) else res.booking.car.title
                            booking_details['booking_id'] = res.booking.id
                            booking_details['booking_number'] = res.booking.booking_number
                            booking_details['status'] = res.booking.status
                            booking_details['car_title'] = car_display
                            booking_details['date'] = curr_date.strftime('%Y-%m-%d')
                            booking_details['date_display'] = curr_date.strftime('%a, %d %b %Y')
                            booking_details['slot_time'] = f"{slot_start.strftime('%H:%M')} - {slot_end.strftime('%H:%M')}"
                            booking_details['showroom_location'] = "CarVistaHub Showroom"
                            booking_details['can_cancel'] = bool(res.booking.status == TestDriveBooking.Status.CONFIRMED)

                slot_entry = {
                    'date': curr_date.strftime('%Y-%m-%d'),
                    'start_time': slot_start.strftime('%H:%M'),
                    'end_time': slot_end.strftime('%H:%M'),
                    'slot_key': slot_key,
                    'status': status,
                    'is_past': is_past,
                    'reason': reason,
                    'booking_details': booking_details,
                }
                day_dict['slots'].append(slot_entry)
                current_slot_dt += slot_delta

        days_data.append(day_dict)
        curr_date += delta_day

    return {
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'is_manager_view': manager_view,
        'is_guest_view': False,
        'days': days_data,
    }


def models_q_break(weekday):
    return Q(
        closure_type=ShowroomClosure.ClosureType.BREAK,
        is_recurring=True,
    ) & (Q(day_of_week=weekday) | Q(day_of_week__isnull=True))


def models_q_partial(target_date):
    return Q(
        closure_type__in=[
            ShowroomClosure.ClosureType.PARTIAL,
            ShowroomClosure.ClosureType.EXCEPTION
        ],
        specific_date=target_date,
    )


# Set of 2-letter Indian State & Union Territory codes under MoRTH / Sarathi
VALID_INDIAN_STATE_CODES = {
    'AN', 'AP', 'AR', 'AS', 'BR', 'CG', 'CH', 'DD', 'DL', 'DN',
    'GA', 'GJ', 'HP', 'HR', 'JH', 'JK', 'KA', 'KL', 'LA', 'LD',
    'MH', 'ML', 'MN', 'MP', 'MZ', 'NL', 'OD', 'PB', 'PY', 'RJ',
    'SK', 'TN', 'TR', 'TS', 'UK', 'UP', 'WB', 'OR', 'UA'
}


def validate_driving_license_image(file):
    """
    Validates customer-uploaded front-side photo of their Indian Driving Licence.

    Enforces:
      1. Mandatory presence (file exists and size > 0).
      2. File size limit: maximum 5 MB (5 * 1024 * 1024 bytes).
      3. File extension whitelist: .jpg, .jpeg, .png.
      4. MIME type check: image/jpeg, image/png.
      5. Real image decoding and integrity verification via Pillow (PIL.Image).
    """
    if not file:
        raise ValidationError("Driving licence photograph is compulsory. Please upload the front side of your licence.")

    # 1. Size check (5 MB limit)
    max_size = 5 * 1024 * 1024
    file_size = getattr(file, 'size', None)
    if file_size is not None:
        if file_size == 0:
            raise ValidationError("The uploaded licence photo file is empty. Please select a valid image.")
        if file_size > max_size:
            raise ValidationError("File size exceeds 5 MB. Please upload a clear photo under 5 MB in size.")

    # 2. File extension check
    filename = getattr(file, 'name', '')
    if not filename or '.' not in filename:
        raise ValidationError("Uploaded file must have a valid image extension (.jpg, .jpeg, or .png).")

    ext = filename.rsplit('.', 1)[-1].lower()
    if ext not in ['jpg', 'jpeg', 'png']:
        raise ValidationError(f"Invalid file type (.{ext}). Only JPG, JPEG, and PNG images are accepted.")

    # 3. Content type check
    content_type = getattr(file, 'content_type', None)
    if content_type:
        allowed_mimes = {'image/jpeg', 'image/png', 'image/pjpeg', 'image/x-png'}
        if content_type.lower() not in allowed_mimes:
            raise ValidationError(f"Invalid image content type ({content_type}). Only JPG and PNG photos are accepted.")

    # 4. Actual image decoding using Pillow
    try:
        from PIL import Image
        if hasattr(file, 'seek'):
            file.seek(0)
        img = Image.open(file)
        img.verify()
        if img.format not in ['JPEG', 'PNG']:
            raise ValidationError("Unsupported image format. Please upload a genuine JPG or PNG photo.")
        if hasattr(file, 'seek'):
            file.seek(0)
    except ValidationError:
        raise
    except Exception:
        raise ValidationError("Uploaded file is corrupt or not a valid readable image.")

    return True


def validate_and_normalize_indian_dl(dl_number):
    """
    Validates that the submitted driving licence number conforms to a plausible
    Indian DL format (Ministry of Road Transport and Highways / Sarathi standards),
    normalizes whitespace and letter casing safely, and returns the normalized string.

    NOTE: Format validation is NOT authenticity verification. Every licence starts
    in PENDING verification status awaiting manual inspection by the Showroom Manager.
    """
    if not dl_number or not str(dl_number).strip():
        raise ValidationError("Driving licence number is compulsory.")

    raw = str(dl_number).strip().upper()
    # Strip spaces, hyphens, and slashes for core alphanumeric pattern validation
    cleaned = re.sub(r'[\s\-\/]+', '', raw)

    # Plausible Indian DL: 2-letter state code + 2-digit RTO + 4-digit issue year + 4-7 unique digits
    # Total alphanumeric length: 12 to 15 characters (standard Sarathi is 15 chars)
    if not (12 <= len(cleaned) <= 15):
        raise ValidationError(
            "Please enter a valid Indian Driving Licence number (e.g., DL-0120150001234 or MH-0220180012345)."
        )

    state_code = cleaned[:2]
    if state_code not in VALID_INDIAN_STATE_CODES:
        raise ValidationError(
            f"'{state_code}' is not a recognized Indian State or Union Territory code. "
            "Please enter a valid Indian Driving Licence number."
        )

    # Next 2 chars: RTO code (digits)
    rto_code = cleaned[2:4]
    if not rto_code.isdigit():
        raise ValidationError(
            "Invalid RTO jurisdiction code in driving licence. Expected 2 digits after state code."
        )

    # Next 4 chars: issue year (digits, between 1950 and current_year)
    year_str = cleaned[4:8]
    if not year_str.isdigit():
        raise ValidationError(
            "Invalid issue year in driving licence number. Expected 4 digits for year of issue."
        )
    year = int(year_str)
    current_year = timezone.now().year
    if year < 1950 or year > current_year:
        raise ValidationError(
            f"Invalid issue year ({year}) in driving licence. Year must be between 1950 and {current_year}."
        )

    # Remaining characters: 4 to 7 digits
    remaining = cleaned[8:]
    if not remaining.isdigit() or len(remaining) < 4:
        raise ValidationError(
            "Invalid unique licence serial digits in driving licence number."
        )

    # Normalized canonical representation: State-RTOYearSerial (e.g. MH-0120150001234)
    return f"{state_code}-{cleaned[2:]}"


def mask_driving_license(dl_number):
    """
    Masks DL number for customer privacy (e.g. DL-*******1234).
    Full DL numbers are never exposed in customer-facing APIs, logs, or public outputs.
    """
    if not dl_number:
        return ""
    clean_dl = str(dl_number).strip().upper()
    if len(clean_dl) >= 8:
        return f"{clean_dl[:3]}*******{clean_dl[-4:]}"
    return "DL-********"


def create_customer_test_drive_booking(
    customer,
    car,
    preferred_date,
    start_time,
    license_image=None,
    driving_license_number='',
    customer_notes='',
    contact_phone='',
    terms_agreed=False
):
    """
    Core business service for customer test drive appointment booking submission.

    Enforces:
      1. Authenticated customer role strictly (UserType.CUSTOMER).
      2. Server-side validation of car availability from database.
      3. Mandatory front-side driving licence image upload (validated via Pillow).
      4. Driving licence verification status initialized to PENDING.
      5. Compulsory terms & conditions agreement.
      6. Chronological validation: reject past dates and past times.
      7. Showroom schedule and closure validation (operating hours, lunch breaks, holidays).
      8. Dynamic single active Showroom Manager assignment (fails safely if missing).
      9. Server-side slot availability check and duplicate reservation protection.
      10. Atomic database transaction with ActiveSlotReservation hold and BookingActivity audit log.
      11. 24-hour pending reservation expiration timestamp.
    """
    # 1. Enforce customer authentication and role
    if not customer or not customer.is_authenticated:
        raise PermissionDenied("Authentication is required to book a test drive.")

    if getattr(customer, 'user_type', None) != User.UserType.CUSTOMER:
        raise PermissionDenied("Only registered customers can book a test drive appointment.")

    # 2. Enforce one active test-drive booking per customer restriction
    validate_customer_has_no_active_booking(customer)

    # 3. Compulsory terms & conditions agreement
    if not terms_agreed:
        raise ValidationError({'terms_agreed': "You must accept the Terms and Conditions to submit a booking."})

    # 3. Driving licence validation: Mandatory front-side image upload
    if not license_image:
        raise ValidationError({'license_image': "Upload of the front side of your original driving licence is compulsory."})
    validate_driving_license_image(license_image)

    # 4. Validate selected car from database
    if not car or not getattr(car, 'is_available', False):
        raise ValidationError({'car': "The selected vehicle is currently not available for showroom test drives."})

    # 5. Coerce preferred_date and start_time
    if isinstance(preferred_date, str):
        try:
            preferred_date = datetime.date.fromisoformat(preferred_date.strip())
        except (ValueError, TypeError):
            raise ValidationError({'preferred_date': "Invalid appointment date format. Expected YYYY-MM-DD."})

    if isinstance(start_time, str):
        try:
            time_parts = [int(p) for p in start_time.strip().split(':')[:2]]
            start_time = datetime.time(time_parts[0], time_parts[1])
        except (ValueError, TypeError, IndexError):
            raise ValidationError({'start_time': "Invalid slot start time format. Expected HH:MM."})

    # 6. Validate rolling 7-day customer booking window (today through today + 6 calendar days)
    validate_date_in_rolling_window(preferred_date)

    # 7. Reject past time slots for today (in showroom timezone)
    now = timezone.now()
    tz = zoneinfo.ZoneInfo(settings.TIME_ZONE)
    slot_tz_dt = datetime.datetime.combine(preferred_date, start_time).replace(tzinfo=tz)
    if slot_tz_dt <= now:
        raise ValidationError({'start_time': "Cannot book appointment slots in the past."})

    # 7. Validate showroom operating schedule for this weekday
    weekday = preferred_date.weekday()
    try:
        schedule = ShowroomSchedule.objects.get(day_of_week=weekday, is_active=True)
    except ShowroomSchedule.DoesNotExist:
        raise ValidationError({'preferred_date': "Showroom is closed on this day."})

    if not schedule.is_open:
        raise ValidationError({'preferred_date': "Showroom is closed on this day."})

    duration_minutes = schedule.slot_duration_minutes or 60
    slot_delta = datetime.timedelta(minutes=duration_minutes)
    end_time = (datetime.datetime.combine(preferred_date, start_time) + slot_delta).time()

    # Verify within opening and closing hours
    if start_time < schedule.open_time or end_time > schedule.close_time:
        raise ValidationError({
            'start_time': (
                f"Requested slot ({start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}) "
                f"is outside showroom operating hours ({schedule.open_time.strftime('%H:%M')} - {schedule.close_time.strftime('%H:%M')})."
            )
        })

    # 8. Check for full-day holiday
    holiday = ShowroomClosure.objects.filter(
        closure_type=ShowroomClosure.ClosureType.HOLIDAY,
        specific_date=preferred_date,
        is_active=True
    ).first()
    if holiday:
        raise ValidationError({'preferred_date': f"Showroom is closed on this date ({holiday.title})."})

    # 9. Check for break or partial closure overlaps
    break_closures = ShowroomClosure.objects.filter(is_active=True).filter(
        models_q_break(weekday) | models_q_partial(preferred_date)
    )
    for c in break_closures:
        if c.start_time and c.end_time:
            if start_time < c.end_time and end_time > c.start_time:
                raise ValidationError({
                    'start_time': f"Selected appointment slot overlaps showroom closure / break ({c.title})."
                })

    # 10. Retrieve the single active Showroom Manager (fails safely with clear error if missing)
    assigned_manager = get_assigned_manager()

    # 11. Generate slot key & expiration timestamp (strictly 24 hours)
    slot_key = ActiveSlotReservation.generate_slot_key(preferred_date, start_time)
    pending_expires_at = now + datetime.timedelta(hours=24)

    # 12. Atomic write with unique slot constraint as final duplicate-reservation defense
    try:
        with transaction.atomic():
            # Check for existing reservation on this slot key
            existing_res = ActiveSlotReservation.objects.select_for_update().filter(slot_key=slot_key).first()
            if existing_res:
                is_active_res = (
                    existing_res.reservation_type == ActiveSlotReservation.ReservationType.CONFIRMED
                    or (existing_res.expires_at is None or existing_res.expires_at > now)
                )
                if is_active_res:
                    raise SlotUnavailableError(
                        "This appointment slot is already reserved and no longer available. Please choose another available slot."
                    )
                else:
                    # Expired pending reservation: transition old booking to EXPIRED and clear stale reservation
                    old_booking = existing_res.booking
                    if old_booking and old_booking.status == TestDriveBooking.Status.PENDING:
                        old_booking.status = TestDriveBooking.Status.EXPIRED
                        old_booking.save(update_fields=['status', 'updated_at'])
                        BookingActivity.objects.create(
                            booking=old_booking,
                            actor=None,
                            action=BookingActivity.Action.EXPIRED,
                            notes="Pending reservation expired automatically before slot was rebooked."
                        )
                    existing_res.delete()

            # Atomic concurrency check for customer active booking
            validate_customer_has_no_active_booking(customer)

            # Create TestDriveBooking with PENDING status and PENDING DL verification
            booking = TestDriveBooking.objects.create(
                customer=customer,
                assigned_manager=assigned_manager,
                car=car,
                preferred_date=preferred_date,
                start_time=start_time,
                end_time=end_time,
                driving_license_number='',
                driving_license_image=license_image,
                license_verification_status=TestDriveBooking.LicenseVerificationStatus.PENDING,
                status=TestDriveBooking.Status.PENDING,
                pending_expires_at=pending_expires_at,
                customer_notes=customer_notes.strip() if customer_notes else '',
            )

            # Create corresponding ActiveSlotReservation
            ActiveSlotReservation.objects.create(
                slot_key=slot_key,
                slot_date=preferred_date,
                start_time=start_time,
                end_time=end_time,
                booking=booking,
                reservation_type=ActiveSlotReservation.ReservationType.PENDING,
                expires_at=pending_expires_at,
            )

            # Create BookingActivity audit record
            BookingActivity.objects.create(
                booking=booking,
                actor=customer,
                action=BookingActivity.Action.REQUEST_SUBMITTED,
                previous_status='',
                new_status=TestDriveBooking.Status.PENDING,
                notes=(
                    f"Customer submitted test drive booking request for {car.brand.name} {car.title} "
                    f"on {preferred_date} ({start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}). "
                    f"Front-side driving licence photo uploaded (Verification Status: PENDING review by Manager)."
                )
            )

            return booking

    except IntegrityError:
        # SQLite duplicate slot_key constraint violation from concurrent submission
        raise SlotUnavailableError(
            "This appointment slot was just reserved by another customer. Please choose another available slot."
        )


def manager_update_license_verification(booking, manager, action, reason=''):
    """
    Showroom Manager workflow actions for customer driving licence verification:
      1. 'VERIFY': Changes license_verification_status to VERIFIED.
         Records Manager ID and verification timestamp.
         Creates a BookingActivity audit entry.
         Does NOT automatically confirm the test-drive booking.
         Booking becomes eligible for subsequent confirmation.
      2. 'REJECT': Changes license_verification_status to REJECTED.
         Changes TestDriveBooking.status to REJECTED.
         Requires and saves mandatory rejection reason.
         Records Manager ID and timestamp.
         Creates a BookingActivity audit entry (action=REJECTED).
         Releases the ActiveSlotReservation for this booking within an atomic transaction.
         Makes slot available again in the shared customer calendar.
         Creates a persistent in-app CustomerNotification for the affected customer.
    """
    if not is_manager_or_admin(manager):
        raise PermissionDenied("Only authorized Showroom Managers can review licence documents.")

    # Showroom Manager assignment check
    if getattr(manager, 'user_type', None) == User.UserType.MANAGER:
        if booking.assigned_manager_id and booking.assigned_manager_id != manager.id and not manager.is_staff:
            raise PermissionDenied("Access denied. You are not the assigned Showroom Manager for this booking.")

    action_upper = str(action).strip().upper()
    reason_clean = str(reason or '').strip()

    # Guard against invalid transitions
    if booking.status in [TestDriveBooking.Status.CANCELLED, TestDriveBooking.Status.COMPLETED]:
        raise ValidationError(f"Cannot perform verification actions on a {booking.get_status_display().lower()} booking.")

    if action_upper == 'VERIFY':
        if booking.status == TestDriveBooking.Status.REJECTED or booking.license_verification_status == TestDriveBooking.LicenseVerificationStatus.REJECTED:
            raise ValidationError("Cannot verify a driving licence document for an appointment that has been rejected.")

        if booking.license_verification_status == TestDriveBooking.LicenseVerificationStatus.VERIFIED:
            raise ValidationError("This driving licence document has already been verified.")

        booking.license_verification_status = TestDriveBooking.LicenseVerificationStatus.VERIFIED
        booking.verified_by = manager
        booking.verified_at = timezone.now()
        booking.save(update_fields=['license_verification_status', 'verified_by', 'verified_at', 'updated_at'])

        BookingActivity.objects.create(
            booking=booking,
            actor=manager,
            action=BookingActivity.Action.NOTE_ADDED,
            previous_status=booking.status,
            new_status=booking.status,
            notes=f"Driving licence document reviewed and verified by Showroom Manager {manager.username}."
        )
        return {
            'success': True,
            'status': booking.license_verification_status,
            'booking_status': booking.status,
            'display': 'Document Verified by Manager',
            'message': 'Driving licence document successfully verified.'
        }

    elif action_upper == 'REJECT':
        if not reason_clean:
            raise ValidationError("A rejection reason is mandatory when rejecting a driving licence document.")

        if booking.status == TestDriveBooking.Status.REJECTED and booking.license_verification_status == TestDriveBooking.LicenseVerificationStatus.REJECTED:
            raise ValidationError("This booking and driving licence document have already been rejected.")

        with transaction.atomic():
            now = timezone.now()
            old_status = booking.status
            booking.license_verification_status = TestDriveBooking.LicenseVerificationStatus.REJECTED
            booking.status = TestDriveBooking.Status.REJECTED
            booking.rejection_reason = reason_clean
            booking.rejected_by = manager
            booking.rejected_at = now
            booking.save(update_fields=[
                'license_verification_status',
                'status',
                'rejection_reason',
                'rejected_by',
                'rejected_at',
                'updated_at'
            ])

            # Audit trail
            BookingActivity.objects.create(
                booking=booking,
                actor=manager,
                action=BookingActivity.Action.REJECTED,
                previous_status=old_status,
                new_status=TestDriveBooking.Status.REJECTED,
                notes=f"Document verification failed and appointment rejected by Showroom Manager {manager.username}. Reason: {reason_clean}. Showroom slot released."
            )

            # Immediately release the ActiveSlotReservation belonging strictly to this booking
            ActiveSlotReservation.objects.filter(booking=booking).delete()

            # Create persistent in-app CustomerNotification
            slot_time_str = f"{booking.start_time.strftime('%H:%M')} - {booking.end_time.strftime('%H:%M')}" if booking.start_time and booking.end_time else booking.time_slot
            car_name = f"{booking.car.brand.name} {booking.car.title}" if getattr(booking.car, 'brand', None) else booking.car.title

            CustomerNotification.objects.create(
                user=booking.customer,
                booking=booking,
                notification_type=CustomerNotification.NotificationType.BOOKING_REJECTED,
                title="Test Drive Request Rejected",
                message=(
                    f"Your test drive request for {car_name} on {booking.preferred_date} ({slot_time_str}) "
                    f"has been rejected by Showroom Manager {manager.username}. Reason: {reason_clean}. "
                    "The showroom appointment slot has been released."
                ),
                booking_reference=booking.booking_number,
                car_title=car_name,
                slot_date=booking.preferred_date,
                slot_time=slot_time_str,
                rejection_reason=reason_clean,
                is_read=False,
            )

        return {
            'success': True,
            'status': booking.license_verification_status,
            'booking_status': booking.status,
            'display': 'Document Rejected',
            'message': f'Licence document rejected and appointment slot released: {reason_clean}'
        }
    else:
        raise ValidationError(f"Invalid verification action '{action}'. Permitted actions: VERIFY, REJECT.")


def validate_booking_confirmation(booking):
    """
    Enforces the safety rule:
    Do not permit booking confirmation unless the licence verification status is VERIFIED.
    """
    if booking.license_verification_status != TestDriveBooking.LicenseVerificationStatus.VERIFIED:
        raise ValidationError(
            "Booking cannot be confirmed until the customer's driving licence document "
            "has been verified by the Showroom Manager (status must be VERIFIED)."
        )
    return True


def manager_confirm_test_drive_booking(booking, manager):
    """
    Showroom Manager final test-drive confirmation action (Stage 2).
    Enforces:
      1. Only authorized Showroom Managers / Admins can confirm appointments.
      2. Manager assignment check if assigned.
      3. Driving licence verification status must be strictly VERIFIED.
      4. Appointment must be in a valid pre-confirmation state (PENDING).
      5. Prevents repeated confirmation or confirmation of rejected/cancelled/expired bookings.
      6. Verifies that the correct ActiveSlotReservation belongs to this booking and is not expired.
      7. Performs all state transitions within transaction.atomic():
         - Sets TestDriveBooking.status = CONFIRMED.
         - Sets confirmed_at = timezone.now().
         - Sets confirmed_by = manager.
         - Updates ActiveSlotReservation: reservation_type = CONFIRMED, expires_at = None.
         - Logs BookingActivity audit trail (action = CONFIRMED).
         - Dispatches persistent in-app CustomerNotification (notification_type = BOOKING_CONFIRMED).
    """
    if not is_manager_or_admin(manager):
        raise PermissionDenied("Only authorized Showroom Managers can confirm test-drive appointments.")

    if getattr(manager, 'user_type', None) == User.UserType.MANAGER:
        if booking.assigned_manager_id and booking.assigned_manager_id != manager.id and not manager.is_staff:
            raise PermissionDenied("Access denied. You are not the assigned Showroom Manager for this booking.")

    # 1. Licence verification requirement
    if booking.license_verification_status != TestDriveBooking.LicenseVerificationStatus.VERIFIED:
        raise ValidationError(
            "Booking cannot be confirmed until the customer's driving licence document "
            "has been verified by the Showroom Manager (licence verification status must be VERIFIED)."
        )

    # 2. Prevent duplicate / invalid confirmation
    if booking.status == TestDriveBooking.Status.CONFIRMED:
        raise ValidationError("This test-drive booking has already been confirmed.")

    if booking.status in [
        TestDriveBooking.Status.REJECTED,
        TestDriveBooking.Status.CANCELLED,
        TestDriveBooking.Status.COMPLETED,
        TestDriveBooking.Status.EXPIRED,
        TestDriveBooking.Status.NO_SHOW,
    ]:
        raise ValidationError(f"Cannot confirm an appointment with status '{booking.get_status_display()}'.")

    # 3. Active slot reservation check
    reservation = ActiveSlotReservation.objects.filter(booking=booking).first()
    if not reservation:
        raise ValidationError(
            "No active slot reservation found for this booking. The reservation may have expired or been released."
        )

    if reservation.slot_date != booking.preferred_date or reservation.start_time != booking.start_time:
        raise ValidationError(
            "Active slot reservation does not match the booking appointment date and time."
        )

    if reservation.expires_at and reservation.expires_at <= timezone.now() and reservation.reservation_type != ActiveSlotReservation.ReservationType.CONFIRMED:
        raise ValidationError(
            "The temporary reservation hold for this appointment has expired. Slot cannot be confirmed."
        )

    with transaction.atomic():
        now = timezone.now()

        # Update booking
        booking.status = TestDriveBooking.Status.CONFIRMED
        booking.confirmed_at = now
        booking.confirmed_by = manager
        if not booking.assigned_manager_id and getattr(manager, 'user_type', None) == User.UserType.MANAGER:
            booking.assigned_manager = manager
        booking.save(update_fields=['status', 'confirmed_at', 'confirmed_by', 'assigned_manager', 'updated_at'])

        # Update reservation to CONFIRMED and release hold expiry (expires_at = None)
        reservation.reservation_type = ActiveSlotReservation.ReservationType.CONFIRMED
        reservation.expires_at = None
        reservation.save(update_fields=['reservation_type', 'expires_at'])

        # Create BookingActivity audit log
        BookingActivity.objects.create(
            booking=booking,
            actor=manager,
            action=BookingActivity.Action.CONFIRMED,
            previous_status=TestDriveBooking.Status.PENDING,
            new_status=TestDriveBooking.Status.CONFIRMED,
            notes=(
                f"Showroom test drive appointment officially confirmed by Showroom Manager {manager.username}. "
                f"Slot reservation locked permanently without expiry."
            )
        )

        # Create persistent customer confirmation notification (idempotent get_or_create)
        slot_time_str = (
            f"{booking.start_time.strftime('%H:%M')} - {booking.end_time.strftime('%H:%M')}"
            if booking.start_time and booking.end_time
            else booking.time_slot
        )
        car_name = (
            f"{booking.car.brand.name} {booking.car.title}"
            if getattr(booking.car, 'brand', None)
            else booking.car.title
        )

        CustomerNotification.objects.get_or_create(
            booking=booking,
            notification_type=CustomerNotification.NotificationType.BOOKING_CONFIRMED,
            defaults={
                'user': booking.customer,
                'title': "Test Drive Confirmed!",
                'message': (
                    "Your Driving Licence has been reviewed and your test-drive appointment "
                    "has been confirmed by the Showroom Manager."
                ),
                'booking_reference': booking.booking_number,
                'car_title': car_name,
                'slot_date': booking.preferred_date,
                'slot_time': slot_time_str,
                'showroom_location': "CarVistaHub Showroom",
                'is_read': False,
            }
        )

    return {
        'success': True,
        'booking_id': booking.id,
        'booking_number': booking.booking_number,
        'status': booking.status,
        'status_display': 'Confirmed',
        'license_verification_status': booking.license_verification_status,
        'confirmed_at': booking.confirmed_at.isoformat(),
        'message': 'Test-drive booking successfully confirmed. Customer notification dispatched.'
    }


def customer_cancel_test_drive_booking(booking, customer, reason=''):
    """
    Customer cancels their test-drive appointment.
    Enforces:
      1. Authentication & booking ownership (customer owns the booking).
      2. Prevent repeated cancellation of an already cancelled booking.
      3. Prevent cancellation of completed or rejected bookings.
      4. Atomic transaction:
         - Sets booking.status = CANCELLED.
         - Records cancelled_at = timezone.now().
         - Saves cancellation_reason.
         - Deletes/releases ONLY the ActiveSlotReservation for this booking.
         - Creates BookingActivity audit entry (action = CANCELLED, actor = customer).
      5. Slot immediately becomes AVAILABLE in shared showroom calendar.
    """
    if not customer or not customer.is_authenticated:
        raise PermissionDenied("Authentication required to cancel appointment.")

    if booking.customer_id != customer.id and not (customer.is_staff or is_manager_or_admin(customer)):
        raise PermissionDenied("Access denied. You can only cancel your own test-drive appointments.")

    if booking.status == TestDriveBooking.Status.CANCELLED:
        raise ValidationError("This test-drive booking has already been cancelled.")

    if booking.status == TestDriveBooking.Status.COMPLETED:
        raise ValidationError("Cannot cancel an appointment that has already been completed.")

    if booking.status == TestDriveBooking.Status.REJECTED:
        raise ValidationError("Cannot cancel an appointment that has already been rejected.")

    with transaction.atomic():
        now = timezone.now()
        old_status = booking.status
        booking.status = TestDriveBooking.Status.CANCELLED
        booking.cancelled_at = now
        booking.cancellation_reason = reason.strip() if reason else "Cancelled by customer"
        booking.save(update_fields=['status', 'cancelled_at', 'cancellation_reason', 'updated_at'])

        # Release active slot reservation belonging strictly to this booking
        ActiveSlotReservation.objects.filter(booking=booking).delete()

        # Audit trail
        BookingActivity.objects.create(
            booking=booking,
            actor=customer,
            action=BookingActivity.Action.CANCELLED,
            previous_status=old_status,
            new_status=TestDriveBooking.Status.CANCELLED,
            notes=f"Test-drive appointment cancelled by customer {customer.username}. Reason: {booking.cancellation_reason}. Showroom slot released."
        )

    return {
        'success': True,
        'booking_id': booking.id,
        'booking_number': booking.booking_number,
        'status': 'CANCELLED',
        'message': 'Your test-drive appointment has been cancelled successfully. The selected time slot is now available for other customers.'
    }


def manager_complete_test_drive_booking(booking, manager):
    """
    Showroom Manager marks a confirmed test drive as COMPLETED after the session ends.
    Enforces:
      1. Authorized Showroom Manager / Admin only (customers cannot complete their own appointments).
      2. Manager assignment check if assigned.
      3. Booking must be CONFIRMED.
      4. Cannot complete before scheduled appointment end time.
      5. Atomic transaction:
         - Sets booking.status = COMPLETED.
         - Records completed_at = timezone.now().
         - Logs BookingActivity audit trail (action = COMPLETED, actor = manager).
         - Preserves confirmed reservation in history (no premature release).
      6. Lifts the customer's one-active-booking restriction.
    """
    if not is_manager_or_admin(manager):
        raise PermissionDenied("Only authorized Showroom Managers can mark appointments as completed.")

    if getattr(manager, 'user_type', None) == User.UserType.MANAGER:
        if booking.assigned_manager_id and booking.assigned_manager_id != manager.id and not manager.is_staff:
            raise PermissionDenied("Access denied. You are not the assigned Showroom Manager for this booking.")

    if booking.status == TestDriveBooking.Status.COMPLETED:
        raise ValidationError("This test-drive booking has already been marked as completed.")

    if booking.status != TestDriveBooking.Status.CONFIRMED:
        raise ValidationError(
            f"Only confirmed appointments can be marked as completed (current status: {booking.get_status_display()})."
        )

    # Chronological enforcement: appointment slot end time must have concluded
    tz = zoneinfo.ZoneInfo(settings.TIME_ZONE)
    end_time = booking.end_time or datetime.time(18, 0)
    slot_end_dt = datetime.datetime.combine(booking.preferred_date, end_time).replace(tzinfo=tz)
    if timezone.now() < slot_end_dt:
        raise ValidationError(
            f"Cannot mark appointment as completed before the scheduled appointment end time ({booking.preferred_date} {end_time.strftime('%H:%M')})."
        )

    with transaction.atomic():
        now = timezone.now()
        old_status = booking.status
        booking.status = TestDriveBooking.Status.COMPLETED
        booking.completed_at = now
        booking.save(update_fields=['status', 'completed_at', 'updated_at'])

        # Audit trail
        BookingActivity.objects.create(
            booking=booking,
            actor=manager,
            action=BookingActivity.Action.COMPLETED,
            previous_status=old_status,
            new_status=TestDriveBooking.Status.COMPLETED,
            notes=f"Showroom test drive appointment successfully completed and verified by Showroom Manager {manager.username}."
        )

    return {
        'success': True,
        'booking_id': booking.id,
        'booking_number': booking.booking_number,
        'status': 'COMPLETED',
        'completed_at': booking.completed_at.isoformat(),
        'message': 'Test-drive booking successfully marked as completed.'
    }


def expire_stale_pending_reservations():
    """
    Checks for expired 24-hour pending slot reservations and updates associated bookings to EXPIRED.
    Releases slot reservations so slots become available again, and logs BookingActivity audit entries.
    """
    now = timezone.now()
    expired_count = 0
    with transaction.atomic():
        expired_res = list(ActiveSlotReservation.objects.filter(
            reservation_type=ActiveSlotReservation.ReservationType.PENDING,
            expires_at__lte=now
        ).select_related('booking'))

        for res in expired_res:
            booking = res.booking
            if booking and booking.status == TestDriveBooking.Status.PENDING:
                old_status = booking.status
                booking.status = TestDriveBooking.Status.EXPIRED
                booking.save(update_fields=['status', 'updated_at'])
                BookingActivity.objects.create(
                    booking=booking,
                    actor=None,
                    action=BookingActivity.Action.EXPIRED,
                    previous_status=old_status,
                    new_status=TestDriveBooking.Status.EXPIRED,
                    notes="Pending reservation hold expired automatically after 24 hours. Showroom slot released."
                )
                expired_count += 1
            res.delete()

    return expired_count


