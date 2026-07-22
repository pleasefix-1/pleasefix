from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from core.models import Flag, Issue, IssuePhoto, IssueUpdate


class IssuePhotoInline(admin.TabularInline[IssuePhoto, Issue]):
    model = IssuePhoto
    extra = 0


class IssueUpdateInline(admin.TabularInline[IssueUpdate, Issue]):
    model = IssueUpdate
    extra = 0
    fields = ["text", "author_name", "by_reporter", "is_hidden", "created_at"]
    readonly_fields = ["created_at"]


@admin.register(Issue)
class IssueAdmin(GISModelAdmin[Issue]):
    list_display = ["public_id", "title", "status", "is_hidden", "reporter_name", "created_at"]
    list_filter = ["status", "is_hidden"]
    search_fields = ["title", "description", "public_id"]
    inlines = [IssuePhotoInline, IssueUpdateInline]
    actions = ["unhide"]

    @admin.action(description=_("Unhide selected issues (dismiss flags)"))
    def unhide(self, request: HttpRequest, queryset: QuerySet[Issue]) -> None:
        queryset.update(is_hidden=False)


@admin.register(IssueUpdate)
class IssueUpdateAdmin(admin.ModelAdmin[IssueUpdate]):
    list_display = ["issue", "author_name", "by_reporter", "is_hidden", "created_at"]
    list_filter = ["is_hidden", "by_reporter"]
    list_select_related = ["issue"]


@admin.register(Flag)
class FlagAdmin(admin.ModelAdmin[Flag]):
    list_display = ["issue", "update", "created_at"]
    list_select_related = ["issue", "update"]
    readonly_fields = ["issue", "update", "ip_hash", "created_at"]
