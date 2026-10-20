from django.db import models
from core.models import TimeStampedModel


class Customer(TimeStampedModel):
    name = models.CharField(max_length=255)
    region = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True, help_text="Engineering summary only; contacts belong in CustomerContact.")

    def __str__(self):
        return self.name


class CustomerContact(TimeStampedModel):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="contacts")
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=80, blank=True)
    email = models.EmailField(blank=True)
    role = models.CharField(max_length=120, blank=True)

    def __str__(self):
        return f"CustomerContact#{self.pk}"


class Deployment(TimeStampedModel):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="deployments")
    site_name = models.CharField(max_length=255)
    units = models.ManyToManyField("fc.FlightController", blank=True, related_name="deployments")
    gcs_version_at_handover = models.CharField(max_length=64, blank=True)
    notes = models.TextField(blank=True)
    deployed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.site_name
