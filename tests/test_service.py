from __future__ import annotations

from datetime import date

from app.config import QueryOptions
from app.models import PricePoint, TransactionDocument
from app.providers import (
    AddressResolver,
    OfficialRecordResult,
    OfficialRecordsConnector,
    PricingHistoryProvider,
    PropertyIdentifiers,
    RecordsProvider,
    RegridConnector,
    RegridPropertyResult,
    USPSAddressResult,
    USPSConnector,
    ValuationProvider,
    ValuationSnapshot,
)
from app.registry import OfficialConnectorRegistry, OfficialSourceConfig, ProviderRegistry, ProviderRoutingConfig
from app.service import PropertyIntelligenceService


class FakeResolver(AddressResolver):
    def __init__(self, jurisdiction: str | None = "TX"):
        self.jurisdiction = jurisdiction

    def resolve(self, address: str) -> PropertyIdentifiers:
        return PropertyIdentifiers("123 MAIN ST", "P-1", "L-2", "B-3", "Townhouse", self.jurisdiction)


class FakeValuation(ValuationProvider):
    def get_valuation(self, parcel_number: str | None, address: str) -> ValuationSnapshot:
        return ValuationSnapshot(300000.0, "ALICE")


class FakeRecords(RecordsProvider):
    def get_unofficial_deeds(self, parcel_number: str | None, address: str):
        return ["https://example/deed"]

    def get_transaction_docs(self, parcel_number: str | None, address: str):
        return [TransactionDocument("Deed", date.today(), "I-1", "https://example/doc")]


class FakePricing(PricingHistoryProvider):
    def get_pricing_history(self, parcel_number: str | None, address: str, years: int = 10):
        return [PricePoint(date(2015, 1, 1), 200000.0, "test"), PricePoint(date(2025, 1, 1), 320000.0, "test")]


class FakeUSPS(USPSConnector):
    def validate_and_standardize(self, address: str) -> USPSAddressResult:
        return USPSAddressResult("123 MAIN ST APT 1 TX 77001", "Y", [], 0.92, "https://usps.example")


class FakeRegrid(RegridConnector):
    def lookup_property(self, address: str) -> RegridPropertyResult:
        return RegridPropertyResult("P-1", "L-2", "B-3", "Townhouse", 315000.0, "ALICE", 0.86, "https://regrid.example")


class FakeOfficial(OfficialRecordsConnector):
    def lookup_records(self, jurisdiction: str, parcel_number: str | None, address: str) -> OfficialRecordResult:
        return OfficialRecordResult(
            deed_urls=["https://official/deed/1"],
            transaction_documents=[TransactionDocument("Warranty Deed", date.today(), "R-1", "https://official/doc/1")],
            confidence=0.85,
            source_url="https://official/registry",
        )


def _registry_with_tx() -> ProviderRegistry:
    return ProviderRegistry(ProviderRoutingConfig(provider_by_jurisdiction={"TX": "multi_source_v1"}))


def _official_registry() -> OfficialConnectorRegistry:
    off = FakeOfficial()
    return OfficialConnectorRegistry(
        OfficialSourceConfig(
            assessor_connector_by_jurisdiction={"TX": off},
            recorder_connector_by_jurisdiction={"TX": off},
        )
    )


def test_evaluate_address_enriched_with_provenance_and_confidence():
    svc = PropertyIntelligenceService(
        FakeResolver("TX"),
        FakeValuation(),
        FakeRecords(),
        FakePricing(),
        _registry_with_tx(),
        FakeUSPS(),
        FakeRegrid(),
        _official_registry(),
    )

    result = svc.evaluate_address("123 Main Street")

    assert result.provider_key == "multi_source_v1"
    assert result.parcel_number == "P-1"
    assert result.estimated_price == 315000.0
    assert result.unofficial_deed_urls == ["https://official/deed/1"]
    assert len(result.source_confidences) >= 3
    assert any(p.field_name == "parcel_number" and p.source_name == "regrid" for p in result.provenance)


def test_evaluate_address_unsupported_still_has_source_confidence():
    svc = PropertyIntelligenceService(
        FakeResolver("WA"),
        FakeValuation(),
        FakeRecords(),
        FakePricing(),
        _registry_with_tx(),
        FakeUSPS(),
        FakeRegrid(),
        _official_registry(),
    )

    result = svc.evaluate_address("123 Main Street")

    assert result.provider_key is None
    assert result.acquisition_score == 0.0
    assert len(result.source_confidences) == 2
    assert "No provider configured" in result.acquisition_notes[0]


def test_query_options_disable_records_and_filter_provenance():
    svc = PropertyIntelligenceService(
        FakeResolver("TX"),
        FakeValuation(),
        FakeRecords(),
        FakePricing(),
        _registry_with_tx(),
        FakeUSPS(),
        FakeRegrid(),
        _official_registry(),
    )

    options = QueryOptions(include_records=False, min_confidence=0.9)
    result = svc.evaluate_address("123 Main Street", options=options, actor="test")

    assert result.unofficial_deed_urls == []
    assert result.transaction_documents == []
    assert all(p.confidence >= 0.9 for p in result.provenance)
