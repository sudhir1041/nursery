import logging
from dateutil import parser # For robust date string parsing (pip install python-dateutil)
from django.core.management.base import BaseCommand
from django.db import transaction
# Correctly import Django's timezone utilities
from django.utils.timezone import make_aware, is_naive
from datetime import datetime, timezone

# Import your model and utility function
# --- Make sure 'woocommerce_app' is the correct name of your Django app ---
try:
    from woocommerce_app.models import WooCommerceOrder
    from woocommerce_app.utils import fetch_orders_from_woo
except ImportError:
    # Provide a helpful message if the app/modules can't be found
    print("ERROR: Could not import WooCommerceOrder or fetch_orders_from_woo.")
    print("Please ensure:")
    print("1. 'woocommerce_app' is the correct name of your Django app containing models.py and utils.py.")
    print("2. Your virtual environment is activated.")
    print("3. The necessary files (models.py, utils.py) exist in the specified app.")
    # Optionally, exit or raise a more specific error
    # import sys
    # sys.exit(1)
    # Or define dummy classes/functions if you want the file to be parseable
    # without the app being fully set up yet (not recommended for runtime)
    class WooCommerceOrder: pass
    def fetch_orders_from_woo(*args, **kwargs): return [], 0, 0
    print("WARNING: Using dummy definitions for WooCommerceOrder and fetch_orders_from_woo.")


logger = logging.getLogger(__name__)
# Basic logging configuration (add this if you don't have project-wide logging setup)
# logging.basicConfig(level=logging.INFO)

class Command(BaseCommand):
    """
    Django management command to sync historical orders from WooCommerce REST API
    to the local database. Fetches orders page by page and saves them using
    update_or_create based on the WooCommerce order ID.
    """
    help = 'Syncs historical orders from WooCommerce REST API to the local database.'

    def add_arguments(self, parser):
        """Adds command-line arguments for controlling the sync process."""
        parser.add_argument(
            '--pages',
            type=int,
            help='Number of pages to fetch (optional, fetches all if not specified).',
        )
        parser.add_argument(
            '--per_page',
            type=int,
            default=50, # Sensible default, adjust based on API limits/performance
            help='Number of orders to fetch per API call (default: 50, max usually 100).',
        )
        parser.add_argument(
            '--start_page',
            type=int,
            default=1,
            help='Page number to start fetching from (default: 1). Useful for resuming.',
        )
        # Example: Add an argument to filter by status
        # parser.add_argument(
        #     '--status',
        #     type=str,
        #     help='Filter orders by status (e.g., processing, completed).',
        # )
         # Example: Add an argument to fetch orders after a specific date
        # parser.add_argument(
        #     '--after_date',
        #     type=str, # Expecting YYYY-MM-DD format
        #     help='Only fetch orders created after this date (YYYY-MM-DD).',
        # )

    def handle(self, *args, **options):
        """The main execution logic of the command."""
        self.stdout.write(self.style.SUCCESS("Starting historical WooCommerce order sync..."))

        current_page = options['start_page']
        per_page = options['per_page']
        limit_pages = options['pages'] # Max number of pages to fetch, if specified
        pages_fetched = 0
        orders_processed = 0
        orders_created = 0
        orders_updated = 0

        # --- Parameter Preparation ---
        # Prepare the base parameters for the API call
        base_params = {
            'per_page': per_page,
            'orderby': 'id', # Order by ID for consistency
            'order': 'asc',  # Start from the oldest orders
        }
        # Add optional filters from command-line arguments
        # if options.get('status'):
        #    base_params['status'] = options['status']
        # if options.get('after_date'):
        #     try:
        #         # Ensure the date format is correct for the API (usually ISO 8601)
        #         after_dt = datetime.strptime(options['after_date'], '%Y-%m-%d')
        #         # Format as ISO 8601, you might need to adjust based on API requirements
        #         base_params['after'] = after_dt.isoformat()
        #     except ValueError:
        #         self.stderr.write(self.style.ERROR(f"Invalid date format for --after_date. Use YYYY-MM-DD."))
        #         return # Stop execution if date format is wrong

        # --- Pagination Loop ---
        while True:
            if limit_pages is not None and pages_fetched >= limit_pages:
                self.stdout.write(f"Reached specified page limit ({limit_pages}). Stopping.")
                break

            self.stdout.write(f"Fetching page {current_page} ({per_page} orders per page)...")

            # Add the current page number to the parameters for this specific request
            request_params = base_params.copy()
            request_params['page'] = current_page

            # --- API Call ---
            try:
                # Use your utility function to fetch orders
                orders_data, total_pages, total_orders = fetch_orders_from_woo(params=request_params)
                # Basic validation of the returned data (can be more robust)
                if not isinstance(orders_data, list):
                     self.stderr.write(self.style.ERROR(f"API function did not return a list for page {current_page}. Got: {type(orders_data)}. Stopping."))
                     break
                self.stdout.write(self.style.SUCCESS(f"Successfully fetched {len(orders_data)} orders (page {current_page}). API Total Orders: {total_orders}, Total Pages: {total_pages}"))

            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error fetching orders from WooCommerce API on page {current_page}: {e}"))
                # Decide whether to retry, skip page, or stop
                # For simplicity, we'll stop here. Implement retry logic if needed.
                break

            # --- Exit Conditions ---
            if not orders_data:
                if current_page == options['start_page']: # Check if it was the very first page attempted
                     self.stdout.write(self.style.WARNING(f"No orders found matching the criteria on the first page (page {current_page})."))
                else:
                     self.stdout.write("No more orders found on subsequent pages. Sync likely complete.")
                break # Exit loop if no orders are returned

            # Display total pages/orders info only once on the first successful fetch
            if pages_fetched == 0: # Use pages_fetched counter instead of current_page == start_page
                 self.stdout.write(f"Total Orders reported by API: {total_orders}")
                 self.stdout.write(f"Total Pages reported by API: {total_pages}")

            # --- Process Fetched Orders ---
            for order_data in orders_data:
                orders_processed += 1
                woo_id = order_data.get('id')

                if not woo_id:
                    self.stderr.write(self.style.ERROR("Skipping order data with missing WC ID."))
                    continue

                try:
                    # Use atomic transaction for each order to ensure data integrity
                    # If one order fails, others in the batch are not affected unless the whole command fails later
                    with transaction.atomic():
                        # Prepare data for the model fields from the API response
                        billing_info = order_data.get('billing', {})
                        defaults = {
                            'number': order_data.get('number'),
                            'status': order_data.get('status', 'unknown'), # Provide default
                            'currency': order_data.get('currency'),
                            'total_amount': order_data.get('total'), # Ensure this matches model field type (DecimalField?)
                            'customer_note': order_data.get('customer_note', ''), # Default to empty string

                            # Billing Info (provide defaults for potentially missing fields)
                            'billing_first_name': billing_info.get('first_name', ''),
                            'billing_last_name': billing_info.get('last_name', ''),
                            'billing_company': billing_info.get('company', ''),
                            'billing_address_1': billing_info.get('address_1', ''),
                            'billing_address_2': billing_info.get('address_2', ''),
                            'billing_city': billing_info.get('city', ''),
                            'billing_state': billing_info.get('state', ''),
                            'billing_postcode': billing_info.get('postcode', ''),
                            'billing_country': billing_info.get('country', ''),
                            'billing_email': billing_info.get('email'), # Often required, maybe validate?
                            'billing_phone': billing_info.get('phone', ''),

                            # Timestamps (Parse safely using the corrected method)
                            # Use '_gmt' fields as they are timezone-aware (UTC) from WC
                            'date_created_woo': self.parse_datetime(order_data.get('date_created_gmt')),
                            'date_modified_woo': self.parse_datetime(order_data.get('date_modified_gmt')),
                            'date_paid_woo': self.parse_datetime(order_data.get('date_paid_gmt')),
                            'date_completed_woo': self.parse_datetime(order_data.get('date_completed_gmt')),

                            # Store relevant JSON data if needed (e.g., for later processing)
                            # Ensure your model fields 'line_items_json', etc. are JSONField
                            'line_items_json': order_data.get('line_items', []),
                            'shipping_lines_json': order_data.get('shipping_lines', []),
                            # Consider storing the entire payload for debugging or future use
                            'raw_data': order_data,

                            # NOTE: shipment_status is likely NOT in the standard WC order payload.
                            # You'll need custom logic (e.g., checking meta fields added by
                            # shipping plugins, or mapping WC status to shipment status)
                            # or leave it to its default value in the model.
                            # 'shipment_status': determine_shipment_status(order_data), # Example
                        }

                        # Remove None values from defaults if your model fields don't allow null=True
                        # defaults = {k: v for k, v in defaults.items() if v is not None}

                        # --- Database Operation ---
                        # Use update_or_create: finds an order by woo_id or creates a new one
                        order_obj, created = WooCommerceOrder.objects.update_or_create(
                            woo_id=woo_id,  # The unique key to find the record
                            defaults=defaults # Fields to update or set on creation
                        )

                        if created:
                            orders_created += 1
                            # Verbose logging, uncomment if needed during debugging
                            # self.stdout.write(f"CREATED Order: WC ID {woo_id} -> DB ID {order_obj.id}")
                        else:
                            orders_updated += 1
                            # Verbose logging, uncomment if needed
                            # self.stdout.write(f"UPDATED Order: WC ID {woo_id} -> DB ID {order_obj.id}")

                except Exception as e:
                    # Log detailed error for the specific order that failed
                    self.stderr.write(self.style.ERROR(f"Failed to process or save order WC ID {woo_id}: {e}"))
                    # Log the problematic data if possible (be mindful of sensitive info)
                    # logger.error(f"Error processing order WC ID {woo_id}. Data: {order_data}", exc_info=True)
                    # Continue with the next order in the batch
                    continue

            # --- Loop Increment and Termination Check ---
            pages_fetched += 1

            # Check if this was the last page based on API headers
            # Only rely on total_pages if the API provides a valid number (> 0)
            if total_pages is not None and total_pages > 0 and current_page >= total_pages:
                self.stdout.write("Reached the last page reported by API.")
                break

            # Safety break: If the API returned fewer items than requested,
            # it's likely the last page, even if total_pages wasn't accurate.
            if len(orders_data) < per_page:
                self.stdout.write(f"Fetched {len(orders_data)} orders, which is less than the per_page limit ({per_page}). Assuming this was the last page.")
                break

            # Move to the next page
            current_page += 1

            # Optional: Add a small delay between pages if you're hitting API rate limits
            # import time
            # time.sleep(1) # Sleep for 1 second

        # --- Final Summary ---
        self.stdout.write(self.style.SUCCESS("-" * 30))
        self.stdout.write(self.style.SUCCESS("Sync finished!"))
        self.stdout.write(f"Total Orders Processed Attempted: {orders_processed}")
        self.stdout.write(f"New Orders Created in DB: {orders_created}")
        self.stdout.write(f"Existing Orders Updated in DB: {orders_updated}")
        self.stdout.write(f"API Pages Fetched: {pages_fetched}")
        self.stdout.write(self.style.SUCCESS("-" * 30))

    def parse_datetime(self, date_string):
        """
        Safely parses a date string (expected to be ISO 8601 format, potentially GMT/UTC)
        into a timezone-aware datetime object (using UTC).
        Returns None if parsing fails or input is empty/None.
        """
        if not date_string:
            return None
        try:
            # dateutil.parser is good at handling various ISO 8601 formats
            dt = parser.parse(date_string)

            # Use Django's timezone utilities to check for naivety
            if is_naive(dt):
                # If parsed datetime is naive, assume it was UTC (common for *_gmt fields)
                # and make it timezone-aware using Django's make_aware.
                # timezone.utc comes from the 'from datetime import timezone' import.
                return make_aware(dt, timezone.utc)
            else:
                # If dateutil.parser already made it aware (e.g., string had '+00:00'),
                # return it directly. You might want to convert it to UTC if it could be
                # other timezones, although *_gmt fields should already be UTC.
                # Example: return dt.astimezone(timezone.utc)
                return dt # Assuming it's already UTC if it's aware

        except (ValueError, TypeError, parser.ParserError) as e:
            # Log the warning - using the logger is good practice
            logger.warning(f"Could not parse date string '{date_string}': {e}")
            # Optionally print to stderr as well if you want immediate console feedback
            # self.stderr.write(self.style.WARNING(f"Could not parse date string '{date_string}': {e}"))
            return None
# This is for product migrate 


# Instructions for running the command (as comments)
# ==================================================
# Ensure your Django project's virtual environment is activated.
# Navigate to your project's root directory (where manage.py is).

# To run the sync with default settings (50 orders per page, starting from page 1):
# python manage.py sync_old_wc_orders

# To specify the number of orders per page:
# python manage.py sync_old_wc_orders --per_page=25

# To fetch only a specific number of pages (e.g., the first 5):
# python manage.py sync_old_wc_orders --pages=5

# To start syncing from a specific page number (e.g., page 11):
# python manage.py sync_old_wc_orders --start_page=11

# To combine options:
# python manage.py sync_old_wc_orders --per_page=30 --start_page=5 --pages=10

# To filter by status (if you uncomment the argument):
# python manage.py sync_old_wc_orders --status=processing

# To filter by date (if you uncomment the argument):
# python manage.py sync_old_wc_orders --after_date=2024-01-01