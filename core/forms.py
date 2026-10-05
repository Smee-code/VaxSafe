from django import forms

from .models import Barangay, CenterSettings, ExposureCategory


class DateInput(forms.DateInput):
    input_type = 'date'

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, format='%Y-%m-%d')


class DateTimeInput(forms.DateTimeInput):
    input_type = 'datetime-local'

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, format='%Y-%m-%dT%H:%M')


class StyledFormMixin:
    """Adds the shared CSS classes to every widget so templates can render fields in a loop."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                css = 'checkbox'
            elif isinstance(widget, forms.Select):
                css = 'input select'
            else:
                css = 'input'
            widget.attrs['class'] = f"{widget.attrs.get('class', '')} {css}".strip()
            if isinstance(widget, forms.Textarea):
                widget.attrs['rows'] = 3


class CenterSettingsForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = CenterSettings
        fields = [
            'name', 'address', 'contact_number', 'email', 'logo',
            'low_stock_threshold', 'expiry_warning_days', 'temp_min', 'temp_max',
        ]

    def clean(self):
        data = super().clean()
        tmin, tmax = data.get('temp_min'), data.get('temp_max')
        if tmin is not None and tmax is not None and tmin >= tmax:
            self.add_error('temp_max', 'The maximum temperature must be higher than the minimum.')
        return data


class ExposureCategoryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ExposureCategory
        fields = ['code', 'name', 'description', 'management', 'sort_order', 'is_active']


class BarangayForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Barangay
        fields = ['name', 'is_active']
