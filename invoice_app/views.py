from django.shortcuts import render,redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from woocommerce_app.models import WooCommerceOrder
from shopify_app.models import ShopifyOrder
from facebook_app.models import Facebook_orders
from .models import Order,Invoice,Company_name
from django.http import HttpResponse
import logging

logger = logging.getLogger(__name__)

def create_invoice(request, woo_id):
    try:
        # Check if invoice already exists for this order
        existing_invoice = Invoice.objects.filter(order_id=woo_id).first()
        if existing_invoice:
            logger.info(f"Invoice already exists with number: {existing_invoice.invoice_number}")
            return HttpResponse(f"Invoice already exists with number: {existing_invoice.invoice_number}")

        # Try to get order from different sources
        try:
            order_source = get_object_or_404(WooCommerceOrder, woo_id=woo_id)
            order_data = {
                'order_id': order_source.woo_id,
                'customer_name': f"{order_source.billing_first_name} {order_source.billing_last_name}",
                'customer_address': f"{order_source.billing_address_1}, {order_source.billing_address_2}, {order_source.billing_city}, {order_source.billing_state}, {order_source.billing_postcode}, {order_source.billing_country}",
                'customer_email': order_source.billing_email,
                'customer_phone': order_source.billing_phone,
                'order_total': order_source.total_amount,
                'order_status': order_source.status,
                'order_items': order_source.line_items_json,
                'order_shipment_status': order_source.shipment_status,
                'order_notes': order_source.customer_note,
                'payment_method': order_source.raw_data.get('payment_method', ''),
                'shipping_charge': order_source.raw_data.get('shipping_charge', 0)
            }
        except:
            try:
                order_source = get_object_or_404(ShopifyOrder, id=woo_id)
                # Add Shopify order data mapping here
                order_data = {}
            except:
                try:
                    order_source = get_object_or_404(Facebook_orders, id=woo_id)
                    # Add Facebook order data mapping here
                    order_data = {}
                except:
                    raise Exception("Order not found in any source")

        # Check if order already exists
        existing_order = Order.objects.filter(order_id=woo_id).first()
        if existing_order:
            order = existing_order
        else:
            # Create Order instance
            order = Order.objects.create(**order_data)

        # Create Invoice instance
        invoice = Invoice.objects.create(
            order=order
        )

        logger.info(f"Invoice created with number: {invoice.invoice_number}")
        return HttpResponse(f"Invoice created successfully with number: {invoice.invoice_number}")

    except Exception as e:
        logger.error(f"Error creating invoice: {str(e)}")
        return HttpResponse(f"Error creating invoice: {str(e)}")

def create_company(request):
    shopify = 'data'

