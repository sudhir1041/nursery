from django.urls import path
from . import views


urlpatterns = [
    
    path('webhooks/orders/receive-9a8b7c6d5e/', views.woocommerce_webhook_receiver, name='woocommerce_webhook'),
    path('', views.order_list_view, name='woocommerce_index'),
    path('orders/<int:woo_id>/', views.order_detail_view, name='order_detail'),
    path('orders/<int:woo_id>/edit/', views.order_edit_view, name='order_edit'),
]