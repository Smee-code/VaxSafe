from django.conf import settings
from django.db import models
from django.utils import timezone


class Patient(models.Model):
    class Sex(models.TextChoices):
        MALE = 'M', 'Male'
        FEMALE = 'F', 'Female'

    patient_code = models.CharField('Patient ID', max_length=20, unique=True, editable=False)
    first_name = models.CharField(max_length=80)
    middle_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80)
    birth_date = models.DateField()
    sex = models.CharField(max_length=1, choices=Sex.choices)
    barangay = models.ForeignKey('core.Barangay', on_delete=models.PROTECT, related_name='patients')
    address_line = models.CharField('House no. / street / purok', max_length=200, blank=True)
    contact_number = models.CharField(max_length=30, blank=True)
    emergency_contact_name = models.CharField(max_length=150, blank=True)
    emergency_contact_relationship = models.CharField('Relationship', max_length=50, blank=True)
    emergency_contact_number = models.CharField(max_length=30, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f'{self.full_name} ({self.patient_code})'

    def save(self, *args, **kwargs):
        if not self.patient_code:
            prefix = f'VS-{timezone.localdate().year}-'
            last = (
                Patient.objects.filter(patient_code__startswith=prefix)
                .order_by('-patient_code').values_list('patient_code', flat=True).first()
            )
            number = int(last.rsplit('-', 1)[1]) + 1 if last else 1
            self.patient_code = f'{prefix}{number:05d}'
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        middle = f' {self.middle_name[0]}.' if self.middle_name else ''
        return f'{self.last_name}, {self.first_name}{middle}'

    @property
    def age(self):
        today = timezone.localdate()
        b = self.birth_date
        return today.year - b.year - ((today.month, today.day) < (b.month, b.day))

    @property
    def full_address(self):
        return ', '.join(part for part in [self.address_line, f'Brgy. {self.barangay}'] if part)


class Visit(models.Model):
    class Priority(models.TextChoices):
        URGENT = 'URGENT', 'Urgent'
        NORMAL = 'NORMAL', 'Normal'

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='visits')
    visit_date = models.DateField(default=timezone.localdate)
    incident_date = models.DateField()
    incident_place = models.CharField('Where it happened', max_length=200)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    triage_notes = models.TextField('Initial notes', blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-visit_date', '-created_at']

    def __str__(self):
        return f'Visit {self.visit_date:%b %d, %Y} – {self.patient.full_name}'

    @property
    def course_status(self):
        """Overall progress of the doses scheduled for this visit."""
        doses = list(self.doses.all())
        if not doses:
            return 'No schedule'
        if all(d.status == Dose.Status.COMPLETED for d in doses):
            return 'Completed'
        if any(d.status == Dose.Status.MISSED or d.is_overdue for d in doses):
            return 'Missed dose'
        return 'Ongoing'


class BiteAssessment(models.Model):
    class Animal(models.TextChoices):
        DOG = 'DOG', 'Dog'
        CAT = 'CAT', 'Cat'
        OTHER = 'OTHER', 'Other'

    class Ownership(models.TextChoices):
        OWNED = 'OWNED', 'Owned / pet'
        STRAY = 'STRAY', 'Stray'
        UNKNOWN = 'UNKNOWN', 'Unknown'

    class AnimalVaccination(models.TextChoices):
        VACCINATED = 'VACCINATED', 'Vaccinated'
        UNVACCINATED = 'UNVACCINATED', 'Not vaccinated'
        UNKNOWN = 'UNKNOWN', 'Unknown'

    class Exposure(models.TextChoices):
        BITE = 'BITE', 'Bite'
        SCRATCH = 'SCRATCH', 'Scratch'
        LICK = 'LICK', 'Lick'

    visit = models.OneToOneField(Visit, on_delete=models.CASCADE, related_name='assessment')
    animal_type = models.CharField(max_length=10, choices=Animal.choices)
    animal_type_other = models.CharField('If other, specify', max_length=60, blank=True)
    animal_ownership = models.CharField('Owned or stray', max_length=10, choices=Ownership.choices)
    animal_vaccination_status = models.CharField("Animal's vaccination status", max_length=15, choices=AnimalVaccination.choices, default=AnimalVaccination.UNKNOWN)
    exposure_type = models.CharField('Type of exposure', max_length=10, choices=Exposure.choices)
    wound_location = models.CharField('Wound location (body part)', max_length=100)
    wound_description = models.TextField(blank=True)
    category = models.ForeignKey('core.ExposureCategory', on_delete=models.PROTECT, related_name='assessments', verbose_name='Exposure category')
    notes = models.TextField('Assessment notes', blank=True)
    assessed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    assessed_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f'{self.category} · {self.visit}'

    @property
    def animal_display(self):
        if self.animal_type == self.Animal.OTHER and self.animal_type_other:
            return self.animal_type_other.title()
        return self.get_animal_type_display()


class Dose(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Scheduled'
        COMPLETED = 'COMPLETED', 'Completed'
        MISSED = 'MISSED', 'Missed'

    visit = models.ForeignKey(Visit, on_delete=models.CASCADE, related_name='doses')
    vaccine_type = models.ForeignKey('inventory.VaccineType', on_delete=models.PROTECT, related_name='doses')
    dose_number = models.PositiveSmallIntegerField()
    day_offset = models.PositiveSmallIntegerField(help_text='Day in the schedule, e.g. 0, 3, 7.')
    due_date = models.DateField(db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    date_given = models.DateField(null=True, blank=True)
    lot = models.ForeignKey('inventory.StockLot', null=True, blank=True, on_delete=models.PROTECT, related_name='doses')
    injection_site = models.CharField(max_length=60, blank=True)
    administered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['due_date', 'vaccine_type__name', 'dose_number']

    def __str__(self):
        return f'{self.vaccine_type} dose {self.dose_number} (Day {self.day_offset}) – {self.visit.patient.full_name}'

    @property
    def is_overdue(self):
        return self.status == self.Status.PENDING and self.due_date < timezone.localdate()

    @property
    def series(self):
        """All doses of the same regimen in this visit, for the dose strip. Uses prefetched doses when available."""
        return [d for d in self.visit.doses.all() if d.vaccine_type_id == self.vaccine_type_id]

    @property
    def strip_state(self):
        if self.status == self.Status.COMPLETED:
            return 'given'
        if self.status == self.Status.MISSED or self.is_overdue:
            return 'missed'
        if self.due_date == timezone.localdate():
            return 'due'
        return 'upcoming'

    @property
    def display_status(self):
        if self.is_overdue:
            return 'Overdue'
        if self.status == self.Status.PENDING and self.due_date == timezone.localdate():
            return 'Due today'
        return self.get_status_display()
