from accounts.models import User

from . import builders

STAFF = User.Role.STAFF
PERSONNEL = User.Role.PERSONNEL

# Administrators can open every report. Health Staff get the operational
# ("basic") reports, and Authorized Personnel get all of them.
REPORTS = {
    'bite-cases': {
        'title': 'Bite cases', 'builder': builders.bite_cases,
        'filters': ['date', 'barangay', 'category'], 'roles': (PERSONNEL,),
    },
    'barangay': {
        'title': 'Cases by barangay', 'builder': builders.barangay_cases,
        'filters': ['date', 'category'], 'roles': (PERSONNEL,),
    },
    'completion': {
        'title': 'Vaccination completion', 'builder': builders.completion,
        'filters': ['date', 'barangay', 'category'], 'roles': (STAFF, PERSONNEL),
    },
    'stock': {
        'title': 'Stock and usage', 'builder': builders.stock_usage,
        'filters': ['date'], 'roles': (STAFF, PERSONNEL),
    },
    'expiring': {
        'title': 'Expiring vaccines', 'builder': builders.expiring,
        'filters': ['days'], 'roles': (STAFF, PERSONNEL),
    },
    'temperature': {
        'title': 'Temperature log', 'builder': builders.temperature,
        'filters': ['date', 'unit'], 'roles': (STAFF, PERSONNEL),
    },
}


def can_view(user, key):
    return user.is_admin or user.role in REPORTS[key]['roles']


def available_reports(user):
    return {key: spec for key, spec in REPORTS.items() if can_view(user, key)}
