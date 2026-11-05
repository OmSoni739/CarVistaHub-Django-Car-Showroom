from django.contrib import admin
from .models import Wishlist, Review


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ('user', 'car', 'added_at')
    list_filter = ('added_at', 'car__brand')
    search_fields = ('user__username', 'user__email', 'car__title')
    ordering = ('-added_at',)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('user', 'car', 'rating', 'created_at')
    list_filter = ('rating', 'created_at', 'car__brand')
    search_fields = ('user__username', 'car__title', 'comment')
    ordering = ('-created_at',)
