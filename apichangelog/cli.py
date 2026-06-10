"""
Command-line interface for API Changelog Tool.
Commands: scan, diff, note, release, versions, services, review.
"""

import sys
import io
import os
from pathlib import Path
from datetime import date, datetime
from typing import Optional

import click

from . import __version__
from .models import (
    ApiSpec, Change, ChangeType, ImpactLevel, ChangeScope,
    VersionDiff, ChangelogEntry, ReleaseInfo, ReleaseStatus
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


def _parse_spec_ref(ref: str, ctx: click.Context, storage: Storage) -> ApiSpec:
    """Parse `file_path.yaml` or `ServiceName:version` into an ApiSpec."""
    if ":" in ref and not Path(ref).exists():
        name, version = ref.split(":", 1)
        spec = storage.load_stored_spec(name, version)
        if spec is None:
            raise click.BadParameter(
                f"Stored spec not found: {name}:{version}. "
                f"Run 'scan <file> --save' first."
            )
        return spec
    return storage.load_spec(ref)


def _parse_entry_ref(ref: str) -> tuple[Optional[str], str]:
    """Parse `[ServiceName:]version` into (spec_name, version).

    spec_name is None when no service prefix was provided; caller must
    handle ambiguity or error out if multiple services match.
    """
    if ":" in ref:
        parts = ref.split(":", 1)
        return parts[0], parts[1]
    return None, ref


def _resolve_entry(storage: Storage, ref: str, cmd: str) -> ChangelogEntry:
    """Resolve an entry reference, with friendly error messages."""
    spec_name, version = _parse_entry_ref(ref)

    if spec_name:
        entry = storage.get_entry(spec_name, version)
        if entry is None:
            raise click.BadParameter(
                f"No changelog entry for {spec_name}:{version}. "
                f"Run 'diff <old> {spec_name}:{version} --save' first."
            )
        return entry

    entries = [e for e in storage.load_changelog() if e.version == version]
    if not entries:
        raise click.BadParameter(
            f"No changelog entry for version {version}. "
            f"Use '{cmd} ServiceName:{version}' or run diff --save first."
        )
    if len(entries) > 1:
        names = ", ".join(f"{e.spec_name}:{version}" for e in entries)
        raise click.BadParameter(
            f"Multiple services have version {version}: {names}. "
            f"Use '{cmd} ServiceName:{version}' to disambiguate."
        )
    return entries[0]


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
@click.argument("spec_ref", required=True)
@click.option("--save", "save_spec", is_flag=True, default=False,
              help="Save the scanned spec to storage for later comparison")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output Markdown summary to file")
@click.pass_context
def scan(ctx: click.Context, spec_ref: str, save_spec: bool, output: Optional[str]) -> None:
    """Read API spec file and list endpoints, fields, and missing examples.

    SPEC_REF: path to YAML/JSON file, or 'ServiceName:version' to re-read a saved spec.
    """
    console: ConsoleFormatter = ctx.obj["console"]
    storage: Storage = ctx.obj["storage"]

    spec = _parse_spec_ref(spec_ref, ctx, storage)
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
@click.argument("old_ref", required=True)
@click.argument("new_ref", required=True)
@click.option("--module", "-M", "modules", type=str, multiple=True,
              help="Filter by module name (repeatable)")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Write full diff as Markdown to file")
@click.option("--pending", "pending_output", type=click.Path(), default=None,
              help="Write pending review checklist as Markdown to file")
@click.option("--save", "save_changes", is_flag=True, default=False,
              help="Save diff as changelog entry for the new version")
@click.pass_context
def diff(ctx: click.Context, old_ref: str, new_ref: str,
         modules: tuple[str, ...], output: Optional[str],
         pending_output: Optional[str], save_changes: bool) -> None:
    """Compare two API versions and show additions, deletions, and field changes.

    OLD_REF / NEW_REF: file path or 'ServiceName:version'.
    """
    console: ConsoleFormatter = ctx.obj["console"]
    storage: Storage = ctx.obj["storage"]
    md: MarkdownFormatter = ctx.obj["markdown"]

    old_spec = _parse_spec_ref(old_ref, ctx, storage)
    new_spec = _parse_spec_ref(new_ref, ctx, storage)

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
        entry = (storage.get_entry(new_spec.name, new_spec.version)
                 or ChangelogEntry(spec_name=new_spec.name, version=new_spec.version))
        entry.changes = version_diff.changes
        entry.diff_from_version = old_spec.version
        entry.spec_name = new_spec.name
        storage.upsert_entry(entry)
        click.echo()
        click.secho(
            f"[OK] Changes saved for {new_spec.name}:{new_spec.version} "
            f"(diff from {old_spec.version})",
            fg="green",
        )


# ============================================================
# note
# ============================================================

@main.command()
@click.argument("entry_ref", required=True)
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
def note(ctx: click.Context, entry_ref: str, change_index: Optional[int],
         note_text: Optional[str], migration: Optional[str],
         confirm: bool, impact: Optional[str], list_changes: bool,
         release_note: Optional[str]) -> None:
    """Add manual notes, migration suggestions, and confirm changes.

    ENTRY_REF: 'ServiceName:version' or just 'version' (if unambiguous).
    """
    storage: Storage = ctx.obj["storage"]
    entry = _resolve_entry(storage, entry_ref, "note")

    if list_changes:
        click.echo(f"Changes for {entry.spec_name}:{entry.version}:")
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
@click.argument("entry_ref", required=True)
@click.option("--date", "release_date", type=str, default=None,
              help="Release date (YYYY-MM-DD, default: today)")
@click.option("--highlight", "-h", "highlights", type=str, multiple=True,
              help="Release highlight (repeatable)")
@click.option("--module", "-M", "modules", type=str, multiple=True,
              help="Filter by module name (repeatable)")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Write release notes as Markdown to file")
@click.option("--no-preview", is_flag=True, default=False,
              help="Disable console preview")
@click.option("--draft", is_flag=True, default=False,
              help="Explicitly set status to DRAFT (useful after --publish)")
@click.option("--publish", is_flag=True, default=False,
              help="Mark release as PUBLISHED")
@click.option("--published-by", type=str, default=None,
              help="Record who performed the release (name/email)")
@click.option("--channel", type=str, default=None,
              help="Release channel, e.g. internal, public, stable, beta")
@click.option("--template", "template_name",
              type=click.Choice(["default", "public", "internal", "beta"]),
              default=None,
              help="Markdown template for release notes")
@click.pass_context
def release(ctx: click.Context, entry_ref: str, release_date: Optional[str],
            highlights: tuple[str, ...], modules: tuple[str, ...],
            output: Optional[str], no_preview: bool,
            draft: bool, publish: bool,
            published_by: Optional[str], channel: Optional[str],
            template_name: Optional[str]) -> None:
    """Generate changelog, maintain release metadata. Supports DRAFT/PUBLISHED status.

    ENTRY_REF: 'ServiceName:version' or just 'version'.
    """
    storage: Storage = ctx.obj["storage"]
    console: ConsoleFormatter = ctx.obj["console"]
    md: MarkdownFormatter = ctx.obj["markdown"]

    entry = _resolve_entry(storage, entry_ref, "release")

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
        version=entry.version,
        release_date=parsed_date,
        highlights=list(highlights),
        modules=entry_modules,
    )

    entry.release_date = parsed_date
    if published_by:
        entry.released_by = published_by
    if channel:
        entry.release_channel = channel
    if template_name:
        entry.release_template = template_name
    if draft:
        entry.status = ReleaseStatus.DRAFT
    if publish:
        entry.status = ReleaseStatus.PUBLISHED
    if published_by and not publish and not draft:
        entry.status = ReleaseStatus.PUBLISHED

    resolved_md_path = ""
    if output:
        resolved_md_path = str(Path(output).resolve())
        entry.markdown_path = resolved_md_path

    storage.upsert_entry(entry)

    if not no_preview:
        console.print_release_preview(entry, release_info, filtered_changes)

    effective_template = entry.release_template or "default"
    if output:
        content = md.render_release(entry, release_info, filtered_changes,
                                     template=effective_template)
        Path(output).write_text(content, encoding="utf-8")
        click.echo()
        click.secho(
            f"[OK] Release notes written to: {resolved_md_path} "
            f"(template={effective_template})",
            fg="green",
        )

    breaking_count = len([c for c in filtered_changes if c.breaking])
    added_count = len([c for c in filtered_changes if c.change_type == ChangeType.ADDED])

    click.echo()
    click.secho(f"Version analysis for {entry.spec_name}:{entry.version}:", fg="cyan")
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

    status = entry.status.value.upper()
    click.echo(f"  Status: {status}")
    if entry.released_by:
        click.echo(f"  Released by: {entry.released_by}")
    if entry.release_channel:
        click.echo(f"  Channel: {entry.release_channel}")
    if entry.release_template:
        click.echo(f"  Template: {entry.release_template}")

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
@click.option("--status", type=click.Choice(["draft", "published"]),
              default=None, help="Filter by release status")
@click.option("--channel", type=str, default=None,
              help="Filter by release channel")
@click.option("--pending", "has_pending", is_flag=True, default=False,
              help="Only show versions with pending review items")
@click.option("--no-pending", "no_pending", is_flag=True, default=False,
              help="Only show versions with no pending items")
@click.pass_context
def versions(ctx: click.Context, service: Optional[str],
             status: Optional[str], channel: Optional[str],
             has_pending: bool, no_pending: bool) -> None:
    """List saved specs and changelog entries across all services."""
    storage: Storage = ctx.obj["storage"]
    console: ConsoleFormatter = ctx.obj["console"]

    specs = storage.list_stored_specs()
    if service:
        specs = [(n, v) for n, v in specs if n == service]

    rs_enum = (ReleaseStatus(status) if status else None)
    pending_flag: Optional[bool] = None
    if has_pending:
        pending_flag = True
    if no_pending:
        pending_flag = False

    entries = storage.list_entries_filtered(
        spec_name=service, status=rs_enum,
        channel=channel, has_pending=pending_flag,
    )

    entry_map: dict[tuple[str, str], ChangelogEntry] = {}
    for e in entries:
        entry_map[(e.spec_name, e.version)] = e

    if status or channel or pending_flag is not None:
        spec_keys = set(entry_map.keys())
        specs = [(n, v) for n, v in specs if (n, v) in spec_keys]

    console.print_versions(specs, entry_map)


# ============================================================
# services / workspace
# ============================================================

@main.command("services")
@click.option("--service", "-s", type=str, default=None,
              help="Show only a specific service")
@click.option("--status", type=click.Choice(["draft", "published"]),
              default=None, help="Filter versions by release status")
@click.option("--channel", type=str, default=None,
              help="Filter versions by release channel")
@click.option("--pending", "has_pending", is_flag=True, default=False,
              help="Only show services with pending review items")
@click.option("--health", "health_check", is_flag=True, default=False,
              help="Run workspace health check")
@click.pass_context
def services_cmd(ctx: click.Context, service: Optional[str],
                 status: Optional[str], channel: Optional[str],
                 has_pending: bool, health_check: bool) -> None:
    """Workspace overview: grouped by service, with version lines and stats."""
    storage: Storage = ctx.obj["storage"]
    console: ConsoleFormatter = ctx.obj["console"]

    if health_check:
        report = storage.health_check()
        console.print_health_check(report)
        return

    summary = storage.workspace_summary()
    if service:
        if service not in summary:
            click.secho(f"[!] Service '{service}' not found in workspace", fg="red")
            sys.exit(1)
        summary = {service: summary[service]}

    rs_enum = (ReleaseStatus(status) if status else None)
    if rs_enum or channel or has_pending:
        filtered_entries = storage.list_entries_filtered(
            status=rs_enum, channel=channel,
            has_pending=(True if has_pending else None),
        )
        by_svc: dict[str, set] = {}
        for e in filtered_entries:
            by_svc.setdefault(e.spec_name, set()).add(e.version)
        filtered_services = set(by_svc.keys())

        summary = {
            name: {
                "versions": [v for v in data["versions"]
                             if not by_svc.get(name) or v[0] in by_svc.get(name, set())],
                "entries": [e for e in data["entries"]
                            if not by_svc.get(e.spec_name) or e.version in by_svc.get(e.spec_name, set())],
            }
            for name, data in summary.items()
            if name in filtered_services or not filtered_services
        }
        summary = {
            n: d for n, d in summary.items()
            if d["versions"] or d["entries"]
        }

    console.print_workspace(summary)


# ============================================================
# review
# ============================================================

@main.command()
@click.argument("entry_ref", required=True)
@click.option("--module", "-M", "modules", type=str, multiple=True,
              help="Filter by module name")
@click.option("--confirm", "confirm_indices", type=str, default=None,
              help="Confirm changes by index: --confirm 0,2,5 or --confirm all")
@click.option("--migrate", type=str, default=None,
              help="Add migration guide: --migrate INDEX:GUIDE")
@click.option("--note", "-n", "note_text", type=str, default=None,
              help="Add a note: --note INDEX:NOTE")
@click.pass_context
def review(ctx: click.Context, entry_ref: str, modules: tuple[str, ...],
           confirm_indices: Optional[str], migrate: Optional[str],
           note_text: Optional[str]) -> None:
    """Review pending changes: list unconfirmed items, batch confirm, add notes."""
    storage: Storage = ctx.obj["storage"]
    console: ConsoleFormatter = ctx.obj["console"]

    entry = _resolve_entry(storage, entry_ref, "review")

    changes = list(entry.changes)
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
        _print_pending_summary(changes)

    if migrate:
        idx, guide = _parse_indexed_value(migrate, "migrate")
        if idx < 0 or idx >= len(changes):
            raise click.BadParameter(f"Invalid index {idx}. Valid: 0-{len(changes)-1}")
        changes[idx].migration_guide = guide
        storage.upsert_entry(entry)
        click.secho(f"  [OK] Migration guide added to [{idx}]", fg="green")
        _print_pending_summary(changes)

    if note_text:
        idx, text = _parse_indexed_value(note_text, "note")
        if idx < 0 or idx >= len(changes):
            raise click.BadParameter(f"Invalid index {idx}. Valid: 0-{len(changes)-1}")
        changes[idx].notes.append(text)
        storage.upsert_entry(entry)
        click.secho(f"  [OK] Note added to [{idx}]", fg="green")
        _print_pending_summary(changes)


def _parse_indices(value: str, max_len: int) -> list[int]:
    if value.strip().lower() == "all":
        return list(range(max_len))
    try:
        return [int(x.strip()) for x in value.split(",")]
    except ValueError:
        raise click.BadParameter(f"Invalid index list: {value}. Use comma-separated numbers or 'all'.")


def _parse_indexed_value(value: str, option_name: str) -> tuple[int, str]:
    if ":" not in value:
        raise click.BadParameter(
            f"--{option_name} format: INDEX:TEXT, e.g. 2:Update your client code"
        )
    idx_str, text = value.split(":", 1)
    try:
        idx = int(idx_str.strip())
    except ValueError:
        raise click.BadParameter(f"Invalid index in --{option_name}: {idx_str}")
    return idx, text.strip()


def _print_pending_summary(changes: list[Change]) -> None:
    pending = [c for c in changes if c.is_pending()]
    confirmed = len(changes) - len(pending)
    click.echo(
        f"  Progress: {confirmed}/{len(changes)} confirmed, "
        f"{len(pending)} pending"
    )


# ============================================================
# approval
# ============================================================

@main.command()
@click.argument("entry_ref", required=True)
@click.pass_context
def approval(ctx: click.Context, entry_ref: str) -> None:
    """Approval view: per-module review status before publishing.

    Shows each module's unconfirmed changes and breaking changes
    missing migration guides.
    """
    storage: Storage = ctx.obj["storage"]
    console: ConsoleFormatter = ctx.obj["console"]

    entry = _resolve_entry(storage, entry_ref, "approval")
    summary = storage.approval_summary(entry.spec_name, entry.version)
    console.print_approval(entry, summary)


# ============================================================
# export
# ============================================================

@main.command("export")
@click.argument("output", required=True, type=click.Path())
@click.pass_context
def export_cmd(ctx: click.Context, output: str) -> None:
    """Export entire workspace (specs + changelog) to a zip archive."""
    storage: Storage = ctx.obj["storage"]
    path = storage.export_workspace(output)
    click.secho(f"[OK] Workspace exported to: {path}", fg="green")


# ============================================================
# import
# ============================================================

@main.command("import")
@click.argument("archive", required=True, type=click.Path(exists=True))
@click.option("--overwrite", is_flag=True, default=False,
              help="Overwrite existing files if present")
@click.pass_context
def import_cmd(ctx: click.Context, archive: str, overwrite: bool) -> None:
    """Import workspace from a zip archive created by 'export'."""
    storage: Storage = ctx.obj["storage"]
    count = storage.import_workspace(archive, overwrite=overwrite)
    click.secho(
        f"[OK] Imported {count} files from {archive}"
        + (" (no overwrites)" if not overwrite else ""),
        fg="green",
    )


if __name__ == "__main__":
    main()
