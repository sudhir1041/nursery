# invoice/urls.py

from django.urls import path
from .views import invoice_detail_view, create_invoice_view, generate_invoice_pdf

app_name = 'invoice'

urlpatterns = [
    path('create/', create_invoice_view, name='create_invoice'),
    path('<int:invoice_id>/', invoice_detail_view, name='invoice_detail'),
    path('<int:invoice_id>/pdf/', generate_invoice_pdf, name='invoice_pdf'),
]
