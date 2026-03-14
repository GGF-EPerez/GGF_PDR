from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional


@dataclass
class PricePoint:
    """A dated valuation or transaction price."""

    as_of: date
    amount: float
    source: str


@dataclass
class TransactionDocument:
    """A public record transaction document metadata entry."""

    doc_type: str
    recording_date: date
    instrument_number: str
    source_url: str


@dataclass
class ProvenanceEntry:
    field_name: str
    source_name: str
    source_url: Optional[str]
    retrieved_at: date
    confidence: float
    notes: Optional[str] = None


@dataclass
class SourceConfidence:
    source_name: str
    confidence: float
    rationale: str


@dataclass
class CrossValidationFlag:
    field_name: str
    severity: str
    message: str
    source_names: List[str] = field(default_factory=list)


@dataclass
class PropertyRecord:
    """Canonical property record assembled from multiple public sources."""

    submitted_address: str
    normalized_address: str
    jurisdiction: Optional[str] = None
    provider_key: Optional[str] = None
    parcel_number: Optional[str] = None
    lot_number: Optional[str] = None
    bay_number: Optional[str] = None
    dwelling_description: Optional[str] = None
    estimated_price: Optional[float] = None
    last_known_owner: Optional[str] = None
    unofficial_deed_urls: List[str] = field(default_factory=list)
    transaction_documents: List[TransactionDocument] = field(default_factory=list)
    pricing_history_10y: List[PricePoint] = field(default_factory=list)
    source_confidences: List[SourceConfidence] = field(default_factory=list)
    validation_flags: List[CrossValidationFlag] = field(default_factory=list)
    provenance: List[ProvenanceEntry] = field(default_factory=list)
    acquisition_score: Optional[float] = None
    acquisition_notes: List[str] = field(default_factory=list)
