"""The fail-fast runserver: pending schema work stops the dev server
with the exact fix command instead of Django's ignorable warning."""

import pytest
from django.core.management import get_commands
from django.db import connection, models
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

from core.management.commands.runserver import Command, pending_schema_work

pytestmark = pytest.mark.django_db


def test_core_runserver_shadows_the_stock_command() -> None:
    # If INSTALLED_APPS ordering ever regresses, the override silently
    # stops applying — this is the tripwire.
    assert get_commands()["runserver"] == "core"


def test_clean_schema_reports_nothing_pending() -> None:
    unapplied, changed_apps = pending_schema_work()
    assert unapplied == []
    assert changed_apps == []


def _unapply_latest_core_migration() -> str:
    """Simulate 'pulled code with a new migration, forgot to migrate':
    mark the newest core migration as unapplied in the ledger."""
    executor = MigrationExecutor(connection)
    leaf = next(node for node in executor.loader.graph.leaf_nodes() if node[0] == "core")
    MigrationRecorder(connection).record_unapplied(*leaf)
    return f"{leaf[0]}.{leaf[1]}"


def test_unapplied_migration_is_detected() -> None:
    name = _unapply_latest_core_migration()
    unapplied, _ = pending_schema_work()
    assert name in unapplied


def test_model_change_without_migration_is_detected() -> None:
    class Stray(models.Model):  # noqa: DJ008 — a model no migration knows about
        name = models.CharField(max_length=10)

        class Meta:
            app_label = "core"

    try:
        _, changed_apps = pending_schema_work()
        assert changed_apps == ["core"]
    finally:
        # Unregister so the stray model can't leak into other tests.
        from django.apps import apps

        del apps.get_app_config("core").models["stray"]
        apps.all_models["core"].pop("stray", None)
        apps.clear_cache()


def test_handle_refuses_and_names_the_fix() -> None:
    name = _unapply_latest_core_migration()
    command = Command()
    with pytest.raises(Exception, match=r"manage\.py migrate") as excinfo:
        command.handle()
    assert "Refusing to start" in str(excinfo.value)
    assert name in str(excinfo.value)
