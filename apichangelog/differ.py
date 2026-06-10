"""
Diff engine for comparing two API specs and detecting changes.
Handles endpoint additions, deletions, modifications, and field-level changes.
"""

from .models import (
    ApiSpec, EndpointDef, FieldDef, ParameterDef, RequestDef,
    ResponseDef, Change, ChangeType, ImpactLevel, ChangeScope,
    FieldChange, VersionDiff
)


class Differ:
    """Compares two API specs and produces a VersionDiff."""

    def compare(self, old_spec: ApiSpec, new_spec: ApiSpec) -> VersionDiff:
        """Compare two API specs and return all changes."""
        diff = VersionDiff(old_version=old_spec.version, new_version=new_spec.version)

        old_eps = old_spec.endpoint_map()
        new_eps = new_spec.endpoint_map()

        all_keys = set(old_eps.keys()) | set(new_eps.keys())

        for key in sorted(all_keys):
            old_ep = old_eps.get(key)
            new_ep = new_eps.get(key)

            if old_ep is None and new_ep is not None:
                diff.changes.extend(self._added_endpoint(new_ep))
            elif old_ep is not None and new_ep is None:
                diff.changes.extend(self._removed_endpoint(old_ep))
            else:
                diff.changes.extend(self._modified_endpoint(old_ep, new_ep))

        self._assign_impact(diff)
        return diff

    # ---------- Endpoint-level changes ----------

    def _added_endpoint(self, ep: EndpointDef) -> list[Change]:
        changes = []
        changes.append(Change(
            change_type=ChangeType.ADDED,
            scope=ChangeScope.ENDPOINT,
            endpoint_key=ep.key,
            module=ep.module,
            description=f"New endpoint added: {ep.method} {ep.path}",
            impact=ImpactLevel.LOW,
            breaking=False,
        ))
        return changes

    def _removed_endpoint(self, ep: EndpointDef) -> list[Change]:
        changes = []
        changes.append(Change(
            change_type=ChangeType.REMOVED,
            scope=ChangeScope.ENDPOINT,
            endpoint_key=ep.key,
            module=ep.module,
            description=f"Endpoint removed: {ep.method} {ep.path}",
            impact=ImpactLevel.BREAKING,
            breaking=True,
        ))
        return changes

    def _modified_endpoint(self, old: EndpointDef, new: EndpointDef) -> list[Change]:
        changes: list[Change] = []

        if old.deprecated != new.deprecated and new.deprecated:
            changes.append(Change(
                change_type=ChangeType.DEPRECATED,
                scope=ChangeScope.ENDPOINT,
                endpoint_key=new.key,
                module=new.module,
                description=f"Endpoint deprecated: {new.method} {new.path}",
                impact=ImpactLevel.MEDIUM,
                breaking=False,
            ))

        if old.summary != new.summary or old.description != new.description:
            field_changes = []
            if old.summary != new.summary:
                field_changes.append(FieldChange(
                    field_name="summary",
                    change_type=ChangeType.MODIFIED,
                    old_value=old.summary,
                    new_value=new.summary,
                    property_changed="summary",
                ))
            if old.description != new.description:
                field_changes.append(FieldChange(
                    field_name="description",
                    change_type=ChangeType.MODIFIED,
                    old_value=old.description,
                    new_value=new.description,
                    property_changed="description",
                ))
            if field_changes:
                changes.append(Change(
                    change_type=ChangeType.MODIFIED,
                    scope=ChangeScope.ENDPOINT,
                    endpoint_key=new.key,
                    module=new.module,
                    description=f"Endpoint metadata updated: {new.method} {new.path}",
                    field_changes=field_changes,
                    impact=ImpactLevel.LOW,
                    breaking=False,
                ))

        changes.extend(self._compare_parameters(old, new))
        changes.extend(self._compare_request(old, new))
        changes.extend(self._compare_responses(old, new))

        return changes

    # ---------- Parameter comparison ----------

    def _compare_parameters(self, old: EndpointDef, new: EndpointDef) -> list[Change]:
        changes: list[Change] = []
        old_params = {f"{p.location}:{p.name}": p for p in old.parameters}
        new_params = {f"{p.location}:{p.name}": p for p in new.parameters}

        all_keys = set(old_params.keys()) | set(new_params.keys())

        for key in sorted(all_keys):
            old_p = old_params.get(key)
            new_p = new_params.get(key)

            if old_p is None and new_p is not None:
                changes.append(Change(
                    change_type=ChangeType.ADDED,
                    scope=ChangeScope.PARAMETER,
                    endpoint_key=new.key,
                    module=new.module,
                    description=f"New {new_p.location} parameter: {new_p.name}"
                                + (" (required)" if new_p.required else ""),
                    field_changes=[FieldChange(
                        field_name=new_p.name,
                        change_type=ChangeType.ADDED,
                        new_value=new_p.type,
                    )],
                    impact=ImpactLevel.HIGH if new_p.required else ImpactLevel.LOW,
                    breaking=new_p.required,
                ))
            elif old_p is not None and new_p is None:
                changes.append(Change(
                    change_type=ChangeType.REMOVED,
                    scope=ChangeScope.PARAMETER,
                    endpoint_key=new.key,
                    module=new.module,
                    description=f"Removed {old_p.location} parameter: {old_p.name}",
                    field_changes=[FieldChange(
                        field_name=old_p.name,
                        change_type=ChangeType.REMOVED,
                        old_value=old_p.type,
                    )],
                    impact=ImpactLevel.BREAKING if old_p.required else ImpactLevel.MEDIUM,
                    breaking=True,
                ))
            else:
                changes.extend(self._compare_single_parameter(old_p, new_p, new))

        return changes

    def _compare_single_parameter(self, old: ParameterDef, new: ParameterDef,
                                   ep: EndpointDef) -> list[Change]:
        changes: list[Change] = []
        field_changes: list[FieldChange] = []

        if old.type != new.type:
            field_changes.append(FieldChange(
                field_name=new.name,
                change_type=ChangeType.MODIFIED,
                old_value=old.type,
                new_value=new.type,
                property_changed="type",
            ))
        if old.required != new.required:
            field_changes.append(FieldChange(
                field_name=new.name,
                change_type=ChangeType.MODIFIED,
                old_value=old.required,
                new_value=new.required,
                property_changed="required",
            ))
        if old.default != new.default:
            field_changes.append(FieldChange(
                field_name=new.name,
                change_type=ChangeType.MODIFIED,
                old_value=old.default,
                new_value=new.default,
                property_changed="default",
            ))

        if field_changes:
            breaking = any(fc.property_changed in ("type", "required")
                           and (fc.property_changed == "required" and new.required)
                           or (fc.property_changed == "type")
                           for fc in field_changes)
            changes.append(Change(
                change_type=ChangeType.MODIFIED,
                scope=ChangeScope.PARAMETER,
                endpoint_key=ep.key,
                module=ep.module,
                description=f"Parameter {new.location}:{new.name} modified",
                field_changes=field_changes,
                impact=ImpactLevel.HIGH if breaking else ImpactLevel.LOW,
                breaking=breaking,
            ))

        return changes

    # ---------- Request body comparison ----------

    def _compare_request(self, old: EndpointDef, new: EndpointDef) -> list[Change]:
        changes: list[Change] = []

        if old.request is None and new.request is not None:
            changes.append(Change(
                change_type=ChangeType.ADDED,
                scope=ChangeScope.RESPONSE,
                endpoint_key=new.key,
                module=new.module,
                description=f"Request body added for {new.method} {new.path}",
                impact=ImpactLevel.MEDIUM,
                breaking=False,
            ))
        elif old.request is not None and new.request is None:
            changes.append(Change(
                change_type=ChangeType.REMOVED,
                scope=ChangeScope.RESPONSE,
                endpoint_key=new.key,
                module=new.module,
                description=f"Request body removed for {new.method} {new.path}",
                impact=ImpactLevel.BREAKING,
                breaking=True,
            ))
        elif old.request is not None and new.request is not None:
            changes.extend(self._compare_fields(
                old.request.fields, new.request.fields,
                ChangeScope.FIELD, new, "Request"
            ))

        return changes

    # ---------- Response comparison ----------

    def _compare_responses(self, old: EndpointDef, new: EndpointDef) -> list[Change]:
        changes: list[Change] = []

        old_resp = {r.status_code: r for r in old.responses}
        new_resp = {r.status_code: r for r in new.responses}

        all_codes = set(old_resp.keys()) | set(new_resp.keys())

        for code in sorted(all_codes):
            old_r = old_resp.get(code)
            new_r = new_resp.get(code)

            if old_r is None and new_r is not None:
                changes.append(Change(
                    change_type=ChangeType.ADDED,
                    scope=ChangeScope.RESPONSE,
                    endpoint_key=new.key,
                    module=new.module,
                    description=f"New response {code} for {new.method} {new.path}",
                    impact=ImpactLevel.LOW,
                    breaking=False,
                ))
            elif old_r is not None and new_r is None:
                changes.append(Change(
                    change_type=ChangeType.REMOVED,
                    scope=ChangeScope.RESPONSE,
                    endpoint_key=new.key,
                    module=new.module,
                    description=f"Removed response {code} for {new.method} {new.path}",
                    impact=ImpactLevel.HIGH,
                    breaking=True,
                ))
            else:
                changes.extend(self._compare_fields(
                    old_r.fields, new_r.fields,
                    ChangeScope.FIELD, new, f"Response {code}"
                ))

        return changes

    # ---------- Field-level comparison ----------

    def _compare_fields(self, old_fields: list[FieldDef], new_fields: list[FieldDef],
                        scope: ChangeScope, ep: EndpointDef, context: str) -> list[Change]:
        changes: list[Change] = []
        old_map = {f.name: f for f in old_fields}
        new_map = {f.name: f for f in new_fields}

        all_names = set(old_map.keys()) | set(new_map.keys())

        added_fields: list[FieldChange] = []
        removed_fields: list[FieldChange] = []
        modified_fields: list[FieldChange] = []

        for name in sorted(all_names):
            old_f = old_map.get(name)
            new_f = new_map.get(name)

            if old_f is None and new_f is not None:
                added_fields.append(FieldChange(
                    field_name=name,
                    change_type=ChangeType.ADDED,
                    new_value=new_f.type + (" (required)" if new_f.required else ""),
                ))
            elif old_f is not None and new_f is None:
                removed_fields.append(FieldChange(
                    field_name=name,
                    change_type=ChangeType.REMOVED,
                    old_value=old_f.type + (" (required)" if old_f.required else ""),
                ))
            else:
                modified_fields.extend(self._compare_single_field(old_f, new_f))

        if added_fields:
            breaking = any("required" in str(fc.new_value) for fc in added_fields)
            changes.append(Change(
                change_type=ChangeType.ADDED,
                scope=scope,
                endpoint_key=ep.key,
                module=ep.module,
                description=f"{context} fields added: {', '.join(fc.field_name for fc in added_fields)}",
                field_changes=added_fields,
                impact=ImpactLevel.HIGH if breaking else ImpactLevel.LOW,
                breaking=breaking,
            ))

        if removed_fields:
            breaking = any("required" in str(fc.old_value) for fc in removed_fields)
            changes.append(Change(
                change_type=ChangeType.REMOVED,
                scope=scope,
                endpoint_key=ep.key,
                module=ep.module,
                description=f"{context} fields removed: {', '.join(fc.field_name for fc in removed_fields)}",
                field_changes=removed_fields,
                impact=ImpactLevel.BREAKING if breaking else ImpactLevel.HIGH,
                breaking=True,
            ))

        if modified_fields:
            breaking = any(
                fc.property_changed in ("type", "required")
                and (fc.property_changed == "required" and fc.new_value is True)
                or fc.property_changed == "type"
                for fc in modified_fields
            )
            changes.append(Change(
                change_type=ChangeType.MODIFIED,
                scope=scope,
                endpoint_key=ep.key,
                module=ep.module,
                description=f"{context} fields modified: {', '.join(sorted({fc.field_name for fc in modified_fields}))}",
                field_changes=modified_fields,
                impact=ImpactLevel.HIGH if breaking else ImpactLevel.LOW,
                breaking=breaking,
            ))

        return changes

    def _compare_single_field(self, old: FieldDef, new: FieldDef) -> list[FieldChange]:
        changes: list[FieldChange] = []

        if old.type != new.type:
            changes.append(FieldChange(
                field_name=new.name,
                change_type=ChangeType.MODIFIED,
                old_value=old.type,
                new_value=new.type,
                property_changed="type",
            ))
        if old.required != new.required:
            changes.append(FieldChange(
                field_name=new.name,
                change_type=ChangeType.MODIFIED,
                old_value=old.required,
                new_value=new.required,
                property_changed="required",
            ))
        if old.description != new.description:
            changes.append(FieldChange(
                field_name=new.name,
                change_type=ChangeType.MODIFIED,
                old_value=old.description,
                new_value=new.description,
                property_changed="description",
            ))
        if old.default != new.default:
            changes.append(FieldChange(
                field_name=new.name,
                change_type=ChangeType.MODIFIED,
                old_value=old.default,
                new_value=new.default,
                property_changed="default",
            ))
        if old.enum != new.enum:
            changes.append(FieldChange(
                field_name=new.name,
                change_type=ChangeType.MODIFIED,
                old_value=str(old.enum),
                new_value=str(new.enum),
                property_changed="enum",
            ))

        return changes

    # ---------- Impact assignment ----------

    def _assign_impact(self, diff: VersionDiff) -> None:
        """Ensure all changes have appropriate impact and breaking flags.

        Already assigned during detection; this is a safety net and could be
        extended with custom rules in the future.
        """
        for c in diff.changes:
            if c.breaking and c.impact == ImpactLevel.NONE:
                c.impact = ImpactLevel.BREAKING
            if not c.breaking and c.impact == ImpactLevel.BREAKING:
                c.breaking = True
