"""
Output formatting module for API Changelog Tool.
Handles console rendering with Rich and Markdown file generation.
"""

from datetime import date
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree

from .models import (
    ApiSpec, EndpointDef, Change, ChangeType, ImpactLevel, ChangeScope,
    VersionDiff, ChangelogEntry, ReleaseInfo
)


IMPACT_COLORS = {
    ImpactLevel.NONE: "white",
    ImpactLevel.LOW: "green",
    ImpactLevel.MEDIUM: "yellow",
    ImpactLevel.HIGH: "orange_red1",
    ImpactLevel.BREAKING: "red",
}

CHANGE_TYPE_LABELS = {
    ChangeType.ADDED: ("+", "green", "新增"),
    ChangeType.REMOVED: ("-", "red", "删除"),
    ChangeType.MODIFIED: ("~", "yellow", "修改"),
    ChangeType.DEPRECATED: ("!", "yellow", "废弃"),
}


class ConsoleFormatter:
    """Formats output for terminal display using Rich."""

    def __init__(self):
        import sys
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        self.console = Console(legacy_windows=False, highlight=False)

    # ---------- Scan output ----------

    def print_spec_summary(self, spec: ApiSpec) -> None:
        """Print a summary of an API spec."""
        header = Panel.fit(
            Text.from_markup(
                f"[bold cyan]{spec.name}[/bold cyan]\n"
                f"[dim]Version:[/dim] [bold]{spec.version}[/bold]\n"
                f"[dim]Base URL:[/dim] {spec.base_url or '(none)'}\n"
                f"[dim]Endpoints:[/dim] [bold]{len(spec.endpoints)}[/bold]\n"
                f"[dim]Modules:[/dim] [bold]{len(spec.modules())}[/bold]"
            ),
            title="API Specification",
            border_style="cyan",
        )
        self.console.print(header)

        by_module = spec.endpoints_by_module()
        for mod in sorted(by_module.keys()):
            tree = Tree(f"[bold blue]{mod}[/bold blue] ({len(by_module[mod])} endpoints)")
            for ep in sorted(by_module[mod], key=lambda e: e.key):
                label = f"[bold]{ep.method}[/bold] {ep.path}"
                if ep.deprecated:
                    label += " [yellow](deprecated)[/yellow]"
                if ep.summary:
                    label += f" [dim]- {ep.summary}[/dim]"
                if not ep.has_examples():
                    label += " [red][!] no examples[/red]"
                tree.add(label)
            self.console.print(tree)

    # ---------- Diff output ----------

    def print_diff(self, diff: VersionDiff, new_spec: Optional[ApiSpec] = None) -> None:
        """Print a formatted diff summary."""
        total = len(diff.changes)
        breaking = len(diff.breaking_changes())
        pending = len(diff.pending_changes())

        header = Panel.fit(
            Text.from_markup(
                f"[bold cyan]{diff.old_version}[/bold cyan] → "
                f"[bold green]{diff.new_version}[/bold green]\n"
                f"[dim]Total changes:[/dim] [bold]{total}[/bold]\n"
                f"[dim]Breaking changes:[/dim] [bold red]{breaking}[/bold red]\n"
                f"[dim]Pending review:[/dim] [bold yellow]{pending}[/bold yellow]"
            ),
            title="API Diff",
            border_style="cyan",
        )
        self.console.print(header)

        by_module = diff.by_module()
        for mod in sorted(by_module.keys()):
            changes = by_module[mod]
            mod_title = f"[bold blue]{mod}[/bold blue] ({len(changes)} changes)"
            tree = Tree(mod_title)

            for c in sorted(changes, key=lambda x: (x.endpoint_key or "", x.scope.value)):
                self._add_change_to_tree(tree, c)

            self.console.print(tree)

        if new_spec:
            missing = diff.missing_examples(new_spec)
            if missing:
                self.console.print()
                self.console.print(
                    Panel.fit(
                        "\n".join(f"  • [red]{ep.key}[/red]" for ep in missing),
                        title=f"[!] Missing examples ({len(missing)} endpoints)",
                        border_style="yellow",
                    )
                )

        pending_list = diff.pending_changes()
        if pending_list:
            self.console.print()
            self.console.print(
                Panel.fit(
                    "\n".join(
                        f"  • [yellow]{c.description}[/yellow]"
                        + (" [bold red](breaking)[/bold red]" if c.breaking else "")
                        for c in pending_list
                    ),
                    title=f"[!] Pending review ({len(pending_list)} items)",
                    border_style="yellow",
                )
            )

    def _add_change_to_tree(self, tree: Tree, change: Change) -> None:
        icon, color, label = CHANGE_TYPE_LABELS[change.change_type]
        impact_color = IMPACT_COLORS[change.impact]
        prefix = f"[{color}]{icon}[/{color}]"

        text_parts = [f"{prefix} "]
        if change.breaking:
            text_parts.append("[bold red]BREAKING[/bold red] ")
        text_parts.append(f"[{impact_color}]{change.impact.value.upper()}[/{impact_color}] ")
        text_parts.append(change.description)

        branch = tree.add("".join(text_parts))

        if change.field_changes:
            for fc in change.field_changes:
                fc_icon, fc_color, _ = CHANGE_TYPE_LABELS[fc.change_type]
                detail = f"[{fc_color}]{fc_icon}[/{fc_color}] {fc.field_name}"
                if fc.property_changed:
                    detail += f" [dim]({fc.property_changed})[/dim]"
                if fc.old_value is not None and fc.new_value is not None:
                    detail += f": [red]{fc.old_value}[/red] → [green]{fc.new_value}[/green]"
                elif fc.new_value is not None:
                    detail += f": [green]{fc.new_value}[/green]"
                elif fc.old_value is not None:
                    detail += f": [red]{fc.old_value}[/red]"
                branch.add(detail)

        if change.notes:
            for note in change.notes:
                branch.add(f"[cyan][NOTE] {note}[/cyan]")
        if change.migration_guide:
            branch.add(f"[blue]→ Migration: {change.migration_guide}[/blue]")
        if not change.confirmed:
            branch.add("[yellow][PENDING] Pending confirmation[/yellow]")

    # ---------- Release output ----------

    def print_release_preview(self, entry: ChangelogEntry, release_info: ReleaseInfo) -> None:
        """Print a release changelog preview."""
        date_str = release_info.release_date.isoformat()
        header = Panel.fit(
            Text.from_markup(
                f"[bold cyan]{release_info.version}[/bold cyan]\n"
                f"[dim]Release date:[/dim] [bold]{date_str}[/bold]\n"
                f"[dim]Modules:[/dim] [bold]{', '.join(release_info.modules)}[/bold]\n"
                f"[dim]Total changes:[/dim] [bold]{len(entry.changes)}[/bold]"
            ),
            title="Release Notes Preview",
            border_style="green",
        )
        self.console.print(header)

        if release_info.highlights:
            highlights = Tree("[bold yellow][*] Highlights[/bold yellow]")
            for h in release_info.highlights:
                highlights.add(h)
            self.console.print(highlights)
            self.console.print()

        breaking = [c for c in entry.changes if c.breaking]
        if breaking:
            self.console.print("[bold red][!] BREAKING CHANGES[/bold red]")
            for c in breaking:
                self.console.print(f"  • {c.description}")
                if c.migration_guide:
                    self.console.print(f"    [blue]→ {c.migration_guide}[/blue]")
            self.console.print()

        by_module = {}
        for c in entry.changes:
            by_module.setdefault(c.module, []).append(c)
        for mod in sorted(by_module.keys()):
            self.console.print(f"[bold blue]### {mod}[/bold blue]")
            for change_type in (ChangeType.ADDED, ChangeType.MODIFIED,
                                ChangeType.REMOVED, ChangeType.DEPRECATED):
                changes = [c for c in by_module[mod] if c.change_type == change_type]
                if not changes:
                    continue
                _, _, label = CHANGE_TYPE_LABELS[change_type]
                self.console.print(f"  **{label}**")
                for c in changes:
                    if c.breaking:
                        continue
                    self.console.print(f"    - {c.description}")
                    for note in c.notes:
                        self.console.print(f"      [dim]_{note}_[/dim]")
            self.console.print()


class MarkdownFormatter:
    """Generates Markdown format changelogs."""

    # ---------- Diff Markdown ----------

    def render_diff(self, diff: VersionDiff, new_spec: Optional[ApiSpec] = None) -> str:
        """Render a VersionDiff as Markdown."""
        lines: list[str] = []
        lines.append(f"# API Diff: {diff.old_version} → {diff.new_version}")
        lines.append("")

        total = len(diff.changes)
        breaking_count = len(diff.breaking_changes())
        pending = len(diff.pending_changes())
        breaking_changes_list = diff.breaking_changes()
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Total changes:** {total}")
        lines.append(f"- **Breaking changes:** {breaking_count}")
        lines.append(f"- **Pending review:** {pending}")
        lines.append("")

        if breaking_changes_list:
            lines.append("## ⚠ Breaking Changes")
            lines.append("")
            for c in breaking_changes_list:
                lines.append(f"### {c.description}")
                if c.field_changes:
                    lines.append("")
                    lines.append("| Field | Change | Old | New |")
                    lines.append("|-------|--------|-----|-----|")
                    for fc in c.field_changes:
                        old_v = str(fc.old_value).replace("|", "\\|") if fc.old_value else "-"
                        new_v = str(fc.new_value).replace("|", "\\|") if fc.new_value else "-"
                        lines.append(f"| {fc.field_name} | {fc.change_type.value} | {old_v} | {new_v} |")
                if c.migration_guide:
                    lines.append("")
                    lines.append(f"**Migration guide:** {c.migration_guide}")
                lines.append("")

        by_module = diff.by_module()
        for mod in sorted(by_module.keys()):
            changes = by_module[mod]
            lines.append(f"## {mod}")
            lines.append("")
            lines.extend(self._render_change_group(changes))
            lines.append("")

        if new_spec:
            missing = diff.missing_examples(new_spec)
            if missing:
                lines.append("## ⚠ Missing Examples")
                lines.append("")
                for ep in missing:
                    lines.append(f"- `{ep.key}`")
                lines.append("")

        pending_list = diff.pending_changes()
        if pending_list:
            lines.append("## ⏳ Pending Review")
            lines.append("")
            for c in pending_list:
                tag = " **[BREAKING]**" if c.breaking else ""
                lines.append(f"- {c.description}{tag}")
            lines.append("")

        return "\n".join(lines)

    def _render_change_group(self, changes: list[Change]) -> list[str]:
        lines: list[str] = []
        for ct in (ChangeType.ADDED, ChangeType.MODIFIED,
                   ChangeType.REMOVED, ChangeType.DEPRECATED):
            group = [c for c in changes if c.change_type == ct and not c.breaking]
            if not group:
                continue
            _, _, label = CHANGE_TYPE_LABELS[ct]
            lines.append(f"### {label}")
            lines.append("")
            for c in group:
                impact = f" `[{c.impact.value.upper()}]`" if c.impact != ImpactLevel.NONE else ""
                lines.append(f"- {c.description}{impact}")
                for fc in c.field_changes:
                    detail = f"  - `{fc.field_name}`"
                    if fc.property_changed:
                        detail += f" ({fc.property_changed})"
                    if fc.old_value is not None and fc.new_value is not None:
                        detail += f": `{fc.old_value}` → `{fc.new_value}`"
                    elif fc.new_value is not None:
                        detail += f": `{fc.new_value}`"
                    elif fc.old_value is not None:
                        detail += f": `{fc.old_value}`"
                    lines.append(detail)
                for note in c.notes:
                    lines.append(f"  - _{note}_")
                if c.migration_guide:
                    lines.append(f"  - **Migration:** {c.migration_guide}")
            lines.append("")
        return lines

    # ---------- Release Markdown ----------

    def render_release(self, entry: ChangelogEntry, release_info: ReleaseInfo) -> str:
        """Render a full release changelog as Markdown."""
        lines: list[str] = []
        date_str = release_info.release_date.isoformat()
        lines.append(f"# {release_info.version}")
        lines.append("")
        lines.append(f"_Released on {date_str}_")
        lines.append("")

        if release_info.highlights:
            lines.append("## ✨ Highlights")
            lines.append("")
            for h in release_info.highlights:
                lines.append(f"- {h}")
            lines.append("")

        breaking = [c for c in entry.changes if c.breaking]
        if breaking:
            lines.append("## ⚠ Breaking Changes")
            lines.append("")
            for c in breaking:
                lines.append(f"### {c.description}")
                lines.append("")
                if c.field_changes:
                    lines.append("| Field | Change | Old | New |")
                    lines.append("|-------|--------|-----|-----|")
                    for fc in c.field_changes:
                        old_v = str(fc.old_value).replace("|", "\\|") if fc.old_value else "-"
                        new_v = str(fc.new_value).replace("|", "\\|") if fc.new_value else "-"
                        lines.append(f"| {fc.field_name} | {fc.change_type.value} | {old_v} | {new_v} |")
                    lines.append("")
                if c.migration_guide:
                    lines.append(f"**Migration guide:** {c.migration_guide}")
                    lines.append("")
                for note in c.notes:
                    lines.append(f"> {note}")
                    lines.append("")

        by_module = {}
        for c in entry.changes:
            by_module.setdefault(c.module, []).append(c)

        for mod in sorted(by_module.keys()):
            lines.append(f"## {mod}")
            lines.append("")
            lines.extend(self._render_change_group(by_module[mod]))

        if entry.notes:
            lines.append("---")
            lines.append("")
            lines.append("## Notes")
            lines.append("")
            for n in entry.notes:
                lines.append(f"- {n}")
            lines.append("")

        return "\n".join(lines)

    def render_pending_items(self, diff: VersionDiff,
                              new_spec: Optional[ApiSpec] = None) -> str:
        """Render pending review items as a Markdown checklist."""
        lines: list[str] = []
        lines.append("# Pending Review Checklist")
        lines.append("")
        lines.append(f"_Version: {diff.new_version}_")
        lines.append("")

        pending = diff.pending_changes()
        if pending:
            lines.append("## Changes requiring confirmation")
            lines.append("")
            for c in pending:
                tag = " **[BREAKING]**" if c.breaking else ""
                lines.append(f"- [ ] {c.description}{tag}")
                if c.breaking and not c.migration_guide:
                    lines.append(f"  - [ ] Add migration guide")
            lines.append("")

        if new_spec:
            missing = diff.missing_examples(new_spec)
            if missing:
                lines.append("## Endpoints missing examples")
                lines.append("")
                for ep in missing:
                    lines.append(f"- [ ] `{ep.key}`")
                lines.append("")

        return "\n".join(lines)
