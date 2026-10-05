from datetime import timedelta
from decimal import Decimal

from django import forms
from django.utils import timezone

from core.forms import DateInput, DateTimeInput, StyledFormMixin

from .models import StockLot, StockMovement, StorageUnit, TemperatureLog, VaccineType, parse_schedule


class VaccineTypeForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = VaccineType
        fields = ['name', 'manufacturer', 'kind', 'route', 'schedule_days', 'low_stock_threshold', 'description', 'is_active']

    def clean_schedule_days(self):
        days = parse_schedule(self.cleaned_data['schedule_days'])
        return ','.join(str(d) for d in days)


class StorageUnitForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = StorageUnit
        fields = ['name', 'location', 'is_active']


class StockReceiveForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = StockLot
        fields = ['vaccine_type', 'lot_number', 'quantity_received', 'expiry_date', 'supplier', 'date_received', 'storage_unit', 'notes']
        widgets = {'expiry_date': DateInput(), 'date_received': DateInput()}
        labels = {'quantity_received': 'Quantity (doses)'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['vaccine_type'].queryset = VaccineType.objects.filter(is_active=True)
        self.fields['storage_unit'].queryset = StorageUnit.objects.filter(is_active=True)

    def clean_quantity_received(self):
        qty = self.cleaned_data['quantity_received']
        if qty < 1:
            raise forms.ValidationError('Quantity must be at least 1.')
        return qty

    def clean(self):
        data = super().clean()
        expiry, received = data.get('expiry_date'), data.get('date_received')
        if received and received > timezone.localdate():
            self.add_error('date_received', 'Date received cannot be in the future.')
        if expiry and expiry < timezone.localdate():
            self.add_error('expiry_date', 'This lot is already expired. Do not receive expired stock.')
        return data


class LotChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f'{obj.vaccine_type.name} · Lot {obj.lot_number} · {obj.quantity_on_hand} on hand'


class StockAdjustmentForm(StyledFormMixin, forms.Form):
    lot = LotChoiceField(queryset=StockLot.objects.select_related('vaccine_type').filter(quantity_on_hand__gt=0))
    movement_type = forms.ChoiceField(
        label='Type', choices=[(t.value, t.label) for t in StockMovement.MANUAL_TYPES],
    )
    quantity = forms.IntegerField(
        help_text='Number of doses. For a count correction, use a negative number to remove doses or a positive number to add them.',
    )
    reason = forms.CharField(max_length=255, help_text='e.g. Vial dropped, power outage, physical count on Oct 1.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Allow corrections on lots that are already at zero.
        if self.data.get('movement_type') == StockMovement.Type.ADJUSTMENT or self.initial.get('lot'):
            self.fields['lot'].queryset = StockLot.objects.select_related('vaccine_type')

    def clean(self):
        data = super().clean()
        lot, kind, qty = data.get('lot'), data.get('movement_type'), data.get('quantity')
        if lot is None or kind is None or qty is None:
            return data
        if qty == 0:
            self.add_error('quantity', 'Quantity cannot be zero.')
            return data
        if kind == StockMovement.Type.ADJUSTMENT:
            delta = qty
        else:
            if qty < 0:
                self.add_error('quantity', 'Enter a positive number of doses to remove.')
                return data
            delta = -qty
        if lot.quantity_on_hand + delta < 0:
            self.add_error('quantity', f'Only {lot.quantity_on_hand} doses are on hand in this lot.')
        data['delta'] = delta
        return data


class TemperatureLogForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = TemperatureLog
        fields = ['unit', 'reading', 'recorded_at', 'notes']
        widgets = {'recorded_at': DateTimeInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unit'].queryset = StorageUnit.objects.filter(is_active=True)
        self.fields['reading'].widget.attrs['step'] = '0.1'

    def clean_reading(self):
        value = self.cleaned_data['reading']
        if not Decimal('-40') <= value <= Decimal('50'):
            raise forms.ValidationError('That reading looks wrong. Check the thermometer and try again.')
        return value

    def clean_recorded_at(self):
        value = self.cleaned_data['recorded_at']
        if value > timezone.now() + timedelta(minutes=5):
            raise forms.ValidationError('Reading time cannot be in the future.')
        return value
