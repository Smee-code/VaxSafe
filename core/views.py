import os
import sqlite3
import tempfile
from datetime import date, timedelta
from io import StringIO

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.management import call_command
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required
from accounts.models import User
from clinic.models import Dose, Patient, Visit
from inventory.forms import StorageUnitForm, VaccineTypeForm
from inventory.models import StockMovement, StorageUnit, VaccineType
from reports import builders

from .forms import BarangayForm, CenterSettingsForm, ExposureCategoryForm
from .models import AuditLog, Barangay, CenterSettings, ExposureCategory
from .signals import log_event
from .utils import get_date_param, get_int_param, paginate


# Dashboards ----------------------------------------------------------------

@login_required
def dashboard(request):
    today = timezone.localdate()
    if request.user.is_personnel:
        return _personnel_dashboard(request, today)

    doses = Dose.objects.select_related('visit__patient', 'vaccine_type').prefetch_related('visit__doses')
    due_today = doses.filter(status=Dose.Status.PENDING, due_date=today)
    follow_up = doses.filter(
        Q(status=Dose.Status.MISSED) | Q(status=Dose.Status.PENDING, due_date__lt=today)
    ).order_by('due_date')
    recent_visits = Visit.objects.select_related('patient', 'assessment__category').order_by('-visit_date', '-created_at')[:6]

    context = {
        'today': today,
        'fridges': fridge_readout(),
        'due_today': due_today[:10],
        'due_today_count': due_today.count(),
        'follow_up': follow_up[:8],
        'follow_up_count': follow_up.count(),
        'recent_visits': recent_visits,
        'visits_today': Visit.objects.filter(visit_date=today).count(),
        'given_today': doses.filter(status=Dose.Status.COMPLETED, date_given=today).count(),
    }
    if request.user.is_admin:
        start = (today.replace(day=1) - timedelta(days=150)).replace(day=1)
        bite = builders.bite_cases(builders.Filters(start, today))
        context.update({
            'total_patients': Patient.objects.count(),
            'active_users': User.objects.filter(is_active=True).count(),
            'charts': [bite.charts[0]],
        })
    return render(request, 'core/dashboard.html', context)


def _personnel_dashboard(request, today):
    year = builders.Filters(date(today.year, 1, 1), today)
    month = builders.Filters(today.replace(day=1), today)
    bite = builders.bite_cases(year)
    brgy = builders.barangay_cases(year)
    comp = builders.completion(year)
    comp_summary = dict(comp.summary)
    month_cases = Visit.objects.filter(visit_date__gte=month.date_from).count()
    given_month = StockMovement.objects.filter(
        movement_type=StockMovement.Type.USED, created_at__date__gte=month.date_from,
    ).count()
    return render(request, 'core/dashboard_personnel.html', {
        'today': today,
        'cases_year': dict(bite.summary).get('Total cases', 0),
        'cases_month': month_cases,
        'completion_rate': comp_summary.get('Course completion rate', '–'),
        'adherence': comp_summary.get('Dose adherence', '–'),
        'given_month': given_month,
        'fridges': fridge_readout(),
        'charts': [bite.charts[0], brgy.charts[0], bite.charts[1], comp.charts[0]],
    })


def fridge_readout():
    """Latest reading per storage unit, positioned on a small gauge around the safe range."""
    center = CenterSettings.load()
    lo, hi = float(center.temp_min), float(center.temp_max)
    scale_min, scale_max = lo - 6, hi + 6
    span = scale_max - scale_min

    def pct(value):
        return round(max(0.0, min(100.0, (value - scale_min) / span * 100)), 1)

    readout = []
    for unit in StorageUnit.objects.filter(is_active=True):
        last = unit.temperature_logs.order_by('-recorded_at').first()
        readout.append({
            'unit': unit,
            'last': last,
            'band_left': pct(lo),
            'band_width': round(pct(hi) - pct(lo), 1),
            'pin': pct(float(last.reading)) if last else None,
            'stale': last is None or last.recorded_at < timezone.now() - timedelta(hours=24),
        })
    return readout


# Settings ------------------------------------------------------------------

SETTINGS_KINDS = {
    'categories': {
        'model': ExposureCategory, 'form': ExposureCategoryForm,
        'title': 'Bite exposure categories', 'singular': 'category',
        'description': 'Categories I–III and what each one means. Staff pick one during bite assessment.',
        'columns': [('code', 'Code'), ('name', 'Name'), ('description', 'Description')],
    },
    'vaccines': {
        'model': VaccineType, 'form': VaccineTypeForm,
        'title': 'Vaccine types and schedules', 'singular': 'vaccine type',
        'description': 'The dosing schedule of each vaccine drives the automatic follow-up dates.',
        'columns': [('name', 'Name'), ('kind', 'Type'), ('route', 'Route'), ('schedule_display', 'Schedule'),
                    ('low_stock_threshold', 'Low-stock level')],
    },
    'barangays': {
        'model': Barangay, 'form': BarangayForm,
        'title': 'Barangays', 'singular': 'barangay',
        'description': 'Used for patient addresses and the cases-by-barangay report.',
        'columns': [('name', 'Name')],
    },
    'storage-units': {
        'model': StorageUnit, 'form': StorageUnitForm,
        'title': 'Storage units', 'singular': 'storage unit',
        'description': 'Refrigerators and cold boxes that need temperature monitoring.',
        'columns': [('name', 'Name'), ('location', 'Location')],
    },
}


def _kind(kind):
    if kind not in SETTINGS_KINDS:
        raise Http404
    return SETTINGS_KINDS[kind]


@admin_required
def settings_index(request):
    center = CenterSettings.load()
    form = CenterSettingsForm(request.POST or None, request.FILES or None, instance=center)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Center settings saved.')
        return redirect('core:settings')
    cards = [
        {'kind': key, 'title': spec['title'], 'description': spec['description'],
         'count': spec['model'].objects.filter(is_active=True).count()}
        for key, spec in SETTINGS_KINDS.items()
    ]
    return render(request, 'core/settings.html', {
        'form': form,
        'cards': cards,
        'sections': [
            ('Center details', ['name', 'address', 'contact_number', 'email', 'logo']),
            ('Alert limits', ['low_stock_threshold', 'expiry_warning_days', 'temp_min', 'temp_max']),
        ],
    })


@admin_required
def settings_list(request, kind):
    spec = _kind(kind)
    return render(request, 'core/settings_list.html', {
        'kind': kind, 'spec': spec, 'objects': spec['model'].objects.all(),
    })


@admin_required
def settings_edit(request, kind, pk=None):
    spec = _kind(kind)
    instance = get_object_or_404(spec['model'], pk=pk) if pk else None
    form = spec['form'](request.POST or None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        messages.success(request, f'{spec["singular"].capitalize()} "{obj}" saved.')
        return redirect('core:settings_list', kind=kind)
    return render(request, 'form_page.html', {
        'form': form,
        'title': f'Edit {spec["singular"]}' if instance else f'Add {spec["singular"]}',
        'subtitle': spec['description'],
        'back_url': reverse('core:settings_list', args=[kind]),
        'submit_label': 'Save',
    })


@admin_required
@require_POST
def settings_toggle(request, kind, pk):
    spec = _kind(kind)
    obj = get_object_or_404(spec['model'], pk=pk)
    obj.is_active = not obj.is_active
    obj.save()
    messages.success(request, f'"{obj}" {"enabled" if obj.is_active else "disabled"}.')
    return redirect('core:settings_list', kind=kind)


# Audit log -----------------------------------------------------------------

@admin_required
def audit_log(request):
    entries = AuditLog.objects.select_related('user')
    user_id = get_int_param(request, 'user')
    action = request.GET.get('action', '')
    model = request.GET.get('model', '')
    q = request.GET.get('q', '').strip()
    date_from = get_date_param(request, 'date_from')
    date_to = get_date_param(request, 'date_to')
    if user_id:
        entries = entries.filter(user_id=user_id)
    if action in AuditLog.Action.values:
        entries = entries.filter(action=action)
    if model:
        entries = entries.filter(model_name=model)
    if q:
        entries = entries.filter(object_repr__icontains=q)
    if date_from:
        entries = entries.filter(timestamp__date__gte=date_from)
    if date_to:
        entries = entries.filter(timestamp__date__lte=date_to)
    return render(request, 'core/audit_log.html', {
        'page': paginate(request, entries, per_page=50),
        'users': User.objects.all(),
        'actions': AuditLog.Action.choices,
        'models': AuditLog.objects.exclude(model_name='').values_list('model_name', flat=True).distinct().order_by('model_name'),
        'user_id': user_id, 'action': action, 'model': model, 'q': q,
        'date_from': date_from, 'date_to': date_to,
    })


# Backup --------------------------------------------------------------------

@admin_required
def backup(request):
    db_path = settings.DATABASES['default']['NAME']
    size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    last = AuditLog.objects.filter(action=AuditLog.Action.EXPORT, object_repr__startswith='Backup').first()
    counts = [
        ('Patients', Patient.objects.count()),
        ('Visits', Visit.objects.count()),
        ('Doses', Dose.objects.count()),
        ('Stock movements', StockMovement.objects.count()),
        ('Users', User.objects.count()),
        ('Audit entries', AuditLog.objects.count()),
    ]
    return render(request, 'core/backup.html', {'size': size, 'last': last, 'counts': counts})


@admin_required
def backup_database(request):
    """Download a consistent copy of the SQLite database, made with SQLite's online backup API."""
    fd, tmp_path = tempfile.mkstemp(suffix='.sqlite3')
    os.close(fd)
    try:
        source = sqlite3.connect(settings.DATABASES['default']['NAME'])
        target = sqlite3.connect(tmp_path)
        with target:
            source.backup(target)
        target.close()
        source.close()
        with open(tmp_path, 'rb') as fh:
            data = fh.read()
    finally:
        os.remove(tmp_path)
    log_event(AuditLog.Action.EXPORT, label='Backup: full database')
    response = HttpResponse(data, content_type='application/vnd.sqlite3')
    response['Content-Disposition'] = f'attachment; filename="vaxsafe-backup-{timezone.localtime():%Y%m%d-%H%M}.sqlite3"'
    return response


@admin_required
def backup_json(request):
    out = StringIO()
    call_command(
        'dumpdata', exclude=['contenttypes', 'auth.permission', 'sessions', 'admin.logentry'],
        indent=2, natural_foreign=True, stdout=out,
    )
    log_event(AuditLog.Action.EXPORT, label='Backup: JSON data export')
    response = HttpResponse(out.getvalue(), content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="vaxsafe-data-{timezone.localtime():%Y%m%d-%H%M}.json"'
    return response


# Error pages ---------------------------------------------------------------

def permission_denied(request, exception=None):
    return render(request, '403.html', status=403)


def page_not_found(request, exception=None):
    return render(request, '404.html', status=404)
