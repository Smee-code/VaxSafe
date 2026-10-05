"""Keeps the current request available to model signals so audit entries know who made a change."""
import threading

from django.http import JsonResponse

_state = threading.local()


def get_current_request():
    return getattr(_state, 'request', None)


def get_current_user():
    request = get_current_request()
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        return user
    return None


def get_client_ip(request=None):
    request = request or get_current_request()
    if request is None:
        return None
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class CurrentRequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _state.request = request
        try:
            return self.get_response(request)
        finally:
            _state.request = None


def is_modal_request(request):
    """Forms opened in a dialog are fetched with this header and rendered without the page shell."""
    return request is not None and request.headers.get('X-Modal') == '1'


class ModalRedirectMiddleware:
    """A form saved inside a dialog should not follow its redirect inside the fetch.
    Hand the destination back as JSON so the page can open the next form or navigate."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if is_modal_request(request) and response.status_code in (301, 302, 303):
            return JsonResponse({'redirect': response['Location']})
        return response
