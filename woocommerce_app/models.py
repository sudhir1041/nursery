from django.db import models
from django.utils import timezone 


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

    # Clone orders save here
    clone_orders = models.JSONField(default=list, blank=True, 
        help_text="Store clone orders as a JSON list, e.g., [{'order_id': 'XXX', 'platform': 'WooCommerce'}, ...]")

    # Django Timestamps
    django_date_created = models.DateTimeField(auto_now_add=True)
    django_date_modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"WooCommerce Order #{self.number or self.woo_id} ({self.status})"

    class Meta:
        verbose_name = "WooCommerce Order"
        verbose_name_plural = "WooCommerce Orders"
        ordering = ['-date_created_woo'] 
# This model for product data
class WooCommerceProduct(models.Model):
    """Represents a synchronized product from WooCommerce."""
    woo_id = models.PositiveIntegerField(
        unique=True,
        db_index=True,
        help_text="WooCommerce Product ID"
    )
    name = models.CharField(max_length=255, blank=True, null=True, help_text="Product name")
    slug = models.SlugField(max_length=255, blank=True, null=True, db_index=True, help_text="Product slug")
    sku = models.CharField(max_length=100, blank=True, null=True, db_index=True, help_text="Stock Keeping Unit")
    permalink = models.URLField(blank=True, null=True, help_text="Product URL on WooCommerce")
    type = models.CharField(max_length=50, blank=True, null=True, help_text="Product type (e.g., simple, variable)")
    status = models.CharField(max_length=50, blank=True, null=True, db_index=True, help_text="Product status (e.g., publish, draft)")
    featured = models.BooleanField(default=False, help_text="Is the product featured?")
    catalog_visibility = models.CharField(max_length=50, blank=True, null=True, help_text="Catalog visibility setting")
    description = models.TextField(blank=True, null=True, help_text="Full product description")
    short_description = models.TextField(blank=True, null=True, help_text="Short product description")
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Product price")
    regular_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Regular price")
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Sale price")
    on_sale = models.BooleanField(default=False, help_text="Is the product on sale?")
    total_sales = models.PositiveIntegerField(default=0, help_text="Number of total sales")
    weight = models.CharField(max_length=50, blank=True, null=True, help_text="Product weight")
    dimensions = models.JSONField(blank=True, null=True, help_text="Product dimensions (length, width, height)")
    stock_status = models.CharField(max_length=50, blank=True, null=True, db_index=True, help_text="Stock status (e.g., instock, outofstock)")
    stock_quantity = models.IntegerField(blank=True, null=True, help_text="Available stock quantity")
    backorders = models.CharField(max_length=50, blank=True, null=True, help_text="Backorders allowed?")
    low_stock_amount = models.IntegerField(blank=True, null=True, help_text="Low stock threshold")
    reviews_allowed = models.BooleanField(default=True, help_text="Are reviews allowed?")
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, blank=True, null=True, help_text="Average product rating")
    rating_count = models.PositiveIntegerField(default=0, help_text="Number of ratings")
    parent_id = models.PositiveIntegerField(blank=True, null=True, db_index=True, help_text="ID of the parent product (for variations)")
    categories_json = models.JSONField(blank=True, null=True, help_text="Raw JSON data for categories")
    tags_json = models.JSONField(blank=True, null=True, help_text="Raw JSON data for tags")
    images_json = models.JSONField(blank=True, null=True, help_text="Raw JSON data for product images")
    attributes_json = models.JSONField(blank=True, null=True, help_text="Raw JSON data for product attributes")
    variations_json = models.JSONField(blank=True, null=True, help_text="Raw JSON data for product variations")
    menu_order = models.IntegerField(default=0, help_text="Menu order position")
    meta_data_json = models.JSONField(blank=True, null=True, help_text="Raw JSON data for meta data")
    raw_data = models.JSONField(blank=True, null=True, help_text="Full webhook payload or API response")

    # Django Timestamps
    django_date_created = models.DateTimeField(auto_now_add=True)
    django_date_modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"WooCommerce Product: {self.name or self.woo_id}"

    class Meta:
        verbose_name = "WooCommerce Product"
        verbose_name_plural = "WooCommerce Products"
        ordering = ['name']
