from rest_framework.routers import DefaultRouter
from .views import CredentialViewSet

router = DefaultRouter()
router.register(r'', CredentialViewSet)

urlpatterns = router.urls
