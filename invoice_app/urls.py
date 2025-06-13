from django.urls import path
from . import views

app_name = 'invoice_app'

urlpatterns = [
    path('invoice/<int:invoice_id>/download/', views.download_invoice_pdf, name='download_invoice_pdf'),
]