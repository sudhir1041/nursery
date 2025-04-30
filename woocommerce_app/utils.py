from woocommerce import API
from django.conf import settings
import logging

logger = logging.getLogger(__name__) # Use the logger configured in settings.py

def get_woocommerce_api_client():
    """Initializes and returns a WooCommerce API client instance."""
    required_settings = [
        settings.WOOCOMMERCE_STORE_URL,
        settings.WOOCOMMERCE_CONSUMER_KEY,
        settings.WOOCOMMERCE_CONSUMER_SECRET
    ]
    if not all(required_settings):
        logger.error("WooCommerce API settings (URL, Key, Secret) are not fully configured in Django settings.")
        raise ValueError("WooCommerce API settings missing in Django settings.")

    try:
        wcapi = API(
            url=settings.WOOCOMMERCE_STORE_URL,
            consumer_key=settings.WOOCOMMERCE_CONSUMER_KEY,
            consumer_secret=settings.WOOCOMMERCE_CONSUMER_SECRET,
            wp_api=True, # Usually required
            version="wc/v3", # Check WooCommerce REST API docs for the latest stable version
            timeout=20 # Increase timeout if needed
        )
        return wcapi
    except Exception as e:
        logger.exception(f"Failed to initialize WooCommerce API client: {e}")
        raise # Re-raise the exception to be handled upstream

def fetch_order_from_woo(order_id):
    """Fetches specific order details from the WooCommerce API."""
    logger.debug(f"Attempting to fetch order {order_id} from WooCommerce API.")
    try:
        wcapi = get_woocommerce_api_client()
        response = wcapi.get(f"orders/{order_id}")
        response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
        order_data = response.json()
        logger.info(f"Successfully fetched order {order_id} from WooCommerce API.")
        return order_data
    except Exception as e:
        # Log detailed error including the order_id
        logger.error(f"Failed to fetch order {order_id} from WooCommerce API: {e}", exc_info=True)
        return None # Return None to indicate failure

# fetch_orders_from_woo function (for the management command) can remain the same as before
def fetch_orders_from_woo(params=None):
    """
    Fetches orders from the WooCommerce API, potentially with pagination.
    Returns a tuple: (list_of_orders, total_pages, total_orders)
    """
    if params is None:
        params = {'per_page': 10, 'orderby': 'date', 'order': 'desc'}

    logger.debug(f"Attempting to fetch orders from WooCommerce API with params: {params}")
    try:
        wcapi = get_woocommerce_api_client()
        response = wcapi.get("orders", params=params)
        response.raise_for_status()
        total_pages = int(response.headers.get('X-WP-TotalPages', 0))
        total_orders = int(response.headers.get('X-WP-Total', 0))
        orders_data = response.json()
        logger.info(f"Successfully fetched {len(orders_data)} orders (page {params.get('page', 1)}) from WooCommerce API. Total Orders: {total_orders}, Total Pages: {total_pages}")
        return orders_data, total_pages, total_orders
    except Exception as e:
        logger.error(f"Failed to fetch orders from WooCommerce API with params {params}: {e}", exc_info=True)
        return [], 0, 0