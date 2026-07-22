from django.db import migrations, models

import core.models


def backfill_public_ids(apps, schema_editor):  # type: ignore[no-untyped-def]
    from core.models import generate_public_id

    Issue = apps.get_model("core", "Issue")
    for issue in Issue.objects.filter(public_id__isnull=True):
        candidate = generate_public_id()
        while Issue.objects.filter(public_id=candidate).exists():
            candidate = generate_public_id()
        issue.public_id = candidate
        issue.save(update_fields=["public_id"])


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="issue",
            name="public_id",
            field=models.CharField(max_length=12, null=True, editable=False),
        ),
        migrations.RunPython(backfill_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="issue",
            name="public_id",
            field=models.CharField(
                max_length=12,
                unique=True,
                editable=False,
                default=core.models.generate_public_id,
            ),
        ),
        migrations.AddField(
            model_name="issue",
            name="source_url",
            field=models.URLField(blank=True, verbose_name="source link"),
        ),
    ]
