from rest_framework import serializers
from access import policy
from access.mixins import ScopedPrimaryKeyRelatedField
from .models import Customer, CustomerContact, Deployment


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ("id", "name", "region", "notes", "created_at", "updated_at")


class ContactSerializer(serializers.ModelSerializer):
    customer = ScopedPrimaryKeyRelatedField(policy.contact_customers)

    class Meta:
        model = CustomerContact
        fields = ("id", "customer", "name", "phone", "email", "role", "created_at", "updated_at")


class DeploymentSerializer(serializers.ModelSerializer):
    customer = ScopedPrimaryKeyRelatedField(policy.visible_customers)
    units = ScopedPrimaryKeyRelatedField(policy.visible_fcs, many=True, required=False)

    class Meta:
        model = Deployment
        fields = ("id", "customer", "site_name", "units", "gcs_version_at_handover",
                  "notes", "deployed_at", "created_at", "updated_at")
