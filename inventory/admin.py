from django.contrib import admin

from .models import StockLot, StockMovement, StorageUnit, TemperatureLog, VaccineType

admin.site.register(VaccineType)
admin.site.register(StorageUnit)
admin.site.register(StockLot)
admin.site.register(StockMovement)
admin.site.register(TemperatureLog)
