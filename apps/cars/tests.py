from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from apps.cars.models import Brand, Car, CarImage


class CarDiscoveryAndFilterTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Create test brands
        self.brand_bmw = Brand.objects.create(name='BMW', slug='bmw')
        self.brand_tata = Brand.objects.create(name='Tata Motors', slug='tata')
        self.brand_merc = Brand.objects.create(name='Mercedes-Benz', slug='mercedes-benz')
        self.brand_hyundai = Brand.objects.create(name='Hyundai', slug='hyundai')

        # Create test cars across budget, fuel, and body types
        # 1. Budget under 15 Lakh: Petrol Hatchback
        self.car_budget = Car.objects.create(
            title='i20 Asta',
            slug='hyundai-i20-asta',
            brand=self.brand_hyundai,
            body_type=Car.BodyType.HATCHBACK,
            price=Decimal('1150000.00'),
            booking_amount=Decimal('25000.00'),
            fuel_type=Car.FuelType.PETROL,
            transmission=Car.Transmission.MANUAL,
            engine_capacity='1197 cc',
            seating_capacity=5,
            mileage='20.0 kmpl',
            color_options='Polar White, Fiery Red',
            stock_quantity=3,
            is_available=True,
            is_featured=False,
            description='Affordable premium hatchback with smart connectivity.'
        )

        # 2. Budget 15L-35L: Electric SUV (Featured)
        self.car_ev = Car.objects.create(
            title='Nexon EV Empowered',
            slug='tata-nexon-ev-empowered',
            brand=self.brand_tata,
            body_type=Car.BodyType.SUV,
            price=Decimal('1950000.00'),
            booking_amount=Decimal('21000.00'),
            fuel_type=Car.FuelType.ELECTRIC,
            transmission=Car.Transmission.AUTOMATIC,
            engine_capacity='Long Range 40.5 kWh',
            seating_capacity=5,
            mileage='465 km',
            color_options='Empowered Oxide, Pristine White',
            stock_quantity=2,
            is_available=True,
            is_featured=True,
            description='India best selling electric SUV.'
        )

        # 3. Budget 15L-35L: Diesel SUV
        self.car_diesel = Car.objects.create(
            title='Harrier XZA+',
            slug='tata-harrier-xza-plus',
            brand=self.brand_tata,
            body_type=Car.BodyType.SUV,
            price=Decimal('2450000.00'),
            booking_amount=Decimal('30000.00'),
            fuel_type=Car.FuelType.DIESEL,
            transmission=Car.Transmission.AUTOMATIC,
            engine_capacity='1956 cc Kryotec Diesel',
            seating_capacity=5,
            mileage='16.8 kmpl',
            color_options='Sunlit Yellow, Ash Grey',
            stock_quantity=1,
            is_available=True,
            is_featured=False,
            description='Commanding road presence diesel SUV.'
        )

        # 4. Budget 35L-75L: Petrol Sedan (Featured)
        self.car_luxury = Car.objects.create(
            title='C-Class C 300',
            slug='mercedes-benz-c-class-c300',
            brand=self.brand_merc,
            body_type=Car.BodyType.SEDAN,
            price=Decimal('6500000.00'),
            booking_amount=Decimal('50000.00'),
            fuel_type=Car.FuelType.PETROL,
            transmission=Car.Transmission.AUTOMATIC,
            engine_capacity='1999 cc Turbo',
            seating_capacity=5,
            mileage='16.9 kmpl',
            color_options='Obsidian Black, Polar White',
            stock_quantity=2,
            is_available=True,
            is_featured=True,
            description='Executive luxury sports sedan.'
        )

        # 5. Budget Above 75L: Luxury Sports Sedan
        self.car_super_luxury = Car.objects.create(
            title='M340i xDrive',
            slug='bmw-m340i-xdrive',
            brand=self.brand_bmw,
            body_type=Car.BodyType.SEDAN,
            price=Decimal('7800000.00'),
            booking_amount=Decimal('100000.00'),
            fuel_type=Car.FuelType.PETROL,
            transmission=Car.Transmission.AUTOMATIC,
            engine_capacity='2998 cc 6-Cylinder',
            seating_capacity=5,
            mileage='13.0 kmpl',
            color_options='Dravit Grey, Tanzanite Blue',
            stock_quantity=1,
            is_available=True,
            is_featured=False,
            description='Pure performance sports sedan.'
        )

        # Add image to luxury car
        CarImage.objects.create(car=self.car_luxury, is_primary=True, image='cars/Mercedes.avif')

    def test_homepage_loads_and_has_brand_search(self):
        """Homepage loads with 200 OK and contains dynamic brand options and featured cars."""
        response = self.client.get(reverse('cars:home'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'pages/home.html')
        self.assertContains(response, 'C-Class C 300')
        self.assertContains(response, 'Nexon EV Empowered')
        self.assertContains(response, 'Tata Motors')

        # Check search form parameters
        self.assertContains(response, 'name="brand"')
        self.assertContains(response, 'name="budget"')
        self.assertContains(response, 'name="fuel"')

    def test_car_listing_page_loads_all_available_cars(self):
        """Car listing view returns 200 OK and lists all 5 active cars with correct count."""
        response = self.client.get(reverse('cars:car_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'pages/car_list.html')
        self.assertEqual(len(response.context['cars']), 5)
        self.assertContains(response, '5 Cars Available')
        self.assertContains(response, 'i20 Asta')
        self.assertContains(response, 'Nexon EV Empowered')
        self.assertContains(response, 'Harrier XZA+')
        self.assertContains(response, 'C-Class C 300')
        self.assertContains(response, 'M340i xDrive')

    def test_filter_by_brand_slug(self):
        """Filtering by brand slug returns only cars of that manufacturer."""
        response = self.client.get(reverse('cars:car_list'), {'brand': 'tata'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['cars']), 2)
        self.assertContains(response, 'Nexon EV Empowered')
        self.assertContains(response, 'Harrier XZA+')
        self.assertNotContains(response, 'i20 Asta')
        self.assertNotContains(response, 'C-Class C 300')
        self.assertNotContains(response, 'M340i xDrive')

    def test_filter_by_brand_prefix(self):
        """Filtering with 'mercedes' prefix matches 'mercedes-benz'."""
        response = self.client.get(reverse('cars:car_list'), {'brand': 'mercedes'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['cars']), 1)
        self.assertContains(response, 'C-Class C 300')
        self.assertNotContains(response, 'M340i xDrive')

    def test_filter_by_budget_presets(self):
        """Filtering by budget ranges returns correctly priced cars."""
        # Under 15 Lakh
        res_under_15 = self.client.get(reverse('cars:car_list'), {'budget': 'under-15l'})
        self.assertEqual(len(res_under_15.context['cars']), 1)
        self.assertEqual(res_under_15.context['cars'][0].title, 'i20 Asta')

        # 15L - 35L
        res_15_35 = self.client.get(reverse('cars:car_list'), {'budget': '15l-35l'})
        self.assertEqual(len(res_15_35.context['cars']), 2)
        titles_15_35 = [c.title for c in res_15_35.context['cars']]
        self.assertIn('Nexon EV Empowered', titles_15_35)
        self.assertIn('Harrier XZA+', titles_15_35)

        # 35L - 75L
        res_35_75 = self.client.get(reverse('cars:car_list'), {'budget': '35l-75l'})
        self.assertEqual(len(res_35_75.context['cars']), 1)
        self.assertEqual(res_35_75.context['cars'][0].title, 'C-Class C 300')

        # Above 75L
        res_above_75 = self.client.get(reverse('cars:car_list'), {'budget': 'above-75l'})
        self.assertEqual(len(res_above_75.context['cars']), 1)
        self.assertEqual(res_above_75.context['cars'][0].title, 'M340i xDrive')

    def test_filter_by_fuel_type(self):
        """Filtering by fuel type correctly filters petrol, diesel, and electric cars."""
        # Electric
        res_ev = self.client.get(reverse('cars:car_list'), {'fuel': 'electric'})
        self.assertEqual(len(res_ev.context['cars']), 1)
        self.assertEqual(res_ev.context['cars'][0].title, 'Nexon EV Empowered')

        # Diesel
        res_diesel = self.client.get(reverse('cars:car_list'), {'fuel': 'diesel'})
        self.assertEqual(len(res_diesel.context['cars']), 1)
        self.assertEqual(res_diesel.context['cars'][0].title, 'Harrier XZA+')

        # Petrol
        res_petrol = self.client.get(reverse('cars:car_list'), {'fuel': 'petrol'})
        self.assertEqual(len(res_petrol.context['cars']), 3)

    def test_multi_filter_combination(self):
        """Combining brand, budget, and fuel filters works accurately."""
        # Tata + Electric -> Nexon EV
        response = self.client.get(reverse('cars:car_list'), {
            'brand': 'tata',
            'fuel': 'electric',
            'budget': '15l-35l'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['cars']), 1)
        self.assertEqual(response.context['cars'][0].title, 'Nexon EV Empowered')

        # Tata + Petrol -> 0 cars
        res_empty = self.client.get(reverse('cars:car_list'), {
            'brand': 'tata',
            'fuel': 'petrol'
        })
        self.assertEqual(res_empty.status_code, 200)
        self.assertEqual(len(res_empty.context['cars']), 0)
        self.assertContains(res_empty, 'No Matching Cars Found')

    def test_safe_handling_of_invalid_query_parameters(self):
        """Passing invalid filter values does not crash the server and returns safely."""
        response = self.client.get(reverse('cars:car_list'), {
            'brand': 'non_existent_brand_xyz',
            'budget': 'invalid-budget-string',
            'fuel': 'nuclear_fuel_type',
            'min_price': 'not_a_number'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['cars']), 0)
        self.assertContains(response, 'No Matching Cars Found')

    def test_car_detail_page_valid_slug(self):
        """Detail page returns 200 OK, uses car_detail.html, and displays car specifications."""
        url = reverse('cars:car_detail', kwargs={'slug': 'mercedes-benz-c-class-c300'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'pages/car_detail.html')
        self.assertContains(response, 'Mercedes-Benz C-Class C 300')
        self.assertContains(response, '65,00,000.00')
        self.assertContains(response, '50,000.00')  # advance booking deposit
        self.assertContains(response, '1999 cc Turbo')
        self.assertContains(response, '16.9 kmpl')
        self.assertContains(response, '5 Persons')
        self.assertContains(response, 'Executive luxury sports sedan.')

    def test_car_detail_page_unknown_slug_returns_404(self):
        """Requesting an unknown car slug returns HTTP 404 Not Found."""
        url = reverse('cars:car_detail', kwargs={'slug': 'unknown-phantom-car-slug'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_view_details_links_point_to_car_detail_view(self):
        """'View Details' buttons on homepage and car list point to car_detail URLs, not in-page anchors."""
        # Homepage test
        home_res = self.client.get(reverse('cars:home'))
        expected_detail_url = reverse('cars:car_detail', kwargs={'slug': self.car_luxury.slug})
        self.assertContains(home_res, f'href="{expected_detail_url}"')

        # Car Listing test
        list_res = self.client.get(reverse('cars:car_list'))
        for car in [self.car_budget, self.car_ev, self.car_luxury]:
            detail_url = reverse('cars:car_detail', kwargs={'slug': car.slug})
            self.assertContains(list_res, f'href="{detail_url}"')

        # Verify no broken anchor-only buttons exist for detail links
        self.assertNotContains(list_res, 'href="#details-')

    def test_shop_by_brand_navigation_links(self):
        """Brand cards on homepage link to car listing page with brand query parameter."""
        response = self.client.get(reverse('cars:home'))
        self.assertContains(response, reverse('cars:car_list') + '?brand=tata')
        self.assertContains(response, reverse('cars:car_list') + '?brand=bmw')
        self.assertContains(response, reverse('cars:car_list') + '?brand=hyundai')
        self.assertContains(response, reverse('cars:car_list') + '?brand=mercedes-benz')

    def test_rest_api_endpoints_preserved(self):
        """Preserve existing REST API list and detail endpoints."""
        list_api_res = self.client.get(reverse('cars:api_car_list'))
        self.assertEqual(list_api_res.status_code, 200)

        detail_api_res = self.client.get(reverse('cars:api_car_detail', kwargs={'slug': self.car_luxury.slug}))
        self.assertEqual(detail_api_res.status_code, 200)
        self.assertEqual(detail_api_res.json()['title'], 'C-Class C 300')


class IndianCurrencyFormattingTests(TestCase):
    """Test suite for Indian currency formatting template filter and display."""

    def test_filter_exact_spec_values(self):
        """Verify the Indian numbering system formatting for standard specification amounts."""
        from apps.cars.templatetags.currency_tags import indian_currency

        self.assertEqual(indian_currency(1850000.00), '18,50,000.00')
        self.assertEqual(indian_currency(25000.00), '25,000.00')
        self.assertEqual(indian_currency(1500000.00), '15,00,000.00')
        self.assertEqual(indian_currency(950000.00), '9,50,000.00')
        self.assertEqual(indian_currency(75000.00), '75,000.00')

    def test_filter_large_and_small_values(self):
        """Verify formatting for large amounts (crores) and small amounts (under 1000)."""
        from apps.cars.templatetags.currency_tags import indian_currency

        self.assertEqual(indian_currency(12345678.00), '1,23,45,678.00')
        self.assertEqual(indian_currency(Decimal('12345678.00')), '1,23,45,678.00')
        self.assertEqual(indian_currency(999.00), '999.00')
        self.assertEqual(indian_currency(999), '999.00')
        self.assertEqual(indian_currency(50.00), '50.00')
        self.assertEqual(indian_currency(0), '0.00')
        self.assertEqual(indian_currency(Decimal('0.00')), '0.00')

    def test_filter_safe_handling_of_edge_cases(self):
        """Verify handling of None, empty strings, invalid inputs, negative numbers, and strings."""
        from apps.cars.templatetags.currency_tags import indian_currency

        self.assertEqual(indian_currency(None), '')
        self.assertEqual(indian_currency(''), '')
        self.assertEqual(indian_currency('   '), '')
        self.assertEqual(indian_currency('invalid_number'), 'invalid_number')
        self.assertEqual(indian_currency(-25000.00), '-25,000.00')
        self.assertEqual(indian_currency('1850000'), '18,50,000.00')
        self.assertEqual(indian_currency('₹1850000.00'), '18,50,000.00')
        self.assertEqual(indian_currency('1,850,000.00'), '18,50,000.00')

    def test_template_tag_library_loading_and_aliases(self):
        """Verify template tags can be loaded in templates with all aliases."""
        from django.template import Template, Context

        # Test currency_tags with indian_currency
        t1 = Template('{% load currency_tags %}₹{{ amount|indian_currency }}')
        self.assertEqual(t1.render(Context({'amount': Decimal('1850000.00')})), '₹18,50,000.00')

        # Test currency_tags with intcomma_indian alias
        t2 = Template('{% load currency_tags %}₹{{ amount|intcomma_indian }}')
        self.assertEqual(t2.render(Context({'amount': Decimal('25000.00')})), '₹25,000.00')

        # Test car_tags alias library
        t3 = Template('{% load car_tags %}₹{{ amount|indian_currency }}')
        self.assertEqual(t3.render(Context({'amount': Decimal('12345678.00')})), '₹1,23,45,678.00')


class CompareCarsFeatureTests(TestCase):
    """Test suite for the Compare Cars feature and related APIs."""

    def setUp(self):
        self.client = Client()
        self.brand_tata = Brand.objects.create(name='Tata Motors', slug='tata')
        self.brand_hyundai = Brand.objects.create(name='Hyundai', slug='hyundai')
        self.brand_bmw = Brand.objects.create(name='BMW', slug='bmw')

        self.car_creta = Car.objects.create(
            title='Creta SX',
            slug='hyundai-creta-sx',
            brand=self.brand_hyundai,
            body_type=Car.BodyType.SUV,
            price=Decimal('1850000.00'),
            booking_amount=Decimal('25000.00'),
            fuel_type=Car.FuelType.PETROL,
            transmission=Car.Transmission.AUTOMATIC,
            engine_capacity='1497 cc',
            seating_capacity=5,
            mileage='17.4 kmpl',
            power='113.4 bhp @ 6,300 rpm',
            torque='143.8 Nm @ 4,500 rpm',
            length=4330,
            width=1790,
            height=1635,
            wheelbase=2610,
            ground_clearance=190,
            boot_space=433,
            touchscreen_size=Decimal('10.25'),
            usb_port_count=3,
            usb_details='1 Front USB-A, 1 Front USB-C, 1 Rear USB',
            color_options='Polar White, Titan Grey',
            stock_quantity=8,
            is_available=True,
            is_featured=True,
            description='Popular mid-size SUV.'
        )

        self.car_nexon = Car.objects.create(
            title='Nexon EV Empowered+',
            slug='tata-nexon-ev-empowered-plus',
            brand=self.brand_tata,
            body_type=Car.BodyType.SUV,
            price=Decimal('1950000.00'),
            booking_amount=Decimal('25000.00'),
            fuel_type=Car.FuelType.ELECTRIC,
            transmission=Car.Transmission.AUTOMATIC,
            engine_capacity='40.5 kWh',
            seating_capacity=5,
            mileage='465 km range',
            power='142.7 bhp (106.4 kW)',
            torque='215 Nm @ 0-3,100 rpm',
            length=3994,
            width=1811,
            height=1616,
            wheelbase=2498,
            ground_clearance=190,
            boot_space=350,
            airbag_count=6,
            touchscreen_size=Decimal('12.3'),
            speaker_count=9,
            usb_port_count=3,
            usb_details='1 Front USB-A (15W), 1 Front USB-C (45W), 1 Rear USB-C',
            color_options='Empowered Oxide',
            stock_quantity=4,
            is_available=True,
            is_featured=False,
            description='Leading electric SUV.'
        )

        self.car_bmw = Car.objects.create(
            title='3 Series 330i M Sport',
            slug='bmw-3-series-330i-m-sport',
            brand=self.brand_bmw,
            body_type=Car.BodyType.SEDAN,
            price=Decimal('6200000.00'),
            booking_amount=Decimal('50000.00'),
            fuel_type=Car.FuelType.PETROL,
            transmission=Car.Transmission.AUTOMATIC,
            engine_capacity='1998 cc Turbo',
            seating_capacity=5,
            mileage='15.0 kmpl',
            power='255 bhp @ 5,000 rpm',
            torque='400 Nm @ 1,550-4,400 rpm',
            length=4709,
            width=1827,
            height=1435,
            wheelbase=2851,
            ground_clearance=136,
            boot_space=480,
            airbag_count=6,
            touchscreen_size=Decimal('10.25'),
            speaker_count=10,
            usb_port_count=4,
            usb_details='1 Front USB-A, 1 Front USB-C, 2 Rear USB-C',
            color_options='Portimao Blue',
            stock_quantity=3,
            is_available=True,
            is_featured=False,
            description='Sports luxury sedan.'
        )

        # Set up test features and mappings to test tri-state availability
        from apps.cars.models import CarFeature, CarFeatureMap
        self.feat_abs, _ = CarFeature.objects.get_or_create(name='Anti-lock Braking System (ABS)', category=CarFeature.Category.SAFETY)
        self.feat_cam360, _ = CarFeature.objects.get_or_create(name='360-degree Camera', category=CarFeature.Category.SAFETY)
        self.feat_knee, _ = CarFeature.objects.get_or_create(name='Driver Knee Airbag', category=CarFeature.Category.SAFETY)

        # Creta: ABS=True, 360-cam=False, Knee Airbag=False
        CarFeatureMap.objects.create(car=self.car_creta, feature=self.feat_abs, is_available=True)
        CarFeatureMap.objects.create(car=self.car_creta, feature=self.feat_cam360, is_available=False)
        CarFeatureMap.objects.create(car=self.car_creta, feature=self.feat_knee, is_available=False)

        # Nexon: ABS=True, 360-cam=True, Knee Airbag=False
        CarFeatureMap.objects.create(car=self.car_nexon, feature=self.feat_abs, is_available=True)
        CarFeatureMap.objects.create(car=self.car_nexon, feature=self.feat_cam360, is_available=True)
        CarFeatureMap.objects.create(car=self.car_nexon, feature=self.feat_knee, is_available=False)

    def test_compare_page_loads_for_guest_users(self):
        """Compare page loads with 200 OK for unauthenticated guests."""
        response = self.client.get(reverse('cars:compare'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'pages/compare.html')
        self.assertContains(response, 'Compare Cars')
        self.assertContains(response, 'Choose Car 1')
        self.assertContains(response, 'Choose Car 2')
        self.assertContains(response, 'Choose Car 3')
        self.assertContains(response, 'Add Another Car')
        self.assertContains(response, 'Select Brand / Model')

    def test_compare_page_loads_for_authenticated_users(self):
        """Compare page loads with 200 OK for logged-in users."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user(username='tester', email='tester@example.com', password='password123')
        self.client.login(username='tester', password='password123')

        response = self.client.get(reverse('cars:compare'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'pages/compare.html')

    def test_compare_page_accepts_initial_cars_query_params(self):
        """Passing initial car IDs or slugs in query params populates initial context."""
        url = reverse('cars:compare') + f'?cars={self.car_creta.id},{self.car_nexon.slug}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['initial_cars']), 2)
        self.assertIn(self.car_creta.id, response.context['initial_car_ids'])
        self.assertIn(self.car_nexon.id, response.context['initial_car_ids'])

    def test_compare_page_accepts_single_car_slug_query_param(self):
        """Passing single ?car=slug query param correctly resolves the car into context."""
        url = reverse('cars:compare') + f'?car={self.car_bmw.slug}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['initial_cars']), 1)
        self.assertEqual(response.context['initial_cars'][0].id, self.car_bmw.id)
        self.assertIn(self.car_bmw.id, response.context['initial_car_ids'])

    def test_api_compare_search_all_and_filtered(self):
        """Search API returns all cars when empty and filters accurately on query."""
        # 1. Search all
        res_all = self.client.get(reverse('cars:api_compare_search'))
        self.assertEqual(res_all.status_code, 200)
        data_all = res_all.json()
        self.assertEqual(data_all['status'], 'success')
        self.assertEqual(data_all['count'], 3)

        # 2. Search by brand name
        res_tata = self.client.get(reverse('cars:api_compare_search'), {'q': 'tata'})
        self.assertEqual(res_tata.status_code, 200)
        data_tata = res_tata.json()
        self.assertEqual(data_tata['count'], 1)
        self.assertEqual(data_tata['cars'][0]['title'], 'Nexon EV Empowered+')
        self.assertEqual(data_tata['cars'][0]['formatted_price'], '₹19,50,000.00')

        # 3. Search by model title keyword
        res_creta = self.client.get(reverse('cars:api_compare_search'), {'q': 'Creta'})
        self.assertEqual(res_creta.status_code, 200)
        data_creta = res_creta.json()
        self.assertEqual(data_creta['count'], 1)
        self.assertEqual(data_creta['cars'][0]['title'], 'Creta SX')
        self.assertEqual(data_creta['cars'][0]['formatted_price'], '₹18,50,000.00')

        # 4. Search by exact slug
        res_slug = self.client.get(reverse('cars:api_compare_search'), {'q': self.car_bmw.slug})
        self.assertEqual(res_slug.status_code, 200)
        data_slug = res_slug.json()
        self.assertEqual(data_slug['count'], 1)
        self.assertEqual(data_slug['cars'][0]['title'], '3 Series 330i M Sport')

        # 5. Search non-matching returns 0
        res_none = self.client.get(reverse('cars:api_compare_search'), {'q': 'ferrari_phantom'})
        self.assertEqual(res_none.status_code, 200)
        self.assertEqual(res_none.json()['count'], 0)

    def test_api_compare_details_two_cars(self):
        """Details API returns complete 6-group specifications for 2 selected cars."""
        url = reverse('cars:api_compare_details') + f'?ids={self.car_creta.id},{self.car_nexon.id}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['cars']), 2)

        # Verify car summaries
        c1, c2 = data['cars'][0], data['cars'][1]
        self.assertEqual(c1['title'], 'Creta SX')
        self.assertEqual(c1['formatted_price'], '₹18,50,000.00')
        self.assertTrue(c1['is_lowest_price'])  # 18.5L < 19.5L
        self.assertEqual(c2['title'], 'Nexon EV Empowered+')
        self.assertEqual(c2['formatted_price'], '₹19,50,000.00')
        self.assertFalse(c2['is_lowest_price'])

        # Verify groups
        groups = {g['name']: g['fields'] for g in data['groups']}
        self.assertIn('1. Price & Overview', groups)
        self.assertIn('2. Engine & Performance', groups)
        self.assertIn('3. Fuel & Transmission', groups)
        self.assertIn('4. Dimensions & Capacity', groups)
        self.assertIn('5. Safety', groups)
        self.assertIn('6. Entertainment & Communication', groups)

        # Check Price difference detected
        price_field = [f for f in groups['1. Price & Overview'] if f['label'] == 'Ex-Showroom Price'][0]
        self.assertTrue(price_field['is_different'])
        self.assertEqual(price_field['values'], ['₹18,50,000.00', '₹19,50,000.00'])

    def test_api_compare_dimensions_and_capacity_values(self):
        """Verify dimensional specifications formatting and comparison."""
        url = reverse('cars:api_compare_details') + f'?ids={self.car_creta.id},{self.car_nexon.id}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        groups = {g['name']: {f['label']: f['values'] for f in g['fields']} for g in data['groups']}

        dims = groups['4. Dimensions & Capacity']
        self.assertEqual(dims['Length'], ['4330 mm', '3994 mm'])
        self.assertEqual(dims['Width'], ['1790 mm', '1811 mm'])
        self.assertEqual(dims['Height'], ['1635 mm', '1616 mm'])
        self.assertEqual(dims['Wheelbase'], ['2610 mm', '2498 mm'])
        self.assertEqual(dims['Ground Clearance'], ['190 mm', '190 mm'])
        self.assertEqual(dims['Boot Space'], ['433 Litres', '350 Litres'])
        self.assertEqual(dims['Seating Capacity'], ['5 Persons', '5 Persons'])

    def test_api_compare_tri_state_safety_and_entertainment(self):
        """Verify tri-state rendering ('Yes', 'No', '—') and entertainment specifications."""
        url = reverse('cars:api_compare_details') + f'?ids={self.car_creta.id},{self.car_nexon.id}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        groups = {g['name']: {f['label']: f['values'] for f in g['fields']} for g in data['groups']}

        # Safety tri-state
        safety = groups['5. Safety']
        # Airbag count: Creta SX is None -> '—', Nexon EV is 6 -> '6'
        self.assertEqual(safety['Number of Airbags'], ['—', '6'])
        # ABS: Both mapped True -> 'Yes'
        self.assertEqual(safety['Anti-lock Braking System (ABS)'], ['Yes', 'Yes'])
        # 360 Camera: Creta SX False -> 'No', Nexon EV True -> 'Yes'
        self.assertEqual(safety['360-degree Camera'], ['No', 'Yes'])
        # Knee airbag: Both False -> 'No'
        self.assertEqual(safety['Driver Knee Airbag'], ['No', 'No'])
        # Unmapped feature (Hill Assist): Both '—'
        self.assertEqual(safety['Hill Assist'], ['—', '—'])

        # Entertainment
        ent = groups['6. Entertainment & Communication']
        self.assertEqual(ent['Touchscreen Size'], ['10.25 inches', '12.3 inches'])
        # Speakers: Creta SX is None -> '—', Nexon EV is 9 -> '9 Speakers'
        self.assertEqual(ent['Number of Speakers'], ['—', '9 Speakers'])
        self.assertEqual(ent['USB Ports'], [
            '3 Ports (1 Front USB-A, 1 Front USB-C, 1 Rear USB)',
            '3 Ports (1 Front USB-A (15W), 1 Front USB-C (45W), 1 Rear USB-C)'
        ])

    def test_api_compare_ev_specifications(self):
        """Verify electric vehicle powertrain attributes are properly displayed."""
        url = reverse('cars:api_compare_details') + f'?ids={self.car_nexon.id},{self.car_creta.id}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        groups = {g['name']: {f['label']: f['values'] for f in g['fields']} for g in data['groups']}

        engine = groups['2. Engine & Performance']
        self.assertEqual(engine['Engine / Motor Specs'], ['40.5 kWh', '1497 cc'])
        self.assertEqual(engine['Maximum Power'], ['142.7 bhp (106.4 kW)', '113.4 bhp @ 6,300 rpm'])
        self.assertEqual(engine['Maximum Torque'], ['215 Nm @ 0-3,100 rpm', '143.8 Nm @ 4,500 rpm'])
        self.assertEqual(engine['Mileage / Driving Range'], ['465 km range', '17.4 kmpl'])

    def test_api_compare_details_three_cars(self):
        """Details API handles 3 selected cars accurately."""
        url = reverse('cars:api_compare_details') + f'?ids={self.car_creta.id},{self.car_nexon.id},{self.car_bmw.id}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['cars']), 3)

        # Check that values for each specification have 3 elements
        groups = data['groups']
        for g in groups:
            for f in g['fields']:
                self.assertEqual(len(f['values']), 3)

    def test_api_compare_details_safely_handles_invalid_and_duplicate_ids(self):
        """Details API safely handles duplicates, fewer than 2 cars, and non-existent IDs."""
        # 1. Fewer than 2 cars
        res_single = self.client.get(reverse('cars:api_compare_details') + f'?ids={self.car_creta.id}')
        self.assertEqual(res_single.status_code, 400)
        self.assertEqual(res_single.json()['status'], 'error')

        # 2. Duplicate of same car
        res_dup = self.client.get(reverse('cars:api_compare_details') + f'?ids={self.car_creta.id},{self.car_creta.id}')
        self.assertEqual(res_dup.status_code, 400)

        # 3. Non-existent ID
        res_invalid = self.client.get(reverse('cars:api_compare_details') + '?ids=99999,88888')
        self.assertEqual(res_invalid.status_code, 400)

    def test_navigation_integration(self):
        """Header, footer, and car cards link to compare page."""
        compare_url = reverse('cars:compare')

        # Check homepage navbar and footer
        res_home = self.client.get(reverse('cars:home'))
        self.assertContains(res_home, f'href="{compare_url}"')

        # Check car listing page navbar and footer
        res_list = self.client.get(reverse('cars:car_list'))
        self.assertContains(res_list, f'href="{compare_url}"')

        # Check detail page sidebar link
        res_detail = self.client.get(reverse('cars:car_detail', kwargs={'slug': self.car_creta.slug}))
        self.assertContains(res_detail, f'href="{compare_url}?car={self.car_creta.slug}"')


