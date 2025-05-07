from django.shortcuts import render,redirect,HttpResponse
from shopify_app.models import ShopifyOrder
from woocommerce_app.models import WooCommerceOrder
from facebook_app.models import Facebook_orders
from datetime import datetime, timedelta


def home(request):
    # Get current date and date 30 days ago
    today = datetime.now()
    thirty_days_ago = today - timedelta(days=30)

    shopify = ShopifyOrder.objects.filter(created_at_shopify__gte=thirty_days_ago)
    woo = WooCommerceOrder.objects.filter(date_created_woo__gte=thirty_days_ago)
    fb = Facebook_orders.objects.filter(date_created__gte=thirty_days_ago)
    
    # ====================== Shopify Orders =======================
    shopify_orders = []
    for sf in shopify:
        if sf.fulfillment_status == 'unfulfilled' or sf.fulfillment_status == 'none':
            shopify_orders.append({
                'order_id': sf.name,
                'date': sf.created_at_shopify,
                'status': sf.fulfillment_status,
                'amount': sf.total_price,
                'customer': sf.shipping_address_json.get('name', ''),
                'phone': sf.shipping_address_json.get('phone', ''),
                'pincode': sf.shipping_address_json.get('zip', ''),
                'city': sf.shipping_address_json.get('city', ''),
                'note': sf.internal_notes,
                'tracking': sf.tracking_details_json,
                'platform': 'Shopify',
                'shipment_status': sf.shipment_status,
                'items': sf.line_items_json
            })

    # ======================== WooCommerce orders ======================
    woo_orders = []
    for o in woo:
        if o.status == 'processing' or o.status == 'partial-paid' :
            woo_orders.append({
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
                'platform': 'Wordpress',
                'shipment_status': o.shipment_status,
                'items': o.line_items_json
            })

    # ======================== Facebook orders ======================
    fb_orders = []
    for f in fb:
        if f.status == 'processing' :
            fb_orders.append({
                'order_id': f.order_id,
                'date': f.date_created,
                'status': f.status,
                'amount': f.total_amount,
                'customer': f"{f.billing_first_name or ''} {f.billing_last_name or ''}".strip(),
                'phone': f.billing_phone,
                'pincode': f.billing_postcode,
                'city': f.billing_city,
                'note': f.customer_note,
                'tracking': f.tracking_info,
                'platform': 'Facebook',
                'shipment_status': f.shipment_status,
                'items': f.products_json
            })

    # Combine all orders
    all_orders = shopify_orders + woo_orders + fb_orders
    
    # Sort orders by date in descending order (newest first)
    all_orders.sort(key=lambda x: x['date'], reverse=True)

    context = {
        'orders': all_orders
    }

    return render(request, 'shipment/shipment.html', context)

