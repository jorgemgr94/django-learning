from rest_framework.routers import DefaultRouter

from .views import OrganizationViewSet, PetViewSet

router = DefaultRouter()
router.register("organizations", OrganizationViewSet, basename="organization")
router.register("pets", PetViewSet, basename="pet")

urlpatterns = router.urls
