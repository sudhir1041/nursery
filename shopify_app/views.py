import json
import logging

from django.conf import settings
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    Http404
)
from django.shortcuts import render,redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from datetime import timedelta
from django.utils import timezone
from django.contrib import messages
from django.utils.dateparse import parse_datetime,parse_date
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils import timezone
from django.views import View 
from django.utils.decorators import method_decorator 
from django.db.models import Q
from django.http import JsonResponse
from django.template.loader import render_to_string
from .forms import ShopifyOrderEditForm
from django.contrib.auth.decorators import login_required
from .forms import ShopifyOrderEditForm 
import logging

logger = logging.getLogger(__name__)

# Local Imports (from shopify_app)
from .models import ShopifyOrder
# --- Import helper functions from your utils.py ---
from .utils import verify_shopify_webhook, fetch_shopify_order

# --- Helper Functions ---

def _parse_iso_datetime(datetime_str):
    """Safely parses ISO 8601 datetime strings from Shopify."""
    if datetime_str:
        try:
            # parse_datetime handles ISO 8601 format including timezone offsets
            return parse_datetime(datetime_str)
        except (ValueError, TypeError):
            logger.warning(f"Could not parse datetime string from Shopify: {datetime_str}")
    return None

def _process_shopify_order_data(order_data_dict):
    """
    Processes Shopify order data (fetched from API) and updates or creates
    a ShopifyOrder model instance in the Django database.
    """
    shopify_id = order_data_dict.get('id')
    if not shopify_id:
        logger.warning("Shopify order data is missing the 'id'. Cannot process.")
        return None

    # Map Shopify API data to your model fields
    defaults = {
        'name': order_data_dict.get('name'),
        'email': order_data_dict.get('email'),
        'financial_status': order_data_dict.get('financial_status'),
        'fulfillment_status': order_data_dict.get('fulfillment_status'),
        'total_price': order_data_dict.get('total_price'),
        'currency': order_data_dict.get('currency'),
        # Store complex nested data as JSON
        'billing_address_json': order_data_dict.get('billing_address'),
        'shipping_address_json': order_data_dict.get('shipping_address'),
        'line_items_json': order_data_dict.get('line_items', []),
        # Parse timestamps
        'created_at_shopify': _parse_iso_datetime(order_data_dict.get('created_at')),
        'updated_at_shopify': _parse_iso_datetime(order_data_dict.get('updated_at')),
        # Store the full raw data for reference/debugging
        'raw_data': order_data_dict,
        # Set Django timestamp for modification
        'django_date_modified': timezone.now(),
    }
    # Remove None values from defaults to avoid accidentally clearing existing fields
    # if the API response didn't include them for some reason.
    defaults = {k: v for k, v in defaults.items() if v is not None}

    try:
        # Use update_or_create to handle both new and existing orders
        order_obj, created = ShopifyOrder.objects.update_or_create(
            shopify_id=shopify_id, # Match based on Shopify's unique ID
            defaults=defaults      # Apply the mapped data
        )
        status_log = "Created" if created else "Updated"
        # Set creation timestamp only if newly created
        # Note: update_or_create doesn't automatically update auto_now_add fields
        # on creation if using defaults. We set it manually if needed.
        # The model now uses default=timezone.now for django_date_created.

        logger.info(f"{status_log} ShopifyOrder object for shopify_id={shopify_id}.")
        return order_obj
    except Exception as e:
        # Log database errors specifically
        logger.exception(f"Database error processing Shopify order ID {shopify_id}: {e}")
        return None

# --- Shopify Webhook Receiver View ---

@csrf_exempt # Disable CSRF protection for incoming webhooks
@require_POST # Ensure only POST requests are accepted
def shopify_webhook_receiver(request):
    """
    Handles incoming webhooks from Shopify.
    1. Verifies the HMAC signature using the secret key.
    2. Parses the payload to get the resource ID.
    3. Fetches the latest resource data (e.g., Order) via the API.
    4. Processes and saves the fetched data to the local database.
    """
    # Step 1: Verify Signature (using the function imported from utils.py)
    if not verify_shopify_webhook(request):
        # Verification function already logs the specific failure reason (missing/mismatch)
        return HttpResponseForbidden("Invalid HMAC signature.") # Return 403 Forbidden

    # --- Signature is VALID, proceed ---
    logger.info("Shopify webhook signature verified successfully.")
    topic = request.headers.get('X-Shopify-Topic', 'unknown/topic')

    # Step 2: Parse Payload and Get Resource ID
    try:
        payload = json.loads(request.body)
        # Shopify ID is usually top-level 'id' for core resources
        # May need adjustment for other events (e.g., fulfillments use 'order_id')
        resource_id = payload.get('id') or payload.get('order_id')
        logger.info(f"Processing webhook for topic '{topic}', resource ID '{resource_id}'.")

        if not resource_id:
             logger.warning(f"Webhook payload for topic '{topic}' missing expected resource ID. Acknowledging receipt.")
             # Return 200 OK because signature was valid, but log we couldn't process fully.
             return HttpResponse(f"Webhook payload missing resource ID for topic {topic}.", status=200)

        # Step 3: Handle Specific Topics (Example: Orders)
        # Use startswith for broader matching (e.g., orders/create, orders/updated, etc.)
        if topic.startswith('orders/'):
            logger.info(f"Order-related topic detected. Fetching latest data for order ID {resource_id} via API...")
            # Step 3a: Fetch fresh data via API
            latest_order_data = fetch_shopify_order(resource_id) # Call API fetch function from utils

            # Step 3b: Process and Save API data
            if latest_order_data:
                order_obj = _process_shopify_order_data(latest_order_data)
                if order_obj:
                    # Success!
                    return HttpResponse("Webhook processed: Order data fetched via API and saved.", status=200)
                else:
                    # Error during database save (already logged)
                    return HttpResponse("Server error saving fetched order data.", status=500) # Internal error
            else:
                # API fetch failed (already logged by fetch_shopify_order)
                logger.error(f"API fetch failed for Shopify order {resource_id}. Webhook partially processed.")
                # Return 500 to encourage Shopify retry if API failure might be temporary
                return HttpResponse("Webhook received, but failed to fetch full order details via API.", status=500)
        else:
            # Handle other topics if needed, or just acknowledge them
            logger.info(f"Ignoring non-order topic: {topic}")
            return HttpResponse(f"Webhook received and verified for ignored topic: {topic}", status=200)

    except json.JSONDecodeError:
        logger.error("Invalid JSON received in Shopify webhook body.")
        return HttpResponseBadRequest("Invalid JSON payload.")
    except Exception as e:
        logger.exception(f"Unexpected error processing Shopify webhook (topic: {topic}): {e}")
        # Return 500 for unexpected server errors during processing
        return HttpResponse("Internal server error processing webhook.", status=500)


# --- Basic Frontend Views ---
@login_required
@require_GET
def shopify_order_list_view(request):
    """
    Displays a paginated list of synchronized Shopify orders,
    with filtering, searching, and overdue highlighting based on fulfillment status.
    """
    queryset = ShopifyOrder.objects.all()

    # Get filter values from GET parameters
    date_filter_str = request.GET.get('date_filter', None)
    days_filter_str = request.GET.get('days_filter', None)
    not_shipped_filter_str = request.GET.get('not_shipped', None)
    search_query = request.GET.get('search_query', '').strip() # Get search query and strip whitespace

    # --- Apply Filters (Date/Days) ---
    # Prioritize specific date filter if provided
    active_filter = False 
    selected_date = None 
    if date_filter_str:
        selected_date = parse_date(date_filter_str)
        if selected_date:
            logger.debug(f"Shopify Filtering by specific date: {selected_date}")
            # Convert selected_date to datetime range for that full day
            start_datetime = timezone.make_aware(timezone.datetime.combine(selected_date, timezone.datetime.min.time()))
            end_datetime = timezone.make_aware(timezone.datetime.combine(selected_date, timezone.datetime.max.time()))
            queryset = queryset.filter(created_at_shopify__range=(start_datetime, end_datetime))
            active_filter = True
        else:
            logger.warning(f"Shopify Invalid date format received: {date_filter_str}")
            # Keep date_filter_str for context, but don't mark active_filter=True
    elif days_filter_str:
        try:
            num_days = int(days_filter_str)
            if num_days > 0:
                start_date = timezone.now() - timedelta(days=num_days)
                logger.debug(f"Shopify Filtering by last {num_days} days (since {start_date})")
                queryset = queryset.filter(created_at_shopify__gte=start_date)
                active_filter = True
        except ValueError:
            logger.warning(f"Shopify Invalid days filter value received: {days_filter_str}")
            # Keep days_filter_str for context, but don't mark active_filter=True
    elif not_shipped_filter_str:
        not_shipped = ['unfulfilled', 'partially_fulfilled', 'scheduled', 'on_hold','null']
        two_days_ago = timezone.now() - timedelta(days=2)
        query_filter = Q(fulfillment_status__in=not_shipped) & Q(created_at_shopify__lt=two_days_ago)
        queryset = queryset.filter(query_filter)
        active_filter = True

    # --- Apply Search Filter (in addition to date/days filters) ---
    if search_query:
        logger.debug(f"Shopify Applying search filter: '{search_query}'")
        # Use Q objects for OR query on various fields 
        # Use icontains for case-insensitive containment search
        query_filter = (
            Q(email__icontains=search_query) |
            Q(name__icontains=search_query) | # 'name' is like #1001
            Q(financial_status__icontains=search_query) |
            Q(fulfillment_status__icontains=search_query) |
            # Assuming billing_address_json is a JSONField and you want to search within it
            Q(billing_address_json__phone__icontains=search_query) |
            Q(billing_address_json__city__icontains=search_query) |
            Q(billing_address_json__zip__icontains=search_query)
        )
        queryset = queryset.filter(query_filter)
        active_filter = True # Search counts as an active filter
    ordered_queryset = queryset.order_by('-created_at_shopify', '-shopify_id')

    # --- Pagination ---
    paginator = Paginator(ordered_queryset, 15) # Show 15 orders per page
    page_number = request.GET.get('page')
    try:
        orders = paginator.page(page_number)
    except PageNotAnInteger:
        orders = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        orders = paginator.page(paginator.num_pages)

    # --- >>> Calculate Overdue Highlight Flag for Shopify <<< ---
    now = timezone.now()
    two_days_ago = now - timedelta(days=2)
    # Define which fulfillment statuses indicate the order needs action
    actionable_fulfillment_statuses = ['unfulfilled', 'partially_fulfilled', 'scheduled', 'on_hold']

    for order in orders: # Iterate through the orders ON THE CURRENT PAGE
        # Set a default value first
        order.is_overdue_highlight = False
        try:
            # Check if required fields exist and date is valid before processing
            if hasattr(order, 'fulfillment_status') and hasattr(order, 'created_at_shopify') and order.created_at_shopify:

                # Check if fulfillment status indicates action needed
                # Handles None status and checks against the list (case-insensitive)
                current_status = order.fulfillment_status
                needs_action = (
                    current_status is None or
                    (isinstance(current_status, str) and
                     current_status.lower() in actionable_fulfillment_statuses)
                )

                # Check if it's older than 3 days
                is_old = order.created_at_shopify < two_days_ago
                # matching timezone.now(). Adjust if it's naive.

                # Highlight if both conditions are met
                if needs_action and is_old:
                    order.is_overdue_highlight = True

        except Exception as e:
            # Log unexpected errors during highlight calculation for a specific order
            shopify_order_id = getattr(order, 'shopify_id', getattr(order, 'id', 'N/A')) # Get ID safely
            logger.error(f"Error calculating highlight for Shopify Order ID {shopify_order_id}: {e}", exc_info=True)
            order.is_overdue_highlight = False 

    # --- Prepare Context ---
    context = {
        'orders': orders, 
        'page_title': 'Synced Shopify Orders',
        # Pass current filter/search values back to keep forms populated/indicate current view
        'current_date_filter': date_filter_str if date_filter_str else '',
        'current_days_filter': days_filter_str if days_filter_str else '',
        'current_search_query': search_query,
        'active_filter': active_filter, 
    }

    # Ensure this template path matches your project structure
    template_name = 'shopify/order_list.html'
    return render(request, template_name, context)


@login_required
@require_GET
def shopify_order_detail_view(request, shopify_id):
    """Displays the details of a single synchronized Shopify order from local DB."""
    try:
        # Ensure shopify_id is treated as an integer for the lookup
        order = get_object_or_404(ShopifyOrder, shopify_id=int(shopify_id))
    except ValueError:
        # Handle cases where shopify_id is not a valid integer
        raise Http404("Invalid Shopify Order ID format. Must be numeric.")

    context = {
        'order': order,
        'page_title': f'Shopify Order {order.name or f"#{order.shopify_id}"}'
    }
    # Make sure template path matches your structure
    return render(request, 'shopify/order_detail.html', context)

@login_required 
def shopify_order_edit_view(request, shopify_id):
    """
    Handles displaying and processing the edit form for a specific ShopifyOrder.
    Supports standard POST and AJAX POST submissions.
    """
    try:
        # Use shopify_id for lookup
        order = get_object_or_404(ShopifyOrder, shopify_id=int(shopify_id))
    except ValueError:
        raise Http404("Invalid Shopify Order ID format.")

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST':
        # Populate form with POST data and the existing order instance
        form = ShopifyOrderEditForm(request.POST, instance=order)
        if form.is_valid():
            try:
                form.save() 
                logger.info(f"Locally updated Shopify order {shopify_id} via form.")

                if is_ajax:
                    # Return JSON success response for AJAX request
                    return JsonResponse({
                        'status': 'success',
                        'message': 'Shopify order updated successfully!',
                        # Optionally include updated data if JS needs it
                        'internal_notes': order.internal_notes,
                        })
                else:
                    # Standard POST: Redirect to detail view after saving
                    return redirect('shopify_order_detail', shopify_id=order.shopify_id)
            except Exception as e:
                 logger.exception(f"Error saving updated Shopify order {shopify_id}: {e}")
                 error_message = "An error occurred while saving the order."
                 if is_ajax:
                     return JsonResponse({'status': 'error', 'message': error_message}, status=500)
                 else:
                     # Handle non-AJAX error (e.g., add message to context)
                     # For now, just fall through to re-render the form with general error
                     messagesDiv.innerHTML = f'<div class="alert alert-danger">{error_message}</div>' # This won't work directly, need context processor or Django messages framework

        else: 
            logger.warning(f"Shopify order edit form invalid for {shopify_id}: {form.errors.as_json()}")
            if is_ajax:
                # Return validation errors as JSON for AJAX request
                return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
            # else: Non-AJAX POST with invalid form: Let it fall through to re-render form below

    else: # GET request
        # Create form instance populated with the order's current data
        form = ShopifyOrderEditForm(instance=order)

    context = {
        'form': form,
        'order': order, # Pass order object for reference in template (e.g., title)
        'page_title': f'Edit Shopify Order {order.name or f"#{order.shopify_id}"}'
    }
    # Render the edit page template for GET requests or non-AJAX POST errors
    return render(request, 'shopify/order_edit.html', context)
