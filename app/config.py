from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class QueryOptions:
    include_identifiers: bool = True
    include_valuation: bool = True
    include_owner: bool = True
    include_records: bool = True
    include_pricing_history: bool = True
    source_census: bool = True
    source_usps: bool = True
    source_regrid: bool = True
    source_official: bool = True
    min_confidence: float = 0.0
    max_validation_severity: str = "critical"


@dataclass
class SearchAuditEvent:
    timestamp_iso: str
    actor: str
    address: str
    enabled_sources: List[str] = field(default_factory=list)
    min_confidence: float = 0.0
