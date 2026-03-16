from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from app.jurisdiction import CoverageStatus, US_STATES_AND_TERRITORIES
from app.providers import OfficialRecordsConnector


@dataclass
class ProviderRoutingConfig:
    provider_by_jurisdiction: Dict[str, str]
    default_provider: Optional[str] = None


class ProviderRegistry:
    """Coverage-aware provider routing registry."""

    def __init__(self, config: ProviderRoutingConfig):
        self.config = config

    def coverage_for(self, jurisdiction: Optional[str]) -> CoverageStatus:
        if not jurisdiction:
            return CoverageStatus(None, False, None, "Could not determine jurisdiction from address.")

        code = jurisdiction.upper()
        if code not in US_STATES_AND_TERRITORIES:
            return CoverageStatus(code, False, None, "Jurisdiction is not a US state/DC/territory code.")

        provider = self.config.provider_by_jurisdiction.get(code, self.config.default_provider)
        if provider is None:
            return CoverageStatus(code, False, None, "No provider configured for this jurisdiction yet.")

        return CoverageStatus(code, True, provider)


@dataclass
class OfficialSourceConfig:
    assessor_connector_by_jurisdiction: Dict[str, OfficialRecordsConnector]
    recorder_connector_by_jurisdiction: Dict[str, OfficialRecordsConnector]
    default_assessor_connector: Optional[OfficialRecordsConnector] = None
    default_recorder_connector: Optional[OfficialRecordsConnector] = None


class OfficialConnectorRegistry:
    """Registry for official county/territory data sources.

    Can route assessor and recorder/deed connectors separately.
    """

    def __init__(self, config: OfficialSourceConfig):
        self.config = config

    def assessor_for(self, jurisdiction: str) -> Optional[OfficialRecordsConnector]:
        code = jurisdiction.upper()
        return self.config.assessor_connector_by_jurisdiction.get(code, self.config.default_assessor_connector)

    def recorder_for(self, jurisdiction: str) -> Optional[OfficialRecordsConnector]:
        code = jurisdiction.upper()
        return self.config.recorder_connector_by_jurisdiction.get(code, self.config.default_recorder_connector)
