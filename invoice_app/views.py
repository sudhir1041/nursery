from django.shortcuts import get_object_or_404
from woocommerce_app.models import WooCommerceOrder
from shopify_app.models import ShopifyOrder
from facebook_app.models import Facebook_orders
from .models import Order, Invoice
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.core.files.base import ContentFile
import json
import logging

from weasyprint import HTML

logger = logging.getLogger(__name__)


def _get_order_data(order_id):
    """Return normalized order data for the given ID from any platform."""
    if WooCommerceOrder.objects.filter(pk=order_id).exists():
        order_source = WooCommerceOrder.objects.get(pk=order_id)
        raw = order_source.raw_data or {}
        return {
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
    if ShopifyOrder.objects.filter(pk=order_id).exists():
        order_source = ShopifyOrder.objects.get(pk=order_id)
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
        return {
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
    if Facebook_orders.objects.filter(pk=order_id).exists():
        order_source = Facebook_orders.objects.get(pk=order_id)
        address = ", ".join(filter(None, [
            order_source.address,
            order_source.city,
            order_source.state,
            order_source.postcode,
            order_source.country,
        ]))
        return {
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
    raise Exception("Order not found in any source")


def _get_or_create_invoice(order_id):
    order_data = _get_order_data(order_id)
    invoice = Invoice.objects.filter(order__order_id=order_data['order_id']).first()
    if invoice:
        return invoice

    order_obj, _ = Order.objects.get_or_create(order_id=order_data['order_id'], defaults=order_data)
    invoice = Invoice.objects.create(order=order_obj)
    return invoice


def create_invoice(request, id):
    """Create an invoice for a given order ID across all platforms."""
    try:
        invoice = _get_or_create_invoice(id)
        logger.info(f"Invoice ready with number: {invoice.invoice_number}")
        return HttpResponse(
            f"Invoice created successfully with number: {invoice.invoice_number}"
        )

    except Exception as e:
        logger.error(f"Error creating invoice: {str(e)}")
        return HttpResponse(f"Error creating invoice: {str(e)}")


def create_company(request):
    shopify = 'data'


def invoice_pdf(request, id):
    """Return a PDF invoice for the given order ID."""
    try:
        invoice = _get_or_create_invoice(id)
        order = invoice.order

        items = order.order_items or []
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except Exception:
                items = []

        subtotal = sum(
            (float(item.get('price', 0)) * float(item.get('quantity', 1)))
            for item in items
        )
        shipping_cost = float(order.shipping_charge or 0)
        total = subtotal + shipping_cost

        html_string = render_to_string(
            'invoice/pdf_template.html',
            {
                'invoice': invoice,
                'items': items,
                'subtotal': subtotal,
                'shipping_cost': shipping_cost,
                'payment_method': order.payment_method,
                'total': total,
            },
        )

        # Use the site root as base URL so static assets resolve correctly
        base_url = request.build_absolute_uri('/')
        pdf_bytes = HTML(string=html_string, base_url=base_url).write_pdf()

        if not invoice.pdf_file:
            invoice.pdf_file.save(
                f"invoice_{invoice.invoice_number}.pdf",
                ContentFile(pdf_bytes),
                save=True,
            )

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response[
            'Content-Disposition'
        ] = f'attachment; filename=invoice_{invoice.invoice_number}.pdf'
        return response

    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}")
        return HttpResponse(f"Error generating invoice PDF: {str(e)}")
