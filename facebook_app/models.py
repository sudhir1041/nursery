from django.db import models
from django.utils import timezone
import json 

ORDER_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('processing', 'Processing'),
    ('shipped', 'Shipped'),
    ('delivered', 'Delivered'),
    ('cancelled', 'Cancelled'),
    ('on-hold', 'On Hold'),
]

SHIPMENT_STATUS_CHOICES = [
    ('pending', 'Pending'), 
    ('shipped', 'Shipped'),
    ('on-hold', 'On Hold'),
]


def default_empty_list():
    return []

class Facebook_orders(models.Model):
    order_id = models.CharField(max_length=100, unique=True, db_index=True, help_text="Only Add Number Value Don't use any letter.")
    email = models.EmailField(blank=True, null=True, db_index=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    company = models.CharField(max_length=200, blank=True, null=True)
    address = models.TextField(blank=True, null=True) 
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    postcode = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(default="INDIA", max_length=50, blank=True, null=True)
    date_created = models.DateTimeField(default=timezone.now)
    date_modified = models.DateTimeField(auto_now=True)
    currency = models.CharField(default="INR", max_length=10, blank=True, null=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    customer_note = models.TextField(blank=True, null=True)
    mode_of_payment = models.CharField(max_length=50, blank=True, null=True)
    alternet_number = models.CharField(max_length=50, blank=True, null=True)
    received_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    shipment_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    pending_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    plateform = models.CharField(default="Manual", max_length=100, blank=True, null=True)
    status = models.CharField(
        max_length=50,
        choices=ORDER_STATUS_CHOICES,
        default='processing',
        blank=False, null=False,
        db_index=True
    )
    shipment_status = models.CharField(
        max_length=50,
        choices=SHIPMENT_STATUS_CHOICES,
        default='pending',
        blank=False, null=False,
        db_index=True
    )
    tracking_info = models.TextField(
        blank=True,
        help_text="Enter tracking numbers, links, or carrier info here."
    )
    internal_notes = models.TextField(
        blank=True,
        help_text="Internal staff notes about this order."
    )

    products_json = models.JSONField(
        default=default_empty_list, 
        blank=True,
        help_text='Store product line items as a JSON list, e.g., [{"name": "Plant A", "qty": 2, "price": "150.00"}, ...]'
    )
    
    clone_orders = models.JSONField(
        default=default_empty_list,
        blank=True,
        help_text='Store clone orders as a JSON list, e.g., [{"order_id": "XXX", "platform": "facebook"}, ...]'
    )
    def __str__(self):
        return f"FB Order {self.order_id} ({self.billing_first_name or self.billing_email or ''})"

    class Meta:
         verbose_name = "Facebook Order"
         verbose_name_plural = "Facebook Orders"
         ordering = ['-date_created']