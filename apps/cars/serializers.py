from rest_framework import serializers
from .models import Brand, Car


class BrandSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for Brand information.
    """
    class Meta:
        model = Brand
        fields = ['id', 'name', 'slug']


class CarSerializer(serializers.ModelSerializer):
    """
    Read-only ModelSerializer for the user-defined Car model.
    Includes nested brand details and core technical/catalog attributes.
    """
    brand = BrandSerializer(read_only=True)

    class Meta:
        model = Car
        fields = [
            'id',
            'title',
            'slug',
            'brand',
            'body_type',
            'price',
            'booking_amount',
            'fuel_type',
            'transmission',
            'engine_capacity',
            'seating_capacity',
            'mileage',
            'color_options',
            'stock_quantity',
            'is_available',
            'is_featured',
            'description',
            'power',
            'torque',
            'length',
            'width',
            'height',
            'wheelbase',
            'ground_clearance',
            'boot_space',
            'airbag_count',
            'touchscreen_size',
            'speaker_count',
            'usb_port_count',
            'usb_details',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields
