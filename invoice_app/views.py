import decimal
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.template.loader import render_to_string

# You will need to install weasyprint: pip install WeasyPrint
from weasyprint import HTML

# Make sure to import your actual models
# from .models import Invoice, InvoiceItem

def download_invoice_pdf(request, invoice_id):
    """
    Generates a PDF from a Tailwind CSS HTML template for a given invoice
    and returns it as a downloadable file.
    """
    # 1. Fetch the required invoice object.
    # get_object_or_404 is a shortcut that raises a 404 error if the object is not found.
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    
    # Assumes your InvoiceItem model has a ForeignKey to Invoice with related_name='items'
    items = invoice.items.all() 

    # 2. Calculate totals directly in the view.
    # This keeps your template clean and focused on presentation.
    subtotal = sum(item.quantity * item.unit_price for item in items)
    
    # Safely get 'shipping_cost' from your Invoice model.
    # Defaults to 0.00 if the field doesn't exist for some reason.
    shipping_cost = getattr(invoice, 'shipping_cost', decimal.Decimal('0.00'))
    total = subtotal + shipping_cost

    # 3. Prepare the full context dictionary to pass to the template.
    # This contains all the dynamic data your HTML template needs.
    context = {
        'invoice': invoice,
        'items': items,
        'subtotal': subtotal,
        'shipping_cost': shipping_cost,
        'total': total,
        # Safely get 'payment_method'. Defaults to 'Not Specified'.
        'payment_method': getattr(invoice, 'payment_method', 'Not Specified'), 
    }

    # 4. Render the HTML template to a string.
    # Replace 'your_invoice_app' with the actual name of your Django app.
    # The template file should be located at:
    # your_invoice_app/templates/your_invoice_app/tailwind_invoice_template.html
    html_string = render_to_string('your_invoice_app/tailwind_invoice_template.html', context)

    # 5. Generate the PDF file in memory using WeasyPrint.
    # The base_url helps WeasyPrint locate external files like images or fonts.
    pdf_file = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf()

    # 6. Create the final HTTP response with the correct headers.
    response = HttpResponse(pdf_file, content_type='application/pdf')
    
    # The Content-Disposition header tells the browser to prompt a download.
    response['Content-Disposition'] = f'attachment; filename="invoice-{invoice.invoice_number}.pdf"'
    
    return response
