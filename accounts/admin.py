from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import User

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("id", "username", "email", "is_active", "is_staff")
    search_fields = ("username", "email")
    ordering = ("id",)