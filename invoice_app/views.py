from django.shortcuts import render,redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from woocommerce_app.models import WooCommerceOrder
from shopify_app.models import ShopifyOrder
from facebook_app.models import Facebook_orders
from .models import Order,Invoice,Company_name
import logging

logger = logging.getLogger(__name__)

def create_invoice(request,id):
    try:
        # Check if invoice already exists for this order
        existing_invoice = Invoice.objects.filter(order__id=id).first()
        if existing_invoice:
            logger.info(f"Invoice already exists with number: {existing_invoice.invoice_number}")
            return

        woo_order = get_object_or_404(WooCommerceOrder, id=id)
        shopify = get_object_or_404(ShopifyOrder,id=id) 
        fb = get_object_or_404(Facebook_orders,id=id)

        # Check if order already exists
        existing_order = Order.objects.filter(id=id).first()
        if existing_order:
            order = existing_order
        else:
            # Create Order instance
            order = Order.objects.create(
                customer_name=f"{woo_order.billing_first_name} {woo_order.billing_last_name}",
                customer_address=f"{woo_order.billing_address_1}, {woo_order.billing_address_2}, {woo_order.billing_city}, {woo_order.billing_state}, {woo_order.billing_postcode}, {woo_order.billing_country}",
                customer_email=woo_order.billing_email,
                customer_phone=woo_order.billing_phone,
                order_total=woo_order.total_amount,
                order_status=woo_order.status,
                order_items=woo_order.line_items_json,
                order_shipment_status=woo_order.shipment_status,
                order_notes=woo_order.customer_note,
                payment_method=woo_order.raw_data.get('payment_method', ''),
                shipping_charge=woo_order.raw_data.get('shipping_charge', 0)
            )

        # Create Invoice instance
        invoice = Invoice.objects.create(
            order=order
        )

        logger.info(f"Invoice created with number: {invoice.invoice_number}")

    except Exception as e:
        logger.error(f"Error creating invoice: {str(e)}")

def create_company(request):
    shopify = 'data'

