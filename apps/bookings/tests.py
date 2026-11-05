import datetime
import io
import zoneinfo
from PIL import Image
from django.conf import settings
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from apps.cars.models import Car, Brand
from .models import (
    TestDriveBooking,
    ShowroomSchedule,
    ShowroomClosure,
    BookingProposal,
    BookingActivity,
    ActiveSlotReservation,
    CustomerNotification,
)
from .services import (
    get_assigned_manager,
    generate_showroom_daily_slots,
    ManagerNotConfiguredError,
    validate_and_normalize_indian_dl,
    validate_driving_license_image,
    create_customer_test_drive_booking,
    manager_update_license_verification,
    validate_booking_confirmation,
    SlotUnavailableError,
)

def create_test_image(filename="license_front.jpg", size=(200, 100), color=(0, 120, 200), format="JPEG"):
    file_obj = io.BytesIO()
    image = Image.new("RGB", size, color=color)
    image.save(file_obj, format=format)
    file_obj.seek(0)
    content_type = "image/jpeg" if format.upper() == "JPEG" else "image/png"
    return SimpleUploadedFile(filename, file_obj.read(), content_type=content_type)


User = get_user_model()


class ManagerRoleAndConstraintTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username='test_customer',
            email='customer@example.com',
            password='Password123!',
            user_type=User.UserType.CUSTOMER
        )

    def test_manager_user_type_choice_available(self):
        """Verifies User.UserType.MANAGER is an available choice."""
        self.assertIn(('MANAGER', 'Showroom Manager'), User.UserType.choices)

    def test_get_active_manager_none_initially(self):
        """Verifies get_active_manager returns None when no manager account exists."""
        self.assertIsNone(User.get_active_manager())

    def test_get_assigned_manager_raises_error_when_no_manager(self):
        """Verifies get_assigned_manager raises ManagerNotConfiguredError when missing."""
        with self.assertRaises(ManagerNotConfiguredError) as ctx:
            get_assigned_manager()
        self.assertIn("No active Showroom Manager", str(ctx.exception))

    def test_single_active_manager_creation_and_resolution(self):
        """Verifies an active manager can be created and retrieved."""
        manager = User.objects.create_user(
            username='showroom_mgr',
            email='manager@example.com',
            password='ManagerPass123!',
            user_type=User.UserType.MANAGER,
            is_active=True
        )
        self.assertEqual(User.get_active_manager(), manager)
        self.assertEqual(get_assigned_manager(), manager)

    def test_prevent_second_active_manager_via_clean(self):
        """Verifies that activating a second manager raises ValidationError."""
        User.objects.create_user(
            username='first_manager',
            email='mgr1@example.com',
            password='PassWord123!',
            user_type=User.UserType.MANAGER,
            is_active=True
        )

        second_manager = User(
            username='second_manager',
            email='mgr2@example.com',
            user_type=User.UserType.MANAGER,
            is_active=True
        )
        with self.assertRaises(ValidationError) as ctx:
            second_manager.clean()
        self.assertIn('user_type', ctx.exception.message_dict)
        self.assertIn('Only one active Showroom Manager account is allowed', ctx.exception.message_dict['user_type'][0])

    def test_second_inactive_manager_allowed(self):
        """Verifies a second manager account with is_active=False is allowed."""
        User.objects.create_user(
            username='active_manager',
            email='active@example.com',
            password='PassWord123!',
            user_type=User.UserType.MANAGER,
            is_active=True
        )

        inactive_manager = User(
            username='backup_manager',
            email='backup@example.com',
            user_type=User.UserType.MANAGER,
            is_active=False
        )
        # Should not raise validation error
        inactive_manager.clean()
        inactive_manager.save()
        self.assertEqual(User.get_active_manager().username, 'active_manager')


class ShowroomScheduleAndClosureTests(TestCase):
    def test_initial_schedules_exist_for_all_weekdays(self):
        """Verifies initial data migration initialized schedules for days 0-6 (09:00-18:00)."""
        self.assertEqual(ShowroomSchedule.objects.count(), 7)
        for s in ShowroomSchedule.objects.all():
            self.assertTrue(s.is_open)
            self.assertEqual(s.open_time, datetime.time(9, 0))
            self.assertEqual(s.close_time, datetime.time(18, 0))
            self.assertEqual(s.slot_duration_minutes, 60)

    def test_initial_lunch_breaks_exist(self):
        """Verifies daily lunch break (13:00 - 14:00) exists."""
        breaks = ShowroomClosure.objects.filter(closure_type=ShowroomClosure.ClosureType.BREAK)
        self.assertGreaterEqual(breaks.count(), 7)
        for b in breaks:
            self.assertEqual(b.start_time, datetime.time(13, 0))
            self.assertEqual(b.end_time, datetime.time(14, 0))

    def test_schedule_validation_rejects_closing_before_opening(self):
        """Verifies ShowroomSchedule.clean rejects open_time >= close_time."""
        schedule = ShowroomSchedule(
            day_of_week=0,
            open_time=datetime.time(18, 0),
            close_time=datetime.time(9, 0)
        )
        with self.assertRaises(ValidationError):
            schedule.clean()

    def test_closure_validation_rejects_end_before_start(self):
        """Verifies ShowroomClosure.clean rejects start_time >= end_time."""
        closure = ShowroomClosure(
            closure_type=ShowroomClosure.ClosureType.BREAK,
            title='Bad Break',
            start_time=datetime.time(14, 0),
            end_time=datetime.time(13, 0)
        )
        with self.assertRaises(ValidationError):
            closure.clean()


class DynamicSlotGenerationTests(TestCase):
    def test_generate_daily_slots_expected_eight_slots(self):
        """
        Verifies standard operating day generates exactly 8 one-hour slots:
        09:00-10:00, 10:00-11:00, 11:00-12:00, 12:00-13:00,
        14:00-15:00, 15:00-16:00, 16:00-17:00, 17:00-18:00.
        Excludes 13:00-14:00 lunch break.
        """
        test_date = datetime.date(2026, 11, 2)  # Monday
        slots = generate_showroom_daily_slots(test_date)

        self.assertEqual(len(slots), 8)

        expected_starts = [
            datetime.time(9, 0),
            datetime.time(10, 0),
            datetime.time(11, 0),
            datetime.time(12, 0),
            datetime.time(14, 0),
            datetime.time(15, 0),
            datetime.time(16, 0),
            datetime.time(17, 0),
        ]

        actual_starts = [s['start_time'] for s in slots]
        self.assertEqual(actual_starts, expected_starts)

        # Confirm 13:00 - 14:00 is explicitly absent
        self.assertNotIn(datetime.time(13, 0), actual_starts)

    def test_generate_daily_slots_full_day_holiday_returns_zero(self):
        """Verifies full-day holiday closure suppresses all slots for that date."""
        holiday_date = datetime.date(2026, 11, 4)
        ShowroomClosure.objects.create(
            closure_type=ShowroomClosure.ClosureType.HOLIDAY,
            title='Diwali Festival',
            specific_date=holiday_date,
            is_active=True
        )

        slots = generate_showroom_daily_slots(holiday_date)
        self.assertEqual(len(slots), 0)

    def test_generate_daily_slots_closed_weekday_returns_zero(self):
        """Verifies day with is_open=False returns 0 slots."""
        # Close Sunday (day 6)
        sunday_schedule = ShowroomSchedule.objects.get(day_of_week=6)
        sunday_schedule.is_open = False
        sunday_schedule.save()

        sunday_date = datetime.date(2026, 11, 8)  # Sunday
        slots = generate_showroom_daily_slots(sunday_date)
        self.assertEqual(len(slots), 0)


class BookingModelsAndLifecycleTests(TestCase):
    def setUp(self):
        self.brand = Brand.objects.create(name='Audi', slug='audi')
        self.car = Car.objects.create(
            title='Audi A4',
            slug='audi-a4',
            brand=self.brand,
            price=4500000,
            booking_amount=50000,
            is_available=True
        )
        self.customer = User.objects.create_user(
            username='arjun_k',
            email='arjun@example.com',
            password='Password123!',
            user_type=User.UserType.CUSTOMER
        )
        self.manager = User.objects.create_user(
            username='mgr_vikram',
            email='vikram@example.com',
            password='Password123!',
            user_type=User.UserType.MANAGER,
            is_active=True
        )

    def test_create_test_drive_booking_with_extended_fields(self):
        """Verifies TestDriveBooking can be created with 1-hour slot and manager."""
        preferred_date = datetime.date(2026, 11, 5)
        start_time = datetime.time(10, 0)
        end_time = datetime.time(11, 0)
        expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)

        booking = TestDriveBooking.objects.create(
            customer=self.customer,
            assigned_manager=self.manager,
            car=self.car,
            preferred_date=preferred_date,
            start_time=start_time,
            end_time=end_time,
            driving_license_number='MH-0120150001234',
            status=TestDriveBooking.Status.PENDING,
            pending_expires_at=expires_at,
            customer_notes='Interested in Technology pack'
        )

        self.assertTrue(booking.booking_number.startswith('TD-'))
        self.assertEqual(booking.status, TestDriveBooking.Status.PENDING)
        self.assertEqual(booking.assigned_manager, self.manager)
        self.assertEqual(booking.start_time, start_time)
        self.assertEqual(booking.end_time, end_time)
        self.assertEqual(booking.time_slot, TestDriveBooking.TimeSlot.MORNING)  # derived from 10:00

    def test_all_lifecycle_statuses_valid(self):
        """Verifies all required lifecycle statuses exist and can be assigned."""
        expected_statuses = [
            'PENDING',
            'PROPOSED',
            'CUSTOMER_ACCEPTED',
            'CONFIRMED',
            'APPROVED',
            'REJECTED',
            'CANCELLED',
            'COMPLETED',
            'NO_SHOW',
            'EXPIRED',
        ]
        available_status_keys = [c[0] for c in TestDriveBooking.Status.choices]
        for st in expected_statuses:
            self.assertIn(st, available_status_keys)

    def test_booking_proposal_creation(self):
        """Verifies BookingProposal records alternative date/time from manager."""
        booking = TestDriveBooking.objects.create(
            customer=self.customer,
            car=self.car,
            preferred_date=datetime.date(2026, 11, 5),
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            driving_license_number='MH-0120150001234'
        )

        proposal = BookingProposal.objects.create(
            booking=booking,
            proposed_by=self.manager,
            proposed_date=datetime.date(2026, 11, 6),
            proposed_start_time=datetime.time(14, 0),
            proposed_end_time=datetime.time(15, 0),
            status=BookingProposal.Status.PENDING,
            manager_note='Car available on Friday 2pm',
            expires_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)
        )

        self.assertEqual(booking.proposals.count(), 1)
        self.assertEqual(proposal.status, BookingProposal.Status.PENDING)

    def test_booking_activity_append_only(self):
        """Verifies BookingActivity records audit events."""
        booking = TestDriveBooking.objects.create(
            customer=self.customer,
            car=self.car,
            preferred_date=datetime.date(2026, 11, 5),
            driving_license_number='MH-0120150001234'
        )

        BookingActivity.objects.create(
            booking=booking,
            actor=self.customer,
            action=BookingActivity.Action.REQUEST_SUBMITTED,
            notes='Initial test drive booking requested'
        )

        BookingActivity.objects.create(
            booking=booking,
            actor=self.manager,
            action=BookingActivity.Action.MANAGER_ASSIGNED,
            notes='Assigned to manager Vikram'
        )

        self.assertEqual(booking.activities.count(), 2)
        actions = list(booking.activities.values_list('action', flat=True))
        self.assertEqual(actions, [
            BookingActivity.Action.REQUEST_SUBMITTED,
            BookingActivity.Action.MANAGER_ASSIGNED,
        ])


class ActiveSlotReservationConcurrencyTests(TestCase):
    def setUp(self):
        self.brand = Brand.objects.create(name='BMW', slug='bmw')
        self.car = Car.objects.create(
            title='BMW X5',
            slug='bmw-x5',
            brand=self.brand,
            price=9500000,
            booking_amount=100000,
            is_available=True
        )
        self.customer1 = User.objects.create_user(
            username='cust_1',
            email='c1@example.com',
            password='Password123!'
        )
        self.customer2 = User.objects.create_user(
            username='cust_2',
            email='c2@example.com',
            password='Password123!'
        )
        self.booking1 = TestDriveBooking.objects.create(
            customer=self.customer1,
            car=self.car,
            preferred_date=datetime.date(2026, 11, 5),
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            driving_license_number='DL-0120150001234'
        )
        self.booking2 = TestDriveBooking.objects.create(
            customer=self.customer2,
            car=self.car,
            preferred_date=datetime.date(2026, 11, 5),
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            driving_license_number='DL-0120150005678'
        )

    def test_active_slot_reservation_creation(self):
        """Verifies ActiveSlotReservation creates slot key and links to booking."""
        res = ActiveSlotReservation.objects.create(
            slot_date=datetime.date(2026, 11, 5),
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            booking=self.booking1,
            reservation_type=ActiveSlotReservation.ReservationType.PENDING
        )
        self.assertEqual(res.slot_key, '2026-11-05_10:00')

    def test_active_slot_reservation_prevents_duplicate_slot_key(self):
        """
        Verifies database-level uniqueness constraint rejects a second reservation
        attempt for the same date and 1-hour start time, raising IntegrityError.
        """
        ActiveSlotReservation.objects.create(
            slot_date=datetime.date(2026, 11, 5),
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            booking=self.booking1,
            reservation_type=ActiveSlotReservation.ReservationType.PENDING
        )

        with self.assertRaises(IntegrityError):
            ActiveSlotReservation.objects.create(
                slot_date=datetime.date(2026, 11, 5),
                start_time=datetime.time(10, 0),
                end_time=datetime.time(11, 0),
                booking=self.booking2,
                reservation_type=ActiveSlotReservation.ReservationType.PENDING
            )



from django.urls import reverse
from django.utils import timezone


class Phase2CalendarAvailabilityAPITests(TestCase):
    def setUp(self):
        self.brand = Brand.objects.create(name='Mercedes-Benz', slug='mercedes-benz')
        self.car = Car.objects.create(
            title='C-Class',
            slug='c-class',
            brand=self.brand,
            price=6000000,
            booking_amount=50000,
            is_available=True
        )
        self.manager = User.objects.create_user(
            username='mgr_calendar',
            email='manager@calendar.com',
            password='Password123!',
            first_name='Vikram',
            last_name='Singhania',
            phone_number='9811122233',
            user_type=User.UserType.MANAGER,
            is_active=True
        )
        self.customer1 = User.objects.create_user(
            username='cust_a',
            email='cust_a@example.com',
            password='Password123!',
            first_name='Aarav',
            last_name='Sharma',
            phone_number='9822233344',
            user_type=User.UserType.CUSTOMER
        )
        self.customer2 = User.objects.create_user(
            username='cust_b',
            email='cust_b@example.com',
            password='Password123!',
            first_name='Rohan',
            last_name='Mehta',
            phone_number='9833344455',
            user_type=User.UserType.CUSTOMER
        )
        # Use future date (3 days from now) to ensure slots are not in the past
        self.target_date = timezone.localdate() + datetime.timedelta(days=3)
        self.target_date_str = self.target_date.strftime('%Y-%m-%d')
        # Default authenticated customer session for availability engine tests
        self.client.force_login(self.customer1)

    def test_calendar_api_customer_response_sanitization(self):
        """
        Item 1 & 14: Verifies ordinary customer gets 200 OK and cannot see another customer's
        name, phone, email, license, notes, or booking identifier.
        """
        # Create booking for Customer 2
        booking = TestDriveBooking.objects.create(
            customer=self.customer2,
            car=self.car,
            preferred_date=self.target_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            driving_license_number='DL-SECRET-12345',
            customer_notes='Private customer note'
        )
        ActiveSlotReservation.objects.create(
            slot_date=self.target_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            booking=booking,
            reservation_type=ActiveSlotReservation.ReservationType.PENDING,
            expires_at=timezone.now() + datetime.timedelta(hours=24)
        )

        # Authenticate as Customer 1
        self.client.force_login(self.customer1)
        url = f"{reverse('bookings:api_calendar_availability')}?start_date={self.target_date_str}&end_date={self.target_date_str}"
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['is_manager_view'])

        day = data['days'][0]
        slot_10 = next(s for s in day['slots'] if s['start_time'] == '10:00')
        self.assertEqual(slot_10['status'], 'PENDING')

        # Privacy checks: no customer 2 data in response
        self.assertFalse(slot_10['booking_details']['is_my_booking'])
        self.assertNotIn('customer_name', slot_10['booking_details'])
        self.assertNotIn('customer_phone', slot_10['booking_details'])
        self.assertNotIn('customer_email', slot_10['booking_details'])
        self.assertNotIn('driving_license_number', slot_10['booking_details'])
        self.assertNotIn('booking_number', slot_10['booking_details'])

        # Response text should not contain Customer 2's sensitive details anywhere
        self.assertNotIn('Rohan', response.content.decode())
        self.assertNotIn('DL-SECRET-12345', response.content.decode())
        self.assertNotIn('Private customer note', response.content.decode())

    def test_calendar_api_manager_response_full_details(self):
        """
        Item 2: Verifies active Manager gets 200 OK with full booking details.
        """
        booking = TestDriveBooking.objects.create(
            customer=self.customer2,
            car=self.car,
            preferred_date=self.target_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            driving_license_number='DL-MGR-VIEW-999',
            customer_notes='VIP customer'
        )
        ActiveSlotReservation.objects.create(
            slot_date=self.target_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            booking=booking,
            reservation_type=ActiveSlotReservation.ReservationType.PENDING,
            expires_at=timezone.now() + datetime.timedelta(hours=24)
        )

        self.client.force_login(self.manager)
        url = f"{reverse('bookings:api_calendar_availability')}?start_date={self.target_date_str}&end_date={self.target_date_str}"
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['is_manager_view'])

        day = data['days'][0]
        slot_10 = next(s for s in day['slots'] if s['start_time'] == '10:00')
        self.assertEqual(slot_10['status'], 'PENDING')
        b_details = slot_10['booking_details']

        self.assertEqual(b_details['customer_name'], 'Rohan Mehta')
        self.assertEqual(b_details['customer_email'], 'cust_b@example.com')
        self.assertEqual(b_details['customer_phone'], '9833344455')
        self.assertEqual(b_details['driving_license_number'], 'DL-MGR-VIEW-999')
        self.assertEqual(b_details['car_title'], 'Mercedes-Benz C-Class')

    def test_correct_one_hour_slot_generation(self):
        """Item 4: Verifies correct 1-hour appointment slot generation."""
        url = f"{reverse('bookings:api_calendar_availability')}?start_date={self.target_date_str}&end_date={self.target_date_str}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        slots = response.json()['days'][0]['slots']
        # 09:00 to 18:00 has 9 one-hour increments (including 13:00 break)
        self.assertEqual(len(slots), 9)
        slot_times = [(s['start_time'], s['end_time']) for s in slots]
        self.assertIn(('09:00', '10:00'), slot_times)
        self.assertIn(('10:00', '11:00'), slot_times)
        self.assertIn(('11:00', '12:00'), slot_times)
        self.assertIn(('12:00', '13:00'), slot_times)
        self.assertIn(('13:00', '14:00'), slot_times)
        self.assertIn(('14:00', '15:00'), slot_times)
        self.assertIn(('15:00', '16:00'), slot_times)
        self.assertIn(('16:00', '17:00'), slot_times)
        self.assertIn(('17:00', '18:00'), slot_times)

    def test_lunch_break_exclusion(self):
        """Item 5: Verifies 13:00-14:00 lunch break slot is marked CLOSED with reason."""
        url = f"{reverse('bookings:api_calendar_availability')}?start_date={self.target_date_str}&end_date={self.target_date_str}"
        response = self.client.get(url)
        slots = response.json()['days'][0]['slots']
        lunch_slot = next(s for s in slots if s['start_time'] == '13:00')
        self.assertEqual(lunch_slot['status'], 'CLOSED')
        self.assertIn('Break', lunch_slot['reason'])

    def test_holiday_exclusion(self):
        """Item 6: Verifies holiday closure marks day as closed."""
        holiday_date = self.target_date + datetime.timedelta(days=1)
        holiday_str = holiday_date.strftime('%Y-%m-%d')
        ShowroomClosure.objects.create(
            closure_type=ShowroomClosure.ClosureType.HOLIDAY,
            title='National Holiday',
            specific_date=holiday_date,
            is_active=True
        )

        url = f"{reverse('bookings:api_calendar_availability')}?start_date={holiday_str}&end_date={holiday_str}"
        response = self.client.get(url)
        day = response.json()['days'][0]
        self.assertFalse(day['is_open'])
        self.assertEqual(day['closure_reason'], 'National Holiday')
        self.assertEqual(len(day['slots']), 0)

    def test_partial_closure_exclusion(self):
        """Item 7: Verifies partial closure marks affected slot as CLOSED."""
        partial_date = self.target_date + datetime.timedelta(days=1)
        partial_str = partial_date.strftime('%Y-%m-%d')
        ShowroomClosure.objects.create(
            closure_type=ShowroomClosure.ClosureType.PARTIAL,
            title='Staff Training',
            specific_date=partial_date,
            start_time=datetime.time(15, 0),
            end_time=datetime.time(16, 0),
            is_active=True
        )

        url = f"{reverse('bookings:api_calendar_availability')}?start_date={partial_str}&end_date={partial_str}"
        response = self.client.get(url)
        slots = response.json()['days'][0]['slots']
        slot_15 = next(s for s in slots if s['start_time'] == '15:00')
        self.assertEqual(slot_15['status'], 'CLOSED')
        self.assertIn('Staff Training', slot_15['reason'])

    def test_existing_pending_reservation_exclusion(self):
        """Item 8: Verifies pending reservation marks slot as PENDING."""
        booking = TestDriveBooking.objects.create(
            customer=self.customer1,
            car=self.car,
            preferred_date=self.target_date,
            start_time=datetime.time(11, 0),
            end_time=datetime.time(12, 0),
            driving_license_number='DL-PEND-111'
        )
        ActiveSlotReservation.objects.create(
            slot_date=self.target_date,
            start_time=datetime.time(11, 0),
            end_time=datetime.time(12, 0),
            booking=booking,
            reservation_type=ActiveSlotReservation.ReservationType.PENDING,
            expires_at=timezone.now() + datetime.timedelta(hours=24)
        )

        url = f"{reverse('bookings:api_calendar_availability')}?start_date={self.target_date_str}&end_date={self.target_date_str}"
        response = self.client.get(url)
        slot_11 = next(s for s in response.json()['days'][0]['slots'] if s['start_time'] == '11:00')
        self.assertEqual(slot_11['status'], 'PENDING')

    def test_proposed_reservation_exclusion(self):
        """Item 9: Verifies proposed reservation marks slot as PROPOSED."""
        booking = TestDriveBooking.objects.create(
            customer=self.customer1,
            car=self.car,
            preferred_date=self.target_date,
            start_time=datetime.time(14, 0),
            end_time=datetime.time(15, 0),
            driving_license_number='DL-PROP-222'
        )
        proposal = BookingProposal.objects.create(
            booking=booking,
            proposed_by=self.manager,
            proposed_date=self.target_date,
            proposed_start_time=datetime.time(14, 0),
            proposed_end_time=datetime.time(15, 0),
            status=BookingProposal.Status.PENDING,
            expires_at=timezone.now() + datetime.timedelta(hours=24)
        )
        ActiveSlotReservation.objects.create(
            slot_date=self.target_date,
            start_time=datetime.time(14, 0),
            end_time=datetime.time(15, 0),
            booking=booking,
            proposal=proposal,
            reservation_type=ActiveSlotReservation.ReservationType.PROPOSED,
            expires_at=proposal.expires_at
        )

        url = f"{reverse('bookings:api_calendar_availability')}?start_date={self.target_date_str}&end_date={self.target_date_str}"
        response = self.client.get(url)
        slot_14 = next(s for s in response.json()['days'][0]['slots'] if s['start_time'] == '14:00')
        self.assertEqual(slot_14['status'], 'PROPOSED')

    def test_confirmed_booking_exclusion(self):
        """Item 10: Verifies confirmed booking marks slot as BOOKED."""
        booking = TestDriveBooking.objects.create(
            customer=self.customer1,
            car=self.car,
            preferred_date=self.target_date,
            start_time=datetime.time(16, 0),
            end_time=datetime.time(17, 0),
            status=TestDriveBooking.Status.CONFIRMED,
            driving_license_number='DL-CONF-333'
        )
        ActiveSlotReservation.objects.create(
            slot_date=self.target_date,
            start_time=datetime.time(16, 0),
            end_time=datetime.time(17, 0),
            booking=booking,
            reservation_type=ActiveSlotReservation.ReservationType.CONFIRMED
        )

        url = f"{reverse('bookings:api_calendar_availability')}?start_date={self.target_date_str}&end_date={self.target_date_str}"
        response = self.client.get(url)
        slot_16 = next(s for s in response.json()['days'][0]['slots'] if s['start_time'] == '16:00')
        self.assertEqual(slot_16['status'], 'BOOKED')

    def test_expired_reservation_handling(self):
        """
        Item 11: Verifies expired pending reservation (expires_at < now)
        does NOT block availability; slot remains AVAILABLE.
        """
        booking = TestDriveBooking.objects.create(
            customer=self.customer1,
            car=self.car,
            preferred_date=self.target_date,
            start_time=datetime.time(17, 0),
            end_time=datetime.time(18, 0),
            driving_license_number='DL-EXP-444'
        )
        # Reservation expired 10 minutes ago
        ActiveSlotReservation.objects.create(
            slot_date=self.target_date,
            start_time=datetime.time(17, 0),
            end_time=datetime.time(18, 0),
            booking=booking,
            reservation_type=ActiveSlotReservation.ReservationType.PENDING,
            expires_at=timezone.now() - datetime.timedelta(minutes=10)
        )

        url = f"{reverse('bookings:api_calendar_availability')}?start_date={self.target_date_str}&end_date={self.target_date_str}"
        response = self.client.get(url)
        slot_17 = next(s for s in response.json()['days'][0]['slots'] if s['start_time'] == '17:00')
        self.assertEqual(slot_17['status'], 'AVAILABLE')

    def test_past_datetime_exclusion(self):
        """Item 12: Verifies past appointment slot is marked CLOSED with reason for manager inspection."""
        self.client.force_login(self.manager)
        yesterday = timezone.localdate() - datetime.timedelta(days=1)
        yesterday_str = yesterday.strftime('%Y-%m-%d')

        url = f"{reverse('bookings:api_calendar_availability')}?start_date={yesterday_str}&end_date={yesterday_str}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        slots = response.json()['days'][0]['slots']
        for s in slots:
            self.assertEqual(s['status'], 'CLOSED')
            self.assertTrue(s['is_past'])

    def test_date_range_validation(self):
        """Item 13: Verifies date range parameter validation."""
        # 1. Invalid date format
        res = self.client.get(f"{reverse('bookings:api_calendar_availability')}?start_date=invalid-date")
        self.assertEqual(res.status_code, 400)
        self.assertIn('Invalid start_date format', res.json()['error'])

        # 2. start_date > end_date
        res = self.client.get(f"{reverse('bookings:api_calendar_availability')}?start_date=2026-11-10&end_date=2026-11-05")
        self.assertEqual(res.status_code, 400)
        self.assertIn('start_date cannot be after end_date', res.json()['error'])

        # 3. Date range > 31 days (for Manager inspection)
        self.client.force_login(self.manager)
        res = self.client.get(f"{reverse('bookings:api_calendar_availability')}?start_date=2026-11-01&end_date=2026-12-15")
        self.assertEqual(res.status_code, 400)
        self.assertIn('cannot exceed 31 days', res.json()['error'])

    def test_calendar_api_when_no_manager_exists(self):
        """Item 15: Verifies calendar API still functions cleanly when no active Manager exists."""
        self.manager.delete()
        url = f"{reverse('bookings:api_calendar_availability')}?start_date={self.target_date_str}&end_date={self.target_date_str}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('days', response.json())

    def test_guest_api_calendar_returns_locked_preview_no_actual_availability(self):
        """
        Verifies unauthenticated guests receive a locked preview where all slots are LOCKED.
        No actual booking availability, break, or closure details are exposed.
        """
        self.client.logout()
        url = f"{reverse('bookings:api_calendar_availability')}?start_date={self.target_date_str}&end_date={self.target_date_str}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertFalse(data['is_manager_view'])
        self.assertTrue(data.get('is_guest_view'))

        slots = data['days'][0]['slots']
        self.assertGreater(len(slots), 0)
        for s in slots:
            self.assertEqual(s['status'], 'LOCKED')
            self.assertIsNone(s['booking_details'])
            # Must not reveal any actual operational or booking state
            self.assertNotIn(s['status'], ['AVAILABLE', 'PENDING', 'BOOKED', 'PROPOSED', 'CLOSED'])

    def test_guest_api_does_not_expose_booking_ids_or_customer_information(self):
        """
        Verifies guest API response never exposes customer names, emails, phones,
        driving licenses, notes, booking IDs, or proposal information.
        """
        booking = TestDriveBooking.objects.create(
            customer=self.customer2,
            car=self.car,
            preferred_date=self.target_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            driving_license_number='DL-SECRET-GUEST-TEST-999',
            customer_notes='Highly confidential customer preferences'
        )
        ActiveSlotReservation.objects.create(
            slot_date=self.target_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            booking=booking,
            reservation_type=ActiveSlotReservation.ReservationType.CONFIRMED
        )

        self.client.logout()
        url = f"{reverse('bookings:api_calendar_availability')}?start_date={self.target_date_str}&end_date={self.target_date_str}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        content_str = response.content.decode()
        self.assertNotIn('Rohan', content_str)
        self.assertNotIn('Mehta', content_str)
        self.assertNotIn('cust_b@example.com', content_str)
        self.assertNotIn('9833344455', content_str)
        self.assertNotIn('DL-SECRET-GUEST-TEST-999', content_str)
        self.assertNotIn('Highly confidential', content_str)
        self.assertNotIn('BOOKED', content_str)


class Phase2CalendarViewAndInterfaceTests(TestCase):
    def setUp(self):
        self.brand = Brand.objects.create(name='BMW', slug='bmw')
        self.car = Car.objects.create(
            title='M340i',
            slug='bmw-m340i',
            brand=self.brand,
            price=7200000,
            booking_amount=100000,
            is_available=True
        )
        self.manager = User.objects.create_user(
            username='mgr_interface',
            email='mgr@interface.com',
            password='Password123!',
            user_type=User.UserType.MANAGER,
            is_active=True
        )
        self.customer = User.objects.create_user(
            username='cust_ui',
            email='cust@ui.com',
            password='Password123!',
            user_type=User.UserType.CUSTOMER
        )
        self.admin = User.objects.create_superuser(
            username='admin_ui',
            email='admin@ui.com',
            password='Password123!',
            user_type=User.UserType.ADMIN,
            is_staff=True,
            is_superuser=True
        )

    def test_unauthorized_access_to_manager_calendar(self):
        """
        Verifies access control:
        - Anonymous redirected to login (302).
        - Regular customer gets 403 Forbidden.
        - Admin user gets 403 Forbidden (must NOT access Manager Calendar).
        - Active Manager gets 200 OK.
        """
        mgr_url = reverse('dashboard:manager_calendar')

        # 1. Anonymous user -> 302 to login
        res_anon = self.client.get(mgr_url)
        self.assertEqual(res_anon.status_code, 302)
        self.assertIn(reverse('accounts:login'), res_anon.url)

        # 2. Ordinary customer -> 403 Forbidden
        self.client.force_login(self.customer)
        res_cust = self.client.get(mgr_url)
        self.assertEqual(res_cust.status_code, 403)

        # 3. Admin user (user_type == 'ADMIN') -> 403 Forbidden
        self.client.force_login(self.admin)
        res_admin = self.client.get(mgr_url)
        self.assertEqual(res_admin.status_code, 403)

        # 4. Active Manager -> 200 OK
        self.client.force_login(self.manager)
        res_mgr = self.client.get(mgr_url)
        self.assertEqual(res_mgr.status_code, 200)

    def test_guest_clicking_schedule_test_drive_sees_friendly_prompt_not_403(self):
        """
        Verifies guest accessing car detail sees the sign-up/login message, not a 403 page.
        Car context is preserved in query params.
        Modal displays locked preview notice and prompt headers.
        """
        url = reverse('cars:car_detail', kwargs={'slug': self.car.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.status_code, 403)

        # Unlock / registration prompt messages
        self.assertContains(
            response,
            "Unlock Test Drive Availability"
        )
        self.assertContains(
            response,
            "Sign up or log in to explore available showroom appointments and book your preferred time slot."
        )
        self.assertContains(
            response,
            "Sign up or log in to access our Test Drive feature and book your preferred showroom appointment."
        )
        self.assertContains(response, "Locked Preview")
        self.assertContains(response, "Appointment slots locked")

        # Two clear buttons with preserved car context
        register_url = reverse('accounts:register')
        login_url = reverse('accounts:login')
        self.assertContains(response, f"{register_url}?next={url}")
        self.assertContains(response, f"{login_url}?next={url}")

    def test_guest_cannot_submit_booking_request(self):
        """
        Verifies an unauthenticated guest cannot submit a test drive booking request.
        """
        cal_url = reverse('bookings:api_calendar_availability')
        response = self.client.post(cal_url, {'car_id': self.car.id})
        self.assertIn(response.status_code, [401, 403, 405])

    def test_customer_can_access_availability_calendar(self):
        """
        Verifies logged-in customer can access the availability calendar with public slot data.
        """
        self.client.force_login(self.customer)
        cal_url = reverse('bookings:api_calendar_availability')
        response = self.client.get(cal_url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['is_manager_view'])
        self.assertIn('days', data)

    def test_admin_receives_sanitized_public_view_on_calendar_api(self):
        """
        Verifies Admin does not receive manager view or other customers' private data via calendar API.
        """
        self.client.force_login(self.admin)
        cal_url = reverse('bookings:api_calendar_availability')
        response = self.client.get(cal_url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['is_manager_view'])

    def test_admin_retains_django_admin_access(self):
        """
        Verifies Admin retains full access to Django Admin, while non-staff Manager cannot.
        """
        admin_url = reverse('admin:index')

        # Admin -> 200 OK
        self.client.force_login(self.admin)
        res_admin = self.client.get(admin_url)
        self.assertEqual(res_admin.status_code, 200)

        # Manager without staff status -> redirected to admin login
        self.client.force_login(self.manager)
        res_mgr = self.client.get(admin_url)
        self.assertEqual(res_mgr.status_code, 302)

    def test_customer_calendar_modal_rendering_on_car_detail(self):
        """
        Item 16: Verifies car detail page renders the calendar modal and Schedule Test Drive button.
        """
        url = reverse('cars:car_detail', kwargs={'slug': self.car.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-bs-target="#showroomCalendarModal"')
        self.assertContains(response, 'id="showroomCalendarModal"')
        self.assertContains(response, 'calendar.js')
        self.assertContains(response, 'Schedule Test Drive')

    def test_manager_calendar_rendering(self):
        """
        Item 17: Verifies Manager calendar view renders toolbar, datepicker, sync badge, and inspector.
        """
        self.client.force_login(self.manager)
        url = reverse('dashboard:manager_calendar')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Showroom Test Drive Calendar')
        self.assertContains(response, 'id="mgrDateInput"')
        self.assertContains(response, 'id="mgrInspectorContent"')
        self.assertContains(response, 'calendar.js')
        self.assertContains(response, 'Sync: 30s')

    def test_compare_feature_unaffected(self):
        """
        Verifies Compare feature continues functioning normally for guest users.
        """
        compare_url = reverse('cars:compare')
        response = self.client.get(compare_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Compare Cars')


class Phase3ACustomerBookingSubmissionTests(TestCase):
    """
    Comprehensive verification test suite for Phase 3A: Customer Test Drive Booking Submission.
    Covers all 19 non-negotiable requirements including role constraints, driving licence validation,
    single active Manager assignment, atomic 24-hour reservation hold, and privacy controls.
    """
    def setUp(self):
        self.brand = Brand.objects.create(name='Porsche', slug='porsche')
        self.car = Car.objects.create(
            title='Taycan 4S',
            slug='porsche-taycan-4s',
            brand=self.brand,
            price=15000000,
            booking_amount=200000,
            is_available=True
        )
        self.manager = User.objects.create_user(
            username='mgr_vikram',
            email='manager.vikram@carvistahub.com',
            password='Password123!',
            first_name='Vikram',
            last_name='Singhania',
            phone_number='9811122233',
            user_type=User.UserType.MANAGER,
            is_active=True
        )
        self.customer = User.objects.create_user(
            username='cust_aarav',
            email='aarav.sharma@example.com',
            password='Password123!',
            first_name='Aarav',
            last_name='Sharma',
            phone_number='9876543210',
            user_type=User.UserType.CUSTOMER
        )
        self.customer2 = User.objects.create_user(
            username='cust_rohan',
            email='rohan.mehta@example.com',
            password='Password123!',
            first_name='Rohan',
            last_name='Mehta',
            phone_number='9876543211',
            user_type=User.UserType.CUSTOMER
        )
        self.admin = User.objects.create_superuser(
            username='admin_boss',
            email='admin@carvistahub.com',
            password='Password123!',
            user_type=User.UserType.ADMIN,
            is_staff=True,
            is_superuser=True
        )

        # Target future date (4 days from now)
        self.target_date = timezone.localdate() + datetime.timedelta(days=4)
        self.target_date_str = self.target_date.strftime('%Y-%m-%d')
        self.api_book_url = reverse('bookings:api_booking_submission')

    def _get_valid_payload(self, **kwargs):
        payload = {
            'car_id': self.car.id,
            'preferred_date': self.target_date_str,
            'start_time': '10:00',
            'license_image': create_test_image(),
            'customer_notes': 'Interested in battery performance features.',
            'terms_agreed': True,
        }
        payload.update(kwargs)
        return payload

    def test_authenticated_customer_can_submit_valid_booking(self):
        """
        Requirement 1: Authenticated customer can submit a valid test drive booking request.
        Verifies 201 Created response, booking creation with PENDING status, and assigned Manager.
        """
        self.client.force_login(self.customer)
        payload = self._get_valid_payload()
        response = self.client.post(self.api_book_url, payload)
        self.assertEqual(response.status_code, 201)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertTrue(data['booking_number'].startswith('TD-'))
        self.assertEqual(data['status'], 'PENDING')
        self.assertEqual(data['status_display'], 'Pending Manager Review')
        self.assertEqual(data['date'], self.target_date_str)
        self.assertEqual(data['start_time'], '10:00')
        self.assertEqual(data['end_time'], '11:00')

        # Database verification
        booking = TestDriveBooking.objects.get(booking_number=data['booking_number'])
        self.assertEqual(booking.customer, self.customer)
        self.assertEqual(booking.assigned_manager, self.manager)
        self.assertEqual(booking.car, self.car)
        self.assertEqual(booking.status, TestDriveBooking.Status.PENDING)
        self.assertEqual(booking.license_verification_status, TestDriveBooking.LicenseVerificationStatus.PENDING)
        self.assertTrue(bool(booking.driving_license_image))
        self.assertEqual(booking.customer_notes, 'Interested in battery performance features.')

    def test_guest_cannot_submit_booking(self):
        """
        Requirement 2: Unauthenticated guest cannot submit a booking (rejected with 401).
        """
        payload = self._get_valid_payload()
        response = self.client.post(self.api_book_url, payload)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(TestDriveBooking.objects.count(), 0)

    def test_admin_cannot_submit_customer_booking(self):
        """
        Requirement 3: Admin account cannot submit a customer booking request (rejected with 403).
        """
        self.client.force_login(self.admin)
        payload = self._get_valid_payload()
        response = self.client.post(self.api_book_url, payload)
        self.assertEqual(response.status_code, 403)
        self.assertIn("Only registered customers", response.json()['error'])
        self.assertEqual(TestDriveBooking.objects.count(), 0)

    def test_manager_cannot_submit_customer_booking(self):
        """
        Requirement 4: Manager account cannot submit a customer booking request (rejected with 403).
        """
        self.client.force_login(self.manager)
        payload = self._get_valid_payload()
        response = self.client.post(self.api_book_url, payload)
        self.assertEqual(response.status_code, 403)
        self.assertIn("Only registered customers", response.json()['error'])
        self.assertEqual(TestDriveBooking.objects.count(), 0)

    def test_license_image_is_compulsory(self):
        """
        Requirement 5: Driving licence image upload is compulsory; missing is rejected with 400.
        """
        self.client.force_login(self.customer)
        payload = {
            'car_id': self.car.id,
            'preferred_date': self.target_date_str,
            'start_time': '10:00',
            'terms_agreed': True,
        }
        res = self.client.post(self.api_book_url, payload)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(TestDriveBooking.objects.count(), 0)

    def test_valid_looking_dl_saved_with_pending_verification_never_verified(self):
        """
        Requirement 7: Uploaded licence is saved with verification status PENDING, never VERIFIED.
        Even if the client submits forged status overrides, server strictly enforces PENDING.
        """
        self.client.force_login(self.customer)
        payload = self._get_valid_payload(
            license_verification_status='VERIFIED',  # Client forgery attempt
            status='CONFIRMED',                      # Client forgery attempt
        )
        response = self.client.post(self.api_book_url, payload)
        self.assertEqual(response.status_code, 201)

        booking = TestDriveBooking.objects.latest('created_at')
        # Verification status is STRICTLY PENDING
        self.assertEqual(booking.license_verification_status, TestDriveBooking.LicenseVerificationStatus.PENDING)
        self.assertEqual(booking.driving_license_verification_status, 'PENDING')
        self.assertNotEqual(booking.license_verification_status, 'VERIFIED')
        # Booking lifecycle status is STRICTLY PENDING
        self.assertEqual(booking.status, TestDriveBooking.Status.PENDING)

    def test_missing_active_manager_prevents_booking_safely(self):
        """
        Requirement 8: Missing active Manager prevents booking safely with clear message.
        Never falls back to Admin or another user.
        """
        # Deactivate Manager
        self.manager.is_active = False
        self.manager.save()
        self.assertIsNone(User.get_active_manager())

        self.client.force_login(self.customer)
        payload = self._get_valid_payload()
        response = self.client.post(self.api_book_url, payload)
        self.assertEqual(response.status_code, 503)
        self.assertIn("no active Showroom Manager", response.json()['error'])

        # No booking or reservation created
        self.assertEqual(TestDriveBooking.objects.count(), 0)
        self.assertEqual(ActiveSlotReservation.objects.count(), 0)

    def test_booking_assigned_to_single_active_manager(self):
        """
        Requirement 9: Successful booking is assigned to the single active Manager.
        """
        self.client.force_login(self.customer)
        payload = self._get_valid_payload()
        response = self.client.post(self.api_book_url, payload)
        self.assertEqual(response.status_code, 201)

        booking = TestDriveBooking.objects.latest('created_at')
        self.assertEqual(booking.assigned_manager, self.manager)
        self.assertEqual(booking.assigned_manager.user_type, User.UserType.MANAGER)

    def test_successful_submission_creates_exactly_one_active_slot_reservation(self):
        """
        Requirement 10: Successful submission creates exactly one active slot reservation
        and corresponding BookingActivity audit record.
        """
        self.client.force_login(self.customer)
        payload = self._get_valid_payload()
        response = self.client.post(self.api_book_url, payload)
        self.assertEqual(response.status_code, 201)

        booking = TestDriveBooking.objects.latest('created_at')
        reservations = ActiveSlotReservation.objects.filter(booking=booking)
        self.assertEqual(reservations.count(), 1)

        res = reservations.first()
        self.assertEqual(res.slot_key, f"{self.target_date_str}_10:00")
        self.assertEqual(res.reservation_type, ActiveSlotReservation.ReservationType.PENDING)
        self.assertEqual(res.slot_date, self.target_date)
        self.assertEqual(res.start_time, datetime.time(10, 0))
        self.assertEqual(res.end_time, datetime.time(11, 0))

        # BookingActivity created
        activities = booking.activities.all()
        self.assertEqual(activities.count(), 1)
        self.assertEqual(activities.first().action, BookingActivity.Action.REQUEST_SUBMITTED)
        self.assertEqual(activities.first().actor, self.customer)

    def test_pending_expiry_is_24_hours_after_submission(self):
        """
        Requirement 11: Pending reservation expiry is exactly 24 hours after submission.
        """
        before_submission = timezone.now()
        self.client.force_login(self.customer)
        payload = self._get_valid_payload()
        response = self.client.post(self.api_book_url, payload)
        self.assertEqual(response.status_code, 201)
        after_submission = timezone.now()

        booking = TestDriveBooking.objects.latest('created_at')
        res = ActiveSlotReservation.objects.get(booking=booking)

        # Expiry timestamp on booking
        self.assertIsNotNone(booking.pending_expires_at)
        expected_min = before_submission + datetime.timedelta(hours=24)
        expected_max = after_submission + datetime.timedelta(hours=24)
        self.assertGreaterEqual(booking.pending_expires_at, expected_min)
        self.assertLessEqual(booking.pending_expires_at, expected_max)

        # Expiry timestamp on reservation
        self.assertIsNotNone(res.expires_at)
        self.assertEqual(booking.pending_expires_at, res.expires_at)

    def test_duplicate_booking_of_same_slot_is_rejected(self):
        """
        Requirement 12: Duplicate booking of the same slot is rejected with 409 Conflict.
        """
        # Customer 1 reserves 10:00 slot
        self.client.force_login(self.customer)
        payload1 = self._get_valid_payload()
        res1 = self.client.post(self.api_book_url, payload1)
        self.assertEqual(res1.status_code, 201)

        # Customer 2 attempts to reserve the identical slot
        self.client.force_login(self.customer2)
        payload2 = self._get_valid_payload()
        res2 = self.client.post(self.api_book_url, payload2)
        self.assertEqual(res2.status_code, 409)
        self.assertTrue(any(w in res2.json()['error'].lower() for w in ['already reserved', 'no longer available', 'reserved by another']))
        self.assertIn("available slot", res2.json()['error'].lower())

        # Exactly 1 booking was created
        self.assertEqual(TestDriveBooking.objects.count(), 1)
        self.assertEqual(ActiveSlotReservation.objects.count(), 1)

    def test_slot_became_unavailable_after_calendar_loaded_is_rejected(self):
        """
        Requirement 13: A slot that became unavailable after calendar loaded is rejected cleanly.
        """
        # Manager holds or confirms slot out of band
        other_booking = TestDriveBooking.objects.create(
            customer=self.customer2,
            assigned_manager=self.manager,
            car=self.car,
            preferred_date=self.target_date,
            start_time=datetime.time(11, 0),
            end_time=datetime.time(12, 0),
            status=TestDriveBooking.Status.CONFIRMED,
        )
        ActiveSlotReservation.objects.create(
            slot_date=self.target_date,
            start_time=datetime.time(11, 0),
            end_time=datetime.time(12, 0),
            booking=other_booking,
            reservation_type=ActiveSlotReservation.ReservationType.CONFIRMED
        )

        # Customer attempts to submit 11:00 slot
        self.client.force_login(self.customer)
        payload = self._get_valid_payload(start_time='11:00')
        response = self.client.post(self.api_book_url, payload)
        self.assertEqual(response.status_code, 409)
        self.assertTrue(any(w in response.json()['error'].lower() for w in ['no longer available', 'already reserved']))
        self.assertIn("available slot", response.json()['error'].lower())

    def test_invalid_date_time_past_date_lunch_break_closed_dates_rejected(self):
        """
        Requirement 14: Invalid date/time, past date/time, lunch break, and closed dates are rejected.
        """
        self.client.force_login(self.customer)

        # 1. Past date
        yesterday_str = (timezone.localdate() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        res_past = self.client.post(self.api_book_url, self._get_valid_payload(preferred_date=yesterday_str))
        self.assertEqual(res_past.status_code, 400)
        self.assertIn("past", res_past.json()['error'].lower())

        # 2. Lunch break (13:00 - 14:00)
        res_lunch = self.client.post(self.api_book_url, self._get_valid_payload(start_time='13:00'))
        self.assertEqual(res_lunch.status_code, 400)
        self.assertIn("break", res_lunch.json()['error'].lower())

        # 3. Full-day holiday
        holiday_date = self.target_date + datetime.timedelta(days=2)
        ShowroomClosure.objects.create(
            closure_type=ShowroomClosure.ClosureType.HOLIDAY,
            title='National Holiday',
            specific_date=holiday_date,
            is_active=True
        )
        res_holiday = self.client.post(self.api_book_url, self._get_valid_payload(preferred_date=holiday_date.strftime('%Y-%m-%d')))
        self.assertEqual(res_holiday.status_code, 400)
        self.assertIn("closed", res_holiday.json()['error'].lower())

        # 4. Out of operating hours (08:00 before 09:00 opening)
        res_early = self.client.post(self.api_book_url, self._get_valid_payload(start_time='08:00'))
        self.assertEqual(res_early.status_code, 400)

    def test_customer_cannot_access_another_customer_private_booking_details(self):
        """
        Requirement 15: Customer cannot access another customer's private booking details.
        After submission, slot appears as PENDING to other customers without private info.
        """
        # Customer 1 books
        self.client.force_login(self.customer)
        payload = self._get_valid_payload(customer_notes='Confidential personal preference note')
        res_submit = self.client.post(self.api_book_url, payload)
        self.assertEqual(res_submit.status_code, 201)
        booking_number = res_submit.json()['booking_number']

        # Customer 2 queries calendar availability
        self.client.force_login(self.customer2)
        cal_url = f"{reverse('bookings:api_calendar_availability')}?start_date={self.target_date_str}&end_date={self.target_date_str}"
        res_cal = self.client.get(cal_url)
        self.assertEqual(res_cal.status_code, 200)

        cal_data = res_cal.json()
        slot_10 = next(s for s in cal_data['days'][0]['slots'] if s['start_time'] == '10:00')

        # Slot is PENDING and blocked for selection
        self.assertEqual(slot_10['status'], 'PENDING')
        self.assertFalse(slot_10['booking_details']['is_my_booking'])

        # No private details exposed in response
        content = res_cal.content.decode()
        self.assertNotIn('Aarav', content)
        self.assertNotIn('aarav.sharma@example.com', content)
        self.assertNotIn('9876543210', content)
        self.assertNotIn('Confidential personal preference note', content)
        self.assertNotIn('license_image_url', content)
        self.assertNotIn(booking_number, content)

    def test_dl_number_not_exposed_in_customer_facing_api_responses(self):
        """
        Requirement 16: DL image and private details are not exposed in customer-facing API responses.
        """
        self.client.force_login(self.customer)
        payload = self._get_valid_payload()
        response = self.client.post(self.api_book_url, payload)
        self.assertEqual(response.status_code, 201)

        # Sensitive document fields must NOT be in JSON payload
        data = response.json()
        self.assertNotIn('license_image_url', data)
        self.assertNotIn('driving_license_image', data)
        self.assertNotIn('secure_licenses', response.content.decode())

    def test_terms_compulsory(self):
        """
        Verifies terms and conditions agreement is strictly compulsory.
        """
        self.client.force_login(self.customer)
        payload = self._get_valid_payload(terms_agreed=False)
        response = self.client.post(self.api_book_url, payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(TestDriveBooking.objects.count(), 0)

    def test_expired_reservation_cleanup_and_rebooking(self):
        """
        Verifies that an expired pending reservation (expires_at < now)
        allows a new customer to book that slot, cleaning up the stale reservation.
        """
        # Create an expired reservation on this slot
        old_booking = TestDriveBooking.objects.create(
            customer=self.customer2,
            assigned_manager=self.manager,
            car=self.car,
            preferred_date=self.target_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            status=TestDriveBooking.Status.PENDING,
            pending_expires_at=timezone.now() - datetime.timedelta(hours=2)
        )
        ActiveSlotReservation.objects.create(
            slot_date=self.target_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            booking=old_booking,
            reservation_type=ActiveSlotReservation.ReservationType.PENDING,
            expires_at=timezone.now() - datetime.timedelta(hours=2)
        )

        # New customer books the now-available slot
        self.client.force_login(self.customer)
        payload = self._get_valid_payload()
        response = self.client.post(self.api_book_url, payload)
        self.assertEqual(response.status_code, 201)

        # Old booking is marked EXPIRED
        old_booking.refresh_from_db()
        self.assertEqual(old_booking.status, TestDriveBooking.Status.EXPIRED)

        # New booking holds the slot
        new_booking = TestDriveBooking.objects.latest('created_at')
        self.assertEqual(new_booking.customer, self.customer)
        res = ActiveSlotReservation.objects.get(slot_key=f"{self.target_date_str}_10:00")
        self.assertEqual(res.booking, new_booking)

    def test_customer_cannot_book_for_another_user(self):
        """
        Verifies customer cannot submit a booking on behalf of another user via forged user_id.
        """
        self.client.force_login(self.customer)
        payload = self._get_valid_payload(
            customer_id=self.customer2.id,  # Forgery attempt
            user_id=self.customer2.id,      # Forgery attempt
        )
        response = self.client.post(self.api_book_url, payload)
        self.assertEqual(response.status_code, 201)

        booking = TestDriveBooking.objects.latest('created_at')
        # Booking customer is strictly the authenticated session user
        self.assertEqual(booking.customer, self.customer)
        self.assertNotEqual(booking.customer, self.customer2)

    def test_indian_dl_format_normalization_unit(self):
        """
        Unit tests for validate_and_normalize_indian_dl across common Indian formats.
        """
        test_cases = [
            ('mh 01 2015 0001234', 'MH-0120150001234'),
            ('dl-04-2019-0004567', 'DL-0420190004567'),
            ('ka0520200008888', 'KA-0520200008888'),
            ('gj-01/2017/0001234', 'GJ-0120170001234'),
            ('up-14 2016 0009999', 'UP-1420160009999'),
        ]
        for raw, expected in test_cases:
            normalized = validate_and_normalize_indian_dl(raw)
            self.assertEqual(normalized, expected)


class DrivingLicenseUploadAndManagerVerificationTests(TestCase):
    """
    Dedicated verification test suite for Driving Licence Photo Upload Replacement
    and Showroom Manager Document Review Workflow:
      - Mandatory front-side photo upload
      - Invalid file extension rejection
      - Oversized file rejection (> 5 MB)
      - Corrupt/non-image file rejection via Pillow
      - Safe storage & secure Manager-only serving (guest 401, customer 403, manager 200)
      - Customer & guest calendar privacy (images never exposed)
      - Manager verification actions (VERIFY, REQUEST_REUPLOAD, REJECT)
      - Confirmation blocked until VERIFIED
      - Historical bookings without image remain fully accessible
    """
    def setUp(self):
        self.brand = Brand.objects.create(name='Audi', slug='audi')
        self.car = Car.objects.create(
            title='e-tron GT',
            slug='audi-etron-gt',
            brand=self.brand,
            price=17000000,
            booking_amount=250000,
            is_available=True
        )
        self.manager = User.objects.create_user(
            username='mgr_rajesh',
            email='rajesh.manager@carvistahub.com',
            password='Password123!',
            first_name='Rajesh',
            last_name='Kumar',
            phone_number='9822233344',
            user_type=User.UserType.MANAGER,
            is_active=True
        )
        self.customer = User.objects.create_user(
            username='cust_priya',
            email='priya.sharma@example.com',
            password='Password123!',
            first_name='Priya',
            last_name='Sharma',
            phone_number='9877788899',
            user_type=User.UserType.CUSTOMER
        )
        self.other_customer = User.objects.create_user(
            username='cust_other',
            email='other.customer@example.com',
            password='Password123!',
            first_name='Other',
            last_name='User',
            phone_number='9877788800',
            user_type=User.UserType.CUSTOMER
        )
        self.target_date = timezone.localdate() + datetime.timedelta(days=3)
        self.target_date_str = self.target_date.strftime('%Y-%m-%d')
        self.api_book_url = reverse('bookings:api_booking_submission')

    def test_mandatory_upload_missing_image_rejected(self):
        """Mandatory upload: submission without license_image returns 400 Bad Request."""
        self.client.force_login(self.customer)
        payload = {
            'car_id': self.car.id,
            'preferred_date': self.target_date_str,
            'start_time': '10:00',
            'terms_agreed': True,
        }
        res = self.client.post(self.api_book_url, payload)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(TestDriveBooking.objects.count(), 0)

    def test_invalid_file_type_rejected(self):
        """Invalid file extension (.pdf/.txt) is rejected with 400 Bad Request."""
        self.client.force_login(self.customer)
        fake_pdf = SimpleUploadedFile("dl_doc.pdf", b"%PDF-1.4 fake content", content_type="application/pdf")
        payload = {
            'car_id': self.car.id,
            'preferred_date': self.target_date_str,
            'start_time': '10:00',
            'license_image': fake_pdf,
            'terms_agreed': True,
        }
        res = self.client.post(self.api_book_url, payload)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(TestDriveBooking.objects.count(), 0)

    def test_oversized_file_rejected(self):
        """Oversized file (> 5 MB) is rejected with 400 Bad Request."""
        self.client.force_login(self.customer)
        import os
        raw_noise = os.urandom(1600 * 1200 * 3)
        img = Image.frombytes('RGB', (1600, 1200), raw_noise)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        large_file = SimpleUploadedFile("large_license.png", buf.read(), content_type="image/png")
        payload = {
            'car_id': self.car.id,
            'preferred_date': self.target_date_str,
            'start_time': '10:00',
            'license_image': large_file,
            'terms_agreed': True,
        }
        res = self.client.post(self.api_book_url, payload)
        self.assertEqual(res.status_code, 400)
        self.assertTrue(any("5 mb" in str(err).lower() for err in res.json().values()))

    def test_corrupt_image_rejected(self):
        """Corrupt or non-image file with .jpg extension is rejected via Pillow decoding."""
        self.client.force_login(self.customer)
        corrupt_file = SimpleUploadedFile("corrupt.jpg", b"NOT_A_VALID_JPEG_HEADER_CONTENT", content_type="image/jpeg")
        payload = {
            'car_id': self.car.id,
            'preferred_date': self.target_date_str,
            'start_time': '10:00',
            'license_image': corrupt_file,
            'terms_agreed': True,
        }
        res = self.client.post(self.api_book_url, payload)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(TestDriveBooking.objects.count(), 0)

    def test_valid_upload_saved_with_pending_status(self):
        """Valid JPG image is saved securely with initial verification status PENDING."""
        self.client.force_login(self.customer)
        valid_img = create_test_image("my_dl_front.jpg")
        payload = {
            'car_id': self.car.id,
            'preferred_date': self.target_date_str,
            'start_time': '10:00',
            'license_image': valid_img,
            'terms_agreed': True,
        }
        res = self.client.post(self.api_book_url, payload)
        self.assertEqual(res.status_code, 201)
        booking = TestDriveBooking.objects.latest('created_at')
        self.assertEqual(booking.customer, self.customer)
        self.assertEqual(booking.license_verification_status, TestDriveBooking.LicenseVerificationStatus.PENDING)
        self.assertTrue(bool(booking.driving_license_image))
        self.assertEqual(booking.driving_license_number, '')

    def test_secure_manager_only_image_access_assigned_manager_success(self):
        """Assigned Showroom Manager can view the uploaded licence via secure view."""
        self.client.force_login(self.customer)
        valid_img = create_test_image("valid_dl.jpg")
        self.client.post(self.api_book_url, {
            'car_id': self.car.id,
            'preferred_date': self.target_date_str,
            'start_time': '10:00',
            'license_image': valid_img,
            'terms_agreed': True,
        })
        booking = TestDriveBooking.objects.latest('created_at')

        # Assigned Manager requests secure image
        self.client.force_login(self.manager)
        doc_url = reverse('bookings:secure_license_image', kwargs={'booking_id': booking.id})
        res = self.client.get(doc_url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'image/jpeg')
        self.assertIn('private', res['Cache-Control'])
        self.assertIn('no-store', res['Cache-Control'])

    def test_secure_image_access_unauthenticated_guest_denied(self):
        """Unauthenticated guest receives 401 Unauthorized when attempting to access licence."""
        booking = TestDriveBooking.objects.create(
            customer=self.customer,
            assigned_manager=self.manager,
            car=self.car,
            preferred_date=self.target_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            driving_license_image=create_test_image(),
            status=TestDriveBooking.Status.PENDING
        )
        self.client.logout()
        doc_url = reverse('bookings:secure_license_image', kwargs={'booking_id': booking.id})
        res = self.client.get(doc_url)
        self.assertEqual(res.status_code, 401)

    def test_secure_image_access_other_customer_denied(self):
        """Customers receive 403 Forbidden when attempting to access licence documents."""
        booking = TestDriveBooking.objects.create(
            customer=self.customer,
            assigned_manager=self.manager,
            car=self.car,
            preferred_date=self.target_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            driving_license_image=create_test_image(),
            status=TestDriveBooking.Status.PENDING
        )
        # Even the booking customer themselves receives 403 from the manager doc inspection endpoint
        self.client.force_login(self.customer)
        doc_url = reverse('bookings:secure_license_image', kwargs={'booking_id': booking.id})
        res_same_cust = self.client.get(doc_url)
        self.assertEqual(res_same_cust.status_code, 403)

        # Another customer receives 403
        self.client.force_login(self.other_customer)
        res_other_cust = self.client.get(doc_url)
        self.assertEqual(res_other_cust.status_code, 403)

    def test_calendar_and_booking_apis_never_expose_license_image_to_customers(self):
        """Calendar availability and booking APIs never leak licence images or URLs to customers."""
        self.client.force_login(self.customer)
        valid_img = create_test_image("confidential_dl.jpg")
        res_book = self.client.post(self.api_book_url, {
            'car_id': self.car.id,
            'preferred_date': self.target_date_str,
            'start_time': '10:00',
            'license_image': valid_img,
            'terms_agreed': True,
        })
        self.assertEqual(res_book.status_code, 201)
        # Confirmation response has no licence URL
        self.assertNotIn('license_image_url', res_book.json())

        # Other customer queries calendar
        self.client.force_login(self.other_customer)
        cal_url = f"{reverse('bookings:api_calendar_availability')}?start_date={self.target_date_str}&end_date={self.target_date_str}"
        res_cal = self.client.get(cal_url)
        self.assertEqual(res_cal.status_code, 200)
        cal_content = res_cal.content.decode()
        self.assertNotIn('license_image_url', cal_content)
        self.assertNotIn('confidential_dl', cal_content)

    def test_manager_verify_action_transitions_status_to_verified(self):
        """
        Manager 'VERIFY' action:
          - Transitions licence verification status to VERIFIED
          - Records Manager user ID and verification timestamp
          - Creates BookingActivity audit entry
          - Does NOT automatically confirm the test-drive booking (status remains PENDING)
          - Booking becomes eligible for confirmation via validate_booking_confirmation()
        """
        booking = TestDriveBooking.objects.create(
            customer=self.customer,
            assigned_manager=self.manager,
            car=self.car,
            preferred_date=self.target_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            driving_license_image=create_test_image(),
            license_verification_status=TestDriveBooking.LicenseVerificationStatus.PENDING,
            status=TestDriveBooking.Status.PENDING
        )
        self.client.force_login(self.manager)
        action_url = reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id})
        res = self.client.post(action_url, {'action': 'VERIFY'}, content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['success'])
        self.assertEqual(res.json()['status'], 'VERIFIED')
        self.assertEqual(res.json()['display'], 'Document Verified by Manager')

        booking.refresh_from_db()
        self.assertEqual(booking.license_verification_status, TestDriveBooking.LicenseVerificationStatus.VERIFIED)
        self.assertEqual(booking.verified_by, self.manager)
        self.assertIsNotNone(booking.verified_at)
        # Booking status is NOT automatically confirmed
        self.assertEqual(booking.status, TestDriveBooking.Status.PENDING)

        # Booking is now eligible for confirmation
        self.assertTrue(validate_booking_confirmation(booking))

        # BookingActivity logged
        activity = booking.activities.last()
        self.assertEqual(activity.actor, self.manager)
        self.assertIn("verified", activity.notes.lower())

    def test_manager_request_reupload_is_disallowed(self):
        """Request Re-upload feature is completely removed and rejected as an invalid action."""
        booking = TestDriveBooking.objects.create(
            customer=self.customer,
            assigned_manager=self.manager,
            car=self.car,
            preferred_date=self.target_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            driving_license_image=create_test_image(),
            license_verification_status=TestDriveBooking.LicenseVerificationStatus.PENDING,
            status=TestDriveBooking.Status.PENDING
        )
        self.client.force_login(self.manager)
        action_url = reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id})
        res = self.client.post(action_url, {'action': 'REQUEST_REUPLOAD', 'reason': 'blurred'}, content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertIn("invalid verification action", res.json()['error'].lower())

    def test_manager_reject_action_releases_reservation_restores_calendar_and_notifies_customer(self):
        """
        Manager 'REJECT' action:
          - Sets license_verification_status = REJECTED
          - Sets TestDriveBooking.status = REJECTED
          - Saves mandatory rejection reason, manager, and timestamp
          - Creates BookingActivity audit entry (action=REJECTED)
          - Atomically releases ActiveSlotReservation
          - Makes slot available again in the shared customer calendar
          - Creates persistent in-app CustomerNotification
        """
        booking = TestDriveBooking.objects.create(
            customer=self.customer,
            assigned_manager=self.manager,
            car=self.car,
            preferred_date=self.target_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            driving_license_image=create_test_image(),
            license_verification_status=TestDriveBooking.LicenseVerificationStatus.PENDING,
            status=TestDriveBooking.Status.PENDING
        )
        slot_key = ActiveSlotReservation.generate_slot_key(self.target_date, datetime.time(10, 0))
        reservation = ActiveSlotReservation.objects.create(
            slot_key=slot_key,
            slot_date=self.target_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            booking=booking,
            reservation_type=ActiveSlotReservation.ReservationType.PENDING
        )

        # Before rejection, calendar slot is PENDING / RESERVED (not available)
        self.client.force_login(self.customer)
        cal_url = f"{reverse('bookings:api_calendar_availability')}?start_date={self.target_date_str}&end_date={self.target_date_str}"
        res_cal_before = self.client.get(cal_url)
        slot_before = next(s for s in res_cal_before.json()['days'][0]['slots'] if s['start_time'] == '10:00')
        self.assertEqual(slot_before['status'], 'PENDING')

        # Manager executes REJECT
        self.client.force_login(self.manager)
        action_url = reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id})
        reject_reason = "Expired licence card dated 2021. Image is illegible."
        res = self.client.post(action_url, {'action': 'REJECT', 'reason': reject_reason}, content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['success'])
        self.assertEqual(res.json()['status'], 'REJECTED')
        self.assertEqual(res.json()['booking_status'], 'REJECTED')

        booking.refresh_from_db()
        self.assertEqual(booking.license_verification_status, TestDriveBooking.LicenseVerificationStatus.REJECTED)
        self.assertEqual(booking.status, TestDriveBooking.Status.REJECTED)
        self.assertEqual(booking.rejection_reason, reject_reason)
        self.assertEqual(booking.rejected_by, self.manager)
        self.assertIsNotNone(booking.rejected_at)

        # Audit trail logged
        self.assertTrue(
            BookingActivity.objects.filter(booking=booking, action=BookingActivity.Action.REJECTED).exists()
        )

        # Reservation is released immediately
        self.assertFalse(ActiveSlotReservation.objects.filter(booking=booking).exists())

        # Calendar slot is now AVAILABLE in shared customer calendar
        self.client.force_login(self.customer)
        res_cal_after = self.client.get(cal_url)
        slot_after = next(s for s in res_cal_after.json()['days'][0]['slots'] if s['start_time'] == '10:00')
        self.assertEqual(slot_after['status'], 'AVAILABLE')

        # CustomerNotification created for customer
        notif = CustomerNotification.objects.filter(user=self.customer, booking=booking).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.booking_reference, booking.booking_number)
        self.assertEqual(notif.rejection_reason, reject_reason)
        self.assertFalse(notif.is_read)

    def test_manager_reject_requires_reason(self):
        """REJECT without reason returns 400 Bad Request."""
        booking = TestDriveBooking.objects.create(
            customer=self.customer,
            assigned_manager=self.manager,
            car=self.car,
            preferred_date=self.target_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            driving_license_image=create_test_image(),
            license_verification_status=TestDriveBooking.LicenseVerificationStatus.PENDING,
            status=TestDriveBooking.Status.PENDING
        )
        self.client.force_login(self.manager)
        action_url = reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id})
        res = self.client.post(action_url, {'action': 'REJECT', 'reason': '   '}, content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertIn("reason is mandatory", res.json()['error'].lower())

    def test_customer_rejection_notification_popup_context_and_privacy(self):
        """
        Customer rejection notification:
          - Automatically provided in template context for the affected customer
          - Popup modal rendered in HTML
          - Strictly isolated so other customers and managers never receive it
          - Dismissal endpoint marks notification as read (no duplicate popups)
        """
        booking = TestDriveBooking.objects.create(
            customer=self.customer,
            assigned_manager=self.manager,
            car=self.car,
            preferred_date=self.target_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            driving_license_image=create_test_image(),
            license_verification_status=TestDriveBooking.LicenseVerificationStatus.PENDING,
            status=TestDriveBooking.Status.PENDING
        )
        self.client.force_login(self.manager)
        action_url = reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id})
        self.client.post(action_url, {'action': 'REJECT', 'reason': 'Expired DL'}, content_type='application/json')

        notif = CustomerNotification.objects.get(user=self.customer, booking=booking)

        # 1. Affected customer visits website -> receives notification in context & popup modal
        self.client.force_login(self.customer)
        res_home = self.client.get(reverse('cars:home'))
        self.assertEqual(res_home.status_code, 200)
        self.assertEqual(res_home.context['customer_unread_notification'], notif)
        self.assertContains(res_home, 'modalCustomerRejectionNotice')
        self.assertContains(res_home, booking.booking_number)
        self.assertContains(res_home, 'Expired DL')

        # 2. Other customer visits website -> NEVER receives notification or modal
        self.client.force_login(self.other_customer)
        res_other = self.client.get(reverse('cars:home'))
        self.assertEqual(res_other.status_code, 200)
        self.assertIsNone(res_other.context['customer_unread_notification'])
        self.assertNotContains(res_other, 'modalCustomerRejectionNotice')

        # 3. Manager visits -> does not receive customer popup
        self.client.force_login(self.manager)
        res_mgr = self.client.get(reverse('cars:home'))
        self.assertEqual(res_mgr.status_code, 200)
        self.assertIsNone(res_mgr.context['customer_unread_notification'])

        # 4. Customer dismisses notification -> is_read = True, no duplicate popups
        self.client.force_login(self.customer)
        dismiss_url = reverse('bookings:api_notification_dismiss', kwargs={'notification_id': notif.id})
        res_dismiss = self.client.post(dismiss_url)
        self.assertEqual(res_dismiss.status_code, 200)
        self.assertTrue(res_dismiss.json()['success'])

        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

        # Next page request no longer renders popup modal
        res_after_dismiss = self.client.get(reverse('cars:home'))
        self.assertIsNone(res_after_dismiss.context['customer_unread_notification'])
        self.assertNotContains(res_after_dismiss, 'modalCustomerRejectionNotice')

    def test_customer_can_view_rejection_reason_in_booking_history(self):
        """Customer can access their booking history to review the detailed manager rejection reason."""
        booking = TestDriveBooking.objects.create(
            customer=self.customer,
            assigned_manager=self.manager,
            car=self.car,
            preferred_date=self.target_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            driving_license_image=create_test_image(),
            license_verification_status=TestDriveBooking.LicenseVerificationStatus.REJECTED,
            status=TestDriveBooking.Status.REJECTED,
            rejection_reason="Licence photo is expired."
        )
        self.client.force_login(self.customer)
        res = self.client.get(reverse('dashboard:customer_bookings'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, booking.booking_number)
        self.assertContains(res, "Licence photo is expired.")
        self.assertContains(res, "Request Rejected")
        self.assertContains(res, "Document Rejected")

    def test_unauthorized_users_cannot_perform_manager_verification_actions(self):
        """Customers and guests cannot execute Manager licence verification or rejection actions."""
        booking = TestDriveBooking.objects.create(
            customer=self.customer,
            assigned_manager=self.manager,
            car=self.car,
            preferred_date=self.target_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            driving_license_image=create_test_image(),
            license_verification_status=TestDriveBooking.LicenseVerificationStatus.PENDING,
            status=TestDriveBooking.Status.PENDING
        )
        action_url = reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id})

        # Guest -> 401 Unauthorized
        self.client.logout()
        res_guest = self.client.post(action_url, {'action': 'VERIFY'}, content_type='application/json')
        self.assertEqual(res_guest.status_code, 401)

        # Customer -> 403 Forbidden
        self.client.force_login(self.customer)
        res_customer = self.client.post(action_url, {'action': 'VERIFY'}, content_type='application/json')
        self.assertEqual(res_customer.status_code, 403)

    def test_booking_confirmation_blocked_until_verified(self):
        """Booking confirmation is strictly blocked until licence verification status is VERIFIED."""
        booking = TestDriveBooking.objects.create(
            customer=self.customer,
            assigned_manager=self.manager,
            car=self.car,
            preferred_date=self.target_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            driving_license_image=create_test_image(),
            license_verification_status=TestDriveBooking.LicenseVerificationStatus.PENDING,
            status=TestDriveBooking.Status.PENDING
        )
        # Status PENDING -> raises ValidationError
        with self.assertRaises(ValidationError) as ctx:
            validate_booking_confirmation(booking)
        self.assertIn("until the customer's driving licence document has been verified", str(ctx.exception))

        # Status REJECTED -> raises ValidationError
        booking.license_verification_status = TestDriveBooking.LicenseVerificationStatus.REJECTED
        booking.save()
        with self.assertRaises(ValidationError):
            validate_booking_confirmation(booking)

        # Status VERIFIED -> validation succeeds
        booking.license_verification_status = TestDriveBooking.LicenseVerificationStatus.VERIFIED
        booking.save()
        self.assertTrue(validate_booking_confirmation(booking))

    def test_old_bookings_without_image_still_accessible(self):
        """Historical bookings created before DL image upload remain fully accessible and functional."""
        old_booking = TestDriveBooking.objects.create(
            customer=self.customer,
            assigned_manager=self.manager,
            car=self.car,
            preferred_date=self.target_date,
            start_time=datetime.time(12, 0),
            end_time=datetime.time(13, 0),
            driving_license_number='MH-0120150001234',
            driving_license_image=None,  # No uploaded photo
            license_verification_status=TestDriveBooking.LicenseVerificationStatus.PENDING,
            status=TestDriveBooking.Status.PENDING
        )
        ActiveSlotReservation.objects.create(
            slot_date=self.target_date,
            start_time=datetime.time(12, 0),
            end_time=datetime.time(13, 0),
            booking=old_booking,
            reservation_type=ActiveSlotReservation.ReservationType.PENDING
        )

        # Manager queries calendar availability
        self.client.force_login(self.manager)
        cal_url = f"{reverse('bookings:api_calendar_availability')}?start_date={self.target_date_str}&end_date={self.target_date_str}"
        res_cal = self.client.get(cal_url)
        self.assertEqual(res_cal.status_code, 200)

        slot_12 = next(s for s in res_cal.json()['days'][0]['slots'] if s['start_time'] == '12:00')
        b_details = slot_12['booking_details']
        self.assertFalse(b_details['has_license_image'])
        self.assertIsNone(b_details['license_image_url'])
        self.assertEqual(b_details['booking_number'], old_booking.booking_number)

        # Requesting secure document for booking without image returns 404 cleanly
        doc_url = reverse('bookings:secure_license_image', kwargs={'booking_id': old_booking.id})
        res_doc = self.client.get(doc_url)
        self.assertEqual(res_doc.status_code, 404)


class RollingSevenDayBookingWindowTests(TestCase):
    """
    Dedicated test suite verifying the Rolling 7-Day Customer Test Drive Booking Window:
      1. Today is bookable when valid slots exist.
      2. The sixth day after today (today + 6 days) is bookable.
      3. The seventh day after today (today + 7 days) is not bookable.
      4. Yesterday (today - 1 day) is not bookable.
      5. The allowed window advances dynamically from the current showroom date.
      6. Manual API requests outside the window are rejected with 400 Bad Request.
      7. Existing bookings outside the current window remain accessible to the Showroom Manager.
      8. Existing confirmed and pending reservations remain intact.
      9. The current calendar and booking submission workflow continue to work cleanly.
    """
    def setUp(self):
        self.brand = Brand.objects.create(name='BMW', slug='bmw')
        self.car = Car.objects.create(
            title='M4 Competition Coupe',
            slug='bmw-m4-competition',
            brand=self.brand,
            price=15000000,
            booking_amount=200000,
            is_available=True
        )
        self.manager = User.objects.create_user(
            username='mgr_vikram',
            email='vikram@carvistahub.com',
            password='Password123!',
            first_name='Vikram',
            last_name='Malhotra',
            user_type=User.UserType.MANAGER,
            is_active=True
        )
        self.customer = User.objects.create_user(
            username='arjun_customer',
            email='arjun@example.com',
            password='Password123!',
            first_name='Arjun',
            last_name='Kapoor',
            user_type=User.UserType.CUSTOMER
        )

        ShowroomSchedule.objects.all().update(
            is_open=True,
            open_time=datetime.time(9, 0),
            close_time=datetime.time(18, 0),
            slot_duration_minutes=60,
            is_active=True
        )
        ShowroomClosure.objects.filter(closure_type=ShowroomClosure.ClosureType.BREAK).update(
            start_time=datetime.time(13, 0),
            end_time=datetime.time(14, 0),
            is_recurring=True,
            is_active=True
        )

        self.api_book_url = reverse('bookings:api_booking_submission')
        self.api_cal_url = reverse('bookings:api_calendar_availability')
        self.today = timezone.localdate()

    def _get_payload(self, preferred_date, start_time='10:00'):
        return {
            'car_id': self.car.id,
            'preferred_date': preferred_date if isinstance(preferred_date, str) else preferred_date.strftime('%Y-%m-%d'),
            'start_time': start_time,
            'contact_phone': '9876543210',
            'customer_notes': '7-day window test booking.',
            'license_image': create_test_image('dl_test.jpg'),
            'terms_agreed': True,
        }

    def test_today_is_bookable_when_valid_slots_exist(self):
        """Item 1: Today is within the 7-day window and bookable for future slots today."""
        self.client.force_login(self.customer)
        # Use an afternoon slot so it is in the future relative to current time, or future slot
        target_time = '16:00'
        # Check if 16:00 is in the past
        now = timezone.now()
        tz = zoneinfo.ZoneInfo(settings.TIME_ZONE)
        if datetime.datetime.combine(self.today, datetime.time(16, 0)).replace(tzinfo=tz) <= now:
            target_time = '17:00'
        # If current time is after operating hours, verify calendar API returns today as part of the 7-day window
        cal_res = self.client.get(f"{self.api_cal_url}?start_date={self.today.strftime('%Y-%m-%d')}&end_date={self.today.strftime('%Y-%m-%d')}")
        self.assertEqual(cal_res.status_code, 200)
        self.assertEqual(cal_res.json()['days'][0]['date'], self.today.strftime('%Y-%m-%d'))

        # If slot is in the future, booking submission succeeds
        slot_dt = datetime.datetime.combine(self.today, datetime.time(17, 0)).replace(tzinfo=tz)
        if slot_dt > now:
            res = self.client.post(self.api_book_url, self._get_payload(self.today, start_time='17:00'))
            self.assertEqual(res.status_code, 201)
            self.assertEqual(res.json()['date'], self.today.strftime('%Y-%m-%d'))

    def test_sixth_day_after_today_is_bookable(self):
        """Item 2: The sixth day after today (today + 6 days) is the 7th day of the window and is bookable."""
        self.client.force_login(self.customer)
        day_6 = self.today + datetime.timedelta(days=6)
        day_6_str = day_6.strftime('%Y-%m-%d')

        # Calendar API returns slots for day 6
        cal_res = self.client.get(f"{self.api_cal_url}?start_date={day_6_str}&end_date={day_6_str}")
        self.assertEqual(cal_res.status_code, 200)
        self.assertEqual(cal_res.json()['days'][0]['date'], day_6_str)

        # Booking submission succeeds on day 6
        res = self.client.post(self.api_book_url, self._get_payload(day_6, start_time='10:00'))
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()['date'], day_6_str)

        booking = TestDriveBooking.objects.get(booking_number=res.json()['booking_number'])
        self.assertEqual(booking.preferred_date, day_6)

    def test_seventh_day_after_today_is_not_bookable(self):
        """Item 3: The seventh day after today (today + 7 days) is beyond the 7-day window and is rejected."""
        self.client.force_login(self.customer)
        day_7 = self.today + datetime.timedelta(days=7)
        day_7_str = day_7.strftime('%Y-%m-%d')

        # Booking submission rejected with 400 Bad Request
        res = self.client.post(self.api_book_url, self._get_payload(day_7, start_time='10:00'))
        self.assertEqual(res.status_code, 400)
        self.assertIn("7-day booking window", str(res.json()))

        # Customer Calendar availability API rejected with 400 Bad Request
        cal_res = self.client.get(f"{self.api_cal_url}?start_date={day_7_str}&end_date={day_7_str}")
        self.assertEqual(cal_res.status_code, 400)
        self.assertIn("beyond the 7-day booking window", cal_res.json()['error'])

    def test_yesterday_is_not_bookable(self):
        """Item 4: Yesterday (today - 1 day) is in the past and is rejected for customers."""
        self.client.force_login(self.customer)
        yesterday = self.today - datetime.timedelta(days=1)
        yesterday_str = yesterday.strftime('%Y-%m-%d')

        # Booking submission rejected with 400 Bad Request
        res = self.client.post(self.api_book_url, self._get_payload(yesterday, start_time='10:00'))
        self.assertEqual(res.status_code, 400)
        self.assertIn("cannot be in the past", str(res.json()))

        # Calendar availability API rejected with 400 Bad Request
        cal_res = self.client.get(f"{self.api_cal_url}?start_date={yesterday_str}&end_date={yesterday_str}")
        self.assertEqual(cal_res.status_code, 400)
        self.assertIn("cannot be in the past", cal_res.json()['error'])

    def test_rolling_window_advances_dynamically(self):
        """Item 5: The allowed window is calculated dynamically from current showroom date."""
        from .services import get_rolling_booking_window
        window_start, window_end = get_rolling_booking_window()
        self.assertEqual(window_start, self.today)
        self.assertEqual(window_end, self.today + datetime.timedelta(days=6))
        # Total calendar days in window is exactly 7
        self.assertEqual((window_end - window_start).days + 1, 7)

    def test_manual_api_requests_outside_window_are_rejected(self):
        """Item 6: Customer cannot bypass window by submitting manual API requests with future/past dates."""
        self.client.force_login(self.customer)
        # Attempt date 14 days in the future
        far_future = self.today + datetime.timedelta(days=14)
        far_future_str = far_future.strftime('%Y-%m-%d')

        res_book = self.client.post(self.api_book_url, self._get_payload(far_future, start_time='11:00'))
        self.assertEqual(res_book.status_code, 400)
        self.assertIn("7-day booking window", str(res_book.json()))

        res_cal = self.client.get(f"{self.api_cal_url}?start_date={far_future_str}&end_date={far_future_str}")
        self.assertEqual(res_cal.status_code, 400)
        self.assertIn("beyond the 7-day booking window", res_cal.json()['error'])

    def test_existing_bookings_outside_window_remain_accessible_to_manager(self):
        """Item 7: Manager can inspect existing bookings on historical and future dates outside the 7-day window."""
        past_date = self.today - datetime.timedelta(days=10)
        past_booking = TestDriveBooking.objects.create(
            customer=self.customer,
            assigned_manager=self.manager,
            car=self.car,
            preferred_date=past_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            driving_license_image=create_test_image('past.jpg'),
            license_verification_status=TestDriveBooking.LicenseVerificationStatus.VERIFIED,
            status=TestDriveBooking.Status.CONFIRMED
        )
        ActiveSlotReservation.objects.create(
            slot_key=ActiveSlotReservation.generate_slot_key(past_date, datetime.time(10, 0)),
            slot_date=past_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            booking=past_booking,
            reservation_type=ActiveSlotReservation.ReservationType.CONFIRMED
        )

        future_date = self.today + datetime.timedelta(days=20)
        future_booking = TestDriveBooking.objects.create(
            customer=self.customer,
            assigned_manager=self.manager,
            car=self.car,
            preferred_date=future_date,
            start_time=datetime.time(15, 0),
            end_time=datetime.time(16, 0),
            driving_license_image=create_test_image('future.jpg'),
            license_verification_status=TestDriveBooking.LicenseVerificationStatus.PENDING,
            status=TestDriveBooking.Status.PENDING
        )
        ActiveSlotReservation.objects.create(
            slot_key=ActiveSlotReservation.generate_slot_key(future_date, datetime.time(15, 0)),
            slot_date=future_date,
            start_time=datetime.time(15, 0),
            end_time=datetime.time(16, 0),
            booking=future_booking,
            reservation_type=ActiveSlotReservation.ReservationType.PENDING
        )

        # Manager queries past date -> 200 OK with booking details
        self.client.force_login(self.manager)
        past_url = f"{self.api_cal_url}?start_date={past_date.strftime('%Y-%m-%d')}&end_date={past_date.strftime('%Y-%m-%d')}"
        res_past = self.client.get(past_url)
        self.assertEqual(res_past.status_code, 200)
        slot_10 = next(s for s in res_past.json()['days'][0]['slots'] if s['start_time'] == '10:00')
        self.assertEqual(slot_10['booking_details']['booking_number'], past_booking.booking_number)

        # Manager queries future date outside window -> 200 OK with booking details
        future_url = f"{self.api_cal_url}?start_date={future_date.strftime('%Y-%m-%d')}&end_date={future_date.strftime('%Y-%m-%d')}"
        res_future = self.client.get(future_url)
        self.assertEqual(res_future.status_code, 200)
        slot_15 = next(s for s in res_future.json()['days'][0]['slots'] if s['start_time'] == '15:00')
        self.assertEqual(slot_15['booking_details']['booking_number'], future_booking.booking_number)

    def test_existing_confirmed_and_pending_reservations_remain_intact(self):
        """Item 8: Bookings and slot reservations are never deleted simply because their date moves outside the window."""
        outside_date = self.today + datetime.timedelta(days=12)
        booking = TestDriveBooking.objects.create(
            customer=self.customer,
            assigned_manager=self.manager,
            car=self.car,
            preferred_date=outside_date,
            start_time=datetime.time(11, 0),
            end_time=datetime.time(12, 0),
            driving_license_image=create_test_image('outside.jpg'),
            license_verification_status=TestDriveBooking.LicenseVerificationStatus.PENDING,
            status=TestDriveBooking.Status.PENDING
        )
        res_entry = ActiveSlotReservation.objects.create(
            slot_date=outside_date,
            start_time=datetime.time(11, 0),
            end_time=datetime.time(12, 0),
            booking=booking,
            reservation_type=ActiveSlotReservation.ReservationType.PENDING
        )

        # Execute customer calendar availability default query
        self.client.force_login(self.customer)
        res_cal = self.client.get(self.api_cal_url)
        self.assertEqual(res_cal.status_code, 200)
        # Exactly 7 days returned
        self.assertEqual(len(res_cal.json()['days']), 7)

        # Verify outside reservation and booking remain untouched in DB
        res_entry.refresh_from_db()
        self.assertEqual(res_entry.booking, booking)
        self.assertEqual(res_entry.reservation_type, ActiveSlotReservation.ReservationType.PENDING)
        booking.refresh_from_db()
        self.assertEqual(booking.status, TestDriveBooking.Status.PENDING)

    def test_customer_calendar_default_request_returns_rolling_7_days(self):
        """Item 9: Default customer query returns exactly 7 days starting from showroom-local today."""
        self.client.force_login(self.customer)
        res = self.client.get(self.api_cal_url)
        self.assertEqual(res.status_code, 200)
        days = res.json()['days']
        self.assertEqual(len(days), 7)
        self.assertEqual(days[0]['date'], self.today.strftime('%Y-%m-%d'))
        self.assertEqual(days[6]['date'], (self.today + datetime.timedelta(days=6)).strftime('%Y-%m-%d'))


class TwoStageConfirmationWorkflowTests(TestCase):
    """
    Test suite for Phase 3 Manager Two-Stage Confirmation Workflow:
      Stage 1: Document review (Verify Document / Reject Document)
      Stage 2: Final test-drive confirmation (Confirm Driving Test)
      Persistent customer confirmation notification & isolation.
    """

    def setUp(self):
        self.user_model = get_user_model()
        self.manager = self.user_model.objects.create_user(
            username='mgr_twostage',
            email='mgr_twostage@example.com',
            password='testpassword123',
            user_type=self.user_model.UserType.MANAGER,
            is_active=True
        )
        self.customer = self.user_model.objects.create_user(
            username='cust_twostage',
            email='cust_twostage@example.com',
            password='testpassword123',
            user_type=self.user_model.UserType.CUSTOMER,
            first_name='Aarav',
            last_name='Patel',
            phone_number='9876543210',
            is_active=True
        )
        self.other_customer = self.user_model.objects.create_user(
            username='other_twostage',
            email='other_twostage@example.com',
            password='testpassword123',
            user_type=self.user_model.UserType.CUSTOMER,
            is_active=True
        )
        self.brand = Brand.objects.create(name='BMW Stage', slug='bmw-stage')
        self.car = Car.objects.create(
            title='M340i xDrive',
            slug='bmw-m340i-stage',
            brand=self.brand,
            price=7200000.00,
            booking_amount=100000,
            is_available=True
        )
        ShowroomSchedule.objects.all().update(
            is_open=True,
            open_time=datetime.time(9, 0),
            close_time=datetime.time(18, 0),
            slot_duration_minutes=60,
            is_active=True
        )
        ShowroomClosure.objects.filter(closure_type=ShowroomClosure.ClosureType.BREAK).update(
            is_active=True,
            start_time=datetime.time(13, 0),
            end_time=datetime.time(14, 0)
        )
        self.today = timezone.localdate()
        self.target_date = self.today + datetime.timedelta(days=2)
        self.start_time = datetime.time(11, 0)
        self.end_time = datetime.time(12, 0)
        self.slot_key = ActiveSlotReservation.generate_slot_key(self.target_date, self.start_time)

    def _create_pending_booking(self):
        booking = TestDriveBooking.objects.create(
            customer=self.customer,
            assigned_manager=self.manager,
            car=self.car,
            preferred_date=self.target_date,
            start_time=self.start_time,
            end_time=self.end_time,
            driving_license_image=create_test_image('dl_stage.jpg'),
            license_verification_status=TestDriveBooking.LicenseVerificationStatus.PENDING,
            status=TestDriveBooking.Status.PENDING,
            pending_expires_at=timezone.now() + datetime.timedelta(hours=24)
        )
        reservation = ActiveSlotReservation.objects.create(
            slot_key=self.slot_key,
            slot_date=self.target_date,
            start_time=self.start_time,
            end_time=self.end_time,
            booking=booking,
            reservation_type=ActiveSlotReservation.ReservationType.PENDING,
            expires_at=booking.pending_expires_at
        )
        return booking, reservation

    def test_01_stage1_pending_licence_state(self):
        """Item 1: Pending licence shows PENDING verification and booking status; eligible for verify/reject."""
        booking, res = self._create_pending_booking()
        self.assertEqual(booking.license_verification_status, TestDriveBooking.LicenseVerificationStatus.PENDING)
        self.assertEqual(booking.status, TestDriveBooking.Status.PENDING)
        self.assertIsNotNone(booking.driving_license_image)

        # Check calendar API for manager inspection
        self.client.force_login(self.manager)
        url = f"{reverse('bookings:api_calendar_availability')}?start_date={self.target_date.strftime('%Y-%m-%d')}&end_date={self.target_date.strftime('%Y-%m-%d')}"
        res_cal = self.client.get(url)
        self.assertEqual(res_cal.status_code, 200)
        slot = next(s for s in res_cal.json()['days'][0]['slots'] if s['start_time'] == '11:00')
        self.assertEqual(slot['status'], 'PENDING')
        self.assertEqual(slot['booking_details']['license_verification_status'], 'PENDING')
        self.assertEqual(slot['booking_details']['status'], 'PENDING')
        # Cannot confirm yet because document is not verified
        self.assertFalse(slot['booking_details']['can_confirm'])

    def test_02_clicking_verify_changes_only_licence_verification_status(self):
        """Item 2: Verify action updates license_verification_status to VERIFIED, sets manager & timestamp."""
        booking, _ = self._create_pending_booking()
        self.client.force_login(self.manager)
        action_url = reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id})
        res = self.client.post(action_url, {'action': 'VERIFY'}, content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['status'], 'VERIFIED')

        booking.refresh_from_db()
        self.assertEqual(booking.license_verification_status, TestDriveBooking.LicenseVerificationStatus.VERIFIED)
        self.assertEqual(booking.verified_by, self.manager)
        self.assertIsNotNone(booking.verified_at)

        # Audit log created
        activity = BookingActivity.objects.filter(booking=booking, action=BookingActivity.Action.NOTE_ADDED).first()
        self.assertIsNotNone(activity)
        self.assertIn("verified", activity.notes.lower())

    def test_03_booking_remains_pending_after_licence_verification(self):
        """Item 3: Clicking Verify Document does NOT automatically confirm the test-drive booking."""
        booking, res = self._create_pending_booking()
        self.client.force_login(self.manager)
        action_url = reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id})
        self.client.post(action_url, {'action': 'VERIFY'}, content_type='application/json')

        booking.refresh_from_db()
        res.refresh_from_db()
        # Booking remains PENDING
        self.assertEqual(booking.status, TestDriveBooking.Status.PENDING)
        self.assertIsNone(booking.confirmed_at)
        # Reservation remains PENDING with 24-hr expiry
        self.assertEqual(res.reservation_type, ActiveSlotReservation.ReservationType.PENDING)
        self.assertIsNotNone(res.expires_at)

    def test_04_confirm_button_eligible_after_verification(self):
        """Item 4: After licence is VERIFIED, booking becomes eligible for final confirmation."""
        booking, res = self._create_pending_booking()
        self.client.force_login(self.manager)
        action_url = reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id})
        self.client.post(action_url, {'action': 'VERIFY'}, content_type='application/json')

        # Query manager calendar
        url = f"{reverse('bookings:api_calendar_availability')}?start_date={self.target_date.strftime('%Y-%m-%d')}&end_date={self.target_date.strftime('%Y-%m-%d')}"
        res_cal = self.client.get(url)
        slot = next(s for s in res_cal.json()['days'][0]['slots'] if s['start_time'] == '11:00')
        self.assertEqual(slot['booking_details']['license_verification_status'], 'VERIFIED')
        self.assertEqual(slot['booking_details']['status'], 'PENDING')
        self.assertTrue(slot['booking_details']['can_confirm'])

    def test_05_clicking_confirm_driving_test_confirms_booking(self):
        """Item 5: Final confirmation transitions booking to CONFIRMED, records manager and timestamp."""
        booking, res = self._create_pending_booking()
        # Step 1: Verify document
        self.client.force_login(self.manager)
        action_url = reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id})
        self.client.post(action_url, {'action': 'VERIFY'}, content_type='application/json')

        # Step 2: Final Confirm Driving Test
        confirm_url = reverse('bookings:manager_booking_confirm', kwargs={'booking_id': booking.id})
        res_confirm = self.client.post(confirm_url, content_type='application/json')
        self.assertEqual(res_confirm.status_code, 200)
        self.assertTrue(res_confirm.json()['success'])
        self.assertEqual(res_confirm.json()['status'], 'CONFIRMED')

        booking.refresh_from_db()
        self.assertEqual(booking.status, TestDriveBooking.Status.CONFIRMED)
        self.assertEqual(booking.confirmed_by, self.manager)
        self.assertIsNotNone(booking.confirmed_at)

        # Audit log for CONFIRMED
        activity = BookingActivity.objects.filter(booking=booking, action=BookingActivity.Action.CONFIRMED).first()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.actor, self.manager)

    def test_06_reservation_becomes_confirmed_without_temporary_expiry(self):
        """Item 6: ActiveSlotReservation becomes CONFIRMED with expires_at = NULL."""
        booking, res = self._create_pending_booking()
        self.client.force_login(self.manager)
        self.client.post(reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id}), {'action': 'VERIFY'}, content_type='application/json')
        self.client.post(reverse('bookings:manager_booking_confirm', kwargs={'booking_id': booking.id}), content_type='application/json')

        res.refresh_from_db()
        self.assertEqual(res.reservation_type, ActiveSlotReservation.ReservationType.CONFIRMED)
        self.assertIsNone(res.expires_at)

    def test_07_customer_receives_persistent_confirmation_notification(self):
        """Item 7: Customer receives in-app persistent CustomerNotification with notification_type BOOKING_CONFIRMED."""
        booking, _ = self._create_pending_booking()
        self.client.force_login(self.manager)
        self.client.post(reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id}), {'action': 'VERIFY'}, content_type='application/json')
        self.client.post(reverse('bookings:manager_booking_confirm', kwargs={'booking_id': booking.id}), content_type='application/json')

        notif = CustomerNotification.objects.filter(
            booking=booking,
            notification_type=CustomerNotification.NotificationType.BOOKING_CONFIRMED
        ).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.user, self.customer)
        self.assertEqual(notif.title, "Test Drive Confirmed!")
        self.assertIn("confirmed by the Showroom Manager", notif.message)
        self.assertEqual(notif.booking_reference, booking.booking_number)
        self.assertIn("M340i", notif.car_title)
        self.assertEqual(notif.slot_date, self.target_date)
        self.assertFalse(notif.is_read)

    def test_08_customer_notification_visible_when_online_and_returning_later(self):
        """Item 8: Online polling endpoint returns unread confirmation; page load injects it into template."""
        booking, _ = self._create_pending_booking()
        self.client.force_login(self.manager)
        self.client.post(reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id}), {'action': 'VERIFY'}, content_type='application/json')
        self.client.post(reverse('bookings:manager_booking_confirm', kwargs={'booking_id': booking.id}), content_type='application/json')

        # 1. Online customer polling
        self.client.force_login(self.customer)
        res_unread = self.client.get(reverse('bookings:api_notification_unread'))
        self.assertEqual(res_unread.status_code, 200)
        data = res_unread.json()
        self.assertTrue(data['has_unread'])
        self.assertEqual(data['notification']['type'], 'BOOKING_CONFIRMED')
        self.assertEqual(data['notification']['title'], 'Test Drive Confirmed!')
        self.assertEqual(data['notification']['booking_reference'], booking.booking_number)
        self.assertEqual(data['notification']['status_display'], 'CONFIRMED')
        self.assertEqual(data['notification']['showroom_location'], 'CarVistaHub Showroom')

        # 2. Re-visiting website / page load
        res_home = self.client.get(reverse('cars:home'))
        self.assertEqual(res_home.status_code, 200)
        self.assertIsNotNone(res_home.context['customer_unread_notification'])
        self.assertContains(res_home, 'Test Drive Confirmed!')
        self.assertContains(res_home, booking.booking_number)

    def test_09_notification_visible_only_to_correct_customer(self):
        """Item 9: Notification is isolated strictly to the affected customer."""
        booking, _ = self._create_pending_booking()
        self.client.force_login(self.manager)
        self.client.post(reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id}), {'action': 'VERIFY'}, content_type='application/json')
        self.client.post(reverse('bookings:manager_booking_confirm', kwargs={'booking_id': booking.id}), content_type='application/json')

        # Other customer visits
        self.client.force_login(self.other_customer)
        res_other = self.client.get(reverse('bookings:api_notification_unread'))
        self.assertFalse(res_other.json()['has_unread'])

        res_other_page = self.client.get(reverse('cars:home'))
        self.assertIsNone(res_other_page.context['customer_unread_notification'])

        # Manager visits
        self.client.force_login(self.manager)
        res_mgr = self.client.get(reverse('bookings:api_notification_unread'))
        self.assertFalse(res_mgr.json()['has_unread'])

    def test_10_acknowledging_notification_does_not_change_booking_status(self):
        """Item 10: Dismissing notification marks is_read=True but preserves booking status as CONFIRMED."""
        booking, _ = self._create_pending_booking()
        self.client.force_login(self.manager)
        self.client.post(reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id}), {'action': 'VERIFY'}, content_type='application/json')
        self.client.post(reverse('bookings:manager_booking_confirm', kwargs={'booking_id': booking.id}), content_type='application/json')

        notif = CustomerNotification.objects.get(booking=booking, notification_type=CustomerNotification.NotificationType.BOOKING_CONFIRMED)

        self.client.force_login(self.customer)
        dismiss_url = reverse('bookings:api_notification_dismiss', kwargs={'notification_id': notif.id})
        res_dismiss = self.client.post(dismiss_url)
        self.assertEqual(res_dismiss.status_code, 200)

        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

        booking.refresh_from_db()
        self.assertEqual(booking.status, TestDriveBooking.Status.CONFIRMED)

        # Unread API now reports no unread
        res_poll = self.client.get(reverse('bookings:api_notification_unread'))
        self.assertFalse(res_poll.json()['has_unread'])

    def test_11_rejection_workflow_still_works_and_releases_slot(self):
        """Item 11: Rejection workflow functions properly, releases ActiveSlotReservation, and notifies customer."""
        booking, res = self._create_pending_booking()
        self.client.force_login(self.manager)
        action_url = reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id})
        res_reject = self.client.post(action_url, {'action': 'REJECT', 'reason': 'Illegible photo'}, content_type='application/json')
        self.assertEqual(res_reject.status_code, 200)

        booking.refresh_from_db()
        self.assertEqual(booking.status, TestDriveBooking.Status.REJECTED)
        self.assertEqual(booking.license_verification_status, TestDriveBooking.LicenseVerificationStatus.REJECTED)
        self.assertEqual(booking.rejection_reason, 'Illegible photo')

        # Reservation is released
        self.assertFalse(ActiveSlotReservation.objects.filter(booking=booking).exists())

        # Customer receives rejection notification
        notif = CustomerNotification.objects.get(booking=booking, notification_type=CustomerNotification.NotificationType.BOOKING_REJECTED)
        self.assertEqual(notif.rejection_reason, 'Illegible photo')

    def test_12_confirmation_blocked_when_licence_not_verified(self):
        """Item 12: Manager cannot confirm appointment if licence verification status is PENDING or REJECTED."""
        booking, _ = self._create_pending_booking()
        self.client.force_login(self.manager)
        confirm_url = reverse('bookings:manager_booking_confirm', kwargs={'booking_id': booking.id})

        # When PENDING
        res_fail = self.client.post(confirm_url, content_type='application/json')
        self.assertEqual(res_fail.status_code, 400)
        self.assertIn("verified", res_fail.json()['error'].lower())

        booking.refresh_from_db()
        self.assertEqual(booking.status, TestDriveBooking.Status.PENDING)

    def test_13_repeated_confirmation_prevented(self):
        """Item 13: Once confirmed, repeated confirmation requests are rejected with 400; no duplicate notifications."""
        booking, _ = self._create_pending_booking()
        self.client.force_login(self.manager)
        self.client.post(reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id}), {'action': 'VERIFY'}, content_type='application/json')
        res_first = self.client.post(reverse('bookings:manager_booking_confirm', kwargs={'booking_id': booking.id}), content_type='application/json')
        self.assertEqual(res_first.status_code, 200)

        # Second attempt
        res_second = self.client.post(reverse('bookings:manager_booking_confirm', kwargs={'booking_id': booking.id}), content_type='application/json')
        self.assertEqual(res_second.status_code, 400)
        self.assertIn("already been confirmed", res_second.json()['error'])

        # Exactly 1 notification and 1 CONFIRMED activity entry
        self.assertEqual(CustomerNotification.objects.filter(booking=booking).count(), 1)
        self.assertEqual(BookingActivity.objects.filter(booking=booking, action=BookingActivity.Action.CONFIRMED).count(), 1)

    def test_14_unauthorized_users_cannot_confirm_or_verify(self):
        """Item 14: Anonymous users and customers cannot invoke manager verification or confirmation actions."""
        booking, _ = self._create_pending_booking()
        confirm_url = reverse('bookings:manager_booking_confirm', kwargs={'booking_id': booking.id})
        verify_url = reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id})

        # Anonymous
        self.client.logout()
        res_anon_c = self.client.post(confirm_url, content_type='application/json')
        self.assertEqual(res_anon_c.status_code, 401)
        res_anon_v = self.client.post(verify_url, {'action': 'VERIFY'}, content_type='application/json')
        self.assertEqual(res_anon_v.status_code, 401)

        # Customer
        self.client.force_login(self.customer)
        res_cust_c = self.client.post(confirm_url, content_type='application/json')
        self.assertEqual(res_cust_c.status_code, 403)
        res_cust_v = self.client.post(verify_url, {'action': 'VERIFY'}, content_type='application/json')
        self.assertEqual(res_cust_v.status_code, 403)


class CustomerBookingManagementAndOneActiveRestrictionTests(TestCase):
    """
    Comprehensive test suite verifying Phase 3 confirmed booking management,
    customer cancellation workflow, and the one-active-booking restriction (Phase H).
    """
    def setUp(self):
        self.customer = User.objects.create_user(
            username='arjun_customer',
            email='arjun@example.com',
            password='Password123!',
            user_type=User.UserType.CUSTOMER
        )
        self.customer2 = User.objects.create_user(
            username='rohit_customer',
            email='rohit@example.com',
            password='Password123!',
            user_type=User.UserType.CUSTOMER
        )
        self.manager = User.objects.create_user(
            username='vikram_manager',
            email='vikram@example.com',
            password='Password123!',
            user_type=User.UserType.MANAGER,
            is_active=True
        )
        self.brand = Brand.objects.create(name='Audi', slug='audi-active')
        self.car = Car.objects.create(
            title='RS e-tron GT',
            slug='audi-rs-etron-gt',
            brand=self.brand,
            price=19000000.00,
            booking_amount=200000,
            is_available=True
        )
        self.car2 = Car.objects.create(
            title='Q8 Sportback e-tron',
            slug='audi-q8-etron',
            brand=self.brand,
            price=11500000.00,
            booking_amount=150000,
            is_available=True
        )
        ShowroomSchedule.objects.all().update(
            is_open=True,
            open_time=datetime.time(9, 0),
            close_time=datetime.time(18, 0),
            slot_duration_minutes=60,
            is_active=True
        )
        ShowroomClosure.objects.filter(closure_type=ShowroomClosure.ClosureType.BREAK).update(
            is_active=True,
            start_time=datetime.time(13, 0),
            end_time=datetime.time(14, 0)
        )
        self.today = timezone.localdate()
        self.target_date = self.today + datetime.timedelta(days=2)
        self.target_date_str = self.target_date.strftime('%Y-%m-%d')
        self.start_time = datetime.time(11, 0)
        self.end_time = datetime.time(12, 0)
        self.slot_key = ActiveSlotReservation.generate_slot_key(self.target_date, self.start_time)
        self.api_book_url = reverse('bookings:api_booking_submission')

    def _create_confirmed_booking(self, customer=None, car=None, date=None, start_time=None, end_time=None):
        cust = customer or self.customer
        vehicle = car or self.car
        slot_d = date or self.target_date
        s_time = start_time or self.start_time
        e_time = end_time or self.end_time
        s_key = ActiveSlotReservation.generate_slot_key(slot_d, s_time)

        booking = TestDriveBooking.objects.create(
            customer=cust,
            assigned_manager=self.manager,
            car=vehicle,
            preferred_date=slot_d,
            start_time=s_time,
            end_time=e_time,
            driving_license_image=create_test_image('dl_active.jpg'),
            license_verification_status=TestDriveBooking.LicenseVerificationStatus.VERIFIED,
            status=TestDriveBooking.Status.CONFIRMED,
            verified_by=self.manager,
            verified_at=timezone.now(),
            confirmed_by=self.manager,
            confirmed_at=timezone.now()
        )
        reservation = ActiveSlotReservation.objects.create(
            slot_key=s_key,
            slot_date=slot_d,
            start_time=s_time,
            end_time=e_time,
            booking=booking,
            reservation_type=ActiveSlotReservation.ReservationType.CONFIRMED,
            expires_at=None
        )
        return booking, reservation

    def _get_valid_payload(self, car=None, date=None, start_time='10:00', **kwargs):
        payload = {
            'car_id': (car or self.car).id,
            'preferred_date': date or (self.today + datetime.timedelta(days=3)).strftime('%Y-%m-%d'),
            'start_time': start_time,
            'license_image': create_test_image(),
            'customer_notes': 'Booking management test.',
            'terms_agreed': True,
        }
        payload.update(kwargs)
        return payload

    def test_01_customer_can_open_confirmed_booking_details(self):
        """Scenario 1: Customer can open their confirmed booking from the calendar and retrieve details."""
        booking, _ = self._create_confirmed_booking()
        self.client.force_login(self.customer)

        details_url = reverse('bookings:api_booking_details', kwargs={'booking_id': booking.id})
        res = self.client.get(details_url)
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertTrue(data['success'])
        b = data['booking']
        self.assertEqual(b['booking_number'], booking.booking_number)
        self.assertIn('RS e-tron GT', b['car_title'])
        self.assertEqual(b['date'], self.target_date_str)
        self.assertEqual(b['slot_time'], '11:00 - 12:00')
        self.assertEqual(b['showroom_location'], 'CarVistaHub Showroom')
        self.assertEqual(b['status'], 'CONFIRMED')
        self.assertTrue(b['can_cancel'])

    def test_02_customer_cannot_inspect_another_customers_booking(self):
        """Scenario 2: Customer cannot inspect another customer's booking (isolated access control)."""
        booking, _ = self._create_confirmed_booking(customer=self.customer)
        self.client.force_login(self.customer2)

        details_url = reverse('bookings:api_booking_details', kwargs={'booking_id': booking.id})
        res = self.client.get(details_url)
        self.assertEqual(res.status_code, 403)
        self.assertIn("Access denied", res.json()['error'])

    def test_03_customer_can_cancel_their_confirmed_appointment(self):
        """Scenario 3: Customer can successfully cancel their confirmed test-drive appointment."""
        booking, _ = self._create_confirmed_booking()
        self.client.force_login(self.customer)

        cancel_url = reverse('bookings:api_booking_cancel', kwargs={'booking_id': booking.id})
        res = self.client.post(cancel_url, {'reason': 'Schedule conflict'}, content_type='application/json')
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['status'], 'CANCELLED')
        self.assertIn('cancelled successfully', data['message'])

    def test_04_cancellation_changes_status_and_records_audit(self):
        """Scenario 4: Cancellation changes status to CANCELLED, records cancelled_at, reason, and BookingActivity."""
        booking, _ = self._create_confirmed_booking()
        self.client.force_login(self.customer)

        cancel_url = reverse('bookings:api_booking_cancel', kwargs={'booking_id': booking.id})
        self.client.post(cancel_url, {'reason': 'Change of plans'}, content_type='application/json')

        booking.refresh_from_db()
        self.assertEqual(booking.status, TestDriveBooking.Status.CANCELLED)
        self.assertIsNotNone(booking.cancelled_at)
        self.assertEqual(booking.cancellation_reason, 'Change of plans')

        activity = BookingActivity.objects.filter(booking=booking, action=BookingActivity.Action.CANCELLED).first()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.actor, self.customer)
        self.assertIn('Change of plans', activity.notes)

    def test_05_cancellation_releases_correct_reservation(self):
        """Scenario 5: Cancelling releases only the booking's ActiveSlotReservation without touching others."""
        booking1, res1 = self._create_confirmed_booking(customer=self.customer, start_time=datetime.time(10, 0), end_time=datetime.time(11, 0))
        booking2, res2 = self._create_confirmed_booking(customer=self.customer2, start_time=datetime.time(15, 0), end_time=datetime.time(16, 0))

        self.client.force_login(self.customer)
        cancel_url = reverse('bookings:api_booking_cancel', kwargs={'booking_id': booking1.id})
        res = self.client.post(cancel_url, {'reason': 'Customer requested cancellation'}, content_type='application/json')
        self.assertEqual(res.status_code, 200)

        # Booking 1 reservation released
        self.assertFalse(ActiveSlotReservation.objects.filter(booking=booking1).exists())
        # Booking 2 reservation strictly intact
        self.assertTrue(ActiveSlotReservation.objects.filter(booking=booking2).exists())

    def test_06_customer_calendar_shows_released_slot_as_available(self):
        """Scenario 6: Customer calendar immediately displays the cancelled slot as AVAILABLE."""
        booking, _ = self._create_confirmed_booking(start_time=datetime.time(11, 0), end_time=datetime.time(12, 0))
        self.client.force_login(self.customer)

        # Cancel
        cancel_url = reverse('bookings:api_booking_cancel', kwargs={'booking_id': booking.id})
        self.client.post(cancel_url, {'reason': 'Cancelled'}, content_type='application/json')

        # Check calendar endpoint
        cal_url = f"{reverse('bookings:api_calendar_availability')}?start_date={self.target_date_str}&end_date={self.target_date_str}"
        res_cal = self.client.get(cal_url)
        self.assertEqual(res_cal.status_code, 200)

        slot = next(s for s in res_cal.json()['days'][0]['slots'] if s['start_time'] == '11:00')
        self.assertEqual(slot['status'], 'AVAILABLE')
        self.assertIsNone(slot['booking_details'])

    def test_07_manager_calendar_shows_slot_released(self):
        """Scenario 7: Manager calendar shows slot released and available after customer cancellation."""
        booking, _ = self._create_confirmed_booking(start_time=datetime.time(11, 0), end_time=datetime.time(12, 0))
        self.client.force_login(self.customer)

        cancel_url = reverse('bookings:api_booking_cancel', kwargs={'booking_id': booking.id})
        self.client.post(cancel_url, {'reason': 'Cancelled'}, content_type='application/json')

        # Manager inspects calendar
        self.client.force_login(self.manager)
        cal_url = f"{reverse('bookings:api_calendar_availability')}?start_date={self.target_date_str}&end_date={self.target_date_str}"
        res_cal = self.client.get(cal_url)
        self.assertEqual(res_cal.status_code, 200)

        slot = next(s for s in res_cal.json()['days'][0]['slots'] if s['start_time'] == '11:00')
        self.assertEqual(slot['status'], 'AVAILABLE')
        self.assertIsNone(slot['booking_details'])

    def test_08_cancelled_booking_remains_in_history(self):
        """Scenario 8: Cancelled booking is preserved in customer booking history portal."""
        booking, _ = self._create_confirmed_booking()
        self.client.force_login(self.customer)

        cancel_url = reverse('bookings:api_booking_cancel', kwargs={'booking_id': booking.id})
        self.client.post(cancel_url, {'reason': 'Rescheduling needed'}, content_type='application/json')

        history_url = reverse('dashboard:customer_bookings')
        res_hist = self.client.get(history_url)
        self.assertEqual(res_hist.status_code, 200)

        bookings_in_ctx = res_hist.context['bookings']
        self.assertTrue(any(b.id == booking.id and b.status == TestDriveBooking.Status.CANCELLED for b in bookings_in_ctx))

    def test_09_customer_cannot_cancel_same_booking_twice(self):
        """Scenario 9: Customer cannot cancel the same booking twice; repeated attempts return 400."""
        booking, _ = self._create_confirmed_booking()
        self.client.force_login(self.customer)

        cancel_url = reverse('bookings:api_booking_cancel', kwargs={'booking_id': booking.id})
        res1 = self.client.post(cancel_url, {'reason': 'First cancel'}, content_type='application/json')
        self.assertEqual(res1.status_code, 200)

        # Attempt 2
        res2 = self.client.post(cancel_url, {'reason': 'Second cancel attempt'}, content_type='application/json')
        self.assertEqual(res2.status_code, 400)
        self.assertIn("already been cancelled", res2.json()['error'])

    def test_10_customer_with_pending_booking_cannot_create_another(self):
        """Scenario 10: Customer with a PENDING booking cannot create another booking across cars/dates."""
        booking = TestDriveBooking.objects.create(
            customer=self.customer,
            assigned_manager=self.manager,
            car=self.car,
            preferred_date=self.target_date,
            start_time=self.start_time,
            end_time=self.end_time,
            driving_license_image=create_test_image('dl_pending.jpg'),
            license_verification_status=TestDriveBooking.LicenseVerificationStatus.PENDING,
            status=TestDriveBooking.Status.PENDING,
            pending_expires_at=timezone.now() + datetime.timedelta(hours=24)
        )
        ActiveSlotReservation.objects.create(
            slot_key=self.slot_key,
            slot_date=self.target_date,
            start_time=self.start_time,
            end_time=self.end_time,
            booking=booking,
            reservation_type=ActiveSlotReservation.ReservationType.PENDING,
            expires_at=booking.pending_expires_at
        )

        self.client.force_login(self.customer)
        # Attempt to book another car on another date
        payload = self._get_valid_payload(car=self.car2, date=(self.today + datetime.timedelta(days=4)).strftime('%Y-%m-%d'))
        res = self.client.post(self.api_book_url, payload)
        self.assertEqual(res.status_code, 400)

        err_msg = res.json()['error']
        self.assertIn("You already have an active test-drive appointment", err_msg)
        self.assertIn("RS e-tron GT", err_msg)
        self.assertIn("You can book another test drive after this appointment is completed or cancelled.", err_msg)

    def test_11_customer_with_confirmed_booking_cannot_create_another(self):
        """Scenario 11: Customer with a CONFIRMED booking cannot create another booking."""
        self._create_confirmed_booking()
        self.client.force_login(self.customer)

        payload = self._get_valid_payload(car=self.car2)
        res = self.client.post(self.api_book_url, payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("already have an active test-drive appointment", res.json()['error'])

    def test_12_customer_cannot_bypass_restriction_via_direct_api(self):
        """Scenario 12: Direct API submissions attempting to bypass one-active rule are strictly rejected."""
        self._create_confirmed_booking()
        self.client.force_login(self.customer)

        initial_booking_count = TestDriveBooking.objects.count()
        payload = self._get_valid_payload(car=self.car2, start_time='16:00')
        res = self.client.post(self.api_book_url, payload)
        self.assertEqual(res.status_code, 400)
        # Total booking records must remain unchanged
        self.assertEqual(TestDriveBooking.objects.count(), initial_booking_count)

    def test_13_customer_can_book_again_after_completed(self):
        """Scenario 13: Customer can schedule a new test drive after their previous booking is COMPLETED."""
        booking, res_obj = self._create_confirmed_booking()
        booking.status = TestDriveBooking.Status.COMPLETED
        booking.completed_at = timezone.now()
        booking.save()

        self.client.force_login(self.customer)
        payload = self._get_valid_payload(car=self.car2, start_time='15:00')
        res = self.client.post(self.api_book_url, payload)
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.json()['success'])

    def test_14_customer_can_book_again_after_cancelled(self):
        """Scenario 14: Customer can schedule a new test drive after their previous booking is CANCELLED."""
        booking, res_obj = self._create_confirmed_booking()
        booking.status = TestDriveBooking.Status.CANCELLED
        booking.cancelled_at = timezone.now()
        booking.save()
        res_obj.delete()

        self.client.force_login(self.customer)
        payload = self._get_valid_payload(car=self.car2, start_time='16:00')
        res = self.client.post(self.api_book_url, payload)
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.json()['success'])

    def test_15_customer_can_book_again_after_rejected(self):
        """Scenario 15: Customer can schedule a new test drive after their previous booking is REJECTED."""
        booking, res_obj = self._create_confirmed_booking()
        booking.status = TestDriveBooking.Status.REJECTED
        booking.license_verification_status = TestDriveBooking.LicenseVerificationStatus.REJECTED
        booking.rejection_reason = "Unreadable document"
        booking.save()
        res_obj.delete()

        self.client.force_login(self.customer)
        payload = self._get_valid_payload(car=self.car2, start_time='14:00')
        res = self.client.post(self.api_book_url, payload)
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.json()['success'])

    def test_16_customer_can_book_again_after_expired(self):
        """Scenario 16: Customer can schedule a new test drive after their previous booking is EXPIRED."""
        booking, res_obj = self._create_confirmed_booking()
        booking.status = TestDriveBooking.Status.EXPIRED
        booking.save()
        res_obj.delete()

        self.client.force_login(self.customer)
        payload = self._get_valid_payload(car=self.car, start_time='15:00')
        res = self.client.post(self.api_book_url, payload)
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.json()['success'])

    def test_17_another_customer_can_book_independently(self):
        """Scenario 17: Another customer without active bookings can book independently."""
        self._create_confirmed_booking(customer=self.customer, start_time=datetime.time(11, 0), end_time=datetime.time(12, 0))

        # Customer 2 books different slot
        self.client.force_login(self.customer2)
        payload = self._get_valid_payload(car=self.car2, start_time='15:00')
        res = self.client.post(self.api_book_url, payload)
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.json()['success'])

    def test_18_no_show_status_remains_blocking_until_resolved(self):
        """Scenario 18: NO_SHOW status is an active booking status that continues to block new bookings."""
        booking, _ = self._create_confirmed_booking()
        booking.status = TestDriveBooking.Status.NO_SHOW
        booking.save()

        self.client.force_login(self.customer)
        payload = self._get_valid_payload(car=self.car2)
        res = self.client.post(self.api_book_url, payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("already have an active test-drive appointment", res.json()['error'])

    def test_19_manager_can_mark_confirmed_appointment_completed(self):
        """Scenario 19: Showroom Manager marks confirmed appointment COMPLETED after slot end time."""
        past_date = self.today - datetime.timedelta(days=1)
        booking, _ = self._create_confirmed_booking(date=past_date, start_time=datetime.time(10, 0), end_time=datetime.time(11, 0))

        self.client.force_login(self.manager)
        complete_url = reverse('bookings:manager_booking_complete', kwargs={'booking_id': booking.id})
        res = self.client.post(complete_url, content_type='application/json')
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['status'], 'COMPLETED')

        booking.refresh_from_db()
        self.assertEqual(booking.status, TestDriveBooking.Status.COMPLETED)
        self.assertIsNotNone(booking.completed_at)

        # Audit activity logged
        act = BookingActivity.objects.filter(booking=booking, action=BookingActivity.Action.COMPLETED).first()
        self.assertIsNotNone(act)
        self.assertEqual(act.actor, self.manager)

        # Test chronological block: future appointment cannot be completed prematurely
        future_booking, _ = self._create_confirmed_booking(date=self.today + datetime.timedelta(days=3))
        res_future = self.client.post(
            reverse('bookings:manager_booking_complete', kwargs={'booking_id': future_booking.id}),
            content_type='application/json'
        )
        self.assertEqual(res_future.status_code, 400)
        self.assertIn("before the scheduled appointment end time", res_future.json()['error'])

    def test_20_customer_cannot_mark_booking_completed(self):
        """Scenario 20: Customer cannot mark appointments completed (403 Forbidden)."""
        booking, _ = self._create_confirmed_booking()
        self.client.force_login(self.customer)

        complete_url = reverse('bookings:manager_booking_complete', kwargs={'booking_id': booking.id})
        res = self.client.post(complete_url, content_type='application/json')
        self.assertEqual(res.status_code, 403)
        self.assertIn("Access denied", res.json()['error'])


class ManagerAuditRecordsAndTimelineTests(TestCase):
    """
    Test suite verifying the Manager Test Drive Records & Audit Logs portal,
    chronological timeline inspection, backend activity generation, and search/filtering (Section 10).
    """
    def setUp(self):
        self.customer = User.objects.create_user(
            username='neha_customer',
            email='neha.audit@example.com',
            password='Password123!',
            user_type=User.UserType.CUSTOMER
        )
        self.customer2 = User.objects.create_user(
            username='dev_customer',
            email='dev.audit@example.com',
            password='Password123!',
            user_type=User.UserType.CUSTOMER
        )
        self.manager = User.objects.create_user(
            username='rajesh_manager',
            email='rajesh.manager@example.com',
            password='Password123!',
            user_type=User.UserType.MANAGER,
            is_active=True
        )
        self.brand = Brand.objects.create(name='Porsche', slug='porsche-audit')
        self.car = Car.objects.create(
            title='Taycan 4S',
            slug='porsche-taycan-4s-audit',
            brand=self.brand,
            price=16500000.00,
            booking_amount=200000,
            is_available=True
        )
        self.car2 = Car.objects.create(
            title='Macan EV',
            slug='porsche-macan-ev-audit',
            brand=self.brand,
            price=12500000.00,
            booking_amount=150000,
            is_available=True
        )
        ShowroomSchedule.objects.all().update(
            is_open=True,
            open_time=datetime.time(9, 0),
            close_time=datetime.time(18, 0),
            slot_duration_minutes=60,
            is_active=True
        )
        ShowroomClosure.objects.filter(closure_type=ShowroomClosure.ClosureType.BREAK).update(
            is_active=True,
            start_time=datetime.time(13, 0),
            end_time=datetime.time(14, 0)
        )
        self.today = timezone.localdate()
        self.target_date = self.today + datetime.timedelta(days=2)
        self.target_date_str = self.target_date.strftime('%Y-%m-%d')
        self.records_url = reverse('dashboard:manager_records')
        self.api_book_url = reverse('bookings:api_booking_submission')

    def _create_booking(self, customer=None, car=None, date=None, start_time=None, end_time=None, status=TestDriveBooking.Status.PENDING):
        cust = customer or self.customer
        vehicle = car or self.car
        slot_d = date or self.target_date
        s_time = start_time or datetime.time(10, 0)
        e_time = end_time or datetime.time(11, 0)
        s_key = ActiveSlotReservation.generate_slot_key(slot_d, s_time)

        booking = TestDriveBooking.objects.create(
            customer=cust,
            assigned_manager=self.manager,
            car=vehicle,
            preferred_date=slot_d,
            start_time=s_time,
            end_time=e_time,
            driving_license_image=create_test_image('dl_audit.jpg'),
            license_verification_status=TestDriveBooking.LicenseVerificationStatus.PENDING,
            status=status,
            pending_expires_at=timezone.now() + datetime.timedelta(hours=24)
        )
        res_type = ActiveSlotReservation.ReservationType.CONFIRMED if status == TestDriveBooking.Status.CONFIRMED else ActiveSlotReservation.ReservationType.PENDING
        reservation = ActiveSlotReservation.objects.create(
            slot_key=s_key,
            slot_date=slot_d,
            start_time=s_time,
            end_time=e_time,
            booking=booking,
            reservation_type=res_type,
            expires_at=booking.pending_expires_at if res_type == ActiveSlotReservation.ReservationType.PENDING else None
        )
        return booking, reservation

    def test_01_new_booking_request_creates_audit_entry(self):
        """Scenario 1: Customer booking submission automatically logs REQUEST_SUBMITTED audit entry."""
        self.client.force_login(self.customer)
        payload = {
            'car_id': self.car.id,
            'preferred_date': self.target_date_str,
            'start_time': '10:00',
            'license_image': create_test_image('dl_req.jpg'),
            'customer_notes': 'Requested test drive for Porsche.',
            'terms_agreed': True,
        }
        res = self.client.post(self.api_book_url, payload)
        self.assertEqual(res.status_code, 201)

        booking = TestDriveBooking.objects.get(booking_number=res.json()['booking_number'])
        activity = BookingActivity.objects.filter(booking=booking, action=BookingActivity.Action.REQUEST_SUBMITTED).first()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.actor, self.customer)
        self.assertEqual(activity.new_status, TestDriveBooking.Status.PENDING)
        self.assertIn("Customer submitted test drive booking request", activity.notes)

    def test_02_dl_verification_creates_audit_entry(self):
        """Scenario 2: Showroom Manager DL verification creates a verified audit entry."""
        booking, _ = self._create_booking()
        self.client.force_login(self.manager)

        action_url = reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id})
        res = self.client.post(action_url, {'action': 'VERIFY'}, content_type='application/json')
        self.assertEqual(res.status_code, 200)

        activity = BookingActivity.objects.filter(booking=booking, actor=self.manager).first()
        self.assertIsNotNone(activity)
        self.assertIn("verified", activity.notes.lower())
        self.assertEqual(activity.activity_type_label, 'Licence Verified')

    def test_03_dl_rejection_records_manager_and_reason(self):
        """Scenario 3: Showroom Manager DL rejection records manager, timestamp, and mandatory reason."""
        booking, _ = self._create_booking()
        self.client.force_login(self.manager)

        action_url = reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id})
        res = self.client.post(action_url, {'action': 'REJECT', 'reason': 'Expired licence card'}, content_type='application/json')
        self.assertEqual(res.status_code, 200)

        activity = BookingActivity.objects.filter(booking=booking, action=BookingActivity.Action.REJECTED).first()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.actor, self.manager)
        self.assertIn('Expired licence card', activity.notes)
        self.assertEqual(activity.new_status, TestDriveBooking.Status.REJECTED)

    def test_04_final_confirmation_creates_audit_entry(self):
        """Scenario 4: Final appointment confirmation creates a CONFIRMED audit entry."""
        booking, _ = self._create_booking()
        self.client.force_login(self.manager)

        # 1. Verify
        self.client.post(reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id}), {'action': 'VERIFY'}, content_type='application/json')
        # 2. Confirm
        confirm_url = reverse('bookings:manager_booking_confirm', kwargs={'booking_id': booking.id})
        res = self.client.post(confirm_url, content_type='application/json')
        self.assertEqual(res.status_code, 200)

        activity = BookingActivity.objects.filter(booking=booking, action=BookingActivity.Action.CONFIRMED).first()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.actor, self.manager)
        self.assertEqual(activity.new_status, TestDriveBooking.Status.CONFIRMED)

    def test_05_customer_cancellation_creates_audit_entry(self):
        """Scenario 5: Customer cancellation logs CANCELLED audit entry with actor and reason."""
        booking, _ = self._create_booking(status=TestDriveBooking.Status.CONFIRMED)
        self.client.force_login(self.customer)

        cancel_url = reverse('bookings:api_booking_cancel', kwargs={'booking_id': booking.id})
        res = self.client.post(cancel_url, {'reason': 'Flight postponed'}, content_type='application/json')
        self.assertEqual(res.status_code, 200)

        activity = BookingActivity.objects.filter(booking=booking, action=BookingActivity.Action.CANCELLED).first()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.actor, self.customer)
        self.assertIn('Flight postponed', activity.notes)
        self.assertEqual(activity.new_status, TestDriveBooking.Status.CANCELLED)

    def test_06_manager_completion_creates_audit_entry(self):
        """Scenario 6: Manager marking test drive completed creates COMPLETED audit entry."""
        past_date = self.today - datetime.timedelta(days=1)
        booking, _ = self._create_booking(date=past_date, status=TestDriveBooking.Status.CONFIRMED)
        self.client.force_login(self.manager)

        complete_url = reverse('bookings:manager_booking_complete', kwargs={'booking_id': booking.id})
        res = self.client.post(complete_url, content_type='application/json')
        self.assertEqual(res.status_code, 200)

        activity = BookingActivity.objects.filter(booking=booking, action=BookingActivity.Action.COMPLETED).first()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.actor, self.manager)
        self.assertEqual(activity.new_status, TestDriveBooking.Status.COMPLETED)

    def test_07_expiry_events_logged_when_expiry_executes(self):
        """Scenario 7: Expiry cleanup process records System EXPIRED audit entry and releases slot."""
        booking, res = self._create_booking()
        # Set expiry in the past
        past_time = timezone.now() - datetime.timedelta(hours=2)
        booking.pending_expires_at = past_time
        booking.save()
        res.expires_at = past_time
        res.save()

        from apps.bookings.services import expire_stale_pending_reservations
        expired_count = expire_stale_pending_reservations()
        self.assertGreaterEqual(expired_count, 1)

        booking.refresh_from_db()
        self.assertEqual(booking.status, TestDriveBooking.Status.EXPIRED)

        activity = BookingActivity.objects.filter(booking=booking, action=BookingActivity.Action.EXPIRED).first()
        self.assertIsNotNone(activity)
        self.assertIsNone(activity.actor)
        self.assertEqual(activity.actor_display_name, "System")
        self.assertEqual(activity.new_status, TestDriveBooking.Status.EXPIRED)

    def test_08_historical_audit_records_not_overwritten(self):
        """Scenario 8: Multiple lifecycle steps create append-only records without overwriting history."""
        past_date = self.today - datetime.timedelta(days=1)
        booking, _ = self._create_booking(date=past_date)

        # 1. Request Submitted
        BookingActivity.objects.create(
            booking=booking,
            actor=self.customer,
            action=BookingActivity.Action.REQUEST_SUBMITTED,
            new_status='PENDING',
            notes="Initial request"
        )
        # 2. DL Verified
        self.client.force_login(self.manager)
        self.client.post(reverse('bookings:manager_license_action', kwargs={'booking_id': booking.id}), {'action': 'VERIFY'}, content_type='application/json')
        # 3. Confirmed
        self.client.post(reverse('bookings:manager_booking_confirm', kwargs={'booking_id': booking.id}), content_type='application/json')
        # 4. Completed
        self.client.post(reverse('bookings:manager_booking_complete', kwargs={'booking_id': booking.id}), content_type='application/json')

        activities = booking.activities.all().order_by('created_at')
        self.assertGreaterEqual(activities.count(), 4)

        # Verify all distinct actions exist
        actions = list(activities.values_list('action', flat=True))
        self.assertIn(BookingActivity.Action.REQUEST_SUBMITTED, actions)
        self.assertIn(BookingActivity.Action.CONFIRMED, actions)
        self.assertIn(BookingActivity.Action.COMPLETED, actions)

    def test_09_timeline_api_chronological_order(self):
        """Scenario 9: Manager booking timeline API returns all activities in ascending chronological order."""
        past_date = self.today - datetime.timedelta(days=1)
        booking, _ = self._create_booking(date=past_date)

        t1 = timezone.now() - datetime.timedelta(hours=3)
        t2 = timezone.now() - datetime.timedelta(hours=2)
        t3 = timezone.now() - datetime.timedelta(hours=1)

        a1 = BookingActivity.objects.create(booking=booking, actor=self.customer, action=BookingActivity.Action.REQUEST_SUBMITTED, notes="Step 1")
        a2 = BookingActivity.objects.create(booking=booking, actor=self.manager, action=BookingActivity.Action.NOTE_ADDED, notes="Step 2 verified")
        a3 = BookingActivity.objects.create(booking=booking, actor=self.manager, action=BookingActivity.Action.CONFIRMED, notes="Step 3 confirmed")

        # Manually assign distinct timestamps
        BookingActivity.objects.filter(id=a1.id).update(created_at=t1)
        BookingActivity.objects.filter(id=a2.id).update(created_at=t2)
        BookingActivity.objects.filter(id=a3.id).update(created_at=t3)

        self.client.force_login(self.manager)
        url = reverse('dashboard:manager_booking_timeline', kwargs={'booking_id': booking.id})
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertTrue(data['success'])
        events = data['timeline']
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0]['notes'], "Step 1")
        self.assertEqual(events[1]['notes'], "Step 2 verified")
        self.assertEqual(events[2]['notes'], "Step 3 confirmed")

    def test_10_search_and_filters(self):
        """Scenario 10: Records page filters by reference, customer, vehicle, activity type, and status."""
        b1, _ = self._create_booking(customer=self.customer, car=self.car, start_time=datetime.time(10, 0), end_time=datetime.time(11, 0), status=TestDriveBooking.Status.CONFIRMED)
        b2, _ = self._create_booking(customer=self.customer2, car=self.car2, start_time=datetime.time(11, 0), end_time=datetime.time(12, 0), status=TestDriveBooking.Status.CANCELLED)

        act1 = BookingActivity.objects.create(booking=b1, actor=self.manager, action=BookingActivity.Action.CONFIRMED, notes="Confirmed for Porsche")
        act2 = BookingActivity.objects.create(booking=b2, actor=self.customer2, action=BookingActivity.Action.CANCELLED, notes="Cancelled by customer")

        self.client.force_login(self.manager)

        # 1. Search by booking reference
        res_ref = self.client.get(f"{self.records_url}?q={b1.booking_number}")
        self.assertEqual(res_ref.status_code, 200)
        self.assertContains(res_ref, b1.booking_number)
        self.assertNotContains(res_ref, b2.booking_number)

        # 2. Filter by activity type CONFIRMED
        res_act = self.client.get(f"{self.records_url}?activity_type=CONFIRMED")
        self.assertEqual(res_act.status_code, 200)
        self.assertContains(res_act, b1.booking_number)
        self.assertNotContains(res_act, b2.booking_number)

        # 3. Filter by booking status CANCELLED
        res_stat = self.client.get(f"{self.records_url}?booking_status=CANCELLED")
        self.assertEqual(res_stat.status_code, 200)
        self.assertContains(res_stat, b2.booking_number)
        self.assertNotContains(res_stat, b1.booking_number)

    def test_11_pagination(self):
        """Scenario 11: Records page paginates large result sets properly."""
        booking, _ = self._create_booking()
        for i in range(20):
            BookingActivity.objects.create(
                booking=booking,
                actor=self.manager,
                action=BookingActivity.Action.NOTE_ADDED,
                notes=f"Audit note #{i+1}"
            )

        self.client.force_login(self.manager)
        res_p1 = self.client.get(f"{self.records_url}?page=1")
        self.assertEqual(res_p1.status_code, 200)
        self.assertEqual(len(res_p1.context['activities']), 15)

        res_p2 = self.client.get(f"{self.records_url}?page=2")
        self.assertEqual(res_p2.status_code, 200)
        self.assertEqual(len(res_p2.context['activities']), 5)

    def test_12_only_authorized_manager_can_access_records_page(self):
        """Scenario 12: Only authenticated Showroom Managers/Admins can access the records page."""
        # Anonymous
        self.client.logout()
        res_anon = self.client.get(self.records_url)
        self.assertEqual(res_anon.status_code, 302)  # Redirected to login

        # Customer
        self.client.force_login(self.customer)
        res_cust = self.client.get(self.records_url)
        self.assertEqual(res_cust.status_code, 403)

        # Manager
        self.client.force_login(self.manager)
        res_mgr = self.client.get(self.records_url)
        self.assertEqual(res_mgr.status_code, 200)
        self.assertContains(res_mgr, "Test Drive Records &amp; Audit Logs")

    def test_13_customers_cannot_read_timeline_api(self):
        """Scenario 13: Ordinary customers cannot query the Manager timeline API."""
        booking, _ = self._create_booking()
        timeline_url = reverse('dashboard:manager_booking_timeline', kwargs={'booking_id': booking.id})

        self.client.force_login(self.customer)
        res = self.client.get(timeline_url)
        self.assertEqual(res.status_code, 403)

    def test_14_licence_images_never_exposed_in_records(self):
        """Scenario 14: Sensitive document paths, images, and full licence numbers are not exposed in audit views."""
        booking, _ = self._create_booking()
        BookingActivity.objects.create(
            booking=booking,
            actor=self.customer,
            action=BookingActivity.Action.REQUEST_SUBMITTED,
            notes="Submitted document"
        )

        self.client.force_login(self.manager)
        res_page = self.client.get(self.records_url)
        self.assertEqual(res_page.status_code, 200)
        content = res_page.content.decode()

        self.assertNotIn("secure-document", content)
        self.assertNotIn("secure_licenses", content)
        self.assertNotIn("dl_audit.jpg", content)

        res_timeline = self.client.get(reverse('dashboard:manager_booking_timeline', kwargs={'booking_id': booking.id}))
        self.assertEqual(res_timeline.status_code, 200)
        tl_content = res_timeline.content.decode()

        self.assertNotIn("secure-document", tl_content)
        self.assertNotIn("secure_licenses", tl_content)
        self.assertNotIn("dl_audit.jpg", tl_content)

    def test_15_existing_booking_workflows_continue_working(self):
        """Scenario 15: Existing customer booking, calendar availability, and manager verification workflows remain functional."""
        # 1. Customer queries availability
        self.client.force_login(self.customer)
        cal_url = f"{reverse('bookings:api_calendar_availability')}?start_date={self.target_date_str}&end_date={self.target_date_str}&car_id={self.car.id}"
        res_cal = self.client.get(cal_url)
        self.assertEqual(res_cal.status_code, 200)
        self.assertIn('days', res_cal.json())

        # 2. Customer submits booking
        payload = {
            'car_id': self.car.id,
            'preferred_date': self.target_date_str,
            'start_time': '10:00',
            'license_image': create_test_image('dl_e2e.jpg'),
            'terms_agreed': True,
        }
        res_sub = self.client.post(self.api_book_url, payload)
        self.assertEqual(res_sub.status_code, 201)
        booking_id = res_sub.json()['booking_id']

        # 3. Manager verifies
        self.client.force_login(self.manager)
        res_v = self.client.post(reverse('bookings:manager_license_action', kwargs={'booking_id': booking_id}), {'action': 'VERIFY'}, content_type='application/json')
        self.assertEqual(res_v.status_code, 200)

        # 4. Manager confirms
        res_c = self.client.post(reverse('bookings:manager_booking_confirm', kwargs={'booking_id': booking_id}), content_type='application/json')
        self.assertEqual(res_c.status_code, 200)

        # 5. Customer cancels
        self.client.force_login(self.customer)
        res_can = self.client.post(reverse('bookings:api_booking_cancel', kwargs={'booking_id': booking_id}), {'reason': 'E2E cancel'}, content_type='application/json')
        self.assertEqual(res_can.status_code, 200)

        # 6. Customer booking history shows cancelled
        res_hist = self.client.get(reverse('dashboard:customer_bookings'))
        self.assertEqual(res_hist.status_code, 200)
        self.assertContains(res_hist, res_sub.json()['booking_number'])






