from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone

from core.models import AuditLog, Barangay, CenterSettings, ExposureCategory
from core.signals import log_event
from core.utils import get_date_param, get_int_param
from inventory.models import StorageUnit

from .builders import Filters
from .exporters import excel_response, pdf_response
from .registry import REPORTS, available_reports, can_view


def parse_filters(request, center):
    today = timezone.localdate()
    date_from = get_date_param(request, 'date_from', date(today.year, 1, 1))
    date_to = get_date_param(request, 'date_to', today)
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    barangay_id = get_int_param(request, 'barangay')
    category_id = get_int_param(request, 'category')
    unit_id = get_int_param(request, 'unit')
    days = get_int_param(request, 'days', center.expiry_warning_days)
    return Filters(
        date_from=date_from,
        date_to=date_to,
        barangay=Barangay.objects.filter(pk=barangay_id).first() if barangay_id else None,
        category=ExposureCategory.objects.filter(pk=category_id).first() if category_id else None,
        unit=StorageUnit.objects.filter(pk=unit_id).first() if unit_id else None,
        days=max(1, min(days, 3650)),
    )


@login_required
def report_index(request):
    available = available_reports(request.user)
    if not available:
        raise PermissionDenied
    return redirect('reports:report', key=next(iter(available)))


@login_required
def report_view(request, key):
    if key not in REPORTS:
        raise Http404
    if not can_view(request.user, key):
        raise PermissionDenied
    spec = REPORTS[key]
    center = CenterSettings.load()
    filters = parse_filters(request, center)
    report = spec['builder'](filters)
    filter_text = filters.describe(spec['filters'])

    export = request.GET.get('export')
    if export in ('xlsx', 'pdf'):
        log_event(AuditLog.Action.EXPORT, label=f'{report.title} report ({export.upper()})',
                  changes={'filters': {'new': ' · '.join(filter_text)}})
        respond = excel_response if export == 'xlsx' else pdf_response
        return respond(report, filter_text, center, request.user)

    query = request.GET.copy()
    query.pop('export', None)
    return render(request, 'reports/report.html', {
        'key': key,
        'spec': spec,
        'report': report,
        'filters': filters,
        'filter_text': filter_text,
        'available': available_reports(request.user),
        'barangays': Barangay.objects.all(),
        'categories': ExposureCategory.objects.all(),
        'units': StorageUnit.objects.all(),
        'query': query.urlencode(),
        'generated': timezone.localtime(),
    })
