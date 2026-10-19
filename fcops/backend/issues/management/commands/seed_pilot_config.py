"""``python manage.py seed_pilot_config``: PLACEHOLDER queues and routing
rules (IMPLEMENTATION_PLAN Appendix A), for development and staging only.

A queue is created for the first department of each listed kind, with that
department's head as head and the first manager as backup; the fallback
queue has the first manager as both coordinator and backup until the real
coordinator is decided. Re-running updates rather than duplicates.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Capability, Department, TeamMembership, User
from issues.models import ProductArea, Queue, RoutingRule

ROUTES = {  # PLACEHOLDER mapping, to be confirmed with the heads
    Department.KIND_SOFTWARE: [ProductArea.GCS, ProductArea.CONFIGURATOR],
    Department.KIND_FIRMWARE: [ProductArea.FIRMWARE, ProductArea.PARAMETERS],
    Department.KIND_HARDWARE: [ProductArea.FC_HARDWARE, ProductArea.MECHANICAL],
    Department.KIND_SERVICE: [ProductArea.ROVER],
}


class Command(BaseCommand):
    help = "Create placeholder queues and routing rules (not for production)."

    def handle(self, *args, **options):
        if not settings.DEBUG or settings.PRODUCTION:
            raise CommandError("Refusing to seed placeholder routing: DEBUG is off "
                               "or PRODUCTION=1.")
        manager = User.objects.filter(
            is_active=True, capability_grants__capability=Capability.IS_MANAGER,
            capability_grants__revoked_at__isnull=True).first()
        if manager is None:
            raise CommandError("No active manager to act as coordinator/backup.")
        Queue.objects.update_or_create(is_fallback=True, defaults={
            "name": "Fallback (coordinator)", "head": manager, "backup": manager})
        for kind, areas in ROUTES.items():
            dept = Department.objects.filter(kind=kind).order_by("pk").first()
            head = dept and TeamMembership.objects.filter(
                department=dept, role=TeamMembership.ROLE_HEAD,
                active_to__isnull=True).select_related("user").first()
            if head is None:
                self.stdout.write(f"skip {kind}: no department with a head")
                continue
            queue, _ = Queue.objects.update_or_create(department=dept, defaults={
                "name": dept.name, "head": head.user, "backup": manager})
            for area in areas:
                RoutingRule.objects.update_or_create(
                    product_area=area, queue=queue, defaults={"priority": 100})
            self.stdout.write(f"{queue.name}: {', '.join(areas)}")
        self.stdout.write(self.style.SUCCESS("Placeholder routing configured."))
