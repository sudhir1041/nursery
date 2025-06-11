import json
from django.db import transaction
from django.utils.dateparse import parse_datetime
from .models import Customer, Invoice, InvoiceItem

@transaction.atomic
def create_invoice_from_data(source: str, raw_data: str):
    """
    Parses raw JSON data from a given source (Shopify or WooCommerce)
    and creates the corresponding Customer, Invoice, and InvoiceItem objects.

    Args:
        source (str): The source of the data, either 'shopify' or 'woocommerce'.
        raw_data (str): The raw JSON string of the order.

    Returns:
        Invoice: The newly created Invoice object.
    
    Raises:
        ValueError: If the source is unknown, JSON is invalid, or the invoice already exists.
    """
    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON data provided.")

    if source.lower() == 'shopify':
        if not isinstance(data, list) or not data:
            raise ValueError("Invalid Shopify JSON format. Expected a list with one order.")
        order_data = data[0]
        parsed_data = _parse_shopify_order(order_data)
    elif source.lower() == 'woocommerce':
        if not isinstance(data, dict):
            raise ValueError("Invalid WooCommerce JSON format. Expected a single order object.")
        order_data = data
        parsed_data = _parse_woocommerce_order(order_data)
    else:
        raise ValueError(f"Unknown source: '{source}'. Must be 'shopify' or 'woocommerce'.")

    # Get or create customer
    customer_details = parsed_data['customer']
    customer, _ = Customer.objects.update_or_create(
        email=customer_details['email'],
        defaults={
            'name': customer_details['name'],
            'phone': customer_details.get('phone'),
            'address': customer_details.get('address')
        }
    )

    # Create the invoice
    invoice_details = parsed_data['invoice']
    
    # Check if an invoice with this number already exists
    if Invoice.objects.filter(invoice_number=invoice_details['invoice_number']).exists():
        raise ValueError(f"An invoice with number {invoice_details['invoice_number']} already exists.")

    invoice = Invoice.objects.create(
        customer=customer,
        invoice_number=invoice_details['invoice_number'],
        issue_date=invoice_details['issue_date'],
        due_date=invoice_details['due_date'],
        status=invoice_details['status'],
        notes=f"Imported from {source.capitalize()}. Source Order ID: {invoice_details['invoice_number']}"
    )

    # Create invoice items
    for item_data in parsed_data['items']:
        InvoiceItem.objects.create(
            invoice=invoice,
            description=item_data['description'],
            quantity=item_data['quantity'],
            unit_price=item_data['unit_price']
        )
    
    return invoice

def _parse_shopify_order(data):
    """Parses a single order object from Shopify JSON using only raw data fields."""
    customer_data = data.get('customer', {})
    display_address = data.get('shipping_address') or data.get('billing_address', {})
    
    full_address = "\n".join(filter(None, [
        display_address.get('address1'),
        display_address.get('address2'),
        f"{display_address.get('city', '')} {display_address.get('zip', '')}".strip(),
        f"{display_address.get('province', '')}, {display_address.get('country', '')}".strip()
    ]))

    return {
        'customer': {
            'name': display_address.get('name', '').strip(),
            'email': data.get('contact_email') or customer_data.get('email'),
            'phone': display_address.get('phone'),
            'address': full_address
        },
        'invoice': {
            'invoice_number': data.get('name'),
            'issue_date': parse_datetime(data['created_at']).date(),
            'due_date': parse_datetime(data['created_at']).date(),
            'status': 'PAID' if data.get('financial_status') == 'paid' else 'DRAFT',
        },
        'items': [
            {
                'description': item.get('title', 'N/A'),
                'quantity': item.get('quantity', 1),
                'unit_price': item.get('price', 0)
            }
            for item in data.get('line_items', [])
        ]
    }

def _parse_woocommerce_order(data):
    """Parses a single order object from WooCommerce JSON using only raw data fields."""
    billing_info = data.get('billing', {})
    display_address = data.get('shipping') or billing_info
    
    full_address = "\n".join(filter(None, [
        display_address.get('address_1'),
        display_address.get('address_2'),
        f"{display_address.get('city', '')} {display_address.get('postcode', '')}".strip(),
        f"{display_address.get('state', '')}, {display_address.get('country', '')}".strip()
    ]))

    return {
        'customer': {
            'name': f"{display_address.get('first_name', '')} {display_address.get('last_name', '')}".strip(),
            'email': billing_info.get('email'),
            'phone': billing_info.get('phone'),
            'address': full_address
        },
        'invoice': {
            'invoice_number': str(data.get('number')),
            'issue_date': parse_datetime(data['date_created']).date(),
            'due_date': parse_datetime(data['date_created']).date(),
            'status': 'PAID' if data.get('status') in ['processing', 'completed', 'in-transit', 'paid'] else 'DRAFT',
        },
        'items': [
            {
                'description': item.get('name', 'N/A'),
                'quantity': item.get('quantity', 1),
                'unit_price': item.get('price', 0)
            }
            for item in data.get('line_items', [])
        ]
    }
