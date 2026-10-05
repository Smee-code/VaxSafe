"""Report builders.

Each builder takes a Filters object and returns a Report made of summary
figures, tables and chart data. The same Report is rendered on screen,
exported to Excel and printed to PDF, so the three always match. Reports
only contain aggregated data, never patient names, because Authorized
Personnel can open them.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.utils import timezone

from clinic.models import BiteAssessment, Dose, Visit
from core.models import Barangay, CenterSettings, ExposureCategory
from inventory.models import StockLot, StockMovement, StorageUnit, TemperatureLog, VaccineType

NOT_ASSESSED = 'Not assessed'


@dataclass
class Table:
    title: str
    columns: list
    rows: list
    footer: Optional[list] = None
    note: str = ''


@dataclass
class Report:
    title: str
    description: str = ''
    summary: list = field(default_factory=list)
    tables: list = field(default_factory=list)
    charts: list = field(default_factory=list)


@dataclass
class Filters:
    date_from: date
    date_to: date
    barangay: Optional[Barangay] = None
    category: Optional[ExposureCategory] = None
    unit: Optional[StorageUnit] = None
    days: int = 30

    def describe(self, used):
        parts = []
        if 'date' in used:
            parts.append(f'{self.date_from:%b %d, %Y} to {self.date_to:%b %d, %Y}')
        if 'barangay' in used:
            parts.append(f'Barangay: {self.barangay}' if self.barangay else 'All barangays')
        if 'category' in used:
            parts.append(str(self.category) if self.category else 'All categories')
        if 'unit' in used:
            parts.append(str(self.unit) if self.unit else 'All storage units')
        if 'days' in used:
            parts.append(f'Expiring within {self.days} days')
        return parts


# Helpers -------------------------------------------------------------------

def pct(part, whole):
    return f'{part / whole * 100:.1f}%' if whole else '–'


def month_starts(start, end):
    current = start.replace(day=1)
    months = []
    while current <= end:
        months.append(current)
        current = (current + timedelta(days=32)).replace(day=1)
    return months


def category_codes():
    return [f'Category {c}' for c in ExposureCategory.objects.order_by('sort_order', 'code').values_list('code', flat=True)]


def case_visits(f):
    visits = Visit.objects.filter(visit_date__range=(f.date_from, f.date_to))
    if f.barangay:
        visits = visits.filter(patient__barangay=f.barangay)
    if f.category:
        visits = visits.filter(assessment__category=f.category)
    return visits


def _category_label(code):
    return f'Category {code}' if code else NOT_ASSESSED


# Bite cases ----------------------------------------------------------------

def bite_cases(f):
    rows = list(case_visits(f).values(
        'visit_date', 'assessment__category__code', 'assessment__animal_type',
        'assessment__animal_type_other', 'assessment__exposure_type', 'assessment__animal_ownership',
    ))
    cats = category_codes() + [NOT_ASSESSED]
    total = len(rows)

    by_month = defaultdict(Counter)
    overall = Counter()
    animals, exposures, ownership = Counter(), Counter(), Counter()
    animal_labels = dict(BiteAssessment.Animal.choices)
    exposure_labels = dict(BiteAssessment.Exposure.choices)
    ownership_labels = dict(BiteAssessment.Ownership.choices)
    for r in rows:
        cat = _category_label(r['assessment__category__code'])
        by_month[r['visit_date'].replace(day=1)][cat] += 1
        overall[cat] += 1
        if r['assessment__animal_type']:
            animals[animal_labels[r['assessment__animal_type']]] += 1
            exposures[exposure_labels[r['assessment__exposure_type']]] += 1
            ownership[ownership_labels[r['assessment__animal_ownership']]] += 1

    months = month_starts(f.date_from, f.date_to)
    month_rows = []
    for m in months:
        counts = by_month.get(m, Counter())
        month_rows.append([m.strftime('%b %Y')] + [counts[c] for c in cats] + [sum(counts.values())])

    def breakdown(title, counter, label):
        assessed = sum(counter.values())
        return Table(title, [label, 'Cases', 'Share'],
                     [[k, v, pct(v, assessed)] for k, v in counter.most_common()],
                     footer=['Total assessed', assessed, '100%' if assessed else '–'])

    report = Report('Bite cases', 'Bite cases recorded in the period, by month, exposure category and animal.')
    report.summary = [('Total cases', total)] + [(c, overall[c]) for c in cats if overall[c] or c != NOT_ASSESSED]
    report.tables = [
        Table('Cases by month', ['Month'] + cats + ['Total'], month_rows,
              footer=['Total'] + [overall[c] for c in cats] + [total]),
        breakdown('Cases by animal', animals, 'Animal'),
        breakdown('Cases by type of exposure', exposures, 'Exposure'),
        breakdown('Owned or stray animal', ownership, 'Animal status'),
    ]
    report.charts = [
        {'id': 'cases-by-month', 'type': 'bar', 'stacked': True, 'title': 'Cases per month by category',
         'labels': [m.strftime('%b %Y') for m in months],
         'datasets': [{'label': c, 'data': [by_month.get(m, Counter())[c] for m in months]} for c in cats if overall[c]]},
        {'id': 'cases-by-animal', 'type': 'doughnut', 'title': 'Cases by animal',
         'labels': list(animals.keys()), 'datasets': [{'label': 'Cases', 'data': list(animals.values())}]},
    ]
    return report


# Barangay ------------------------------------------------------------------

def barangay_cases(f):
    rows = case_visits(f).values('patient__barangay__name', 'assessment__category__code')
    cats = category_codes() + [NOT_ASSESSED]
    by_brgy = defaultdict(Counter)
    for r in rows:
        by_brgy[r['patient__barangay__name']][_category_label(r['assessment__category__code'])] += 1
    total = sum(sum(c.values()) for c in by_brgy.values())
    ordered = sorted(by_brgy.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))

    table_rows = [
        [name] + [counts[c] for c in cats] + [sum(counts.values()), pct(sum(counts.values()), total)]
        for name, counts in ordered
    ]
    totals = Counter()
    for counts in by_brgy.values():
        totals.update(counts)

    top = ordered[:15]
    report = Report('Cases by barangay', "Where patients live. Use this to spot barangays where cases cluster.")
    report.summary = [
        ('Total cases', total),
        ('Barangays with cases', len(by_brgy)),
        ('Highest', f'{ordered[0][0]} ({sum(ordered[0][1].values())})' if ordered else '–'),
    ]
    report.tables = [Table(
        'Cases by barangay of residence', ['Barangay'] + cats + ['Total', 'Share'], table_rows,
        footer=['Total'] + [totals[c] for c in cats] + [total, '100%' if total else '–'],
        note='Barangays with no cases in the period are not listed.',
    )]
    report.charts = [{
        'id': 'cases-by-barangay', 'type': 'bar', 'horizontal': True, 'stacked': True,
        'title': 'Top barangays by number of cases',
        'labels': [name for name, _ in top],
        'datasets': [{'label': c, 'data': [counts[c] for _, counts in top]} for c in cats if totals[c]],
    }]
    return report


# Vaccination completion ----------------------------------------------------

def completion(f):
    today = timezone.localdate()
    visits = case_visits(f).filter(doses__isnull=False).distinct()
    doses = list(Dose.objects.filter(visit__in=visits).values('visit_id', 'visit__visit_date', 'status', 'due_date', 'vaccine_type__name'))

    def dose_state(d):
        if d['status'] == Dose.Status.COMPLETED:
            return 'completed'
        if d['status'] == Dose.Status.MISSED or d['due_date'] < today:
            return 'missed'
        return 'pending'

    per_visit = defaultdict(list)
    per_vaccine = defaultdict(Counter)
    dose_totals = Counter()
    visit_month = {}
    for d in doses:
        state = dose_state(d)
        per_visit[d['visit_id']].append(state)
        per_vaccine[d['vaccine_type__name']][state] += 1
        dose_totals[state] += 1
        visit_month[d['visit_id']] = d['visit__visit_date'].replace(day=1)

    courses = Counter()
    by_month = defaultdict(Counter)
    for visit_id, states in per_visit.items():
        if all(s == 'completed' for s in states):
            status = 'Completed'
        elif 'missed' in states:
            status = 'With missed dose'
        else:
            status = 'Ongoing'
        courses[status] += 1
        by_month[visit_month[visit_id]][status] += 1

    started = len(per_visit)
    finished_or_missed = dose_totals['completed'] + dose_totals['missed']
    report = Report('Vaccination completion', 'Treatment courses started in the period and how many doses were completed or missed.')
    report.summary = [
        ('Courses started', started),
        ('Completed', courses['Completed']),
        ('Ongoing', courses['Ongoing']),
        ('With missed dose', courses['With missed dose']),
        ('Course completion rate', pct(courses['Completed'], started)),
        ('Dose adherence', pct(dose_totals['completed'], finished_or_missed)),
    ]
    months = month_starts(f.date_from, f.date_to)
    status_cols = ['Completed', 'Ongoing', 'With missed dose']
    report.tables = [
        Table('Doses by vaccine', ['Vaccine', 'Scheduled', 'Completed', 'Missed / overdue', 'Upcoming', 'Adherence'],
              [[name, sum(c.values()), c['completed'], c['missed'], c['pending'], pct(c['completed'], c['completed'] + c['missed'])]
               for name, c in sorted(per_vaccine.items())],
              footer=['Total', sum(dose_totals.values()), dose_totals['completed'], dose_totals['missed'],
                      dose_totals['pending'], pct(dose_totals['completed'], finished_or_missed)],
              note='Adherence = completed doses ÷ (completed + missed). Upcoming doses are not counted yet.'),
        Table('Courses by month started', ['Month'] + status_cols + ['Total', 'Completion rate'],
              [[m.strftime('%b %Y')] + [by_month[m][s] for s in status_cols]
               + [sum(by_month[m].values()), pct(by_month[m]['Completed'], sum(by_month[m].values()))] for m in months],
              footer=['Total'] + [courses[s] for s in status_cols] + [started, pct(courses['Completed'], started)]),
    ]
    report.charts = [
        {'id': 'dose-status', 'type': 'doughnut', 'title': 'Doses: completed vs missed',
         'labels': ['Completed', 'Missed / overdue', 'Upcoming'],
         'datasets': [{'label': 'Doses', 'data': [dose_totals['completed'], dose_totals['missed'], dose_totals['pending']]}],
         'colors': ['ok', 'danger', 'muted']},
        {'id': 'courses-month', 'type': 'bar', 'stacked': True, 'title': 'Courses by month started',
         'labels': [m.strftime('%b %Y') for m in months],
         'datasets': [{'label': s, 'data': [by_month[m][s] for m in months]} for s in status_cols],
         'colors': ['ok', 'muted', 'danger']},
    ]
    return report


# Stock and usage -----------------------------------------------------------

LOSS_TYPES = (StockMovement.Type.WASTED, StockMovement.Type.DAMAGED, StockMovement.Type.EXPIRED)


def stock_usage(f):
    today = timezone.localdate()
    movements = StockMovement.objects.filter(created_at__date__range=(f.date_from, f.date_to))
    per_type = defaultdict(Counter)
    per_lot = defaultdict(Counter)
    for row in movements.values('lot_id', 'lot__vaccine_type_id', 'movement_type').annotate(total=Sum('quantity')):
        per_type[row['lot__vaccine_type_id']][row['movement_type']] += row['total']
        per_lot[row['lot_id']][row['movement_type']] += row['total']

    type_rows, chart_labels, chart_used, chart_lost = [], [], [], []
    totals = Counter()
    for v in VaccineType.objects.annotate(
        usable=Sum('lots__quantity_on_hand', filter=Q(lots__expiry_date__gte=today)),
        expired=Sum('lots__quantity_on_hand', filter=Q(lots__expiry_date__lt=today)),
    ):
        c = per_type.get(v.pk, Counter())
        received = c[StockMovement.Type.RECEIVED]
        used = -c[StockMovement.Type.USED]
        lost = -sum(c[t] for t in LOSS_TYPES)
        corrected = c[StockMovement.Type.ADJUSTMENT]
        if not (received or used or lost or corrected or v.usable or v.expired):
            continue
        type_rows.append([v.name, received, used, lost, f'{corrected:+d}' if corrected else 0, v.usable or 0, v.expired or 0])
        totals.update({'received': received, 'used': used, 'lost': lost, 'usable': v.usable or 0, 'expired': v.expired or 0})
        chart_labels.append(v.name)
        chart_used.append(used)
        chart_lost.append(lost)

    center = CenterSettings.load()
    lot_rows = []
    lots = StockLot.objects.select_related('vaccine_type').filter(
        Q(quantity_on_hand__gt=0) | Q(pk__in=list(per_lot.keys()))
    ).order_by('vaccine_type__name', 'expiry_date')
    for lot in lots:
        c = per_lot.get(lot.pk, Counter())
        lot_rows.append([
            lot.vaccine_type.name, lot.lot_number, lot.expiry_date, lot.quantity_received,
            -c[StockMovement.Type.USED], -sum(c[t] for t in LOSS_TYPES), lot.quantity_on_hand, lot.status(center),
        ])

    report = Report('Vaccine stock and usage', 'Doses received, given and lost in the period, with current stock.')
    report.summary = [
        ('Doses received', totals['received']),
        ('Doses given', totals['used']),
        ('Doses lost', totals['lost']),
        ('Usable on hand now', totals['usable']),
        ('Expired still on hand', totals['expired']),
    ]
    report.tables = [
        Table('By vaccine', ['Vaccine', 'Received', 'Given', 'Wasted / damaged / expired', 'Corrections', 'Usable now', 'Expired on hand'],
              type_rows, footer=['Total', totals['received'], totals['used'], totals['lost'], '', totals['usable'], totals['expired']]),
        Table('By lot', ['Vaccine', 'Lot', 'Expiry', 'Received (total)', 'Given', 'Lost', 'On hand', 'Status'], lot_rows,
              note='"Given" and "Lost" count only the selected period. Lots with no stock and no activity are hidden.'),
    ]
    report.charts = [{
        'id': 'usage', 'type': 'bar', 'title': 'Doses given and lost by vaccine', 'labels': chart_labels,
        'datasets': [{'label': 'Given', 'data': chart_used}, {'label': 'Lost', 'data': chart_lost}],
        'colors': ['brand', 'danger'],
    }]
    return report


# Expiry --------------------------------------------------------------------

def expiring(f):
    today = timezone.localdate()
    lots = StockLot.objects.select_related('vaccine_type', 'storage_unit').filter(quantity_on_hand__gt=0)
    expired = lots.filter(expiry_date__lt=today).order_by('expiry_date')
    soon = lots.filter(expiry_date__gte=today, expiry_date__lte=today + timedelta(days=f.days)).order_by('expiry_date')

    def rows(qs, overdue):
        out = []
        for lot in qs:
            days = (lot.expiry_date - today).days
            out.append([lot.vaccine_type.name, lot.lot_number, lot.expiry_date,
                        f'{-days} days ago' if overdue else f'in {days} days',
                        lot.quantity_on_hand, str(lot.storage_unit or '–')])
        return out

    cols = ['Vaccine', 'Lot', 'Expiry date', 'When', 'Doses on hand', 'Storage']
    expired_qty = sum(l.quantity_on_hand for l in expired)
    soon_qty = sum(l.quantity_on_hand for l in soon)
    report = Report('Expiring and expired vaccines', 'Lots that still have doses on hand and are expired or about to expire.')
    report.summary = [
        ('Expired lots on hand', len(expired)), ('Expired doses', expired_qty),
        (f'Lots expiring in {f.days} days', len(soon)), ('Doses at risk', soon_qty),
    ]
    report.tables = [
        Table('Expired, still in stock', cols, rows(expired, True), footer=['Total', '', '', '', expired_qty, ''],
              note='Remove these from storage and record them as "Expired / disposed" in Inventory.'),
        Table(f'Expiring within {f.days} days', cols, rows(soon, False), footer=['Total', '', '', '', soon_qty, ''],
              note='Use these lots first.'),
    ]
    return report


# Temperature ---------------------------------------------------------------

def temperature(f):
    center = CenterSettings.load()
    logs = TemperatureLog.objects.filter(recorded_at__date__range=(f.date_from, f.date_to)).select_related('unit', 'recorded_by')
    if f.unit:
        logs = logs.filter(unit=f.unit)
    stats = logs.aggregate(n=Count('id'), bad=Count('id', filter=Q(out_of_range=True)),
                           lo=Min('reading'), hi=Max('reading'), avg=Avg('reading'))

    unit_rows = []
    for row in logs.values('unit__name').annotate(
        n=Count('id'), bad=Count('id', filter=Q(out_of_range=True)), lo=Min('reading'), hi=Max('reading'), avg=Avg('reading'),
    ).order_by('unit__name'):
        unit_rows.append([row['unit__name'], row['n'], row['bad'], row['lo'], row['hi'], round(row['avg'], 1)])

    def log_row(log):
        return [timezone.localtime(log.recorded_at).strftime('%Y-%m-%d %H:%M'), log.unit.name, log.reading,
                'Out of range' if log.out_of_range else 'OK', str(log.recorded_by or '–'), log.notes]

    log_cols = ['Date and time', 'Storage unit', '°C', 'Status', 'Recorded by', 'Notes']
    excursions = [log_row(l) for l in logs.filter(out_of_range=True).order_by('-recorded_at')]
    all_logs = [log_row(l) for l in logs.order_by('-recorded_at')[:1000]]

    # Daily average per unit for the chart.
    days = []
    d = f.date_from
    while d <= f.date_to and len(days) < 400:
        days.append(d)
        d += timedelta(days=1)
    daily = defaultdict(dict)
    for row in logs.values('unit__name', 'recorded_at__date').annotate(avg=Avg('reading')):
        daily[row['unit__name']][row['recorded_at__date']] = round(float(row['avg']), 1)
    datasets = [{'label': unit, 'data': [values.get(day) for day in days]} for unit, values in sorted(daily.items())]
    datasets += [
        {'label': f'Min {center.temp_min}°C', 'data': [float(center.temp_min)] * len(days), 'limit': True},
        {'label': f'Max {center.temp_max}°C', 'data': [float(center.temp_max)] * len(days), 'limit': True},
    ]

    report = Report('Temperature log and incidents', f'Cold chain readings. Safe range is {center.temp_min}°C to {center.temp_max}°C.')
    report.summary = [
        ('Readings', stats['n']), ('Out of range', stats['bad']),
        ('Lowest', f"{stats['lo']}°C" if stats['lo'] is not None else '–'),
        ('Highest', f"{stats['hi']}°C" if stats['hi'] is not None else '–'),
        ('Average', f"{stats['avg']:.1f}°C" if stats['avg'] is not None else '–'),
    ]
    report.tables = [
        Table('By storage unit', ['Storage unit', 'Readings', 'Out of range', 'Lowest °C', 'Highest °C', 'Average °C'], unit_rows),
        Table('Incidents (out of range)', log_cols, excursions),
        Table('All readings', log_cols, all_logs, note='Shows up to 1,000 most recent readings.' if len(all_logs) == 1000 else ''),
    ]
    report.charts = [{
        'id': 'temperature', 'type': 'line', 'title': 'Daily average temperature',
        'labels': [day.strftime('%b %d') for day in days], 'datasets': datasets,
    }]
    return report
