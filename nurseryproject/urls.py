from django.contrib import admin
from django.urls import path, include
admin.site.site_header = "Nursery Nisarga"
admin.site.site_title = "Admin"
admin.site.index_title = "Welcome Admin"
from . import views  

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.dashboard_view, name='dashboard'),
    path('orders', views.all_orders_view, name='orders'),
    path('order_deatils_view/<str:order_id>',views.order_details_view,name='order_details_view'),
    path('orders/<str:order_id>',views.all_orders_edit, name='all_order_edit'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('woocommerce/', include('woocommerce_app.urls')),
    path('shopify/', include('shopify_app.urls')),
    path('facebook/', include('facebook_app.urls')),
    path('whatsapp/', include('whatsapp_app.urls', namespace='whatsapp_app')),
    path('shipment/',include('shipment_app.urls')),
    path('invoice/', include('invoice_app.urls', namespace='invoice_app')),
]