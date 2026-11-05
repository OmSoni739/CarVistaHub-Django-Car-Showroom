import uuid
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from apps.cars.models import Car
from .storage import private_storage


class TestDriveBooking(models.Model):
    """
    Test drive appointment booking request.
    Extended in Phase 1 to support 1-hour slots, Manager assignment,
    multi-step negotiation lifecycle, and reservation tracking.
    """
    class TimeSlot(models.TextChoices):
        MORNING = 'MORNING', 'Morning (9:00 AM - 12:00 PM)'
        AFTERNOON = 'AFTERNOON', 'Afternoon (12:00 PM - 4:00 PM)'
        EVENING = 'EVENING', 'Evening (4:00 PM - 7:00 PM)'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Approval'
        PROPOSED = 'PROPOSED', 'Alternative Proposed'
        CUSTOMER_ACCEPTED = 'CUSTOMER_ACCEPTED', 'Customer Accepted Proposal'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        APPROVED = 'APPROVED', 'Approved (Legacy)'
        REJECTED = 'REJECTED', 'Rejected'
        CANCELLED = 'CANCELLED', 'Cancelled'
        COMPLETED = 'COMPLETED', 'Completed'
        NO_SHOW = 'NO_SHOW', 'Customer No Show'
        EXPIRED = 'EXPIRED', 'Reservation Expired'

    class LicenseVerificationStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending Verification'
        VERIFIED = 'VERIFIED', 'Verified'
        REJECTED = 'REJECTED', 'Rejected'

    booking_number = models.CharField(
        max_length=30,
        unique=True,
        editable=False,
        verbose_name="Booking Number"
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='test_drives',
        verbose_name="Customer"
    )
    assigned_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_test_drives',
        verbose_name="Assigned Showroom Manager"
    )
    car = models.ForeignKey(
        Car,
        on_delete=models.CASCADE,
        related_name='test_drives',
        verbose_name="Car"
    )
    preferred_date = models.DateField(verbose_name="Preferred Test Drive Date")
    start_time = models.TimeField(null=True, blank=True, verbose_name="Slot Start Time")
    end_time = models.TimeField(null=True, blank=True, verbose_name="Slot End Time")
    time_slot = models.CharField(
        max_length=20,
        choices=TimeSlot.choices,
        default=TimeSlot.MORNING,
        blank=True,
        verbose_name="Time Slot (Legacy / Window)"
    )
    driving_license_number = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name="Driving License Number"
    )
    driving_license_image = models.ImageField(
        storage=private_storage,
        upload_to='licenses/%Y/%m/',
        null=True,
        blank=True,
        verbose_name="Driving Licence Image (Front Side)"
    )
    license_verification_status = models.CharField(
        max_length=20,
        choices=LicenseVerificationStatus.choices,
        default=LicenseVerificationStatus.PENDING,
        verbose_name="Driving License Verification Status"
    )
    status = models.CharField(
        max_length=25,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Appointment Status"
    )
    pending_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Pending Expiration Timestamp"
    )
    customer_notes = models.TextField(blank=True, verbose_name="Customer Notes")
    manager_notes = models.TextField(blank=True, verbose_name="Internal Manager Notes")
    rejection_reason = models.TextField(blank=True, verbose_name="Rejection Reason")
    cancellation_reason = models.TextField(blank=True, verbose_name="Cancellation Reason")
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_test_drives',
        verbose_name="Verified By Manager"
    )
    verified_at = models.DateTimeField(null=True, blank=True, verbose_name="Verified At")
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rejected_test_drives',
        verbose_name="Rejected By Manager"
    )
    rejected_at = models.DateTimeField(null=True, blank=True, verbose_name="Rejected At")
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='confirmed_test_drives',
        verbose_name="Confirmed By Manager"
    )
    confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name="Confirmed At")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Completed At")
    cancelled_at = models.DateTimeField(null=True, blank=True, verbose_name="Cancelled At")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Requested At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        verbose_name = "Test Drive Booking"
        verbose_name_plural = "Test Drive Bookings"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['preferred_date', 'status']),
            models.Index(fields=['assigned_manager', 'status']),
            models.Index(fields=['preferred_date', 'start_time']),
        ]

    @property
    def driving_license_verification_status(self):
        """Convenience property for driving license verification status."""
        return self.license_verification_status

    def clean(self):
        super().clean()
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({'end_time': "End time must be after start time."})

    def save(self, *args, **kwargs):
        if not self.booking_number:
            self.booking_number = f"TD-{uuid.uuid4().hex[:8].upper()}"
        # Auto-derive legacy time_slot if start_time is provided
        if self.start_time and not self.time_slot:
            hour = self.start_time.hour
            if hour < 12:
                self.time_slot = self.TimeSlot.MORNING
            elif hour < 16:
                self.time_slot = self.TimeSlot.AFTERNOON
            else:
                self.time_slot = self.TimeSlot.EVENING
        super().save(*args, **kwargs)

    def __str__(self):
        slot_info = f"{self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}" if self.start_time and self.end_time else self.time_slot
        return f"{self.booking_number} - {self.customer.username} ({self.car.title} on {self.preferred_date} {slot_info})"


class ShowroomSchedule(models.Model):
    """
    Configurable showroom operating hours and appointment slot duration.
    Shared showroom-level schedule.
    """
    class Weekday(models.IntegerChoices):
        MONDAY = 0, 'Monday'
        TUESDAY = 1, 'Tuesday'
        WEDNESDAY = 2, 'Wednesday'
        THURSDAY = 3, 'Thursday'
        FRIDAY = 4, 'Friday'
        SATURDAY = 5, 'Saturday'
        SUNDAY = 6, 'Sunday'

    day_of_week = models.IntegerField(
        choices=Weekday.choices,
        unique=True,
        verbose_name="Day of the Week"
    )
    is_open = models.BooleanField(default=True, verbose_name="Is Open")
    open_time = models.TimeField(default="09:00:00", verbose_name="Opening Time")
    close_time = models.TimeField(default="18:00:00", verbose_name="Closing Time")
    slot_duration_minutes = models.PositiveIntegerField(
        default=60,
        verbose_name="Slot Duration (Minutes)"
    )
    is_active = models.BooleanField(default=True, verbose_name="Schedule Rule Active")

    class Meta:
        verbose_name = "Showroom Schedule"
        verbose_name_plural = "Showroom Schedules"
        ordering = ['day_of_week']

    def clean(self):
        super().clean()
        if self.open_time and self.close_time and self.open_time >= self.close_time:
            raise ValidationError({'close_time': "Closing time must be after opening time."})

    def __str__(self):
        status = f"{self.open_time.strftime('%H:%M')} - {self.close_time.strftime('%H:%M')}" if self.is_open else "Closed"
        return f"{self.get_day_of_week_display()}: {status}"


class ShowroomClosure(models.Model):
    """
    Configurable daily breaks (e.g. lunch 13:00-14:00), public holidays,
    full-day closures, and partial-day exceptions.
    """
    class ClosureType(models.TextChoices):
        BREAK = 'BREAK', 'Recurring Daily Break'
        HOLIDAY = 'HOLIDAY', 'Full Day Holiday / Closure'
        PARTIAL = 'PARTIAL', 'Partial Day Closure'
        EXCEPTION = 'EXCEPTION', 'Special Schedule Exception'

    closure_type = models.CharField(
        max_length=20,
        choices=ClosureType.choices,
        default=ClosureType.BREAK,
        verbose_name="Closure Type"
    )
    title = models.CharField(max_length=150, verbose_name="Closure Title / Reason")
    day_of_week = models.IntegerField(
        choices=ShowroomSchedule.Weekday.choices,
        null=True,
        blank=True,
        verbose_name="Day of Week (for Recurring Breaks)"
    )
    specific_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Specific Date (for Holidays/Exceptions)"
    )
    start_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Start Time (for Breaks/Partial Closures)"
    )
    end_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name="End Time (for Breaks/Partial Closures)"
    )
    is_recurring = models.BooleanField(
        default=False,
        verbose_name="Is Weekly Recurring"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Is Active"
    )

    class Meta:
        verbose_name = "Showroom Closure / Break"
        verbose_name_plural = "Showroom Closures & Breaks"
        ordering = ['specific_date', 'day_of_week', 'start_time']
        indexes = [
            models.Index(fields=['closure_type', 'is_active']),
            models.Index(fields=['specific_date']),
            models.Index(fields=['day_of_week']),
        ]

    def clean(self):
        super().clean()
        if self.closure_type == self.ClosureType.BREAK:
            if not self.start_time or not self.end_time:
                raise ValidationError("Start time and end time are required for showroom breaks.")
            if self.start_time >= self.end_time:
                raise ValidationError({'end_time': "Break end time must be after start time."})
        elif self.closure_type == self.ClosureType.PARTIAL:
            if not self.specific_date:
                raise ValidationError({'specific_date': "Specific date is required for partial closures."})
            if not self.start_time or not self.end_time:
                raise ValidationError("Start and end times are required for partial closures.")
            if self.start_time >= self.end_time:
                raise ValidationError({'end_time': "Closure end time must be after start time."})
        elif self.closure_type == self.ClosureType.HOLIDAY:
            if not self.specific_date:
                raise ValidationError({'specific_date': "Specific date is required for holiday closures."})

    def __str__(self):
        if self.closure_type == self.ClosureType.BREAK:
            day_str = self.get_day_of_week_display() if self.day_of_week is not None else "Daily"
            times = f"{self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')}" if self.start_time and self.end_time else ""
            return f"Break: {self.title} ({day_str} {times})"
        elif self.specific_date:
            return f"{self.get_closure_type_display()}: {self.title} on {self.specific_date}"
        return f"{self.get_closure_type_display()}: {self.title}"


class BookingProposal(models.Model):
    """
    Alternative appointment date/time proposed by the Manager.
    Holds the proposed slot while awaiting Customer response.
    """
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Awaiting Customer Response'
        ACCEPTED = 'ACCEPTED', 'Accepted by Customer'
        DECLINED = 'DECLINED', 'Declined by Customer'
        EXPIRED = 'EXPIRED', 'Proposal Expired'

    booking = models.ForeignKey(
        TestDriveBooking,
        on_delete=models.CASCADE,
        related_name='proposals',
        verbose_name="Test Drive Booking"
    )
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_proposals',
        verbose_name="Proposed By"
    )
    proposed_date = models.DateField(verbose_name="Proposed Date")
    proposed_start_time = models.TimeField(verbose_name="Proposed Start Time")
    proposed_end_time = models.TimeField(verbose_name="Proposed End Time")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Proposal Status"
    )
    manager_note = models.TextField(blank=True, verbose_name="Manager Proposal Note")
    customer_response_note = models.TextField(blank=True, verbose_name="Customer Response Note")
    expires_at = models.DateTimeField(verbose_name="Proposal Expiration Timestamp")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")
    responded_at = models.DateTimeField(null=True, blank=True, verbose_name="Responded At")

    class Meta:
        verbose_name = "Booking Proposal"
        verbose_name_plural = "Booking Proposals"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['booking', 'status']),
            models.Index(fields=['proposed_date', 'status']),
            models.Index(fields=['expires_at']),
        ]

    def clean(self):
        super().clean()
        if self.proposed_start_time and self.proposed_end_time:
            if self.proposed_start_time >= self.proposed_end_time:
                raise ValidationError({'proposed_end_time': "Proposed end time must be after start time."})

    def __str__(self):
        return f"Proposal for {self.booking.booking_number} ({self.proposed_date} {self.proposed_start_time.strftime('%H:%M')}) - {self.get_status_display()}"


class BookingActivity(models.Model):
    """
    Append-only audit trail recording every significant event and state transition
    on a test drive booking.
    """
    class Action(models.TextChoices):
        REQUEST_SUBMITTED = 'REQUEST_SUBMITTED', 'Request Submitted'
        MANAGER_ASSIGNED = 'MANAGER_ASSIGNED', 'Manager Assigned'
        CONFIRMED = 'CONFIRMED', 'Booking Confirmed'
        REJECTED = 'REJECTED', 'Booking Rejected'
        ALTERNATIVE_PROPOSED = 'ALTERNATIVE_PROPOSED', 'Alternative Proposed'
        PROPOSAL_ACCEPTED = 'PROPOSAL_ACCEPTED', 'Proposal Accepted by Customer'
        PROPOSAL_DECLINED = 'PROPOSAL_DECLINED', 'Proposal Declined by Customer'
        CANCELLED = 'CANCELLED', 'Booking Cancelled'
        COMPLETED = 'COMPLETED', 'Booking Completed'
        NO_SHOW = 'NO_SHOW', 'Marked No Show'
        EXPIRED = 'EXPIRED', 'Reservation Expired'
        NOTE_ADDED = 'NOTE_ADDED', 'Note Added'
        LICENSE_VERIFIED = 'LICENSE_VERIFIED', 'Licence Verified'
        LICENSE_REJECTED = 'LICENSE_REJECTED', 'Licence Rejected'
        SLOT_RESERVATION_RELEASED = 'SLOT_RESERVATION_RELEASED', 'Slot Reservation Released'

    booking = models.ForeignKey(
        TestDriveBooking,
        on_delete=models.CASCADE,
        related_name='activities',
        verbose_name="Test Drive Booking"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='booking_activities',
        verbose_name="Action Performed By"
    )
    action = models.CharField(
        max_length=40,
        choices=Action.choices,
        verbose_name="Action Type"
    )
    previous_status = models.CharField(
        max_length=40,
        blank=True,
        default='',
        verbose_name="Previous Booking Status"
    )
    new_status = models.CharField(
        max_length=40,
        blank=True,
        default='',
        verbose_name="New Booking Status"
    )
    notes = models.TextField(blank=True, verbose_name="Activity Notes / Metadata")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Logged At")

    class Meta:
        verbose_name = "Booking Activity"
        verbose_name_plural = "Booking Activities"
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['booking', 'created_at']),
            models.Index(fields=['action']),
        ]

    @property
    def actor_display_name(self):
        if self.actor:
            name = self.actor.get_full_name()
            return name if name else self.actor.username
        return "System"

    @property
    def actor_role(self):
        if not self.actor:
            return "System"
        user_type = getattr(self.actor, 'user_type', None)
        if user_type == 'MANAGER':
            return "Showroom Manager"
        elif self.actor.is_staff or user_type == 'ADMIN':
            return "Administrator"
        return "Customer"

    @property
    def activity_type_label(self):
        if self.action == self.Action.NOTE_ADDED:
            notes_lower = self.notes.lower()
            if 'verified' in notes_lower:
                return 'Licence Verified'
            elif 'rejected' in notes_lower:
                return 'Licence Rejected'
            elif 're-upload' in notes_lower:
                return 'Re-upload Requested'
            return 'Note Added'
        elif self.action in (self.Action.REQUEST_SUBMITTED, 'TEST_DRIVE_REQUESTED'):
            return 'Test Drive Requested'
        elif self.action in (self.Action.CONFIRMED, 'TEST_DRIVE_CONFIRMED'):
            return 'Test Drive Confirmed'
        elif self.action in (self.Action.CANCELLED, 'TEST_DRIVE_CANCELLED'):
            return 'Test Drive Cancelled'
        elif self.action in (self.Action.COMPLETED, 'TEST_DRIVE_COMPLETED'):
            return 'Test Drive Completed'
        elif self.action in (self.Action.REJECTED, 'TEST_DRIVE_REJECTED'):
            if 'licence' in self.notes.lower() or 'document' in self.notes.lower():
                return 'Licence Rejected'
            return 'Test Drive Rejected'
        elif self.action in (self.Action.EXPIRED, 'BOOKING_EXPIRED'):
            return 'Reservation Expired'
        elif self.action == self.Action.LICENSE_VERIFIED:
            return 'Licence Verified'
        elif self.action == self.Action.LICENSE_REJECTED:
            return 'Licence Rejected'
        elif self.action == self.Action.SLOT_RESERVATION_RELEASED:
            return 'Slot Reservation Released'
        return self.get_action_display()

    @property
    def badge_class(self):
        label = self.activity_type_label.lower()
        if 'verified' in label:
            return 'badge bg-success-subtle text-success border border-success-subtle'
        elif 'requested' in label:
            return 'badge bg-warning-subtle text-warning-emphasis border border-warning-subtle'
        elif 'rejected' in label:
            return 'badge bg-danger-subtle text-danger border border-danger-subtle'
        elif 'confirmed' in label:
            return 'badge bg-primary text-white'
        elif 'completed' in label:
            return 'badge bg-success text-white'
        elif 'cancelled' in label:
            return 'badge bg-secondary-subtle text-secondary border border-secondary-subtle'
        elif 'expired' in label:
            return 'badge bg-secondary-subtle text-secondary border border-secondary-subtle'
        elif 'released' in label:
            return 'badge bg-info-subtle text-info-emphasis border border-info-subtle'
        return 'badge bg-light text-dark border'

    @property
    def timeline_icon(self):
        label = self.activity_type_label.lower()
        if 'verified' in label:
            return 'verified'
        elif 'requested' in label:
            return 'calendar_month'
        elif 'rejected' in label:
            return 'cancel'
        elif 'confirmed' in label:
            return 'task_alt'
        elif 'completed' in label:
            return 'done_all'
        elif 'cancelled' in label:
            return 'event_busy'
        elif 'expired' in label:
            return 'timer_off'
        elif 'released' in label:
            return 'lock_open'
        return 'info'

    @property
    def display_previous_status(self):
        if self.previous_status:
            return self.previous_status
        if self.action in [self.Action.REQUEST_SUBMITTED]:
            return '—'
        elif self.action in [self.Action.CONFIRMED, self.Action.REJECTED, self.Action.EXPIRED]:
            return 'PENDING'
        elif self.action in [self.Action.CANCELLED, self.Action.COMPLETED]:
            return 'CONFIRMED'
        return '—'

    @property
    def display_new_status(self):
        if self.new_status:
            return self.new_status
        if self.action == self.Action.REQUEST_SUBMITTED:
            return 'PENDING'
        elif self.action == self.Action.CONFIRMED:
            return 'CONFIRMED'
        elif self.action == self.Action.REJECTED:
            return 'REJECTED'
        elif self.action == self.Action.CANCELLED:
            return 'CANCELLED'
        elif self.action == self.Action.COMPLETED:
            return 'COMPLETED'
        elif self.action == self.Action.EXPIRED:
            return 'EXPIRED'
        elif self.action == self.Action.NOTE_ADDED:
            return getattr(self.booking, 'status', 'PENDING')
        return getattr(self.booking, 'status', '—')

    def __str__(self):
        actor_name = self.actor.username if self.actor else "System"
        return f"[{self.created_at.strftime('%Y-%m-%d %H:%M')}] {self.booking.booking_number} - {self.get_action_display()} by {actor_name}"


class ActiveSlotReservation(models.Model):
    """
    Guarantees showroom appointment slot uniqueness and prevents double bookings
    via database-level primary key/unique constraints across both SQLite and MySQL.
    """
    class ReservationType(models.TextChoices):
        PENDING = 'PENDING', 'Pending Reservation'
        CUSTOMER_ACCEPTED = 'CUSTOMER_ACCEPTED', 'Customer Accepted Hold'
        CONFIRMED = 'CONFIRMED', 'Confirmed Booking'
        PROPOSED = 'PROPOSED', 'Manager Proposal Hold'

    slot_key = models.CharField(
        max_length=40,
        unique=True,
        db_index=True,
        verbose_name="Unique Slot Key (YYYY-MM-DD_HH:MM)"
    )
    slot_date = models.DateField(db_index=True, verbose_name="Appointment Date")
    start_time = models.TimeField(verbose_name="Slot Start Time")
    end_time = models.TimeField(verbose_name="Slot End Time")
    booking = models.ForeignKey(
        TestDriveBooking,
        on_delete=models.CASCADE,
        related_name='slot_reservations',
        verbose_name="Test Drive Booking"
    )
    proposal = models.ForeignKey(
        BookingProposal,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='slot_reservations',
        verbose_name="Booking Proposal"
    )
    reservation_type = models.CharField(
        max_length=25,
        choices=ReservationType.choices,
        default=ReservationType.PENDING,
        verbose_name="Reservation Type"
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Reservation Expiration Timestamp"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Reserved At")

    class Meta:
        verbose_name = "Active Slot Reservation"
        verbose_name_plural = "Active Slot Reservations"
        ordering = ['slot_date', 'start_time']
        indexes = [
            models.Index(fields=['slot_date', 'start_time']),
            models.Index(fields=['reservation_type']),
            models.Index(fields=['expires_at']),
        ]

    def save(self, *args, **kwargs):
        if not self.slot_key:
            self.slot_key = self.generate_slot_key(self.slot_date, self.start_time)
        super().save(*args, **kwargs)

    @classmethod
    def generate_slot_key(cls, slot_date, start_time):
        return f"{slot_date.strftime('%Y-%m-%d')}_{start_time.strftime('%H:%M')}"

    def __str__(self):
        return f"{self.slot_key} [{self.get_reservation_type_display()}] -> {self.booking.booking_number}"


class CarBooking(models.Model):
    """
    Online car reservation order.
    """
    class PaymentStatus(models.TextChoices):
        PENDING = 'PENDING', 'Payment Pending'
        PAID = 'PAID', 'Payment Paid'
        FAILED = 'FAILED', 'Payment Failed'
        REFUNDED = 'REFUNDED', 'Payment Refunded'

    class BookingStatus(models.TextChoices):
        PENDING = 'PENDING', 'Reservation Pending'
        CONFIRMED = 'CONFIRMED', 'Reservation Confirmed'
        DELIVERED = 'DELIVERED', 'Vehicle Delivered'
        CANCELLED = 'CANCELLED', 'Reservation Cancelled'

    booking_id = models.CharField(
        max_length=30,
        unique=True,
        editable=False,
        verbose_name="Booking Reference ID"
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='car_bookings',
        verbose_name="Customer"
    )
    car = models.ForeignKey(
        Car,
        on_delete=models.CASCADE,
        related_name='bookings',
        verbose_name="Reserved Car"
    )
    booking_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Advance Booking Fee Paid (₹)"
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        verbose_name="Payment Status"
    )
    booking_status = models.CharField(
        max_length=20,
        choices=BookingStatus.choices,
        default=BookingStatus.PENDING,
        verbose_name="Booking Status"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Booking Date")

    class Meta:
        verbose_name = "Car Booking"
        verbose_name_plural = "Car Bookings"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['customer', 'booking_status']),
            models.Index(fields=['payment_status']),
        ]

    def save(self, *args, **kwargs):
        if not self.booking_id:
            self.booking_id = f"BK-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.booking_id} - {self.customer.username} ({self.car.title})"


class CustomerNotification(models.Model):
    """
    Persistent in-app notification delivered to customers.
    Used for test drive rejection notices, status changes, and alerts.
    """
    class NotificationType(models.TextChoices):
        BOOKING_REJECTED = 'BOOKING_REJECTED', 'Test Drive Request Rejected'
        BOOKING_CONFIRMED = 'BOOKING_CONFIRMED', 'Test Drive Booking Confirmed'
        GENERAL = 'GENERAL', 'General Notice'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='customer_notifications',
        verbose_name="Recipient Customer"
    )
    booking = models.ForeignKey(
        TestDriveBooking,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
        verbose_name="Associated Booking"
    )
    notification_type = models.CharField(
        max_length=30,
        choices=NotificationType.choices,
        default=NotificationType.BOOKING_REJECTED,
        verbose_name="Notification Type"
    )
    title = models.CharField(max_length=200, verbose_name="Notification Title")
    message = models.TextField(verbose_name="Notification Message")
    rejection_reason = models.TextField(blank=True, verbose_name="Rejection Reason")
    booking_reference = models.CharField(max_length=50, blank=True, verbose_name="Booking Reference")
    car_title = models.CharField(max_length=200, blank=True, verbose_name="Vehicle Name")
    slot_date = models.DateField(null=True, blank=True, verbose_name="Appointment Date")
    slot_time = models.CharField(max_length=50, blank=True, verbose_name="Appointment Time Slot")
    showroom_location = models.CharField(
        max_length=200,
        default="CarVistaHub Showroom",
        blank=True,
        verbose_name="Showroom Location"
    )
    is_read = models.BooleanField(default=False, verbose_name="Is Read / Dismissed")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    read_at = models.DateTimeField(null=True, blank=True, verbose_name="Read At")

    class Meta:
        verbose_name = "Customer Notification"
        verbose_name_plural = "Customer Notifications"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at']),
        ]

    def __str__(self):
        return f"Notification for {self.user.username}: {self.title} (Read: {self.is_read})"

