from django.db import models
from django.utils import timezone


SHIPMENT_STATUS_CHOICES = [
    ('pending', 'Pending'), 
    ('shipped', 'Shipped'),
    ('on-hold', 'On Hold'),
]

class ShopifyOrder(models.Model):
    """ Represents a synchronized order from Shopify """
    shopify_id = models.BigIntegerField(
        unique=True,
        db_index=True,
        help_text="Shopify Order ID"
    )
    name = models.CharField(
        max_length=100,
        blank=True, null=True,
        db_index=True,
        help_text="Shopify order name (e.g., #1001)"
    )
    email = models.EmailField(blank=True, null=True, db_index=True)
    financial_status = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    fulfillment_status = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    currency = models.CharField(max_length=10, blank=True, null=True)
    shipment_status = models.CharField(
        max_length=50,
        choices=SHIPMENT_STATUS_CHOICES,
        default='pending',
        blank=False, null=False,
        db_index=True
    )
    # Store complex nested data like addresses or line items as JSON
    billing_address_json = models.JSONField(blank=True, null=True)
    shipping_address_json = models.JSONField(blank=True, null=True)
    line_items_json = models.JSONField(blank=True, null=True)

    # --- NEW FIELD for Tracking Details ---
    tracking_details_json = models.JSONField(
        blank=True,
        null=True,
        help_text="Store tracking numbers, URLs, carrier info, or structured fulfillment data as JSON"
    )

    # --- NEW FIELD for Internal Notes ---
    internal_notes = models.TextField(
        blank=True, # Allow it to be empty
        help_text="Internal administrative notes about this order (not from Shopify)"
    )

    # Timestamps from Shopify (Note: Shopify uses ISO 8601 format)
    created_at_shopify = models.DateTimeField(blank=True, null=True)
    updated_at_shopify = models.DateTimeField(blank=True, null=True)
    closed_at_shopify = models.DateTimeField(blank=True, null=True)
    #Add other timestamps if needed (processed_at, closed_at)
    #processed_at_shopify = models.DateTimeField(blank=True, null=True)

    # Store the full raw data for reference or if fields are missed
    raw_data = models.JSONField(blank=True, null=True, help_text="Raw JSON data from API or webhook")

    # Django Timestamps
    django_date_created = models.DateTimeField(default=timezone.now)
    django_date_modified = models.DateTimeField(auto_now=True)


    def __str__(self):
        return f"Shopify Order {self.name or self.shopify_id} ({self.financial_status})"

    class Meta:
        verbose_name = "Shopify Order"
        verbose_name_plural = "Shopify Orders"
        ordering = ['-created_at_shopify']