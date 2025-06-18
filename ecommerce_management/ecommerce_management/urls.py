from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/settings/', include('settings_app.urls')),
    path('api/whatsapp/', include('whatsapp_app.api_urls')),
    path('api/facebook/', include('facebook_app.api_urls')),
    path('api/shopify/', include('shopify_app.api_urls')),
    path('api/woocommerce/', include('woocommerce_app.api_urls')),
    path('api/invoice/', include('invoice_app.api_urls')),
]
