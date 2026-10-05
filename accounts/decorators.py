from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import User

STAFF = User.Role.STAFF
PERSONNEL = User.Role.PERSONNEL
ALL_ROLES = (User.Role.ADMIN, STAFF, PERSONNEL)


def role_required(*roles):
    """Allow only users whose role is listed. Administrators can always get in."""

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped(request, *args, **kwargs):
            user = request.user
            if user.is_admin or user.role in roles:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return wrapped
    return decorator


admin_required = role_required()
clinical_required = role_required(STAFF)
