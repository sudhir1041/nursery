from django.urls import path
from . import views

#app_name = 'shipment'

urlpatterns = [
    path('',views.home,name='shipment_index'),
    path('process-shipment/', views.process_shipment, name='process_shipment'),
    # path('clone-order/<str:order_id>/', views.clone_order, name='clone_order_detail'),
]