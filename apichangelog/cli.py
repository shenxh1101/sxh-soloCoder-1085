"""
Command-line interface for API Changelog Tool.
Provides commands: scan, diff, note, release, versions, review.
"""

import sys
import io
from pathlib import Path
from datetime import date, datetime
from typing import Optional

import click

from . import __version__
from .models import (
    ApiSpec, Change, ChangeType, ImpactLevel, ChangeScope,
    VersionDiff, ChangelogEntry, ReleaseInfo
)
from .storage import Storage
from .differ import Differ
from .formatter import ConsoleFormatter, MarkdownFormatter


def _setup_encoding():
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass


def _resolve_spec(ctx, param, value):
    if not value:
        return None
    storage: Storage = ctx.obj["storage"]

    if ":" in value and not Path(value).exists():
        name, version = value.split(":", 1)
        spec = storage.load_stored_spec(name, version)
        if spec is None:
            raise click.BadParameter(f"Stored spec not found: {name}:{version}")
        return spec
    else:
        return storage.load_spec(value)


@click.group()
@click.version_option(version=__version__, prog_name="apichangelog")
@click.option("--dir", "base_dir", type=click.Path(), default=None,
              help="Working directory (default: current directory)")
@click.pass_context
def main(ctx: click.Context, base_dir: Optional[str]) -> None:
    """API Changelog Tool - Track, compare, and document API interface changes."""
    ctx.ensure_object(dict)
    _setup_encoding()
    ctx.obj["storage"] = Storage(base_dir)
    ctx.obj["console"] = ConsoleFormatter()
    ctx.obj["markdown"] = MarkdownFormatter()


# ============================================================
# scan
# ============================================================

@main.command()
@click.argument("spec", callback=_resolve_spec, required=True)
@click.option("--save", "save_spec", is_flag=True, default=False,
              help="Save the scanned spec to storage for later comparison")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output Markdown summary to file")
@click.pass_context
def scan(ctx: click.Context, spec: ApiSpec, save_spec: bool, output: Optional[str]) -> None:
    """Read API spec file and list endpoints, fields, and missing examples."""
    console: ConsoleFormatter = ctx.obj["console"]
    storage: Storage = ctx.obj["storage"]

    console.print_spec_summary(spec)

    no_examples = [ep for ep in spec.endpoints if not ep.has_examples()]
    if no_examples:
        click.echo()
        click.secho(f"[!] {len(no_examples)} endpoints are missing examples:", fg="yellow")
        for ep in no_examples:
            click.echo(f"  - {ep.key}")

    if save_spec:
        path = storage.save_stored_spec(spec)
        click.echo()
        click.secho(f"[OK] Spec saved: {spec.name}:{spec.version} -> {path}", fg="green")

    if output:
        lines = [f"# {spec.name} {spec.version}", ""]
        lines.append(f"- **Endpoints:** {len(spec.endpoints)}")
        lines.append(f"- **Modules:** {', '.join(spec.modules())}")
        lines.append("")
        by_module = spec.endpoints_by_module()
        for mod in sorted(by_module.keys()):
            lines.append(f"## {mod}")
            lines.append("")
            for ep in sorted(by_module[mod], key=lambda e: e.key):
                tag = " [NO EXAMPLE]" if not ep.has_examples() else ""
                lines.append(f"- `{ep.method} {ep.path}`{tag}")
                if ep.summary:
                    lines.append(f"  - {ep.summary}")
            lines.append("")
        Path(output).write_text("\n".join(lines), encoding="utf-8")
        click.echo()
        click.secho(f"[OK] Markdown written to: {output}", fg="green")


# ============================================================
# diff
# ============================================================

@main.command()
@click.argument("old_spec", callback=_resolve_spec, required=True)
@click.argument("new_spec", callback=_resolve_spec, required=True)
@click.option("--module", "-M", "modules", type=str, multiple=True,
              help="Filter by module name (can be repeated, e.g. -M users -M auth)")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Write full diff as Markdown to file")
@click.option("--pending", "pending_output", type=click.Path(), default=None,
              help="Write pending review checklist as Markdown to file")
@click.option("--save", "save_changes", is_flag=True, default=False,
              help="Save diff as changelog entry for the new version")
@click.pass_context
def diff(ctx: click.Context, old_spec: ApiSpec, new_spec: ApiSpec,
         modules: tuple[str, ...], output: Optional[str],
         pending_output: Optional[str], save_changes: bool) -> None:
    """Compare two API versions and show additions, deletions, and field changes."""
    console: ConsoleFormatter = ctx.obj["console"]
    storage: Storage = ctx.obj["storage"]
    md: MarkdownFormatter = ctx.obj["markdown"]

    differ = Differ()
    version_diff = differ.compare(old_spec, new_spec)

    if modules:
        module_set = set(modules)
        version_diff.changes = [c for c in version_diff.changes if c.module in module_set]

    console.print_diff(version_diff, new_spec)

    if output:
        content = md.render_diff(version_diff, new_spec)
        Path(output).write_text(content, encoding="utf-8")
        click.echo()
        click.secho(f"[OK] Diff Markdown written to: {output}", fg="green")

    if pending_output:
        content = md.render_pending_items(version_diff, new_spec)
        Path(pending_output).write_text(content, encoding="utf-8")
        click.echo()
        click.secho(f"[OK] Pending checklist written to: {pending_output}", fg="green")

    if save_changes:
        entry = storage.get_entry(new_spec.version) or ChangelogEntry(version=new_spec.version)
        entry.changes = version_diff.changes
        entry.spec_name = new_spec.name
        storage.upsert_entry(entry)
        click.echo()
        click.secho(f"[OK] Changes saved for {new_spec.name}:{new_spec.version}", fg="green")


# ============================================================
# note
# ============================================================

@main.command()
@click.argument("version", required=True)
@click.option("--change", "change_index", type=int, default=None,
              help="Index of specific change to annotate")
@click.option("--note", "-n", "note_text", type=str, default=None,
              help="Add a note to the change or release")
@click.option("--migration", "-m", type=str, default=None,
              help="Add migration guide for a breaking change")
@click.option("--confirm", is_flag=True, default=False,
              help="Mark a change as confirmed/reviewed")
@click.option("--impact", type=click.Choice(["low", "medium", "high", "breaking"]),
              default=None, help="Override impact level")
@click.option("--list", "list_changes", is_flag=True, default=False,
              help="List all changes with their indices")
@click.option("--release-note", type=str, default=None,
              help="Add a release-level note")
@click.pass_context
def note(ctx: click.Context, version: str, change_index: Optional[int],
         note_text: Optional[str], migration: Optional[str],
         confirm: bool, impact: Optional[str], list_changes: bool,
         release_note: Optional[str]) -> None:
    """Add manual notes, migration suggestions, and confirm changes."""
    storage: Storage = ctx.obj["storage"]

    entry = storage.get_entry(version)
    if entry is None:
        raise click.BadParameter(
            f"No changelog entry found for version {version}. "
            "Run 'diff' with --save first."
        )

    if list_changes:
        click.echo(f"Changes for version {version}:")
        for i, c in enumerate(entry.changes):
            status = "[OK]" if c.confirmed else "[PENDING]"
            tag = " [BREAKING]" if c.breaking else ""
            click.echo(f"  [{i}] {status} {c.description}{tag}")
        if entry.notes:
            click.echo()
            click.echo("Release notes:")
            for n in entry.notes:
                click.echo(f"  - {n}")
        return

    if release_note:
        entry.notes.append(release_note)
        storage.upsert_entry(entry)
        click.secho("[OK] Release note added", fg="green")
        return

    if change_index is None:
        raise click.BadParameter("Please specify --change INDEX or use --list to see indices")

    if change_index < 0 or change_index >= len(entry.changes):
        raise click.BadParameter(
            f"Invalid change index {change_index}. "
            f"Valid range: 0-{len(entry.changes) - 1}"
        )

    change = entry.changes[change_index]

    if note_text:
        change.notes.append(note_text)
    if migration:
        change.migration_guide = migration
    if confirm:
        change.confirmed = True
    if impact:
        change.impact = ImpactLevel(impact)
        change.breaking = (impact == "breaking")

    storage.upsert_entry(entry)
    click.secho(f"[OK] Change [{change_index}] updated", fg="green")
    click.echo(f"  Description: {change.description}")
    if change.notes:
        click.echo(f"  Notes: {'; '.join(change.notes)}")
    if change.migration_guide:
        click.echo(f"  Migration: {change.migration_guide}")
    click.echo(f"  Confirmed: {change.confirmed}")
    click.echo(f"  Impact: {change.impact.value}")


# ============================================================
# release
# ============================================================

@main.command()
@click.argument("version", required=True)
@click.option("--date", "release_date", type=str, default=None,
              help="Release date (YYYY-MM-DD, default: today)")
@click.option("--highlight", "-h", "highlights", type=str, multiple=True,
              help="Release highlight (can be repeated)")
@click.option("--module", "-M", "modules", type=str, multiple=True,
              help="Filter by module name (can be repeated)")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Write release notes as Markdown to file")
@click.option("--no-preview", is_flag=True, default=False,
              help="Disable console preview")
@click.pass_context
def release(ctx: click.Context, version: str, release_date: Optional[str],
            highlights: tuple[str, ...], modules: tuple[str, ...],
            output: Optional[str], no_preview: bool) -> None:
    """Generate module-level changelog summary, maintain version and release date."""
    storage: Storage = ctx.obj["storage"]
    console: ConsoleFormatter = ctx.obj["console"]
    md: MarkdownFormatter = ctx.obj["markdown"]

    entry = storage.get_entry(version)
    if entry is None:
        raise click.BadParameter(
            f"No changelog entry found for version {version}. "
            "Run 'diff' with --save first."
        )

    if modules:
        module_set = set(modules)
        filtered_changes = [c for c in entry.changes if c.module in module_set]
    else:
        filtered_changes = list(entry.changes)

    parsed_date: date
    if release_date:
        try:
            parsed_date = datetime.strptime(release_date, "%Y-%m-%d").date()
        except ValueError:
            raise click.BadParameter("Date must be in YYYY-MM-DD format")
    else:
        parsed_date = date.today()

    entry_modules = sorted({c.module for c in filtered_changes})
    release_info = ReleaseInfo(
        version=version,
        release_date=parsed_date,
        highlights=list(highlights),
        modules=entry_modules,
    )

    entry.release_date = parsed_date
    entry.released = True
    storage.upsert_entry(entry)

    if not no_preview:
        console.print_release_preview(entry, release_info, filtered_changes)

    if output:
        content = md.render_release(entry, release_info, filtered_changes)
        Path(output).write_text(content, encoding="utf-8")
        click.echo()
        click.secho(f"[OK] Release notes written to: {output}", fg="green")

    breaking_count = len([c for c in filtered_changes if c.breaking])
    added_count = len([c for c in filtered_changes if c.change_type == ChangeType.ADDED])

    click.echo()
    click.secho(f"Version analysis for {version}:", fg="cyan")
    click.echo(f"  Breaking changes: {breaking_count}")
    click.echo(f"  New additions: {added_count}")

    suggested = None
    if breaking_count > 0:
        suggested = "MAJOR"
    elif added_count > 0:
        suggested = "MINOR"
    else:
        suggested = "PATCH"
    click.secho(f"  Suggested semver bump: {suggested}", fg="yellow")

    pending = [c for c in filtered_changes if c.is_pending()]
    if pending:
        click.echo()
        click.secho(f"[!] {len(pending)} changes still pending review:", fg="yellow")
        for c in pending:
            tag = " [BREAKING]" if c.breaking else ""
            click.echo(f"  - {c.description}{tag}")


# ============================================================
# versions
# ============================================================

@main.command()
@click.option("--service", "-s", type=str, default=None,
              help="Filter by service name")
@click.pass_context
def versions(ctx: click.Context, service: Optional[str]) -> None:
    """List locally saved API specs and changelog entries."""
    storage: Storage = ctx.obj["storage"]
    console: ConsoleFormatter = ctx.obj["console"]

    specs = storage.list_stored_specs()
    if service:
        specs = [(n, v) for n, v in specs if n == service]

    entries = storage.load_changelog()
    entry_map: dict[str, ChangelogEntry] = {}
    for e in entries:
        entry_map[e.version] = e

    console.print_versions(specs, entry_map)


# ============================================================
# review
# ============================================================

@main.command()
@click.argument("version", required=True)
@click.option("--module", "-M", "modules", type=str, multiple=True,
              help="Filter by module name")
@click.option("--confirm", "confirm_indices", type=str, default=None,
              help="Confirm changes by index, e.g. --confirm 0,2,5 or --confirm all")
@click.option("--migrate", type=str, default=None,
              help="Add migration guide to a change, format: INDEX:GUIDE")
@click.option("--note", "-n", "note_text", type=str, default=None,
              help="Add a note to a change, format: INDEX:NOTE")
@click.pass_context
def review(ctx: click.Context, version: str, modules: tuple[str, ...],
           confirm_indices: Optional[str], migrate: Optional[str],
           note_text: Optional[str]) -> None:
    """Review pending changes: list unconfirmed items, batch confirm, add migration guides."""
    storage: Storage = ctx.obj["storage"]
    console: ConsoleFormatter = ctx.obj["console"]

    entry = storage.get_entry(version)
    if entry is None:
        raise click.BadParameter(
            f"No changelog entry found for version {version}. "
            "Run 'diff' with --save first."
        )

    changes = entry.changes
    if modules:
        module_set = set(modules)
        changes = [c for c in changes if c.module in module_set]

    if not confirm_indices and not migrate and not note_text:
        console.print_review_list(entry, changes)
        return

    if confirm_indices:
        indices = _parse_indices(confirm_indices, len(changes))
        for i in indices:
            changes[i].confirmed = True
            click.secho(f"  [OK] Confirmed [{i}]: {changes[i].description}", fg="green")
        storage.upsert_entry(entry)
        _print_pending_summary(entry, modules)

    if migrate:
        idx, guide = _parse_indexed_value(migrate, "migrate")
        if idx < 0 or idx >= len(changes):
            raise click.BadParameter(f"Invalid index {idx}. Valid: 0-{len(changes)-1}")
        changes[idx].migration_guide = guide
        storage.upsert_entry(entry)
        click.secho(f"  [OK] Migration guide added to [{idx}]", fg="green")
        _print_pending_summary(entry, modules)

    if note_text:
        idx, text = _parse_indexed_value(note_text, "note")
        if idx < 0 or idx >= len(changes):
            raise click.BadParameter(f"Invalid index {idx}. Valid: 0-{len(changes)-1}")
        changes[idx].notes.append(text)
        storage.upsert_entry(entry)
        click.secho(f"  [OK] Note added to [{idx}]", fg="green")
        _print_pending_summary(entry, modules)


def _parse_indices(value: str, max_len: int) -> list[int]:
    if value.strip().lower() == "all":
        return list(range(max_len))
    try:
        return [int(x.strip()) for x in value.split(",")]
    except ValueError:
        raise click.BadParameter(f"Invalid index list: {value}. Use comma-separated numbers or 'all'.")


def _parse_indexed_value(value: str, option_name: str) -> tuple[int, str]:
    if ":" not in value:
        raise click.BadParameter(f"--{option_name} format: INDEX:TEXT, e.g. 2:Update your client code")
    idx_str, text = value.split(":", 1)
    try:
        idx = int(idx_str.strip())
    except ValueError:
        raise click.BadParameter(f"Invalid index in --{option_name}: {idx_str}")
    return idx, text.strip()


def _print_pending_summary(entry: ChangelogEntry, modules: tuple[str, ...]) -> None:
    changes = entry.changes
    if modules:
        changes = [c for c in changes if c.module in set(modules)]
    pending = [c for c in changes if c.is_pending()]
    confirmed = len(changes) - len(pending)
    click.echo()
    click.echo(f"  Progress: {confirmed}/{len(changes)} confirmed, {len(pending)} pending")


if __name__ == "__main__":
    main()
