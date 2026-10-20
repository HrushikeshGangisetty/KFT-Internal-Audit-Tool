from rest_framework import mixins, viewsets
from access import policy
from access.mixins import ScopedViewSetMixin
from . import services
from .models import Customer, CustomerContact, Deployment
from .serializers import CustomerSerializer, ContactSerializer, DeploymentSerializer


class MaintainedViewSet(ScopedViewSetMixin, mixins.CreateModelMixin,
                        mixins.UpdateModelMixin, mixins.RetrieveModelMixin,
                        mixins.ListModelMixin, viewsets.GenericViewSet):
    # No delete: linked records and audit history must remain available.
    def perform_create(self, serializer):
        serializer.instance = services.save_record(serializer.Meta.model,
            actor=self.request.user, changes=serializer.validated_data)

    def perform_update(self, serializer):
        serializer.instance = services.save_record(serializer.Meta.model,
            actor=self.request.user, changes=serializer.validated_data,
            instance=serializer.instance)


class CustomerViewSet(MaintainedViewSet):
    serializer_class = CustomerSerializer

    def get_scoped_queryset(self):
        return policy.visible_customers(self.request.user).order_by("id")


class ContactViewSet(MaintainedViewSet):
    serializer_class = ContactSerializer
    filterset_fields = ("customer",)

    def get_scoped_queryset(self):
        return policy.visible_customer_contacts(self.request.user).order_by("id")


class DeploymentViewSet(MaintainedViewSet):
    serializer_class = DeploymentSerializer
    filterset_fields = ("customer",)

    def get_scoped_queryset(self):
        return policy.visible_deployments(self.request.user).prefetch_related("units").order_by("id")
