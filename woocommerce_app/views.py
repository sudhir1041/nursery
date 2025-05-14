import json
import hashlib
import hmac
import base64
import logging
from django.http import JsonResponse 
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, Http404
from django.shortcuts import render,redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.utils.dateparse import parse_datetime,parse_date
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.template.loader import render_to_string # To potentially render form errors for AJAX
from django.contrib.auth.decorators import login_required # Optional: Secure the view
from .forms import OrderEditForm # Import the new form
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q
from django.contrib.auth.decorators import login_required


# Import the model and the API utility function
from .models import WooCommerceOrder
from .utils import fetch_order_from_woo # <-- Import the API fetch function

logger = logging.getLogger(__name__)

# --- Helper Functions ---
def _verify_webhook_signature(request):
    """Verifies the signature of the incoming webhook request. (Same as before)"""
    signature = request.headers.get('X-Wc-Webhook-Signature')
    secret = getattr(settings, 'WOOCOMMERCE_WEBHOOK_SECRET', None)
    print(signature)

    if not signature:
        logger.warning("Webhook verification failed: Missing 'X-Wc-Webhook-Signature' header.")
        return False
    if not secret:
        logger.error("Webhook verification failed: WOOCOMMERCE_WEBHOOK_SECRET not set in Django settings.")
        return False

    try:
        raw_body = request.body
        computed_hash = hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha256).digest()
        computed_signature = base64.b64encode(computed_hash).decode()
        if hmac.compare_digest(computed_signature, signature):
            return True
        else:
            logger.warning(f"Webhook signature mismatch. Received: {signature}, Computed: {computed_signature}")
            return False
    except Exception as e:
        logger.error(f"Error during webhook signature verification: {e}", exc_info=True)
        return False

def _parse_webhook_datetime(datetime_str):
    """Safely parses ISO 8601 datetime strings. (Same as before)"""
    if datetime_str:
        try:
            return parse_datetime(datetime_str)
        except ValueError:
            logger.warning(f"Could not parse datetime string: {datetime_str}")
    return None

def _process_order_data(order_data_dict):
    """
    Processes order data (received from API or webhook payload)
    and updates or creates a WooCommerceOrder model instance.
    (Slightly adapted to ensure it works with API response structure)
    """
    woo_id = order_data_dict.get('id')
    if not woo_id:
        logger.warning("Order data is missing the 'id'. Cannot process.")
        return None

    # Map payload data to your model fields
    billing_info = order_data_dict.get('billing', {})
    defaults = {
        'number': order_data_dict.get('number'),
        'status': order_data_dict.get('status'),
        'currency': order_data_dict.get('currency'),
        'total_amount': order_data_dict.get('total'),
        'customer_note': order_data_dict.get('customer_note'),
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
        # Use '_gmt' fields if available and prefer UTC, otherwise fallback
        'date_created_woo': _parse_webhook_datetime(order_data_dict.get('date_created_gmt') or order_data_dict.get('date_created')),
        'date_modified_woo': _parse_webhook_datetime(order_data_dict.get('date_modified_gmt') or order_data_dict.get('date_modified')),
        'date_paid_woo': _parse_webhook_datetime(order_data_dict.get('date_paid_gmt') or order_data_dict.get('date_paid')),
        'date_completed_woo': _parse_webhook_datetime(order_data_dict.get('date_completed_gmt') or order_data_dict.get('date_completed')),
        'line_items_json': order_data_dict.get('line_items', []),
        'shipping_lines_json': order_data_dict.get('shipping_lines', []),
        'raw_data': order_data_dict, # Store the fetched API data or payload
    }

    try:
        order_obj, created = WooCommerceOrder.objects.update_or_create(
            woo_id=woo_id,
            defaults=defaults
        )
        status_log = "Created" if created else "Updated"
        logger.info(f"{status_log} WooCommerceOrder object for woo_id={woo_id} using provided data.")
        return order_obj
    except Exception as e:
        logger.exception(f"Database error processing order ID {woo_id}: {e}")
        return None

# --- REVISED Webhook View ---

@csrf_exempt

def woocommerce_webhook_receiver(request):
    
    if not _verify_webhook_signature(request):
        logger.warning("Webhook received with invalid signature.")
        return HttpResponseForbidden("Invalid signature.")

    # 2. Parse Payload to get Order ID
    try:
        payload = json.loads(request.body)
        order_id = payload.get('id')
        # Log webhook details (topic helps understand the event)
        topic = request.headers.get('X-Wc-Webhook-Topic', 'unknown_topic')
        logger.info(f"Webhook received for topic '{topic}', order ID '{order_id}'. Verifying signature successful.")

        if not order_id:
            logger.warning("Webhook payload missing order 'id'. Cannot fetch details.")
            return HttpResponseBadRequest("Webhook payload missing order ID.")

    except json.JSONDecodeError:
        logger.error("Webhook received with invalid JSON payload.")
        return HttpResponseBadRequest("Invalid JSON payload.")
    except Exception as e:
        logger.error(f"Error reading webhook payload: {e}", exc_info=True)
        return HttpResponseBadRequest("Could not read payload.")

    # 3. Fetch Latest Order Data using REST API
    logger.info(f"Attempting to fetch full order details for ID {order_id} via REST API...")
    try:
        # Call the utility function which uses API Key/Secret
        latest_order_data = fetch_order_from_woo(order_id)

    except Exception as e:
        # Catch potential errors during API client initialization or the request itself
        logger.exception(f"Unhandled exception during API fetch for order {order_id}: {e}")
        # Decide response: 500 might cause retries, 200 acknowledges receipt but notes failure
        return HttpResponse(f"Server error fetching order details via API for order {order_id}.", status=500)

    # 4. Process the Fetched API Data
    if latest_order_data:
        logger.info(f"Successfully fetched API data for order {order_id}. Processing...")
        # Use the helper function to save the data obtained from the API
        order_obj = _process_order_data(latest_order_data)

        if order_obj:
            logger.info(f"Successfully processed and saved API data for order {order_id}.")
            # Return 200 OK to WooCommerce
            return HttpResponse("Webhook processed successfully using fetched API data.", status=200)
        else:
            # Error during database save, already logged by _process_order_data
            logger.error(f"Failed to save processed API data for order {order_id} to database.")
            # Return 500 to indicate server-side processing error after successful API fetch
            return HttpResponse(f"Error saving fetched order data for order {order_id}.", status=500)
    else:
        # fetch_order_from_woo returned None (error already logged within the function)
        logger.error(f"API fetch for order {order_id} failed or returned no data. Webhook cannot be fully processed.")
        # Decide response: 500 might cause retries, 200 acknowledges receipt but notes failure
        # Returning 500 is often preferred if you want WooCommerce to retry later when API might be back up.
        return HttpResponse(f"Failed to fetch order details via API for order {order_id}.", status=500)

# --- Frontend Views ---

@login_required
@require_GET # Use require_GET for views that only display data
def order_list_view(request):
    """
    Displays a paginated list of synchronized WooCommerce orders,
    with filtering and searching based on GET parameters,
    and adds a flag for highlighting overdue orders.
    """
    queryset = WooCommerceOrder.objects.all()

    # Get filter values from GET parameters
    date_filter_str = request.GET.get('date_filter', None)
    days_filter_str = request.GET.get('days_filter', None)
    not_shipped_filter_str = request.GET.get('not_shipped')
    search_query = request.GET.get('search_query', '').strip() # Get search query

    # --- Apply Filters (Date/Days) ---
    active_filter = False
    selected_date = None 
    if date_filter_str:
        selected_date = parse_date(date_filter_str)
        if selected_date:
            logger.debug(f"WC Filtering by specific date: {selected_date}")
            queryset = queryset.filter(date_created_woo__date=selected_date)
            if queryset.exists():
                active_filter = True
            else:
                queryset = WooCommerceOrder.objects.all()
                logger.warning(f"No orders found for date {selected_date}")
        else:
            logger.warning(f"WC Invalid date format received: {date_filter_str}")
            # Keep date_filter_str for context, but don't mark active_filter=True
    elif days_filter_str:
        try:
            num_days = int(days_filter_str)
            if num_days > 0:
                start_date = timezone.now() - timedelta(days=num_days)
                logger.debug(f"WC Filtering by last {num_days} days (since {start_date})")
                # Use __gte for "greater than or equal to" start_date (within the last num_days)
                filtered_queryset = queryset.filter(date_created_woo__gte=start_date)
                if filtered_queryset.exists():
                    queryset = filtered_queryset
                    active_filter = True
                else:
                    queryset = WooCommerceOrder.objects.all()
                    logger.warning(f"No orders found in last {num_days} days")
        except ValueError:
            logger.warning(f"WC Invalid days filter value received: {days_filter_str}")
            # Keep days_filter_str for context, but don't mark active_filter=True
    elif not_shipped_filter_str:
            not_shipped = ['processing', 'on-hold', 'partial-paid']
            two_days_ago = timezone.now() - timedelta(days=2)
            query_filter = Q(status__in=not_shipped) & Q(date_created_woo__lt=two_days_ago)
            filtered_queryset = queryset.filter(query_filter)
            if filtered_queryset.exists():
                queryset = filtered_queryset
                active_filter = True
            else:
                queryset = WooCommerceOrder.objects.all()
                logger.warning("No unshipped orders found")

    # --- Apply Search Filter ---
    if search_query:
        logger.debug(f"WC Applying search filter: '{search_query}'")
        # Prepare Q objects for OR query
        query_filter = Q(billing_email__icontains=search_query) | \
                       Q(billing_first_name__icontains=search_query) | \
                       Q(billing_last_name__icontains=search_query) | \
                       Q(billing_city__icontains=search_query) | \
                       Q(billing_postcode__icontains=search_query) | \
                       Q(billing_phone__icontains=search_query) | \
                       Q(status__icontains=search_query)

        # Check if search query might be an Order ID (integer)
        if search_query.isdigit():
            query_filter |= Q(woo_id=int(search_query))
            query_filter |= Q(number__icontains=search_query)
        
        filtered_queryset = queryset.filter(query_filter)
        if filtered_queryset.exists():
            queryset = filtered_queryset
            active_filter = True
        else:
            queryset = WooCommerceOrder.objects.all()
            logger.warning(f"No orders found matching search: {search_query}")

    # Apply ordering (Important: order *before* pagination)
    ordered_queryset = queryset.order_by('-date_created_woo', '-woo_id')

    # --- Pagination ---
    paginator = Paginator(ordered_queryset, 20) # Show 15 orders per page
    page_number = request.GET.get('page')
    try:
        orders = paginator.page(page_number)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        orders = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        orders = paginator.page(paginator.num_pages)

    # --- >>> Calculate Overdue Highlight Flag <<< ---
    now = timezone.now()
    two_days_ago = now - timedelta(days=2)

    for order in orders: # Iterate through the orders ON THE CURRENT PAGE
        # Set a default value first
        order.is_overdue_highlight = False
        try:
            # Check status and date validity before comparison
            if order.status and order.date_created_woo:
                is_overdue = (
                    order.status.lower() in ['processing', 'on-hold', 'partial-paid'] and
                    order.date_created_woo < two_days_ago
                    # ^^ IMPORTANT: Assumes date_created_woo is timezone-aware,
                    # matching timezone.now(). Adjust if it's naive.
                )
                order.is_overdue_highlight = is_overdue
        except AttributeError:
            # Log if expected attributes are missing on an order object
            logger.error(f"Order ID {getattr(order, 'woo_id', 'N/A')} missing 'status' or 'date_created_woo' attribute for overdue check.")
            order.is_overdue_highlight = False # Ensure flag is false if data is missing

    # --- Prepare Context ---
    context = {
        'orders': orders, # Pass the paginated orders (now with the flag) to the template
        'page_title': 'Synced WooCommerce Orders',
        # Pass current filter/search values back to maintain state in template forms/links
        'current_date_filter': date_filter_str if date_filter_str else '', # Pass back even if invalid format
        'current_days_filter': days_filter_str if days_filter_str else '', # Pass back even if invalid format
        'current_search_query': search_query,
        'active_filter': active_filter # Flag to maybe show a "clear filters" button
    }

    # Ensure template path matches your project structure
    template_name = 'woocommerce/order_list.html' # Or wherever your template lives
    return render(request, template_name, context)



@login_required
@require_GET
def order_detail_view(request, woo_id):
    """Displays the details of a single synchronized WooCommerce order."""
    # Fetch using the unique woo_id field
    try:
        # Ensure woo_id is treated as an integer
        order = get_object_or_404(WooCommerceOrder, woo_id=int(woo_id))
    except ValueError:
         raise Http404("Invalid Order ID format.")


    context = {
        'order': order,
        'page_title': f'Order Details #{order.number or order.woo_id}'
    }
    return render(request, 'woocommerce/order_detail.html', context)

@login_required 
def order_edit_view(request, woo_id):
    try:
        order = get_object_or_404(WooCommerceOrder, woo_id=int(woo_id))
    except ValueError:
        raise Http404("Invalid Order ID format.")

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST':
        form = OrderEditForm(request.POST, instance=order)
        if form.is_valid():
            try:
                # Get shipment status from form data
                shipment_status = request.POST.get('shipment_status')
                
                # Save form and update shipment status
                order = form.save(commit=False)
                order.shipment_status = shipment_status
                order.save()
                
                logger.info(f"Locally updated order {woo_id} via form with shipment status {shipment_status}.")

                if is_ajax:
                    return JsonResponse({
                        'status': 'success',
                        'message': 'Order updated successfully!',
                        'shipment_status': shipment_status
                    })
                else:
                    return redirect('order_detail', woo_id=order.woo_id)
            except Exception as e:
                 logger.exception(f"Error saving updated order {woo_id}: {e}")
                 error_message = "An error occurred while saving."
                 if is_ajax:
                     return JsonResponse({'status': 'error', 'message': error_message}, status=500)
                 else:
                     pass

        else:
            logger.warning(f"Order edit form invalid for order {woo_id}: {form.errors.as_json()}")
            if is_ajax:
                return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)

    else:
        form = OrderEditForm(instance=order)

    context = {
        'form': form,
        'order': order,
        'page_title': f'Edit Order #{order.number or order.woo_id}',
        'shipment_status': order.shipment_status
    }
    return render(request, 'woocommerce/order_edit.html', context)
