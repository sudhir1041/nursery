from django.db import models


class SiteSettings(models.Model):
    """Central configuration stored in the database."""

    # --- Registration and admin contact ---
    registration_open = models.BooleanField(default=True)
    admin_contact_email = models.EmailField(blank=True, null=True)

    # --- WooCommerce API ---
    woocommerce_store_url = models.URLField(blank=True, null=True)
    woocommerce_consumer_key = models.CharField(max_length=255, blank=True, null=True)
    woocommerce_consumer_secret = models.CharField(max_length=255, blank=True, null=True)
    woocommerce_webhook_secret = models.CharField(max_length=255, blank=True, null=True)

    # --- Shopify API ---
    shopify_store_domain = models.CharField(max_length=255, blank=True, null=True)
    shopify_api_version = models.CharField(max_length=32, default="2024-04", blank=True, null=True)
    shopify_admin_access_token = models.CharField(max_length=255, blank=True, null=True)
    shopify_api_key = models.CharField(max_length=255, blank=True, null=True)
    shopify_api_secret_key = models.CharField(max_length=255, blank=True, null=True)
    shopify_webhook_secret = models.CharField(max_length=255, blank=True, null=True)

    # --- Logos ---
    site_logo = models.ImageField(upload_to="site_logo/", blank=True, null=True)
    company_logo = models.ImageField(upload_to="company_logo/", blank=True, null=True)

    # --- Invoicing company details ---
    company_name = models.CharField(max_length=100, blank=True, null=True)
    company_address = models.TextField(blank=True, null=True)
    company_phone = models.CharField(max_length=50, blank=True, null=True)
    company_email = models.EmailField(blank=True, null=True)
    company_website = models.URLField(blank=True, null=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return "Site Settings"


def get_site_settings():
    """Return the single instance of :class:`SiteSettings` if it exists."""
    return SiteSettings.objects.first()

