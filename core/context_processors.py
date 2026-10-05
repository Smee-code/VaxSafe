from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone

from .middleware import is_modal_request
from .models import CenterSettings


def vaxsafe(request):
    try:
        center = CenterSettings.load()
    except (OperationalError, ProgrammingError):  # Database not migrated yet.
        return {}
    is_modal = is_modal_request(request)
    context = {'center': center, 'today': timezone.localdate(), 'is_modal': is_modal}
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated and not is_modal:
        from .alerts import get_alerts
        context['alerts'] = get_alerts(center)
    return context
