# Direct query surfaces for WP1

Supplement to INVENTORY.md. Static source expressions from view methods, including actions that bypass get_queryset. These are current behaviour, not approved access policy. Nested serializers and service/search helpers also need scoping review.

### AuditedTokenObtainPairView.post

`fcops/backend/accounts/views.py:20`

```python
User.objects.filter(username=username).first()
```

### NotificationViewSet.get_queryset

`fcops/backend/core/views.py:34`

```python
Notification.objects.filter(recipient=self.request.user)
```

### DashboardSummaryView._build

`fcops/backend/core/views.py:79`

```python
FlightController.objects.exclude(status__in=[FCStatus.APPROVED, FCStatus.REJECTED]).values('current_stage').annotate(n=Count('id'))
Issue.objects.exclude(status=IssueStatus.CLOSED)
list(Issue.objects.filter(created_at__gte=since).values('discovered_stage').annotate(n=Count('id')).order_by('-n'))
FlightController.objects.filter(status=FCStatus.BLOCKED).prefetch_related(Prefetch('issues', queryset=Issue.objects.exclude(status=IssueStatus.CLOSED)))
Issue.objects.filter(resolved_at__isnull=False, created_at__gte=since).aggregate(avg=Avg(F('resolved_at') - F('created_at')))
ReworkRecord.objects.filter(created_at__gte=since).values('fc__serial').annotate(n=Count('id')).order_by('-n')
FlightController.objects.count()
FlightController.objects.values('status').annotate(n=Count('id'))
StageRecord.objects.filter(completed_at__isnull=False, started_at__isnull=False, completed_at__gte=since).values('stage').annotate(avg=Avg(F('completed_at') - F('started_at'))).order_by('stage')
```

### FlightControllerViewSet.get_queryset

`fcops/backend/fc/views.py:161`

```python
qs.prefetch_related(Prefetch('stage_records', queryset=StageRecord.objects.select_related('operator', 'department', 'signed_off_by')), Prefetch('issues', queryset=Issue.objects.select_related('fc', 'resolved_by', 'assigned_department', 'discovering_department', 'assigned_person')), Prefetch('firmware_records', queryset=FirmwareRecord.objects.select_related('operator', 'parameter_profile')))
```

### FlightControllerViewSet._department

`fcops/backend/fc/views.py:204`

```python
Department.objects.filter(pk=dept_id).first()
```

### SoftwareUpdateViewSet.create

`fcops/backend/fc/views.py:451`

```python
config_services.push_software_update(kind=data['kind'], version=data['version'], git_sha=data['git_sha'], release_notes=data['release_notes'], approved_by=User.objects.filter(pk=data['approved_by']).first(), actor=request.user)
```

### SoftwareUpdateViewSet.approvers

`fcops/backend/fc/views.py:476`

```python
User.objects.filter(is_active=True, role__in=[Role.DEPARTMENT_LEAD, Role.MANAGER, Role.ADMIN]).select_related('department').order_by('full_name', 'username')
```

### FirmwareBuildViewSet.flash

`fcops/backend/fc/views.py:547`

```python
get_object_or_404(FlightController, pk=data['fc'])
get_object_or_404(FirmwareBuild, pk=data['build'])
StageRecord.objects.filter(pk=data.get('stage_record'), fc=fc).first()
```

### ChecklistItemViewSet.create

`fcops/backend/fc/views.py:584`

```python
get_object_or_404(ChecklistTemplate, pk=request.data.get('template'))
```

### ParameterFileViewSet.create

`fcops/backend/fc/views.py:640`

```python
ParameterFile.objects.create(name=upload.name[:160], label=request.data.get('label', '')[:160], fc=FlightController.objects.filter(pk=request.data.get('fc')).first() if request.data.get('fc') else None, parameter_profile=ParameterProfile.objects.filter(pk=request.data.get('parameter_profile')).first() if request.data.get('parameter_profile') else None, parameters=parameters, raw_text=text, parameter_count=len(parameters), uploaded_by=request.user)
```

### ParameterFileViewSet.parameters

`fcops/backend/fc/views.py:671`

```python
ParameterFile.objects.get(pk=pk)
```

### IssueViewSet.get_queryset

`fcops/backend/issues/views.py:44`

```python
search_issues(qs, text=text, filters={k: params.get(k) for k in params.keys()})
```

### IssueViewSet.create

`fcops/backend/issues/views.py:56`

```python
get_object_or_404(FlightController, pk=data['fc'])
services.create_issue(fc=fc, title=data['title'], symptoms=data['symptoms'], description=data.get('description', ''), discovered_stage=data.get('discovered_stage'), discovered_stage_record=stage_record, category=data.get('category'), severity=data.get('severity', Severity.MAJOR), assigned_department=Department.objects.filter(pk=data.get('assigned_department')).first(), assigned_person=User.objects.filter(pk=data.get('assigned_person')).first(), symptom_tags=data.get('symptom_tags', []), version_overrides={'firmware_version': data.get('firmware_version'), 'hardware_revision': data.get('hardware_revision'), 'gcs_version': data.get('gcs_version'), 'configurator_version': data.get('configurator_version'), 'parameter_profile': data.get('parameter_profile')}, actor=request.user)
StageRecord.objects.filter(pk=data['discovered_stage_record'], fc=fc).first()
```

### IssueViewSet.reassign

`fcops/backend/issues/views.py:118`

```python
services.reassign(issue, actor=request.user, to_department=Department.objects.filter(pk=s.validated_data.get('to_department')).first(), to_person=User.objects.filter(pk=s.validated_data.get('to_person')).first(), reason=s.validated_data['reason'])
```

### IssueViewSet.change_status

`fcops/backend/issues/views.py:132`

```python
services.change_status(issue, d['status'], actor=request.user, note=d.get('note', ''), root_cause=d.get('root_cause'), resolution=d.get('resolution'), root_cause_department=Department.objects.filter(pk=d.get('root_cause_department')).first() if d.get('root_cause_department') else None)
```

### IssueViewSet.link_known_issue

`fcops/backend/issues/views.py:176`

```python
get_object_or_404(KnownIssue, pk=request.data.get('known_issue'))
```

### IssueViewSet.similar

`fcops/backend/issues/views.py:184`

```python
find_similar(text=f'{issue.title} {issue.symptoms}', stage=issue.discovered_stage, category=issue.category, hardware_revision=issue.hardware_revision, firmware_version=issue.firmware_version, gcs_version=issue.gcs_version, configurator_version=issue.configurator_version, parameter_profile=issue.parameter_profile, exclude_issue_id=issue.pk)
```

### IssueViewSet.similar_search

`fcops/backend/issues/views.py:198`

```python
find_similar(text=d.get('text', ''), stage=d.get('stage') or None, category=d.get('category') or None, hardware_revision=d.get('hardware_revision') or None, firmware_version=d.get('firmware_version') or None, gcs_version=d.get('gcs_version') or None, configurator_version=d.get('configurator_version') or None, parameter_profile=d.get('parameter_profile') or None, exclude_issue_id=d.get('exclude_issue_id'), limit=d.get('limit', 10))
```

### IssueViewSet.search

`fcops/backend/issues/views.py:216`

```python
search_issues(self.queryset, text=params.get('q'), filters={k: params.get(k) for k in params.keys()})
```

### KnownIssueViewSet.get_queryset

`fcops/backend/issues/views.py:254`

```python
search_known_issues(qs, text=text, filters={})
```
