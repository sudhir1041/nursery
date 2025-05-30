from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt 
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

# Your existing home view (slightly modified for item structure consistency if needed)
def home(request):
    today = datetime.now().astimezone()
    thirty_days_ago = today - timedelta(days=30)

    shopify_qs = ShopifyOrder.objects.filter(created_at_shopify__gte=thirty_days_ago)
    woo_qs = WooCommerceOrder.objects.filter(date_created_woo__gte=thirty_days_ago)
    fb_qs = Facebook_orders.objects.filter(date_created__gte=thirty_days_ago)
    
    all_orders = []

    # ====================== Shopify Orders =======================
    for o in shopify_qs:
        unfulfilled = o.fulfillment_status == 'unfulfilled' or o.fulfillment_status == 'none' and o.shipment_status== 'pending'
        if unfulfilled: # Process only orders that need shipping
            days_since_order = (today - o.created_at_shopify.astimezone()).days
            highlight = 'normal'
            if days_since_order >= 4: highlight = 'three_days_old'
            elif days_since_order >= 3: highlight = 'two_days_old'
            
            # Determine advance and balance amounts for Shopify
            # Shopify's o.total_price is typically the final amount due after discounts.
            # If you have a specific field in your ShopifyOrder model for 'advance paid' or 'discounts applied'
            # that you want to use for 'advance_amount', use that here.
            # For example, if o.current_total_discounts exists and represents the discount value:
            # advance_payment_or_discount = o.current_total_discounts if hasattr(o, 'current_total_discounts') else "0.00"
            # balance = o.total_price 
            # original_total_before_discount = float(o.total_price) + float(advance_payment_or_discount)

            # Assuming no separate advance payment field is explicitly tracked for Shopify in this context,
            # and total_price is the amount to be collected.
            shopify_advance_amount = "0.00" 
            shopify_balance_amount = o.total_price
            # If you want 'original_total' to be subtotal_price before discounts, and have a discount field:
            # shopify_original_total = o.subtotal_price # or (float(o.total_price) + float(o.your_discount_field_value))
            # For simplicity, if total_price is the grand total:
            shopify_original_total = o.total_price


            all_orders.append({
                'order_id': o.name, # Shopify's display name for order ID
                'date': o.created_at_shopify,
                'status': o.fulfillment_status or 'unfulfilled', # Main status
                'amount': o.total_price, # This is usually the final amount the customer pays
                'customer': o.shipping_address_json.get('name', 'N/A'),
                'phone': o.shipping_address_json.get('phone', 'N/A'),
                'pincode': o.shipping_address_json.get('zip', 'N/A'),
                'state': o.shipping_address_json.get('province', 'N/A'),                
                'note': o.internal_notes,
                'tracking': o.tracking_details_json, # This might be a complex object
                'platform': 'Shopify',
                'shipment_status': o.shipment_status or 'Pending', # Your custom shipment status field
                'items': [{
                    'name': item.get('name', ''),
                    'quantity': item.get('quantity', 0),
                    'price': item.get('price', 0),
                    'pot_size': item.get('variant_title', '') or 'N/A' # Ensure pot_size is available
                } for item in o.line_items_json],
                'original_total': shopify_original_total, 
                'advance_amount': shopify_advance_amount, # Corrected: ShopifyOrder might not have 'total_discounts'.
                                                          # Set to 0.00 or None if advance payments are not tracked this way for Shopify.
                                                          # Verify against your ShopifyOrder model.
                'balance_amount': shopify_balance_amount, # This would be o.total_price if advance_amount is 0.
                'is_overdue_highlight': highlight
            })

    # ======================== WooCommerce orders ======================
    for woo in woo_qs:
        if woo.status == 'processing' or woo.status == 'partial-paid' and woo.shipment_status == 'pending':            
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

            all_orders.append({
                'order_id': woo.woo_id,
                'date': woo.date_created_woo,
                'status': woo.status,
                'amount': woo.total_amount,
                'customer': f"{woo.billing_first_name or ''} {woo.billing_last_name or ''}".strip(),
                'phone': woo.billing_phone,
                'pincode': woo.billing_postcode,
                'state': woo.billing_state,
                'note': woo.customer_note,
                'tracking': f'https://nurserynisarga.in/admin-track-order/?track_order_id={woo.woo_id}',
                'platform': 'Wordpress',
                'shipment_status': woo.shipment_status or 'Pending',
                'items': [{
                    'name': item.get('name', ''),
                    'quantity': item.get('quantity', 0),
                    'price': item.get('price', 0),
                    'pot_size': next((m.get('value') for m in item.get('meta_data', []) if m.get('key') == 'pa_size' or m.get('display_key', '').lower() == 'size'), 'N/A') 
                } for item in woo.line_items_json],
                'original_total': original_total,
                'advance_amount': advance_amount,
                'balance_amount': balance_amount,
                'is_overdue_highlight': highlight
            })

    # ======================== Facebook orders ======================
    for f in fb_qs:
        if f.status == 'processing'  and f.shipment_status == 'pending': 
            highlight = 'normal'
            if days_since_order >= 4: highlight = 'three_days_old'
            elif days_since_order >= 3: highlight = 'two_days_old'
            
            products = f.products_json if isinstance(f.products_json, list) else json.loads(f.products_json or '[]')

            all_orders.append({
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
                'items': [{
                    'name': product.get('product_name', ''),
                    'quantity': product.get('quantity', 0),
                    'price': product.get('price', 0),
                    'pot_size': product.get('variant_details', {}).get('size', 'N/A') 
                } for product in products],
                'original_total': f.total_amount, 
                'advance_amount': None, 
                'balance_amount': f.total_amount, 
                'is_overdue_highlight': highlight
            })
    
    all_orders.sort(key=lambda x: x['date'], reverse=True)
    context = {'orders': all_orders, 'project_name': 'Order Dashboard'} 
    return render(request, 'shipment/shipment.html', context)


@require_POST
def process_shipment(request):
    try:
        data = json.loads(request.body)
        order_id_str = data.get('orderId', '').strip()
        platform = data.get('platform')
        new_shipping_status = data.get('shippingStatus')
        unselected_items = data.get('unselectedItems', [])

        if not all([order_id_str, platform, new_shipping_status]):
            return JsonResponse({'error': 'Missing required data (orderId, platform, shippingStatus).'}, status=400)

        order_instance = None
        logger.info(f"Processing shipment for Platform: {platform}, ID: {order_id_str}")

        # Step 1: Find the original order
        if platform == 'Shopify':
            order_instance = get_object_or_404(ShopifyOrder, name=order_id_str)
        elif platform == 'Wordpress':
            order_instance = get_object_or_404(WooCommerceOrder, woo_id=int(order_id_str))
        elif platform == 'Facebook':
            order_instance = get_object_or_404(Facebook_orders, order_id=order_id_str)
        else:
            return JsonResponse({'error': 'Invalid platform specified.'}, status=400)

        # Step 2: Update the original order's status
        order_instance.shipment_status = new_shipping_status
        order_instance.save()

        cloned_order_id = None
        # Step 3: If there are unselected items, create a new "cloned" order
        if unselected_items:
            new_id = f"P{order_id_str}"
            total_amount = sum(float(item.get('price', 0)) * int(item.get('quantity', 0)) for item in unselected_items)

            if platform == 'Shopify':
                # Assumes you have access to the original JSON for customer data
                shipping_address = order_instance.shipping_address_json
                new_order = ShopifyOrder.objects.create(
                    name=new_id,
                    created_at_shopify=datetime.now(),
                    shipping_address_json=shipping_address,
                    line_items_json=unselected_items,
                    total_price=str(total_amount),
                    fulfillment_status='unfulfilled',
                    shipment_status='pending' # Set initial status
                    # Copy other relevant fields from order_instance
                )
                cloned_order_id = new_order.name

            elif platform == 'Wordpress':
                new_order = WooCommerceOrder.objects.create(
                    woo_id=new_id, # Or generate a new unique numeric ID if your system requires it
                    date_created_woo=datetime.now(),
                    billing_first_name=order_instance.billing_first_name,
                    billing_last_name=order_instance.billing_last_name,
                    billing_phone=order_instance.billing_phone,
                    billing_postcode=order_instance.billing_postcode,
                    billing_state=order_instance.billing_state,
                    line_items_json=unselected_items,
                    total_amount=str(total_amount),
                    status='processing', # Set initial status
                    shipment_status='pending'
                    # Copy other relevant fields from order_instance
                )
                cloned_order_id = new_order.woo_id

            elif platform == 'Facebook':
                new_order = Facebook_orders.objects.create(
                    order_id=new_id,
                    date_created=datetime.now(),
                    first_name=order_instance.first_name,
                    last_name=order_instance.last_name,
                    phone=order_instance.phone,
                    postcode=order_instance.postcode,
                    state=order_instance.state,
                    products_json=unselected_items,
                    total_amount=str(total_amount),
                    status='processing', # Set initial status
                    shipment_status='pending'
                    # Copy other relevant fields from order_instance
                )
                cloned_order_id = new_order.order_id

            logger.info(f"Created new partial order {cloned_order_id} for unselected items.")

        message = f'{platform} Order {order_id_str} updated successfully.'
        if cloned_order_id:
            message += f' New partial order {cloned_order_id} has been created for the remaining items.'

        return JsonResponse({
            'message': message,
            'newShipmentStatus': new_shipping_status,
            'clonedOrderId': cloned_order_id
        })

    except (ValueError, TypeError) as e:
        logger.error(f"Invalid Order ID format for Wordpress: {e}")
        return JsonResponse({'error': 'Invalid Order ID format for Wordpress.'}, status=400)
    except Exception as e:
        logger.error(f"Error processing shipment: {e}", exc_info=True)
        return JsonResponse({'error': f'An unexpected error occurred: {str(e)}'}, status=500)

    
# Clone order if nedd ==================================================
@require_POST
def clone_order(request):
    try:
        data = json.loads(request.body)
        original_order_id_str = data.get('orderId', '').strip()
        platform = data.get('platform')

        if not all([original_order_id_str, platform]):
            return JsonResponse({'error': 'Missing required data (orderId, platform).'}, status=400)

        # 1. Define models and fields based on platform
        OrderModel = None
        id_field_name = ''
        items_field_name = ''
        date_field_name = ''
        total_field_name = ''
        
        if platform == 'Shopify':
            OrderModel, id_field_name, items_field_name, date_field_name, total_field_name = ShopifyOrder, 'name', 'line_items_json', 'created_at_shopify', 'total_price'
        elif platform == 'Wordpress':
            OrderModel, id_field_name, items_field_name, date_field_name, total_field_name = WooCommerceOrder, 'woo_id', 'line_items_json', 'date_created_woo', 'total_amount'
        elif platform == 'Facebook':
            OrderModel, id_field_name, items_field_name, date_field_name, total_field_name = Facebook_orders, 'order_id', 'products_json', 'date_created', 'total_amount'
        else:
            return JsonResponse({'error': 'Invalid platform specified.'}, status=400)

        # 2. Fetch the original order instance
        original_order_instance = get_object_or_404(OrderModel, **{id_field_name: original_order_id_str})
        
        # 3. Get the unselected items saved on the original order
        items_to_clone = getattr(original_order_instance, 'unselected_items_for_clone', [])
        if not items_to_clone:
            return JsonResponse({'error': 'No unselected items found on the original order to clone.'}, status=400)

        # 4. Generate the new sequential order ID (e.g., 4623-1, 4623-2)
        base_id = str(original_order_id_str).split('-')[0]
        # Find all existing orders with the same base ID
        regex_pattern = rf"^{re.escape(base_id)}(-\d+)?$"
        existing_orders = OrderModel.objects.filter(**{f"{id_field_name}__regex": regex_pattern}).values_list(id_field_name, flat=True)

        highest_suffix = 0
        for order_id in existing_orders:
            parts = str(order_id).split('-')
            if len(parts) > 1 and parts[1].isdigit():
                suffix = int(parts[1])
                if suffix > highest_suffix:
                    highest_suffix = suffix
        
        new_order_id = f"{base_id}-{highest_suffix + 1}"

        # 5. Create the new order by cloning the original
        # This effectively copies all fields from the original order
        original_order_instance.pk = None
        new_order_instance = original_order_instance
        
        # 6. Overwrite fields for the new cloned order
        setattr(new_order_instance, id_field_name, new_order_id)
        setattr(new_order_instance, items_field_name, items_to_clone) # Set new item list
        setattr(new_order_instance, date_field_name, datetime.now()) # Update creation date
        
        # Reset status fields
        new_order_instance.status = 'processing' if platform != 'Shopify' else 'unfulfilled'
        new_order_instance.fulfillment_status = 'unfulfilled' if platform == 'Shopify' else None
        new_order_instance.shipment_status = 'pending'
        new_order_instance.unselected_items_for_clone = [] # Clear unselected items on the new clone
        new_order_instance.internal_notes = f"Cloned from order {original_order_id_str}" if platform == 'Shopify' else F('customer_note')
        
        # Recalculate total amount based on the items being cloned
        new_total = sum(float(item.get('price', 0)) * int(item.get('quantity', 0)) for item in items_to_clone)
        setattr(new_order_instance, total_field_name, str(new_total))
        new_order_instance.balance_amount = str(new_total)
        new_order_instance.advance_amount = "0.00"

        new_order_instance.save() # Save the new order to the database

        return JsonResponse({'message': 'Order cloned successfully from unselected items!', 'newOrderId': new_order_id})

    except Exception as e:
        logger.error(f"Error cloning order: {e}", exc_info=True)
        return JsonResponse({'error': f'An unexpected error occurred: {str(e)}'}, status=500)