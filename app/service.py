from __future__ import annotations

from datetime import date, datetime, timedelta

from app.admin import append_audit
from app.config import QueryOptions, SearchAuditEvent
from app.models import CrossValidationFlag, PropertyRecord, SourceConfidence
from app.providers import (
    AddressResolver,
    PricingHistoryProvider,
    RecordsProvider,
    RegridConnector,
    USPSConnector,
    ValuationProvider,
    provenance_for,
)
from app.registry import OfficialConnectorRegistry, ProviderRegistry
from app.scoring import calculate_acquisition_score


class PropertyIntelligenceService:
    def __init__(
        self,
        resolver: AddressResolver,
        valuation_provider: ValuationProvider,
        records_provider: RecordsProvider,
        pricing_provider: PricingHistoryProvider,
        registry: ProviderRegistry,
        usps_connector: USPSConnector,
        regrid_connector: RegridConnector,
        official_registry: OfficialConnectorRegistry,
    ):
        self.resolver = resolver
        self.valuation_provider = valuation_provider
        self.records_provider = records_provider
        self.pricing_provider = pricing_provider
        self.registry = registry
        self.usps_connector = usps_connector
        self.regrid_connector = regrid_connector
        self.official_registry = official_registry

    def evaluate_address(
        self,
        submitted_address: str,
        options: QueryOptions | None = None,
        actor: str = "api_user",
    ) -> PropertyRecord:
        options = options or QueryOptions()

        ids = self.resolver.resolve(submitted_address) if options.source_census else None
        jurisdiction = ids.jurisdiction if ids else None
        coverage = self.registry.coverage_for(jurisdiction)

        usps = self.usps_connector.validate_and_standardize(submitted_address) if options.source_usps else None
        normalized_address = usps.normalized_address if usps else (ids.normalized_address if ids else submitted_address)
        regrid = self.regrid_connector.lookup_property(normalized_address) if options.source_regrid else None

        self._audit(actor, submitted_address, options)

        if not coverage.supported:
            return PropertyRecord(
                submitted_address=submitted_address,
                normalized_address=normalized_address,
                jurisdiction=jurisdiction,
                provider_key=None,
                source_confidences=[
                    *([SourceConfidence("usps", usps.confidence, "Address standardization confidence")] if usps else []),
                    *([SourceConfidence("regrid", regrid.confidence, "Parcel candidate confidence")] if regrid else []),
                ],
                provenance=self._apply_confidence_filter(
                    [
                        *([provenance_for("normalized_address", "usps", usps.confidence, usps.source_url)] if usps else []),
                        *([provenance_for("parcel_number", "regrid", regrid.confidence, regrid.source_url, "No coverage route")] if regrid else []),
                    ],
                    options.min_confidence,
                ),
                acquisition_score=0.0,
                acquisition_notes=[coverage.reason or "Unsupported jurisdiction."],
            )

        parcel = regrid.parcel_number if regrid else (ids.parcel_number if ids else None)
        official_records = (
            self._official_records(coverage.jurisdiction, parcel, normalized_address)
            if options.source_official and options.include_records
            else ([], [], False, None)
        )

        valuation = self.valuation_provider.get_valuation(parcel, normalized_address) if options.include_valuation else None
        deeds = (official_records[0] or self.records_provider.get_unofficial_deeds(parcel, normalized_address)) if options.include_records else []
        docs = (official_records[1] or self.records_provider.get_transaction_docs(parcel, normalized_address)) if options.include_records else []
        history = self.pricing_provider.get_pricing_history(parcel, normalized_address, years=10) if options.include_pricing_history else []

        has_recent_docs = any(d.recording_date >= (date.today() - timedelta(days=365)) for d in docs)
        score, notes = calculate_acquisition_score(history, valuation.estimated_price if valuation else None, has_recent_docs)

        conflicts = self._cross_validation_flags(
            ids.normalized_address if ids else normalized_address,
            normalized_address,
            ids.parcel_number if ids else None,
            regrid.parcel_number if regrid else None,
        )

        severity_order = {"info": 1, "warning": 2, "critical": 3}
        max_sev = severity_order.get(options.max_validation_severity, 3)
        filtered_conflicts = [f for f in conflicts if severity_order.get(f.severity, 3) <= max_sev]

        record = PropertyRecord(
            submitted_address=submitted_address,
            normalized_address=normalized_address,
            jurisdiction=coverage.jurisdiction,
            provider_key=coverage.provider_key,
            parcel_number=(regrid.parcel_number if regrid else None) or (ids.parcel_number if ids and options.include_identifiers else None),
            lot_number=(regrid.lot_number if regrid else None) or (ids.lot_number if ids and options.include_identifiers else None),
            bay_number=(regrid.bay_number if regrid else None) or (ids.bay_number if ids and options.include_identifiers else None),
            dwelling_description=(regrid.dwelling_description if regrid else None) or (ids.dwelling_description if ids and options.include_identifiers else None),
            estimated_price=(regrid.estimated_price if regrid else None) or (valuation.estimated_price if valuation and options.include_valuation else None),
            last_known_owner=(regrid.last_known_owner if regrid else None) or (valuation.last_known_owner if valuation and options.include_owner else None),
            unofficial_deed_urls=deeds,
            transaction_documents=docs,
            pricing_history_10y=history,
            source_confidences=[
                *([SourceConfidence("usps", usps.confidence, "DPV and normalization result")] if usps else []),
                *([SourceConfidence("regrid", regrid.confidence, "Parcel candidate quality")] if regrid else []),
                *([SourceConfidence("official_recorder", 0.8 if official_records[2] else 0.55, "Official registry match")] if options.include_records else []),
            ],
            validation_flags=filtered_conflicts,
            provenance=self._apply_confidence_filter(
                [
                    *([provenance_for("normalized_address", "census", 0.75, None)] if ids else []),
                    *([provenance_for("normalized_address", "usps", usps.confidence, usps.source_url)] if usps else []),
                    *([provenance_for("parcel_number", "regrid", regrid.confidence, regrid.source_url)] if regrid else []),
                    *([provenance_for("estimated_price", "valuation_provider", 0.6, None)] if valuation else []),
                    *([
                        provenance_for(
                            "transaction_documents",
                            "official_recorder",
                            0.8 if official_records[2] else 0.55,
                            official_records[3],
                        )
                    ] if options.include_records else []),
                ],
                options.min_confidence,
            ),
            acquisition_score=score,
            acquisition_notes=notes,
        )
        return record

    @staticmethod
    def _apply_confidence_filter(items, min_confidence: float):
        return [p for p in items if p.confidence >= min_confidence]

    @staticmethod
    def _audit(actor: str, address: str, options: QueryOptions) -> None:
        append_audit(
            SearchAuditEvent(
                timestamp_iso=datetime.utcnow().isoformat(),
                actor=actor,
                address=address,
                enabled_sources=[
                    src
                    for src, enabled in [
                        ("census", options.source_census),
                        ("usps", options.source_usps),
                        ("regrid", options.source_regrid),
                        ("official", options.source_official),
                    ]
                    if enabled
                ],
                min_confidence=options.min_confidence,
            )
        )

    def _official_records(
        self,
        jurisdiction: str | None,
        parcel_number: str | None,
        address: str,
    ) -> tuple[list[str], list, bool, str | None]:
        if not jurisdiction:
            return [], [], False, None
        recorder = self.official_registry.recorder_for(jurisdiction)
        if recorder is None:
            return [], [], False, None
        result = recorder.lookup_records(jurisdiction, parcel_number, address)
        return result.deed_urls, result.transaction_documents, True, result.source_url

    @staticmethod
    def _cross_validation_flags(
        census_normalized: str,
        usps_normalized: str,
        census_parcel: str | None,
        regrid_parcel: str | None,
    ) -> list[CrossValidationFlag]:
        flags: list[CrossValidationFlag] = []
        if census_normalized and usps_normalized and census_normalized.upper() != usps_normalized.upper():
            flags.append(
                CrossValidationFlag(
                    field_name="normalized_address",
                    severity="warning",
                    message="Census and USPS normalized address differ.",
                    source_names=["census", "usps"],
                )
            )
        if census_parcel and regrid_parcel and census_parcel != regrid_parcel:
            flags.append(
                CrossValidationFlag(
                    field_name="parcel_number",
                    severity="critical",
                    message="Parcel mismatch between resolver path and Regrid.",
                    source_names=["resolver", "regrid"],
                )
            )
        return flags
