from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from operator import itemgetter
from .models import *
from facebook_app.models import Facebook_orders
from shopify_app.models import ShopifyOrder
from woocommerce_app.models import WooCommerceOrder

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_api(request):
    thirty_days_ago = timezone.now() - timedelta(days=30)

    woo_orders = WooCommerceOrder.objects.filter(date_created_woo__gte=thirty_days_ago)
    shopify_orders = ShopifyOrder.objects.filter(created_at_shopify__gte=thirty_days_ago)
    fb_orders = Facebook_orders.objects.filter(date_created__gte=thirty_days_ago)

    woo_total = woo_orders.count()
    shopify_total = shopify_orders.count()
    fb_total = fb_orders.count()
    total_orders = woo_total + shopify_total + fb_total

    woo_pending_orders = woo_orders.filter(status__in=['pending', 'cancelled','failed',]).count()
    woo_not_shipped = woo_orders.filter(status__in=['processing', 'on-hold', 'partial-paid']).count()
    shopify_pending_orders = shopify_orders.filter(financial_status__in=['pending', 'authorized', 'partially_paid']).count()
    shopify_not_shipped_orders = shopify_orders.filter(Q(fulfillment_status=None) |
        Q(fulfillment_status__in=['unfulfilled', 'partially_fulfilled', 'scheduled', 'on_hold'])
    ).count()
    fb_pending_orders = fb_orders.filter(status='pending').count()
    fb_not_shipped = fb_orders.filter(status__in=['processing', 'on-hold']).count()

    total_pending_orders = woo_pending_orders + shopify_pending_orders + fb_pending_orders
    total_not_shipped = woo_not_shipped + shopify_not_shipped_orders + fb_not_shipped
    woo_shipped_orders = woo_orders.filter(status__in=['completed', 'delivered', 'refunded',  'rto', 'lost', 'pickup-pending','not-picked', 'out-for-pickup', 'picked', 'dispatched', 'in-transit', 'on-process', 'ndr', 'rts', 'rto-pending', 'rto-dispatched', 'rto-in-transit']).count()
    shopify_shipped_orders = shopify_orders.filter(fulfillment_status__in=['fulfilled', 'complete', 'shipped']).count()
    fb_shipped_orders = fb_orders.filter(status__in=['completed', 'shipped', 'delivered']).count()
    total_shipment_status = woo_shipped_orders + shopify_shipped_orders + fb_shipped_orders

    data = {
        'total_orders': total_orders,
        'total_pending_orders': total_pending_orders,
        'total_shipment_status_orders': total_shipment_status,
        'total_not_shipped': total_not_shipped,
        'woo_orders': woo_total,
        'woo_pending_orders': woo_pending_orders,
        'woo_shipped_orders': woo_shipped_orders,
        'woo_not_shipped': woo_not_shipped,
        'shopify_orders': shopify_total,
        'shopify_pending_orders': shopify_pending_orders,
        'shopify_shipped_orders': shopify_shipped_orders,
        'shopify_not_shipped_orders': shopify_not_shipped_orders,
        'fb_orders': fb_total,
        'fb_pending_orders': fb_pending_orders,
        'fb_shipped_orders': fb_shipped_orders,
        'fb_not_shipped': fb_not_shipped,
    }
    return Response(data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def orders_api(request):
    search_query = request.GET.get('search_query', '').strip()
    date_filter_str = request.GET.get('date_filter', None)
    days_filter_str = request.GET.get('days_filter', None)
    not_shpped_filter_str = request.GET.get('not_shipped', None)

    now = timezone.now()
    two_days_ago = now - timedelta(days=2)
    thirty_five_days_ago = now - timedelta(days=35)

    selected_date = None
    num_days = None
    start_date = None
    active_filter = bool(search_query or date_filter_str or days_filter_str or not_shpped_filter_str)

    if date_filter_str:
        selected_date = timezone.datetime.fromisoformat(date_filter_str)
        end_date = selected_date + timedelta(days=1)
    elif days_filter_str:
        try:
            num_days = int(days_filter_str)
            if num_days > 0:
                start_date = now - timedelta(days=num_days)
        except (ValueError, TypeError):
            num_days = None
    elif not_shpped_filter_str:
        not_shipped = ['processing', 'on-hold', 'partial-paid']
        query_filter = Q(status__in=not_shipped) & Q(date_created_woo__lt=two_days_ago)
    elif not active_filter:
        start_date = thirty_five_days_ago

    woo_queryset = WooCommerceOrder.objects.all()
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
        woo_queryset = woo_queryset.filter(date_created_woo__gte=selected_date, date_created_woo__lt=end_date)
    elif start_date:
        woo_queryset = woo_queryset.filter(date_created_woo__gte=start_date)
    if not_shpped_filter_str:
        not_shipped = ['processing', 'on-hold', 'partial-paid']
        woo_queryset = woo_queryset.filter(Q(status__in=not_shipped) & Q(date_created_woo__lt=two_days_ago))

    woo_actionable_statuses = ['processing','on-hold','partial-paid']
    woo_data = []
    for o in woo_queryset:
        highlight = False
        if o.status and o.date_created_woo:
            status_needs_action = o.status.lower() in woo_actionable_statuses
            is_old = o.date_created_woo < two_days_ago
            if status_needs_action and is_old:
                highlight = True
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

    shopify_queryset = ShopifyOrder.objects.all()
    if search_query:
        shopify_queryset = shopify_queryset.filter(
            Q(email__icontains=search_query) |
            Q(name__icontains=search_query) |
            Q(billing_address_json__phone__icontains=search_query) |
            Q(billing_address_json__city__icontains=search_query) |
            Q(billing_address_json__zip__icontains=search_query)
        )
    if selected_date:
        shopify_queryset = shopify_queryset.filter(created_at_shopify__gte=selected_date, created_at_shopify__lt=end_date)
    elif start_date:
        shopify_queryset = shopify_queryset.filter(created_at_shopify__gte=start_date)

    shopify_actionable_statuses = ['unfulfilled', 'partially_fulfilled', 'scheduled', 'on_hold']
    shopify_data = []
    for o in shopify_queryset:
        highlight = False
        if o.fulfillment_status is None or str(o.fulfillment_status).lower() in shopify_actionable_statuses:
            if o.created_at_shopify and o.created_at_shopify < two_days_ago:
                highlight = True
        shipping = o.shipping_address_json or {}
        tracking_url = 'N/A'
        if isinstance(o.raw_data, dict) and isinstance(o.raw_data.get('fulfillments'), list) and o.raw_data['fulfillments']:
            fulfillment = o.raw_data['fulfillments'][0]
            if isinstance(fulfillment, dict):
                tracking_url = fulfillment.get('tracking_url', 'N/A')
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

    fb_queryset = Facebook_orders.objects.all()
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
        fb_queryset = fb_queryset.filter(date_created__gte=selected_date, date_created__lt=end_date)
    elif start_date:
        fb_queryset = fb_queryset.filter(date_created__gte=start_date)

    fb_actionable_statuses = ['pending', 'processing', 'on-hold']
    fb_data = []
    for o in fb_queryset:
        highlight = False
        current_status = getattr(o, 'status', None)
        creation_date = getattr(o, 'date_created', None)
        if creation_date and current_status in fb_actionable_statuses and creation_date < two_days_ago:
            highlight = True
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

    combined_orders = woo_data + shopify_data + fb_data
    combined_orders_sorted = sorted([order for order in combined_orders if order.get('date')], key=itemgetter('date'), reverse=True)
    return Response({'orders': combined_orders_sorted})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def order_detail_api(request, order_id):
    if '#' in str(order_id):
        woo_order = None
        shopify_order = ShopifyOrder.objects.filter(name=order_id).first()
        fb_order = None
    else:
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
            'address': woo_order.billing_address_1,
            'pincode': woo_order.billing_postcode,
            'city': woo_order.billing_city,
            'note': woo_order.customer_note,
            'tracking': f'https://nurserynisarga.in/admin-track-order/?track_order_id={woo_order.woo_id}',
            'platform': 'WooCommerce',
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
            'address': shopify_order.shipping_address_json.get('address1', 'N/A'),
            'phone': shipping.get('phone', ''),
            'pincode': shipping.get('zip', ''),
            'city': shipping.get('city', ''),
            'note': shopify_order.internal_notes,
            'tracking': f'https://lalitenterprise.com/pages/trackorder?channel_order_no={shopify_order.name.replace("#","")}',
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
            'address': fb_order.address,
            'pincode': fb_order.postcode,
            'city': fb_order.city,
            'note': fb_order.customer_note,
            'tracking': f'http://parcelx.in/tracking.php?waybill_no={fb_order.tracking_info}',
            'platform': 'Facebook',
            'products': [{'name': item.get('product_name', ''), 'total': item.get('price', 0), 'quantity': item.get('quantity', 0), 'pot_size': item.get('pot_size', '')} for item in (fb_order.products_json or [])]
            }
    else:
        order_data = None
    return Response({'order': order_data})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def order_update_api(request, order_id):
    if '#' in str(order_id):
        woo_order = None
        shopify_order = ShopifyOrder.objects.filter(name=order_id).first()
        fb_order = None
    else:
        try:
            order_id_int = int(order_id)
            woo_order = WooCommerceOrder.objects.filter(woo_id=order_id_int).first()
            fb_order = None
            shopify_order = None
        except ValueError:
            woo_order = None
            shopify_order = None
            fb_order = Facebook_orders.objects.filter(order_id=order_id).first()

    status = request.data.get('status')
    tracking = request.data.get('tracking')
    note = request.data.get('note')
    shipment_status = request.data.get('shipment_status')

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

    return Response({'message': 'Order updated successfully'})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def settings_api(request):
    """Retrieve or update integration credentials."""
    if request.method == 'GET':
        data = {
            setting.service: setting.credentials
            for setting in IntegrationSetting.objects.all()
        }
        return Response({'settings': data})

    service = request.data.get('service')
    credentials = request.data.get('credentials', {})
    if not service:
        return Response({'error': 'service is required'}, status=400)
    setting, _ = IntegrationSetting.objects.update_or_create(
        service=service, defaults={'credentials': credentials}
    )
    return Response({'service': setting.service, 'credentials': setting.credentials})
