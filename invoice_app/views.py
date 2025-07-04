from django.shortcuts import get_object_or_404
from woocommerce_app.models import WooCommerceOrder
from shopify_app.models import ShopifyOrder
from facebook_app.models import Facebook_orders
from .models import Order, Invoice,Company_name
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.core.files.base import ContentFile
import json
import logging

from weasyprint import HTML

logger = logging.getLogger(__name__)


def _get_order_data(order_id):
    """Return normalized order data for the given ID from any platform."""

    order_id_str = str(order_id)

    # Shopify: IDs start with # or @# (e.g. #1234, @#LE1234)
    if order_id_str.startswith('#') or order_id_str.startswith('@#'):
        order_source = get_object_or_404(ShopifyOrder, name=order_id_str)
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
            'order_date' : order_source.created_at_shopify,
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

    # Facebook: IDs start with NS (e.g. NS202398)
    elif order_id_str.startswith('NS'):
        order_source = get_object_or_404(Facebook_orders, order_id=order_id_str)
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
            'order_date' : order_source.date_created,
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

    # WooCommerce: Integer or UUID as PK
    elif WooCommerceOrder.objects.filter(pk=order_id).exists():
        order_source = WooCommerceOrder.objects.get(pk=order_id)
        raw = order_source.raw_data or {}
        return {
            'order_id': str(order_source.woo_id),
            'customer_name': f"{order_source.billing_first_name} {order_source.billing_last_name}".strip(),
            'customer_address': f"{order_source.billing_address_1}, {order_source.billing_address_2}, {order_source.billing_city}, {order_source.billing_state}, {order_source.billing_postcode}, {order_source.billing_country}",
            'customer_email': order_source.billing_email,
            'order_date' : order_source.date_created_woo,
            'customer_phone': order_source.billing_phone,
            'order_total': order_source.total_amount or 0,
            'order_status': order_source.status,
            'order_items': order_source.line_items_json or {},
            'order_shipment_status': order_source.shipment_status,
            'order_notes': order_source.customer_note,
            'payment_method': raw.get('payment_method', ''),
            'shipping_charge': raw.get('shipping_charge', 0),
        }

    # Optional: Facebook fallback if PK matches (not recommended unless you use integer PKs for Facebook orders)
    elif Facebook_orders.objects.filter(pk=order_id).exists():
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
            'order_date' : order_source.date_created,
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
    
    # Get or create the Order object
    order_obj, created = Order.objects.get_or_create(
        order_id=order_data['order_id'], defaults=order_data
    )

    # If not created, update all relevant fields (including order_date)
    if not created:
        for field, value in order_data.items():
            if hasattr(order_obj, field):
                setattr(order_obj, field, value)
        order_obj.save()

    # Now get or create the invoice for this order
    invoice, _ = Invoice.objects.get_or_create(order=order_obj)
    return invoice


def create_invoice(request, id):
    """Create an invoice for a given order ID across all platforms."""
    try:
        invoice = _get_or_create_invoice(id)
        # Generate PDF after creating invoice
        invoice_pdf(request, id)
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

        # Check if PDF already exists and return it
        if invoice.pdf_file:
            with invoice.pdf_file.open('rb') as f:
                pdf_content = f.read()
            response = HttpResponse(pdf_content, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename=invoice_{invoice.invoice_number}.pdf'
            return response

        # If PDF doesn't exist, generate it
        order = invoice.order
        order_data = _get_order_data(id)

        # --- START: Corrected items block ---
        items = order.order_items or []

        if isinstance(items, str):
            try:
                items = json.loads(items)
            except Exception:
                items = []

        if isinstance(items, dict):
            items = [v for v in items.values() if isinstance(v, dict)]

        if not (isinstance(items, list) and all(isinstance(i, dict) for i in items)):
            items = []
        # --- END: Corrected items block ---

        subtotal = sum(
            (float(item.get('price', 0)) * float(item.get('quantity', 1)))
            for item in items
        )
        shipping_cost = float(order.shipping_charge or 0)
        total = subtotal + shipping_cost

        # Get company info
        company = Company_name.objects.first()
        context = {
            'invoice': invoice,
            'invoice_number': invoice.invoice_number,
            'invoice_date': invoice.created_at.strftime('%Y-%m-%d'),
            'order_date': order.order_date.strftime('%Y-%m-%d'),
            'order_data': order_data,
            'items': items,
            'subtotal': subtotal,
            'shipping_cost': shipping_cost,
            'payment_method': order.payment_method,
            'total': total,
            'company_name': company.company_name if company else 'Your Company Name',
            'company_address': company.company_address if company else '',
            'company_contact': f"Phone: {company.company_phone}\nEmail: {company.company_email}" if company else '',
            'company_email': company.company_email if company else '',
            'social_media': company.company_website if company else '',
            'logo_url': request.build_absolute_uri(company.company_logo.url) if company and company.company_logo else request.build_absolute_uri('/static/images/logo.png'),
        }

        html_string = render_to_string('invoice/pdf_template.html', context)

        base_url = request.build_absolute_uri('/')
        pdf_bytes = HTML(string=html_string, base_url=base_url).write_pdf()

        # Save PDF file
        invoice.pdf_file.save(
            f"invoice_{invoice.invoice_number}.pdf",
            ContentFile(pdf_bytes),
            save=True,
        )

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename=invoice_{invoice.invoice_number}.pdf'
        return response

    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}")
        return HttpResponse(f"Error generating invoice PDF: {str(e)}")
