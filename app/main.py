from __future__ import annotations

import os
from dataclasses import asdict
from datetime import datetime

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.admin import audit_window, create_account, load_defaults, set_defaults
from app.config import QueryOptions
from app.providers import (
    CensusGeocoderResolver,
    DemoOfficialRecordsConnector,
    DemoPublicDataClient,
    RegridAPIConnector,
    USPSWebtoolsConnector,
)
from app.registry import (
    OfficialConnectorRegistry,
    OfficialSourceConfig,
    ProviderRegistry,
    ProviderRoutingConfig,
)
from app.service import PropertyIntelligenceService

app = FastAPI(title="Property Intelligence API", version="0.4.0")

resolver = CensusGeocoderResolver()
demo_data = DemoPublicDataClient()
usps_connector = USPSWebtoolsConnector(user_id=os.getenv("USPS_USER_ID"))
regrid_connector = RegridAPIConnector(api_token=os.getenv("REGRID_API_TOKEN"))

demo_official = DemoOfficialRecordsConnector()
official_registry = OfficialConnectorRegistry(
    OfficialSourceConfig(
        assessor_connector_by_jurisdiction={"CA": demo_official, "TX": demo_official, "PR": demo_official},
        recorder_connector_by_jurisdiction={"CA": demo_official, "TX": demo_official, "PR": demo_official},
    )
)

registry = ProviderRegistry(
    ProviderRoutingConfig(
        provider_by_jurisdiction={"CA": "multi_source_v1", "TX": "multi_source_v1", "FL": "multi_source_v1", "NY": "multi_source_v1", "PR": "multi_source_v1"},
        default_provider=None,
    )
)

service = PropertyIntelligenceService(
    resolver=resolver,
    valuation_provider=demo_data,
    records_provider=demo_data,
    pricing_provider=demo_data,
    registry=registry,
    usps_connector=usps_connector,
    regrid_connector=regrid_connector,
    official_registry=official_registry,
)


class PropertyRequest(BaseModel):
    address: str = Field(..., min_length=5, description="Street address to evaluate")
    options: QueryOptions = Field(default_factory=QueryOptions)
    actor: str = "api_user"


class AccountRequest(BaseModel):
    username: str
    role: str
    account_type: str = "human"


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
    <html><body style='font-family:Arial;max-width:900px;margin:20px auto;'>
      <h2>Property Intelligence Search</h2>
      <form method='post' action='/evaluate-web' oninput='updateMap()'>
        <label>Address:</label><br/>
        <input type='text' id='address' name='address' style='width:100%;padding:8px;' placeholder='1600 Pennsylvania Ave NW, Washington, DC' required/>
        <h4>Services to query</h4>
        <label><input type='checkbox' name='source_census' checked/> Census</label>
        <label><input type='checkbox' name='source_usps' checked/> USPS</label>
        <label><input type='checkbox' name='source_regrid' checked/> Regrid</label>
        <label><input type='checkbox' name='source_official' checked/> Official county/territory</label>
        <br/><br/>
        <button type='submit'>Evaluate</button>
      </form>
      <h4>Map validation frame</h4>
      <iframe id='map' width='100%' height='360' style='border:0' loading='lazy' src='https://www.google.com/maps?q=Washington%2C%20DC&output=embed'></iframe>
      <script>
        function updateMap(){
          const q=encodeURIComponent(document.getElementById('address').value||'Washington, DC');
          document.getElementById('map').src='https://www.google.com/maps?q='+q+'&output=embed';
        }
      </script>
    </body></html>
    """


@app.post("/evaluate-web", response_class=HTMLResponse)
def evaluate_web(
    address: str = Form(...),
    source_census: str | None = Form(None),
    source_usps: str | None = Form(None),
    source_regrid: str | None = Form(None),
    source_official: str | None = Form(None),
) -> str:
    options = QueryOptions(
        source_census=bool(source_census),
        source_usps=bool(source_usps),
        source_regrid=bool(source_regrid),
        source_official=bool(source_official),
    )
    result = service.evaluate_address(address.strip(), options=options, actor="web_user")
    return f"<html><body><h3>Evaluation Result</h3><pre>{asdict(result)}</pre><a href='/'>Back</a></body></html>"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/coverage/{jurisdiction}")
def coverage(jurisdiction: str) -> dict:
    return asdict(registry.coverage_for(jurisdiction.upper()))


@app.post("/evaluate")
def evaluate(req: PropertyRequest) -> dict:
    address = req.address.strip()
    if not address:
        raise HTTPException(status_code=400, detail="Address is required")
    return asdict(service.evaluate_address(address, options=req.options, actor=req.actor))


@app.post("/admin/accounts")
def admin_create_account(req: AccountRequest) -> dict:
    return create_account(req.username, req.role, req.account_type)


@app.get("/admin/audit")
def admin_audit(start_iso: str, end_iso: str) -> dict:
    return {"count": len(audit_window(start_iso, end_iso)), "results": audit_window(start_iso, end_iso)}


@app.post("/admin/defaults")
def admin_set_defaults(options: QueryOptions) -> dict:
    return set_defaults(options)


@app.get("/admin/defaults")
def admin_get_defaults() -> dict:
    return asdict(load_defaults())


@app.get("/admin/audit/today")
def admin_audit_today() -> dict:
    now = datetime.utcnow()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end = now.isoformat()
    rows = audit_window(start, end)
    return {"count": len(rows), "results": rows}
