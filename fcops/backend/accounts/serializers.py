from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Department, Role, User


class DepartmentSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(source="members.count", read_only=True)

    class Meta:
        model = Department
        fields = ("id", "name", "code", "kind", "description", "is_active",
                  "member_count")


class UserSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    role_display = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "email", "full_name", "role", "role_display",
                  "department", "department_name", "is_active", "is_active_employee")


class UserWriteSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False,
                                     validators=[validate_password])

    class Meta:
        model = User
        fields = ("id", "username", "email", "full_name", "role", "department",
                  "is_active", "is_active_employee", "password")

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        user.set_password(password or User.objects.make_random_password())
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class MeSerializer(UserSerializer):
    permissions = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ("permissions",)

    def get_permissions(self, user):
        return {
            "is_admin": user.is_admin_role,
            "is_manager": user.is_manager_role,
            "is_lead": user.is_lead_role,
            "is_test_engineer": user.is_test_engineer,
            "can_promote_known_issue": user.is_lead_role,
            "can_approve": user.is_manager_role,
            "can_verify": user.is_test_engineer or user.is_lead_role,
            # Capability flags for the configuration features. The frontend uses
            # these to decide what to show; the backend enforces them again on
            # every write.
            "can_push_software_update": user.can_push_software_update,
            "can_manage_firmware": user.can_manage_firmware,
            "can_approve_software_update": user.can_approve_software_update,
            "can_configure_tests": user.is_manager_role,
            "can_manage_fc_models": user.is_manager_role,
        }
