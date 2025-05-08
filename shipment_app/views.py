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
                'items': sf.line_items_json,
                'clone_orders': sf.clone_orders if hasattr(sf, 'clone_orders') else []
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
                'items': o.line_items_json,
                'clone_orders': o.clone_orders if hasattr(o, 'clone_orders') else []
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
                'items': f.products_json,
                'clone_orders': f.clone_orders if hasattr(f, 'clone_orders') else []
            })

    # Combine all orders
    all_orders = shopify_orders + woo_orders + fb_orders
    
    # Sort orders by date in descending order (newest first)
    all_orders.sort(key=lambda x: x['date'], reverse=True)

    context = {
        'orders': all_orders
    }

    return render(request, 'shipment/shipment.html', context)

def clone_order(request,order_id):
    if request.method == 'POST':
        order_id = request.POST.get('order_id')
        platform = request.POST.get('platform')
        
        if platform == 'Shopify':
            order = ShopifyOrder.objects.get(name=order_id)
            clone_data = {
                'order_id': order.name,
                'date': datetime.now(),
                'items': order.line_items_json,
                'customer': order.shipping_address_json.get('name', ''),
                'amount': order.total_price,
                'raw_data': order.raw_data_json
            }
            if not order.clone_orders:
                order.clone_orders = []
            order.clone_orders.append(clone_data)
            order.save()
            
        elif platform == 'Wordpress':
            order = WooCommerceOrder.objects.get(woo_id=order_id)
            clone_data = {
                'order_id': order.woo_id,
                'date': datetime.now(),
                'items': order.line_items_json,
                'customer': f"{order.billing_first_name or ''} {order.billing_last_name or ''}".strip(),
                'amount': order.total_amount,
                'raw_data': order.raw_data_json
            }
            if not order.clone_orders:
                order.clone_orders = []
            order.clone_orders.append(clone_data)
            order.save()
            
        elif platform == 'Facebook':
            order = Facebook_orders.objects.get(order_id=order_id)
            clone_data = {
                'order_id': order.order_id,
                'date': datetime.now(),
                'items': order.products_json,
                'customer': f"{order.billing_first_name or ''} {order.billing_last_name or ''}".strip(),
                'amount': order.total_amount,
                'raw_data': order.raw_data_json
            }
            if not order.clone_orders:
                order.clone_orders = []
            order.clone_orders.append(clone_data)
            order.save()
            
        return HttpResponse('Order cloned successfully')
    
    return HttpResponse('Invalid request method')
    
