"""
Command-line interface for API Changelog Tool.
Provides four commands: scan, diff, note, release.
"""

import sys
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


def _resolve_spec(ctx, param, value):
    """Click callback: resolve spec from argument (file path or stored name:version)."""
    if not value:
        return None
    storage: Storage = ctx.obj["storage"]

    if ":" in value and Path(value).suffix not in (".yaml", ".yml", ".json"):
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
    ctx.obj["storage"] = Storage(base_dir)
    ctx.obj["console"] = ConsoleFormatter()
    ctx.obj["markdown"] = MarkdownFormatter()


# ============================================================
# scan 命令
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
    md: MarkdownFormatter = ctx.obj["markdown"]

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
        click.secho(f"[OK] Spec saved to: {path}", fg="green")

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
# diff 命令
# ============================================================

@main.command()
@click.argument("old_spec", callback=_resolve_spec, required=True)
@click.argument("new_spec", callback=_resolve_spec, required=True)
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Write full diff as Markdown to file")
@click.option("--pending", "pending_output", type=click.Path(), default=None,
              help="Write pending review checklist as Markdown to file")
@click.option("--save", "save_changes", is_flag=True, default=False,
              help="Save diff as changelog entry for the new version")
@click.pass_context
def diff(ctx: click.Context, old_spec: ApiSpec, new_spec: ApiSpec,
         output: Optional[str], pending_output: Optional[str],
         save_changes: bool) -> None:
    """Compare two API versions and show additions, deletions, and field changes."""
    console: ConsoleFormatter = ctx.obj["console"]
    storage: Storage = ctx.obj["storage"]
    md: MarkdownFormatter = ctx.obj["markdown"]

    differ = Differ()
    version_diff = differ.compare(old_spec, new_spec)

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
        storage.upsert_entry(entry)
        click.echo()
        click.secho(f"[OK] Changes saved for version {new_spec.version}", fg="green")


# ============================================================
# note 命令
# ============================================================

@main.command()
@click.argument("version", required=True)
@click.option("--change", "change_index", type=int, default=None,
              help="Index of specific change to annotate (from diff/list output)")
@click.option("--note", "-n", "note_text", type=str, default=None,
              help="Add a note to the change or release")
@click.option("--migration", "-m", type=str, default=None,
              help="Add migration guide for a breaking change")
@click.option("--confirm", is_flag=True, default=False,
              help="Mark a change as confirmed/reviewed")
@click.option("--impact", type=click.Choice(["low", "medium", "high", "breaking"]),
              default=None, help="Override impact level")
@click.option("--list", "list_changes", is_flag=True, default=False,
              help="List all changes with their indices for the given version")
@click.option("--release-note", type=str, default=None,
              help="Add a release-level note")
@click.pass_context
def note(ctx: click.Context, version: str, change_index: Optional[int],
         note_text: Optional[str], migration: Optional[str],
         confirm: bool, impact: Optional[str], list_changes: bool,
         release_note: Optional[str]) -> None:
    """Add manual notes, migration suggestions, and confirm changes."""
    storage: Storage = ctx.obj["storage"]
    console: ConsoleFormatter = ctx.obj["console"]

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
        click.secho(f"[OK] Release note added", fg="green")
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
# release 命令
# ============================================================

@main.command()
@click.argument("version", required=True)
@click.option("--date", "release_date", type=str, default=None,
              help="Release date (YYYY-MM-DD, default: today)")
@click.option("--highlight", "-h", "highlights", type=str, multiple=True,
              help="Release highlight (can be repeated)")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Write release notes as Markdown to file")
@click.option("--preview", is_flag=True, default=True,
              help="Print release notes preview to console (default: on)")
@click.option("--no-preview", is_flag=True, default=False,
              help="Disable console preview")
@click.option("--bump-major", is_flag=True, default=False,
              help="Suggest major version bump based on breaking changes")
@click.option("--bump-minor", is_flag=True, default=False,
              help="Suggest minor version bump based on additions")
@click.option("--bump-patch", is_flag=True, default=False,
              help="Suggest patch version bump based on fixes only")
@click.pass_context
def release(ctx: click.Context, version: str, release_date: Optional[str],
            highlights: tuple[str, ...], output: Optional[str],
            preview: bool, no_preview: bool,
            bump_major: bool, bump_minor: bool, bump_patch: bool) -> None:
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

    parsed_date: date
    if release_date:
        try:
            parsed_date = datetime.strptime(release_date, "%Y-%m-%d").date()
        except ValueError:
            raise click.BadParameter("Date must be in YYYY-MM-DD format")
    else:
        parsed_date = date.today()

    modules = sorted({c.module for c in entry.changes})
    release_info = ReleaseInfo(
        version=version,
        release_date=parsed_date,
        highlights=list(highlights),
        modules=modules,
    )

    entry.release_date = parsed_date
    entry.released = True
    storage.upsert_entry(entry)

    if not no_preview and preview:
        console.print_release_preview(entry, release_info)

    if output:
        content = md.render_release(entry, release_info)
        Path(output).write_text(content, encoding="utf-8")
        click.echo()
        click.secho(f"[OK] Release notes written to: {output}", fg="green")

    # Version bump suggestion
    breaking_count = len([c for c in entry.changes if c.breaking])
    added_count = len([c for c in entry.changes if c.change_type == ChangeType.ADDED])

    click.echo()
    click.secho(f"Version analysis for {version}:", fg="cyan")
    click.echo(f"  Breaking changes: {breaking_count}")
    click.echo(f"  New additions: {added_count}")

    suggested = None
    if bump_major or breaking_count > 0:
        suggested = "MAJOR"
    elif bump_minor or added_count > 0:
        suggested = "MINOR"
    elif bump_patch:
        suggested = "PATCH"

    if suggested:
        click.secho(f"  Suggested semver bump: {suggested}", fg="yellow")

    pending = [c for c in entry.changes if c.is_pending()]
    if pending:
        click.echo()
        click.secho(f"[!] {len(pending)} changes still pending review:", fg="yellow")
        for c in pending:
            tag = " [BREAKING]" if c.breaking else ""
            click.echo(f"  - {c.description}{tag}")


if __name__ == "__main__":
    main()
