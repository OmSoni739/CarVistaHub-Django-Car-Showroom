from rest_framework import generics
from .models import Car
from .serializers import CarSerializer


class CarListAPIView(generics.ListAPIView):
    """
    Read-only endpoint returning all currently available cars as a JSON list.
    Eagerly loads related Brand entity to prevent N+1 queries.
    """
    serializer_class = CarSerializer
    pagination_class = None

    def get_queryset(self):
        return Car.objects.filter(is_available=True).select_related('brand').order_by('-created_at')


class CarDetailAPIView(generics.RetrieveAPIView):
    """
    Read-only endpoint returning complete JSON details of a single car by slug.
    Eagerly loads related Brand entity to prevent N+1 queries.
    """
    serializer_class = CarSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        return Car.objects.all().select_related('brand')
