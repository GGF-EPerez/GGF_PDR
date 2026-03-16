from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from app.models import PricePoint, ProvenanceEntry, TransactionDocument


@dataclass
class PropertyIdentifiers:
    normalized_address: str
    parcel_number: Optional[str]
    lot_number: Optional[str]
    bay_number: Optional[str]
    dwelling_description: Optional[str]
    jurisdiction: Optional[str] = None


@dataclass
class ValuationSnapshot:
    estimated_price: Optional[float]
    last_known_owner: Optional[str]


@dataclass
class USPSAddressResult:
    normalized_address: str
    dpv_confirmation: Optional[str]
    footnotes: List[str]
    confidence: float
    source_url: Optional[str]


@dataclass
class RegridPropertyResult:
    parcel_number: Optional[str]
    lot_number: Optional[str]
    bay_number: Optional[str]
    dwelling_description: Optional[str]
    estimated_price: Optional[float]
    last_known_owner: Optional[str]
    confidence: float
    source_url: Optional[str]


@dataclass
class OfficialRecordResult:
    deed_urls: List[str]
    transaction_documents: List[TransactionDocument]
    confidence: float
    source_url: Optional[str]


class AddressResolver(ABC):
    @abstractmethod
    def resolve(self, address: str) -> PropertyIdentifiers:
        """Resolve a raw address into normalized identifiers."""


class ValuationProvider(ABC):
    @abstractmethod
    def get_valuation(self, parcel_number: Optional[str], address: str) -> ValuationSnapshot:
        """Fetch latest estimated value and owner from public/non-confidential records."""


class RecordsProvider(ABC):
    @abstractmethod
    def get_unofficial_deeds(self, parcel_number: Optional[str], address: str) -> List[str]:
        """Return URLs to unofficial deed copies, if available."""

    @abstractmethod
    def get_transaction_docs(
        self,
        parcel_number: Optional[str],
        address: str,
    ) -> List[TransactionDocument]:
        """Return related transfer/recording transaction docs."""


class PricingHistoryProvider(ABC):
    @abstractmethod
    def get_pricing_history(
        self,
        parcel_number: Optional[str],
        address: str,
        years: int = 10,
    ) -> List[PricePoint]:
        """Return historic pricing points for the requested year range."""


class USPSConnector(ABC):
    @abstractmethod
    def validate_and_standardize(self, address: str) -> USPSAddressResult:
        """Validate and normalize address using USPS-compatible source."""


class RegridConnector(ABC):
    @abstractmethod
    def lookup_property(self, address: str) -> RegridPropertyResult:
        """Lookup parcel/property attributes in Regrid."""


class OfficialRecordsConnector(ABC):
    @abstractmethod
    def lookup_records(self, jurisdiction: str, parcel_number: Optional[str], address: str) -> OfficialRecordResult:
        """Retrieve official county/territory recorder data for deeds and transaction documents."""


class CensusGeocoderResolver(AddressResolver):
    GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

    def __init__(self, timeout_s: float = 4.0):
        self.timeout_s = timeout_s

    def resolve(self, address: str) -> PropertyIdentifiers:
        normalized = " ".join(address.strip().upper().split())
        params = {"address": address, "benchmark": "Public_AR_Current", "format": "json"}
        try:
            query = urlencode(params)
            with urlopen(f"{self.GEOCODER_URL}?{query}", timeout=self.timeout_s) as response:
                data = json.loads(response.read().decode("utf-8"))
            matches = data.get("result", {}).get("addressMatches", [])
            if not matches:
                return PropertyIdentifiers(normalized, None, None, None, None, self._infer_from_text(address))
            match = matches[0]
            components = match.get("addressComponents", {})
            return PropertyIdentifiers(
                normalized_address=match.get("matchedAddress", normalized),
                parcel_number=None,
                lot_number=None,
                bay_number=None,
                dwelling_description=None,
                jurisdiction=components.get("state"),
            )
        except (URLError, ValueError, TimeoutError):
            return PropertyIdentifiers(normalized, None, None, None, None, self._infer_from_text(address))

    @staticmethod
    def _infer_from_text(address: str) -> Optional[str]:
        parts = [p.strip().upper() for p in address.replace(",", " ").split() if p.strip()]
        if not parts:
            return None
        token = parts[-1]
        return token if len(token) == 2 else None


class USPSWebtoolsConnector(USPSConnector):
    """USPS-compatible connector.

    Uses USPS API-style request/response mapping when credentials are configured.
    If credentials are absent or call fails, returns normalized fallback with low confidence.
    """

    BASE_URL = "https://secure.shippingapis.com/ShippingAPI.dll"

    def __init__(self, user_id: Optional[str] = None, timeout_s: float = 4.0):
        self.user_id = user_id
        self.timeout_s = timeout_s

    def validate_and_standardize(self, address: str) -> USPSAddressResult:
        fallback = USPSAddressResult(
            normalized_address=" ".join(address.strip().upper().split()),
            dpv_confirmation=None,
            footnotes=["USPS credentials unavailable or request failed"],
            confidence=0.35,
            source_url=None,
        )
        if not self.user_id:
            return fallback

        xml = (
            f"<AddressValidateRequest USERID=\"{self.user_id}\">"
            "<Revision>1</Revision><Address ID=\"0\">"
            f"<Address1></Address1><Address2>{address}</Address2><City></City><State></State><Zip5></Zip5><Zip4></Zip4>"
            "</Address></AddressValidateRequest>"
        )
        params = {"API": "Verify", "XML": xml}

        try:
            query = urlencode(params)
            request_url = f"{self.BASE_URL}?{query}"
            with urlopen(request_url, timeout=self.timeout_s) as response:
                raw = response.read().decode("utf-8")
            # Lightweight mapping without external XML libs.
            normalized = self._xml_value(raw, "Address2") or fallback.normalized_address
            city = self._xml_value(raw, "City") or ""
            state = self._xml_value(raw, "State") or ""
            zip5 = self._xml_value(raw, "Zip5") or ""
            dpv = self._xml_value(raw, "DPVConfirmation")
            foot = self._xml_value(raw, "Footnotes")
            formatted = " ".join([normalized, city, state, zip5]).strip()
            confidence = 0.9 if dpv in {"Y", "D", "S"} else 0.65
            return USPSAddressResult(
                normalized_address=formatted or fallback.normalized_address,
                dpv_confirmation=dpv,
                footnotes=[foot] if foot else [],
                confidence=confidence,
                source_url=request_url,
            )
        except (URLError, HTTPError, TimeoutError, ValueError):
            return fallback

    @staticmethod
    def _xml_value(raw: str, tag: str) -> Optional[str]:
        open_t = f"<{tag}>"
        close_t = f"</{tag}>"
        if open_t not in raw or close_t not in raw:
            return None
        start = raw.index(open_t) + len(open_t)
        end = raw.index(close_t, start)
        return raw[start:end].strip() or None


class RegridAPIConnector(RegridConnector):
    BASE_URL = "https://app.regrid.com/api/v1/typeahead.json"

    def __init__(self, api_token: Optional[str] = None, timeout_s: float = 4.0):
        self.api_token = api_token
        self.timeout_s = timeout_s

    def lookup_property(self, address: str) -> RegridPropertyResult:
        if not self.api_token:
            return RegridPropertyResult(None, None, None, None, None, None, 0.3, None)

        params = {"token": self.api_token, "query": address, "limit": 1}
        query = urlencode(params)
        request_url = f"{self.BASE_URL}?{query}"

        try:
            with urlopen(request_url, timeout=self.timeout_s) as response:
                data = json.loads(response.read().decode("utf-8"))

            matches = data.get("results", [])
            if not matches:
                return RegridPropertyResult(None, None, None, None, None, None, 0.4, request_url)

            item = matches[0]
            properties = item.get("properties", {})
            parceln = properties.get("parcelnumb") or properties.get("parcel_number")
            lot = properties.get("lot")
            unit = properties.get("unit")
            desc = properties.get("usedesc") or properties.get("landusecode")
            est = properties.get("avm") or properties.get("estimated_value")
            owner = properties.get("owner") or properties.get("owner_name")

            confidence = 0.85 if parceln else 0.6
            return RegridPropertyResult(
                parcel_number=str(parceln) if parceln else None,
                lot_number=str(lot) if lot else None,
                bay_number=str(unit) if unit else None,
                dwelling_description=str(desc) if desc else None,
                estimated_price=float(est) if isinstance(est, (int, float)) else None,
                last_known_owner=str(owner) if owner else None,
                confidence=confidence,
                source_url=request_url,
            )
        except (URLError, HTTPError, TimeoutError, ValueError, TypeError):
            return RegridPropertyResult(None, None, None, None, None, None, 0.35, request_url)


class DemoOfficialRecordsConnector(OfficialRecordsConnector):
    def lookup_records(self, jurisdiction: str, parcel_number: Optional[str], address: str) -> OfficialRecordResult:
        return OfficialRecordResult(
            deed_urls=[
                f"https://official-records.example/{jurisdiction.lower()}/deeds/2021-001122",
                f"https://official-records.example/{jurisdiction.lower()}/deeds/2017-004444",
            ],
            transaction_documents=[
                TransactionDocument(
                    doc_type="Warranty Deed",
                    recording_date=date(2021, 6, 14),
                    instrument_number="2021-001122",
                    source_url=f"https://official-records.example/{jurisdiction.lower()}/docs/2021-001122",
                ),
                TransactionDocument(
                    doc_type="Mortgage",
                    recording_date=date(2021, 6, 14),
                    instrument_number="2021-001123",
                    source_url=f"https://official-records.example/{jurisdiction.lower()}/docs/2021-001123",
                ),
            ],
            confidence=0.8,
            source_url=f"https://official-records.example/{jurisdiction.lower()}",
        )


class DemoPublicDataClient(ValuationProvider, RecordsProvider, PricingHistoryProvider):
    def get_valuation(self, parcel_number: Optional[str], address: str) -> ValuationSnapshot:
        return ValuationSnapshot(estimated_price=425000.0, last_known_owner="JANE DOE")

    def get_unofficial_deeds(self, parcel_number: Optional[str], address: str) -> List[str]:
        return [
            "https://records.example.gov/deeds/2021-001122",
            "https://records.example.gov/deeds/2017-004444",
        ]

    def get_transaction_docs(self, parcel_number: Optional[str], address: str) -> List[TransactionDocument]:
        return [
            TransactionDocument(
                doc_type="Warranty Deed",
                recording_date=date(2021, 6, 14),
                instrument_number="2021-001122",
                source_url="https://records.example.gov/docs/2021-001122",
            ),
            TransactionDocument(
                doc_type="Mortgage",
                recording_date=date(2021, 6, 14),
                instrument_number="2021-001123",
                source_url="https://records.example.gov/docs/2021-001123",
            ),
        ]

    def get_pricing_history(self, parcel_number: Optional[str], address: str, years: int = 10) -> List[PricePoint]:
        today = date.today()
        base_year = today.year - years
        start_price = 280000.0
        points: List[PricePoint] = []
        for i in range(years + 1):
            points.append(PricePoint(as_of=date(base_year + i, 1, 1), amount=round(start_price * (1.045**i), 2), source="demo-avm"))
        return points


def provenance_for(field_name: str, source_name: str, confidence: float, source_url: Optional[str], notes: Optional[str] = None) -> ProvenanceEntry:
    return ProvenanceEntry(
        field_name=field_name,
        source_name=source_name,
        source_url=source_url,
        retrieved_at=date.today(),
        confidence=round(max(0.0, min(1.0, confidence)), 3),
        notes=notes,
    )
