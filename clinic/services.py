from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction

from inventory.models import StockLot, StockMovement

from .models import Dose


@transaction.atomic
def generate_schedule(visit, vaccine_type, start_date):
    """Create one scheduled dose per day in the vaccine's regimen, counted from start_date."""
    doses = []
    for number, day in enumerate(vaccine_type.schedule_day_list(), start=1):
        doses.append(Dose.objects.create(
            visit=visit,
            vaccine_type=vaccine_type,
            dose_number=number,
            day_offset=day,
            due_date=start_date + timedelta(days=day),
        ))
    return doses


@transaction.atomic
def record_dose(dose, lot, date_given, user, injection_site='', notes=''):
    """Mark a dose as given and take one dose out of the chosen lot."""
    dose = Dose.objects.select_for_update().get(pk=dose.pk)
    if dose.status == Dose.Status.COMPLETED:
        raise ValidationError('This dose has already been recorded.')
    lot = StockLot.objects.select_for_update().get(pk=lot.pk)
    if lot.vaccine_type_id != dose.vaccine_type_id:
        raise ValidationError('The selected lot is for a different vaccine.')
    if lot.quantity_on_hand < 1:
        raise ValidationError(f'Lot {lot.lot_number} has no doses left.')

    lot.quantity_on_hand -= 1
    lot.save(update_fields=['quantity_on_hand'])

    dose.status = Dose.Status.COMPLETED
    dose.date_given = date_given
    dose.lot = lot
    dose.injection_site = injection_site
    dose.administered_by = user
    if notes:
        dose.notes = notes
    dose.save()

    StockMovement.objects.create(
        lot=lot,
        movement_type=StockMovement.Type.USED,
        quantity=-1,
        reason=f'{dose.visit.patient.patient_code} · dose {dose.dose_number} (Day {dose.day_offset})',
        dose=dose,
        performed_by=user,
    )
    return dose
