from decimal import Decimal

from django.conf import settings
from django.db import models


class CenterSettings(models.Model):
    """Single-row table that holds the center's details and alert limits."""

    name = models.CharField(max_length=150, default='Animal Bite Treatment Center')
    address = models.CharField(max_length=255, blank=True)
    contact_number = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    logo = models.ImageField(upload_to='center/', blank=True, help_text='Shown on the sidebar and on printed reports.')
    low_stock_threshold = models.PositiveIntegerField(
        default=10,
        help_text='Warn when usable doses of a vaccine fall to or below this number. Each vaccine type can override it.',
    )
    expiry_warning_days = models.PositiveIntegerField(
        default=30, help_text='Warn this many days before a lot expires.',
    )
    temp_min = models.DecimalField('Minimum safe temperature (°C)', max_digits=4, decimal_places=1, default=Decimal('2.0'))
    temp_max = models.DecimalField('Maximum safe temperature (°C)', max_digits=4, decimal_places=1, default=Decimal('8.0'))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'center settings'
        verbose_name_plural = 'center settings'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ExposureCategory(models.Model):
    code = models.CharField(max_length=10, unique=True, help_text='Short code, e.g. I, II or III.')
    name = models.CharField(max_length=100)
    description = models.TextField(help_text='Which exposures fall under this category.')
    management = models.TextField('Recommended management', blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'code']
        verbose_name_plural = 'exposure categories'

    def __str__(self):
        return f'Category {self.code}'


class Barangay(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = 'CREATE', 'Created'
        UPDATE = 'UPDATE', 'Updated'
        DELETE = 'DELETE', 'Deleted'
        LOGIN = 'LOGIN', 'Signed in'
        LOGOUT = 'LOGOUT', 'Signed out'
        LOGIN_FAILED = 'LOGIN_FAILED', 'Failed sign-in'
        EXPORT = 'EXPORT', 'Exported'

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='audit_entries')
    action = models.CharField(max_length=20, choices=Action.choices)
    model_name = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.timestamp:%Y-%m-%d %H:%M} {self.user} {self.action} {self.object_repr}'
