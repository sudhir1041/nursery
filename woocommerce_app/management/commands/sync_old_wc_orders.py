import logging
from dateutil import parser # For robust date string parsing (pip install python-dateutil)
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

# Import your model and utility function
from woocommerce_app.models import WooCommerceOrder # <--- Adjust 'yourapp' if needed
from utils import fetch_orders_from_woo # <--- Adjust 'yourapp' if needed

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Syncs historical orders from WooCommerce REST API to the local database.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--pages',
            type=int,
            help='Number of pages to fetch (optional, fetches all if not specified).',
        )
        parser.add_argument(
            '--per_page',
            type=int,
            default=50, # Adjust based on performance/memory, max 100
            help='Number of orders to fetch per API call (default: 50).',
        )
        parser.add_argument(
            '--start_page',
            type=int,
            default=1,
            help='Page number to start fetching from (default: 1).',
        )
        # Add more arguments if needed, e.g., --status, --after_date

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting historical WooCommerce order sync..."))

        current_page = options['start_page']
        per_page = options['per_page']
        limit_pages = options['pages'] # Max number of pages to fetch, if specified
        pages_fetched = 0
        orders_processed = 0
        orders_created = 0
        orders_updated = 0

        while True:
            if limit_pages is not None and pages_fetched >= limit_pages:
                self.stdout.write(f"Reached specified page limit ({limit_pages}). Stopping.")
                break

            self.stdout.write(f"Fetching page {current_page} ({per_page} orders per page)...")

            # Use your utility function to fetch orders
            params = {
                'page': current_page,
                'per_page': per_page,
                'orderby': 'id', # Order by ID for consistency
                'order': 'asc',  # Start from oldest
                # Add other filters if needed from options, e.g.:
                # 'status': options.get('status')
            }
            orders_data, total_pages, total_orders = fetch_orders_from_woo(params=params)

            if not orders_data:
                if current_page == 1:
                     self.stdout.write(self.style.WARNING("No orders found at all."))
                else:
                     self.stdout.write("No more orders found on subsequent pages. Sync likely complete.")
                break # Exit loop if no orders are returned

            # Get the total pages on the first iteration
            if current_page == options['start_page']:
                 self.stdout.write(f"Total Orders reported by API: {total_orders}")
                 self.stdout.write(f"Total Pages reported by API: {total_pages}")

            # Process fetched orders
            for order_data in orders_data:
                orders_processed += 1
                woo_id = order_data.get('id')
                if not woo_id:
                    self.stderr.write(self.style.ERROR("Skipping order data with missing ID."))
                    continue

                try:
                    # Use atomic transaction for each order to ensure data integrity
                    with transaction.atomic():
                        # Prepare data for the model fields
                        billing_info = order_data.get('billing', {})
                        defaults = {
                            'number': order_data.get('number'),
                            'status': order_data.get('status'),
                            'currency': order_data.get('currency'),
                            'total_amount': order_data.get('total'),
                            'customer_note': order_data.get('customer_note'),
                            # Billing Info
                            'billing_first_name': billing_info.get('first_name'),
                            'billing_last_name': billing_info.get('last_name'),
                            'billing_company': billing_info.get('company'),
                            'billing_address_1': billing_info.get('address_1'),
                            'billing_address_2': billing_info.get('address_2'),
                            'billing_city': billing_info.get('city'),
                            'billing_state': billing_info.get('state'),
                            'billing_postcode': billing_info.get('postcode'),
                            'billing_country': billing_info.get('country'),
                            'billing_email': billing_info.get('email'),
                            'billing_phone': billing_info.get('phone'),
                            # Timestamps (Parse safely)
                            'date_created_woo': self.parse_datetime(order_data.get('date_created_gmt')),
                            'date_modified_woo': self.parse_datetime(order_data.get('date_modified_gmt')),
                            'date_paid_woo': self.parse_datetime(order_data.get('date_paid_gmt')),
                            'date_completed_woo': self.parse_datetime(order_data.get('date_completed_gmt')),
                            # Store raw JSON data
                            'line_items_json': order_data.get('line_items', []),
                            'shipping_lines_json': order_data.get('shipping_lines', []),
                            'raw_data': order_data, # Store the entire payload
                            # NOTE: shipment_status is likely NOT in the WC order payload by default.
                            # You might need custom logic or leave it as default 'pending'.
                            # 'shipment_status': 'pending', # Or determine based on WC status/meta
                        }

                        # Use update_or_create to insert new or update existing based on woo_id
                        order_obj, created = WooCommerceOrder.objects.update_or_create(
                            woo_id=woo_id,
                            defaults=defaults
                        )

                        if created:
                            orders_created += 1
                            # self.stdout.write(f"CREATED Order: WC ID {woo_id} -> Django ID {order_obj.id}")
                        else:
                            orders_updated += 1
                            # self.stdout.write(f"UPDATED Order: WC ID {woo_id} -> Django ID {order_obj.id}")

                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"Failed to process or save order WC ID {woo_id}: {e}"))
                    # Optionally continue to next order or break, depending on desired behavior
                    continue # Continue with the next order

            pages_fetched += 1

            # Break if this was the last page based on API headers
            # Check against total_pages only if it's reliable (> 0)
            if total_pages > 0 and current_page >= total_pages:
                 self.stdout.write("Reached the last page reported by API.")
                 break

            # Safety break if API doesn't report total_pages correctly but returns empty list next time
            if len(orders_data) < per_page:
                 self.stdout.write("Fetched less orders than per_page limit, assuming last page.")
                 break

            current_page += 1

        self.stdout.write(self.style.SUCCESS("-" * 30))
        self.stdout.write(self.style.SUCCESS("Sync finished!"))
        self.stdout.write(f"Total Orders Processed: {orders_processed}")
        self.stdout.write(f"New Orders Created: {orders_created}")
        self.stdout.write(f"Existing Orders Updated: {orders_updated}")
        self.stdout.write(f"Pages Fetched: {pages_fetched}")

    def parse_datetime(self, date_string):
        """Safely parses a date string into a timezone-aware datetime object."""
        if not date_string:
            return None
        try:
            # Use dateutil.parser for flexibility with formats, assumes UTC if no timezone specified
            dt = parser.parse(date_string)
            # Ensure the datetime object is timezone-aware (make it UTC if naive)
            if timezone.is_naive(dt):
                return timezone.make_aware(dt, timezone.utc)
            return dt
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not parse date string '{date_string}': {e}")
            return None
        

# Commmand for get older orders 
# Run the Management Command

# Open your terminal in your Django project's root directory (where manage.py is).
# Run the command:
# Bash

# python manage.py sync_old_wc_orders
# To control the number of orders per page (e.g., if you hit timeouts or memory limits):
# Bash

# python manage.py sync_old_wc_orders --per_page=25
# To fetch only the first 5 pages:
# Bash

# python manage.py sync_old_wc_orders --pages=5
# To resume from a specific page (e.g., if it was interrupted):
# Bash

# python manage.py sync_old_wc_orders --start_page=11