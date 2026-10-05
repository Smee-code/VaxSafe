from django.contrib import admin

from .models import BiteAssessment, Dose, Patient, Visit


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ['patient_code', 'last_name', 'first_name', 'barangay', 'contact_number']
    search_fields = ['patient_code', 'last_name', 'first_name', 'contact_number']


admin.site.register(Visit)
admin.site.register(BiteAssessment)
admin.site.register(Dose)
