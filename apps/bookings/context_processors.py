"""
Context processors for CarVistaHub customer notifications.
Provides unread notification data for the customer rejection popup.
"""
from apps.bookings.models import CustomerNotification


def customer_notifications(request):
    """
    Exposes customer's unread booking rejection notification to templates.
    Strictly isolated to the authenticated customer; never exposed to other users or managers.
    """
    if not request.user.is_authenticated:
        return {'customer_unread_notification': None}

    # Showroom Managers and Admins have their own dashboards
    if getattr(request.user, 'user_type', None) == 'MANAGER' or request.user.is_staff:
        return {'customer_unread_notification': None}

    latest_unread = CustomerNotification.objects.filter(
        user=request.user,
        notification_type__in=[
            CustomerNotification.NotificationType.BOOKING_REJECTED,
            CustomerNotification.NotificationType.BOOKING_CONFIRMED,
        ],
        is_read=False
    ).select_related('booking', 'booking__car').first()

    return {
        'customer_unread_notification': latest_unread
    }

