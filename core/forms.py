from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.utils.translation import gettext_lazy as _

from core.models import Media, media_kind_for_name

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB — photos
MAX_VIDEO_BYTES = 50 * 1024 * 1024  # 50 MB — short clips, not films
MAX_MEDIA_FILES = 10


def validate_photo_size(photo: UploadedFile | None) -> UploadedFile | None:
    """Cap uploaded photo size — Pillow validates it's an image, but an
    ImageField has no size bound, so a huge upload could OOM the worker."""
    if photo is not None and photo.size is not None and photo.size > MAX_UPLOAD_BYTES:
        raise ValidationError(_("Photo is too large (max 10 MB)."))
    return photo


class MultipleFileInput(forms.ClearableFileInput):
    """The stock ClearableFileInput rejects `multiple`; opt in explicitly."""

    allow_multiple_selected = True


class MediaField(forms.FileField):
    """Accepts several image/video files at once. Each is checked for a
    recognised media extension and a per-kind size cap; the cleaned value
    is the list of UploadedFiles (empty when nothing was attached)."""

    widget = MultipleFileInput

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("required", False)
        super().__init__(*args, **kwargs)

    def clean(self, data: Any, initial: Any = None) -> list[UploadedFile]:
        uploads = data if isinstance(data, list | tuple) else [data]
        uploads = [f for f in uploads if f not in (None, "")]
        if self.required and not uploads:
            raise ValidationError(self.error_messages["required"], code="required")
        if len(uploads) > MAX_MEDIA_FILES:
            raise ValidationError(_("Too many files (max %(n)d).") % {"n": MAX_MEDIA_FILES})
        cleaned: list[UploadedFile] = []
        for upload in uploads:
            single = super().clean(upload, initial)
            kind = media_kind_for_name(getattr(single, "name", "") or "")
            if kind is None:
                raise ValidationError(_("Only image or video files can be attached."))
            cap = MAX_VIDEO_BYTES if kind == Media.Kind.VIDEO else MAX_UPLOAD_BYTES
            if single.size is not None and single.size > cap:
                raise ValidationError(_("%(name)s is too large.") % {"name": single.name})
            cleaned.append(single)
        return cleaned


class MediaUploadForm(forms.Form):
    """One file for the async upload endpoint — reuses MediaField's
    validation (extension + per-kind size cap) rather than forking it."""

    file = MediaField(required=True, widget=forms.ClearableFileInput)

    def clean_file(self) -> UploadedFile:
        files: list[UploadedFile] = self.cleaned_data.get("file") or []
        return files[0]


class HoneypotMixin(forms.Form):
    """Invisible field (hidden by CSS on the page); humans leave it
    empty, bots fill it. Filled → the view silently pretends success."""

    website = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "off", "tabindex": "-1"}),
    )

    @property
    def is_spam(self) -> bool:
        return bool(self.cleaned_data.get("website"))

    def clean_photo(self) -> Any:
        return validate_photo_size(self.cleaned_data.get("photo"))


class IssueForm(HoneypotMixin, forms.Form):
    title = forms.CharField(
        label=_("What's the problem?"),
        max_length=200,
        widget=forms.TextInput(
            attrs={"placeholder": _("e.g. Broken streetlight outside the surau")}
        ),
    )
    description = forms.CharField(
        label=_("Details"),
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": _("What's wrong, since when, and how it affects people"),
            }
        ),
    )
    latitude = forms.FloatField(
        label=_("Latitude"),
        min_value=-90,
        max_value=90,
        widget=forms.NumberInput(attrs={"step": "any"}),
    )
    longitude = forms.FloatField(
        label=_("Longitude"),
        min_value=-180,
        max_value=180,
        widget=forms.NumberInput(attrs={"step": "any"}),
    )
    attachments = MediaField(
        label=_("Photos or videos"),
        widget=MultipleFileInput(attrs={"multiple": True, "accept": "image/*,video/*"}),
    )
    reporter_name = forms.CharField(
        label=_("Your name (optional, shown publicly)"), max_length=100, required=False
    )
    # Carried through the URL-import flow (hidden; see core.importers).
    source_url = forms.URLField(required=False, widget=forms.HiddenInput())
    photo_url = forms.URLField(required=False, widget=forms.HiddenInput())


class UpdateForm(HoneypotMixin, forms.Form):
    text = forms.CharField(
        label=_("Add an update"),
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": _("Still broken? Fixed? Add what you know — photos help."),
            }
        ),
    )
    photo = forms.ImageField(label=_("Photo"), required=False)
    author_name = forms.CharField(
        label=_("Your name (optional, shown publicly)"), max_length=100, required=False
    )
    reporter_secret = forms.CharField(
        label=_("Reporter secret (optional)"),
        max_length=40,
        required=False,
        help_text=_(
            "If you're the original reporter, paste the secret you were "
            "given — your update gets a verified badge."
        ),
    )


class ClaimForm(forms.Form):
    secret = forms.CharField(
        label=_("Reporter secret"),
        max_length=40,
        widget=forms.TextInput(attrs={"placeholder": "e.g. x7km2p9qw4ne"}),
    )


class ImportForm(forms.Form):
    url = forms.URLField(
        label=_("Link to import"),
        widget=forms.URLInput(
            attrs={"placeholder": "https://www.reddit.com/r/malaysia/comments/…"}
        ),
    )
