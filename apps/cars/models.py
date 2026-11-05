from django.db import models
from django.utils.text import slugify


class Brand(models.Model):
    """
    Automotive brand/manufacturer (e.g. BMW, Audi, Hyundai, Tata).
    """
    name = models.CharField(max_length=100, unique=True, verbose_name="Brand Name")
    slug = models.SlugField(max_length=120, unique=True, blank=True, verbose_name="Slug")
    logo = models.ImageField(upload_to='brands/', blank=True, null=True, verbose_name="Brand Logo")

    class Meta:
        verbose_name = "Brand"
        verbose_name_plural = "Brands"
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Car(models.Model):
    """
    New car model specification and inventory record.
    """
    class BodyType(models.TextChoices):
        SEDAN = 'SEDAN', 'Sedan'
        SUV = 'SUV', 'SUV'
        HATCHBACK = 'HATCHBACK', 'Hatchback'
        EV = 'EV', 'Electric Vehicle'
        LUXURY = 'LUXURY', 'Luxury'
        SPORTS = 'SPORTS', 'Sports'
        COUPE = 'COUPE', 'Coupe'
        CONVERTIBLE = 'CONVERTIBLE', 'Convertible'
        MPV = 'MPV', 'MPV'

    class FuelType(models.TextChoices):
        PETROL = 'PETROL', 'Petrol'
        DIESEL = 'DIESEL', 'Diesel'
        ELECTRIC = 'ELECTRIC', 'Electric'
        HYBRID = 'HYBRID', 'Hybrid'
        CNG = 'CNG', 'CNG'

    class Transmission(models.TextChoices):
        MANUAL = 'MANUAL', 'Manual'
        AUTOMATIC = 'AUTOMATIC', 'Automatic'

    title = models.CharField(max_length=200, verbose_name="Car Title")
    slug = models.SlugField(max_length=230, unique=True, blank=True, verbose_name="Slug")
    brand = models.ForeignKey(
        Brand,
        on_delete=models.CASCADE,
        related_name='cars',
        verbose_name="Brand"
    )
    body_type = models.CharField(
        max_length=20,
        choices=BodyType.choices,
        default=BodyType.SEDAN,
        verbose_name="Body Type"
    )
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Ex-Showroom Price (₹)")
    booking_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Advance Booking Fee (₹)")
    fuel_type = models.CharField(
        max_length=20,
        choices=FuelType.choices,
        default=FuelType.PETROL,
        verbose_name="Fuel Type"
    )
    transmission = models.CharField(
        max_length=20,
        choices=Transmission.choices,
        default=Transmission.AUTOMATIC,
        verbose_name="Transmission"
    )
    engine_capacity = models.CharField(max_length=50, verbose_name="Engine / Motor Specs")
    seating_capacity = models.PositiveIntegerField(default=5, verbose_name="Seating Capacity")
    mileage = models.CharField(max_length=50, verbose_name="Mileage / Range")
    color_options = models.CharField(max_length=255, verbose_name="Available Colors")
    stock_quantity = models.PositiveIntegerField(default=1, verbose_name="Stock Quantity")
    is_available = models.BooleanField(default=True, verbose_name="Available for Booking")
    is_featured = models.BooleanField(default=False, verbose_name="Featured on Homepage")
    description = models.TextField(blank=True, verbose_name="Description")

    # Technical & Performance Specifications (Structured)
    power = models.CharField(max_length=60, blank=True, verbose_name="Max Power")
    torque = models.CharField(max_length=60, blank=True, verbose_name="Max Torque")
    drivetrain = models.CharField(max_length=50, blank=True, default='', verbose_name="Drivetrain")
    model_year = models.CharField(max_length=50, blank=True, default='', verbose_name="Model Year / Version")

    # Dimensions & Capacity (mm / Litres)
    length = models.PositiveIntegerField(null=True, blank=True, verbose_name="Length (mm)")
    width = models.PositiveIntegerField(null=True, blank=True, verbose_name="Width (mm)")
    height = models.PositiveIntegerField(null=True, blank=True, verbose_name="Height (mm)")
    wheelbase = models.PositiveIntegerField(null=True, blank=True, verbose_name="Wheelbase (mm)")
    ground_clearance = models.PositiveIntegerField(null=True, blank=True, verbose_name="Ground Clearance (mm)")
    boot_space = models.PositiveIntegerField(null=True, blank=True, verbose_name="Boot Space (Litres)")

    # Key Count & Size Fields
    airbag_count = models.PositiveIntegerField(null=True, blank=True, verbose_name="Number of Airbags")
    touchscreen_size = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True, verbose_name="Touchscreen Size (Inches)")
    speaker_count = models.PositiveIntegerField(null=True, blank=True, verbose_name="Number of Speakers")
    usb_port_count = models.PositiveIntegerField(null=True, blank=True, verbose_name="USB Port Count")
    usb_details = models.CharField(max_length=150, blank=True, verbose_name="USB Port Details")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        verbose_name = "Car"
        verbose_name_plural = "Cars"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['brand', 'body_type']),
            models.Index(fields=['fuel_type', 'transmission']),
            models.Index(fields=['price']),
            models.Index(fields=['is_available', 'is_featured']),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.brand.name}-{self.title}")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.brand.name} {self.title}"


class CarImage(models.Model):
    """
    Car photo gallery images.
    """
    car = models.ForeignKey(
        Car,
        on_delete=models.CASCADE,
        related_name='images',
        verbose_name="Car"
    )
    image = models.ImageField(upload_to='cars/', verbose_name="Image File")
    is_primary = models.BooleanField(default=False, verbose_name="Primary Image")

    class Meta:
        verbose_name = "Car Image"
        verbose_name_plural = "Car Images"
        ordering = ['-is_primary', 'id']

    def __str__(self):
        return f"Image for {self.car.title} ({'Primary' if self.is_primary else 'Gallery'})"


class CarFeature(models.Model):
    """
    Specification feature (e.g. Panoramic Sunroof, ADAS, Ventilated Seats).
    """
    class Category(models.TextChoices):
        SAFETY = 'SAFETY', 'Safety'
        COMFORT = 'COMFORT', 'Comfort & Convenience'
        INFOTAINMENT = 'INFOTAINMENT', 'Infotainment & Connectivity'
        PERFORMANCE = 'PERFORMANCE', 'Performance & Handling'
        EXTERIOR = 'EXTERIOR', 'Exterior Features'

    name = models.CharField(max_length=100, verbose_name="Feature Name")
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.COMFORT,
        verbose_name="Category"
    )

    class Meta:
        verbose_name = "Car Feature"
        verbose_name_plural = "Car Features"
        ordering = ['category', 'name']

    def __str__(self):
        return f"{self.name} [{self.get_category_display()}]"


class CarFeatureMap(models.Model):
    """
    Mapping model linking Cars to Feature tags with availability state and source provenance.
    """
    class VerificationStatus(models.TextChoices):
        VERIFIED = 'VERIFIED', 'Verified (Exact Variant)'
        CLOSEST_VARIANT = 'CLOSEST_VARIANT', 'Estimated / Closest Variant'
        UNCONFIRMED = 'UNCONFIRMED', 'Unconfirmed / Pending Clarification'

    car = models.ForeignKey(
        Car,
        on_delete=models.CASCADE,
        related_name='feature_mappings',
        verbose_name="Car"
    )
    feature = models.ForeignKey(
        CarFeature,
        on_delete=models.CASCADE,
        related_name='car_mappings',
        verbose_name="Feature"
    )
    is_available = models.BooleanField(default=True, verbose_name="Is Available")
    source_url = models.URLField(max_length=500, blank=True, verbose_name="Source URL")
    verification_status = models.CharField(
        max_length=25,
        choices=VerificationStatus.choices,
        default=VerificationStatus.VERIFIED,
        verbose_name="Verification Status"
    )
    notes = models.CharField(max_length=255, blank=True, verbose_name="Research Notes")

    class Meta:
        verbose_name = "Car Feature Mapping"
        verbose_name_plural = "Car Feature Mappings"
        unique_together = ('car', 'feature')

    def __str__(self):
        status_symbol = "✓" if self.is_available else "✗"
        return f"{self.car.title} - {self.feature.name} [{status_symbol}]"


class CarSpecificationSource(models.Model):
    """
    Granular provenance records for researched numeric and dimensional specifications.
    Associates source URLs, verification status, and research notes per specification field.
    """
    class VerificationStatus(models.TextChoices):
        VERIFIED = 'VERIFIED', 'Verified (Exact Variant)'
        CLOSEST_VARIANT = 'CLOSEST_VARIANT', 'Estimated / Closest Variant'
        UNCONFIRMED = 'UNCONFIRMED', 'Unconfirmed / Pending Clarification'

    car = models.ForeignKey(
        Car,
        on_delete=models.CASCADE,
        related_name='spec_sources',
        verbose_name="Car"
    )
    spec_field = models.CharField(max_length=60, verbose_name="Specification Field")
    source_url = models.URLField(max_length=500, blank=True, verbose_name="Source URL")
    verification_status = models.CharField(
        max_length=25,
        choices=VerificationStatus.choices,
        default=VerificationStatus.VERIFIED,
        verbose_name="Verification Status"
    )
    notes = models.CharField(max_length=255, blank=True, verbose_name="Research Notes")

    class Meta:
        verbose_name = "Car Specification Source"
        verbose_name_plural = "Car Specification Sources"
        unique_together = ('car', 'spec_field')

    def __str__(self):
        return f"{self.car.title} - {self.spec_field} ({self.get_verification_status_display()})"
