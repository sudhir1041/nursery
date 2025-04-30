import logging
import time
from dateutil import parser # For robust date string parsing
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import make_aware, is_naive # For date parsing helper
from datetime import timezone # For date parsing helper

# --- Adjust 'shopify_app' if your app name is different ---
try:
    from shopify_app.models import ShopifyOrder
    from shopify_app.utils import fetch_shopify_orders # Use the Shopify util
except ImportError:
    print("ERROR: Could not import ShopifyOrder or fetch_shopify_orders.")
    print("Please ensure:")
    print("1. 'shopify_app' is the correct name of your Django app containing models.py and utils.py.")
    print("2. Your virtual environment is activated.")
    print("3. The necessary files (models.py, utils.py) exist in the specified app.")
    # Define dummy classes/functions for basic parsing if needed
    class ShopifyOrder: pass
    def fetch_shopify_orders(*args, **kwargs): return []
    print("WARNING: Using dummy definitions for ShopifyOrder and fetch_shopify_orders.")

logger = logging.getLogger(__name__) # Uses Django's logging setup

class Command(BaseCommand):
    """
    Django management command to sync historical orders from the Shopify REST API
    to the local database using since_id pagination.
    """
    help = 'Syncs historical orders from Shopify REST API to the local database.'

    def add_arguments(self, parser):
        """Adds command-line arguments for controlling the sync process."""
        parser.add_argument(
            '--limit',
            type=int,
            default=50, # Shopify default is 50, max is 250
            help='Number of orders to fetch per API request (default: 50, max: 250).',
        )
        parser.add_argument(
            '--start_id',
            type=int,
            default=0,
            help='Shopify Order ID to start fetching *after* (default: 0, fetches from the beginning).',
        )
        parser.add_argument(
            '--max_batches',
            type=int,
            help='Maximum number of API request batches to fetch (optional).',
        )
        parser.add_argument(
            '--status',
            type=str,
            default='any',
            help='Filter orders by status (open, closed, cancelled, any - default: any).',
        )
        parser.add_argument(
            '--financial_status',
            type=str,
            default='any',
            help='Filter orders by financial status (e.g., paid, pending, refunded, any - default: any).',
        )
        # Add more filters as needed (e.g., created_at_min/max, fulfillment_status)
        # parser.add_argument('--created_at_min', type=str, help='Fetch orders created after this ISO date (YYYY-MM-DDTHH:MM:SSZ)')

    def handle(self, *args, **options):
        """The main execution logic of the command."""
        self.stdout.write(self.style.SUCCESS("Starting historical Shopify order sync..."))

        # --- Parameters & Counters ---
        limit = options['limit']
        if not 1 <= limit <= 250:
            self.stderr.write(self.style.ERROR("Invalid limit. Must be between 1 and 250."))
            return
        current_since_id = options['start_id']
        max_batches = options['max_batches']
        status_filter = options['status']
        financial_status_filter = options['financial_status']
        # Add other filters here

        batches_fetched = 0
        orders_processed = 0
        orders_created = 0
        orders_updated = 0

        # --- Main Sync Loop (using since_id) ---
        while True:
            # Check batch limit if set
            if max_batches is not None and batches_fetched >= max_batches:
                self.stdout.write(f"Reached specified batch limit ({max_batches}). Stopping.")
                break

            self.stdout.write(f"Fetching batch {batches_fetched + 1} (Limit: {limit}, Since ID: {current_since_id})...")

            # --- Prepare API Parameters ---
            params = {
                'limit': limit,
                'since_id': current_since_id,
                'status': status_filter,
                'financial_status': financial_status_filter,
                'order': 'id asc', # Crucial for since_id pagination
                # Add other optional parameters based on args
                # 'fields': 'id,name,email,...' # To fetch only specific fields
            }
            # Example: Add created_at_min if provided
            # if options.get('created_at_min'):
            #     params['created_at_min'] = options['created_at_min']

            # --- API Call ---
            try:
                # Use the utility function to fetch orders (it handles retries/errors)
                orders_data = fetch_shopify_orders(params=params) # Expects a list of orders
                # fetch_shopify_orders should return [] on error/no data
                if orders_data is None: # Should not happen if util returns [] on error
                    self.stderr.write(self.style.ERROR(f"API fetch returned None for batch {batches_fetched + 1}. Stopping."))
                    break
                elif not isinstance(orders_data, list):
                     self.stderr.write(self.style.ERROR(f"API fetch did not return a list for batch {batches_fetched + 1}. Got: {type(orders_data)}. Stopping."))
                     break

                self.stdout.write(self.style.SUCCESS(f"Fetched {len(orders_data)} orders in this batch."))

            except Exception as e:
                # Although util should handle errors, catch unexpected issues here
                self.stderr.write(self.style.ERROR(f"Unexpected error during API call for batch {batches_fetched + 1}: {e}"))
                break # Stop the sync on unexpected errors

            # --- Exit Condition ---
            if not orders_data:
                self.stdout.write("No more orders found matching criteria. Sync complete.")
                break # Exit loop if no orders are returned in the batch

            last_order_id_in_batch = 0 # Track the last ID for the next 'since_id'

            # --- Process Fetched Orders ---
            for order_data in orders_data:
                orders_processed += 1
                shopify_id = order_data.get('id')

                if not shopify_id:
                    self.stderr.write(self.style.ERROR("Skipping order data with missing Shopify ID."))
                    continue

                # Keep track of the highest ID encountered in this batch
                last_order_id_in_batch = max(last_order_id_in_batch, shopify_id)

                try:
                    # Use atomic transaction for each order
                    with transaction.atomic():
                        # Prepare data for the ShopifyOrder model fields
                        defaults = {
                            'name': order_data.get('name'), # e.g., #1001
                            'email': order_data.get('email'),
                            'financial_status': order_data.get('financial_status'),
                            'fulfillment_status': order_data.get('fulfillment_status'), # Map directly
                            'total_price': order_data.get('total_price'),
                            'currency': order_data.get('currency'),

                            # JSON Fields - Store the relevant structures directly
                            'billing_address_json': order_data.get('billing_address'),
                            'shipping_address_json': order_data.get('shipping_address'),
                            'line_items_json': order_data.get('line_items', []),

                            # NOTE: shipment_status - Leave to default 'pending' or add custom logic
                            # based on fulfillment_status or fulfillment data if needed.
                            # 'shipment_status': self.determine_shipment_status(order_data),

                            # NOTE: tracking_details_json requires parsing 'fulfillments' array
                            # which might not be fully included by default or requires another API call.
                            # Leave as null for basic sync.
                            'tracking_details_json': order_data.get('fulfillments'), # Store fulfillments if present

                            # NOTE: internal_notes is not from Shopify, leave blank/null.
                            # 'internal_notes': '',

                            # Timestamps (Parse safely using helper) - Use Shopify's timestamps
                            'created_at_shopify': self.parse_datetime(order_data.get('created_at')),
                            'updated_at_shopify': self.parse_datetime(order_data.get('updated_at')),
                            'closed_at_shopify': self.parse_datetime(order_data.get('closed_at')), # Note: 'closed_at' field name

                            # Store the raw payload
                            'raw_data': order_data,
                        }

                        # Remove None values ONLY if your model fields explicitly forbid null=True
                        # Be careful, as setting blank=True, null=True (common) means None is okay.
                        # defaults = {k: v for k, v in defaults.items() if v is not None}

                        # --- Database Operation ---
                        order_obj, created = ShopifyOrder.objects.update_or_create(
                            shopify_id=shopify_id, # Unique key
                            defaults=defaults      # Fields to update/create
                        )

                        if created:
                            orders_created += 1
                            # Verbose logging:
                            # self.stdout.write(f"CREATED Order: Shopify ID {shopify_id} -> DB ID {order_obj.id}")
                        else:
                            orders_updated += 1
                            # Verbose logging:
                            # self.stdout.write(f"UPDATED Order: Shopify ID {shopify_id} -> DB ID {order_obj.id}")

                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"Failed to process or save Shopify order ID {shopify_id}: {e}"))
                    logger.error(f"Error processing Shopify order ID {shopify_id}. Data snippet: {str(order_data)[:500]}", exc_info=True)
                    # Continue with the next order in the batch
                    continue

            # --- Prepare for Next Iteration ---
            # Update since_id to the ID of the last successfully processed order in this batch
            current_since_id = last_order_id_in_batch
            batches_fetched += 1

            # Optional: Add delay between batches if hitting secondary rate limits
            # time.sleep(0.5) # Shopify's bucket refills at 2/sec (plus burst)

        # --- Final Summary ---
        self.stdout.write(self.style.SUCCESS("-" * 30))
        self.stdout.write(self.style.SUCCESS("Shopify Sync finished!"))
        self.stdout.write(f"Total Orders Processed Attempted: {orders_processed}")
        self.stdout.write(f"New Orders Created in DB: {orders_created}")
        self.stdout.write(f"Existing Orders Updated in DB: {orders_updated}")
        self.stdout.write(f"API Batches Fetched: {batches_fetched}")
        self.stdout.write(self.style.SUCCESS("-" * 30))


    def parse_datetime(self, date_string):
        """
        Safely parses an ISO 8601 date string (used by Shopify) into a
        timezone-aware datetime object (using UTC).
        Returns None if parsing fails or input is empty/None.
        """
        if not date_string:
            return None
        try:
            # dateutil.parser handles ISO 8601 format well, including timezones
            dt = parser.parse(date_string)

            # Ensure it's timezone-aware. If parser didn't make it aware (unlikely for ISO 8601),
            # make it UTC. If it is aware, convert it to UTC for consistency.
            if is_naive(dt):
                logger.warning(f"Parsed date '{date_string}' as naive, assuming UTC.")
                return make_aware(dt, timezone.utc)
            else:
                # Convert to UTC if it's not already (e.g., if offset was -04:00)
                return dt.astimezone(timezone.utc)

        except (ValueError, TypeError, parser.ParserError) as e:
            logger.warning(f"Could not parse date string '{date_string}': {e}")
            return None

# Instructions for running the command
# =====================================
# Ensure your Django project's virtual environment is activated.
# Navigate to your project's root directory (where manage.py is).

# To run the sync with default settings (50 orders/batch, from beginning):
# python manage.py sync_old_shopify_orders

# To specify the number of orders per batch (limit):
# python manage.py sync_old_shopify_orders --limit=100

# To start syncing orders CREATED AFTER a specific order ID:
# python manage.py sync_old_shopify_orders --start_id=1234567890

# To limit the number of batches fetched (e.g., fetch 10 batches):
# python manage.py sync_old_shopify_orders --max_batches=10

# To filter by status:
# python manage.py sync_old_shopify_orders --status=open --financial_status=paid

# Combine options:
# python manage.py sync_old_shopify_orders --limit=250 --start_id=1234567890 --status=closed