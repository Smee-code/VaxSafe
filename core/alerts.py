"""Stock, expiry and cold chain alerts shown on dashboards and in the top bar."""
from datetime import timedelta

from django.db.models import Q, Sum
from django.utils import timezone

from inventory.models import StockLot, StorageUnit, TemperatureLog, VaccineType

from .models import CenterSettings


def get_alerts(center=None):
    center = center or CenterSettings.load()
    today = timezone.localdate()

    low_stock = []
    vaccines = VaccineType.objects.filter(is_active=True).annotate(
        usable=Sum('lots__quantity_on_hand', filter=Q(lots__expiry_date__gte=today)),
    )
    for vaccine in vaccines:
        usable = vaccine.usable or 0
        threshold = vaccine.effective_threshold(center)
        if usable <= threshold:
            low_stock.append({'vaccine': vaccine, 'usable': usable, 'threshold': threshold})

    lots_in_stock = StockLot.objects.filter(quantity_on_hand__gt=0).select_related('vaccine_type')
    expiring = list(lots_in_stock.filter(
        expiry_date__gte=today,
        expiry_date__lte=today + timedelta(days=center.expiry_warning_days),
    ).order_by('expiry_date'))
    expired = list(lots_in_stock.filter(expiry_date__lt=today).order_by('expiry_date'))

    # A unit is in alert when its most recent reading is out of range, and
    # needs attention when nobody has logged a reading for 24 hours.
    temperature, stale_units = [], []
    stale_cutoff = timezone.now() - timedelta(hours=24)
    for unit in StorageUnit.objects.filter(is_active=True):
        log = TemperatureLog.objects.filter(unit=unit).order_by('-recorded_at').first()
        if log is None or log.recorded_at < stale_cutoff:
            stale_units.append(unit)
        if log is not None and log.out_of_range:
            temperature.append(log)

    stock_total = len(low_stock) + len(expiring) + len(expired)
    total = stock_total + len(temperature)
    return {
        'low_stock': low_stock,
        'expiring': expiring,
        'expired': expired,
        'temperature': temperature,
        'stale_units': stale_units,
        'stock_total': stock_total,
        'total': total,
        'center': center,
    }
