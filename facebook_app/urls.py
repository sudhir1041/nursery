from django.contrib import admin
from django.urls import path
from .views import *

urlpatterns = [
     path('',facebook_order_list_view,name='facebook_index'),
     path('orders/create/', facebook_order_create_view, name='facebook_order_create'),
     path('orders/<str:order_id>/', facebook_order_detail_view, name='facebook_order_detail'),
     path('orders/<str:order_id>/edit/', facebook_order_edit_view, name='facebook_order_edit'),
     path('orders/<str:order_id>/delete/', FacebookOrderDeleteView.as_view(), name='facebook_order_delete'),
]
