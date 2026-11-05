from decimal import Decimal
import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.cars.models import Car, Brand
from apps.bookings.models import CarBooking, TestDriveBooking, CustomerNotification
from apps.payments.models import Payment


class CustomerDashboardSeparationTests(TestCase):
    """
    Unit & integration tests verifying strict separation between:
    - Customer Vehicle Reservations (/dashboard/vehicle-reservations/)
    - Customer Test Drive Appointments (/dashboard/test-drive-appointments/)
    And confirmation popup isolation.
    """

    def setUp(self):
        self.client = Client()

        # Users
        self.customer = User.objects.create_user(
            username='cust_alex',
            email='alex@example.com',
            password='Password123!',
            user_type=User.UserType.CUSTOMER
        )
        self.other_customer = User.objects.create_user(
            username='cust_bob',
            email='bob@example.com',
            password='Password123!',
            user_type=User.UserType.CUSTOMER
        )
        self.manager = User.objects.create_user(
            username='mgr_sarah',
            email='sarah@example.com',
            password='Password123!',
            user_type=User.UserType.MANAGER
        )

        # Vehicle data
        self.brand = Brand.objects.create(name='Honda')
        self.car = Car.objects.create(
            brand=self.brand,
            title='Elevate ZX CVT',
            slug='honda-elevate-zx-cvt',
            price=Decimal('1650000.00'),
            booking_amount=Decimal('25000.00'),
            body_type='SUV',
            fuel_type='PETROL',
            transmission='AUTOMATIC',
            seating_capacity=5,
            stock_quantity=5,
            is_available=True
        )

        # CarBooking for Customer
        self.car_booking = CarBooking.objects.create(
            booking_id='BK-CUST1234',
            customer=self.customer,
            car=self.car,
            booking_amount=Decimal('25000.00'),
            payment_status=CarBooking.PaymentStatus.PAID,
            booking_status=CarBooking.BookingStatus.CONFIRMED
        )
        self.payment = Payment.objects.create(
            booking=self.car_booking,
            razorpay_order_id='order_dash_test_1',
            razorpay_payment_id='pay_dash_test_1',
            amount=Decimal('25000.00'),
            currency='INR',
            payment_status=Payment.PaymentStatus.SUCCESS,
            paid_at=timezone.now()
        )

        # TestDriveBooking for Customer
        self.td_booking = TestDriveBooking.objects.create(
            booking_number='TD-CUST9876',
            customer=self.customer,
            car=self.car,
            preferred_date=datetime.date.today() + datetime.timedelta(days=2),
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            time_slot='10:00-11:00',
            status=TestDriveBooking.Status.CONFIRMED,
            license_verification_status=TestDriveBooking.LicenseVerificationStatus.VERIFIED
        )

    # ==============================================================================
    # 1. Page A: Vehicle Reservations Isolation
    # ==============================================================================
    def test_vehicle_reservations_page_shows_only_car_bookings(self):
        """Vehicle reservation page renders only CarBooking records, never Test Drives."""
        self.client.force_login(self.customer)
        url = reverse('dashboard:vehicle_reservations')
        res = self.client.get(url)

        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, 'dashboard/vehicle_reservations.html')
        self.assertContains(res, 'BK-CUST1234')
        self.assertContains(res, 'Honda')
        self.assertContains(res, 'Elevate ZX CVT')
        self.assertContains(res, '₹25,000')
        self.assertContains(res, 'Verified (PAID)')
        self.assertContains(res, 'Confirmed')
        self.assertContains(res, 'pay_dash_test_1')
        self.assertContains(res, 'View Vehicle')
        self.assertContains(res, 'View Receipt')

        # Strictly must NOT contain TestDriveBooking
        self.assertNotContains(res, 'TD-CUST9876')
        self.assertNotContains(res, 'Showroom Test Drive')
        self.assertNotContains(res, 'Test Drive Confirmed!')

    # ==============================================================================
    # 2. Page B: Test Drive Appointments Isolation
    # ==============================================================================
    def test_test_drive_appointments_page_shows_only_test_drive_bookings(self):
        """Test Drive appointments page renders only TestDriveBooking records, never CarBookings."""
        self.client.force_login(self.customer)
        url = reverse('dashboard:test_drive_appointments')
        res = self.client.get(url)

        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, 'dashboard/test_drive_appointments.html')
        self.assertContains(res, 'TD-CUST9876')
        self.assertContains(res, 'Document Verified')
        self.assertContains(res, '10:00 - 11:00')

        # Strictly must NOT contain CarBooking
        self.assertNotContains(res, 'BK-CUST1234')
        self.assertNotContains(res, 'pay_dash_test_1')
        self.assertNotContains(res, 'Advance Paid')

    # ==============================================================================
    # 3. Customer Ownership Isolation (Cannot view another user's bookings)
    # ==============================================================================
    def test_customer_cannot_see_other_customer_bookings(self):
        """Customer B cannot see Customer A's CarBooking or TestDriveBooking."""
        self.client.force_login(self.other_customer)

        # Vehicle Reservations
        res_veh = self.client.get(reverse('dashboard:vehicle_reservations'))
        self.assertEqual(res_veh.status_code, 200)
        self.assertNotContains(res_veh, 'BK-CUST1234')
        self.assertContains(res_veh, 'No Vehicle Reservations Yet')

        # Test Drive Appointments
        res_td = self.client.get(reverse('dashboard:test_drive_appointments'))
        self.assertEqual(res_td.status_code, 200)
        self.assertNotContains(res_td, 'TD-CUST9876')
        self.assertContains(res_td, 'No Test Drive Bookings Yet')

    # ==============================================================================
    # 4. Independent Empty States
    # ==============================================================================
    def test_independent_empty_states(self):
        """Empty states display correctly and independently when no records exist."""
        # Create user with 0 bookings
        new_customer = User.objects.create_user(
            username='cust_empty',
            email='empty@example.com',
            password='Password123!',
            user_type=User.UserType.CUSTOMER
        )
        self.client.force_login(new_customer)

        res_veh = self.client.get(reverse('dashboard:vehicle_reservations'))
        self.assertContains(res_veh, 'No Vehicle Reservations Yet')
        self.assertContains(res_veh, 'Browse Showroom Inventory')

        res_td = self.client.get(reverse('dashboard:test_drive_appointments'))
        self.assertContains(res_td, 'No Test Drive Bookings Yet')
        self.assertContains(res_td, 'Explore Cars Now')

    # ==============================================================================
    # 5. Vehicle Booking Receipt Never Shows Test Drive Confirmation Popup
    # ==============================================================================
    def test_vehicle_receipt_never_displays_test_drive_confirmation(self):
        """
        Even when a customer has an unread Test Drive notification,
        the vehicle receipt page strictly suppresses the Test Drive modal.
        """
        # Create unread test drive confirmation notification for customer
        CustomerNotification.objects.create(
            user=self.customer,
            notification_type=CustomerNotification.NotificationType.BOOKING_CONFIRMED,
            title="Test Drive Confirmed!",
            message="Your Driving Licence has been reviewed and your test-drive appointment has been confirmed.",
            booking_reference="TD-CUST9876",
            car_title="Honda Elevate ZX CVT",
            is_read=False
        )

        self.client.force_login(self.customer)
        receipt_url = reverse('payments:booking_success', kwargs={'booking_id': self.car_booking.booking_id})
        res = self.client.get(receipt_url)

        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Vehicle Advance Reservation Confirmed!')
        # Must NOT contain Test Drive confirmation popup text
        self.assertNotContains(res, 'Test Drive Confirmed!')
        self.assertNotContains(res, 'modalCustomerRejectionNotice')
        self.assertNotContains(res, 'notifications.js')

    # ==============================================================================
    # 6. Unauthenticated Access Redirects to Login
    # ==============================================================================
    def test_unauthenticated_access_redirects_to_login(self):
        """Guests are redirected to login with next parameter."""
        res_veh = self.client.get(reverse('dashboard:vehicle_reservations'))
        self.assertEqual(res_veh.status_code, 302)
        self.assertIn('/accounts/login/?next=', res_veh.url)

        res_td = self.client.get(reverse('dashboard:test_drive_appointments'))
        self.assertEqual(res_td.status_code, 302)
        self.assertIn('/accounts/login/?next=', res_td.url)

    # ==============================================================================
    # 7. Backward Compatibility: Legacy customer_bookings URL
    # ==============================================================================
    def test_legacy_customer_bookings_url_backward_compatibility(self):
        """Legacy /dashboard/my-bookings/ continues to resolve and render without errors."""
        self.client.force_login(self.customer)
        res = self.client.get(reverse('dashboard:customer_bookings'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'TD-CUST9876')


class ManagerVehicleReservationRecordsTests(TestCase):
    """
    Unit & integration tests verifying:
    - Manager-only access to Vehicle Reservation Records
    - Customer & unauthorized staff 403 Forbidden enforcement
    - Display of customer, vehicle, payment, and reservation info
    - Search and filter functionality
    - Strictly read-only enforcement (no POST / modification capabilities)
    """

    def setUp(self):
        self.client = Client()

        # Manager user
        self.manager = User.objects.create_user(
            username='mgr_vikram',
            email='vikram@carvistahub.in',
            password='Password123!',
            user_type=User.UserType.MANAGER
        )

        # Customer user
        self.customer = User.objects.create_user(
            username='cust_riya',
            first_name='Riya',
            last_name='Sharma',
            email='riya@example.com',
            phone_number='+919876543210',
            password='Password123!',
            user_type=User.UserType.CUSTOMER
        )

        # Second Customer
        self.customer_two = User.objects.create_user(
            username='cust_karan',
            first_name='Karan',
            last_name='Mehta',
            email='karan@example.com',
            phone_number='+919811223344',
            password='Password123!',
            user_type=User.UserType.CUSTOMER
        )

        # Non-manager Staff user
        self.staff_user = User.objects.create_user(
            username='staff_clerk',
            email='clerk@carvistahub.in',
            password='Password123!',
            user_type=User.UserType.CUSTOMER,
            is_staff=True
        )

        # Vehicle Brands & Cars
        self.brand_honda = Brand.objects.create(name='Honda')
        self.car_elevate = Car.objects.create(
            brand=self.brand_honda,
            title='Elevate ZX CVT',
            slug='honda-elevate-zx-cvt',
            price=Decimal('1650000.00'),
            booking_amount=Decimal('25000.00'),
            body_type='SUV',
            fuel_type='PETROL',
            transmission='AUTOMATIC',
            seating_capacity=5,
            stock_quantity=4,
            is_available=True
        )

        self.brand_kia = Brand.objects.create(name='Kia')
        self.car_seltos = Car.objects.create(
            brand=self.brand_kia,
            title='Seltos GTX Plus',
            slug='kia-seltos-gtx-plus',
            price=Decimal('1980000.00'),
            booking_amount=Decimal('30000.00'),
            body_type='SUV',
            fuel_type='DIESEL',
            transmission='AUTOMATIC',
            seating_capacity=5,
            stock_quantity=2,
            is_available=True
        )

        # Booking 1: Confirmed and Paid
        self.booking_one = CarBooking.objects.create(
            booking_id='BK-MGR1111',
            customer=self.customer,
            car=self.car_elevate,
            booking_amount=Decimal('25000.00'),
            payment_status=CarBooking.PaymentStatus.PAID,
            booking_status=CarBooking.BookingStatus.CONFIRMED
        )
        self.payment_one = Payment.objects.create(
            booking=self.booking_one,
            razorpay_order_id='order_mgr_elevate_01',
            razorpay_payment_id='pay_mgr_elevate_01',
            amount=Decimal('25000.00'),
            currency='INR',
            payment_method='Netbanking (SBI)',
            payment_status=Payment.PaymentStatus.SUCCESS,
            paid_at=timezone.now()
        )

        # Booking 2: Pending Allocation
        self.booking_two = CarBooking.objects.create(
            booking_id='BK-MGR2222',
            customer=self.customer_two,
            car=self.car_seltos,
            booking_amount=Decimal('30000.00'),
            payment_status=CarBooking.PaymentStatus.PAID,
            booking_status=CarBooking.BookingStatus.PENDING
        )
        self.payment_two = Payment.objects.create(
            booking=self.booking_two,
            razorpay_order_id='order_mgr_seltos_02',
            razorpay_payment_id='pay_mgr_seltos_02',
            amount=Decimal('30000.00'),
            currency='INR',
            payment_method='UPI',
            payment_status=Payment.PaymentStatus.SUCCESS,
            paid_at=timezone.now()
        )

        self.url = reverse('dashboard:manager_vehicle_reservations')

    def test_manager_can_access_vehicle_reservations_page(self):
        """Active Showroom Manager can view all vehicle reservations with complete information."""
        self.client.force_login(self.manager)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/manager_vehicle_reservations.html')

        # Contains summary stats
        self.assertContains(response, 'Vehicle Reservation Records')
        self.assertContains(response, 'Manager Audit Register')
        self.assertContains(response, 'Read-Only Module')

        # Contains Booking 1 details
        self.assertContains(response, 'BK-MGR1111')
        self.assertContains(response, 'Riya Sharma')
        self.assertContains(response, 'riya@example.com')
        self.assertContains(response, '+919876543210')
        self.assertContains(response, 'Elevate ZX CVT')
        self.assertContains(response, 'Honda')
        self.assertContains(response, '₹25,000')
        self.assertContains(response, 'pay_mgr_elevate_01')
        self.assertContains(response, 'order_mgr_elevate_01')

        # Contains Booking 2 details
        self.assertContains(response, 'BK-MGR2222')
        self.assertContains(response, 'Karan Mehta')
        self.assertContains(response, 'karan@example.com')
        self.assertContains(response, '+919811223344')
        self.assertContains(response, 'Seltos GTX Plus')
        self.assertContains(response, 'Kia')
        self.assertContains(response, '₹30,000')
        self.assertContains(response, 'pay_mgr_seltos_02')
        self.assertContains(response, 'order_mgr_seltos_02')

    def test_customer_cannot_access_manager_vehicle_reservations_page(self):
        """Regular customer accounts receive 403 Forbidden."""
        self.client.force_login(self.customer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_unauthorized_staff_cannot_access_manager_vehicle_reservations_page(self):
        """Non-manager staff accounts receive 403 Forbidden."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_user_redirected_to_login(self):
        """Guests are redirected to the login portal with next destination."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/?next=', response.url)

    def test_search_by_booking_reference(self):
        """Manager can search specifically by booking reference ID."""
        self.client.force_login(self.manager)
        response = self.client.get(f"{self.url}?q=BK-MGR1111")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'BK-MGR1111')
        self.assertNotContains(response, 'BK-MGR2222')

    def test_search_by_customer_name_or_email(self):
        """Manager can search by customer name or email address."""
        self.client.force_login(self.manager)

        # Search by name
        res_name = self.client.get(f"{self.url}?q=Karan")
        self.assertContains(res_name, 'BK-MGR2222')
        self.assertNotContains(res_name, 'BK-MGR1111')

        # Search by email
        res_email = self.client.get(f"{self.url}?q=riya@example.com")
        self.assertContains(res_email, 'BK-MGR1111')
        self.assertNotContains(res_email, 'BK-MGR2222')

    def test_search_by_car_brand_or_model(self):
        """Manager can search by car brand or model."""
        self.client.force_login(self.manager)

        # Search by brand
        res_brand = self.client.get(f"{self.url}?q=Kia")
        self.assertContains(res_brand, 'Seltos GTX Plus')
        self.assertNotContains(res_brand, 'Elevate ZX CVT')

        # Search by model
        res_model = self.client.get(f"{self.url}?q=Elevate")
        self.assertContains(res_model, 'BK-MGR1111')
        self.assertNotContains(res_model, 'BK-MGR2222')

    def test_filter_by_booking_status(self):
        """Manager can filter records by reservation status."""
        self.client.force_login(self.manager)

        # Filter Confirmed
        res_conf = self.client.get(f"{self.url}?booking_status=CONFIRMED")
        self.assertContains(res_conf, 'BK-MGR1111')
        self.assertNotContains(res_conf, 'BK-MGR2222')

        # Filter Pending
        res_pend = self.client.get(f"{self.url}?booking_status=PENDING")
        self.assertContains(res_pend, 'BK-MGR2222')
        self.assertNotContains(res_pend, 'BK-MGR1111')

    def test_strictly_read_only_nature(self):
        """
        Verify the view strictly rejects POST attempts and contains no
        state-mutating forms or action triggers.
        """
        self.client.force_login(self.manager)

        # 1. POST request must receive 405 Method Not Allowed
        post_res = self.client.post(self.url, {'action': 'CONFIRM'})
        self.assertEqual(post_res.status_code, 405)

        # 2. Main content block must not contain any mutation form methods or action endpoints
        get_res = self.client.get(self.url)
        content_html = get_res.content.decode('utf-8')
        main_content = content_html[content_html.find('<main'):content_html.find('</main>')]
        self.assertNotIn('method="POST"', main_content)
        self.assertNotIn('method="post"', main_content)
        self.assertNotIn('Cancel Reservation', main_content)
        self.assertNotIn('Refund Payment', main_content)
        self.assertNotIn('Mark Delivered', main_content)
        self.assertNotIn('Confirm Reservation', main_content)

