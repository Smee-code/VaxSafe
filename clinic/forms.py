from django import forms
from django.utils import timezone

from core.forms import DateInput, StyledFormMixin
from core.models import Barangay, ExposureCategory
from inventory.models import VaccineType, usable_lots

from .models import BiteAssessment, Dose, Patient, Visit

BODY_PARTS = [
    'Head', 'Face', 'Neck', 'Shoulder', 'Upper arm', 'Forearm', 'Hand', 'Fingers',
    'Chest', 'Abdomen', 'Back', 'Buttocks', 'Thigh', 'Knee', 'Leg', 'Ankle', 'Foot', 'Toes',
]


class PatientForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Patient
        fields = [
            'first_name', 'middle_name', 'last_name', 'birth_date', 'sex',
            'barangay', 'address_line', 'contact_number',
            'emergency_contact_name', 'emergency_contact_relationship', 'emergency_contact_number',
        ]
        widgets = {'birth_date': DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = self.instance.barangay_id if self.instance.pk else None
        self.fields['barangay'].queryset = Barangay.objects.filter(is_active=True) | Barangay.objects.filter(pk=current)

    def clean_birth_date(self):
        value = self.cleaned_data['birth_date']
        if value > timezone.localdate():
            raise forms.ValidationError('Birth date cannot be in the future.')
        return value


class VisitForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Visit
        fields = ['visit_date', 'incident_date', 'incident_place', 'priority', 'triage_notes']
        widgets = {'visit_date': DateInput(), 'incident_date': DateInput()}

    def clean(self):
        data = super().clean()
        today = timezone.localdate()
        visit_date, incident_date = data.get('visit_date'), data.get('incident_date')
        if visit_date and visit_date > today:
            self.add_error('visit_date', 'Visit date cannot be in the future.')
        if incident_date and visit_date and incident_date > visit_date:
            self.add_error('incident_date', 'The incident cannot happen after the visit.')
        return data


class BiteAssessmentForm(StyledFormMixin, forms.ModelForm):
    datalists = {'body-parts': BODY_PARTS}

    class Meta:
        model = BiteAssessment
        fields = [
            'animal_type', 'animal_type_other', 'animal_ownership', 'animal_vaccination_status',
            'exposure_type', 'wound_location', 'category', 'wound_description', 'notes',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = self.instance.category_id if self.instance.pk else None
        self.fields['category'].queryset = (
            ExposureCategory.objects.filter(is_active=True) | ExposureCategory.objects.filter(pk=current)
        )
        self.fields['category'].empty_label = 'Select category…'
        self.fields['wound_location'].widget.attrs['list'] = 'body-parts'

    def clean(self):
        data = super().clean()
        if data.get('animal_type') == BiteAssessment.Animal.OTHER and not data.get('animal_type_other'):
            self.add_error('animal_type_other', 'Please name the animal.')
        return data


class VaccineChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f'{obj.name} ({obj.schedule_display})'


class ScheduleForm(StyledFormMixin, forms.Form):
    vaccine_type = VaccineChoiceField(queryset=VaccineType.objects.filter(is_active=True), label='Vaccine / regimen')
    start_date = forms.DateField(widget=DateInput(), initial=timezone.localdate, label='Day 0 (first dose date)')


class LotChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f'Lot {obj.lot_number} · expires {obj.expiry_date:%b %d, %Y} · {obj.quantity_on_hand} left'


class DoseRecordForm(StyledFormMixin, forms.Form):
    lot = LotChoiceField(queryset=None, label='Lot used', empty_label='Select lot…')
    date_given = forms.DateField(widget=DateInput(), initial=timezone.localdate)
    injection_site = forms.CharField(max_length=60, required=False, help_text='e.g. Left deltoid.')
    notes = forms.CharField(max_length=255, required=False)

    def __init__(self, *args, dose, **kwargs):
        super().__init__(*args, **kwargs)
        self.dose = dose
        self.fields['lot'].queryset = usable_lots(dose.vaccine_type)
        if not self.fields['lot'].queryset.exists():
            self.fields['lot'].help_text = f'No usable stock of {dose.vaccine_type}. Receive stock in Inventory first.'

    def clean(self):
        data = super().clean()
        lot, date_given = data.get('lot'), data.get('date_given')
        if date_given and date_given > timezone.localdate():
            self.add_error('date_given', 'Date given cannot be in the future.')
        if lot and date_given and lot.expiry_date < date_given:
            self.add_error('lot', 'This lot was already expired on that date.')
        return data


class RescheduleForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Dose
        fields = ['due_date', 'notes']
        widgets = {'due_date': DateInput()}
        labels = {'due_date': 'New due date', 'notes': 'Reason'}
