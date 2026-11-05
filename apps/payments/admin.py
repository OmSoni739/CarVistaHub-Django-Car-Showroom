from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('razorpay_order_id', 'booking', 'amount', 'currency', 'payment_method', 'payment_status', 'paid_at', 'created_at')
    list_filter = ('payment_status', 'currency', 'created_at')
    search_fields = ('razorpay_order_id', 'razorpay_payment_id', 'booking__booking_id', 'booking__customer__username')
    ordering = ('-created_at',)
