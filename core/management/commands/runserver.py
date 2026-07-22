"""
Dev server that refuses to start with pending schema work.

Django's stock runserver prints a warning about unapplied migrations
and starts anyway; the developer hits a confusing ProgrammingError
minutes later on some unrelated page. Fail fast instead, and print the
exact command that fixes it. Subclasses the staticfiles runserver so
static serving behaves as before; `core` sits above
`django.contrib.staticfiles` in INSTALLED_APPS so this command wins.

The check runs in handle(), so it fires in the reloader parent (clean
CommandError before anything starts) and again in the reloaded child
after code edits (adding a model without a migration stops the server
instead of limping on).
"""

from pathlib import Path
from typing import Any

from django.apps import apps
from django.contrib.staticfiles.management.commands.runserver import (
    Command as StaticfilesRunserverCommand,
)
from django.core.management.base import CommandError
from django.db import DEFAULT_DB_ALIAS, OperationalError, connections
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.state import ProjectState
from django.utils import translation


def _manage(command: str) -> str:
    """The exact invocation for this environment: plain inside the
    container (compose), via uv on bare metal."""
    prefix = "" if Path("/.dockerenv").exists() else "uv run "
    return f"{prefix}python manage.py {command}"


def pending_schema_work() -> tuple[list[str], list[str]]:
    """Returns (unapplied migration names, app labels with model changes
    that have no migration file). Raises CommandError if the database
    cannot be reached at all."""
    connection = connections[DEFAULT_DB_ALIAS]
    try:
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    except OperationalError as exc:
        raise CommandError(
            f"Cannot reach the database ({exc}).\n"
            f"Is Postgres running? Start it with:\n\n"
            f"    docker compose up -d db\n\n"
            f"or point DATABASE_URL in .env at a running PostGIS."
        ) from exc
    unapplied = [f"{migration.app_label}.{migration.name}" for migration, _ in plan]
    # Deactivate translations while diffing models against migrations —
    # under a non-English locale, lazy verbose_names evaluate to BM while
    # migration files carry English, producing phantom AlterFields
    # everywhere (same reason makemigrations runs @no_translations).
    with translation.override(None):
        autodetector = MigrationAutodetector(
            executor.loader.project_state(), ProjectState.from_apps(apps)
        )
        changed_apps = sorted(autodetector.changes(graph=executor.loader.graph))
    return unapplied, changed_apps


class Command(StaticfilesRunserverCommand):
    def handle(self, *args: Any, **options: Any) -> None:
        unapplied, changed_apps = pending_schema_work()
        problems: list[str] = []
        fixes: list[str] = []
        if changed_apps:
            problems.append(
                "Model changes in {apps} have no migration file.".format(
                    apps=", ".join(changed_apps)
                )
            )
            fixes.append(_manage(f"makemigrations {' '.join(changed_apps)}"))
        if unapplied:
            problems.append("Unapplied migration(s): {names}.".format(names=", ".join(unapplied)))
        if unapplied or changed_apps:
            fixes.append(_manage("migrate"))
        if problems:
            fix_lines = "\n".join(f"    {f}" for f in fixes)
            raise CommandError(
                "Refusing to start with a stale database schema.\n"
                + "\n".join(f"  - {p}" for p in problems)
                + f"\n\nFix it with:\n\n{fix_lines}\n"
            )
        super().handle(*args, **options)

    def check_migrations(self) -> None:
        """The stock warning is redundant now — handle() already failed
        hard if anything was pending."""
