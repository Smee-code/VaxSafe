"""Audit trail: records who created, changed or deleted tracked records, and every sign-in."""
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .middleware import get_client_ip, get_current_user
from .models import AuditLog

AUDITED_MODELS = {
    'accounts.User',
    'core.CenterSettings', 'core.ExposureCategory', 'core.Barangay',
    'clinic.Patient', 'clinic.Visit', 'clinic.BiteAssessment', 'clinic.Dose',
    'inventory.VaccineType', 'inventory.StorageUnit', 'inventory.StockLot',
    'inventory.StockMovement', 'inventory.TemperatureLog',
}
SKIPPED_FIELDS = {'last_login', 'updated_at', 'created_at'}
HIDDEN_FIELDS = {'password'}


def _tracked(sender):
    return sender._meta.label in AUDITED_MODELS


def _display(obj, field):
    if field.is_relation:
        related = getattr(obj, field.name, None)
        return str(related) if related is not None else ''
    value = field.value_from_object(obj)
    if value is None:
        return ''
    if hasattr(value, 'name') and field.get_internal_type() in ('FileField', 'ImageField'):
        return value.name or ''
    return str(value)


def _snapshot(obj):
    data = {}
    for field in obj._meta.concrete_fields:
        if field.primary_key or field.name in SKIPPED_FIELDS:
            continue
        data[field.name] = _display(obj, field)
    return data


def log_event(action, obj=None, changes=None, user=None, label=''):
    AuditLog.objects.create(
        user=user or get_current_user(),
        action=action,
        model_name=obj._meta.verbose_name.title() if obj is not None else label,
        object_id=str(obj.pk) if obj is not None and obj.pk is not None else '',
        object_repr=str(obj)[:255] if obj is not None else label,
        changes=changes or {},
        ip_address=get_client_ip(),
    )


@receiver(pre_save)
def audit_capture_old(sender, instance, raw=False, **kwargs):
    if raw or not _tracked(sender):
        return
    instance._audit_old = None
    if instance.pk is not None:
        try:
            instance._audit_old = _snapshot(sender._default_manager.get(pk=instance.pk))
        except sender.DoesNotExist:
            pass


@receiver(post_save)
def audit_save(sender, instance, created, raw=False, update_fields=None, **kwargs):
    if raw or not _tracked(sender):
        return
    if update_fields and set(update_fields) <= SKIPPED_FIELDS:
        return
    new = _snapshot(instance)
    old = getattr(instance, '_audit_old', None)
    if created or old is None:
        changes = {k: {'new': '••••' if k in HIDDEN_FIELDS else v} for k, v in new.items() if v not in ('', 'False')}
        log_event(AuditLog.Action.CREATE, instance, changes)
        return
    changes = {}
    for key, value in new.items():
        if old.get(key) != value:
            if key in HIDDEN_FIELDS:
                changes[key] = {'old': '', 'new': 'changed'}
            else:
                changes[key] = {'old': old.get(key, ''), 'new': value}
    if changes:
        log_event(AuditLog.Action.UPDATE, instance, changes)


@receiver(post_delete)
def audit_delete(sender, instance, **kwargs):
    if not _tracked(sender):
        return
    snapshot = {k: {'old': v} for k, v in _snapshot(instance).items() if v and k not in HIDDEN_FIELDS}
    log_event(AuditLog.Action.DELETE, instance, snapshot)


@receiver(user_logged_in)
def audit_login(sender, request, user, **kwargs):
    log_event(AuditLog.Action.LOGIN, user, user=user)


@receiver(user_logged_out)
def audit_logout(sender, request, user, **kwargs):
    if user is not None:
        log_event(AuditLog.Action.LOGOUT, user, user=user)


@receiver(user_login_failed)
def audit_login_failed(sender, credentials, request=None, **kwargs):
    username = credentials.get('username', '')
    log_event(AuditLog.Action.LOGIN_FAILED, changes={'username': {'new': username}}, label=f'Sign-in attempt: {username}')
