from django.urls import path
from apps.dashboard.views import customer_bookings_view, test_drive_appointments_view
from .api_views import (
    CalendarAvailabilityAPIView,
    CustomerBookingSubmissionAPIView,
    SecureLicenseImageView,
    ManagerLicenseVerificationAPIView,
    ManagerBookingConfirmationAPIView,
    CustomerBookingDetailsAPIView,
    CustomerBookingCancelAPIView,
    ManagerBookingCompleteAPIView,
    CustomerNotificationDismissAPIView,
    CustomerUnreadNotificationAPIView,
)

app_name = 'bookings'

urlpatterns = [
    # Showroom Test Drive Calendar Availability API
    path('api/calendar/', CalendarAvailabilityAPIView.as_view(), name='api_calendar_availability'),
    # Customer Test Drive Booking Submission API
    path('api/book/', CustomerBookingSubmissionAPIView.as_view(), name='api_booking_submission'),
    # Customer Test Drive Appointments Route
    path('test-drive-appointments/', test_drive_appointments_view, name='test_drive_appointments'),
    # Customer Booking History Portal Route (Legacy)
    path('my-bookings/', customer_bookings_view, name='customer_bookings'),
    # Secure Manager-only Driving Licence Document Viewer
    path('secure-document/<int:booking_id>/license/', SecureLicenseImageView.as_view(), name='secure_license_image'),
    # Manager Driving Licence Verification Action Endpoint
    path('api/manager/bookings/<int:booking_id>/license-action/', ManagerLicenseVerificationAPIView.as_view(), name='manager_license_action'),
    # Manager Booking Final Confirmation Endpoint
    path('api/manager/bookings/<int:booking_id>/confirm/', ManagerBookingConfirmationAPIView.as_view(), name='manager_booking_confirm'),
    # Manager Booking Mark Completed Endpoint
    path('api/manager/bookings/<int:booking_id>/complete/', ManagerBookingCompleteAPIView.as_view(), name='manager_booking_complete'),
    # Customer Booking Details & Cancellation Endpoints
    path('api/bookings/<int:booking_id>/details/', CustomerBookingDetailsAPIView.as_view(), name='api_booking_details'),
    path('api/bookings/<int:booking_id>/cancel/', CustomerBookingCancelAPIView.as_view(), name='api_booking_cancel'),
    # Customer In-App Notification Dismiss & Unread Query Endpoints
    path('api/notifications/<int:notification_id>/dismiss/', CustomerNotificationDismissAPIView.as_view(), name='api_notification_dismiss'),
    path('api/notifications/unread/', CustomerUnreadNotificationAPIView.as_view(), name='api_notification_unread'),
]
