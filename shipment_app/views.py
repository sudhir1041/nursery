from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt 
from django.contrib.auth.decorators import login_required
import json
from datetime import datetime, timedelta


# Assuming your models are imported correctly
from shopify_app.models import ShopifyOrder
from woocommerce_app.models import WooCommerceOrder
from facebook_app.models import Facebook_orders 
# Make sure these models have a JSONField, e.g.:
# unselected_items_for_clone = models.JSONField(null=True, blank=True, default=list)

import logging
logger = logging.getLogger(__name__)


@login_required
def home(request):
    today = datetime.now().astimezone()
    thirty_days_ago = today - timedelta(days=30)

    shopify_qs = ShopifyOrder.objects.filter(created_at_shopify__gte=thirty_days_ago)
    woo_qs = WooCommerceOrder.objects.filter(date_created_woo__gte=thirty_days_ago)
    fb_qs = Facebook_orders.objects.filter(date_created__gte=thirty_days_ago)
    
    all_orders = []

    # ====================== Shopify Orders =======================
    for o in shopify_qs:
        if o.fulfillment_status in ['unfulfilled', 'none'] and o.shipment_status in ['pending','processing', 'partially_shipped']:
            days_since_order = (today - o.created_at_shopify.astimezone()).days
            highlight = 'normal'
            if days_since_order >= 4: highlight = 'three_days_old'
            elif days_since_order >= 3: highlight = 'two_days_old'
            
            # Determine advance and balance amounts for Shopify
            shopify_advance_amount = "0.00" 
            shopify_balance_amount = o.total_price
            shopify_original_total = o.total_price

            order_data = {
                'order_id': o.name,
                'date': o.created_at_shopify,
                'status': o.fulfillment_status or 'unfulfilled',
                'amount': o.total_price,
                'customer': o.shipping_address_json.get('name', 'N/A'),
                'phone': o.shipping_address_json.get('phone', 'N/A'),
                'pincode': o.shipping_address_json.get('zip', 'N/A'),
                'state': o.shipping_address_json.get('province', 'N/A'),
                'address': o.shipping_address_json.get('address1', 'N/A'),
                'note': o.internal_notes,
                'tracking': o.tracking_details_json,
                'platform': 'Shopify',
                'shipment_status': o.shipment_status or 'Pending',
                'original_total': shopify_original_total,
                'advance_amount': shopify_advance_amount,
                'balance_amount': shopify_balance_amount,
                'is_overdue_highlight': highlight
            }

            if o.shipment_status == 'partially_shipped':
                order_data.update({
                    'status': o.shipment_status,
                    'items': [{
                        'name': item.get('name', ''),
                        'quantity': item.get('quantity', 0),
                        'price': item.get('price', 0),
                        'pot_size': item.get('variant_title', '') or 'N/A'
                    } for item in o.unselected_items_for_clone]
                })
            else:
                order_data.update({
                    'status': o.fulfillment_status,
                    'items': [{
                        'name': item.get('name', ''),
                        'quantity': item.get('quantity', 0),
                        'price': item.get('price', 0),
                        'pot_size': item.get('variant_title', '') or 'N/A'
                    } for item in o.line_items_json]
                })

            all_orders.append(order_data)

    # ======================== WooCommerce orders ======================
    for woo in woo_qs:
        if woo.status == 'processing' and woo.shipment_status in ['pending','processing', 'partially_shipped']:                      
            days_since_order = (today - woo.date_created_woo.astimezone()).days
            highlight = 'normal'
            if days_since_order >= 4: highlight = 'three_days_old'
            elif days_since_order >= 3: highlight = 'two_days_old'
            raw_data = woo.raw_data if isinstance(woo.raw_data, dict) else json.loads(woo.raw_data or '{}')
            advance_amount = None
            balance_amount = None
            original_total = woo.total_amount 
            for meta in raw_data.get("meta_data", []):
                if meta.get("key") == "_pi_original_total": original_total = meta.get("value")
                elif meta.get("key") == "_pi_advance_amount": advance_amount = meta.get("value")
                elif meta.get("key") == "_pi_balance_amount": balance_amount = meta.get("value")

            order_data = {
                'order_id': woo.woo_id,
                'date': woo.date_created_woo,
                'amount': woo.total_amount,
                'customer': f"{woo.billing_first_name or ''} {woo.billing_last_name or ''}".strip(),
                'phone': woo.billing_phone,
                'pincode': woo.billing_postcode,
                'state': woo.billing_state,
                'address': woo.billing_address_1,
                'note': woo.customer_note,
                'tracking': f'https://nurserynisarga.in/admin-track-order/?track_order_id={woo.woo_id}',
                'platform': 'Wordpress',
                'shipment_status': woo.shipment_status or 'Pending',
                'original_total': original_total,
                'advance_amount': advance_amount,
                'balance_amount': balance_amount,
                'is_overdue_highlight': highlight
            }
            

            if woo.shipment_status == 'partially_shipped':
                order_data.update({
                    'status': woo.shipment_status,
                    'items': [{
                        'name': item.get('name', ''),
                        'quantity': item.get('quantity', 0),
                        'price': item.get('price', 0),
                        'pot_size': next((m.get('value') for m in item.get('meta_data', []) if m.get('key') == 'pa_size' or m.get('display_key', '').lower() == 'size'), 'N/A')
                    } for item in woo.unselected_items_for_clone]
                })
            else:
                order_data.update({
                    'status': woo.status,
                    'items': [{
                        'name': item.get('name', ''),
                        'quantity': item.get('quantity', 0),
                        'price': item.get('price', 0),
                        'pot_size': next((m.get('value') for m in item.get('meta_data', []) if m.get('key') == 'pa_size' or m.get('display_key', '').lower() == 'size'), 'N/A')
                    } for item in woo.line_items_json]
                })

            all_orders.append(order_data)

    # ======================== Facebook orders ======================
    for f in fb_qs:
        if f.status == 'processing' and f.shipment_status in ['pending','processing', 'partially-shipped']:
            days_since_order = (today - f.date_created.astimezone()).days
            highlight = 'normal'
            if days_since_order >= 4: highlight = 'three_days_old'
            elif days_since_order >= 3: highlight = 'two_days_old'
            
            products = f.products_json if isinstance(f.products_json, list) else json.loads(f.products_json or '[]')

            order_data = {
                'order_id': f.order_id,
                'date': f.date_created,
                'status': f.status,
                'amount': f.total_amount,
                'customer': f"{f.first_name or ''} {f.last_name or ''}".strip(),
                'address': f.address,
                'phone': f.phone,
                'pincode': f.postcode,
                'state': f.state,
                'note': f.customer_note,
                'tracking': f.tracking_info,
                'platform': 'Facebook',
                'shipment_status': f.shipment_status or 'Pending',
                'original_total': f.total_amount,
                'advance_amount': None,
                'balance_amount': f.total_amount,
                'is_overdue_highlight': highlight
            }

            if f.shipment_status == 'partially-shipped':
                order_data.update({
                    'status': f.shipment_status,
                    'items': [{
                        'name': item.get('name', ''),
                        'quantity': item.get('quantity', 0),
                        'price': item.get('price', 0),
                        'pot_size': next((m.get('value') for m in item.get('meta_data', []) if m.get('key') == 'pa_size' or m.get('display_key', '').lower() == 'size'), 'N/A')
                    } for item in f.unselected_items_for_clone]
                })
            else:
                order_data.update({
                    'status': f.status,
                    'items': [{
                        'name': product.get('product_name', ''),
                        'quantity': product.get('quantity', 0),
                        'price': product.get('price', 0),
                        'pot_size': product.get('variant_details', {}).get('size', 'N/A')
                    } for product in products]
                })

            all_orders.append(order_data)    
    all_orders.sort(key=lambda x: x['date'], reverse=True)
    context = {'orders': all_orders, 'project_name': 'Order Dashboard'} 
    return render(request, 'shipment/shipment.html', context)

@login_required
@require_POST 
def process_shipment(request):
    try:
        data = json.loads(request.body)
        
        # FIX 1: Use .get() with a default and .strip() to clean the incoming ID string.
        # This removes any accidental leading/trailing whitespace.
        order_id_str = data.get('orderId', '').strip()
        platform = data.get('platform')
        new_shipping_status = data.get('shippingStatus')
        unselected_items = data.get('unselectedItems', [])

        if not all([order_id_str, platform, new_shipping_status]):
            return JsonResponse({'error': 'Missing required data (orderId, platform, shippingStatus).'}, status=400)

        order_instance = None
        
        # FIX 2: Add logging to see the exact ID being used for the database query.
        # This is extremely helpful for debugging.
        logger.info(f"Attempting to process shipment. Platform: '{platform}', Cleaned ID: '{order_id_str}'")

        if platform == 'Shopify':
            # CONFIRMED: Using string lookup for Shopify's 'name' field.
            # Ensure your ShopifyOrder model's field is indeed named 'name'.
            order_instance = get_object_or_404(ShopifyOrder, name=order_id_str)

        elif platform == 'Wordpress':
            # This logic is correct and working, so we leave it as is.
            try:
                order_id_int = int(order_id_str)
                order_instance = get_object_or_404(WooCommerceOrder, woo_id=order_id_int)
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Invalid Order ID format for Wordpress.'}, status=400)

        elif platform == 'Facebook':
            # CONFIRMED: Using string lookup for Facebook's 'order_id' field.
            # Ensure your Facebook_orders model's field is indeed named 'order_id'.
            order_instance = get_object_or_404(Facebook_orders, order_id=order_id_str)
        
        else:
            return JsonResponse({'error': 'Invalid platform specified.'}, status=400)

        # The rest of your function remains the same
        order_instance.shipment_status = new_shipping_status
        
        if hasattr(order_instance, 'unselected_items_for_clone'):
            order_instance.unselected_items_for_clone = unselected_items
        else:
            logger.warning(f"Model for {platform} ID {order_id_str} does not have 'unselected_items_for_clone' field.")

        order_instance.save()
        
        logger.info(f"Successfully processed shipment for {platform} Order ID {order_id_str}.")

        return JsonResponse({
            'message': f'{platform} Order {order_id_str} updated successfully.',
            'newShipmentStatus': new_shipping_status, 
            'unselected_count': len(unselected_items)
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data.'}, status=400)
    except Exception as e:
        # Enhanced logging for any other errors
        logger.error(f"Error processing shipment: {type(e).__name__} - {e}", exc_info=True)
        return JsonResponse({'error': f'An unexpected error occurred: {str(e)}'}, status=500)

@login_required
def shipped(request):
    today = datetime.now().astimezone()
    thirty_days_ago = today - timedelta(days=30)

    shopify_qs = ShopifyOrder.objects.filter(created_at_shopify__gte=thirty_days_ago)
    woo_qs = WooCommerceOrder.objects.filter(date_created_woo__gte=thirty_days_ago)
    fb_qs = Facebook_orders.objects.filter(date_created__gte=thirty_days_ago)
    
    all_orders = []

    #============================== Shopify =================================
    for o in shopify_qs:
        if o.shipment_status in ['shipped', 'partially_shipped']:
            days_since_order = (today - o.created_at_shopify.astimezone()).days
            highlight = 'normal'
            
            # Determine advance and balance amounts for Shopify
            shopify_advance_amount = "0.00" 
            shopify_balance_amount = o.total_price
            shopify_original_total = o.total_price

            order_data = {
                'order_id': o.name,
                'date': o.created_at_shopify,
                'status': o.fulfillment_status or 'fulfilled',
                'amount': o.total_price,
                'customer': o.shipping_address_json.get('name', 'N/A'),
                'phone': o.shipping_address_json.get('phone', 'N/A'),
                'pincode': o.shipping_address_json.get('zip', 'N/A'),
                'state': o.shipping_address_json.get('province', 'N/A'),                
                'note': o.internal_notes,
                'tracking': o.tracking_details_json,
                'platform': 'Shopify',
                'shipment_status': o.shipment_status or 'Pending',
                'original_total': shopify_original_total,
                'advance_amount': shopify_advance_amount,
                'balance_amount': shopify_balance_amount,
                'is_overdue_highlight': highlight
            }

            unselected_name = [item.get('name') for item in o.unselected_items_for_clone]
            all_items = o.line_items_json
            new_items = []

            for item in all_items:
                if item.get('name') not in unselected_name:
                    new_items.append(item)  

            order_data.update({
                'status': "shipped",
                'items': [{
                    'name': item.get('name', ''),
                    'quantity': item.get('quantity', 0),
                    'price': item.get('price', 0),
                    'pot_size': item.get('variant_title', '') or 'N/A'
                } for item in new_items]
            })

            all_orders.append(order_data)
    # ======================== WooCommerce orders ======================
    for woo in woo_qs:
        if woo.shipment_status in ['shipped', 'partially_shipped']:                      
            days_since_order = (today - woo.date_created_woo.astimezone()).days
            highlight = 'normal'
            
            raw_data = woo.raw_data if isinstance(woo.raw_data, dict) else json.loads(woo.raw_data or '{}')
            advance_amount = None
            balance_amount = None
            original_total = woo.total_amount 
            for meta in raw_data.get("meta_data", []):
                if meta.get("key") == "_pi_original_total": original_total = meta.get("value")
                elif meta.get("key") == "_pi_advance_amount": advance_amount = meta.get("value")
                elif meta.get("key") == "_pi_balance_amount": balance_amount = meta.get("value")

            order_data = {
                'order_id': woo.woo_id,
                'date': woo.date_created_woo,
                'amount': woo.total_amount,
                'customer': f"{woo.billing_first_name or ''} {woo.billing_last_name or ''}".strip(),
                'phone': woo.billing_phone,
                'pincode': woo.billing_postcode,
                'state': woo.billing_state,
                'note': woo.customer_note,
                'tracking': f'https://nurserynisarga.in/admin-track-order/?track_order_id={woo.woo_id}',
                'platform': 'Wordpress',
                'shipment_status': woo.shipment_status or 'Pending',
                'original_total': original_total,
                'advance_amount': advance_amount,
                'balance_amount': balance_amount,
                'is_overdue_highlight': highlight
            }

            unselected_name = [item.get('name') for item in woo.unselected_items_for_clone] if woo.unselected_items_for_clone else []            
            all_items = woo.line_items_json
            new_items = []

            for item in all_items:
                if item.get('name') not in unselected_name:
                    new_items.append(item)

            order_data.update({
                'status': "shipped",
                'items': [{
                    'name': item.get('name', ''),
                    'quantity': item.get('quantity', 0),
                    'price': float(item.get('price', 0)),
                    'pot_size': next((m.get('value') for m in item.get('meta_data', []) if m.get('key') == 'pa_size' or m.get('display_key', '').lower() == 'size'), 'N/A'),
                    'sku': item.get('sku', ''),
                    'image': item.get('image', {}).get('src', ''),
                    'product_id': item.get('product_id', ''),
                    'variation_id': item.get('variation_id', 0)
                } for item in new_items]
            })

            all_orders.append(order_data)

    # ======================== Facebook orders ======================
    for f in fb_qs:
        if f.shipment_status in ['shipped', 'partially_shipped']:
            days_since_order = (today - f.date_created.astimezone()).days
            highlight = 'normal'
        
            
            products = f.products_json if isinstance(f.products_json, list) else json.loads(f.products_json or '[]')

            order_data = {
                'order_id': f.order_id,
                'date': f.date_created,
                'status': f.status,
                'amount': f.total_amount,
                'customer': f"{f.first_name or ''} {f.last_name or ''}".strip(),
                'phone': f.phone,
                'pincode': f.postcode,
                'state': f.state,
                'note': f.customer_note,
                'tracking': f.tracking_info,
                'platform': 'Facebook',
                'shipment_status': f.shipment_status or 'Pending',
                'original_total': f.total_amount,
                'advance_amount': None,
                'balance_amount': f.total_amount,
                'is_overdue_highlight': highlight
            }

            unselected_name = [item.get('name') for item in f.unselected_items_for_clone]
            all_items = products
            new_items = []

            for item in all_items:
                if item.get('product_name') not in unselected_name:
                    new_items.append(item)

            order_data.update({
                'status': "shipped",
                'items': [{
                    'name': item.get('product_name', ''),
                    'quantity': item.get('quantity', 0),
                    'price': item.get('price', 0),
                    'pot_size': item.get('variant_details', {}).get('size', 'N/A')
                } for item in new_items]
            })

            all_orders.append(order_data)    

    all_orders.sort(key=lambda x: x['date'], reverse=True)
    context = {'orders': all_orders, 'project_name': 'Order Dashboard'} 
    return render(request, 'shipment/shipped_order.html', context)