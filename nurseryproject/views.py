from django.shortcuts import render,redirect
from facebook_app.models import Facebook_orders
from shopify_app.models import ShopifyOrder
from woocommerce_app.models import WooCommerceOrder
from operator import itemgetter
from django.db.models import Q
from datetime import datetime, timedelta
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import logging
from django.utils import timezone
from django.utils.dateparse import parse_datetime,parse_date
logger = logging.getLogger(__name__)

@login_required
def dashboard_view(request):
    """
    Calculates and displays dashboard statistics for orders across platforms,
    categorizing by pending/processing vs. other statuses based on primary status fields.
    Shows data for last 30 days only.
    """
    # Calculate date 30 days ago from now
    thirty_days_ago = timezone.now() - timedelta(days=30)

    # Get querysets for all platforms filtered by last 30 days
    woo_orders = WooCommerceOrder.objects.filter(date_created_woo__gte=thirty_days_ago)
    shopify_orders = ShopifyOrder.objects.filter(created_at_shopify__gte=thirty_days_ago)
    fb_orders = Facebook_orders.objects.filter(date_created__gte=thirty_days_ago)

    # --- Calculate Total Counts ---
    woo_total = woo_orders.count()
    shopify_total = shopify_orders.count()
    fb_total = fb_orders.count()
    total_orders = woo_total + shopify_total + fb_total

    # --- Calculate "Pending Action" Counts ---
    # Based on statuses indicating the order likely needs processing or fulfillment work.

    # WooCommerce: Pending orders
    woo_pending_orders = woo_orders.filter(
        status__in=['pending', 'cancelled','failed',]
    ).count()
    # WooCommerce: Processing status, on hold, partial paid
    woo_not_shipped = woo_orders.filter(
        status__in=['processing', 'on-hold', 'partial-paid']
    ).count()

    # Shopify: Pending Orders (based on financial status)
    shopify_pending_orders = shopify_orders.filter(
        financial_status__in=['pending', 'authorized', 'partially_paid']
    ).count()

    shopify_not_shipped_orders = shopify_orders.filter(
        Q(fulfillment_status=None) |
        Q(fulfillment_status__in=['unfulfilled', 'partially_fulfilled', 'scheduled', 'on_hold'])
    ).count()


    # Facebook: Pending, Processing, or On Hold status
    fb_pending_orders = fb_orders.filter(
        status='pending'
    ).count()

    fb_not_shipped = fb_orders.filter(
        status__in=['processing', 'on-hold']
    ).count()

    total_pending_orders = woo_pending_orders + shopify_pending_orders + fb_pending_orders
    total_not_shipped = woo_not_shipped + shopify_not_shipped_orders + fb_not_shipped

    # --- Calculate "Other Status" Counts ---
    # These are orders in shipped/completed/delivered states
    woo_shipped_orders = woo_orders.filter(
        status__in=['completed', 'delivered', 'refunded',  'rto', 'lost', 'pickup-pending','not-picked', 'out-for-pickup', 'picked', 'dispatched', 'in-transit', 'on-process', 'ndr', 'rts', 'rto-pending', 'rto-dispatched', 'rto-in-transit']
    ).count()
    
    shopify_shipped_orders = shopify_orders.filter(
        fulfillment_status__in=['fulfilled', 'complete', 'shipped']
    ).count()
    
    fb_shipped_orders = fb_orders.filter(
        status__in=['completed', 'shipped', 'delivered']
    ).count()
    
    total_shipment_status = woo_shipped_orders + shopify_shipped_orders + fb_shipped_orders

    # --- Prepare Context ---
    # Using more descriptive names for clarity in the template
    context = {
        'project_name': 'Nursery Nisarga Dashboard',

        # Overall totals
        'total_orders': total_orders,
        'total_pending_orders': total_pending_orders, 
        'total_shipment_status_orders': total_shipment_status,
        'total_not_shipped': total_not_shipped,
        

        # WooCommerce specific
        'woo_orders': woo_total,
        'woo_pending_orders': woo_pending_orders,
        'woo_shipped_orders': woo_shipped_orders,
        'woo_not_shipped':woo_not_shipped,
        # 'woo_not_count_status_orders': woo_not_count,
        # 'woo_products': 0, 

        # Shopify specific
        'shopify_orders': shopify_total,
        'shopify_pending_orders': shopify_pending_orders,
        'shopify_shipped_orders': shopify_shipped_orders,
        'shopify_not_shipped_orders': shopify_not_shipped_orders,
        # 'shopify_products': 0, 

        # Facebook specific
        'fb_orders': fb_total,
        'fb_pending_orders': fb_pending_orders,
        'fb_shipped_orders': fb_shipped_orders,
        'fb_not_shipped': fb_not_shipped,

        # Connection statuses (assuming static placeholders for now)
        'woo_status': 'Connected',
        'shopify_status': 'Connected'
    }
    return render(request, 'dashboard.html', context)
@login_required
def all_orders_view(request):
    """
    Displays a combined, paginated list of orders from WooCommerce, Shopify, and Facebook,
    with filtering, searching, and overdue highlighting. Defaults to showing the last 35 days.
    """
    # --- Get filter parameters ---
    search_query = request.GET.get('search_query', '').strip()
    date_filter_str = request.GET.get('date_filter', None)     
    days_filter_str = request.GET.get('days_filter', None)     
    not_shpped_filter_str = request.GET.get('not_shipped', None)
    page_number = request.GET.get('page')
    items_per_page = 15 

    # --- Time calculations (do once) ---
    now = timezone.now()
    two_days_ago = now - timedelta(days=2)
    thirty_five_days_ago = now - timedelta(days=35)

    # --- Initialize Filter Variables ---
    selected_date = None
    num_days = None
    start_date = None
    active_filter = bool(search_query or date_filter_str or days_filter_str or not_shpped_filter_str)

    # --- Parse Date/Days Filters (prioritize specific date) ---
    if date_filter_str:
        try:
            selected_date = parse_date(date_filter_str)
            if selected_date:
                logger.debug(f"All Orders: Filtering by specific date: {selected_date}")
                active_filter = True
                # Add one day to include orders from entire selected date
                end_date = selected_date + timedelta(days=1)
            else:
                logger.warning(f"All Orders: Invalid date format received: {date_filter_str}")
                selected_date = None
                end_date = None
        except Exception as e:
            logger.error(f"Error parsing date filter: {e}")
            selected_date = None
            end_date = None
            
    elif days_filter_str:
        try:
            num_days = int(days_filter_str)
            if num_days > 0:
                start_date = now - timedelta(days=num_days)
                logger.debug(f"All Orders: Filtering by last {num_days} days (since {start_date})")
                active_filter = True
            else:
                num_days = None
        except (ValueError, TypeError):
            logger.warning(f"All Orders: Invalid days filter value received: {days_filter_str}")
            num_days = None
    elif not_shpped_filter_str:
        not_shipped = ['processing', 'on-hold', 'partial-paid']
        query_filter = Q(status__in=not_shipped) & Q(date_created_woo__lt=two_days_ago)
        active_filter = True
    elif not active_filter:
        start_date = thirty_five_days_ago
        logger.debug(f"All Orders: Defaulting to orders from the last 35 days (since {start_date})")

    # =================== WooCommerce Orders ===================
    woo_queryset = WooCommerceOrder.objects.all()

    # Apply Filters to WooCommerce Queryset
    if search_query:
        woo_queryset = woo_queryset.filter(
            Q(woo_id__icontains=search_query) |
            Q(billing_first_name__icontains=search_query) |
            Q(billing_last_name__icontains=search_query) |
            Q(billing_phone__icontains=search_query) |
            Q(billing_city__icontains=search_query) |
            Q(billing_postcode__icontains=search_query) |
            Q(billing_email__icontains=search_query)
        )
    if selected_date:
        woo_queryset = woo_queryset.filter(
            date_created_woo__gte=selected_date,
            date_created_woo__lt=end_date
        )
    elif start_date:
        woo_queryset = woo_queryset.filter(date_created_woo__gte=start_date)
    if not_shpped_filter_str:
        not_shipped = ['processing', 'on-hold', 'partial-paid']
        woo_queryset = woo_queryset.filter(Q(status__in=not_shipped) & Q(date_created_woo__lt=two_days_ago))

    # Define highlight criteria for WooCommerce
    woo_actionable_statuses = ['processing','on-hold','partial-paid']

    # Process data and add highlight flag
    woo_data = []
    for o in woo_queryset:
        highlight = False
        try:
            # Check status and date validity before comparing
            if o.status and o.date_created_woo:
                status_needs_action = o.status.lower() in woo_actionable_statuses
                is_old = o.date_created_woo < two_days_ago
                if status_needs_action and is_old:
                    highlight = True
        except Exception as e:
            logger.error(f"Error calculating highlight for Woo Order {getattr(o, 'woo_id', 'N/A')}: {e}", exc_info=False)

        woo_data.append({
            'order_id': o.woo_id,
            'date': o.date_created_woo,
            'status': o.status,
            'amount': o.total_amount,
            'customer': f"{o.billing_first_name or ''} {o.billing_last_name or ''}".strip(),
            'phone': o.billing_phone,
            'pincode': o.billing_postcode,
            'city': o.billing_city,
            'note': o.customer_note,
            'tracking': f'https://nurserynisarga.in/admin-track-order/?track_order_id={o.woo_id}',
            'platform': 'WooCommerce',
            'shipment_status': getattr(o, 'shipment_status', 'N/A'),
            'is_overdue_highlight': highlight,
        })

    # =================== Shopify Orders ===================
    shopify_queryset = ShopifyOrder.objects.all()

    # Apply Filters to Shopify Queryset
    if search_query:
        shopify_queryset = shopify_queryset.filter(
            Q(email__icontains=search_query) |
            Q(name__icontains=search_query) |
            Q(billing_address_json__phone__icontains=search_query) |
            Q(billing_address_json__city__icontains=search_query) |
            Q(billing_address_json__zip__icontains=search_query)
        )
    if selected_date:
        shopify_queryset = shopify_queryset.filter(
            created_at_shopify__gte=selected_date,
            created_at_shopify__lt=end_date
        )
    elif start_date:
        shopify_queryset = shopify_queryset.filter(created_at_shopify__gte=start_date)

    # Define highlight criteria for Shopify
    shopify_actionable_statuses = ['unfulfilled', 'partially_fulfilled', 'scheduled', 'on_hold']

    # Process data and add highlight flag
    shopify_data = []
    for o in shopify_queryset:
        highlight = False
        try:
            # Check if required fields exist and date is valid
            if hasattr(o, 'fulfillment_status') and hasattr(o, 'created_at_shopify') and o.created_at_shopify:
                current_status = o.fulfillment_status
                needs_action = (
                    current_status is None or
                    (isinstance(current_status, str) and
                     current_status.lower() in shopify_actionable_statuses)
                )
                is_old = o.created_at_shopify < two_days_ago
                if needs_action and is_old:
                    highlight = True
        except Exception as e:
            logger.error(f"Error calculating highlight for Shopify Order {getattr(o, 'name', 'N/A')}: {e}", exc_info=False)

        # Extract other data safely
        shipping = o.shipping_address_json or {}
        tracking_url = 'N/A'
        try:
            if isinstance(o.raw_data, dict) and isinstance(o.raw_data.get("fulfillments"), list) and o.raw_data["fulfillments"]:
                fulfillment = o.raw_data["fulfillments"][0]
                if isinstance(fulfillment, dict):
                    tracking_url = fulfillment.get("tracking_url", 'N/A')
        except Exception:
            pass

        shopify_data.append({
            'order_id': o.name,
            'date': o.created_at_shopify,
            'status': o.fulfillment_status,
            'amount': o.total_price,
            'customer': shipping.get('name', ''),
            'phone': shipping.get('phone', ''),
            'pincode': shipping.get('zip', ''),
            'city': shipping.get('city', ''),
            'note': getattr(o, 'note', getattr(o, 'internal_notes', '')),
            'tracking': tracking_url,
            'platform': 'Shopify',
            'shipment_status': getattr(o, 'shipment_status', o.fulfillment_status),
            'is_overdue_highlight': highlight,
        })

    # =================== Facebook Orders ===================
    fb_queryset = Facebook_orders.objects.all()

    # Apply Filters to Facebook Queryset
    if search_query:
        fb_queryset = fb_queryset.filter(
            Q(order_id__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(alternet_number__icontains=search_query)
        )
    if selected_date:
        fb_queryset = fb_queryset.filter(
            date_created__gte=selected_date,
            date_created__lt=end_date
        )
    elif start_date:
        fb_queryset = fb_queryset.filter(date_created__gte=start_date)

    # Define highlight criteria for Facebook (based on model analysis)
    fb_actionable_statuses = ['pending', 'processing', 'on-hold']
    fb_status_field = 'status'
    fb_date_field = 'date_created'

    # Process data and add highlight flag
    fb_data = []
    for o in fb_queryset:
        highlight = False
        try:
            current_status = getattr(o, fb_status_field, None)
            creation_date = getattr(o, fb_date_field, None)
            if creation_date:
                # Status check (already lowercase from choices)
                status_needs_action = current_status in fb_actionable_statuses
                is_old = creation_date < two_days_ago
                if status_needs_action and is_old:
                    highlight = True
        except Exception as e:
            logger.error(f"Error calculating highlight for FB Order {getattr(o, 'order_id', 'N/A')}: {e}", exc_info=False)

        # Construct tracking URL safely
        tracking_info = getattr(o, 'tracking_info', None)
        fb_tracking_url = f'http://parcelx.in/tracking.php?waybill_no={tracking_info}' if tracking_info else 'N/A'

        fb_data.append({
            'order_id': o.order_id,
            'date': o.date_created,
            'status': o.status,
            'amount': o.total_amount,
            'customer': f"{o.first_name or ''} {o.last_name or ''}".strip(),
            'phone': o.phone,
            'pincode': o.postcode,
            'city': o.city,
            'note': o.customer_note,
            'tracking': fb_tracking_url,
            'platform': 'Facebook',
            'shipment_status': getattr(o, 'shipment_status', 'N/A'),
            'is_overdue_highlight': highlight,
        })

    # ================= Combine, Sort, Paginate =================
    combined_orders = woo_data + shopify_data + fb_data

    # Sort by date (descending) - ensure date objects are valid and comparable
    try:
        combined_orders_sorted = sorted(
            [order for order in combined_orders if order.get('date')],
            key=itemgetter('date'),
            reverse=True
        )
    except TypeError as e:
        logger.error(f"Error sorting combined orders by date: {e}. Check date types.")
        combined_orders_sorted = combined_orders

    # Pagination
    paginator = Paginator(combined_orders_sorted, items_per_page)
    try:
        orders_page = paginator.page(page_number)
    except PageNotAnInteger:
        orders_page = paginator.page(1)
    except EmptyPage:
        orders_page = paginator.page(paginator.num_pages)

    # ================= Context =================
    context = {
        'orders': orders_page,
        'current_search_query': search_query,
        'current_date_filter': date_filter_str if date_filter_str else '',
        'current_days_filter': days_filter_str if days_filter_str else '',
        'active_filter': active_filter,
        'has_orders': bool(combined_orders_sorted),  # Add flag to check if orders exist
        'selected_date': selected_date,  # Pass selected date to template
    }

    return render(request, 'orders/orders.html', context)

@login_required
def order_details_view(request,order_id):
    if '#' in str(order_id):
        woo_order = None
        shopify_order = ShopifyOrder.objects.filter(name=order_id).first()
        fb_order = None
    else:
        # For WooCommerce IDs are integers, Facebook IDs are strings
        try:
            order_id_int = int(order_id)
            woo_order = WooCommerceOrder.objects.filter(woo_id=order_id_int).first()
            fb_order = None
            shopify_order = None
        except ValueError:
            woo_order = None
            shopify_order = None
            fb_order = Facebook_orders.objects.filter(order_id=str(order_id)).first()
    if woo_order:
        order_data = {
            'order_id': woo_order.woo_id,
            'date': woo_order.date_created_woo,
            'status': woo_order.status,
            'amount': woo_order.total_amount,
            'customer': f"{woo_order.billing_first_name or ''} {woo_order.billing_last_name or ''}",
            'phone': woo_order.billing_phone,
            'pincode': woo_order.billing_postcode,
            'city': woo_order.billing_city,
            'note': woo_order.customer_note,
            'tracking': f'https://nurserynisarga.in/admin-track-order/?track_order_id={woo_order.woo_id}',            'platform': 'WooCommerce',
            'products': woo_order.line_items_json or []
        }
    elif shopify_order:
        shipping = shopify_order.shipping_address_json or {}
        order_data = {
            'order_id': shopify_order.name,
            'date': shopify_order.created_at_shopify,
            'status': shopify_order.fulfillment_status,
            'amount': shopify_order.total_price,
            'customer': shipping.get('name', ''),
            'phone': shipping.get('phone', ''),
            'pincode': shipping.get('zip', ''),
            'city': shipping.get('city', ''),
            'note': shopify_order.internal_notes,
            'tracking': shopify_order.tracking_details_json,
            'platform': 'Shopify',
            'products': shopify_order.line_items_json or []
        }
    elif fb_order:
        order_data = {
            'order_id': fb_order.order_id,
            'date': fb_order.date_created,
            'status': fb_order.status,
            'amount': fb_order.total_amount,
            'customer': f"{fb_order.first_name or ''} {fb_order.last_name or ''}",
            'phone': fb_order.phone,
            'pincode': fb_order.postcode,
            'city': fb_order.city,
            'note': fb_order.customer_note,
            'tracking': f'http://parcelx.in/tracking.php?waybill_no={fb_order.tracking_info}',            
            'platform': 'Facebook',
            'products': [{'name': item.get('product_name', ''), 'total': item.get('price', 0), 'quantity': item.get('quantity', 0), 'pot_size': item.get('pot_size', '')} for item in (fb_order.products_json or [])]        
            }            
    else:
        order_data = None

    context = {
        'order': order_data,
        'page_title': f'Order Details #{order_id}'
    }
    return render(request, 'orders/orders_view.html', context)


@login_required
def all_orders_edit(request, order_id):
    # Get order from each platform and check which one matches
    # For Shopify orders, ID contains '#' indicating string format
    if '#' in str(order_id):
        woo_order = None
        shopify_order = ShopifyOrder.objects.filter(name=order_id).first()
        fb_order = None
    else:
        # For WooCommerce and Facebook, IDs are integers
        try:
            order_id_int = int(order_id)
            woo_order = WooCommerceOrder.objects.filter(woo_id=order_id_int).first()
            fb_order = None
            shopify_order = None
        except ValueError:
            woo_order = None
            shopify_order = None
            fb_order = Facebook_orders.objects.filter(order_id=order_id).first()

    if request.method == 'POST':
        # Get form data
        status = request.POST.get('status')
        tracking = request.POST.get('tracking')
        note = request.POST.get('note')
        shipment_status = request.POST.get('shipment_status')

        # Update the order based on platform
        if woo_order:
            woo_order.status = status
            woo_order.customer_note = note
            woo_order.shipment_status = shipment_status
            woo_order.save()
        elif shopify_order:
            shopify_order.fulfillment_status = status
            shopify_order.tracking_details_json = tracking
            shopify_order.internal_notes = note
            shopify_order.shipment_status = shipment_status
            shopify_order.save()
        elif fb_order:
            fb_order.status = status
            fb_order.tracking_info = tracking
            fb_order.customer_note = note
            fb_order.shipment_status = shipment_status
            fb_order.save()
            
        return redirect('orders')

    if woo_order:
        order_data = {
            'order_id': woo_order.woo_id,
            'date': woo_order.date_created_woo,
            'status': woo_order.status,
            'amount': woo_order.total_amount,
            'customer': f"{woo_order.billing_first_name or ''} {woo_order.billing_last_name or ''}",
            'phone': woo_order.billing_phone,
            'pincode': woo_order.billing_postcode,
            'city': woo_order.billing_city,
            'note': woo_order.customer_note,
            'tracking': '',
            'platform': 'WooCommerce',
            'shipment_status': woo_order.shipment_status
        }
    elif shopify_order:
        shipping = shopify_order.shipping_address_json or {}
        order_data = {
            'order_id': shopify_order.name,
            'date': shopify_order.created_at_shopify,
            'status': shopify_order.fulfillment_status,
            'amount': shopify_order.total_price,
            'customer': shipping.get('name', ''),
            'phone': shipping.get('phone', ''),
            'pincode': shipping.get('zip', ''),
            'city': shipping.get('city', ''),
            'note': shopify_order.internal_notes,
            'tracking': shopify_order.tracking_details_json,
            'platform': 'Shopify',
            'shipment_status': shopify_order.shipment_status
        }
    elif fb_order:
        order_data = {
            'order_id': fb_order.order_id,
            'date': fb_order.date_created,
            'status': fb_order.status,
            'amount': fb_order.total_amount,
            'customer': f"{fb_order.first_name or ''} {fb_order.last_name or ''}",
            'phone': fb_order.phone,
            'pincode': fb_order.postcode,
            'city': fb_order.city,
            'note': fb_order.customer_note,
            'tracking': fb_order.tracking_info,
            'platform': 'Facebook',
            'shipment_status': fb_order.shipment_status
        }
    else:
        order_data = None

    context = {
        'order': order_data
    }

    return render(request, 'orders/edit_order.html', context)

