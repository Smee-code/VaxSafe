from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.decorators import ALL_ROLES, clinical_required, role_required
from core.models import CenterSettings
from core.utils import get_date_param, get_int_param, paginate

from .forms import StockAdjustmentForm, StockReceiveForm, TemperatureLogForm
from .models import StockLot, StockMovement, StorageUnit, TemperatureLog, VaccineType

view_required = role_required(*ALL_ROLES)


@view_required
def stock_list(request):
    today = timezone.localdate()
    center = CenterSettings.load()
    show = request.GET.get('show', 'active')
    vaccine_filter = get_int_param(request, 'vaccine')

    vaccines = VaccineType.objects.annotate(
        usable=Sum('lots__quantity_on_hand', filter=Q(lots__expiry_date__gte=today)),
        expired_qty=Sum('lots__quantity_on_hand', filter=Q(lots__expiry_date__lt=today)),
    ).order_by('-is_active', 'name')
    summary = []
    for v in vaccines:
        usable = v.usable or 0
        threshold = v.effective_threshold(center)
        summary.append({'vaccine': v, 'usable': usable, 'expired': v.expired_qty or 0,
                        'threshold': threshold, 'low': v.is_active and usable <= threshold})

    lots = StockLot.objects.select_related('vaccine_type', 'storage_unit')
    if show == 'active':
        lots = lots.filter(quantity_on_hand__gt=0)
    if vaccine_filter:
        lots = lots.filter(vaccine_type_id=vaccine_filter)
    lots = [(lot, lot.status(center)) for lot in lots]

    return render(request, 'inventory/stock_list.html', {
        'summary': summary, 'lots': lots, 'show': show,
        'vaccines': VaccineType.objects.all(), 'vaccine_filter': vaccine_filter,
    })


@view_required
def lot_detail(request, pk):
    lot = get_object_or_404(StockLot.objects.select_related('vaccine_type', 'storage_unit', 'received_by'), pk=pk)
    movements = lot.movements.select_related('performed_by', 'dose__visit__patient')
    return render(request, 'inventory/lot_detail.html', {
        'lot': lot, 'status': lot.status(), 'movements': movements,
    })


@clinical_required
def stock_receive(request):
    form = StockReceiveForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            lot = form.save(commit=False)
            lot.quantity_on_hand = lot.quantity_received
            lot.received_by = request.user
            lot.save()
            StockMovement.objects.create(
                lot=lot, movement_type=StockMovement.Type.RECEIVED, quantity=lot.quantity_received,
                reason=f'Received from {lot.supplier}' if lot.supplier else 'Received', performed_by=request.user,
            )
        messages.success(request, f'{lot.quantity_received} doses of {lot.vaccine_type} (lot {lot.lot_number}) added to stock.')
        return redirect('inventory:stock_list')
    return render(request, 'form_page.html', {
        'form': form,
        'title': 'Receive stock',
        'subtitle': 'Record a delivery of vaccines or immunoglobulin.',
        'back_url': reverse('inventory:stock_list'),
        'submit_label': 'Add to stock',
    })


@clinical_required
def stock_adjust(request):
    initial = {}
    lot_id = get_int_param(request, 'lot')
    if lot_id:
        initial['lot'] = lot_id
    form = StockAdjustmentForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        with transaction.atomic():
            lot = StockLot.objects.select_for_update().get(pk=data['lot'].pk)
            if lot.quantity_on_hand + data['delta'] < 0:
                form.add_error('quantity', f'Only {lot.quantity_on_hand} doses are on hand in this lot.')
            else:
                lot.quantity_on_hand += data['delta']
                lot.save(update_fields=['quantity_on_hand'])
                StockMovement.objects.create(
                    lot=lot, movement_type=data['movement_type'], quantity=data['delta'],
                    reason=data['reason'], performed_by=request.user,
                )
        if not form.errors:
            messages.success(request, f'Stock adjusted. Lot {lot.lot_number} now has {lot.quantity_on_hand} doses.')
            return redirect('inventory:lot_detail', pk=lot.pk)
    return render(request, 'form_page.html', {
        'form': form,
        'title': 'Adjust stock',
        'subtitle': 'Record wasted, damaged or expired doses, or correct a count.',
        'back_url': reverse('inventory:stock_list'),
        'submit_label': 'Save adjustment',
    })


@view_required
def movement_list(request):
    movements = StockMovement.objects.select_related('lot__vaccine_type', 'performed_by', 'dose__visit__patient')
    kind = request.GET.get('type', '')
    vaccine = get_int_param(request, 'vaccine')
    date_from = get_date_param(request, 'date_from')
    date_to = get_date_param(request, 'date_to')
    if kind in StockMovement.Type.values:
        movements = movements.filter(movement_type=kind)
    if vaccine:
        movements = movements.filter(lot__vaccine_type_id=vaccine)
    if date_from:
        movements = movements.filter(created_at__date__gte=date_from)
    if date_to:
        movements = movements.filter(created_at__date__lte=date_to)
    return render(request, 'inventory/movement_list.html', {
        'page': paginate(request, movements, per_page=40),
        'types': StockMovement.Type.choices, 'vaccines': VaccineType.objects.all(),
        'kind': kind, 'vaccine': vaccine, 'date_from': date_from, 'date_to': date_to,
    })


@view_required
def temperature_list(request):
    center = CenterSettings.load()
    logs = TemperatureLog.objects.select_related('unit', 'recorded_by')
    unit = get_int_param(request, 'unit')
    only_alerts = request.GET.get('alerts') == '1'
    date_from = get_date_param(request, 'date_from')
    date_to = get_date_param(request, 'date_to')
    if unit:
        logs = logs.filter(unit_id=unit)
    if only_alerts:
        logs = logs.filter(out_of_range=True)
    if date_from:
        logs = logs.filter(recorded_at__date__gte=date_from)
    if date_to:
        logs = logs.filter(recorded_at__date__lte=date_to)

    units = []
    for u in StorageUnit.objects.filter(is_active=True):
        units.append({'unit': u, 'last': u.temperature_logs.order_by('-recorded_at').first()})

    return render(request, 'inventory/temperature_list.html', {
        'page': paginate(request, logs, per_page=40),
        'units': units, 'all_units': StorageUnit.objects.all(),
        'unit': unit, 'only_alerts': only_alerts, 'date_from': date_from, 'date_to': date_to,
        'center': center,
    })


@clinical_required
def temperature_create(request):
    initial = {'recorded_at': timezone.localtime().replace(second=0, microsecond=0)}
    unit = get_int_param(request, 'unit')
    if unit:
        initial['unit'] = unit
    form = TemperatureLogForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        log = form.save(commit=False)
        log.recorded_by = request.user
        log.save()
        if log.out_of_range:
            center = CenterSettings.load()
            messages.error(
                request,
                f'{log.reading}°C is outside the safe range of {center.temp_min}–{center.temp_max}°C for {log.unit}. '
                'Follow the cold chain protocol and note the action you took.',
            )
        else:
            messages.success(request, f'{log.reading}°C logged for {log.unit}.')
        return redirect('inventory:temperature_list')
    center = CenterSettings.load()
    return render(request, 'form_page.html', {
        'form': form,
        'title': 'Log temperature',
        'subtitle': f'Safe range: {center.temp_min}°C to {center.temp_max}°C',
        'back_url': reverse('inventory:temperature_list'),
        'submit_label': 'Save reading',
    })
