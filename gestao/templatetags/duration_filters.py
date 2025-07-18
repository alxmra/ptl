from django import template
from decimal import Decimal

register = template.Library()

@register.filter
def duration_format(value):
    """
    Convert decimal hours to hours and minutes format.
    Example: 15.50 -> "15h30m", 2.25 -> "2h15m", 1.00 -> "1h"
    """
    if value is None:
        return "0h"

    # Convert to Decimal for precise calculation
    decimal_hours = Decimal(str(value))

    # Extract hours and minutes
    hours = int(decimal_hours)
    minutes = int((decimal_hours - hours) * 60)

    # Format the output
    if minutes == 0:
        return f"{hours}h"
    else:
        return f"{hours}h{minutes:02d}m"

@register.filter
def duration_format_js(value):
    """
    Convert decimal hours to hours and minutes format for JavaScript.
    Same as duration_format but ensures consistent string output for JS.
    """
    return duration_format(value)
