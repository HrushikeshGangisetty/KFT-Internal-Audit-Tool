from django.contrib import admin

from .models import (ChecklistTemplate, FCEvent, FCModelType, FirmwareRecord,
                     FlightController, ParameterProfile, ReworkRecord,
                     SoftwareVersion, StageRecord, TestResult)

for model in (FCModelType, ParameterProfile, SoftwareVersion, ChecklistTemplate,
              StageRecord, ReworkRecord, FirmwareRecord, TestResult, FCEvent):
    admin.site.register(model)


@admin.register(FlightController)
class FlightControllerAdmin(admin.ModelAdmin):
    list_display = ("serial", "fc_model", "current_stage", "status", "created_at")
    list_filter = ("status", "current_stage", "fc_model")
    search_fields = ("serial", "hardware_revision", "pcb_batch")
