import requests
import time
import logging
import hmac # For webhook verification
import hashlib # For webhook verification
import base64 # For webhook verification
from django.conf import settings
from urllib.parse import urljoin

# Use the logger configured for 'shopify_app' in settings.py
logger = logging.getLogger(__name__)

def get_shopify_api_base_url():
    """Constructs the base URL for Shopify API requests."""
    domain = getattr(settings, 'SHOPIFY_STORE_DOMAIN', None)
    api_version = getattr(settings, 'SHOPIFY_API_VERSION', None)
    if not domain or not api_version:
        logger.error("Shopify domain or API version not configured in settings.")
        raise ValueError("Shopify domain and API version must be set.")
    # Ensure domain doesn't have https:// prefix already
    domain = domain.replace('https://', '').replace('http://', '')
    return f"https://{domain}/admin/api/{api_version}/"

def get_shopify_api_headers():
    """Returns the necessary headers for Shopify API requests."""
    token = getattr(settings, 'SHOPIFY_ADMIN_ACCESS_TOKEN', None)
    if not token:
        logger.error("Shopify Admin Access Token not configured in settings.")
        raise ValueError("Shopify Admin Access Token must be set.")
    return {
        "Content-Type": "application/json",
        "Accept": "application/json", # Good practice to include Accept header
        "X-Shopify-Access-Token": token,
    }

def make_shopify_request(method, endpoint, params=None, json_data=None, retries=3, base_delay=1):
    """
    Makes a generic request to the Shopify API with enhanced logging,
    error handling, and retries for rate limiting.
    """
    try:
        base_url = get_shopify_api_base_url()
        headers = get_shopify_api_headers()
    except ValueError as config_err:
        # Log config errors and re-raise immediately
        logger.error(f"Configuration error preventing Shopify API call: {config_err}")
        raise

    # Ensure endpoint doesn't start with / if base_url ends with /
    url = urljoin(base_url, endpoint.lstrip('/'))

    # Mask token for logging security
    logged_headers = headers.copy()
    if 'X-Shopify-Access-Token' in logged_headers:
        token_len = len(logged_headers['X-Shopify-Access-Token'])
        logged_headers['X-Shopify-Access-Token'] = f"shpat_{'*' * (token_len - 6)}"

    logger.debug(f"Attempting Shopify API Request: {method.upper()} {url}")
    logger.debug(f"Params: {params}, JSON Data: {json_data}, Headers: {logged_headers}")

    for attempt in range(retries):
        try:
            response = requests.request(
                method.upper(), 
                url,
                headers=headers,
                params=params,
                json=json_data,
                timeout=30 
            )

            logger.debug(f"Shopify API Response Status: {response.status_code} for {method.upper()} {url}")

            # Check for rate limiting (429 Too Many Requests)
            if response.status_code == 429:
                # Exponential backoff based on Shopify's suggestion or calculated delay
                retry_after = int(response.headers.get('Retry-After', base_delay * (2 ** attempt)))
                logger.warning(f"Rate limit hit for {method.upper()} {url}. Retrying after {retry_after}s (Attempt {attempt + 1}/{retries}).")
                time.sleep(retry_after)
                continue 
            # Raise HTTPError for other bad responses (4xx client errors, 5xx server errors)
            response.raise_for_status()

            # Handle successful requests with no content (e.g., 204 No Content for DELETE)
            if not response.content or response.status_code == 204:
                logger.info(f"Shopify API request successful ({method.upper()} {url}), response body is empty (Status: {response.status_code}).")
                return None

            # Try to parse JSON for successful responses with content
            try:
                response_json = response.json()
                # logger.debug(f"Response JSON: {response_json}") # Can be very verbose, uncomment if needed
                return response_json
            except requests.exceptions.JSONDecodeError:
                logger.error(f"Failed to decode JSON response for {method.upper()} {url}. Status: {response.status_code}. Response Text: {response.text[:500]}...")
                # Treat JSON decode error as a failure for this attempt
                raise ValueError("Failed to decode Shopify API JSON response") # Raise a specific error perhaps

        except requests.exceptions.HTTPError as http_err:
            # Log specific HTTP errors (like 401 Unauthorized, 403 Forbidden, 404 Not Found)
            logger.error(f"HTTP Error during Shopify API request ({method.upper()} {url}): {http_err.response.status_code} {http_err.response.reason}")
            try:
                error_details = http_err.response.json()
                logger.error(f"Shopify Error Details: {error_details}")
            except requests.exceptions.JSONDecodeError:
                logger.error(f"Could not parse error response body: {http_err.response.text[:500]}...")
            # Decide if retry is appropriate based on status code?
            # Generally retry on 429, maybe 5xx, but not usually 401/403/404
            if response.status_code not in [429]: # Only retry handled above
                 if attempt == retries - 1: raise http_err # Re-raise if last attempt
                 # Optional: only retry certain non-429 errors like timeouts/5xx

        except requests.exceptions.RequestException as e:
            # Log other request errors (connection, timeout, etc.)
            logger.error(f"General RequestException during Shopify API request ({method.upper()} {url}): {e}", exc_info=True)
            if attempt == retries - 1: raise e # Re-raise if last attempt

        # Wait before retrying after an error (if loop continues)
        wait_time = base_delay * (2 ** attempt)
        logger.info(f"Waiting {wait_time}s before retry {attempt + 2}...")
        time.sleep(wait_time)

    # This part is reached if all retries fail for retryable errors
    logger.error(f"Shopify API request ultimately failed after {retries} attempts ({method.upper()} {url}).")
    return None # Indicate failure after all retries

# --- Specific API Fetch Functions ---

def fetch_shopify_order(order_id):
    """Fetches a specific order by its Shopify ID."""
    logger.debug(f"Util: Attempting to fetch Shopify order {order_id} via API.")
    endpoint = f"orders/{order_id}.json"
    try:
        # Optionally add 'fields' param to limit data:
        # params = {'fields': 'id,name,email,financial_status,total_price,created_at'}
        order_response = make_shopify_request("GET", endpoint) #, params=params)
        # Check if response is not None and contains the 'order' key
        if order_response and isinstance(order_response, dict) and 'order' in order_response:
             logger.info(f"Util: Successfully fetched Shopify order {order_id}.")
             return order_response['order'] # Return the nested order dictionary
        else:
             logger.warning(f"Util: No 'order' key found or empty/invalid response for order {order_id}. Response: {order_response}")
             return None
    except Exception as e:
        # Error should have been logged by make_shopify_request
        logger.error(f"Util: Fetch failed for Shopify order {order_id}.")
        return None

def fetch_shopify_orders(params=None):
    """
    Fetches a list of orders from Shopify. Uses basic limit/status filter.
    NOTE: Consider implementing cursor-based pagination for production use.
    """
    # Default parameters if none provided
    if params is None:
        params = {'limit': 50, 'order': 'updated_at desc', 'status': 'any'}

    logger.debug(f"Util: Attempting to fetch Shopify orders with params: {params}")
    endpoint = "orders.json"
    try:
        response_data = make_shopify_request("GET", endpoint, params=params)
        # Check if response is not None and contains the 'orders' key which should be a list
        if response_data and isinstance(response_data, dict) and 'orders' in response_data and isinstance(response_data['orders'], list):
            order_list = response_data['orders']
            logger.info(f"Util: Successfully fetched {len(order_list)} Shopify orders.")
            return order_list
        else:
            logger.warning(f"Util: No 'orders' key found or invalid response when fetching orders. Params: {params}. Response: {response_data}")
            return [] # Return empty list on failure or unexpected format
    except Exception as e:
         logger.error(f"Util: Failed to fetch Shopify orders list.")
         return []

# --- Webhook Verification Function ---

def verify_shopify_webhook(request):
    """
    Verifies the HMAC-SHA256 signature of an incoming Shopify webhook request
    using the SHOPIFY_WEBHOOK_SECRET from Django settings.
    """
    # Get the secret key (should be the Shopify App's API Secret Key)
    secret = getattr(settings, 'SHOPIFY_WEBHOOK_SECRET', None)
    if not secret:
        logger.error("SHOPIFY_WEBHOOK_SECRET not set in settings. Cannot verify webhook.")
        return False

    # Get the HMAC header sent by Shopify
    shopify_hmac = request.headers.get('X-Shopify-Hmac-Sha256')
    if not shopify_hmac:
        logger.warning("Webhook verification failed: Missing 'X-Shopify-Hmac-Sha256' header.")
        return False

    try:
        # Use the raw request body bytes directly
        raw_body = request.body

        # Calculate the expected signature
        calculated_hmac = hmac.new(
            secret.encode('utf-8'), # Secret needs to be bytes
            raw_body,               # Body is already bytes
            hashlib.sha256
        ).digest()                  # Get digest as bytes

        # Encode the digest to Base64 and then decode to a string for comparison
        calculated_hmac_b64 = base64.b64encode(calculated_hmac).decode('utf-8')

        # Use hmac.compare_digest for secure comparison against timing attacks
        is_valid = hmac.compare_digest(calculated_hmac_b64, shopify_hmac)

        if not is_valid:
            # Log detailed mismatch info only if validation fails
            logger.warning(f"Shopify webhook signature mismatch.")
            logger.warning(f"Received: {shopify_hmac}")
            logger.warning(f"Computed: {calculated_hmac_b64}")
            # Log whether secret was found, but not the secret itself
            logger.warning(f"Secret used for check: {'Found' if secret else 'NOT FOUND'}")
            # You could add body logging here too if mismatch persists
            # logger.debug(f"Body length: {len(raw_body)}, First 100 bytes: {raw_body[:100]}")

        return is_valid

    except Exception as e:
        logger.error(f"Error during Shopify webhook signature verification: {e}", exc_info=True)
        return False