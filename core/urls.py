from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('settings/', views.settings_index, name='settings'),
    path('settings/<slug:kind>/', views.settings_list, name='settings_list'),
    path('settings/<slug:kind>/new/', views.settings_edit, name='settings_create'),
    path('settings/<slug:kind>/<int:pk>/edit/', views.settings_edit, name='settings_edit'),
    path('settings/<slug:kind>/<int:pk>/toggle/', views.settings_toggle, name='settings_toggle'),
    path('audit/', views.audit_log, name='audit_log'),
    path('backup/', views.backup, name='backup'),
    path('backup/database/', views.backup_database, name='backup_database'),
    path('backup/json/', views.backup_json, name='backup_json'),
]
