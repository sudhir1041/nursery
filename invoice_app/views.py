# invoice/views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa

from .models import Invoice
from .utils import create_invoice_from_data

# This callback is necessary for xhtml2pdf to find images via URL
def link_callback(uri, rel):
    """
    Handle external URLs for images.
    """
    # Allows http and https links
    if uri.startswith('https://') or uri.startswith('http://'):
        return uri
    # In case you had local static files, this would handle them, but for now we only need the URL part.
    return uri


def create_invoice_view(request):
    """
    Renders the invoice creation form and handles its submission.
    """
    if request.method == 'POST':
        source = request.POST.get('source')
        raw_data = request.POST.get('raw_data')

        if not source or not raw_data:
            messages.error(request, 'Source and JSON data are required.')
            return render(request, 'invoice/create_invoice.html')
        
        try:
            invoice = create_invoice_from_data(source, raw_data)
            messages.success(request, f'Successfully created invoice {invoice.invoice_number}.')
            return redirect('invoice:invoice_detail', invoice_id=invoice.id)
        except ValueError as e:
            messages.error(request, str(e))
    
    return render(request, 'invoice/create_invoice.html')


def invoice_detail_view(request, invoice_id):
    """
    Displays a single, detailed invoice page.
    """
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    subtotal = invoice.get_total()
    shipping_cost = 0.00
    total = subtotal + shipping_cost

    context = {
        'invoice': invoice,
        'subtotal': subtotal,
        'shipping_cost': "Free Shipping" if shipping_cost == 0 else f"₹{shipping_cost:.2f}",
        'total': total,
        'payment_method': "Credit Card/Debit Card/NetBanking" if invoice.status == 'PAID' else "Pending Payment",
    }
    
    return render(request, 'invoice/invoice_detail.html', context)


def generate_invoice_pdf(request, invoice_id):
    """
    Generates and serves a PDF version of the invoice.
    """
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    subtotal = invoice.get_total()
    shipping_cost = 0.00
    total = subtotal + shipping_cost

    context = {
        'invoice': invoice,
        'subtotal': subtotal,
        'shipping_cost': "Free Shipping" if shipping_cost == 0 else f"₹{shipping_cost:.2f}",
        'total': total,
        'payment_method': "Credit Card/Debit Card/NetBanking" if invoice.status == 'PAID' else "Pending Payment",
    }

    # Render the HTML template for the PDF
    template = get_template('invoice/pdf_template.html')
    html = template.render(context)
    
    # Create the PDF response
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice_{invoice.invoice_number}.pdf"'
    
    # Create the PDF using pisa, passing the link_callback
    pisa_status = pisa.CreatePDF(
       html, dest=response, link_callback=link_callback)
    
    if pisa_status.err:
       return HttpResponse('We had some errors creating the PDF <pre>' + html + '</pre>')
    return response
