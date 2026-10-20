"""WP10: tasks, append-only daily updates and the head progress view."""
from datetime import timedelta

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import AuditLogEntry
from tasks import services
from tasks.models import DailyUpdate, Task

from .access_fixtures import AccessWorld
from .factories import make_user


class TaskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = AccessWorld()
        cls.sw_peer = make_user("sw_peer", department=cls.w.software)
        cls.task = services.create_task(actor=cls.w.sw_member, changes={
            "title": "Port telemetry parser", "department": cls.w.software,
            "issue": cls.w.sw_issue, "fc": cls.w.fc,
            "due_date": services.today() - timedelta(days=1)})

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def ids(self, user, url="/api/tasks/"):
        r = self.client_for(user).get(url)
        self.assertEqual(r.status_code, 200, r.data)
        return {row["id"] for row in r.data["results"]}

    def test_teammate_cannot_see_task_unless_collaborator(self):
        self.assertEqual(self.ids(self.sw_peer), set())
        self.assertEqual(self.client_for(self.sw_peer).get(
            f"/api/tasks/{self.task.pk}/").status_code, 404)
        services.add_collaborator(self.task, actor=self.w.sw_member, user=self.sw_peer)
        self.assertEqual(self.ids(self.sw_peer), {self.task.pk})

    @override_settings(TASKS_TEAMMATES_VISIBLE=True)
    def test_teammate_visibility_flag(self):
        self.assertEqual(self.ids(self.sw_peer), {self.task.pk})
        self.assertEqual(self.ids(self.w.asm_member), set())

    def test_heads_and_manager_see_all_tasks_admin_does_not(self):
        for name in ("sw_head", "asm_head", "manager"):
            self.assertEqual(self.ids(self.w.actor(name)), {self.task.pk}, name)
        self.assertEqual(self.ids(self.w.admin), set())

    def test_task_audit_follows_task_scope(self):
        url = f"/api/audit-log/?entity_type=Task&entity_id={self.task.pk}"
        self.assertEqual(len(self.client_for(self.w.sw_member).get(url).data["results"]), 1)
        self.assertEqual(self.client_for(self.sw_peer).get(url).data["results"], [])

    def test_linked_issue_and_fc_hidden_from_readers_without_access(self):
        services.add_collaborator(self.task, actor=self.w.sw_member, user=self.w.admin)
        data = self.client_for(self.w.admin).get(f"/api/tasks/{self.task.pk}/").data
        self.assertIsNone(data["issue"])
        self.assertIsNone(data["fc"])
        mine = self.client_for(self.w.sw_member).get(f"/api/tasks/{self.task.pk}/").data
        self.assertEqual(mine["issue"], self.w.sw_issue.pk)

    def test_linking_an_unreadable_issue_is_rejected(self):
        r = self.client_for(self.w.sw_member).post("/api/tasks/", {
            "title": "x", "issue": self.w.asm_issue.pk}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_only_heads_assign_or_reassign_to_others(self):
        member = self.client_for(self.w.sw_member)
        r = member.post("/api/tasks/", {"title": "x",
                                        "accountable_user": self.sw_peer.pk}, format="json")
        self.assertEqual(r.status_code, 403)
        r = member.patch(f"/api/tasks/{self.task.pk}/",
                         {"accountable_user": self.sw_peer.pk}, format="json")
        self.assertEqual(r.status_code, 403)
        r = self.client_for(self.w.sw_head).post(
            "/api/tasks/", {"title": "x", "accountable_user": self.sw_peer.pk},
            format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["accountable_user"], self.sw_peer.pk)
        self.assertEqual(r.data["created_by"], self.w.sw_head.pk)

    def test_collaborator_cannot_change_the_task(self):
        services.add_collaborator(self.task, actor=self.w.sw_member, user=self.sw_peer)
        r = self.client_for(self.sw_peer).patch(f"/api/tasks/{self.task.pk}/",
                                                {"status": "done"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_no_delete_route(self):
        r = self.client_for(self.w.sw_head).delete(f"/api/tasks/{self.task.pk}/")
        self.assertEqual(r.status_code, 405)

    def test_scenario_11_blocker_and_dated_update_in_head_view(self):
        yesterday = DailyUpdate.objects.create(
            task=self.task, author=self.w.sw_member,
            date=services.today() - timedelta(days=1), progress="Parsed headers")
        member = self.client_for(self.w.sw_member)
        r = member.patch(f"/api/tasks/{self.task.pk}/", {"status": "blocked"},
                         format="json")
        self.assertEqual(r.status_code, 200, r.data)
        r = member.post("/api/daily-updates/", {
            "task": self.task.pk, "progress": "Waiting on sample logs",
            "next_step": "Parse payload", "blockers": "No logs from service"},
            format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["date"], services.today().isoformat())

        view = self.client_for(self.w.sw_head).get(
            f"/api/progress/?department={self.w.software.pk}").data
        self.assertEqual([t["id"] for t in view["blocked"]], [self.task.pk])
        self.assertEqual([t["id"] for t in view["overdue"]], [self.task.pk])
        self.assertEqual([u["blockers"] for u in view["updates_today"]],
                         ["No logs from service"])
        missing = {p["id"] for p in view["no_update_today"]}
        self.assertNotIn(self.w.sw_member.pk, missing)
        self.assertIn(self.sw_peer.pk, missing)
        for key in view:  # no activity counts or rankings
            self.assertNotIn("count", key)
            self.assertNotIn("rank", key)

        yesterday.refresh_from_db()
        self.assertEqual(yesterday.progress, "Parsed headers")

    def test_progress_view_is_for_heads_and_manager(self):
        for name in ("sw_member", "admin", "svc_member"):
            self.assertEqual(self.client_for(self.w.actor(name)).get(
                "/api/progress/").status_code, 403, name)
        for name in ("asm_head", "manager"):
            self.assertEqual(self.client_for(self.w.actor(name)).get(
                "/api/progress/").status_code, 200, name)

    def test_daily_updates_are_append_only(self):
        update = services.post_update(actor=self.w.sw_member, task=self.task,
                                      progress="first")
        with self.assertRaises(PermissionError):
            update.save()
        member = self.client_for(self.w.sw_member)
        self.assertEqual(member.patch(f"/api/daily-updates/{update.pk}/",
                                      {"progress": "x"}, format="json").status_code, 405)
        self.assertEqual(member.delete(f"/api/daily-updates/{update.pk}/").status_code, 405)

    def test_same_day_correction_keeps_history(self):
        member = self.client_for(self.w.sw_member)
        first = services.post_update(actor=self.w.sw_member, task=self.task,
                                     progress="first")
        r = member.post("/api/daily-updates/", {"task": self.task.pk,
                                                "progress": "corrected",
                                                "supersedes": first.pk}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        current = member.get("/api/daily-updates/?current=1").data["results"]
        self.assertEqual([u["progress"] for u in current], ["corrected"])
        everything = member.get("/api/daily-updates/").data["results"]
        self.assertEqual({u["progress"] for u in everything}, {"first", "corrected"})
        again = member.post("/api/daily-updates/", {"task": self.task.pk, "progress": "x",
                                                    "supersedes": first.pk}, format="json")
        self.assertEqual(again.status_code, 409)

    def test_earlier_days_cannot_be_corrected(self):
        old = DailyUpdate.objects.create(task=self.task, author=self.w.sw_member,
                                         date=services.today() - timedelta(days=1),
                                         progress="old")
        r = self.client_for(self.w.sw_member).post("/api/daily-updates/", {
            "task": self.task.pk, "progress": "rewrite", "supersedes": old.pk},
            format="json")
        self.assertEqual(r.status_code, 409)

    def test_non_participant_cannot_post_on_task(self):
        r = self.client_for(self.w.sw_head).post("/api/daily-updates/", {
            "task": self.task.pk, "progress": "x"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_teammate_cannot_read_updates_on_hidden_task(self):
        services.post_update(actor=self.w.sw_member, task=self.task, progress="private")
        rows = self.client_for(self.sw_peer).get("/api/daily-updates/").data["results"]
        self.assertEqual(rows, [])

    def test_my_queue_lists_tasks_and_update_status(self):
        client = self.client_for(self.w.sw_member)
        data = client.get("/api/me/queue/").data
        self.assertEqual([t["id"] for t in data["tasks"]], [self.task.pk])
        self.assertTrue(data["tasks"][0]["is_overdue"])
        self.assertFalse(data["updated_today"])
        services.post_update(actor=self.w.sw_member, progress="general")
        self.assertTrue(client.get("/api/me/queue/").data["updated_today"])
        self.assertEqual(self.client_for(self.sw_peer).get("/api/me/queue/").data["tasks"], [])

    def test_task_changes_are_audited(self):
        services.update_task(self.task, actor=self.w.sw_member, changes={"status": "done"})
        entry = AuditLogEntry.objects.filter(entity_type="Task",
                                             action=AuditLogEntry.ACTION_UPDATE).first()
        self.assertEqual(entry.after, {"status": Task.DONE})
