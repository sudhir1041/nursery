from django.urls import path
from . import views

urlpatterns = [
    path('invoice/<int:invoice_id>/download/', views.download_invoice_pdf, name='download_invoice_pdf'),
]