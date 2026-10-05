from django.core.paginator import Paginator
from django.utils.dateparse import parse_date


def paginate(request, queryset, per_page=25):
    return Paginator(queryset, per_page).get_page(request.GET.get('page'))


def get_date_param(request, name, default=None):
    value = request.GET.get(name, '')
    try:
        return parse_date(value) or default
    except ValueError:
        return default


def get_int_param(request, name, default=None):
    try:
        return int(request.GET.get(name, ''))
    except (TypeError, ValueError):
        return default
