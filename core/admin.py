from django.contrib import admin

from .models import AuditLog, Barangay, CenterSettings, ExposureCategory

admin.site.register(CenterSettings)
admin.site.register(ExposureCategory)
admin.site.register(Barangay)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'user', 'action', 'model_name', 'object_repr']
    list_filter = ['action', 'model_name']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
