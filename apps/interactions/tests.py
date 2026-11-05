from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from apps.cars.models import Brand, Car, CarImage
from apps.interactions.models import Wishlist

User = get_user_model()


class WishlistModelTests(TestCase):
    """
    Unit tests for Wishlist database model constraints, relationships, and deletion cascades.
    """
    def setUp(self):
        self.user = User.objects.create_user(
            username='wishlist_user',
            email='wishlist_user@example.com',
            password='TestPassword123!',
            user_type='CUSTOMER'
        )
        self.brand = Brand.objects.create(name='Toyota', slug='toyota')
        self.car = Car.objects.create(
            brand=self.brand,
            title='Glanza V MT',
            slug='toyota-glanza-v-mt',
            price=Decimal('999000.00'),
            booking_amount=Decimal('21000.00'),
            body_type=Car.BodyType.HATCHBACK,
            fuel_type=Car.FuelType.PETROL,
            transmission=Car.Transmission.MANUAL,
            is_available=True
        )

    def test_wishlist_creation_and_str(self):
        item = Wishlist.objects.create(user=self.user, car=self.car)
        self.assertEqual(str(item), f"{self.user.username} -> {self.car.title}")
        self.assertEqual(self.user.wishlist_items.count(), 1)
        self.assertEqual(self.car.wishlisted_by.count(), 1)

    def test_wishlist_unique_together_constraint(self):
        Wishlist.objects.create(user=self.user, car=self.car)
        with self.assertRaises(IntegrityError):
            Wishlist.objects.create(user=self.user, car=self.car)

    def test_cascade_delete_user(self):
        Wishlist.objects.create(user=self.user, car=self.car)
        self.user.delete()
        self.assertEqual(Wishlist.objects.count(), 0)

    def test_cascade_delete_car(self):
        Wishlist.objects.create(user=self.user, car=self.car)
        self.car.delete()
        self.assertEqual(Wishlist.objects.count(), 0)


class WishlistAPITests(TestCase):
    """
    Integration tests for Wishlist AJAX API endpoints.
    """
    def setUp(self):
        self.client = Client(SERVER_NAME='127.0.0.1')
        self.user = User.objects.create_user(
            username='buyer1',
            email='buyer1@example.com',
            password='SecurePassword123!',
            user_type='CUSTOMER'
        )
        self.brand = Brand.objects.create(name='Honda', slug='honda')
        self.car = Car.objects.create(
            brand=self.brand,
            title='City ZX CVT',
            slug='honda-city-zx-cvt',
            price=Decimal('1635000.00'),
            booking_amount=Decimal('25000.00'),
            body_type=Car.BodyType.SEDAN,
            fuel_type=Car.FuelType.PETROL,
            transmission=Car.Transmission.AUTOMATIC,
            is_available=True
        )
        self.toggle_url = reverse('interactions:api_toggle')
        self.status_url = reverse('interactions:api_status')

    def test_guest_toggle_rejected_with_401(self):
        response = self.client.post(self.toggle_url, {'car_id': self.car.id})
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertEqual(data['status'], 'unauthenticated')
        self.assertIn('/accounts/login/', data['login_url'])

    def test_guest_status_returns_empty(self):
        response = self.client.get(self.status_url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['car_ids'], [])

    def test_authenticated_add_to_wishlist(self):
        self.client.force_login(self.user)
        response = self.client.post(self.toggle_url, {'car_id': self.car.id})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['action'], 'added')
        self.assertTrue(data['is_wishlisted'])
        self.assertEqual(data['wishlist_count'], 1)
        self.assertTrue(Wishlist.objects.filter(user=self.user, car=self.car).exists())

    def test_authenticated_remove_via_toggle(self):
        Wishlist.objects.create(user=self.user, car=self.car)
        self.client.force_login(self.user)
        response = self.client.post(self.toggle_url, {'car_id': self.car.id})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['action'], 'removed')
        self.assertFalse(data['is_wishlisted'])
        self.assertEqual(data['wishlist_count'], 0)
        self.assertFalse(Wishlist.objects.filter(user=self.user, car=self.car).exists())

    def test_authenticated_remove_via_direct_endpoint(self):
        Wishlist.objects.create(user=self.user, car=self.car)
        self.client.force_login(self.user)
        remove_url = reverse('interactions:api_remove', kwargs={'car_id': self.car.id})
        response = self.client.post(remove_url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['action'], 'removed')
        self.assertEqual(data['wishlist_count'], 0)
        self.assertFalse(Wishlist.objects.filter(user=self.user, car=self.car).exists())

    def test_missing_car_id_returns_400(self):
        self.client.force_login(self.user)
        response = self.client.post(self.toggle_url, {})
        self.assertEqual(response.status_code, 400)

    def test_nonexistent_car_id_returns_404(self):
        self.client.force_login(self.user)
        response = self.client.post(self.toggle_url, {'car_id': 999999})
        self.assertEqual(response.status_code, 404)


class WishlistCustomerIsolationTests(TestCase):
    """
    Tests ensuring Customer A and Customer B wishlists are strictly isolated.
    """
    def setUp(self):
        self.client = Client(SERVER_NAME='127.0.0.1')
        self.user_a = User.objects.create_user(
            username='alice',
            email='alice@example.com',
            password='Password123!',
            user_type='CUSTOMER'
        )
        self.user_b = User.objects.create_user(
            username='bob',
            email='bob@example.com',
            password='Password123!',
            user_type='CUSTOMER'
        )
        self.brand = Brand.objects.create(name='BMW', slug='bmw')
        self.car1 = Car.objects.create(
            brand=self.brand,
            title='3 Series 330i M Sport',
            slug='bmw-3-series',
            price=Decimal('6200000.00'),
            booking_amount=Decimal('100000.00'),
            body_type=Car.BodyType.SEDAN,
            fuel_type=Car.FuelType.PETROL,
            transmission=Car.Transmission.AUTOMATIC,
            is_available=True
        )
        self.car2 = Car.objects.create(
            brand=self.brand,
            title='X1 sDrive18d M Sport',
            slug='bmw-x1',
            price=Decimal('5290000.00'),
            booking_amount=Decimal('50000.00'),
            body_type=Car.BodyType.SUV,
            fuel_type=Car.FuelType.DIESEL,
            transmission=Car.Transmission.AUTOMATIC,
            is_available=True
        )
        # Alice saves car1; Bob saves car2
        Wishlist.objects.create(user=self.user_a, car=self.car1)
        Wishlist.objects.create(user=self.user_b, car=self.car2)

    def test_customer_isolation_on_page(self):
        # Alice's page must only show car1
        self.client.force_login(self.user_a)
        res_a = self.client.get(reverse('interactions:wishlist'))
        self.assertEqual(res_a.status_code, 200)
        self.assertContains(res_a, '3 Series 330i M Sport')
        self.assertNotContains(res_a, 'X1 sDrive18d M Sport')

        # Bob's page must only show car2
        self.client.force_login(self.user_b)
        res_b = self.client.get(reverse('interactions:wishlist'))
        self.assertEqual(res_b.status_code, 200)
        self.assertContains(res_b, 'X1 sDrive18d M Sport')
        self.assertNotContains(res_b, '3 Series 330i M Sport')

    def test_customer_isolation_on_api(self):
        # Alice's API query returns only car1
        self.client.force_login(self.user_a)
        res_status_a = self.client.get(reverse('interactions:api_status'))
        data_a = res_status_a.json()
        self.assertEqual(data_a['count'], 1)
        self.assertEqual(data_a['car_ids'], [self.car1.id])

        # Alice cannot remove Bob's wishlist entry
        remove_bob_car = reverse('interactions:api_remove', kwargs={'car_id': self.car2.id})
        res_remove = self.client.post(remove_bob_car)
        self.assertEqual(res_remove.status_code, 200)
        # Bob's item remains intact!
        self.assertTrue(Wishlist.objects.filter(user=self.user_b, car=self.car2).exists())


class WishlistTemplateAndContextTests(TestCase):
    """
    Tests for template rendering, context processor, empty state, and navbar badges.
    """
    def setUp(self):
        self.client = Client(SERVER_NAME='127.0.0.1')
        self.user = User.objects.create_user(
            username='shopper',
            email='shopper@example.com',
            password='Password123!',
            user_type='CUSTOMER'
        )
        self.brand = Brand.objects.create(name='Tata Motors', slug='tata')
        self.car = Car.objects.create(
            brand=self.brand,
            title='Punch Creative Flagship MT',
            slug='tata-punch',
            price=Decimal('960000.00'),
            booking_amount=Decimal('21000.00'),
            body_type=Car.BodyType.SUV,
            fuel_type=Car.FuelType.PETROL,
            transmission=Car.Transmission.MANUAL,
            is_available=True
        )

    def test_guest_redirected_from_wishlist_page(self):
        response = self.client.get(reverse('interactions:wishlist'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/?next=/wishlist/', response.url)

    def test_empty_wishlist_view(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('interactions:wishlist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your Wishlist is Empty')
        self.assertContains(response, 'Browse Showroom')

    def test_populated_wishlist_view(self):
        Wishlist.objects.create(user=self.user, car=self.car)
        self.client.force_login(self.user)
        response = self.client.get(reverse('interactions:wishlist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Punch Creative Flagship MT')
        self.assertContains(response, '₹9,60,000.00')

    def test_context_processor_guest_vs_authenticated(self):
        # Guest context
        res_guest = self.client.get(reverse('cars:car_list'))
        self.assertEqual(res_guest.context['wishlist_count'], 0)
        self.assertEqual(res_guest.context['user_wishlist_car_ids'], set())

        # Authenticated context
        Wishlist.objects.create(user=self.user, car=self.car)
        self.client.force_login(self.user)
        res_user = self.client.get(reverse('cars:car_list'))
        self.assertEqual(res_user.context['wishlist_count'], 1)
        self.assertIn(self.car.id, res_user.context['user_wishlist_car_ids'])
