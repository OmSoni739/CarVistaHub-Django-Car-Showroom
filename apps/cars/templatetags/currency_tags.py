"""
Template tags and filters for currency formatting in CarVistaHub.
Provides Indian numbering system comma grouping (Lakhs / Crores).
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django import template

register = template.Library()


@register.filter(name='indian_currency')
def indian_currency(value):
    """
    Format a numeric value using the Indian numbering system with commas and 2 decimal places.

    Examples:
        1850000.00  -> '18,50,000.00'
        25000.00    -> '25,000.00'
        1500000.00  -> '15,00,000.00'
        950000.00   -> '9,50,000.00'
        75000.00    -> '75,000.00'
        12345678.00 -> '1,23,45,678.00'
        999.00      -> '999.00'
        0           -> '0.00'
    """
    if value is None or value == '':
        return ''

    try:
        if isinstance(value, Decimal):
            dec_val = value
        elif isinstance(value, (int, float)):
            dec_val = Decimal(str(value))
        elif isinstance(value, str):
            clean_str = value.strip().replace('₹', '').replace(',', '')
            if not clean_str:
                return ''
            dec_val = Decimal(clean_str)
        else:
            dec_val = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return value

    dec_val = dec_val.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if dec_val.is_zero():
        is_neg = False
    else:
        is_neg = dec_val < 0

    dec_str = f'{abs(dec_val):.2f}'
    parts = dec_str.split('.')
    integer_part = parts[0]
    decimal_part = parts[1]

    if len(integer_part) <= 3:
        grouped = integer_part
    else:
        last_three = integer_part[-3:]
        rest = integer_part[:-3]
        rest_rev = rest[::-1]
        chunks = [rest_rev[i:i + 2] for i in range(0, len(rest_rev), 2)]
        grouped = ','.join(chunks)[::-1] + ',' + last_three

    formatted = f'{grouped}.{decimal_part}'
    return f'-{formatted}' if is_neg else formatted


@register.filter(name='intcomma_indian')
def intcomma_indian(value):
    """Alias for indian_currency filter."""
    return indian_currency(value)


@register.filter(name='inr_format')
def inr_format(value):
    """Alias for indian_currency filter."""
    return indian_currency(value)


