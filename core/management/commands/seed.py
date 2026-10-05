import random
import secrets
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from clinic.models import BiteAssessment, Dose, Patient, Visit
from clinic.services import generate_schedule, record_dose
from core.models import AuditLog, Barangay, CenterSettings, ExposureCategory
from inventory.models import StockLot, StockMovement, StorageUnit, TemperatureLog, VaccineType

CATEGORIES = [
    ('I', 'Category I – No exposure',
     'Touching or feeding animals, or licks on intact skin.',
     'Wash exposed skin. No post-exposure prophylaxis needed if the history is reliable.'),
    ('II', 'Category II – Minor exposure',
     'Nibbling of uncovered skin, or minor scratches or abrasions without bleeding.',
     'Wound washing and immediate vaccination.'),
    ('III', 'Category III – Severe exposure',
     'Single or multiple bites or scratches that break the skin, licks on broken skin, '
     'saliva contact with mucous membranes, or any bat exposure.',
     'Wound washing, immediate vaccination and rabies immunoglobulin.'),
]

VACCINES = [
    ('PVRV (Purified Vero Cell Rabies Vaccine)', 'VACCINE', 'IM', '0,3,7,14,28', None),
    ('PCECV (Purified Chick Embryo Cell Vaccine)', 'VACCINE', 'ID', '0,3,7', None),
    ('ERIG (Equine Rabies Immunoglobulin)', 'RIG', 'Wound infiltration', '0', 5),
    ('Tetanus Toxoid', 'OTHER', 'IM', '0', 5),
]

BARANGAYS = [
    'Poblacion', 'San Isidro', 'San Jose', 'Santa Cruz', 'San Roque', 'Bagong Silang',
    'Mabini', 'Rizal', 'Malvar', 'Santo Niño', 'San Antonio', 'Del Pilar',
]

USERS = [
    ('admin', 'Maria', 'Santos', User.Role.ADMIN, 'Center Administrator'),
    ('staff', 'Jose', 'Reyes', User.Role.STAFF, 'Nurse'),
    ('personnel', 'Ana', 'Cruz', User.Role.PERSONNEL, 'Municipal Health Officer'),
]
DEMO_PASSWORD = 'VaxSafe@2026'

FIRST_NAMES = ['Juan', 'Maria', 'Jose', 'Ana', 'Pedro', 'Rosa', 'Mark', 'Angel', 'John', 'Kristine', 'Paolo',
               'Liza', 'Ramon', 'Grace', 'Carlo', 'Joy', 'Miguel', 'Bea', 'Nico', 'Ella', 'Rafael', 'Camille']
LAST_NAMES = ['Dela Cruz', 'Garcia', 'Reyes', 'Ramos', 'Mendoza', 'Santos', 'Flores', 'Gonzales', 'Bautista',
              'Villanueva', 'Fernandez', 'Cruz', 'De Leon', 'Aquino', 'Castillo', 'Rivera', 'Torres', 'Navarro']
PLACES = ['Near home', 'Neighbor\'s yard', 'Street / road', 'School', 'Market', 'Farm', 'Inside the house']
BODY_PARTS = ['Leg', 'Hand', 'Foot', 'Forearm', 'Thigh', 'Fingers', 'Ankle', 'Face', 'Upper arm']


class Command(BaseCommand):
    help = 'Load default settings and demo accounts. Use --demo to add sample patients, stock and readings.'

    def add_arguments(self, parser):
        parser.add_argument('--demo', action='store_true', help='Also create sample patients, stock and temperature logs.')

    @transaction.atomic
    def handle(self, *args, **options):
        started = timezone.now()
        center = CenterSettings.load()
        if not center.address:
            center.address = 'Municipal Health Office, Poblacion'
            center.save()

        for order, (code, name, desc, mgmt) in enumerate(CATEGORIES):
            ExposureCategory.objects.get_or_create(code=code, defaults={
                'name': name, 'description': desc, 'management': mgmt, 'sort_order': order,
            })
        for name, kind, route, days, threshold in VACCINES:
            VaccineType.objects.get_or_create(name=name, defaults={
                'kind': kind, 'route': route, 'schedule_days': days, 'low_stock_threshold': threshold,
            })
        for name in BARANGAYS:
            Barangay.objects.get_or_create(name=name)
        for name, location in [('Vaccine Refrigerator 1', 'Treatment room'), ('Cold Box A', 'Storage room')]:
            StorageUnit.objects.get_or_create(name=name, defaults={'location': location})

        # Local/demo installs get the shared demo password; a live server (DEBUG off)
        # gets a random password per account, shown once here.
        use_demo_password = settings.DEBUG or options['demo']
        for username, first, last, role, position in USERS:
            if not User.objects.filter(username=username).exists():
                password = DEMO_PASSWORD if use_demo_password else secrets.token_urlsafe(9)
                user = User(username=username, first_name=first, last_name=last, role=role, position=position)
                user.set_password(password)
                user.save()
                self.stdout.write(f'  Created {role.label} account: {username} / {password}')
        if not use_demo_password:
            self.stdout.write(self.style.WARNING('  Write these passwords down now. They are not shown again.'))

        if options['demo']:
            if Patient.objects.exists():
                self.stdout.write(self.style.WARNING('Patients already exist, so demo records were not added.'))
            else:
                self._demo()

        # Setup records are not user activity, so keep them out of the audit trail.
        AuditLog.objects.filter(timestamp__gte=started, user__isnull=True).delete()
        self.stdout.write(self.style.SUCCESS('VaxSafe is ready.'))

    def _demo(self):
        random.seed(42)
        today = timezone.localdate()
        staff = User.objects.get(username='staff')
        fridge, coldbox = StorageUnit.objects.order_by('name')
        pvrv, pcecv, erig, tt = [VaccineType.objects.get(name=v[0]) for v in VACCINES]
        categories = {c.code: c for c in ExposureCategory.objects.all()}
        barangays = list(Barangay.objects.all())
        weights = [9, 7, 7, 5, 4, 4, 3, 3, 2, 2, 1, 1]

        def receive(vaccine, lot_number, qty, expiry, received, unit):
            lot = StockLot.objects.create(
                vaccine_type=vaccine, lot_number=lot_number, quantity_received=qty, quantity_on_hand=qty,
                expiry_date=expiry, date_received=received, supplier='DOH Regional Office', storage_unit=unit,
                received_by=staff,
            )
            StockMovement.objects.create(lot=lot, movement_type=StockMovement.Type.RECEIVED, quantity=qty,
                                         reason='Received from DOH Regional Office', performed_by=staff,
                                         created_at=self._at(received, 9))
            return lot

        long_ago = today - timedelta(days=260)
        main_lots = {
            pvrv.pk: receive(pvrv, 'PV24-0815', 300, today + timedelta(days=400), long_ago, fridge),
            pcecv.pk: receive(pcecv, 'PC24-1102', 260, today + timedelta(days=380), long_ago, fridge),
            erig.pk: receive(erig, 'ER24-0310', 90, today + timedelta(days=300), long_ago, fridge),
            tt.pk: receive(tt, 'TT24-0007', 40, today + timedelta(days=500), long_ago, coldbox),
        }
        receive(pvrv, 'PV24-0402', 12, today + timedelta(days=18), today - timedelta(days=200), fridge)
        receive(pcecv, 'PC23-0911', 5, today - timedelta(days=9), today - timedelta(days=330), coldbox)

        for i in range(70):
            patient = Patient.objects.create(
                first_name=random.choice(FIRST_NAMES), last_name=random.choice(LAST_NAMES),
                middle_name=random.choice(LAST_NAMES), sex=random.choice('MF'),
                birth_date=today - timedelta(days=random.randint(3 * 365, 70 * 365)),
                barangay=random.choices(barangays, weights=weights[:len(barangays)])[0],
                address_line=f'Purok {random.randint(1, 7)}',
                contact_number=f'09{random.randint(100000000, 999999999)}',
                emergency_contact_name=f'{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}',
                emergency_contact_relationship=random.choice(['Mother', 'Father', 'Spouse', 'Sibling']),
                emergency_contact_number=f'09{random.randint(100000000, 999999999)}',
                created_by=staff,
            )
            visit_date = today - timedelta(days=int(random.triangular(0, 230, 10)))
            code = random.choices(['I', 'II', 'III'], weights=[1, 6, 4])[0]
            visit = Visit.objects.create(
                patient=patient, visit_date=visit_date, incident_date=visit_date - timedelta(days=random.choice([0, 0, 0, 1, 2])),
                incident_place=random.choice(PLACES), priority='URGENT' if code == 'III' else 'NORMAL',
                triage_notes='Wound washed with soap and water.', created_by=staff,
            )
            animal = random.choices(['DOG', 'CAT', 'OTHER'], weights=[14, 5, 1])[0]
            BiteAssessment.objects.create(
                visit=visit, animal_type=animal, animal_type_other='Monkey' if animal == 'OTHER' else '',
                animal_ownership=random.choices(['OWNED', 'STRAY', 'UNKNOWN'], weights=[6, 3, 1])[0],
                animal_vaccination_status=random.choice(['VACCINATED', 'UNVACCINATED', 'UNKNOWN']),
                exposure_type={'I': 'LICK', 'II': random.choice(['SCRATCH', 'BITE']), 'III': 'BITE'}[code],
                wound_location=random.choice(BODY_PARTS), category=categories[code],
                assessed_by=staff, assessed_at=self._at(visit_date, 10),
            )
            if code == 'I':
                continue
            regimens = [random.choice([pvrv, pcecv])] + ([erig] if code == 'III' else [])
            for vaccine in regimens:
                for dose in generate_schedule(visit, vaccine, visit_date):
                    self._play_dose(dose, main_lots[vaccine.pk], staff, today)

        for unit in (fridge, coldbox):
            for days_back in range(30, -1, -1):
                day = today - timedelta(days=days_back)
                for hour in (8, 16):
                    if day == today and hour > timezone.localtime().hour:
                        continue
                    reading = Decimal(str(round(random.uniform(3.0, 7.0), 1)))
                    if unit == coldbox and days_back in (12, 4) and hour == 16:
                        reading = Decimal('9.4') if days_back == 12 else Decimal('1.3')
                    TemperatureLog.objects.create(
                        unit=unit, reading=reading, recorded_at=self._at(day, hour), recorded_by=staff,
                        notes='Moved vaccines to backup unit.' if reading > 8 or reading < 2 else '',
                    )

        wasted = StockMovement.objects.create(
            lot=main_lots[pvrv.pk], movement_type=StockMovement.Type.WASTED, quantity=-2,
            reason='Vial dropped during preparation', performed_by=staff, created_at=self._at(today - timedelta(days=20), 11),
        )
        wasted.lot.quantity_on_hand -= 2
        wasted.lot.save()
        self.stdout.write(f'  Created {Patient.objects.count()} demo patients with visits, doses, stock and temperature logs.')

    def _play_dose(self, dose, lot, user, today):
        if dose.due_date > today:
            return
        roll = random.random()
        if roll < 0.86:
            given = dose.due_date + timedelta(days=random.choice([0, 0, 0, 1]))
            given = min(given, today)
            record_dose(dose, lot, given, user, injection_site=random.choice(['Left deltoid', 'Right deltoid']))
            StockMovement.objects.filter(dose=dose).update(created_at=self._at(given, random.randint(8, 15)))
        elif roll < 0.94 and dose.due_date < today:
            dose.status = Dose.Status.MISSED
            dose.save()
        # Otherwise leave it pending, so it shows as due today or overdue.

    @staticmethod
    def _at(day, hour):
        return timezone.make_aware(datetime.combine(day, time(hour, random.randint(0, 59))))
