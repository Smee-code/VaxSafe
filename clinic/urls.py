from django.urls import path

from . import views

app_name = 'clinic'

urlpatterns = [
    path('patients/', views.patient_list, name='patient_list'),
    path('patients/new/', views.patient_create, name='patient_create'),
    path('patients/<int:pk>/', views.patient_detail, name='patient_detail'),
    path('patients/<int:pk>/edit/', views.patient_edit, name='patient_edit'),
    path('patients/<int:pk>/visits/new/', views.visit_create, name='visit_create'),
    path('visits/<int:pk>/', views.visit_detail, name='visit_detail'),
    path('visits/<int:pk>/edit/', views.visit_edit, name='visit_edit'),
    path('visits/<int:pk>/assessment/', views.assessment_edit, name='assessment_edit'),
    path('visits/<int:pk>/schedule/', views.schedule_create, name='schedule_create'),
    path('doses/<int:pk>/record/', views.dose_record, name='dose_record'),
    path('doses/<int:pk>/missed/', views.dose_mark_missed, name='dose_missed'),
    path('doses/<int:pk>/reschedule/', views.dose_reschedule, name='dose_reschedule'),
    path('doses/<int:pk>/delete/', views.dose_delete, name='dose_delete'),
    path('assessments/', views.assessment_list, name='assessment_list'),
    path('appointments/', views.appointments, name='appointments'),
    path('appointments/calendar/', views.appointment_calendar, name='calendar'),
]
