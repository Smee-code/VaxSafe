import calendar
from datetime import date, timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Max, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.decorators import clinical_required
from core.models import Barangay, ExposureCategory
from core.utils import get_date_param, get_int_param, paginate

from .forms import BiteAssessmentForm, DoseRecordForm, PatientForm, RescheduleForm, ScheduleForm, VisitForm
from .models import BiteAssessment, Dose, Patient, Visit
from .services import generate_schedule, record_dose


def _safe_next(request, fallback):
    nxt = request.POST.get('next') or request.GET.get('next')
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return nxt
    return fallback


def _search_patients(queryset, q):
    for word in q.split():
        queryset = queryset.filter(
            Q(patient_code__icontains=word) | Q(first_name__icontains=word)
            | Q(middle_name__icontains=word) | Q(last_name__icontains=word)
            | Q(contact_number__icontains=word)
        )
    return queryset


# Patients ------------------------------------------------------------------

@clinical_required
def patient_list(request):
    q = request.GET.get('q', '').strip()
    barangay = get_int_param(request, 'barangay')
    patients = Patient.objects.select_related('barangay').annotate(
        visit_count=Count('visits'), last_visit=Max('visits__visit_date'),
    )
    if q:
        patients = _search_patients(patients, q)
    if barangay:
        patients = patients.filter(barangay_id=barangay)
    patients = patients.order_by('-created_at')
    return render(request, 'clinic/patient_list.html', {
        'page': paginate(request, patients),
        'q': q,
        'barangay': barangay,
        'barangays': Barangay.objects.all(),
    })


@clinical_required
def patient_create(request):
    form = PatientForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        patient = form.save(commit=False)
        patient.created_by = request.user
        patient.save()
        messages.success(request, f'{patient.full_name} registered as {patient.patient_code}.')
        if request.POST.get('then') == 'visit':
            return redirect('clinic:visit_create', pk=patient.pk)
        return redirect('clinic:patient_detail', pk=patient.pk)
    return render(request, 'form_page.html', {
        'form': form,
        'title': 'Register patient',
        'subtitle': 'Search first to avoid duplicate records.',
        'back_url': reverse('clinic:patient_list'),
        'submit_label': 'Register',
        'secondary_submit': ('visit', 'Register and record visit'),
        'sections': [
            ('Personal details', ['first_name', 'middle_name', 'last_name', 'birth_date', 'sex']),
            ('Address and contact', ['barangay', 'address_line', 'contact_number']),
            ('Emergency contact', ['emergency_contact_name', 'emergency_contact_relationship', 'emergency_contact_number']),
        ],
    })


@clinical_required
def patient_edit(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    form = PatientForm(request.POST or None, instance=patient)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Patient record updated.')
        return redirect('clinic:patient_detail', pk=patient.pk)
    return render(request, 'form_page.html', {
        'form': form,
        'title': f'Edit {patient.full_name}',
        'subtitle': patient.patient_code,
        'back_url': reverse('clinic:patient_detail', args=[patient.pk]),
        'submit_label': 'Save changes',
        'sections': [
            ('Personal details', ['first_name', 'middle_name', 'last_name', 'birth_date', 'sex']),
            ('Address and contact', ['barangay', 'address_line', 'contact_number']),
            ('Emergency contact', ['emergency_contact_name', 'emergency_contact_relationship', 'emergency_contact_number']),
        ],
    })


@clinical_required
def patient_detail(request, pk):
    patient = get_object_or_404(Patient.objects.select_related('barangay', 'created_by'), pk=pk)
    visits = (
        patient.visits.select_related('assessment__category', 'assessment__assessed_by', 'created_by')
        .prefetch_related(Prefetch('doses', queryset=Dose.objects.select_related('vaccine_type', 'lot', 'administered_by')))
    )
    return render(request, 'clinic/patient_detail.html', {'patient': patient, 'visits': visits})


# Visits, triage and assessment ---------------------------------------------

@clinical_required
def visit_create(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    form = VisitForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        visit = form.save(commit=False)
        visit.patient = patient
        visit.created_by = request.user
        visit.save()
        messages.success(request, 'Visit recorded. Next, complete the bite assessment.')
        return redirect('clinic:assessment_edit', pk=visit.pk)
    return render(request, 'form_page.html', {
        'form': form,
        'title': 'Record visit and triage',
        'subtitle': f'{patient.full_name} · {patient.patient_code}',
        'back_url': reverse('clinic:patient_detail', args=[patient.pk]),
        'submit_label': 'Save and continue to assessment',
    })


@clinical_required
def visit_edit(request, pk):
    visit = get_object_or_404(Visit.objects.select_related('patient'), pk=pk)
    form = VisitForm(request.POST or None, instance=visit)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Visit updated.')
        return redirect('clinic:visit_detail', pk=visit.pk)
    return render(request, 'form_page.html', {
        'form': form,
        'title': 'Edit visit and triage',
        'subtitle': f'{visit.patient.full_name} · {visit.patient.patient_code}',
        'back_url': reverse('clinic:visit_detail', args=[visit.pk]),
        'submit_label': 'Save changes',
    })


@clinical_required
def visit_detail(request, pk):
    visit = get_object_or_404(
        Visit.objects.select_related('patient__barangay', 'created_by', 'assessment__category', 'assessment__assessed_by'),
        pk=pk,
    )
    doses = list(visit.doses.select_related('vaccine_type', 'lot', 'administered_by'))
    regimens = {}
    for dose in doses:
        regimens.setdefault(dose.vaccine_type_id, {'vaccine': dose.vaccine_type, 'doses': []})['doses'].append(dose)
    for regimen in regimens.values():
        regimen['doses'].sort(key=lambda d: d.dose_number)
        regimen['given'] = sum(1 for d in regimen['doses'] if d.status == Dose.Status.COMPLETED)
    assessment = getattr(visit, 'assessment', None)
    return render(request, 'clinic/visit_detail.html', {
        'visit': visit,
        'patient': visit.patient,
        'assessment': assessment,
        'doses': doses,
        'regimens': list(regimens.values()),
    })


@clinical_required
def assessment_edit(request, pk):
    visit = get_object_or_404(Visit.objects.select_related('patient'), pk=pk)
    instance = getattr(visit, 'assessment', None)
    form = BiteAssessmentForm(request.POST or None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        assessment = form.save(commit=False)
        assessment.visit = visit
        if instance is None:
            assessment.assessed_by = request.user
            assessment.assessed_at = timezone.now()
        assessment.save()
        messages.success(request, 'Bite assessment saved.')
        if not visit.doses.exists():
            return redirect('clinic:schedule_create', pk=visit.pk)
        return redirect('clinic:visit_detail', pk=visit.pk)
    return render(request, 'form_page.html', {
        'form': form,
        'title': 'Bite assessment',
        'subtitle': f'{visit.patient.full_name} · visit on {visit.visit_date:%b %d, %Y}',
        'back_url': reverse('clinic:visit_detail', args=[visit.pk]),
        'submit_label': 'Save assessment',
        'aside_template': 'clinic/_category_guide.html',
        'categories': ExposureCategory.objects.filter(is_active=True),
        'sections': [
            ('Animal', ['animal_type', 'animal_type_other', 'animal_ownership', 'animal_vaccination_status']),
            ('Exposure', ['exposure_type', 'wound_location', 'wound_description']),
            ('Classification', ['category', 'notes']),
        ],
    })


@clinical_required
def assessment_list(request):
    assessments = BiteAssessment.objects.select_related('visit__patient__barangay', 'category', 'assessed_by')
    q = request.GET.get('q', '').strip()
    category = get_int_param(request, 'category')
    animal = request.GET.get('animal', '')
    date_from = get_date_param(request, 'date_from')
    date_to = get_date_param(request, 'date_to')
    if q:
        for word in q.split():
            assessments = assessments.filter(
                Q(visit__patient__first_name__icontains=word) | Q(visit__patient__last_name__icontains=word)
                | Q(visit__patient__patient_code__icontains=word)
            )
    if category:
        assessments = assessments.filter(category_id=category)
    if animal in BiteAssessment.Animal.values:
        assessments = assessments.filter(animal_type=animal)
    if date_from:
        assessments = assessments.filter(visit__visit_date__gte=date_from)
    if date_to:
        assessments = assessments.filter(visit__visit_date__lte=date_to)
    assessments = assessments.order_by('-visit__visit_date', '-assessed_at')
    return render(request, 'clinic/assessment_list.html', {
        'page': paginate(request, assessments),
        'categories': ExposureCategory.objects.all(),
        'animals': BiteAssessment.Animal.choices,
        'q': q, 'category': category, 'animal': animal,
        'date_from': date_from, 'date_to': date_to,
    })


# Vaccination schedule ------------------------------------------------------

@clinical_required
def schedule_create(request, pk):
    visit = get_object_or_404(Visit.objects.select_related('patient'), pk=pk)
    form = ScheduleForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        vaccine = form.cleaned_data['vaccine_type']
        if visit.doses.filter(vaccine_type=vaccine).exists():
            messages.error(request, f'This visit already has a {vaccine} schedule.')
        else:
            doses = generate_schedule(visit, vaccine, form.cleaned_data['start_date'])
            messages.success(request, f'{len(doses)} dose{"s" if len(doses) != 1 else ""} of {vaccine} scheduled.')
            return redirect('clinic:visit_detail', pk=visit.pk)
    assessment = getattr(visit, 'assessment', None)
    return render(request, 'form_page.html', {
        'form': form,
        'title': 'Create vaccination schedule',
        'subtitle': f'{visit.patient.full_name} · '
                    + (f'{assessment.category}' if assessment else 'no assessment yet'),
        'intro': 'Follow-up dates are generated automatically from the regimen of the chosen vaccine. '
                 'Add a second schedule (for example rabies immunoglobulin) by repeating this step.',
        'back_url': reverse('clinic:visit_detail', args=[visit.pk]),
        'submit_label': 'Generate schedule',
    })


@clinical_required
def dose_record(request, pk):
    dose = get_object_or_404(Dose.objects.select_related('visit__patient', 'vaccine_type'), pk=pk)
    back = _safe_next(request, reverse('clinic:visit_detail', args=[dose.visit_id]))
    if dose.status == Dose.Status.COMPLETED:
        messages.info(request, 'This dose has already been recorded.')
        return redirect(back)
    form = DoseRecordForm(request.POST or None, dose=dose)
    if request.method == 'POST' and form.is_valid():
        try:
            record_dose(
                dose, form.cleaned_data['lot'], form.cleaned_data['date_given'], request.user,
                injection_site=form.cleaned_data['injection_site'], notes=form.cleaned_data['notes'],
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f'Dose {dose.dose_number} recorded and deducted from inventory.')
            return redirect(back)
    return render(request, 'form_page.html', {
        'form': form,
        'title': f'Record dose {dose.dose_number} · Day {dose.day_offset}',
        'subtitle': f'{dose.visit.patient.full_name} · {dose.vaccine_type} · due {dose.due_date:%b %d, %Y}',
        'back_url': back,
        'next': back,
        'submit_label': 'Record dose',
    })


@clinical_required
@require_POST
def dose_mark_missed(request, pk):
    dose = get_object_or_404(Dose, pk=pk)
    if dose.status == Dose.Status.PENDING:
        dose.status = Dose.Status.MISSED
        dose.save(update_fields=['status'])
        messages.warning(request, f'Dose {dose.dose_number} marked as missed. It now appears in the follow-up list.')
    return redirect(_safe_next(request, reverse('clinic:visit_detail', args=[dose.visit_id])))


@clinical_required
def dose_reschedule(request, pk):
    dose = get_object_or_404(Dose.objects.select_related('visit__patient', 'vaccine_type'), pk=pk)
    back = _safe_next(request, reverse('clinic:visit_detail', args=[dose.visit_id]))
    if dose.status == Dose.Status.COMPLETED:
        messages.info(request, 'Completed doses cannot be rescheduled.')
        return redirect(back)
    form = RescheduleForm(request.POST or None, instance=dose)
    if request.method == 'POST' and form.is_valid():
        dose = form.save(commit=False)
        dose.status = Dose.Status.PENDING
        dose.save()
        messages.success(request, f'Dose {dose.dose_number} moved to {dose.due_date:%b %d, %Y}.')
        return redirect(back)
    return render(request, 'form_page.html', {
        'form': form,
        'title': f'Reschedule dose {dose.dose_number}',
        'subtitle': f'{dose.visit.patient.full_name} · {dose.vaccine_type} · Day {dose.day_offset}',
        'back_url': back,
        'next': back,
        'submit_label': 'Reschedule',
    })


@clinical_required
@require_POST
def dose_delete(request, pk):
    dose = get_object_or_404(Dose, pk=pk)
    visit_id = dose.visit_id
    if dose.status == Dose.Status.COMPLETED:
        messages.error(request, 'Completed doses cannot be removed because they are linked to inventory.')
    else:
        dose.delete()
        messages.success(request, 'Scheduled dose removed.')
    return redirect('clinic:visit_detail', pk=visit_id)


# Appointments --------------------------------------------------------------

@clinical_required
def appointments(request):
    today = timezone.localdate()
    tab = request.GET.get('tab', 'today')
    on_date = get_date_param(request, 'date')
    days = get_int_param(request, 'days', 7)
    q = request.GET.get('q', '').strip()

    base = Dose.objects.select_related('visit__patient__barangay', 'vaccine_type', 'lot', 'administered_by').prefetch_related('visit__doses')
    pending = base.filter(status=Dose.Status.PENDING)
    follow_up = base.filter(Q(status=Dose.Status.MISSED) | Q(status=Dose.Status.PENDING, due_date__lt=today))
    counts = {
        'today': pending.filter(due_date=today).count(),
        'upcoming': pending.filter(due_date__gt=today, due_date__lte=today + timedelta(days=days)).count(),
        'followup': follow_up.count(),
    }

    if on_date:
        tab = 'date'
        doses = base.filter(due_date=on_date)
    elif tab == 'upcoming':
        doses = pending.filter(due_date__gt=today, due_date__lte=today + timedelta(days=days))
    elif tab == 'followup':
        doses = follow_up.order_by('due_date')
    elif tab == 'completed':
        doses = base.filter(status=Dose.Status.COMPLETED).order_by('-date_given', '-pk')
    else:
        tab = 'today'
        doses = base.filter(due_date=today)

    if q:
        for word in q.split():
            doses = doses.filter(
                Q(visit__patient__first_name__icontains=word) | Q(visit__patient__last_name__icontains=word)
                | Q(visit__patient__patient_code__icontains=word) | Q(visit__patient__contact_number__icontains=word)
            )

    return render(request, 'clinic/appointments.html', {
        'page': paginate(request, doses, per_page=30),
        'tab': tab, 'on_date': on_date, 'days': days, 'q': q,
        'counts': counts, 'today': today,
    })


@clinical_required
def appointment_calendar(request):
    today = timezone.localdate()
    try:
        year, month = (int(x) for x in request.GET.get('month', '').split('-'))
        first = date(year, month, 1)
    except ValueError:
        first = today.replace(day=1)

    cal = calendar.Calendar(firstweekday=6)
    weeks = cal.monthdatescalendar(first.year, first.month)
    start, end = weeks[0][0], weeks[-1][-1]

    tallies = {}
    rows = Dose.objects.filter(due_date__range=(start, end)).values('due_date', 'status')
    for row in rows:
        day = tallies.setdefault(row['due_date'], {'pending': 0, 'completed': 0, 'missed': 0})
        if row['status'] == Dose.Status.COMPLETED:
            day['completed'] += 1
        elif row['status'] == Dose.Status.MISSED or row['due_date'] < today:
            day['missed'] += 1
        else:
            day['pending'] += 1

    prev_month = (first - timedelta(days=1)).replace(day=1)
    next_month = (first + timedelta(days=32)).replace(day=1)
    return render(request, 'clinic/calendar.html', {
        'month': first,
        'weeks': [[(d, tallies.get(d)) for d in week] for week in weeks],
        'weekdays': ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
        'prev_month': prev_month, 'next_month': next_month,
        'today': today,
    })
