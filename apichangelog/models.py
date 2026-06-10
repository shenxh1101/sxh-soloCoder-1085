"""
Data models for API Changelog Tool.
Defines core data structures for API specs, versions, changes, and notes.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from datetime import date


class ChangeType(Enum):
    """Type of API change."""
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    DEPRECATED = "deprecated"


class ImpactLevel(Enum):
    """Impact level of a change for consumers."""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BREAKING = "breaking"


class ChangeScope(Enum):
    """Scope of where the change occurred."""
    API = "api"
    ENDPOINT = "endpoint"
    FIELD = "field"
    PARAMETER = "parameter"
    RESPONSE = "response"
    SCHEMA = "schema"


@dataclass
class FieldDef:
    """Definition of a single field in request/response."""
    name: str
    type: str
    required: bool = False
    description: str = ""
    default: Optional[Any] = None
    example: Optional[Any] = None
    enum: Optional[list] = None


@dataclass
class ParameterDef:
    """Definition of an endpoint parameter (query/path/header)."""
    name: str
    location: str
    type: str
    required: bool = False
    description: str = ""
    default: Optional[Any] = None
    example: Optional[Any] = None


@dataclass
class RequestDef:
    """Request definition for an endpoint."""
    content_type: str = "application/json"
    fields: list[FieldDef] = field(default_factory=list)
    example: Optional[Any] = None


@dataclass
class ResponseDef:
    """Response definition for an endpoint."""
    status_code: int = 200
    content_type: str = "application/json"
    fields: list[FieldDef] = field(default_factory=list)
    example: Optional[Any] = None
    description: str = ""


@dataclass
class EndpointDef:
    """Definition of a single API endpoint."""
    path: str
    method: str
    module: str = "default"
    summary: str = ""
    description: str = ""
    deprecated: bool = False
    parameters: list[ParameterDef] = field(default_factory=list)
    request: Optional[RequestDef] = None
    responses: list[ResponseDef] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    owner: str = ""

    @property
    def key(self) -> str:
        return f"{self.method.upper()} {self.path}"

    def has_examples(self) -> bool:
        """Check if endpoint has request/response examples."""
        has_req_example = self.request is not None and self.request.example is not None
        has_resp_example = any(r.example is not None for r in self.responses)
        return has_req_example or has_resp_example


@dataclass
class ApiSpec:
    """Complete API specification for a version."""
    name: str
    version: str
    base_url: str = ""
    description: str = ""
    endpoints: list[EndpointDef] = field(default_factory=list)
    owner: str = ""

    def endpoint_map(self) -> dict[str, EndpointDef]:
        return {ep.key: ep for ep in self.endpoints}

    def modules(self) -> list[str]:
        return sorted({ep.module for ep in self.endpoints})

    def endpoints_by_module(self) -> dict[str, list[EndpointDef]]:
        result: dict[str, list[EndpointDef]] = {}
        for ep in self.endpoints:
            result.setdefault(ep.module, []).append(ep)
        return result


@dataclass
class FieldChange:
    """Represents a change in a single field."""
    field_name: str
    change_type: ChangeType
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    property_changed: Optional[str] = None


@dataclass
class Change:
    """Represents a single API change between versions."""
    change_type: ChangeType
    scope: ChangeScope
    endpoint_key: Optional[str] = None
    module: str = "default"
    description: str = ""
    field_changes: list[FieldChange] = field(default_factory=list)
    impact: ImpactLevel = ImpactLevel.NONE
    breaking: bool = False
    confirmed: bool = False
    notes: list[str] = field(default_factory=list)
    migration_guide: str = ""
    assignee: str = ""

    def is_pending(self) -> bool:
        """Check if change needs human review."""
        return not self.confirmed or (self.breaking and not self.migration_guide)


@dataclass
class VersionDiff:
    """Complete diff between two API versions."""
    old_version: str
    new_version: str
    changes: list[Change] = field(default_factory=list)

    def by_module(self) -> dict[str, list[Change]]:
        result: dict[str, list[Change]] = {}
        for c in self.changes:
            result.setdefault(c.module, []).append(c)
        return result

    def breaking_changes(self) -> list[Change]:
        return [c for c in self.changes if c.breaking]

    def pending_changes(self) -> list[Change]:
        return [c for c in self.changes if c.is_pending()]

    def missing_examples(self, new_spec: ApiSpec) -> list[EndpointDef]:
        """Find endpoints that are new or modified but lack examples."""
        changed_keys = {c.endpoint_key for c in self.changes if c.endpoint_key}
        endpoints = new_spec.endpoint_map()
        return [endpoints[k] for k in changed_keys if k in endpoints and not endpoints[k].has_examples()]


class ReleaseStatus(Enum):
    """Release lifecycle status."""
    DRAFT = "draft"
    PUBLISHED = "published"


@dataclass
class ReleaseInfo:
    """Metadata for a release."""
    version: str
    release_date: date
    highlights: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)


@dataclass
class ChangelogEntry:
    """Stored changelog entry including notes and release info.

    Primary key is (spec_name, version) to support multiple services
    having the same version number independently.
    """
    spec_name: str
    version: str
    release_date: Optional[date] = None
    changes: list[Change] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    status: ReleaseStatus = ReleaseStatus.DRAFT
    released_by: str = ""
    release_channel: str = ""
    release_template: str = ""
    markdown_path: str = ""
    diff_from_version: str = ""
    owner: str = ""
    module_owners: dict[str, str] = field(default_factory=dict)

    @property
    def released(self) -> bool:
        """Backward-compatible alias."""
        return self.status == ReleaseStatus.PUBLISHED

    @released.setter
    def released(self, value: bool) -> None:
        self.status = ReleaseStatus.PUBLISHED if value else ReleaseStatus.DRAFT

    @property
    def pending_count(self) -> int:
        return len([c for c in self.changes if c.is_pending()])
