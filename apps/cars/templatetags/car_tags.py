"""
Re-export currency filters under car_tags for template compatibility.
"""
from django import template
from .currency_tags import indian_currency, intcomma_indian, inr_format

register = template.Library()

register.filter('indian_currency', indian_currency)
register.filter('intcomma_indian', intcomma_indian)
register.filter('inr_format', inr_format)
