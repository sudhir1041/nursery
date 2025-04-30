from django.urls import path
from . import views

urlpatterns = [
    path('webhooks/receive-shopify-e5d4f3c2b1/', views.shopify_webhook_receiver, name='shopify_webhook'),
    path('', views.shopify_order_list_view, name='shopify_index'),
    path('orders/<int:shopify_id>/', views.shopify_order_detail_view, name='shopify_order_detail'),
    path('orders/<int:shopify_id>/edit/', views.shopify_order_edit_view, name='shopify_order_edit'),
]