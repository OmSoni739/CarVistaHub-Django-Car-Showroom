from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    # Razorpay Order Creation Endpoint
    path('api/create-order/', views.create_booking_payment_order, name='create_order'),
    # Razorpay Payment Signature Verification & Capture Processing Endpoint
    path('api/verify-payment/', views.verify_payment_callback, name='verify_payment'),
    # Customer Booking & Payment Realtime Status Endpoint
    path('api/booking-status/<str:booking_id>/', views.booking_status_api, name='booking_status'),
    # Customer Booking Confirmation Receipt Page
    path('success/<str:booking_id>/', views.booking_success_view, name='booking_success'),
]
