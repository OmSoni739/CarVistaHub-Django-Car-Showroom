"""
DRF Serializers for CarVistaHub Showroom Calendar & Availability (Phase 2).
Enforces role-based privacy sanitization and validates date range parameters.
"""

from rest_framework import serializers


class SlotBookingCustomerSerializer(serializers.Serializer):
    """Sanitized booking preview serializer for regular customers and public viewers."""
    is_my_booking = serializers.BooleanField(default=False)
    booking_id = serializers.IntegerField(required=False, allow_null=True)
    booking_number = serializers.CharField(required=False, allow_null=True)
    status = serializers.CharField(required=False, allow_null=True)
    car_title = serializers.CharField(required=False, allow_null=True)
    date = serializers.CharField(required=False, allow_null=True)
    date_display = serializers.CharField(required=False, allow_null=True)
    slot_time = serializers.CharField(required=False, allow_null=True)
    showroom_location = serializers.CharField(required=False, allow_null=True)
    can_cancel = serializers.BooleanField(required=False, default=False)


class ProposalInfoSerializer(serializers.Serializer):
    """Proposal metadata for manager calendar view."""
    id = serializers.IntegerField()
    proposed_date = serializers.CharField()
    proposed_start_time = serializers.CharField()
    proposed_end_time = serializers.CharField()
    status = serializers.CharField()
    expires_at = serializers.CharField(allow_null=True)


class SlotBookingManagerSerializer(serializers.Serializer):
    """Comprehensive booking metadata serializer strictly for Showroom Managers & Admins."""
    booking_id = serializers.IntegerField()
    booking_number = serializers.CharField()
    customer_name = serializers.CharField()
    customer_email = serializers.EmailField()
    customer_phone = serializers.CharField(allow_blank=True)
    driving_license_number = serializers.CharField(allow_blank=True)
    has_license_image = serializers.BooleanField(default=False)
    license_image_url = serializers.CharField(allow_null=True, required=False)
    license_verification_status = serializers.CharField(default='PENDING')
    license_verification_display = serializers.CharField(default='Pending Review')
    car_id = serializers.IntegerField()
    car_title = serializers.CharField()
    status = serializers.CharField()
    reservation_type = serializers.CharField()
    customer_notes = serializers.CharField(allow_blank=True)
    manager_notes = serializers.CharField(allow_blank=True)
    rejection_reason = serializers.CharField(allow_blank=True, required=False)
    expires_at = serializers.CharField(allow_null=True)
    created_at = serializers.CharField(allow_null=True)
    proposal = ProposalInfoSerializer(required=False, allow_null=True)


class CalendarSlotSerializer(serializers.Serializer):
    """Serializer representing an individual 1-hour appointment slot."""
    date = serializers.CharField()
    start_time = serializers.CharField()
    end_time = serializers.CharField()
    slot_key = serializers.CharField()
    status = serializers.ChoiceField(choices=['AVAILABLE', 'PENDING', 'PROPOSED', 'BOOKED', 'CLOSED', 'LOCKED', 'UNAVAILABLE'])
    is_past = serializers.BooleanField()
    reason = serializers.CharField(allow_null=True)
    booking_details = serializers.JSONField(allow_null=True)


class CalendarDaySerializer(serializers.Serializer):
    """Serializer representing a day's schedule and its slots."""
    date = serializers.CharField()
    weekday = serializers.IntegerField()
    weekday_name = serializers.CharField()
    is_open = serializers.BooleanField()
    closure_reason = serializers.CharField(allow_null=True)
    slots = CalendarSlotSerializer(many=True)


class CalendarAvailabilityResponseSerializer(serializers.Serializer):
    """Top-level response payload for the calendar availability endpoint."""
    start_date = serializers.CharField()
    end_date = serializers.CharField()
    is_manager_view = serializers.BooleanField()
    is_guest_view = serializers.BooleanField(default=False, required=False)
    days = CalendarDaySerializer(many=True)


class CustomerBookingSubmissionSerializer(serializers.Serializer):
    """
    Validates customer test drive appointment booking submission payload.
    Enforces required fields, mandatory front-side driving licence photo upload,
    car availability, and compulsory terms agreement.
    """
    car_id = serializers.IntegerField(required=True)
    preferred_date = serializers.DateField(required=True)
    start_time = serializers.TimeField(required=True, format='%H:%M', input_formats=['%H:%M', '%H:%M:%S'])
    license_image = serializers.ImageField(required=True)
    driving_license_number = serializers.CharField(required=False, allow_blank=True, default='')
    customer_notes = serializers.CharField(required=False, allow_blank=True, default='')
    contact_phone = serializers.CharField(required=False, allow_blank=True, default='')
    terms_agreed = serializers.BooleanField(required=True)

    def validate_preferred_date(self, value):
        from .services import validate_date_in_rolling_window
        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            validate_date_in_rolling_window(value)
            return value
        except DjangoValidationError as err:
            if hasattr(err, 'message_dict') and 'preferred_date' in err.message_dict:
                msg = err.message_dict['preferred_date'][0]
            elif hasattr(err, 'messages'):
                msg = err.messages[0]
            else:
                msg = str(err)
            raise serializers.ValidationError(msg)

    def validate_terms_agreed(self, value):
        if not value:
            raise serializers.ValidationError("You must accept the Terms and Conditions to submit a booking.")
        return value

    def validate_license_image(self, value):
        from .services import validate_driving_license_image
        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            validate_driving_license_image(value)
            return value
        except DjangoValidationError as err:
            msg = err.messages[0] if hasattr(err, 'messages') else str(err)
            raise serializers.ValidationError(msg)

    def validate_car_id(self, value):
        from apps.cars.models import Car
        try:
            Car.objects.get(pk=value, is_available=True)
        except Car.DoesNotExist:
            raise serializers.ValidationError("Selected vehicle is invalid or currently unavailable.")
        return value

    def validate(self, attrs):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            from .services import validate_customer_has_no_active_booking
            from django.core.exceptions import ValidationError as DjangoValidationError
            try:
                validate_customer_has_no_active_booking(request.user)
            except DjangoValidationError as err:
                msg = err.messages[0] if hasattr(err, 'messages') else str(err)
                raise serializers.ValidationError(msg)
        return attrs


class CustomerBookingResponseSerializer(serializers.Serializer):
    """
    Sanitized confirmation payload returned to customer upon successful booking.
    Explicitly omits sensitive full driving licence numbers to ensure customer privacy.
    """
    success = serializers.BooleanField(default=True)
    booking_id = serializers.IntegerField()
    booking_number = serializers.CharField()
    car_title = serializers.CharField()
    date = serializers.CharField()
    start_time = serializers.CharField()
    end_time = serializers.CharField()
    status = serializers.CharField()
    status_display = serializers.CharField()
    expires_at = serializers.CharField(allow_null=True)
    message = serializers.CharField()


