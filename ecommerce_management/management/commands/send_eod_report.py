from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import EmailMessage

from woocommerce_app.models import WooCommerceOrder
from shopify_app.models import ShopifyOrder
from facebook_app.models import Facebook_orders
from settings_app.utils import get_email_connection, get_setting


class Command(BaseCommand):
    help = "Send end-of-day order summary via email"

    def handle(self, *args, **options):
        today = timezone.now().date()
        wc = WooCommerceOrder.objects.filter(django_date_created__date=today).count()
        shop = ShopifyOrder.objects.filter(created_at_shopify__date=today).count()
        fb = Facebook_orders.objects.filter(date_created__date=today).count()

        body = (
            f"Daily report for {today}\n"
            f"WooCommerce orders: {wc}\n"
            f"Shopify orders: {shop}\n"
            f"Facebook orders: {fb}"
        )
        recipient = get_setting('REPORT_RECIPIENT_EMAIL')
        from_email = get_setting('EMAIL_FROM') or get_setting('EMAIL_HOST_USER')
        connection = get_email_connection()
        if connection and recipient:
            EmailMessage(
                "Daily Order Report",
                body,
                from_email,
                [recipient],
                connection=connection,
            ).send()
            self.stdout.write("Report email sent")
        else:
            self.stdout.write("Email credentials or recipient missing")
