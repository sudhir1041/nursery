from rest_framework.routers import DefaultRouter
from .api import ContactViewSet

router = DefaultRouter()
router.register(r'contacts', ContactViewSet)

urlpatterns = router.urls
