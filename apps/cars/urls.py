from django.urls import path
from .views import (
    home_view,
    car_list_view,
    car_detail_view,
    compare_view,
    api_compare_search,
    api_compare_details,
)
from .api_views import CarListAPIView, CarDetailAPIView

app_name = 'cars'

urlpatterns = [
    # Web Showroom Pages
    path('', home_view, name='home'),
    path('cars/', car_list_view, name='car_list'),
    path('cars/<slug:slug>/', car_detail_view, name='car_detail'),
    path('compare/', compare_view, name='compare'),

    # Compare Cars APIs (must be declared before generic <slug:slug> API route)
    path('api/cars/compare/search/', api_compare_search, name='api_compare_search'),
    path('api/cars/compare/details/', api_compare_details, name='api_compare_details'),

    # Read-Only REST API Endpoints
    path('api/cars/', CarListAPIView.as_view(), name='api_car_list'),
    path('api/cars/<slug:slug>/', CarDetailAPIView.as_view(), name='api_car_detail'),
]
