import json
from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone

# Assuming these are your generic invoice models
# from your_invoice_app.models import Customer, Invoice, InvoiceItem

# Source-specific order models
from shopify_app.models import ShopifyOrder
from woocommerce_app.models import WooCommerceOrder
from facebook_app.models import Facebook_orders


@transaction.atomic
def create_invoice_from_data(source: str, raw_data: str):
    """
    Parses raw JSON order data from a given source, saves the raw order
    to its source-specific model, and then creates the corresponding generic
    Customer, Invoice, and InvoiceItem objects.

    This ensures the original data is preserved before being transformed.

    Args:
        source (str): The source of the data ('shopify', 'woocommerce', or 'facebook').
        raw_data (str): The raw JSON string of the order.

    Returns:
        Invoice: The newly created Invoice object.

    Raises:
        ValueError: If the source is unknown, JSON is invalid, the data format
                    is incorrect for the source, or the invoice already exists.
    """
    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON data provided.")

    source = source.lower()
    source_order_record = None
    parsed_data = None

    if source == 'shopify':
        if not isinstance(data, list) or not data:
            raise ValueError("Invalid Shopify JSON format. Expected a list with one order.")
        order_data = data[0]
        # Create a record in the ShopifyOrder table to store the raw data
        source_order_record = ShopifyOrder.objects.create(raw_data_payload=order_data)
        parsed_data = _parse_shopify_order(order_data)

    elif source == 'woocommerce':
        if not isinstance(data, dict):
            raise ValueError("Invalid WooCommerce JSON format. Expected a single order object.")
        order_data = data
        # Create a record in the WooCommerceOrder table to store the raw data
        source_order_record = WooCommerceOrder.objects.create(raw_data_payload=order_data)
        parsed_data = _parse_woocommerce_order(order_data)

    elif source == 'facebook':
        if not isinstance(data, dict):
            raise ValueError("Invalid Facebook JSON format. Expected a single order object.")
        order_data = data
        # Create a record in the Facebook_orders table to store the raw data
        source_order_record = Facebook_orders.objects.create(raw_data_payload=order_data)
        parsed_data = _parse_facebook_order(order_data)
        
    else:
        raise ValueError(f"Unknown source: '{source}'. Must be 'shopify', 'woocommerce', or 'facebook'.")

    # Get or create customer from parsed data
    customer_details = parsed_data['customer']
    customer, _ = Customer.objects.update_or_create(
        email=customer_details['email'],
        defaults={
            'name': customer_details['name'],
            'phone': customer_details.get('phone'),
            'address': customer_details.get('address')
        }
    )

    # Create the generic invoice
    invoice_details = parsed_data['invoice']
    
    # Check if an invoice with this number already exists to prevent duplicates
    if Invoice.objects.filter(invoice_number=invoice_details['invoice_number']).exists():
        raise ValueError(f"An invoice with number {invoice_details['invoice_number']} already exists.")

    invoice = Invoice.objects.create(
        customer=customer,
        invoice_number=invoice_details['invoice_number'],
        issue_date=invoice_details['issue_date'],
        due_date=invoice_details['due_date'],
        status=invoice_details['status'],
        notes=f"Imported from {source.capitalize()}. Source Record ID: {source_order_record.id}"
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
    """Parses a single order object from Shopify JSON into a standardized format."""
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
            'name': display_address.get('name', 'N/A').strip(),
            'email': data.get('contact_email') or customer_data.get('email'),
            'phone': display_address.get('phone'),
            'address': full_address
        },
        'invoice': {
            'invoice_number': data.get('name', 'N/A'),
            'issue_date': parse_datetime(data['created_at']).date(),
            'due_date': parse_datetime(data['created_at']).date(), # Defaulting due_date to issue_date
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
    """Parses a single order object from WooCommerce JSON into a standardized format."""
    billing_info = data.get('billing', {})
    shipping_info = data.get('shipping', {})
    
    # Prefer shipping address for name and address details if available
    display_address = shipping_info if shipping_info.get('address_1') else billing_info
    
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
            'invoice_number': str(data.get('number', 'N/A')),
            'issue_date': parse_datetime(data['date_created']).date(),
            'due_date': parse_datetime(data['date_created']).date(), # Defaulting due_date to issue_date
            'status': 'PAID' if data.get('status') in ['processing', 'completed', 'paid'] else 'DRAFT',
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

def _parse_facebook_order(data):
    """
    Parses a single order object from Facebook Marketplace JSON into a standardized format.
    NOTE: This is based on a presumed structure for Facebook order data. You may need to
    adjust the field names based on the actual JSON you receive.
    """
    shipping_address = data.get('shipping_address', {})
    buyer_details = data.get('buyer', {})

    full_address = "\n".join(filter(None, [
        shipping_address.get('street_1'),
        shipping_address.get('street_2'),
        f"{shipping_address.get('city', '')} {shipping_address.get('postal_code', '')}".strip(),
        f"{shipping_address.get('state', '')}, {shipping_address.get('country', '')}".strip()
    ]))
    
    # Use a fallback for issue date if 'created_time' isn't present
    issue_date = parse_datetime(data['created_time']).date() if 'created_time' in data else timezone.now().date()

    return {
        'customer': {
            'name': shipping_address.get('name', 'N/A').strip(),
            'email': buyer_details.get('email'),
            'phone': buyer_details.get('phone'), # Assuming phone might be available here
            'address': full_address
        },
        'invoice': {
            'invoice_number': data.get('order_id', 'N/A'),
            'issue_date': issue_date,
            'due_date': issue_date, # Defaulting due_date to issue_date
            'status': 'PAID' if data.get('order_status') == 'PAID' else 'DRAFT',
        },
        'items': [
            {
                'description': item.get('product_name', 'N/A'),
                'quantity': item.get('quantity', 1),
                'unit_price': item.get('amount', {}).get('amount', 0)
            }
            for item in data.get('items', [])
        ]
    }
