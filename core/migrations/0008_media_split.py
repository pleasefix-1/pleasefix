"""Split IssueMedia into a reusable Media file + an IssueMedia join.

Phase 2 (docs/media-library-phase2.md): one Media can back several
issues. Existing IssueMedia rows are migrated file/kind → a new Media
each, then linked. Forward preserves data; the RunPython step reverses.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import core.models


def split_media(apps, schema_editor):
    IssueMedia = apps.get_model("core", "IssueMedia")
    Media = apps.get_model("core", "Media")
    for im in IssueMedia.objects.all():
        media = Media.objects.create(file=im.file.name, kind=im.kind, origin="upload")
        im.media = media
        im.save(update_fields=["media"])


def unsplit_media(apps, schema_editor):
    IssueMedia = apps.get_model("core", "IssueMedia")
    for im in IssueMedia.objects.all():
        im.file = im.media.file.name
        im.kind = im.media.kind
        im.save(update_fields=["file", "kind"])


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0007_issuemedia_issuereference_delete_issuephoto"),
    ]

    operations = [
        migrations.CreateModel(
            name="Media",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "file",
                    models.FileField(
                        upload_to="issues/%Y/%m/",
                        validators=[core.models.validate_media_file],
                        verbose_name="file",
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[("image", "Image"), ("video", "Video")],
                        default="image",
                        max_length=5,
                        verbose_name="kind",
                    ),
                ),
                (
                    "origin",
                    models.CharField(
                        choices=[("upload", "Uploaded"), ("import", "Imported")],
                        default="upload",
                        max_length=6,
                        verbose_name="origin",
                    ),
                ),
                (
                    "session_key",
                    models.CharField(
                        blank=True, editable=False, max_length=40, verbose_name="session key"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="uploaded_media",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddField(
            model_name="issuemedia",
            name="order",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="issuemedia",
            name="media",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="attachments",
                to="core.media",
            ),
        ),
        migrations.RunPython(split_media, unsplit_media),
        migrations.AlterField(
            model_name="issuemedia",
            name="media",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="attachments",
                to="core.media",
            ),
        ),
        migrations.RemoveField(model_name="issuemedia", name="file"),
        migrations.RemoveField(model_name="issuemedia", name="kind"),
        migrations.AlterModelOptions(
            name="issuemedia",
            options={"ordering": ["order", "created_at"]},
        ),
        migrations.AddConstraint(
            model_name="issuemedia",
            constraint=models.UniqueConstraint(
                fields=["issue", "media"], name="unique_issue_media"
            ),
        ),
    ]
