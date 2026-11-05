from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.cars.models import Car


class Wishlist(models.Model):
    """
    Customer vehicle wishlist / favorites record.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wishlist_items',
        verbose_name="User"
    )
    car = models.ForeignKey(
        Car,
        on_delete=models.CASCADE,
        related_name='wishlisted_by',
        verbose_name="Wishlisted Car"
    )
    added_at = models.DateTimeField(auto_now_add=True, verbose_name="Added At")

    class Meta:
        verbose_name = "Wishlist Item"
        verbose_name_plural = "Wishlist Items"
        ordering = ['-added_at']
        unique_together = ('user', 'car')
        indexes = [
            models.Index(fields=['user', 'car']),
        ]

    def __str__(self):
        return f"{self.user.username} -> {self.car.title}"


class Review(models.Model):
    """
    Customer review and 1-5 star rating for cars.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name="User"
    )
    car = models.ForeignKey(
        Car,
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name="Car"
    )
    rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="Rating (1 to 5 Stars)"
    )
    comment = models.TextField(verbose_name="Review Comment")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Submitted At")

    class Meta:
        verbose_name = "Car Review"
        verbose_name_plural = "Car Reviews"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['car', 'rating']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.car.title} ({self.rating}★)"
