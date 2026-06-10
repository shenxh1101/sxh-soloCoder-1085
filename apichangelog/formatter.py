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
    VersionDiff, ChangelogEntry, ReleaseInfo, ReleaseStatus
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
        self.console = Console(legacy_windows=False, highlight=False)

    # ---------- Scan output ----------

    def print_spec_summary(self, spec: ApiSpec) -> None:
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
        total = len(diff.changes)
        breaking = len(diff.breaking_changes())
        pending = len(diff.pending_changes())

        header = Panel.fit(
            Text.from_markup(
                f"[bold cyan]{diff.old_version}[/bold cyan] -> "
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
                        "\n".join(f"  - [red]{ep.key}[/red]" for ep in missing),
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
                        f"  - [yellow]{c.description}[/yellow]"
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
                    detail += f": [red]{fc.old_value}[/red] -> [green]{fc.new_value}[/green]"
                elif fc.new_value is not None:
                    detail += f": [green]{fc.new_value}[/green]"
                elif fc.old_value is not None:
                    detail += f": [red]{fc.old_value}[/red]"
                branch.add(detail)

        if change.notes:
            for note in change.notes:
                branch.add(f"[cyan][NOTE] {note}[/cyan]")
        if change.migration_guide:
            branch.add(f"[blue]-> Migration: {change.migration_guide}[/blue]")
        if not change.confirmed:
            branch.add("[yellow][PENDING] Pending confirmation[/yellow]")

    # ---------- Release output ----------

    def print_release_preview(self, entry: ChangelogEntry, release_info: ReleaseInfo,
                               filtered_changes: Optional[list[Change]] = None) -> None:
        changes = filtered_changes if filtered_changes is not None else entry.changes
        date_str = release_info.release_date.isoformat()
        status_label = ("[bold green]PUBLISHED[/bold green]"
                        if entry.status == ReleaseStatus.PUBLISHED
                        else "[yellow]DRAFT[/yellow]")

        meta_parts = [
            f"[bold cyan]{entry.spec_name} {release_info.version}[/bold cyan]",
            f"{status_label}",
            f"[dim]Release date:[/dim] [bold]{date_str}[/bold]",
            f"[dim]Modules:[/dim] [bold]{', '.join(release_info.modules)}[/bold]",
            f"[dim]Total changes:[/dim] [bold]{len(changes)}[/bold]",
        ]
        if entry.released_by:
            meta_parts.append(f"[dim]Released by:[/dim] {entry.released_by}")
        if entry.release_channel:
            meta_parts.append(f"[dim]Channel:[/dim] [magenta]{entry.release_channel}[/magenta]")
        if entry.release_template:
            meta_parts.append(f"[dim]Template:[/dim] [blue]{entry.release_template}[/blue]")
        if entry.markdown_path:
            meta_parts.append(f"[dim]Markdown:[/dim] [blue]{entry.markdown_path}[/blue]")
        if entry.diff_from_version:
            meta_parts.append(f"[dim]Diff from:[/dim] {entry.diff_from_version}")

        header = Panel.fit(
            Text.from_markup("\n".join(meta_parts)),
            title="Release Notes Preview",
            border_style=("green" if entry.status == ReleaseStatus.PUBLISHED else "yellow"),
        )
        self.console.print(header)

        if release_info.highlights:
            highlights = Tree("[bold yellow][*] Highlights[/bold yellow]")
            for h in release_info.highlights:
                highlights.add(h)
            self.console.print(highlights)
            self.console.print()

        breaking = [c for c in changes if c.breaking]
        if breaking:
            self.console.print("[bold red][!] BREAKING CHANGES[/bold red]")
            for c in breaking:
                self.console.print(f"  - {c.description}")
                if c.migration_guide:
                    self.console.print(f"    [blue]-> {c.migration_guide}[/blue]")
            self.console.print()

        by_module: dict[str, list[Change]] = {}
        for c in changes:
            by_module.setdefault(c.module, []).append(c)
        for mod in sorted(by_module.keys()):
            self.console.print(f"[bold blue]### {mod}[/bold blue]")
            for change_type in (ChangeType.ADDED, ChangeType.MODIFIED,
                                ChangeType.REMOVED, ChangeType.DEPRECATED):
                group = [c for c in by_module[mod] if c.change_type == change_type]
                if not group:
                    continue
                _, _, label = CHANGE_TYPE_LABELS[change_type]
                self.console.print(f"  **{label}**")
                for c in group:
                    if c.breaking:
                        continue
                    self.console.print(f"    - {c.description}")
                    for note in c.notes:
                        self.console.print(f"      [dim]_{note}_[/dim]")
            self.console.print()

    # ---------- Versions output ----------

    def print_versions(self, specs: list[tuple[str, str]],
                        entry_map: dict[tuple[str, str], ChangelogEntry]) -> None:
        table = Table(title="Saved API Specs & Changelogs", show_lines=True)
        table.add_column("Service", style="cyan bold")
        table.add_column("Version", style="green")
        table.add_column("Status", style="magenta")
        table.add_column("Release Date", style="yellow")
        table.add_column("By", style="blue")
        table.add_column("Channel", style="magenta")
        table.add_column("Template", style="blue")
        table.add_column("Changes", justify="right")
        table.add_column("Pending", justify="right", style="red")
        table.add_column("Markdown", style="cyan")

        if not specs:
            self.console.print("[dim]No saved specs found. Run 'scan --save' first.[/dim]")
            return

        for name, version in sorted(specs, key=lambda x: (x[0], x[1]), reverse=True):
            entry = entry_map.get((name, version))
            if entry:
                if entry.status == ReleaseStatus.PUBLISHED:
                    status = "[green]PUBLISHED[/green]"
                else:
                    status = "[yellow]DRAFT[/yellow]"
                rel_date = entry.release_date.isoformat() if entry.release_date else "-"
                by = entry.released_by or "-"
                channel = entry.release_channel or "-"
                template = entry.release_template or "-"
                n_changes = len(entry.changes)
                n_pending = entry.pending_count
                md_path = entry.markdown_path or "-"
            else:
                status = "[dim]SCANNED[/dim]"
                rel_date = "-"
                by = "-"
                channel = "-"
                template = "-"
                n_changes = 0
                n_pending = 0
                md_path = "-"
            table.add_row(name, version, status, rel_date, by, channel, template,
                          str(n_changes), str(n_pending), md_path)

        self.console.print(table)

    # ---------- Workspace / Services output ----------

    def print_workspace(self, summary: dict[str, dict]) -> None:
        if not summary:
            self.console.print("[dim]No services in workspace yet. Run 'scan --save' to add one.[/dim]")
            return

        self.console.print(Panel(
            Text.from_markup(f"[bold cyan]{len(summary)}[/bold cyan] services tracked"),
            title="Workspace Overview",
            border_style="cyan",
        ))
        self.console.print()

        for name in sorted(summary.keys()):
            data = summary[name]
            versions = data["versions"]
            entries = data["entries"]

            latest_version = versions[0][0] if versions else "?"
            latest_entry = entries[0] if entries else None
            total_pending = sum(e.pending_count for e in entries)
            total_no_example = sum(v[2] for v in versions)
            total_endpoints = sum(v[1] for v in versions)

            service_owner = ""
            if latest_entry and latest_entry.owner:
                service_owner = latest_entry.owner

            if latest_entry:
                if latest_entry.status == ReleaseStatus.PUBLISHED:
                    latest_status = "[green]PUBLISHED[/green]"
                    last_release = latest_entry.release_date.isoformat() if latest_entry.release_date else "-"
                else:
                    latest_status = "[yellow]DRAFT[/yellow]"
                    last_release = latest_entry.release_date.isoformat() if latest_entry.release_date else "Not set"
                diff_from = latest_entry.diff_from_version or "(manual)"
                last_diff = f"{diff_from} -> {latest_entry.version}"
            else:
                latest_status = "[dim]NO DIFF[/dim]"
                last_release = "-"
                last_diff = "-"

            owner_str = f"  [dim]owner:[/dim] [blue]{service_owner}[/blue]" if service_owner else ""
            tree = Tree(
                f"[bold cyan]{name}[/bold cyan]  "
                f"[dim]latest:[/dim] [green]{latest_version}[/green] {latest_status}  "
                f"[dim]last release:[/dim] {last_release}"
                + owner_str
            )

            tree.add(
                f"[dim]Versions tracked:[/dim] {len(versions)}  |  "
                f"[dim]Total endpoints:[/dim] {total_endpoints}  |  "
                f"[dim]Missing examples:[/dim] [red]{total_no_example}[/red]  |  "
                f"[dim]Pending review items:[/dim] [yellow]{total_pending}[/yellow]"
            )
            tree.add(
                f"[dim]Last diff:[/dim] {last_diff}  "
                f"([dim]changelogs:[/dim] {len(entries)})"
            )

            version_branch = tree.add("[bold]Version timeline[/bold]")
            for ver, eps, noex in versions:
                entry_for_ver = next((e for e in entries if e.version == ver), None)
                tags: list[str] = []
                if entry_for_ver:
                    if entry_for_ver.status == ReleaseStatus.PUBLISHED:
                        tags.append("[green]PUBLISHED[/green]")
                    else:
                        tags.append("[yellow]DRAFT[/yellow]")
                    if entry_for_ver.changes:
                        tags.append(f"[dim]{len(entry_for_ver.changes)} changes[/dim]")
                    if entry_for_ver.pending_count:
                        tags.append(f"[red]{entry_for_ver.pending_count} pending[/red]")
                    if entry_for_ver.release_channel:
                        tags.append(f"[magenta]{entry_for_ver.release_channel}[/magenta]")
                tag_str = "  ".join(tags)
                version_branch.add(
                    f"[bold]{ver}[/bold]  [dim]{eps} eps, {noex} no-ex[/dim]  "
                    + (tag_str if tag_str else "[dim]scanned only[/dim]")
                )

            self.console.print(tree)
            self.console.print()

    # ---------- Review output ----------

    def print_review_list(self, entry: ChangelogEntry,
                           changes: list[Change]) -> None:
        pending = [c for c in changes if c.is_pending()]
        confirmed = [c for c in changes if not c.is_pending()]

        status_label = ("[bold green]PUBLISHED[/bold green]"
                        if entry.status == ReleaseStatus.PUBLISHED
                        else "[yellow]DRAFT[/yellow]")
        header = Panel.fit(
            Text.from_markup(
                f"[bold]{entry.spec_name} {entry.version}[/bold]  {status_label}\n"
                f"[dim]Total:[/dim] {len(changes)}  "
                f"[green]Confirmed:[/green] {len(confirmed)}  "
                f"[red]Pending:[/red] {len(pending)}"
            ),
            title="Review Status",
            border_style="yellow" if pending else "green",
        )
        self.console.print(header)

        if pending:
            self.console.print()
            self.console.print("[bold red]Unconfirmed Changes[/bold red]")
            for i, c in enumerate(changes):
                if not c.is_pending():
                    continue
                tag = " [bold red][BREAKING][/bold red]" if c.breaking else ""
                impact_color = IMPACT_COLORS[c.impact]
                status_parts = [
                    f"  [{i}] ",
                    f"[{impact_color}]{c.impact.value.upper()}[/{impact_color}] ",
                    c.description,
                    tag,
                ]
                self.console.print("".join(status_parts))
                if c.breaking and not c.migration_guide:
                    self.console.print("      [dim]-> needs migration guide[/dim]")

        if confirmed:
            self.console.print()
            self.console.print("[bold green]Confirmed Changes[/bold green]")
            for i, c in enumerate(changes):
                if c.is_pending():
                    continue
                self.console.print(f"  [{i}] [dim]{c.description}[/dim]")

        spec_name = getattr(entry, "spec_name", "")
        if spec_name:
            spec = None
            try:
                from .storage import Storage
                import os
                s = Storage()
                spec = s.load_stored_spec(spec_name, entry.version)
            except Exception:
                pass
            if spec:
                no_examples = [ep for ep in spec.endpoints if not ep.has_examples()]
                if no_examples:
                    self.console.print()
                    self.console.print(
                        f"[bold yellow]Missing Examples ({len(no_examples)} endpoints)[/bold yellow]"
                    )
                    for ep in no_examples:
                        self.console.print(f"  - [red]{ep.key}[/red]")

    # ---------- Approval output ----------

    def print_approval(self, entry: ChangelogEntry,
                       approval_by_module: dict[str, dict],
                       by_owner: bool = False) -> None:
        """Print per-module or per-owner approval status for a release candidate."""
        total_changes = len(entry.changes)
        total_pending = entry.pending_count
        breaking_no_mig = sum(
            len(m["breaking_no_migration"]) for m in approval_by_module.values()
        )
        total_unconfirmed = sum(
            len(m["unconfirmed"]) for m in approval_by_module.values()
        )
        ready = (total_pending == 0)

        header_parts = [
            f"[bold cyan]{entry.spec_name} {entry.version}[/bold cyan]  "
            f"{'[bold green]READY TO PUBLISH[/bold green]' if ready else '[bold red]NOT READY[/bold red]'}"
        ]
        if entry.owner:
            header_parts.append(f"[dim]Service owner:[/dim] {entry.owner}")
        header_parts.append(
            f"[dim]Total changes:[/dim] {total_changes}  "
            f"[dim]Confirmed:[/dim] [green]{total_changes - total_unconfirmed}[/green]  "
            f"[dim]Unconfirmed:[/dim] [yellow]{total_unconfirmed}[/yellow]"
        )
        header_parts.append(
            f"[dim]Breaking without migration:[/dim] [red]{breaking_no_mig}[/red]  "
            f"[dim]Pending total:[/dim] [red]{total_pending}[/red]"
        )
        header = Panel.fit(
            Text.from_markup("\n".join(header_parts)),
            title="Approval Checklist",
            border_style=("green" if ready else "red"),
        )
        self.console.print(header)

        if not approval_by_module:
            self.console.print("[dim]No changelog data. Run diff --save first.[/dim]")
            return

        self.console.print()
        if by_owner:
            # Build per-owner aggregation from approval_by_module
            by_owner_data: dict[str, dict] = {}
            module_owners = getattr(entry, "module_owners", {})
            spec_owner = getattr(entry, "owner", "")
            for mod, data in approval_by_module.items():
                for c in data["unconfirmed"]:
                    owner = (c.assignee or module_owners.get(mod, spec_owner) or "(unassigned)")
                    by_owner_data.setdefault(owner, {"unconfirmed": [], "breaking_no_migration": [], "total": 0})
                    by_owner_data[owner]["unconfirmed"].append(c)
                    by_owner_data[owner]["total"] += 1
                for c in data["breaking_no_migration"]:
                    owner = (c.assignee or module_owners.get(mod, spec_owner) or "(unassigned)")
                    by_owner_data.setdefault(owner, {"unconfirmed": [], "breaking_no_migration": [], "total": 0})
                    by_owner_data[owner]["breaking_no_migration"].append(c)

            for owner in sorted(by_owner_data.keys()):
                data = by_owner_data[owner]
                owner_ready = (len(data["unconfirmed"]) == 0 and len(data["breaking_no_migration"]) == 0)
                badge = ("[green][OK][/green]" if owner_ready else "[red][!][/red]")
                tree = Tree(
                    f"{badge} [bold blue]@{owner}[/bold blue]  "
                    f"[dim]total: {data['total']}[/dim]  "
                    f"[yellow]{len(data['unconfirmed'])} unconfirmed[/yellow]  "
                    f"[red]{len(data['breaking_no_migration'])} breaking-no-mig[/red]"
                )
                for c in data["unconfirmed"]:
                    tree.add(f"[yellow][-] [{c.module}] {c.description}[/yellow]")
                for c in data["breaking_no_migration"]:
                    tree.add(f"[red][!] [{c.module}] {c.description}[/red]")
                self.console.print(tree)
                self.console.print()
        else:
            for mod in sorted(approval_by_module.keys()):
                data = approval_by_module[mod]
                mod_ready = (
                    len(data["unconfirmed"]) == 0
                    and len(data["breaking_no_migration"]) == 0
                )
                badge = ("[green][OK][/green]" if mod_ready else "[red][!][/red]")
                owner_tag = ""
                module_owners = getattr(entry, "module_owners", {})
                if mod in module_owners:
                    owner_tag = f" [dim](@{module_owners[mod]})[/dim]"
                tree = Tree(
                    f"{badge} [bold blue]{mod}[/bold blue]{owner_tag}  "
                    f"[dim]{data['total']} changes[/dim]  "
                    f"[yellow]{len(data['unconfirmed'])} unconfirmed[/yellow]  "
                    f"[red]{len(data['breaking_no_migration'])} breaking-no-mig[/red]"
                )
                for c in data["unconfirmed"]:
                    tag = f" [dim](@{c.assignee})[/dim]" if c.assignee else ""
                    tree.add(f"[yellow][-] {c.description}[/yellow]{tag}")
                for c in data["breaking_no_migration"]:
                    tag = f" [dim](@{c.assignee})[/dim]" if c.assignee else ""
                    tree.add(f"[red][!] {c.description}[/red]{tag}")
                self.console.print(tree)
                self.console.print()

    # ---------- Health check output ----------

    def print_health_check(self, health: dict) -> None:
        """Print workspace health check report."""
        stale_services = health["stale_services"]
        missing = health["missing_examples_ranking"]
        stale_drafts = health["stale_drafts"]
        pending_rank = health["pending_ranking"]

        issues = len(stale_services) + len(missing) + len(stale_drafts)
        header = Panel.fit(
            Text.from_markup(
                f"[bold cyan]{issues}[/bold cyan] issues detected\n"
                f"[dim]Stale services:[/dim] {len(stale_services)}  "
                f"[dim]Modules missing examples:[/dim] {len(missing)}  "
                f"[dim]Stale drafts:[/dim] {len(stale_drafts)}"
            ),
            title="Workspace Health Check",
            border_style=("red" if issues else "green"),
        )
        self.console.print(header)

        if stale_services:
            self.console.print()
            self.console.print("[bold red]Stale services (no diff/changelog saved yet)[/bold red]")
            for name in stale_services:
                self.console.print(f"  - [yellow]{name}[/yellow]")

        if missing:
            self.console.print()
            self.console.print("[bold yellow]Modules missing examples (worst first)[/bold yellow]")
            table = Table(show_header=True, show_lines=False)
            table.add_column("Service", style="cyan")
            table.add_column("Module", style="blue")
            table.add_column("Missing Examples", style="red", justify="right")
            for name, mod, cnt in missing:
                table.add_row(name, mod, str(cnt))
            self.console.print(table)

        if stale_drafts:
            self.console.print()
            self.console.print("[bold yellow]Stale drafts (need publishing)[/bold yellow]")
            for e in stale_drafts:
                self.console.print(
                    f"  - [yellow]{e.spec_name}:{e.version}[/yellow]  "
                    f"[dim]{len(e.changes)} changes, {e.pending_count} pending[/dim]"
                )

        if pending_rank:
            self.console.print()
            self.console.print("[bold blue]Services by pending review count[/bold blue]")
            for name, cnt in pending_rank:
                if cnt == 0:
                    continue
                self.console.print(f"  - [cyan]{name}[/cyan]: [red]{cnt}[/red] pending")

        if issues == 0:
            self.console.print()
            self.console.print("[green]All healthy - nothing to address.[/green]")

    # ---------- Release gate output ----------

    def print_release_gate(self, spec_name: str, version: str,
                            report: dict) -> None:
        """Print release gate check result with reasons and next steps."""
        passed: bool = report["passed"]
        channel: str = report["channel"]
        reasons: list[str] = report["reasons"]
        next_steps: list[str] = report["next_steps"]
        pending_by_owner: dict = report["pending_by_owner"]
        missing_mig_by_owner: dict = report["missing_migration_by_owner"]

        status_label = ("[bold green]PASS[/bold green]" if passed
                        else "[bold red]FAIL[/bold red]")
        header = Panel.fit(
            Text.from_markup(
                f"[bold cyan]{spec_name} {version}[/bold cyan]  {status_label}\n"
                f"[dim]Channel:[/dim] [magenta]{channel}[/magenta]  "
                f"[dim]Pending:[/dim] [yellow]{sum(len(v) for v in pending_by_owner.values())}[/yellow]  "
                f"[dim]No-mig breaking:[/dim] [red]{sum(len(v) for v in missing_mig_by_owner.values())}[/red]"
            ),
            title="Release Gate Check",
            border_style=("green" if passed else "red"),
        )
        self.console.print(header)

        if reasons:
            self.console.print()
            self.console.print("[bold yellow]Check results:[/bold yellow]")
            for r in reasons:
                self.console.print(f"  - {r}")

        if next_steps:
            self.console.print()
            self.console.print("[bold green]Next steps:[/bold green]")
            for s in next_steps:
                self.console.print(f"  > {s}")

        if pending_by_owner and not passed:
            self.console.print()
            self.console.print("[bold yellow]Pending items by owner:[/bold yellow]")
            for owner in sorted(pending_by_owner.keys()):
                items = pending_by_owner[owner]
                tree = Tree(
                    f"[bold blue]@{owner}[/bold blue]  "
                    f"[dim]{len(items)} pending[/dim]"
                )
                for c in items:
                    tag = " [red][BREAKING][/red]" if c.breaking else ""
                    tree.add(f"[yellow][{c.module}] {c.description}[/yellow]{tag}")
                self.console.print(tree)

        if missing_mig_by_owner and not passed:
            self.console.print()
            self.console.print("[bold red]Breaking changes missing migration guide:[/bold red]")
            for owner in sorted(missing_mig_by_owner.keys()):
                items = missing_mig_by_owner[owner]
                tree = Tree(
                    f"[bold blue]@{owner}[/bold blue]  "
                    f"[dim]{len(items)} missing guides[/dim]"
                )
                for c in items:
                    tree.add(f"[red][{c.module}] {c.description}[/red]")
                self.console.print(tree)

    # ---------- Import merge result output ----------

    def print_import_merge_result(self, result: dict) -> None:
        """Print incremental import merge summary."""
        merged = result["merged"]
        conflicts = result["conflicts"]
        imported_new = result["imported_new"]
        skipped = result["skipped_specs"]

        total = len(merged) + len(conflicts) + len(imported_new)
        header = Panel.fit(
            Text.from_markup(
                f"[dim]Entries processed:[/dim] {total}\n"
                f"[green]Merged (identical):[/green] {len(merged)}  "
                f"[yellow]Imported new:[/yellow] {len(imported_new)}  "
                f"[red]Conflicts (overwrote local):[/red] {len(conflicts)}  "
                f"[dim]Skipped specs:[/dim] {len(skipped)}"
            ),
            title="Workspace Import (Merge Mode)",
            border_style=("green" if not conflicts else "yellow"),
        )
        self.console.print(header)

        if imported_new:
            self.console.print()
            self.console.print("[green]New entries imported:[/green]")
            for sn, sv in imported_new:
                self.console.print(f"  - [cyan]{sn}:{sv}[/cyan]")

        if merged:
            self.console.print()
            self.console.print("[green]Identical entries (no change):[/green]")
            for sn, sv in merged:
                self.console.print(f"  - [cyan]{sn}:{sv}[/cyan]")

        if conflicts:
            self.console.print()
            self.console.print("[yellow][!] Conflicts detected - incoming version overwrote local:[/yellow]")
            for sn, sv in conflicts:
                self.console.print(
                    f"  - [red]{sn}:{sv}[/red]  "
                    f"[dim](run 'versions {sn}:{sv}' to inspect)[/dim]"
                )

        if skipped:
            self.console.print()
            self.console.print("[dim]Skipped spec files (parse errors):[/dim]")
            for name in skipped:
                self.console.print(f"  - {name}")


class MarkdownFormatter:
    """Generates Markdown format changelogs."""

    # ---------- Diff Markdown ----------

    def render_diff(self, diff: VersionDiff, new_spec: Optional[ApiSpec] = None) -> str:
        lines: list[str] = []
        lines.append(f"# API Diff: {diff.old_version} -> {diff.new_version}")
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
            lines.append("## BREAKING CHANGES")
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
                lines.append("## Missing Examples")
                lines.append("")
                for ep in missing:
                    lines.append(f"- `{ep.key}`")
                lines.append("")

        pending_list = diff.pending_changes()
        if pending_list:
            lines.append("## Pending Review")
            lines.append("")
            for c in pending_list:
                tag = " **[BREAKING]**" if c.breaking else ""
                lines.append(f"- {c.description}{tag}")
            lines.append("")

        return "\n".join(lines)

    def _render_change_group(self, changes: list[Change],
                              template: str = "default") -> list[str]:
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
                if template == "public" and c.impact == ImpactLevel.LOW:
                    continue
                impact = f" `[{c.impact.value.upper()}]`" if c.impact != ImpactLevel.NONE else ""
                lines.append(f"- {c.description}{impact}")
                for fc in c.field_changes:
                    detail = f"  - `{fc.field_name}`"
                    if fc.property_changed:
                        detail += f" ({fc.property_changed})"
                    if fc.old_value is not None and fc.new_value is not None:
                        detail += f": `{fc.old_value}` -> `{fc.new_value}`"
                    elif fc.new_value is not None:
                        detail += f": `{fc.new_value}`"
                    elif fc.old_value is not None:
                        detail += f": `{fc.old_value}`"
                    lines.append(detail)
                for note in c.notes:
                    if template == "internal":
                        lines.append(f"  - _{note}_")
                if c.migration_guide and template != "public":
                    lines.append(f"  - **Migration:** {c.migration_guide}")
            lines.append("")
        return lines

    # ---------- Release Markdown ----------

    def render_release(self, entry: ChangelogEntry, release_info: ReleaseInfo,
                        filtered_changes: Optional[list[Change]] = None,
                        template: str = "default") -> str:
        changes = filtered_changes if filtered_changes is not None else entry.changes
        lines: list[str] = []
        date_str = release_info.release_date.isoformat()
        lines.append(f"# {release_info.version}")
        lines.append("")

        if template == "beta":
            lines.append("> **BETA RELEASE** - This API is under active development and may change without notice.")
            lines.append("")
        elif template == "internal":
            lines.append(f"> **Internal Release** - Channel: {entry.release_channel or 'internal'}")
            if entry.released_by:
                lines.append(f"> Released by: {entry.released_by}")
            lines.append("")

        lines.append(f"_Released on {date_str}_")
        lines.append("")

        if release_info.highlights:
            lines.append("## Highlights")
            lines.append("")
            for h in release_info.highlights:
                lines.append(f"- {h}")
            lines.append("")

        breaking = [c for c in changes if c.breaking]
        if breaking:
            lines.append("## BREAKING CHANGES")
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
                if template == "internal":
                    for note in c.notes:
                        lines.append(f"> {note}")
                        lines.append("")

        by_module: dict[str, list[Change]] = {}
        for c in changes:
            by_module.setdefault(c.module, []).append(c)

        for mod in sorted(by_module.keys()):
            lines.append(f"## {mod}")
            lines.append("")
            lines.extend(self._render_change_group(by_module[mod], template))

        if template == "internal" and entry.notes:
            lines.append("---")
            lines.append("")
            lines.append("## Internal Notes")
            lines.append("")
            for n in entry.notes:
                lines.append(f"- {n}")
            lines.append("")

        if template == "internal":
            pending = [c for c in changes if c.is_pending()]
            if pending:
                lines.append("---")
                lines.append("")
                lines.append("## Pending Review")
                lines.append("")
                for c in pending:
                    tag = " **[BREAKING]**" if c.breaking else ""
                    lines.append(f"- [ ] {c.description}{tag}")
                lines.append("")

        return "\n".join(lines)

    def render_pending_items(self, diff: VersionDiff,
                              new_spec: Optional[ApiSpec] = None) -> str:
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
