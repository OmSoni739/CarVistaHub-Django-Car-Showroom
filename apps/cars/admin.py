from django.contrib import admin
from .models import Brand, Car, CarImage, CarFeature, CarFeatureMap, CarSpecificationSource


class CarImageInline(admin.TabularInline):
    model = CarImage
    extra = 1


class CarFeatureMapInline(admin.TabularInline):
    model = CarFeatureMap
    extra = 1
    fields = ('feature', 'is_available', 'verification_status', 'source_url', 'notes')


class CarSpecificationSourceInline(admin.TabularInline):
    model = CarSpecificationSource
    extra = 1
    fields = ('spec_field', 'verification_status', 'source_url', 'notes')


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('name',)


@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = ('title', 'brand', 'body_type', 'price', 'fuel_type', 'transmission', 'stock_quantity', 'is_available', 'is_featured')
    list_filter = ('brand', 'body_type', 'fuel_type', 'transmission', 'is_available', 'is_featured')
    search_fields = ('title', 'brand__name', 'description')
    prepopulated_fields = {'slug': ('title',)}
    ordering = ('-created_at',)
    inlines = [CarImageInline, CarFeatureMapInline, CarSpecificationSourceInline]


@admin.register(CarImage)
class CarImageAdmin(admin.ModelAdmin):
    list_display = ('car', 'is_primary', 'image')
    list_filter = ('is_primary', 'car__brand')
    search_fields = ('car__title',)


@admin.register(CarFeature)
class CarFeatureAdmin(admin.ModelAdmin):
    list_display = ('name', 'category')
    list_filter = ('category',)
    search_fields = ('name',)
    ordering = ('category', 'name')


@admin.register(CarFeatureMap)
class CarFeatureMapAdmin(admin.ModelAdmin):
    list_display = ('car', 'feature', 'is_available', 'verification_status')
    list_filter = ('is_available', 'verification_status', 'feature__category', 'car__brand')
    search_fields = ('car__title', 'feature__name', 'notes')


@admin.register(CarSpecificationSource)
class CarSpecificationSourceAdmin(admin.ModelAdmin):
    list_display = ('car', 'spec_field', 'verification_status', 'source_url')
    list_filter = ('verification_status', 'car__brand')
    search_fields = ('car__title', 'spec_field', 'notes')
