from django import forms
from django.utils.translation import gettext_lazy as _


class IssueForm(forms.Form):
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
    photo = forms.ImageField(label=_("Photo"), required=False)
    reporter_name = forms.CharField(
        label=_("Your name (optional, shown publicly)"), max_length=100, required=False
    )
