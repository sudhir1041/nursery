from rest_framework.routers import DefaultRouter
from .api import FacebookOrderViewSet

router = DefaultRouter()
router.register(r'facebook-orders', FacebookOrderViewSet)

urlpatterns = router.urls
