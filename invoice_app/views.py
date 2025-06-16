from django.shortcuts import get_object_or_404
from woocommerce_app.models import WooCommerceOrder
from shopify_app.models import ShopifyOrder
from facebook_app.models import Facebook_orders
from .models import Order, Invoice
from django.http import HttpResponse
import logging

logger = logging.getLogger(__name__)


def create_invoice(request, id):
    """Create an invoice for a given order ID across all platforms."""
    try:
        order_data = None

        if WooCommerceOrder.objects.filter(pk=id).exists():
            order_source = WooCommerceOrder.objects.get(pk=id)
            raw = order_source.raw_data or {}
            order_data = {
                'order_id': str(order_source.woo_id),
                'customer_name': f"{order_source.billing_first_name} {order_source.billing_last_name}".strip(),
                'customer_address': f"{order_source.billing_address_1}, {order_source.billing_address_2}, {order_source.billing_city}, {order_source.billing_state}, {order_source.billing_postcode}, {order_source.billing_country}",
                'customer_email': order_source.billing_email,
                'customer_phone': order_source.billing_phone,
                'order_total': order_source.total_amount or 0,
                'order_status': order_source.status,
                'order_items': order_source.line_items_json or {},
                'order_shipment_status': order_source.shipment_status,
                'order_notes': order_source.customer_note,
                'payment_method': raw.get('payment_method', ''),
                'shipping_charge': raw.get('shipping_charge', 0),
            }
        elif ShopifyOrder.objects.filter(pk=id).exists():
            order_source = ShopifyOrder.objects.get(pk=id)
            shipping = order_source.shipping_address_json or {}
            raw = order_source.raw_data or {}
            address = ", ".join(filter(None, [
                shipping.get('address1'),
                shipping.get('address2'),
                shipping.get('city'),
                shipping.get('province'),
                shipping.get('zip'),
                shipping.get('country'),
            ]))
            order_data = {
                'order_id': str(order_source.shopify_id),
                'customer_name': shipping.get('name', '').strip(),
                'customer_address': address,
                'customer_email': order_source.email,
                'customer_phone': shipping.get('phone'),
                'order_total': order_source.total_price or 0,
                'order_status': order_source.financial_status or '',
                'order_items': order_source.line_items_json or {},
                'order_shipment_status': order_source.shipment_status,
                'order_notes': order_source.internal_notes,
                'payment_method': raw.get('payment_method', ''),
                'shipping_charge': raw.get('shipping_charge', 0),
            }
        elif Facebook_orders.objects.filter(pk=id).exists():
            order_source = Facebook_orders.objects.get(pk=id)
            address = ", ".join(filter(None, [
                order_source.address,
                order_source.city,
                order_source.state,
                order_source.postcode,
                order_source.country,
            ]))
            order_data = {
                'order_id': order_source.order_id,
                'customer_name': f"{order_source.first_name} {order_source.last_name}".strip(),
                'customer_address': address,
                'customer_email': order_source.email,
                'customer_phone': order_source.phone,
                'order_total': order_source.total_amount or 0,
                'order_status': order_source.status,
                'order_items': order_source.products_json or {},
                'order_shipment_status': order_source.shipment_status,
                'order_notes': order_source.customer_note,
                'payment_method': order_source.mode_of_payment or '',
                'shipping_charge': order_source.shipment_amount or 0,
            }
        else:
            raise Exception("Order not found in any source")

        existing_invoice = Invoice.objects.filter(order__order_id=order_data['order_id']).first()
        if existing_invoice:
            logger.info(f"Invoice already exists with number: {existing_invoice.invoice_number}")
            return HttpResponse(f"Invoice already exists with number: {existing_invoice.invoice_number}")

        order_obj, _ = Order.objects.get_or_create(order_id=order_data['order_id'], defaults=order_data)

        invoice = Invoice.objects.create(order=order_obj)
        logger.info(f"Invoice created with number: {invoice.invoice_number}")
        return HttpResponse(f"Invoice created successfully with number: {invoice.invoice_number}")

    except Exception as e:
        logger.error(f"Error creating invoice: {str(e)}")
        return HttpResponse(f"Error creating invoice: {str(e)}")


def create_company(request):
    shopify = 'data'
