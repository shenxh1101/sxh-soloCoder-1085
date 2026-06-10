"""
Storage and persistence module for API Changelog Tool.
Handles loading/saving API specs, changelog entries, and notes.
"""

import json
import os
from pathlib import Path
from typing import Any, Optional
from datetime import date, datetime

import yaml

from .models import (
    ApiSpec, EndpointDef, FieldDef, ParameterDef, RequestDef,
    ResponseDef, Change, ChangeType, ImpactLevel, ChangeScope,
    FieldChange, ChangelogEntry, ReleaseInfo, ReleaseStatus
)


DEFAULT_CHANGELOG_DIR = ".apichangelog"
DEFAULT_SPECS_DIR = "specs"
DEFAULT_CHANGELOG_FILE = "changelog.json"


class Storage:
    """Manages file-based storage for API specs and changelog data."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or os.getcwd())
        self.changelog_dir = self.base_dir / DEFAULT_CHANGELOG_DIR
        self.specs_dir = self.changelog_dir / DEFAULT_SPECS_DIR
        self.changelog_file = self.changelog_dir / DEFAULT_CHANGELOG_FILE
        self._ensure_dirs()

    def _ensure_dirs(self):
        self.changelog_dir.mkdir(parents=True, exist_ok=True)
        self.specs_dir.mkdir(parents=True, exist_ok=True)

    # ---------- API Spec Loading ----------

    def load_spec(self, file_path: str) -> ApiSpec:
        """Load an API spec from YAML or JSON file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Spec file not found: {file_path}")

        with open(path, "r", encoding="utf-8") as f:
            if path.suffix in (".yaml", ".yml"):
                data = yaml.safe_load(f)
            elif path.suffix == ".json":
                data = json.load(f)
            else:
                raise ValueError(f"Unsupported file format: {path.suffix}")

        return self._parse_spec(data, path.stem)

    def _parse_spec(self, data: dict, fallback_name: str) -> ApiSpec:
        if "openapi" in data:
            return self._parse_openapi(data)
        return self._parse_native(data, fallback_name)

    def _parse_native(self, data: dict, fallback_name: str) -> ApiSpec:
        spec = ApiSpec(
            name=data.get("name", fallback_name),
            version=data.get("version", "0.0.0"),
            base_url=data.get("base_url", ""),
            description=data.get("description", ""),
        )
        for ep_data in data.get("endpoints", []):
            spec.endpoints.append(self._parse_endpoint(ep_data))
        return spec

    def _parse_openapi(self, data: dict) -> ApiSpec:
        info = data.get("info", {})
        spec = ApiSpec(
            name=info.get("title", "API"),
            version=info.get("version", "0.0.0"),
            base_url=data.get("servers", [{}])[0].get("url", ""),
            description=info.get("description", ""),
        )
        paths = data.get("paths", {})
        components = data.get("components", {})
        schemas = components.get("schemas", {})

        for path, methods in paths.items():
            for method, op_data in methods.items():
                if method.upper() not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
                    continue
                ep = self._parse_openapi_operation(path, method, op_data, schemas)
                spec.endpoints.append(ep)
        return spec

    def _parse_openapi_operation(self, path: str, method: str,
                                  op_data: dict, schemas: dict) -> EndpointDef:
        tags = op_data.get("tags", [])
        ep = EndpointDef(
            path=path,
            method=method.upper(),
            module=tags[0] if tags else "default",
            summary=op_data.get("summary", ""),
            description=op_data.get("description", ""),
            deprecated=op_data.get("deprecated", False),
            tags=tags,
        )

        for param in op_data.get("parameters", []):
            schema_ref = param.get("schema", {})
            param_type = self._resolve_schema_type(schema_ref, schemas)
            ep.parameters.append(ParameterDef(
                name=param.get("name", ""),
                location=param.get("in", "query"),
                type=param_type,
                required=param.get("required", False),
                description=param.get("description", ""),
                example=param.get("example"),
            ))

        request_body = op_data.get("requestBody")
        if request_body:
            content = request_body.get("content", {})
            for ct, ct_data in content.items():
                req_schema = ct_data.get("schema", {})
                fields = self._parse_schema_fields(req_schema, schemas)
                ep.request = RequestDef(
                    content_type=ct,
                    fields=fields,
                    example=ct_data.get("example"),
                )
                break

        for status_code, resp_data in op_data.get("responses", {}).items():
            content = resp_data.get("content", {})
            if content:
                for ct, ct_data in content.items():
                    resp_schema = ct_data.get("schema", {})
                    fields = self._parse_schema_fields(resp_schema, schemas)
                    ep.responses.append(ResponseDef(
                        status_code=int(status_code) if status_code.isdigit() else 200,
                        content_type=ct,
                        fields=fields,
                        example=ct_data.get("example"),
                        description=resp_data.get("description", ""),
                    ))
            else:
                ep.responses.append(ResponseDef(
                    status_code=int(status_code) if status_code.isdigit() else 200,
                    description=resp_data.get("description", ""),
                ))

        return ep

    def _resolve_schema_type(self, schema: dict, schemas: dict) -> str:
        if "$ref" in schema:
            ref_name = schema["$ref"].split("/")[-1]
            ref_schema = schemas.get(ref_name, {})
            return ref_schema.get("type", "object")
        return schema.get("type", "object")

    def _parse_schema_fields(self, schema: dict, schemas: dict) -> list[FieldDef]:
        if "$ref" in schema:
            ref_name = schema["$ref"].split("/")[-1]
            schema = schemas.get(ref_name, {})

        fields: list[FieldDef] = []
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))

        if schema.get("type") == "array":
            items = schema.get("items", {})
            return self._parse_schema_fields(items, schemas)

        for name, prop in properties.items():
            field_type = self._resolve_schema_type(prop, schemas)
            if field_type == "object" and "properties" in prop:
                nested = self._parse_schema_fields(prop, schemas)
                fields.extend(
                    FieldDef(name=f"{name}.{nf.name}", type=nf.type,
                             required=name in required and nf.required,
                             description=nf.description, example=nf.example)
                    for nf in nested
                )
            else:
                fields.append(FieldDef(
                    name=name,
                    type=field_type,
                    required=name in required,
                    description=prop.get("description", ""),
                    example=prop.get("example"),
                    enum=prop.get("enum"),
                ))
        return fields

    def _parse_endpoint(self, data: dict) -> EndpointDef:
        ep = EndpointDef(
            path=data.get("path", ""),
            method=data.get("method", "GET").upper(),
            module=data.get("module", "default"),
            summary=data.get("summary", ""),
            description=data.get("description", ""),
            deprecated=data.get("deprecated", False),
            tags=data.get("tags", []),
        )
        for p in data.get("parameters", []):
            ep.parameters.append(ParameterDef(
                name=p.get("name", ""),
                location=p.get("location", "query"),
                type=p.get("type", "string"),
                required=p.get("required", False),
                description=p.get("description", ""),
                default=p.get("default"),
                example=p.get("example"),
            ))
        req_data = data.get("request")
        if req_data is not None:
            ep.request = RequestDef(
                content_type=req_data.get("content_type", "application/json"),
                fields=[self._parse_field(f) for f in req_data.get("fields", [])],
                example=req_data.get("example"),
            )
        for r in data.get("responses", []):
            ep.responses.append(ResponseDef(
                status_code=r.get("status_code", 200),
                content_type=r.get("content_type", "application/json"),
                fields=[self._parse_field(f) for f in r.get("fields", [])],
                example=r.get("example"),
                description=r.get("description", ""),
            ))
        return ep

    def _parse_field(self, data: dict) -> FieldDef:
        return FieldDef(
            name=data.get("name", ""),
            type=data.get("type", "string"),
            required=data.get("required", False),
            description=data.get("description", ""),
            default=data.get("default"),
            example=data.get("example"),
            enum=data.get("enum"),
        )

    # ---------- Stored Spec Management ----------

    def save_stored_spec(self, spec: ApiSpec, version: Optional[str] = None) -> Path:
        ver = version or spec.version
        path = self.specs_dir / f"{spec.name}_{ver}.json"
        data = self._spec_to_dict(spec)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path

    def load_stored_spec(self, name: str, version: str) -> Optional[ApiSpec]:
        path = self.specs_dir / f"{name}_{version}.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return self._parse_native(data, name)

    def list_stored_specs(self) -> list[tuple[str, str]]:
        specs: list[tuple[str, str]] = []
        if not self.specs_dir.exists():
            return specs
        for f in self.specs_dir.glob("*.json"):
            stem = f.stem
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            name = data.get("name", "")
            version = data.get("version", "")
            if name and version:
                specs.append((name, version))
        return sorted(specs)

    def _spec_to_dict(self, spec: ApiSpec) -> dict:
        endpoints = []
        for ep in spec.endpoints:
            ep_dict: dict[str, Any] = {
                "path": ep.path,
                "method": ep.method,
                "module": ep.module,
                "summary": ep.summary,
                "description": ep.description,
                "deprecated": ep.deprecated,
                "tags": ep.tags,
                "parameters": [
                    {k: v for k, v in p.__dict__.items() if v is not None}
                    for p in ep.parameters
                ],
                "responses": [
                    {
                        "status_code": r.status_code,
                        "content_type": r.content_type,
                        "fields": [
                            {k: v for k, v in f.__dict__.items() if v is not None}
                            for f in r.fields
                        ],
                        **({"example": r.example} if r.example is not None else {}),
                        "description": r.description,
                    } for r in ep.responses
                ],
            }
            if ep.request is not None:
                ep_dict["request"] = {
                    "content_type": ep.request.content_type,
                    "fields": [
                        {k: v for k, v in f.__dict__.items() if v is not None}
                        for f in ep.request.fields
                    ],
                    **({"example": ep.request.example} if ep.request.example is not None else {}),
                }
            endpoints.append(ep_dict)
        return {
            "name": spec.name,
            "version": spec.version,
            "base_url": spec.base_url,
            "description": spec.description,
            "endpoints": endpoints,
        }

    # ---------- Changelog Management ----------

    def load_changelog(self) -> list[ChangelogEntry]:
        if not self.changelog_file.exists():
            return []
        with open(self.changelog_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [self._entry_from_dict(e) for e in data]

    def save_changelog(self, entries: list[ChangelogEntry]) -> None:
        data = [self._entry_to_dict(e) for e in entries]
        with open(self.changelog_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_entry(self, spec_name: str, version: str) -> Optional[ChangelogEntry]:
        """Get a changelog entry by (spec_name, version) composite key."""
        for e in self.load_changelog():
            if e.spec_name == spec_name and e.version == version:
                return e
        return None

    def list_entries_by_spec(self, spec_name: str) -> list[ChangelogEntry]:
        """List all changelog entries for a specific service, newest first."""
        return sorted(
            [e for e in self.load_changelog() if e.spec_name == spec_name],
            key=lambda e: e.version,
            reverse=True,
        )

    def upsert_entry(self, entry: ChangelogEntry) -> None:
        """Insert or update a changelog entry by (spec_name, version)."""
        if not entry.spec_name:
            raise ValueError("ChangelogEntry.spec_name is required for upsert")
        entries = self.load_changelog()
        found = False
        for i, e in enumerate(entries):
            if e.spec_name == entry.spec_name and e.version == entry.version:
                entries[i] = entry
                found = True
                break
        if not found:
            entries.append(entry)
        entries.sort(key=lambda e: (e.spec_name, e.version), reverse=True)
        self.save_changelog(entries)

    def _entry_from_dict(self, data: dict) -> ChangelogEntry:
        changes = []
        for c in data.get("changes", []):
            field_changes = [
                FieldChange(
                    field_name=fc["field_name"],
                    change_type=ChangeType(fc["change_type"]),
                    old_value=fc.get("old_value"),
                    new_value=fc.get("new_value"),
                    property_changed=fc.get("property_changed"),
                ) for fc in c.get("field_changes", [])
            ]
            changes.append(Change(
                change_type=ChangeType(c["change_type"]),
                scope=ChangeScope(c["scope"]),
                endpoint_key=c.get("endpoint_key"),
                module=c.get("module", "default"),
                description=c.get("description", ""),
                field_changes=field_changes,
                impact=ImpactLevel(c.get("impact", "none")),
                breaking=c.get("breaking", False),
                confirmed=c.get("confirmed", False),
                notes=c.get("notes", []),
                migration_guide=c.get("migration_guide", ""),
            ))
        release_date = data.get("release_date")
        status_str = data.get("status")
        if status_str:
            status = ReleaseStatus(status_str)
        elif data.get("released", False):
            status = ReleaseStatus.PUBLISHED
        else:
            status = ReleaseStatus.DRAFT

        return ChangelogEntry(
            spec_name=data.get("spec_name", ""),
            version=data["version"],
            release_date=datetime.fromisoformat(release_date).date() if release_date else None,
            changes=changes,
            notes=data.get("notes", []),
            status=status,
            released_by=data.get("released_by", ""),
            release_channel=data.get("release_channel", ""),
            markdown_path=data.get("markdown_path", ""),
            diff_from_version=data.get("diff_from_version", ""),
        )

    def _entry_to_dict(self, entry: ChangelogEntry) -> dict:
        return {
            "spec_name": entry.spec_name,
            "version": entry.version,
            "release_date": entry.release_date.isoformat() if entry.release_date else None,
            "changes": [
                {
                    "change_type": c.change_type.value,
                    "scope": c.scope.value,
                    "endpoint_key": c.endpoint_key,
                    "module": c.module,
                    "description": c.description,
                    "field_changes": [
                        {
                            "field_name": fc.field_name,
                            "change_type": fc.change_type.value,
                            "old_value": fc.old_value,
                            "new_value": fc.new_value,
                            "property_changed": fc.property_changed,
                        } for fc in c.field_changes
                    ],
                    "impact": c.impact.value,
                    "breaking": c.breaking,
                    "confirmed": c.confirmed,
                    "notes": c.notes,
                    "migration_guide": c.migration_guide,
                } for c in entry.changes
            ],
            "notes": entry.notes,
            "status": entry.status.value,
            "released": entry.released,
            "released_by": entry.released_by,
            "release_channel": entry.release_channel,
            "markdown_path": entry.markdown_path,
            "diff_from_version": entry.diff_from_version,
        }

    # ---------- Aggregation helpers ----------

    def workspace_summary(self) -> dict[str, dict]:
        """Build an aggregate summary grouped by service name."""
        specs = self.list_stored_specs()
        entries = self.load_changelog()

        by_service: dict[str, dict] = {}
        for name, version in specs:
            by_service.setdefault(name, {"versions": [], "entries": []})
            existing_versions = {v[0] for v in by_service[name]["versions"]}
            if version not in existing_versions:
                spec = self.load_stored_spec(name, version)
                endpoint_count = len(spec.endpoints) if spec else 0
                no_example_count = (
                    len([e for e in spec.endpoints if not e.has_examples()])
                    if spec else 0
                )
                by_service[name]["versions"].append((version, endpoint_count, no_example_count))

        for e in entries:
            by_service.setdefault(e.spec_name, {"versions": [], "entries": []})
            by_service[e.spec_name]["entries"].append(e)

        for data in by_service.values():
            data["versions"].sort(key=lambda x: x[0], reverse=True)
            data["entries"].sort(key=lambda x: x.version, reverse=True)

        return by_service
