from django import template
from django.urls import reverse

register = template.Library()

STATUS_TONES = {
    'completed': 'ok', 'good': 'ok', 'ok': 'ok', 'active': 'ok',
    'scheduled': 'info', 'ongoing': 'info', 'due today': 'brand',
    'overdue': 'danger', 'missed': 'danger', 'missed dose': 'danger', 'expired': 'danger',
    'urgent': 'danger', 'out of range': 'danger', 'inactive': 'muted',
    'expiring soon': 'warn', 'used up': 'muted', 'no schedule': 'muted', 'normal': 'muted',
    'received': 'ok', 'administered': 'info', 'wasted': 'warn', 'damaged': 'warn',
    'expired / disposed': 'danger', 'count correction': 'muted',
    'created': 'ok', 'updated': 'info', 'deleted': 'danger', 'signed in': 'muted',
    'signed out': 'muted', 'failed sign-in': 'warn', 'exported': 'brand',
}


@register.filter
def tone(value):
    """Colour tone for a status badge."""
    return STATUS_TONES.get(str(value).lower(), 'muted')


@register.filter
def attr(obj, name):
    display = getattr(obj, f'get_{name}_display', None)
    if callable(display):
        return display()
    value = getattr(obj, name, '')
    return value() if callable(value) else value


@register.filter
def get_item(mapping, key):
    return mapping.get(key) if mapping else None


@register.simple_tag(takes_context=True)
def query(context, **kwargs):
    """Current query string with some parameters replaced. Used by pagination and tabs."""
    params = context['request'].GET.copy()
    for key, value in kwargs.items():
        if value in (None, ''):
            params.pop(key, None)
        else:
            params[key] = value
    return params.urlencode()


@register.simple_tag(takes_context=True)
def nav_active(context, *prefixes):
    path = context['request'].path
    for prefix in prefixes:
        url = reverse(prefix) if ':' in prefix else prefix
        if url == '/' and path == '/':
            return 'is-active'
        if url != '/' and path.startswith(url):
            return 'is-active'
    return ''


@register.filter
def bound_sections(form, sections):
    """Group a form's visible fields into titled sections; fields not listed go last."""
    if not sections:
        return [('', [f for f in form.visible_fields()])]
    used, out = set(), []
    for title, names in sections:
        out.append((title, [form[n] for n in names if n in form.fields]))
        used.update(names)
    rest = [f for f in form.visible_fields() if f.name not in used]
    if rest:
        out.append(('Other details', rest))
    return out


@register.filter
def next_pending(doses):
    """First dose in a series that has not been given yet."""
    for dose in doses:
        if dose.status != 'COMPLETED':
            return dose
    return None


@register.filter
def initials(user):
    first = (getattr(user, 'first_name', '') or '')[:1]
    last = (getattr(user, 'last_name', '') or '')[:1]
    return (first + last).upper() or str(user)[:2].upper()


@register.filter
def filesize(num):
    for unit in ['bytes', 'KB', 'MB', 'GB']:
        if num < 1024:
            return f'{num:.0f} {unit}' if unit == 'bytes' else f'{num:.1f} {unit}'
        num /= 1024
    return f'{num:.1f} TB'
