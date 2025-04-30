from django.db import models
from django.utils import timezone # Import timezone


SHIPMENT_STATUS_CHOICES = [
    ('pending', 'Pending'), 
    ('shipped', 'Shipped'),
    ('on-hold', 'On Hold'),
]
class WooCommerceOrder(models.Model):
    """ Represents a synchronized order from WooCommerce """
    woo_id = models.PositiveIntegerField(
        unique=True,
        db_index=True,
        help_text="WooCommerce Order ID"
    )
    number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text="WooCommerce order number (might be different from ID)"
    )
    status = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    currency = models.CharField(default="₹" ,max_length=10, blank=True, null=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    customer_note = models.TextField(blank=True, null=True)
    shipment_status = models.CharField(
        max_length=50,
        choices=SHIPMENT_STATUS_CHOICES,
        default='pending',
        blank=False, null=False,
        db_index=True
    )

    # Billing Info
    billing_first_name = models.CharField(max_length=100, blank=True, null=True)
    billing_last_name = models.CharField(max_length=100, blank=True, null=True)
    billing_company = models.CharField(max_length=200, blank=True, null=True)
    billing_address_1 = models.CharField(max_length=255, blank=True, null=True)
    billing_address_2 = models.CharField(max_length=255, blank=True, null=True)
    billing_city = models.CharField(max_length=100, blank=True, null=True)
    billing_state = models.CharField(max_length=100, blank=True, null=True)
    billing_postcode = models.CharField(max_length=20, blank=True, null=True)
    billing_country = models.CharField(max_length=50, blank=True, null=True)
    billing_email = models.EmailField(blank=True, null=True, db_index=True)
    billing_phone = models.CharField(max_length=50, blank=True, null=True)

    # Timestamps
    date_created_woo = models.DateTimeField(blank=True, null=True, help_text="Timestamp from WooCommerce (UTC)")
    date_modified_woo = models.DateTimeField(blank=True, null=True, help_text="Timestamp from WooCommerce (UTC)")
    date_paid_woo = models.DateTimeField(blank=True, null=True, help_text="Timestamp from WooCommerce (UTC)")
    date_completed_woo = models.DateTimeField(blank=True, null=True, help_text="Timestamp from WooCommerce (UTC)")

    # Store the raw data for future reference or complex fields
    line_items_json = models.JSONField(blank=True, null=True, help_text="Raw JSON data for line items")
    shipping_lines_json = models.JSONField(blank=True, null=True, help_text="Raw JSON data for shipping lines")
    raw_data = models.JSONField(blank=True, null=True, help_text="Full webhook payload or API response")

    # Django Timestamps
    django_date_created = models.DateTimeField(auto_now_add=True)
    django_date_modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"WooCommerce Order #{self.number or self.woo_id} ({self.status})"

    class Meta:
        verbose_name = "WooCommerce Order"
        verbose_name_plural = "WooCommerce Orders"
        ordering = ['-date_created_woo'] 