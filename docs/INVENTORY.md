# WP0 inventory — 17 October 2026

## Scope and source provenance

Inventory and validation target the working-tree snapshot preserved at `900680d` on `preserve/local-work-2026-10-17`. The WP0 branch `wp/00-baseline` starts at `main` (`ab2d324`) and does not merge application or parameter changes. Source paths below refer to the preservation snapshot unless explicitly stated. Validation runs in an isolated copy of that snapshot, not against Supabase.

The supplied implementation plan targets PRD v0.2. Only v0.1 was present; `docs/PRD.md` preserves it without inventing the missing revision. Later WPs remain gated.

## Initial Git records

### git status --porcelain

```text
 M fcops.tar.gz
 M fcops/IMPLEMENTATION_NOTES.md
 M fcops/README.md
 M fcops/backend/config/settings.py
 M fcops/backend/config/urls.py
 M fcops/backend/core/views.py
 M fcops/backend/fc/lifecycle.py
 M fcops/backend/fc/models.py
 M fcops/backend/fc/serializers.py
 M fcops/backend/fc/services.py
 M fcops/backend/fc/views.py
 M fcops/backend/requirements.txt
 M fcops/e2e/config_features.py
 M fcops/e2e/ui_walkthrough.py
 M fcops/frontend/src/App.jsx
 M fcops/frontend/src/pages/FcDetail.jsx
?? AGENTS.md
?? fcops/PRD.md
?? fcops/backend/core/management/commands/serve.py
?? fcops/backend/fc/migrations/0005_parameterfile.py
?? fcops/backend/fc/parameters.py
?? fcops/backend/tests/test_param_and_routing.py
?? fcops/e2e/param_and_routing.py
?? fcops/frontend/src/pages/ParamCompare.jsx
```

### git stash list

```text

```

### git log -1

```text
commit ab2d324e6bd1308270925527036532dce42b5b6e
Author: Hrushikesh-Gangisetty <hrushikeshgangisett@gmail.com>
Date:   Wed Aug 26 00:49:46 2026 +0530

    changed
```

## Preservation and exclusions

All 24 initial changed/untracked paths were committed as-is, including the already-modified archive. No archive was regenerated. `.env` and the ignored certificate bundle were not staged. A pattern scan of eligible files and archive members found database-URI examples in README/configuration fixtures only; these were reviewed as synthetic examples. No actual credentials were found in the staged paths. This scan is not a proof that the historical repository contains no secrets.

Excluded sensitive-looking paths (paths only):

- `fcops/backend/.env` (existing local environment; not read or copied).
- `fcops/backend/.venv/Lib/site-packages/pip/_vendor/certifi/cacert.pem` (ignored third-party CA bundle; not local work).

### Byte preservation manifest

Git blobs were staged with `core.autocrlf=false`; SHA-256 below refers to the original bytes.

| Path | SHA-256 |
|---|---|
| `fcops.tar.gz` | `4819f8225c93eb8798aa1f7a8c571f3b3eba27878d5675563c7417af76598ae6` |
| `fcops/IMPLEMENTATION_NOTES.md` | `5d9200bcfcaf15c6b89824c398955d34f815b581067b8756c36292eba8ba9d1c` |
| `fcops/README.md` | `018d7700f18d767b76a7b0ffa61674ce0ec6412942512b4be3832bd58e8b0410` |
| `fcops/backend/config/settings.py` | `a22e51c8defb49168be6b5dca9b4b37dea5b2e3a1e8921d08ac6c7ef76d57ef8` |
| `fcops/backend/config/urls.py` | `1f0738a892753a98196fcc5062d0b58f43e5b04135051f48f0692f8a0726e988` |
| `fcops/backend/core/views.py` | `2c5a348d23da692412de9a871edb12ed7a4cd51802461aac86c9ac81c9d75dde` |
| `fcops/backend/fc/lifecycle.py` | `6d649dff2847c127bec98c623ef7cb152bb8d33940e6eb5b28b94048ef904a91` |
| `fcops/backend/fc/models.py` | `ea2e63383492de692a6310f5a0d63e4e59e386c4c84d3dd2ddbe57fbc1ca2420` |
| `fcops/backend/fc/serializers.py` | `fb9ee94c48b98c21a8cfe4977ee268aab3c51bbc39e88cfa3db1317358800ee5` |
| `fcops/backend/fc/services.py` | `2d9602701fe9c5e34a4d97de12916816c16c09f97b79fd35dfaab869f27d9951` |
| `fcops/backend/fc/views.py` | `63f08b698a237bc3de086623b1f9c9b637e8ad2e80b3980901c270a95103ec5a` |
| `fcops/backend/requirements.txt` | `cbb14cc39fdb8dea7fab48134f28c3fcfa6ddbafcbc0f53a36203af3ba00bdfa` |
| `fcops/e2e/config_features.py` | `ae3ee89d744ec6dac53a67479252f7fab493920cc8aa9555525dedca5aec8388` |
| `fcops/e2e/ui_walkthrough.py` | `6855d74b18db9553d057c0f57646bf7a7bfbaca021a0c915115a290c3ba95951` |
| `fcops/frontend/src/App.jsx` | `cb5a10bc605e1799f6fb988fe243fdf6197afbc9feb581fcba83c82ac09b5dd2` |
| `fcops/frontend/src/pages/FcDetail.jsx` | `27c814bd61c631c5c705c375fc246fc2972c490ae64b671941ea67acb2e3ba23` |
| `AGENTS.md` | `e4fcf40e7f76271e294843e4a0c948572711f2698673d70f7b6cf4d427b5a4c8` |
| `fcops/PRD.md` | `571b4c9e85f7038c3cf0978ed0632704fcf583fc590c9db031077279ec32e65f` |
| `fcops/backend/core/management/commands/serve.py` | `e12ec7bdf6d3f817b58cd73c274d7d7efd3f10a229a76b90c48975238946c181` |
| `fcops/backend/fc/migrations/0005_parameterfile.py` | `17858bd3dba828c96a698970ee7d2de9cfe61137175344e4ff62e99c14521da0` |
| `fcops/backend/fc/parameters.py` | `b05181cdc7b8c1b5237af8c3de88c84411a1736abf22a2d1818a284531d09c46` |
| `fcops/backend/tests/test_param_and_routing.py` | `ed1d80a65f06195a1dc050ae81a7b0f683c89641123f0a836a81a1e582875761` |
| `fcops/e2e/param_and_routing.py` | `bb3d57b9c84f7dec6dc38ebe55490bc7533c4d173b7244955e32fae47f6d6e1a` |
| `fcops/frontend/src/pages/ParamCompare.jsx` | `1c3f4ba102371c679ef63f2ffdb3c54c95ad18a4ae5e62e04e658d777cc2aaaf` |

Manual/programmatic check: the preservation commit file set exactly matches all 24 paths from the initial status; every committed blob matches its original SHA-256. Remote push was observed successful.

## Section 2 baseline matrix

| Area | Finding | Evidence |
|---|---|---|
| Backend | confirmed: Django 5.2.17, DRF 3.18.0, PostgreSQL backend and the four named apps; PostgreSQL 16 runtime checked separately | `fcops/backend/requirements.txt`, `config/settings.py` |
| Frontend | different: React 19 + Vite 8; listed production pages present except Diagnostics; ParamCompare, PushUpdate, ManageFirmware, TestConfiguration and FcModels also present | `fcops/frontend/package.json`, `src/App.jsx`, `src/pages/` |
| Auth | confirmed: localStorage JWT access/refresh pair | `fcops/frontend/src/lib/api.js`, `auth.jsx` |
| Access | confirmed: broad authenticated read with universal-read regression; notifications restricted to recipient | `fcops/backend/accounts/permissions.py`, `tests/test_api_rbac.py::test_everyone_can_read_everything`, `core/views.py` |
| Issues | different: FC required; stage is a required CharField with Stage choices, not a Stage FK; optional discovered_stage_record FK | `fcops/backend/issues/models.py::Issue`, `issues/serializers.py::IssueCreateSerializer`, `issues/services.py::create_issue` |
| Releases | confirmed: SoftwareUpdate named approved_by FK plus approved_at; no dual revision-bound approval | `fcops/backend/fc/models.py`, `fc/config_services.py`, `fc/views.py`, `fc/serializers.py` |
| Parameters | confirmed: partially untracked at start; preserved, not merged to WP0 main base | parameter file list below |
| Audit | confirmed: application guards and PostgreSQL UPDATE/DELETE trigger; database owners can bypass protection | `fcops/backend/core/models.py`, `core/migrations/0003_audit_append_only.py`, `core/audit.py` |
| Attachments | confirmed: local disk and public debug media route | `fcops/backend/issues/models.py::IssueAttachment`, `issues/serializers.py`, `config/settings.py`, `config/urls.py` |
| Notifications | confirmed: in-app rows only in current issue services; copied message/link, no current-access recheck | `fcops/backend/core/models.py::Notification`, `core/views.py`, `issues/services.py` |
| DB config | confirmed: URL selection, pooler detection, local fallback and guarded runner; migration URL takes precedence and must be overridden in isolation | `fcops/backend/config/db.py`, `config/test_runner.py`, `config/settings.py` |
| Commands | different: dbcheck, reindex_search, seed and locally-added serve | command list below |
| Tests | different: 155 backend tests now pass; 17 E2E steps pass with no page errors; diagnostics script/page and claimed 23 diagnostics tests absent; earlier attempts retained below | `fcops/backend/tests/`, `fcops/frontend/package.json`, `fcops/e2e/ui_walkthrough.py` |
| Python | confirmed: source enforces >=3.10; Python 3.12 available and isolated venv created | `fcops/backend/config/settings.py`, `fcops/README.md`; runtime logs |

## Every DRF view and queryset

All router routes use `/api/<prefix>/`; ModelViewSets offer standard list/detail/create/update/delete unless overridden in source. Actions are listed individually below. Global DRF filtering/pagination applies after the view queryset; it is not record-access enforcement.

| View | Route | Source | Queryset construction |
|---|---|---|---|
| `AuditedTokenObtainPairView` | `/api/auth/token/` | `fcops/backend/accounts/views.py:19` | `Inherited JWT login; User.objects.filter(username=username).first() for login audit.` |
| `DepartmentViewSet` | `/api/departments/` | `fcops/backend/accounts/views.py:30` | `Department.objects.all()` |
| `UserViewSet` | `/api/users/` | `fcops/backend/accounts/views.py:52` | `User.objects.select_related('department').all().order_by('username')` |
| ↳ `me` | GET `/api/users/me/` | same source, line 82 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `roles` | GET `/api/users/roles/` | same source, line 86 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| `AuditLogViewSet` | `/api/audit-log/` | `fcops/backend/core/views.py:21` | `AuditLogEntry.objects.select_related('actor', 'fc').all()` |
| `NotificationViewSet` | `/api/notifications/` | `fcops/backend/core/views.py:30` | `def get_queryset(self): return Notification.objects.filter(recipient=self.request.user)` |
| ↳ `unread_count` | GET `/api/notifications/unread_count/` | same source, line 38 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `mark_all_read` | POST `/api/notifications/mark_all_read/` | same source, line 42 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `mark_read` | POST `/api/notifications/{id}/mark_read/` | same source, line 47 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| `DashboardSummaryView` | `/api/dashboard/summary/` | `fcops/backend/core/views.py:54` | `Direct unscoped FlightController, Issue, StageRecord, ReworkRecord aggregate queries in _build; cache key dashboard:summary:{window_days}, shared across users.` |
| `HealthView` | `/api/health/` | `fcops/backend/core/views.py:163` | `No queryset; public static status/time.` |
| `FCModelTypeViewSet` | `/api/fc-models/` | `fcops/backend/fc/views.py:45` | `FCModelType.objects.all()` |
| ↳ `set_active` | POST `/api/fc-models/{id}/set-active/` | same source, line 79 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| `ParameterProfileViewSet` | `/api/parameter-profiles/` | `fcops/backend/fc/views.py:88` | `ParameterProfile.objects.all()` |
| `SoftwareVersionViewSet` | `/api/software-versions/` | `fcops/backend/fc/views.py:94` | `SoftwareVersion.objects.all()` |
| `ChecklistTemplateViewSet` | `/api/checklist-templates/` | `fcops/backend/fc/views.py:101` | `ChecklistTemplate.objects.prefetch_related('checklist_items').all()` |
| ↳ `reorder` | POST `/api/checklist-templates/{id}/reorder/` | same source, line 126 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `current` | GET `/api/checklist-templates/{id}/current/` | same source, line 135 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| `FlightControllerViewSet` | `/api/fcs/` | `fcops/backend/fc/views.py:143` | `FlightController.objects.select_related('fc_model', 'registered_by', 'approved_by').all(); def get_queryset(self): qs = super().get_queryset() if self.action == "list": qs = qs.annotate(open_issue_total=self.LIST_ANNOTATION) else: # Detail reads walk stages, issues and firmware; prefetch them once. qs = qs.prefetch_related( Prefetch("stage_records", queryset=StageRecord.objects.select_related( "operator", "department", "signed_off_by")), Prefetch("issues", queryset=Issue.objects.select_related( "fc", "resolved_by", "assigned_department", "discovering_department", "assigned_person")), Prefetch("firmware_records", queryset=FirmwareRecord.objects.select_related( "operator", "parameter_profile"))) search = self.request.query_params.get("search") if search: qs = qs.filter(Q(serial__icontains=search) &#124; Q(hardware_revision__icontains=search) &#124; Q(pcb_batch__icontains=search) &#124; Q(notes__icontains=search)) return qs` |
| ↳ `start_stage` | POST `/api/fcs/{id}/start_stage/` | same source, line 209 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `pass_stage` | POST `/api/fcs/{id}/pass_stage/` | same source, line 220 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `fail_stage` | POST `/api/fcs/{id}/fail_stage/` | same source, line 224 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `approve` | POST `/api/fcs/{id}/approve/` | same source, line 242 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `override_stage` | POST `/api/fcs/{id}/override_stage/` | same source, line 253 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `full` | GET `/api/fcs/{id}/full/` | same source, line 264 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `timeline` | GET `/api/fcs/{id}/timeline/` | same source, line 286 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `stage_records` | GET `/api/fcs/{id}/stage_records/` | same source, line 291 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `issues` | GET `/api/fcs/{id}/issues/` | same source, line 298 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `audit_log` | GET `/api/fcs/{id}/audit_log/` | same source, line 306 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| `StageRecordViewSet` | `/api/stage-records/` | `fcops/backend/fc/views.py:313` | `StageRecord.objects.select_related('fc', 'operator', 'department').all()` |
| `ReworkRecordViewSet` | `/api/rework-records/` | `fcops/backend/fc/views.py:320` | `ReworkRecord.objects.select_related('fc', 'stage_record', 'performed_by').all()` |
| ↳ `complete` | POST `/api/rework-records/{id}/complete/` | same source, line 343 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| `FirmwareRecordViewSet` | `/api/firmware-records/` | `fcops/backend/fc/views.py:354` | `FirmwareRecord.objects.select_related('fc', 'operator', 'parameter_profile').all()` |
| `TestResultViewSet` | `/api/test-results/` | `fcops/backend/fc/views.py:379` | `TestResult.objects.select_related('fc', 'tester', 'stage_record', 'gcs_version', 'configurator_version').all()` |
| `LifecycleMetaView` | `/api/lifecycle/` | `fcops/backend/fc/views.py:410` | `No queryset; enum metadata only.` |
| `SoftwareUpdateViewSet` | `/api/software-updates/` | `fcops/backend/fc/views.py:426` | `SoftwareUpdate.objects.select_related('approved_by', 'pushed_by', 'software_version').all(); def get_queryset(self): qs = super().get_queryset() search = self.request.query_params.get("search") if search: qs = qs.filter(Q(version__icontains=search) &#124; Q(git_sha__icontains=search) &#124; Q(release_notes__icontains=search)) return qs` |
| ↳ `approvers` | GET `/api/software-updates/approvers/` | same source, line 476 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| `FirmwareBuildViewSet` | `/api/firmware-builds/` | `fcops/backend/fc/views.py:486` | `FirmwareBuild.objects.select_related('parameter_profile', 'created_by').prefetch_related('fc_models').all(); def get_queryset(self): qs = super().get_queryset() search = self.request.query_params.get("search") if search: qs = qs.filter(Q(name__icontains=search) &#124; Q(version__icontains=search) &#124; Q(git_sha__icontains=search) &#124; Q(description__icontains=search)) return qs` |
| ↳ `set_active` | POST `/api/firmware-builds/{id}/set-active/` | same source, line 531 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `flashes` | GET `/api/firmware-builds/{id}/flashes/` | same source, line 540 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `flash` | POST `/api/firmware-builds/flash/` | same source, line 547 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `meta` | GET `/api/firmware-builds/meta/` | same source, line 566 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| `ChecklistItemViewSet` | `/api/checklist-items/` | `fcops/backend/fc/views.py:576` | `ChecklistItem.objects.select_related('template').all()` |
| ↳ `set_active` | POST `/api/checklist-items/{id}/set-active/` | same source, line 613 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| `ParameterFileViewSet` | `/api/parameter-files/` | `fcops/backend/fc/views.py:622` | `ParameterFile.objects.select_related('fc', 'uploaded_by', 'parameter_profile').all(); def get_queryset(self): # The parsed parameters and raw text are large and are never needed for # a listing â€” fetching them would make the page crawl. qs = super().get_queryset() if self.action in ("list", "retrieve"): qs = qs.defer("parameters", "raw_text") return qs` |
| ↳ `parameters` | GET `/api/parameter-files/{id}/parameters/` | same source, line 671 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `compare` | POST `/api/parameter-files/compare/` | same source, line 678 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| `IssueViewSet` | `/api/issues/` | `fcops/backend/issues/views.py:27` | `Issue.objects.select_related('fc', 'discovered_by', 'discovering_department', 'assigned_department', 'assigned_person', 'root_cause_department', 'known_issue').all(); def get_queryset(self): qs = super().get_queryset() params = self.request.query_params text = params.get("q") or params.get("search") if text or any(params.get(k) for k in ("hardware_revision", "firmware_version", "gcs_version", "configurator_version", "parameter_profile", "stage", "created_after", "created_before")): qs = search_issues(qs, text=text, filters={ k: params.get(k) for k in params.keys()}) return qs` |
| ↳ `notes` | POST `/api/issues/{id}/notes/` | same source, line 108 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `reassign` | POST `/api/issues/{id}/reassign/` | same source, line 118 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `change_status` | POST `/api/issues/{id}/status/` | same source, line 132 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `reopen` | POST `/api/issues/{id}/reopen/` | same source, line 146 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `waiting` | POST `/api/issues/{id}/waiting/` | same source, line 153 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `promote` | POST `/api/issues/{id}/promote/` | same source, line 161 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `link_known_issue` | POST `/api/issues/{id}/link-known-issue/` | same source, line 176 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `similar` | GET `/api/issues/{id}/similar/` | same source, line 184 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `similar_search` | GET, POST `/api/issues/similar-search/` | same source, line 198 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `search` | GET `/api/issues/search/` | same source, line 216 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| ↳ `meta` | GET `/api/issues/meta/` | same source, line 225 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| `KnownIssueViewSet` | `/api/known-issues/` | `fcops/backend/issues/views.py:243` | `KnownIssue.objects.select_related('promoted_by', 'owning_department').all(); def get_queryset(self): qs = super().get_queryset() params = self.request.query_params text = params.get("q") or params.get("search") if text: qs = search_known_issues(qs, text=text, filters={}) return qs` |
| ↳ `occurrences` | GET `/api/known-issues/{id}/occurrences/` | same source, line 271 | Custom action; inspect its direct model queries as well as get_object/get_queryset. |
| `IssueAttachmentViewSet` | `/api/issue-attachments/` | `fcops/backend/issues/views.py:276` | `IssueAttachment.objects.select_related('issue', 'uploaded_by').all()` |
| `TokenRefreshView` (third party) | POST `/api/auth/token/refresh/` | `fcops/backend/config/urls.py` | Token validation; library serializer, no application queryset. |
| `TokenVerifyView` (third party) | POST `/api/auth/token/verify/` | `fcops/backend/config/urls.py` | Token validation; library serializer. |

Additional URL surfaces: `/admin/` (Django admin), `/api-auth/` (DRF session login/logout), router API root and format suffixes; `/media/` is enabled by DEBUG. These need WP1 route-coverage review too.

## FC/stage coupling for WP4

`Stage` is a TextChoices enum in `fcops/backend/fc/lifecycle.py`; there is no Stage model or FK to Stage. Include StageRecord relationships and stage-choice fields below so the plan cannot mistake them for FKs. Nullability is database nullability (blank is separate).

| Model.field | Kind / target | Nullable | Source |
|---|---|---|---|
| `AuditLogEntry.fc` | models.ForeignKey: `fc.FlightController` | true | `fcops/backend/core/models.py:47` |
| `FlightController.current_stage` | models.CharField: `Stage.choices` | false | `fcops/backend/fc/models.py:49` |
| `StageRecord.fc` | models.ForeignKey: `FlightController` | false | `fcops/backend/fc/models.py:147` |
| `StageRecord.stage` | models.CharField: `Stage.choices` | false | `fcops/backend/fc/models.py:149` |
| `ReworkRecord.stage_record` | models.ForeignKey: `StageRecord` | false | `fcops/backend/fc/models.py:197` |
| `ReworkRecord.fc` | models.ForeignKey: `FlightController` | false | `fcops/backend/fc/models.py:199` |
| `ReworkRecord.return_to_stage` | models.CharField: `Stage.choices` | false | `fcops/backend/fc/models.py:212` |
| `FirmwareRecord.fc` | models.ForeignKey: `FlightController` | false | `fcops/backend/fc/models.py:259` |
| `FirmwareRecord.stage_record` | models.ForeignKey: `StageRecord` | true | `fcops/backend/fc/models.py:261` |
| `ChecklistTemplate.stage` | models.CharField: `Stage.choices` | false | `fcops/backend/fc/models.py:451` |
| `TestResult.fc` | models.ForeignKey: `FlightController` | false | `fcops/backend/fc/models.py:528` |
| `TestResult.stage_record` | models.ForeignKey: `StageRecord` | false | `fcops/backend/fc/models.py:530` |
| `TestResult.test_type` | models.CharField: `Stage.choices` | false | `fcops/backend/fc/models.py:532` |
| `ParameterFile.fc` | models.ForeignKey: `FlightController` | true | `fcops/backend/fc/models.py:581` |
| `FCEvent.fc` | models.ForeignKey: `FlightController` | false | `fcops/backend/fc/models.py:608` |
| `Issue.fc` | models.ForeignKey: `fc.FlightController` | false | `fcops/backend/issues/models.py:112` |
| `Issue.discovered_stage` | models.CharField: `Stage.choices` | false | `fcops/backend/issues/models.py:116` |
| `Issue.discovered_stage_record` | models.ForeignKey: `fc.StageRecord` | true | `fcops/backend/issues/models.py:118` |

## Release records for WP11

`fcops/backend/fc/models.py`: `SoftwareVersion` is the GCS/Configurator version catalogue; `SoftwareUpdate` stores kind, version, git_sha, release_notes, approved_by (required user FK, PROTECT), approved_at, pushed_by (nullable), software_version (nullable). `fc/config_services.py::push_software_update` validates the submitted approver role then stamps approval time during creation; `fc/views.py::SoftwareUpdateViewSet.create` accepts the ID. This is not an authenticated approval by that person and there are no revision/dual-approval rows. `FlightController.approved_by/approved_at` is separate FC manager approval; do not migrate it as release approval.

## File serving

`IssueAttachment.file` uses default FileSystemStorage under MEDIA_ROOT, `issue-attachments/%Y/%m/`; MEDIA_ROOT defaults to backend/media and is env-configurable. `IssueAttachmentSerializer` exposes file/url. `IssueAttachmentViewSet` accepts multipart uploads. `config/urls.py` appends DEBUG media serving without parent-issue permission checks. No object storage or authorised download view found. ParameterFile raw_text/parameters are database fields, not original-byte private file storage.

## Browser token handling

`fcops/frontend/src/lib/api.js`: key `fcops.tokens` in localStorage stores the JSON access/refresh pair; Authorization: Bearer access token on API requests; on 401 POST refresh token to `/api/auth/token/refresh/`, save replacement access token, retry once. Login obtains pair via `/api/auth/token/`; logout removes local entry. `auth.jsx` restores user via `/api/users/me/`. Session auth is also enabled server-side, but frontend flow uses JWT.

## Project management commands

| Command | Source | Behaviour |
|---|---|---|
| `seed [--demo] [--password]` | `fcops/backend/accounts/management/commands/seed.py` | Writes reference/demo data and users; baseline isolation required. |
| `dbcheck [--deep]` | `fcops/backend/core/management/commands/dbcheck.py` | Connectivity/schema checks; deep mode tests raw writes inside rollback transactions. |
| `serve` | `fcops/backend/core/management/commands/serve.py` | Waitress server in preserved local work, absent from main. |
| `reindex_search` | `fcops/backend/issues/management/commands/reindex_search.py` | Rewrites issue/knowledge search vectors. |

Django built-in commands (migrate/test/runserver etc.) remain available; the table enumerates repository-defined commands.

## Parameter/local-work integration list for WP8

Untracked at initial inspection:

- `fcops/backend/fc/migrations/0005_parameterfile.py`
- `fcops/backend/fc/parameters.py`
- `fcops/backend/tests/test_param_and_routing.py`
- `fcops/e2e/param_and_routing.py`
- `fcops/frontend/src/pages/ParamCompare.jsx`

Modified supporting files to diff against main (some also contain unrelated routing/dashboard changes):

- `fcops/IMPLEMENTATION_NOTES.md`
- `fcops/README.md`
- `fcops/backend/config/settings.py`
- `fcops/backend/config/urls.py`
- `fcops/backend/core/views.py`
- `fcops/backend/fc/lifecycle.py`
- `fcops/backend/fc/models.py`
- `fcops/backend/fc/serializers.py`
- `fcops/backend/fc/services.py`
- `fcops/backend/fc/views.py`
- `fcops/backend/requirements.txt`
- `fcops/e2e/config_features.py`
- `fcops/e2e/ui_walkthrough.py`
- `fcops/frontend/src/App.jsx`
- `fcops/frontend/src/pages/FcDetail.jsx`

`fcops.tar.gz` is preserved unchanged as an opaque historical artifact, not an integration source. Review `900680d` vs `main` per file; do not merge the whole preservation branch in WP8.

## Environment and current verification

See [validation/RESULTS.md](validation/RESULTS.md) for commands, exit codes, source revision, isolation and full stdout/stderr. Failures are recorded without application fixes.

Direct model queries inside custom actions and API methods are indexed in [QUERY_SURFACES.md](QUERY_SURFACES.md). Notable bypasses include ParameterFile.parameters direct get, compare-side direct filter, global Issue similarity queries, FC timeline related queries and global SoftwareUpdate approvers.

Plan provenance: `docs/IMPLEMENTATION_PLAN.md` is the full supplied user answer verbatim plus a final newline (answer SHA-256 `84bf51f9ffd5dc1cfbe5f62d05bb7f8d5ce8381dd53faab6180123575260fef2`). `docs/PRD.md` and `fcops/PRD.md` match the original PRD bytes. Static cross-check found all 24 repository DRF view classes in this inventory; imported refresh/verify views are also listed.

Final validation: 155 backend tests pass; migrations, demo seed, deep DB checks and frontend build pass; primary UI walkthrough passes all 17 steps with no page errors. Requested diagnostics command fails because the script is absent. Prior harness timeout, environment-sensitive failures and browser path failures are retained in the execution record.
