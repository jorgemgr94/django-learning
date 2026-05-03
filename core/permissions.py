from typing import Any

from rest_framework import permissions
from rest_framework.request import Request


class IsOwnerOrganizationOrReadOnly(permissions.BasePermission):
    """
    Object-level permission to only allow owners of an organization to edit it.
    Assumes the user model has an 'organization' relation.
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        # Standard check: user must be authenticated for any write action
        if request.method in permissions.SAFE_METHODS:
            return True

        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request: Request, view: Any, obj: Any) -> bool:
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed if the pet/org belongs to
        # the user's organizations
        profile = getattr(request.user, "profile", None)
        if not profile:
            return False

        user_orgs = profile.organizations.all()

        # If checking a Pet, compare with pet.organization
        if hasattr(obj, "organization"):
            return obj.organization in user_orgs

        # If checking an Organization itself
        return obj in user_orgs
