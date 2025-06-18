from django.shortcuts import get_object_or_404
from woocommerce_app.models import WooCommerceOrder
from shopify_app.models import ShopifyOrder
from facebook_app.models import Facebook_orders
from .models import Order, Invoice, Company_name
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.core.files.base import ContentFile
import json
import logging

from weasyprint import HTML

logger = logging.getLogger(__name__)


def _get_order_data(order_identifier):
    """
    Return normalized order data for the given identifier from any platform.
    The 'order_identifier' should be the external ID (e.g., woo_id, shopify_id, facebook_order_id).
    This function now intelligently handles different ID types (integer for WooCommerce,
    string for Shopify and Facebook) by attempting conversion when necessary.
    """
    order_identifier_str = str(order_identifier) # Ensure identifier is treated as string initially

    # Attempt to convert to integer for WooCommerce if the identifier looks like a number.
    # This is crucial because WooCommerce 'woo_id' is typically an IntegerField.
    woo_id_int = None
    try:
        woo_id_int = int(order_identifier_str)
    except ValueError:
        # If conversion fails, it's not a valid integer, so it cannot be a WooCommerce woo_id.
        # We'll keep woo_id_int as None and skip the WooCommerce lookup.
        pass

    order_source = None

    # 1. Check WooCommerce orders using 'woo_id' field.
    # Only attempt lookup if the identifier was successfully converted to an integer.
    if woo_id_int is not None:
        order_source = WooCommerceOrder.objects.filter(woo_id=woo_id_int).first()
        if order_source:
            raw = order_source.raw_data or {}
            return {
                'order_id': str(order_source.woo_id), # Store as string in the common Order model
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

    # 2. Check Shopify orders using 'shopify_id' field.
    # Shopify IDs are typically strings, so we use order_identifier_str directly.
    order_source = ShopifyOrder.objects.filter(shopify_id=order_identifier_str).first()
    if order_source:
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
            'order_id': str(order_source.shopify_id), # Store as string in the common Order model
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

    # 3. Check Facebook orders using 'order_id' field.
    # Facebook IDs are also typically strings, so we use order_identifier_str directly.
    order_source = Facebook_orders.objects.filter(order_id=order_identifier_str).first()
    if order_source:
        address = ", ".join(filter(None, [
            order_source.address,
            order_source.city,
            order_source.state,
            order_source.postcode,
            order_source.country,
        ]))
        return {
            'order_id': order_source.order_id, # Store as string in the common Order model
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

    # If no order is found across all sources, raise an exception.
    raise Exception(f"Order with identifier '{order_identifier}' not found in any source")


def _get_or_create_invoice(order_identifier):
    """
    Retrieves or creates an invoice for a given order identifier.
    Ensures order_identifier is passed as a string to _get_order_data.
    """
    order_data = _get_order_data(str(order_identifier)) # Ensure identifier is string for _get_order_data
    invoice = Invoice.objects.filter(order__order_id=order_data['order_id']).first()
    if invoice:
        return invoice

    # Ensure order_id field in your common Order model is a CharField
    # to accommodate IDs from different platforms (integers as strings, or alphanumeric strings).
    order_obj, created = Order.objects.get_or_create(order_id=order_data['order_id'], defaults={
        'customer_name': order_data.get('customer_name', ''),
        'customer_address': order_data.get('customer_address', ''),
        'customer_email': order_data.get('customer_email', ''),
        'customer_phone': order_data.get('customer_phone', ''),
        'order_total': order_data.get('order_total', 0),
        'order_status': order_data.get('order_status', ''),
        'order_items': order_data.get('order_items', []),
        'order_shipment_status': order_data.get('order_shipment_status', ''),
        'order_notes': order_data.get('order_notes', ''),
        'payment_method': order_data.get('payment_method', ''),
        'shipping_charge': order_data.get('shipping_charge', 0),
        # Assuming order_date is handled correctly or can be defaulted
        'order_date': order_data.get('order_date') # Make sure this key exists if expected
    })
    
    # If the order was just created, logger.info for debugging
    if created:
        logger.info(f"New Order object created for ID: {order_data['order_id']}")

    invoice = Invoice.objects.create(order=order_obj)
    return invoice


def create_invoice(request, id):
    """Create an invoice for a given order ID across all platforms."""
    try:
        # Pass the ID directly as it might be the external string identifier
        invoice = _get_or_create_invoice(id)
        # Generate PDF after creating invoice
        # Note: invoice_pdf function will handle saving the PDF to the invoice object
        response_pdf = invoice_pdf(request, id) 
        
        # Check if the PDF generation was successful and return its response.
        # If it's an HttpResponse (meaning PDF was served), return it.
        if isinstance(response_pdf, HttpResponse):
            logger.info(f"Invoice and PDF generated successfully for order ID: {id} with invoice number: {invoice.invoice_number}")
            return response_pdf
        else:
            # If invoice_pdf didn't return an HttpResponse, something went wrong internally
            # or it simply saved the PDF without serving it immediately.
            logger.info(f"Invoice created successfully with number: {invoice.invoice_number}. PDF generation status unclear or saved internally.")
            return HttpResponse(
                f"Invoice created successfully with number: {invoice.invoice_number}. PDF generated and saved."
            )

    except Exception as e:
        logger.error(f"Error creating invoice for ID {id}: {str(e)}")
        return HttpResponse(f"Error creating invoice: {str(e)}")


def create_company(request):
    """Placeholder function for creating company data."""
    # This function was empty in the original code, leaving as-is.
    shopify = 'data'


def invoice_pdf(request, id):
    """Return a PDF invoice for the given order ID."""
    try:
        # Pass the ID directly as it might be the external string identifier
        invoice = _get_or_create_invoice(id)

        # Check if PDF already exists and return it
        if invoice.pdf_file:
            with invoice.pdf_file.open('rb') as f:
                pdf_content = f.read()
            response = HttpResponse(pdf_content, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename=invoice_{invoice.invoice_number}.pdf'
            logger.info(f"Returning existing PDF for invoice: {invoice.invoice_number}")
            return response

        # If PDF doesn't exist, generate it
        order = invoice.order
        order_data = _get_order_data(id) # Use the original 'id' directly for fetching order details

        # --- START: Corrected items block ---
        # This section handles parsing order_items from various formats (JSON string, dict, list)
        items = order.order_items or []

        if isinstance(items, str):
            try:
                items = json.loads(items)
            except json.JSONDecodeError: # More specific exception for JSON decoding errors
                logger.warning(f"Could not decode order items JSON for order {order.order_id}: {items}")
                items = []
            except Exception as e: # Catch any other unexpected errors during string processing
                logger.error(f"Unexpected error processing order items (string) for order {order.order_id}: {e}")
                items = []

        # If after potential JSON decoding, 'items' is a dictionary, convert its values to a list.
        # This handles cases where line_items_json might store items as a dict with numeric keys.
        if isinstance(items, dict):
            items = [v for v in items.values() if isinstance(v, dict)]

        # Final validation to ensure 'items' is a list of dictionaries, defaulting to empty list if not.
        if not (isinstance(items, list) and all(isinstance(i, dict) for i in items)):
            logger.error(f"Order items for order {order.order_id} are not in expected list of dicts format. Actual: {items}")
            items = []
        # --- END: Corrected items block ---

        # Calculate subtotal, ensuring numeric values are handled correctly, defaulting to 0 if missing or invalid.
        subtotal = sum(
            (float(item.get('price', 0) or 0) * float(item.get('quantity', 1) or 1))
            for item in items
        )
        shipping_cost = float(order.shipping_charge or 0) # Ensure shipping_charge is treated as a float
        total = subtotal + shipping_cost

        # Get company info for the invoice template
        company = Company_name.objects.first()
        context = {
            'invoice': invoice,
            'invoice_number': invoice.invoice_number,
            'invoice_date': invoice.created_at.strftime('%Y-%m-%d'),
            'order_date': order.order_date.strftime('%Y-%m-%d') if order.order_date else '',
            'order_data': order_data, # Contains the normalized order details
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
            # Build absolute URL for logo to ensure it works correctly in PDF generation
            'logo_url': request.build_absolute_uri(company.company_logo.url) if company and company.company_logo else request.build_absolute_uri('/static/images/logo.png'),
        }

        # Render the HTML template to a string
        html_string = render_to_string('invoice/pdf_template.html', context)

        # Generate PDF using WeasyPrint
        # Use request.build_absolute_uri('/') as base_url for resolving relative paths in HTML
        base_url = request.build_absolute_uri('/')
        pdf_bytes = HTML(string=html_string, base_url=base_url).write_pdf()

        # Save the generated PDF file to the Invoice model's pdf_file field
        invoice.pdf_file.save(
            f"invoice_{invoice.invoice_number}.pdf",
            ContentFile(pdf_bytes),
            save=True, # Ensure the model instance is saved after file attachment
        )
        logger.info(f"Generated and saved PDF for invoice: {invoice.invoice_number}")

        # Prepare and return the HTTP response with the PDF content
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename=invoice_{invoice.invoice_number}.pdf'
        return response

    except Exception as e:
        logger.error(f"Error generating invoice PDF for ID {id}: {str(e)}")
        return HttpResponse(f"Error generating invoice PDF: {str(e)}")

