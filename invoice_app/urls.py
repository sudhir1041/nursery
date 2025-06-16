from django.urls import path
from . import views

app_name = 'invoice_app'

urlpatterns = [
    path('create_invoice/<str:id>/', views.create_invoice, name='create_invoice'),
    path('invoice_pdf/<str:id>/', views.invoice_pdf, name='invoice_pdf'),
]
