from rest_framework.routers import DefaultRouter
from .api import WooCommerceOrderViewSet

router = DefaultRouter()
router.register(r'woocommerce-orders', WooCommerceOrderViewSet)

urlpatterns = router.urls
