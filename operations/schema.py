"""Schema configuration loaded after Django initializes the model registry."""
from .models import Order

ORDER_STATUS_CHOICES = Order.Status.choices
