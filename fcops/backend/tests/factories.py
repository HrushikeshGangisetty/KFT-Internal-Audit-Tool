from accounts.models import Department, Role, User
from fc.models import FCModelType


def make_department(code, kind=Department.KIND_HARDWARE, name=None):
    return Department.objects.get_or_create(
        code=code, defaults={"name": name or code.title(), "kind": kind})[0]


def make_user(username, role=Role.TECHNICIAN, department=None, password="TestPass123!"):
    user = User.objects.create(username=username, full_name=username,
                               role=role, department=department)
    user.set_password(password)
    if role == Role.ADMIN:
        user.is_staff = user.is_superuser = True
    user.save()
    return user


def make_fc_model(code="test-fc"):
    return FCModelType.objects.get_or_create(code=code,
                                             defaults={"name": code})[0]
