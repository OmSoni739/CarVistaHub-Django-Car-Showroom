from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    # Manager Showroom Calendar Portal Route
    path('manager/calendar/', views.manager_calendar_view, name='manager_calendar'),
    # Manager Test Drive Records & Audit Logs Route
    path('manager/records/', views.manager_records_view, name='manager_records'),
    # Manager Vehicle Reservation Records Route (Read-Only)
    path('manager/vehicle-reservations/', views.manager_vehicle_reservations_view, name='manager_vehicle_reservations'),
    # Manager Booking Activity Timeline JSON API Route
    path('manager/records/<int:booking_id>/timeline/', views.manager_booking_timeline_api, name='manager_booking_timeline'),
    # Customer Vehicle Reservations Route
    path('vehicle-reservations/', views.vehicle_reservations_view, name='vehicle_reservations'),
    # Customer Test Drive Appointments Route
    path('test-drive-appointments/', views.test_drive_appointments_view, name='test_drive_appointments'),
    # Customer Booking History Portal Route (Backward-Compatible Alias)
    path('my-bookings/', views.customer_bookings_view, name='customer_bookings'),
]
