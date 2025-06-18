from rest_framework.routers import DefaultRouter
from .api import ShopifyOrderViewSet

router = DefaultRouter()
router.register(r'shopify-orders', ShopifyOrderViewSet)

urlpatterns = router.urls
