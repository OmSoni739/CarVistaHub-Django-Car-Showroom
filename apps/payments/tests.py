"""
Unit and Integration Tests for Razorpay Car Booking Backend.
Covers order generation, HMAC-SHA256 signature verification, server-side capture checks,
atomic stock management safeguards, concurrency & race-condition handling, and non-interference.
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock
import razorpay.errors

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.db import DatabaseError

from apps.cars.models import Brand, Car
from apps.bookings.models import CarBooking, CustomerNotification
from apps.payments.models import Payment
from apps.payments.services import (
    get_razorpay_client,
    initiate_car_booking_order,
    verify_and_process_car_booking_payment,
    RazorpayConfigError,
    StockUnavailableError,
    PaymentOwnershipError,
    PaymentVerificationError,
)

User = get_user_model()


class RazorpayBackendTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Create test users
        self.customer = User.objects.create_user(
            username='test_customer',
            email='customer@example.com',
            password='testpassword123',
            user_type=User.UserType.CUSTOMER,
            phone_number='9876543210'
        )

        self.other_customer = User.objects.create_user(
            username='other_customer',
            email='other@example.com',
            password='testpassword123',
            user_type=User.UserType.CUSTOMER,
            phone_number='9876543211'
        )

        self.manager = User.objects.create_user(
            username='test_manager',
            email='manager@example.com',
            password='testpassword123',
            user_type=User.UserType.MANAGER,
            is_active=True
        )

        # Create brand and car
        self.brand = Brand.objects.create(name='Tata Motors', slug='tata-motors')
        self.car = Car.objects.create(
            title='Harrier Fearless Plus',
            slug='tata-harrier-fearless-plus',
            brand=self.brand,
            body_type=Car.BodyType.SUV,
            price=Decimal('2500000.00'),
            booking_amount=Decimal('30000.00'),
            fuel_type=Car.FuelType.DIESEL,
            transmission=Car.Transmission.AUTOMATIC,
            engine_capacity='1956 cc',
            stock_quantity=3,
            is_available=True
        )

        self.create_order_url = reverse('payments:create_order')
        self.verify_payment_url = reverse('payments:verify_payment')

    # ==============================================================================
    # 1. Missing Razorpay Credentials
    # ==============================================================================
    @override_settings(RAZORPAY_KEY_ID='', RAZORPAY_KEY_SECRET='')
    def test_missing_razorpay_credentials(self):
        """Should raise RazorpayConfigError when credentials are missing and not expose secrets in API."""
        with self.assertRaises(RazorpayConfigError):
            get_razorpay_client()

        self.client.force_login(self.customer)
        response = self.client.post(
            self.create_order_url,
            data={'car_id': self.car.id},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertIn('error', data)
        self.assertNotIn('secret', data['error'].lower())

    # ==============================================================================
    # 2. Authentication & Role Enforcement
    # ==============================================================================
    def test_unauthenticated_user_create_order(self):
        """Unauthenticated user cannot create order, redirected or rejected."""
        response = self.client.post(
            self.create_order_url,
            data={'car_id': self.car.id},
            content_type='application/json'
        )
        # login_required decorator redirects unauthenticated users
        self.assertEqual(response.status_code, 302)

    def test_non_customer_user_create_order(self):
        """Showroom Managers cannot initiate customer vehicle advance booking orders."""
        self.client.force_login(self.manager)
        response = self.client.post(
            self.create_order_url,
            data={'car_id': self.car.id},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn('customer accounts', response.json().get('error', '').lower())

    # ==============================================================================
    # 3. Stock & Availability Validation before Order Creation
    # ==============================================================================
    def test_out_of_stock_car_create_order(self):
        """Cannot create booking order for a car with stock_quantity = 0 or is_available = False."""
        self.car.stock_quantity = 0
        self.car.save()

        self.client.force_login(self.customer)
        response = self.client.post(
            self.create_order_url,
            data={'car_id': self.car.id},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('out of stock', response.json().get('error', '').lower())

        # Test is_available = False
        self.car.stock_quantity = 2
        self.car.is_available = False
        self.car.save()

        response2 = self.client.post(
            self.create_order_url,
            data={'car_id': self.car.id},
            content_type='application/json'
        )
        self.assertEqual(response2.status_code, 400)

    # ==============================================================================
    # 4. Successful Order Creation & Rupees-to-Paise Conversion
    # ==============================================================================
    @patch('apps.payments.services.get_razorpay_client')
    def test_successful_order_creation_and_paise_conversion(self, mock_get_client):
        """
        Creates Razorpay order with amount in integer paise (₹30,000 -> 3000000 paise).
        Creates CarBooking and Payment with PENDING status.
        Does NOT deduct stock.
        """
        mock_client = MagicMock()
        mock_client.order.create.return_value = {'id': 'order_test_12345'}
        mock_get_client.return_value = mock_client

        initial_stock = self.car.stock_quantity

        self.client.force_login(self.customer)
        response = self.client.post(
            self.create_order_url,
            data={'car_id': self.car.id},
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['razorpay_order_id'], 'order_test_12345')
        # ₹30,000.00 * 100 = 3,000,000 paise
        self.assertEqual(data['amount'], 3000000)

        # Verify Razorpay client was called with exact integer paise
        mock_client.order.create.assert_called_once()
        create_args = mock_client.order.create.call_args[1]['data']
        self.assertEqual(create_args['amount'], 3000000)
        self.assertEqual(create_args['currency'], 'INR')

        # Verify database records created with PENDING
        booking = CarBooking.objects.get(booking_id=data['booking_id'])
        self.assertEqual(booking.payment_status, CarBooking.PaymentStatus.PENDING)
        self.assertEqual(booking.booking_status, CarBooking.BookingStatus.PENDING)
        self.assertEqual(booking.booking_amount, Decimal('30000.00'))

        payment = Payment.objects.get(razorpay_order_id='order_test_12345')
        self.assertEqual(payment.booking, booking)
        self.assertEqual(payment.payment_status, Payment.PaymentStatus.PENDING)
        self.assertEqual(payment.amount, Decimal('30000.00'))

        # Stock must remain UNTOUCHED
        self.car.refresh_from_db()
        self.assertEqual(self.car.stock_quantity, initial_stock)

    # ==============================================================================
    # 5. Payment Retry without Duplicate Records
    # ==============================================================================
    @patch('apps.payments.services.get_razorpay_client')
    def test_payment_retry_reuses_pending_booking(self, mock_get_client):
        """Retrying an uncompleted order updates the existing booking/payment rather than duplicating."""
        mock_client = MagicMock()
        mock_client.order.create.side_effect = [
            {'id': 'order_first_111'},
            {'id': 'order_retry_222'}
        ]
        mock_get_client.return_value = mock_client

        self.client.force_login(self.customer)

        # Attempt 1
        res1 = self.client.post(self.create_order_url, data={'car_id': self.car.id}, content_type='application/json')
        booking_id_1 = res1.json()['booking_id']

        # Attempt 2 (Retry)
        res2 = self.client.post(self.create_order_url, data={'car_id': self.car.id}, content_type='application/json')
        booking_id_2 = res2.json()['booking_id']

        # Reuses same booking ID
        self.assertEqual(booking_id_1, booking_id_2)
        self.assertEqual(CarBooking.objects.filter(customer=self.customer, car=self.car).count(), 1)
        self.assertEqual(Payment.objects.filter(booking__booking_id=booking_id_1).count(), 1)

        # Payment record updated with new order ID
        payment = Payment.objects.get(booking__booking_id=booking_id_1)
        self.assertEqual(payment.razorpay_order_id, 'order_retry_222')

    # ==============================================================================
    # 6. Invalid Signature Handling
    # ==============================================================================
    @patch('apps.payments.services.get_razorpay_client')
    def test_invalid_signature_rejection(self, mock_get_client):
        """Invalid signature fails verification, marks records FAILED, and does not alter stock."""
        mock_client = MagicMock()
        mock_client.utility.verify_payment_signature.side_effect = razorpay.errors.SignatureVerificationError("Signature mismatch")
        mock_get_client.return_value = mock_client

        # Setup pending booking & payment
        booking = CarBooking.objects.create(
            customer=self.customer,
            car=self.car,
            booking_amount=Decimal('30000.00'),
            payment_status=CarBooking.PaymentStatus.PENDING,
            booking_status=CarBooking.BookingStatus.PENDING
        )
        payment = Payment.objects.create(
            booking=booking,
            razorpay_order_id='order_inv_sig',
            amount=Decimal('30000.00'),
            currency='INR',
            payment_status=Payment.PaymentStatus.PENDING
        )

        initial_stock = self.car.stock_quantity

        self.client.force_login(self.customer)
        response = self.client.post(
            self.verify_payment_url,
            data={
                'razorpay_order_id': 'order_inv_sig',
                'razorpay_payment_id': 'pay_fake_123',
                'razorpay_signature': 'bad_signature_string'
            },
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        payment.refresh_from_db()
        booking.refresh_from_db()
        self.assertEqual(payment.payment_status, Payment.PaymentStatus.FAILED)
        self.assertEqual(booking.payment_status, CarBooking.PaymentStatus.FAILED)

        # Zero stock deduction
        self.car.refresh_from_db()
        self.assertEqual(self.car.stock_quantity, initial_stock)

    # ==============================================================================
    # 7. Gateway Validation: Mismatched Order ID, Amount, Currency, Uncaptured
    # ==============================================================================
    @patch('apps.payments.services.get_razorpay_client')
    def test_gateway_mismatched_order_id(self, mock_get_client):
        """Fails if Razorpay reports payment belonging to a different order."""
        mock_client = MagicMock()
        mock_client.utility.verify_payment_signature.return_value = True
        mock_client.payment.fetch.return_value = {
            'id': 'pay_xyz',
            'order_id': 'order_different_999',
            'amount': 3000000,
            'currency': 'INR',
            'status': 'captured'
        }
        mock_get_client.return_value = mock_client

        booking = CarBooking.objects.create(customer=self.customer, car=self.car, booking_amount=Decimal('30000.00'))
        Payment.objects.create(booking=booking, razorpay_order_id='order_expected', amount=Decimal('30000.00'))

        self.client.force_login(self.customer)
        response = self.client.post(
            self.verify_payment_url,
            data={'razorpay_order_id': 'order_expected', 'razorpay_payment_id': 'pay_xyz', 'razorpay_signature': 'valid'},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('order id', response.json().get('error', '').lower())

    @patch('apps.payments.services.get_razorpay_client')
    def test_gateway_mismatched_amount(self, mock_get_client):
        """Fails if Razorpay reports a payment amount different than expected advance fee."""
        mock_client = MagicMock()
        mock_client.utility.verify_payment_signature.return_value = True
        mock_client.payment.fetch.return_value = {
            'id': 'pay_xyz',
            'order_id': 'order_expected',
            'amount': 1000000,  # ₹10,000 instead of ₹30,000
            'currency': 'INR',
            'status': 'captured'
        }
        mock_get_client.return_value = mock_client

        booking = CarBooking.objects.create(customer=self.customer, car=self.car, booking_amount=Decimal('30000.00'))
        Payment.objects.create(booking=booking, razorpay_order_id='order_expected', amount=Decimal('30000.00'))

        self.client.force_login(self.customer)
        response = self.client.post(
            self.verify_payment_url,
            data={'razorpay_order_id': 'order_expected', 'razorpay_payment_id': 'pay_xyz', 'razorpay_signature': 'valid'},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('amount mismatch', response.json().get('error', '').lower())

    @patch('apps.payments.services.get_razorpay_client')
    def test_gateway_uncaptured_payment(self, mock_get_client):
        """Fails if Razorpay reports payment as authorized or failed instead of captured."""
        mock_client = MagicMock()
        mock_client.utility.verify_payment_signature.return_value = True
        mock_client.payment.fetch.return_value = {
            'id': 'pay_xyz',
            'order_id': 'order_expected',
            'amount': 3000000,
            'currency': 'INR',
            'status': 'authorized'  # Not yet captured
        }
        mock_get_client.return_value = mock_client

        booking = CarBooking.objects.create(customer=self.customer, car=self.car, booking_amount=Decimal('30000.00'))
        Payment.objects.create(booking=booking, razorpay_order_id='order_expected', amount=Decimal('30000.00'))

        self.client.force_login(self.customer)
        response = self.client.post(
            self.verify_payment_url,
            data={'razorpay_order_id': 'order_expected', 'razorpay_payment_id': 'pay_xyz', 'razorpay_signature': 'valid'},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('not captured', response.json().get('error', '').lower())

    # ==============================================================================
    # 8. Successful Payment Verification & Exactly One Stock Deduction
    # ==============================================================================
    @patch('apps.payments.services.get_razorpay_client')
    def test_successful_captured_payment_and_stock_deduction(self, mock_get_client):
        """
        Valid payment signature + captured status:
        - Deducts exactly 1 unit of stock
        - Updates Payment to SUCCESS
        - Updates CarBooking to PAID and CONFIRMED
        - Dispatches customer confirmation notification
        """
        mock_client = MagicMock()
        mock_client.utility.verify_payment_signature.return_value = True
        mock_client.payment.fetch.return_value = {
            'id': 'pay_success_123',
            'order_id': 'order_success_123',
            'amount': 3000000,
            'currency': 'INR',
            'status': 'captured',
            'method': 'upi'
        }
        mock_get_client.return_value = mock_client

        initial_stock = self.car.stock_quantity  # 3
        booking = CarBooking.objects.create(customer=self.customer, car=self.car, booking_amount=Decimal('30000.00'))
        payment = Payment.objects.create(booking=booking, razorpay_order_id='order_success_123', amount=Decimal('30000.00'))

        self.client.force_login(self.customer)
        response = self.client.post(
            self.verify_payment_url,
            data={
                'razorpay_order_id': 'order_success_123',
                'razorpay_payment_id': 'pay_success_123',
                'razorpay_signature': 'sig_valid'
            },
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['status'], 'success')

        # Check records
        payment.refresh_from_db()
        booking.refresh_from_db()
        self.assertEqual(payment.payment_status, Payment.PaymentStatus.SUCCESS)
        self.assertEqual(payment.razorpay_payment_id, 'pay_success_123')
        self.assertEqual(payment.payment_method, 'upi')
        self.assertIsNotNone(payment.paid_at)

        self.assertEqual(booking.payment_status, CarBooking.PaymentStatus.PAID)
        self.assertEqual(booking.booking_status, CarBooking.BookingStatus.CONFIRMED)

        # Check stock deducted by exactly 1
        self.car.refresh_from_db()
        self.assertEqual(self.car.stock_quantity, initial_stock - 1)
        self.assertTrue(self.car.is_available)

        # Check notification delivered
        notif = CustomerNotification.objects.filter(user=self.customer, booking_reference=booking.booking_id).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.notification_type, CustomerNotification.NotificationType.GENERAL)

    # ==============================================================================
    # 9. Stock Reaches Zero: Auto-disables Availability
    # ==============================================================================
    @patch('apps.payments.services.get_razorpay_client')
    def test_stock_depletion_auto_disables_availability(self, mock_get_client):
        """When the last unit is booked (stock 1 -> 0), is_available is set to False."""
        mock_client = MagicMock()
        mock_client.utility.verify_payment_signature.return_value = True
        mock_client.payment.fetch.return_value = {
            'id': 'pay_last_unit',
            'order_id': 'order_last_unit',
            'amount': 3000000,
            'currency': 'INR',
            'status': 'captured',
            'method': 'card'
        }
        mock_get_client.return_value = mock_client

        self.car.stock_quantity = 1
        self.car.is_available = True
        self.car.save()

        booking = CarBooking.objects.create(customer=self.customer, car=self.car, booking_amount=Decimal('30000.00'))
        Payment.objects.create(booking=booking, razorpay_order_id='order_last_unit', amount=Decimal('30000.00'))

        self.client.force_login(self.customer)
        response = self.client.post(
            self.verify_payment_url,
            data={
                'razorpay_order_id': 'order_last_unit',
                'razorpay_payment_id': 'pay_last_unit',
                'razorpay_signature': 'sig_valid'
            },
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        self.car.refresh_from_db()
        self.assertEqual(self.car.stock_quantity, 0)
        self.assertFalse(self.car.is_available)

    # ==============================================================================
    # 10. Duplicate Verification Idempotency
    # ==============================================================================
    @patch('apps.payments.services.get_razorpay_client')
    def test_duplicate_verification_without_repeated_deduction(self, mock_get_client):
        """Duplicate callbacks for already SUCCESS payment do not deduct stock again."""
        mock_client = MagicMock()
        mock_client.utility.verify_payment_signature.return_value = True
        mock_client.payment.fetch.return_value = {
            'id': 'pay_dup',
            'order_id': 'order_dup',
            'amount': 3000000,
            'currency': 'INR',
            'status': 'captured'
        }
        mock_get_client.return_value = mock_client

        booking = CarBooking.objects.create(customer=self.customer, car=self.car, booking_amount=Decimal('30000.00'))
        Payment.objects.create(booking=booking, razorpay_order_id='order_dup', amount=Decimal('30000.00'))

        self.client.force_login(self.customer)

        # Call 1: Success
        res1 = self.client.post(
            self.verify_payment_url,
            data={'razorpay_order_id': 'order_dup', 'razorpay_payment_id': 'pay_dup', 'razorpay_signature': 'sig'},
            content_type='application/json'
        )
        self.assertEqual(res1.json()['status'], 'success')
        self.car.refresh_from_db()
        stock_after_first = self.car.stock_quantity  # 2

        # Call 2: Duplicate
        res2 = self.client.post(
            self.verify_payment_url,
            data={'razorpay_order_id': 'order_dup', 'razorpay_payment_id': 'pay_dup', 'razorpay_signature': 'sig'},
            content_type='application/json'
        )
        self.assertEqual(res2.json()['status'], 'already_processed')

        # Stock remains identical (no second deduction)
        self.car.refresh_from_db()
        self.assertEqual(self.car.stock_quantity, stock_after_first)

    # ==============================================================================
    # 11. Out-of-Stock Race Condition Handling
    # ==============================================================================
    @patch('apps.payments.services.get_razorpay_client')
    def test_stock_becoming_unavailable_during_checkout(self, mock_get_client):
        """
        Payment was captured by Razorpay, but vehicle stock reached 0 in the interim.
        - Payment marked SUCCESS
        - CarBooking marked PAID, but booking_status remains PENDING
        - Stock is NOT deducted (does not become negative)
        - Manager & customer notifications created
        - Status 'out_of_stock' returned
        """
        mock_client = MagicMock()
        mock_client.utility.verify_payment_signature.return_value = True
        mock_client.payment.fetch.return_value = {
            'id': 'pay_race_123',
            'order_id': 'order_race_123',
            'amount': 3000000,
            'currency': 'INR',
            'status': 'captured'
        }
        mock_get_client.return_value = mock_client

        # Simulate vehicle running out of stock after order creation
        self.car.stock_quantity = 0
        self.car.is_available = False
        self.car.save()

        booking = CarBooking.objects.create(customer=self.customer, car=self.car, booking_amount=Decimal('30000.00'))
        payment = Payment.objects.create(booking=booking, razorpay_order_id='order_race_123', amount=Decimal('30000.00'))

        self.client.force_login(self.customer)
        response = self.client.post(
            self.verify_payment_url,
            data={'razorpay_order_id': 'order_race_123', 'razorpay_payment_id': 'pay_race_123', 'razorpay_signature': 'sig'},
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'out_of_stock')

        # Check records
        payment.refresh_from_db()
        booking.refresh_from_db()
        self.assertEqual(payment.payment_status, Payment.PaymentStatus.SUCCESS)
        self.assertEqual(booking.payment_status, CarBooking.PaymentStatus.PAID)
        self.assertEqual(booking.booking_status, CarBooking.BookingStatus.PENDING)  # Held

        # Stock never becomes negative
        self.car.refresh_from_db()
        self.assertEqual(self.car.stock_quantity, 0)

        # Check manager alert notification
        mgr_notif = CustomerNotification.objects.filter(user=self.manager, booking_reference=booking.booking_id).first()
        self.assertIsNotNone(mgr_notif)
        self.assertIn('ACTION REQUIRED', mgr_notif.title)

    # ==============================================================================
    # 12. Customer Ownership Enforcement
    # ==============================================================================
    def test_customer_ownership_validation(self):
        """Customer B cannot verify payment for Customer A's order."""
        booking = CarBooking.objects.create(customer=self.customer, car=self.car, booking_amount=Decimal('30000.00'))
        Payment.objects.create(booking=booking, razorpay_order_id='order_cust_a', amount=Decimal('30000.00'))

        # Log in as other_customer
        self.client.force_login(self.other_customer)
        response = self.client.post(
            self.verify_payment_url,
            data={'razorpay_order_id': 'order_cust_a', 'razorpay_payment_id': 'pay_1', 'razorpay_signature': 'sig'},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn('permission', response.json().get('error', '').lower())

    # ==============================================================================
    # 13. Database Transaction Rollback on Error
    # ==============================================================================
    @patch('apps.payments.services.Car.objects.filter')
    @patch('apps.payments.services.get_razorpay_client')
    def test_database_transaction_rollback_on_unexpected_error(self, mock_get_client, mock_car_filter):
        """Database changes are completely rolled back if an error occurs inside transaction.atomic()."""
        mock_client = MagicMock()
        mock_client.utility.verify_payment_signature.return_value = True
        mock_client.payment.fetch.return_value = {
            'id': 'pay_err',
            'order_id': 'order_err',
            'amount': 3000000,
            'currency': 'INR',
            'status': 'captured'
        }
        mock_get_client.return_value = mock_client

        # Force database error during stock update
        mock_car_filter.side_effect = DatabaseError("Simulated database lock failure")

        booking = CarBooking.objects.create(customer=self.customer, car=self.car, booking_amount=Decimal('30000.00'))
        payment = Payment.objects.create(booking=booking, razorpay_order_id='order_err', amount=Decimal('30000.00'))

        with self.assertRaises(DatabaseError):
            verify_and_process_car_booking_payment(
                customer=self.customer,
                razorpay_order_id='order_err',
                razorpay_payment_id='pay_err',
                razorpay_signature='sig'
            )

        # Confirm rollback: payment and booking remain PENDING
        payment.refresh_from_db()
        booking.refresh_from_db()
        self.assertEqual(payment.payment_status, Payment.PaymentStatus.PENDING)
        self.assertEqual(booking.payment_status, CarBooking.PaymentStatus.PENDING)
        self.assertEqual(booking.booking_status, CarBooking.BookingStatus.PENDING)

    # ==============================================================================
    # 14. Phase 2: Booking Confirmation Receipt View & Ownership Protection
    # ==============================================================================
    def test_booking_success_receipt_view_authorized(self):
        """Customer can access their own booking confirmation receipt."""
        booking = CarBooking.objects.create(
            customer=self.customer,
            car=self.car,
            booking_amount=Decimal('30000.00'),
            payment_status=CarBooking.PaymentStatus.PAID,
            booking_status=CarBooking.BookingStatus.CONFIRMED
        )
        Payment.objects.create(
            booking=booking,
            razorpay_order_id='order_receipt_test',
            razorpay_payment_id='pay_receipt_test',
            amount=Decimal('30000.00'),
            payment_status=Payment.PaymentStatus.SUCCESS
        )

        receipt_url = reverse('payments:booking_success', kwargs={'booking_id': booking.booking_id})
        self.client.force_login(self.customer)
        response = self.client.get(receipt_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, booking.booking_id)
        self.assertContains(response, 'Vehicle Advance Reservation Confirmed!')
        self.assertContains(response, 'pay_receipt_test')
        self.assertContains(response, '30,000.00')

    def test_booking_success_receipt_view_ownership_protection(self):
        """Other customer cannot view another customer's booking receipt."""
        booking = CarBooking.objects.create(
            customer=self.customer,
            car=self.car,
            booking_amount=Decimal('30000.00'),
            payment_status=CarBooking.PaymentStatus.PAID,
            booking_status=CarBooking.BookingStatus.CONFIRMED
        )
        Payment.objects.create(
            booking=booking,
            razorpay_order_id='order_receipt_priv',
            razorpay_payment_id='pay_receipt_priv',
            amount=Decimal('30000.00'),
            payment_status=Payment.PaymentStatus.SUCCESS
        )

        receipt_url = reverse('payments:booking_success', kwargs={'booking_id': booking.booking_id})
        self.client.force_login(self.other_customer)
        response = self.client.get(receipt_url)
        # Unauthorized access is rejected with 403 Forbidden
        self.assertEqual(response.status_code, 403)

    def test_booking_success_receipt_out_of_stock_message(self):
        """Receipt shows allocation in progress message when stock was unavailable."""
        booking = CarBooking.objects.create(
            customer=self.customer,
            car=self.car,
            booking_amount=Decimal('30000.00'),
            payment_status=CarBooking.PaymentStatus.PAID,
            booking_status=CarBooking.BookingStatus.PENDING  # Held
        )
        Payment.objects.create(
            booking=booking,
            razorpay_order_id='order_receipt_pending_alloc',
            razorpay_payment_id='pay_receipt_pending_alloc',
            amount=Decimal('30000.00'),
            payment_status=Payment.PaymentStatus.SUCCESS
        )

        receipt_url = reverse('payments:booking_success', kwargs={'booking_id': booking.booking_id})
        self.client.force_login(self.customer)
        response = self.client.get(receipt_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Payment received. Your vehicle allocation is being reviewed by our showroom team.')
        self.assertNotContains(response, 'Vehicle Advance Reservation Confirmed!')

    # ==============================================================================
    # 15. Phase 2: Customer Dashboard Integration (Car Bookings + Test Drives)
    # ==============================================================================
    def test_customer_dashboard_renders_car_bookings_and_test_drives(self):
        """Dashboard renders both Vehicle Advance Bookings and Test Drive Appointments."""
        from apps.bookings.models import TestDriveBooking

        # Create 1 CarBooking
        car_booking = CarBooking.objects.create(
            customer=self.customer,
            car=self.car,
            booking_amount=Decimal('30000.00'),
            payment_status=CarBooking.PaymentStatus.PAID,
            booking_status=CarBooking.BookingStatus.CONFIRMED
        )
        Payment.objects.create(
            booking=car_booking,
            razorpay_order_id='order_dash_test',
            razorpay_payment_id='pay_dash_test',
            amount=Decimal('30000.00'),
            payment_status=Payment.PaymentStatus.SUCCESS
        )

        # Create 1 TestDriveBooking
        td_booking = TestDriveBooking.objects.create(
            customer=self.customer,
            car=self.car,
            preferred_date='2026-11-15',
            status=TestDriveBooking.Status.PENDING
        )

        # 1. Vehicle Reservations Page contains ONLY CarBooking records
        veh_res_url = reverse('dashboard:vehicle_reservations')
        self.client.force_login(self.customer)
        response_veh = self.client.get(veh_res_url)

        self.assertEqual(response_veh.status_code, 200)
        self.assertContains(response_veh, car_booking.booking_id)
        self.assertNotContains(response_veh, td_booking.booking_number)
        self.assertContains(response_veh, 'My Vehicle Reservations')
        self.assertContains(response_veh, 'View Receipt')
        self.assertNotContains(response_veh, 'Test Drive Confirmed!')

        # 2. Test Drive Appointments Page contains ONLY TestDriveBooking records
        td_app_url = reverse('dashboard:test_drive_appointments')
        response_td = self.client.get(td_app_url)

        self.assertEqual(response_td.status_code, 200)
        self.assertContains(response_td, td_booking.booking_number)
        self.assertNotContains(response_td, car_booking.booking_id)
        self.assertContains(response_td, 'My Test Drive Appointments')

        # 3. Vehicle Booking Receipt never displays Test Drive confirmation modal
        receipt_url = reverse('payments:booking_success', kwargs={'booking_id': car_booking.booking_id})
        response_receipt = self.client.get(receipt_url)
        self.assertEqual(response_receipt.status_code, 200)
        self.assertContains(response_receipt, 'Vehicle Advance Reservation Confirmed!')
        self.assertNotContains(response_receipt, 'Test Drive Confirmed!')

    # ==============================================================================
    # 16. Phase 2: Car Detail Page UI Buttons (Guest, Customer, Manager, Out-of-Stock)
    # ==============================================================================
    def test_car_detail_page_guest_behaviour(self):
        """Guest sees login link for booking with ?next= query param."""
        detail_url = reverse('cars:car_detail', kwargs={'slug': self.car.slug})
        response = self.client.get(detail_url)

        self.assertEqual(response.status_code, 200)
        login_url = reverse('accounts:login')
        self.assertContains(response, f'{login_url}?next={detail_url}')
        self.assertContains(response, 'Book Vehicle Online')
        self.assertContains(response, 'Schedule Test Drive')

    def test_car_detail_page_authenticated_customer_behaviour(self):
        """Authenticated customer sees active Book Vehicle Online button."""
        detail_url = reverse('cars:car_detail', kwargs={'slug': self.car.slug})
        self.client.force_login(self.customer)
        response = self.client.get(detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="btnBookCarNow"')
        self.assertContains(response, 'checkout.razorpay.com/v1/checkout.js')

    def test_car_detail_page_manager_behaviour(self):
        """Showroom manager sees disabled button indicating customer booking is disabled."""
        detail_url = reverse('cars:car_detail', kwargs={'slug': self.car.slug})
        self.client.force_login(self.manager)
        response = self.client.get(detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Staff/Manager Mode')

    def test_car_detail_page_out_of_stock_behaviour(self):
        """Out of stock car shows disabled button with Out of Stock message."""
        self.car.stock_quantity = 0
        self.car.is_available = False
        self.car.save()

        detail_url = reverse('cars:car_detail', kwargs={'slug': self.car.slug})
        self.client.force_login(self.customer)
        response = self.client.get(detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Currently Out of Stock')
        self.assertNotContains(response, 'id="btnBookCarNow"')

