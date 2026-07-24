from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from core.models import (
    Area,
    Body,
    Category,
    CategoryGroup,
    Filing,
    Flag,
    Issue,
    IssueLink,
    IssueMedia,
    IssueReference,
    IssueUpdate,
    Media,
    Subscription,
    Tag,
)


@admin.register(Media)
class MediaAdmin(admin.ModelAdmin[Media]):
    list_display = ["__str__", "kind", "origin", "uploaded_by", "created_at"]
    list_filter = ["kind", "origin"]
    search_fields = ["file", "owner_token"]
    readonly_fields = ["created_at", "owner_token"]
    # Admins can claim/assign dangling (imported) media by setting uploaded_by.
    autocomplete_fields = ["uploaded_by"]


class IssueMediaInline(admin.TabularInline[IssueMedia, Issue]):
    model = IssueMedia
    extra = 0
    autocomplete_fields = ["media"]


class IssueReferenceInline(admin.TabularInline[IssueReference, Issue]):
    model = IssueReference
    extra = 0


class IssueUpdateInline(admin.TabularInline[IssueUpdate, Issue]):
    model = IssueUpdate
    extra = 0
    fields = ["text", "author_name", "by_reporter", "new_status", "is_hidden", "created_at"]
    readonly_fields = ["created_at"]


class FilingInline(admin.TabularInline[Filing, Issue]):
    model = Filing
    extra = 0
    fields = [
        "body",
        "target_name",
        "channel",
        "status",
        "external_reference",
        "external_status",
        "note",
    ]


@admin.register(Issue)
class IssueAdmin(GISModelAdmin[Issue]):
    list_display = [
        "public_id",
        "title",
        "status",
        "category",
        "is_hidden",
        "non_public",
        "reporter_name",
        "created_at",
    ]
    list_filter = ["status", "is_hidden", "non_public", "source_channel", "anonymous"]
    list_select_related = ["category", "category__body"]
    search_fields = ["title", "description", "public_id"]
    autocomplete_fields = ["category", "duplicate_of", "tags"]
    filter_horizontal = ["areas"]
    readonly_fields = ["public_id", "confirmed_at", "source_channel", "created_at", "updated_at"]
    inlines = [IssueMediaInline, IssueReferenceInline, IssueUpdateInline, FilingInline]
    actions = ["unhide"]

    @admin.action(description=_("Unhide selected issues (dismiss flags)"))
    def unhide(self, request: HttpRequest, queryset: QuerySet[Issue]) -> None:
        queryset.update(is_hidden=False)


@admin.register(IssueUpdate)
class IssueUpdateAdmin(admin.ModelAdmin[IssueUpdate]):
    list_display = ["issue", "author_name", "by_reporter", "new_status", "is_hidden", "created_at"]
    list_filter = ["is_hidden", "by_reporter"]
    list_select_related = ["issue"]


@admin.register(Flag)
class FlagAdmin(admin.ModelAdmin[Flag]):
    list_display = ["issue", "update", "created_at"]
    list_select_related = ["issue", "update"]
    readonly_fields = ["issue", "update", "ip_hash", "created_at"]


@admin.register(Area)
class AreaAdmin(GISModelAdmin[Area]):
    list_display = ["name", "kind", "generation", "is_active"]
    list_filter = ["kind", "is_active"]
    search_fields = ["name", "external_code"]


class CategoryInline(admin.TabularInline[Category, Body]):
    model = Category
    extra = 0
    fields = ["name", "group", "state", "dispatch_email", "photo_required", "non_public"]


@admin.register(Body)
class BodyAdmin(admin.ModelAdmin[Body]):
    list_display = ["name", "dispatch_email", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ["name"]}
    filter_horizontal = ["areas"]
    inlines = [CategoryInline]


@admin.register(CategoryGroup)
class CategoryGroupAdmin(admin.ModelAdmin[CategoryGroup]):
    list_display = ["name", "order"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin[Category]):
    list_display = ["name", "body", "group", "state", "non_public", "photo_required"]
    list_filter = ["state", "body", "group", "non_public"]
    list_select_related = ["body", "group"]
    search_fields = ["name", "body__name", "sispaa_category"]


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin[Tag]):
    search_fields = ["name"]


@admin.register(Filing)
class FilingAdmin(admin.ModelAdmin[Filing]):
    list_display = ["issue", "body", "target_name", "channel", "status", "external_reference"]
    list_filter = ["channel", "status", "body"]
    list_select_related = ["issue", "body"]
    search_fields = ["issue__public_id", "external_reference", "target_name"]


@admin.register(IssueLink)
class IssueLinkAdmin(admin.ModelAdmin[IssueLink]):
    list_display = ["blocker", "blocked", "created_at"]
    list_select_related = ["blocker", "blocked"]
    autocomplete_fields = ["blocker", "blocked"]


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin[Subscription]):
    list_display = ["kind", "issue", "user", "email", "phone", "confirmed", "created_at"]
    list_filter = ["kind", "confirmed"]
    list_select_related = ["issue", "user"]
