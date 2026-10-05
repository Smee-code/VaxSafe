from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone


def parse_schedule(value):
    """Turn '0, 3, 7' into [0, 3, 7]. Raises ValidationError for anything else."""
    try:
        days = [int(part) for part in str(value).split(',') if part.strip()]
    except ValueError:
        raise ValidationError('Enter whole numbers separated by commas, e.g. 0,3,7,14,28.')
    if not days:
        raise ValidationError('Enter at least one day.')
    if any(d < 0 for d in days):
        raise ValidationError('Days cannot be negative.')
    if days != sorted(set(days)):
        raise ValidationError('Days must go up in order with no repeats.')
    return days


class VaccineType(models.Model):
    class Kind(models.TextChoices):
        VACCINE = 'VACCINE', 'Anti-rabies vaccine'
        IMMUNOGLOBULIN = 'RIG', 'Rabies immunoglobulin'
        OTHER = 'OTHER', 'Other (e.g. tetanus)'

    name = models.CharField(max_length=150, unique=True)
    manufacturer = models.CharField(max_length=150, blank=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.VACCINE)
    route = models.CharField(max_length=50, blank=True, help_text='e.g. IM (intramuscular) or ID (intradermal).')
    schedule_days = models.CharField(
        'Dosing schedule (days)', max_length=100, default='0,3,7,14,28', validators=[parse_schedule],
        help_text='Days after the first dose, separated by commas. Follow-up dates are generated from this.',
    )
    low_stock_threshold = models.PositiveIntegerField(
        null=True, blank=True, help_text='Leave blank to use the center default.',
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def schedule_day_list(self):
        return parse_schedule(self.schedule_days)

    @property
    def schedule_display(self):
        return ', '.join(f'Day {d}' for d in self.schedule_day_list())

    def effective_threshold(self, center=None):
        if self.low_stock_threshold is not None:
            return self.low_stock_threshold
        from core.models import CenterSettings
        return (center or CenterSettings.load()).low_stock_threshold

    def usable_stock(self):
        today = timezone.localdate()
        total = self.lots.filter(expiry_date__gte=today).aggregate(s=Sum('quantity_on_hand'))['s']
        return total or 0


class StorageUnit(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text='e.g. Vaccine Refrigerator 1.')
    location = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class StockLot(models.Model):
    vaccine_type = models.ForeignKey(VaccineType, on_delete=models.PROTECT, related_name='lots')
    lot_number = models.CharField('Batch / lot number', max_length=60)
    quantity_received = models.PositiveIntegerField(help_text='Number of doses received.')
    quantity_on_hand = models.PositiveIntegerField(default=0)
    expiry_date = models.DateField()
    supplier = models.CharField(max_length=150, blank=True)
    date_received = models.DateField(default=timezone.localdate)
    storage_unit = models.ForeignKey(StorageUnit, null=True, blank=True, on_delete=models.SET_NULL, related_name='lots')
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['expiry_date', 'lot_number']
        constraints = [
            models.UniqueConstraint(fields=['vaccine_type', 'lot_number'], name='unique_lot_per_vaccine'),
        ]

    def __str__(self):
        return f'{self.vaccine_type.name} – Lot {self.lot_number}'

    @property
    def is_expired(self):
        return self.expiry_date < timezone.localdate()

    @property
    def days_to_expiry(self):
        return (self.expiry_date - timezone.localdate()).days

    def status(self, center=None):
        from core.models import CenterSettings
        center = center or CenterSettings.load()
        if self.is_expired:
            return 'Expired'
        if self.quantity_on_hand == 0:
            return 'Used up'
        if self.days_to_expiry <= center.expiry_warning_days:
            return 'Expiring soon'
        return 'Good'


class StockMovement(models.Model):
    class Type(models.TextChoices):
        RECEIVED = 'RECEIVED', 'Received'
        USED = 'USED', 'Administered'
        WASTED = 'WASTED', 'Wasted'
        DAMAGED = 'DAMAGED', 'Damaged'
        EXPIRED = 'EXPIRED', 'Expired / disposed'
        ADJUSTMENT = 'ADJUSTMENT', 'Count correction'

    MANUAL_TYPES = [Type.WASTED, Type.DAMAGED, Type.EXPIRED, Type.ADJUSTMENT]

    lot = models.ForeignKey(StockLot, on_delete=models.PROTECT, related_name='movements')
    movement_type = models.CharField(max_length=20, choices=Type.choices)
    quantity = models.IntegerField(help_text='Positive adds stock, negative removes it.')
    reason = models.CharField(max_length=255, blank=True)
    dose = models.ForeignKey('clinic.Dose', null=True, blank=True, on_delete=models.SET_NULL, related_name='stock_movements')
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_movement_type_display()} {self.quantity:+d} · {self.lot}'


class TemperatureLog(models.Model):
    unit = models.ForeignKey(StorageUnit, on_delete=models.PROTECT, related_name='temperature_logs')
    reading = models.DecimalField('Reading (°C)', max_digits=4, decimal_places=1)
    recorded_at = models.DateTimeField(default=timezone.now, db_index=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    notes = models.CharField(max_length=255, blank=True, help_text='Action taken if the reading is out of range.')
    # Saved with the limits in force when the reading was taken.
    out_of_range = models.BooleanField(default=False, editable=False)

    class Meta:
        ordering = ['-recorded_at']

    def __str__(self):
        return f'{self.unit} {self.reading}°C at {timezone.localtime(self.recorded_at):%Y-%m-%d %H:%M}'

    def save(self, *args, **kwargs):
        from core.models import CenterSettings
        center = CenterSettings.load()
        self.out_of_range = not (center.temp_min <= self.reading <= center.temp_max)
        super().save(*args, **kwargs)


def usable_lots(vaccine_type, on_date=None):
    on_date = on_date or timezone.localdate()
    return StockLot.objects.filter(
        Q(vaccine_type=vaccine_type), Q(quantity_on_hand__gt=0), Q(expiry_date__gte=on_date),
    ).order_by('expiry_date')
