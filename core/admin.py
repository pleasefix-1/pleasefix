from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from core.models import Issue, IssuePhoto


class IssuePhotoInline(admin.TabularInline[IssuePhoto, Issue]):
    model = IssuePhoto
    extra = 0


@admin.register(Issue)
class IssueAdmin(GISModelAdmin[Issue]):
    list_display = ["title", "status", "reporter_name", "created_at"]
    list_filter = ["status"]
    search_fields = ["title", "description"]
    inlines = [IssuePhotoInline]
