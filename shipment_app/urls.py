
from django.urls import path
from . import views

urlpatterns = [
    path('',views.home,name='shipment_index')
]