from django.db import models
from apps.bookings.models import CarBooking


class Payment(models.Model):
    """
    Razorpay payment transaction and verification record.
    """
    class PaymentStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        SUCCESS = 'SUCCESS', 'Success'
        FAILED = 'FAILED', 'Failed'
        REFUNDED = 'REFUNDED', 'Refunded'

    booking = models.OneToOneField(
        CarBooking,
        on_delete=models.CASCADE,
        related_name='payment',
        verbose_name="Car Booking Order"
    )
    razorpay_order_id = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Razorpay Order ID"
    )
    razorpay_payment_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Razorpay Payment ID"
    )
    razorpay_signature = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Razorpay Signature"
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Transaction Amount (₹)"
    )
    currency = models.CharField(
        max_length=10,
        default='INR',
        verbose_name="Currency"
    )
    payment_method = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Payment Method (Card/UPI/Netbanking)"
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        verbose_name="Payment Status"
    )
    paid_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Payment Timestamp"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Record Created At"
    )

    class Meta:
        verbose_name = "Payment Transaction"
        verbose_name_plural = "Payment Transactions"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['razorpay_order_id']),
            models.Index(fields=['payment_status']),
        ]

    def __str__(self):
        return f"Payment {self.razorpay_order_id} - ₹{self.amount} ({self.get_payment_status_display()})"
