from django.urls import path
from . import views

app_name = 'invoice_app'

urlpatterns = [
    path('create_invoice/<int:id>/', views.create_invoice, name='create_invoice'),
]
