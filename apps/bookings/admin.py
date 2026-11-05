from django.contrib import admin
from .models import (
    TestDriveBooking,
    CarBooking,
    ShowroomSchedule,
    ShowroomClosure,
    BookingProposal,
    BookingActivity,
    ActiveSlotReservation,
)


class BookingProposalInline(admin.TabularInline):
    model = BookingProposal
    extra = 0
    fields = ('proposed_by', 'proposed_date', 'proposed_start_time', 'proposed_end_time', 'status', 'expires_at')
    readonly_fields = ('created_at',)


class ActiveSlotReservationInline(admin.TabularInline):
    model = ActiveSlotReservation
    extra = 0
    fields = ('slot_key', 'slot_date', 'start_time', 'end_time', 'reservation_type', 'expires_at')
    readonly_fields = ('created_at',)


class BookingActivityInline(admin.TabularInline):
    model = BookingActivity
    extra = 0
    fields = ('actor', 'action', 'notes', 'created_at')
    readonly_fields = ('actor', 'action', 'notes', 'created_at')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(TestDriveBooking)
class TestDriveBookingAdmin(admin.ModelAdmin):
    list_display = (
        'booking_number',
        'customer',
        'car',
        'preferred_date',
        'start_time',
        'end_time',
        'assigned_manager',
        'status',
        'created_at',
    )
    list_filter = ('status', 'license_verification_status', 'preferred_date', 'assigned_manager', 'car__brand')
    search_fields = (
        'booking_number',
        'customer__username',
        'customer__email',
        'car__title',
        'driving_license_number',
    )
    ordering = ('-created_at',)
    inlines = [BookingProposalInline, ActiveSlotReservationInline, BookingActivityInline]
    fieldsets = (
        ('Booking Core', {
            'fields': (
                'booking_number',
                'customer',
                'assigned_manager',
                'car',
                'status',
            )
        }),
        ('Appointment Schedule', {
            'fields': (
                'preferred_date',
                'start_time',
                'end_time',
                'time_slot',
                'pending_expires_at',
            )
        }),
        ('Verification & Notes', {
            'fields': (
                'driving_license_number',
                'license_verification_status',
                'customer_notes',
                'manager_notes',
                'rejection_reason',
                'cancellation_reason',
            )
        }),
        ('Timestamps', {
            'fields': (
                'confirmed_at',
                'completed_at',
                'cancelled_at',
                'created_at',
                'updated_at',
            )
        }),
    )
    readonly_fields = ('booking_number', 'created_at', 'updated_at')


@admin.register(ShowroomSchedule)
class ShowroomScheduleAdmin(admin.ModelAdmin):
    list_display = (
        'day_of_week',
        'is_open',
        'open_time',
        'close_time',
        'slot_duration_minutes',
        'is_active',
    )
    list_editable = ('is_open', 'open_time', 'close_time', 'is_active')
    ordering = ('day_of_week',)


@admin.register(ShowroomClosure)
class ShowroomClosureAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'closure_type',
        'specific_date',
        'day_of_week',
        'start_time',
        'end_time',
        'is_recurring',
        'is_active',
    )
    list_filter = ('closure_type', 'is_recurring', 'is_active')
    search_fields = ('title',)
    ordering = ('specific_date', 'day_of_week', 'start_time')


@admin.register(BookingProposal)
class BookingProposalAdmin(admin.ModelAdmin):
    list_display = (
        'booking',
        'proposed_by',
        'proposed_date',
        'proposed_start_time',
        'proposed_end_time',
        'status',
        'expires_at',
        'created_at',
    )
    list_filter = ('status', 'proposed_date')
    search_fields = ('booking__booking_number', 'proposed_by__username', 'manager_note')
    ordering = ('-created_at',)


@admin.register(BookingActivity)
class BookingActivityAdmin(admin.ModelAdmin):
    list_display = ('booking', 'actor', 'action', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('booking__booking_number', 'actor__username', 'notes')
    readonly_fields = ('booking', 'actor', 'action', 'notes', 'created_at')
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ActiveSlotReservation)
class ActiveSlotReservationAdmin(admin.ModelAdmin):
    list_display = (
        'slot_key',
        'slot_date',
        'start_time',
        'end_time',
        'booking',
        'reservation_type',
        'expires_at',
        'created_at',
    )
    list_filter = ('reservation_type', 'slot_date')
    search_fields = ('slot_key', 'booking__booking_number')
    ordering = ('slot_date', 'start_time')


@admin.register(CarBooking)
class CarBookingAdmin(admin.ModelAdmin):
    list_display = (
        'booking_id',
        'customer',
        'car',
        'booking_amount',
        'payment_status',
        'booking_status',
        'created_at',
    )
    list_filter = ('payment_status', 'booking_status', 'created_at', 'car__brand')
    search_fields = ('booking_id', 'customer__username', 'customer__email', 'car__title')
    ordering = ('-created_at',)
