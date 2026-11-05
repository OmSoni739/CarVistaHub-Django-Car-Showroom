"""
REST API Views for CarVistaHub Showroom Bookings & Scheduling (Phase 2).
Provides the shared calendar availability endpoint with role-based data filtering.
"""

import datetime
import mimetypes
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from apps.cars.models import Car
from .models import TestDriveBooking, CustomerNotification
from .services import (
    get_showroom_calendar_availability,
    create_customer_test_drive_booking,
    manager_update_license_verification,
    manager_confirm_test_drive_booking,
    customer_cancel_test_drive_booking,
    manager_complete_test_drive_booking,
    is_manager_or_admin,
    get_rolling_booking_window,
    ManagerNotConfiguredError,
    SlotUnavailableError,
)
from .serializers import (
    CalendarAvailabilityResponseSerializer,
    CustomerBookingSubmissionSerializer,
    CustomerBookingResponseSerializer,
)

User = get_user_model()


class CalendarAvailabilityAPIView(APIView):
    """
    GET /bookings/api/calendar/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD

    Retrieves showroom appointment slot availability for the specified date range.
    Dynamically generates 1-hour slots, suppresses past times and daily breaks/holidays,
    and applies role-based privacy filters (scrubbing other customers' PII for customers).
    """
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        today, max_date = get_rolling_booking_window()
        is_mgr = is_manager_or_admin(request.user)

        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        car_id_str = request.query_params.get('car_id')

        # 1. Parse & Validate start_date
        if start_date_str:
            try:
                start_date = datetime.date.fromisoformat(start_date_str.strip())
            except (ValueError, TypeError):
                return Response(
                    {"error": "Invalid start_date format. Expected YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            start_date = today

        # 2. Parse & Validate end_date
        if end_date_str:
            try:
                end_date = datetime.date.fromisoformat(end_date_str.strip())
            except (ValueError, TypeError):
                return Response(
                    {"error": "Invalid end_date format. Expected YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            if is_mgr:
                # Default Manager view to 7-day rolling window
                end_date = start_date + datetime.timedelta(days=6)
            else:
                # Default Customer/Guest view to rolling 7-day window
                end_date = max_date

        # 3. Validate chronological order
        if start_date > end_date:
            return Response(
                {"error": "start_date cannot be after end_date."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 4. Enforce rolling 7-day booking window for customers & guests
        if not is_mgr:
            if start_date < today:
                return Response(
                    {
                        "error": (
                            f"Requested date cannot be in the past. "
                            f"Appointments are only available for the next 7 days ({today.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')})."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            if start_date > max_date:
                return Response(
                    {
                        "error": (
                            f"Requested date is beyond the 7-day booking window. "
                            f"Appointments are only available for the next 7 days ({today.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')})."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            if end_date > max_date:
                return Response(
                    {
                        "error": (
                            f"Requested date range exceeds the 7-day booking window. "
                            f"Appointments are only available for the next 7 days ({today.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')})."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            # 5. Enforce maximum date range (31 days) for Manager/Admin queries
            if (end_date - start_date).days > 31:
                return Response(
                    {"error": "Date range cannot exceed 31 days per request."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # 5. Optional car_id
        car_id = None
        if car_id_str:
            try:
                car_id = int(car_id_str.strip())
            except (ValueError, TypeError):
                pass

        # 6. Retrieve calendar availability
        availability_data = get_showroom_calendar_availability(
            start_date=start_date,
            end_date=end_date,
            user=request.user,
            car_id=car_id
        )

        serializer = CalendarAvailabilityResponseSerializer(availability_data)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CustomerBookingSubmissionAPIView(APIView):
    """
    POST /bookings/api/book/

    Receives customer test drive appointment booking request.
    Enforces customer authentication, server-side schedule and slot availability
    verification, single active Manager assignment, mandatory front-side driving licence
    photo upload (stored with status PENDING), and atomic database reservation with 24-hour hold.
    """
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, *args, **kwargs):
        # 1. Enforce authentication
        if not request.user or not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required. Please log in or sign up to book a test drive."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # 2. Enforce Customer role strictly (Admins & Managers cannot submit customer bookings)
        if getattr(request.user, 'user_type', None) != User.UserType.CUSTOMER:
            return Response(
                {"error": "Only registered customers can book a test drive appointment."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 3. Validate input payload (supports multipart/form-data with file upload)
        serializer = CustomerBookingSubmissionSerializer(data=request.data)
        if not serializer.is_valid():
            first_err = "Invalid booking submission data."
            for field, field_errs in serializer.errors.items():
                if field_errs:
                    first_err = field_errs[0] if isinstance(field_errs, list) else str(field_errs)
                    break
            return Response(
                {"error": first_err, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        validated_data = serializer.validated_data

        # 4. Retrieve Car model from DB (never trust client title or pricing)
        try:
            car = Car.objects.get(pk=validated_data['car_id'], is_available=True)
        except Car.DoesNotExist:
            return Response(
                {"error": "The selected vehicle is invalid or currently unavailable for showroom test drives."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 5. Execute booking creation service with uploaded front-side DL image
        try:
            booking = create_customer_test_drive_booking(
                customer=request.user,
                car=car,
                preferred_date=validated_data['preferred_date'],
                start_time=validated_data['start_time'],
                license_image=validated_data.get('license_image'),
                driving_license_number=validated_data.get('driving_license_number', ''),
                customer_notes=validated_data.get('customer_notes', ''),
                contact_phone=validated_data.get('contact_phone', ''),
                terms_agreed=validated_data['terms_agreed'],
            )
        except ManagerNotConfiguredError as err:
            return Response(
                {
                    "error": (
                        "Test drive bookings are temporarily unavailable as no active Showroom Manager "
                        "is currently configured. Please contact the showroom or try again later."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except SlotUnavailableError as err:
            msg = err.messages[0] if hasattr(err, 'messages') else str(err)
            return Response(
                {"error": msg},
                status=status.HTTP_409_CONFLICT
            )
        except ValidationError as err:
            if hasattr(err, 'message_dict'):
                msg = next(iter(err.message_dict.values()))[0]
            elif hasattr(err, 'messages'):
                msg = err.messages[0]
            else:
                msg = str(err)
            return Response(
                {"error": msg},
                status=status.HTTP_400_BAD_REQUEST
            )
        except PermissionDenied as err:
            return Response(
                {"error": str(err)},
                status=status.HTTP_403_FORBIDDEN
            )

        # 6. Build sanitized response payload (DL image and numbers strictly excluded for customer privacy)
        car_display = f"{booking.car.brand.name} {booking.car.title}" if getattr(booking.car, 'brand', None) else booking.car.title
        response_payload = {
            "success": True,
            "booking_id": booking.id,
            "booking_number": booking.booking_number,
            "car_title": car_display,
            "date": booking.preferred_date.strftime('%Y-%m-%d'),
            "start_time": booking.start_time.strftime('%H:%M'),
            "end_time": booking.end_time.strftime('%H:%M'),
            "status": booking.status,
            "status_display": "Pending Manager Review",
            "expires_at": booking.pending_expires_at.isoformat() if booking.pending_expires_at else None,
            "message": "Your test drive booking request has been submitted successfully.",
        }

        return Response(response_payload, status=status.HTTP_201_CREATED)


class SecureLicenseImageView(APIView):
    """
    GET /bookings/secure-document/<int:booking_id>/license/

    Securely streams the customer's uploaded front-side driving licence photo.
    Strictly restricted to authorized Showroom Managers and Administrators.
    Guests, other customers, and unauthorized accounts receive 401 or 403 Forbidden.
    """
    permission_classes = [AllowAny]

    def get(self, request, booking_id, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required to access customer documents."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not is_manager_or_admin(request.user):
            return Response(
                {"error": "Access denied. Only authorized Showroom Managers can view sensitive licence documents."},
                status=status.HTTP_403_FORBIDDEN
            )

        booking = get_object_or_404(TestDriveBooking, pk=booking_id)

        # If user is a Showroom Manager, enforce assignment check if manager is configured
        if getattr(request.user, 'user_type', None) == User.UserType.MANAGER:
            if booking.assigned_manager_id and booking.assigned_manager_id != request.user.id and not request.user.is_staff:
                return Response(
                    {"error": "Access denied. You are not the assigned Showroom Manager for this booking."},
                    status=status.HTTP_403_FORBIDDEN
                )

        if not booking.driving_license_image:
            raise Http404("No driving licence document has been uploaded for this appointment.")

        try:
            file_obj = booking.driving_license_image.open('rb')
        except Exception:
            raise Http404("Document file could not be read or does not exist on disk.")

        content_type, _ = mimetypes.guess_type(booking.driving_license_image.name)
        if not content_type:
            content_type = 'image/jpeg'

        response = FileResponse(file_obj, content_type=content_type)
        response['Content-Disposition'] = 'inline; filename="driving_licence_front.jpg"'
        response['Cache-Control'] = 'private, no-cache, no-store, must-revalidate'
        return response


class ManagerLicenseVerificationAPIView(APIView):
    """
    POST /bookings/api/manager/bookings/<int:booking_id>/license-action/

    Processes Showroom Manager review decisions on customer driving licence documents:
      - VERIFY: changes license_verification_status to VERIFIED, records manager and timestamp
      - REJECT: changes license_verification_status and booking.status to REJECTED,
                records mandatory reason, releases ActiveSlotReservation, sends customer notification
    """
    permission_classes = [AllowAny]

    def post(self, request, booking_id, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not is_manager_or_admin(request.user):
            return Response(
                {"error": "Access denied. Only authorized Showroom Managers can perform document verification."},
                status=status.HTTP_403_FORBIDDEN
            )

        booking = get_object_or_404(TestDriveBooking, pk=booking_id)

        action = request.data.get('action')
        reason = request.data.get('reason', '')

        if not action:
            return Response(
                {"error": "Action parameter is required ('VERIFY' or 'REJECT')."},
                status=status.HTTP_400_BAD_REQUEST
            )

        action_upper = str(action).strip().upper()
        if action_upper not in ['VERIFY', 'REJECT']:
            return Response(
                {"error": f"Invalid verification action '{action}'. Permitted actions: VERIFY, REJECT."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            result = manager_update_license_verification(
                booking=booking,
                manager=request.user,
                action=action_upper,
                reason=reason
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValidationError as err:
            msg = err.messages[0] if hasattr(err, 'messages') else str(err)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionDenied as err:
            return Response({"error": str(err)}, status=status.HTTP_403_FORBIDDEN)


class ManagerBookingConfirmationAPIView(APIView):
    """
    POST /bookings/api/manager/bookings/<int:booking_id>/confirm/

    Showroom Manager final test-drive confirmation endpoint (Stage 2).
    Confirms the appointment, permanently locks the ActiveSlotReservation,
    and creates a persistent in-app CustomerNotification.
    """
    permission_classes = [AllowAny]

    def post(self, request, booking_id, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not is_manager_or_admin(request.user):
            return Response(
                {"error": "Access denied. Only authorized Showroom Managers can confirm appointments."},
                status=status.HTTP_403_FORBIDDEN
            )

        booking = get_object_or_404(TestDriveBooking, pk=booking_id)

        try:
            result = manager_confirm_test_drive_booking(
                booking=booking,
                manager=request.user
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValidationError as err:
            msg = err.messages[0] if hasattr(err, 'messages') else str(err)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionDenied as err:
            return Response({"error": str(err)}, status=status.HTTP_403_FORBIDDEN)


class CustomerNotificationDismissAPIView(APIView):
    """
    POST /bookings/api/notifications/<int:notification_id>/dismiss/

    Marks a customer in-app notification as read/dismissed.
    Strictly restricted to the notification recipient.
    """
    def post(self, request, notification_id, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        notification = get_object_or_404(CustomerNotification, pk=notification_id)
        if notification.user_id != request.user.id and not request.user.is_staff:
            return Response(
                {"error": "Access denied. You cannot modify notifications for other users."},
                status=status.HTTP_403_FORBIDDEN
            )

        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=['is_read', 'read_at'])

        return Response({
            "success": True,
            "message": "Notification marked as read."
        }, status=status.HTTP_200_OK)


class CustomerUnreadNotificationAPIView(APIView):
    """
    GET /bookings/api/notifications/unread/

    Returns the latest unread persistent notification (confirmation or rejection)
    for the logged-in customer.
    """
    def get(self, request, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return Response({"has_unread": False, "notification": None})

        if getattr(request.user, 'user_type', None) == User.UserType.MANAGER or request.user.is_staff:
            return Response({"has_unread": False, "notification": None})

        notification = CustomerNotification.objects.filter(
            user=request.user,
            notification_type__in=[
                CustomerNotification.NotificationType.BOOKING_REJECTED,
                CustomerNotification.NotificationType.BOOKING_CONFIRMED,
            ],
            is_read=False
        ).select_related('booking', 'booking__car').first()

        if not notification:
            return Response({"has_unread": False, "notification": None})

        status_display = "CONFIRMED" if notification.notification_type == CustomerNotification.NotificationType.BOOKING_CONFIRMED else "REJECTED"

        return Response({
            "has_unread": True,
            "notification": {
                "id": notification.id,
                "type": notification.notification_type,
                "title": notification.title,
                "message": notification.message,
                "booking_reference": notification.booking_reference,
                "car_title": notification.car_title,
                "slot_date": notification.slot_date.strftime('%Y-%m-%d') if notification.slot_date else '',
                "slot_date_display": notification.slot_date.strftime('%a, %d %b %Y') if notification.slot_date else '',
                "slot_time": notification.slot_time,
                "showroom_location": getattr(notification, 'showroom_location', 'CarVistaHub Showroom') or 'CarVistaHub Showroom',
                "status_display": status_display,
                "rejection_reason": notification.rejection_reason,
                "created_at": notification.created_at.isoformat(),
            }
        })


class CustomerBookingDetailsAPIView(APIView):
    """
    GET /bookings/api/bookings/<int:booking_id>/details/

    Customer retrieves details of their confirmed/reserved test drive appointment.
    Strictly isolated: Customers can only access their own booking details.
    """
    def get(self, request, booking_id, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        booking = get_object_or_404(TestDriveBooking, pk=booking_id)

        if booking.customer_id != request.user.id and not request.user.is_staff and not is_manager_or_admin(request.user):
            return Response(
                {"error": "Access denied. You can only view details for your own test-drive appointments."},
                status=status.HTTP_403_FORBIDDEN
            )

        car_display = f"{booking.car.brand.name} {booking.car.title}" if getattr(booking.car, 'brand', None) else booking.car.title
        slot_time_str = f"{booking.start_time.strftime('%H:%M')} - {booking.end_time.strftime('%H:%M')}" if booking.start_time and booking.end_time else booking.time_slot

        return Response({
            "success": True,
            "booking": {
                "id": booking.id,
                "booking_number": booking.booking_number,
                "car_title": car_display,
                "date": booking.preferred_date.strftime('%Y-%m-%d'),
                "date_display": booking.preferred_date.strftime('%a, %d %b %Y'),
                "slot_time": slot_time_str,
                "showroom_location": "CarVistaHub Showroom",
                "status": booking.status,
                "status_display": booking.get_status_display(),
                "can_cancel": bool(booking.status == TestDriveBooking.Status.CONFIRMED),
            }
        })


class CustomerBookingCancelAPIView(APIView):
    """
    POST /bookings/api/bookings/<int:booking_id>/cancel/

    Customer cancels their confirmed test-drive appointment.
    Strictly restricted to the booking owner.
    Releases the ActiveSlotReservation and updates the status to CANCELLED.
    """
    def post(self, request, booking_id, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        booking = get_object_or_404(TestDriveBooking, pk=booking_id)

        try:
            result = customer_cancel_test_drive_booking(
                booking=booking,
                customer=request.user,
                reason=request.data.get('reason', '')
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValidationError as err:
            msg = err.messages[0] if hasattr(err, 'messages') else str(err)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionDenied as err:
            return Response({"error": str(err)}, status=status.HTTP_403_FORBIDDEN)


class ManagerBookingCompleteAPIView(APIView):
    """
    POST /bookings/api/manager/bookings/<int:booking_id>/complete/

    Showroom Manager marks a confirmed test-drive booking as COMPLETED.
    Strictly restricted to authorized Showroom Managers and Admins.
    Cannot be marked completed before the scheduled appointment end time.
    """
    permission_classes = [AllowAny]

    def post(self, request, booking_id, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not is_manager_or_admin(request.user):
            return Response(
                {"error": "Access denied. Only authorized Showroom Managers can mark appointments completed."},
                status=status.HTTP_403_FORBIDDEN
            )

        booking = get_object_or_404(TestDriveBooking, pk=booking_id)

        try:
            result = manager_complete_test_drive_booking(
                booking=booking,
                manager=request.user
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValidationError as err:
            msg = err.messages[0] if hasattr(err, 'messages') else str(err)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionDenied as err:
            return Response({"error": str(err)}, status=status.HTTP_403_FORBIDDEN)




