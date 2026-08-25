from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Department, User


@admin.register(User)
class AppUserAdmin(UserAdmin):
    list_display = ("username", "full_name", "role", "department", "is_active")
    list_filter = ("role", "department", "is_active")
    fieldsets = UserAdmin.fieldsets + (
        ("Production", {"fields": ("full_name", "role", "department",
                                   "is_active_employee")}),)


admin.site.register(Department)
