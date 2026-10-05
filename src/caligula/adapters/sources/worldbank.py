"""World Bank project records (`FunderRecords` adapter)."""

from __future__ import annotations

import httpx

WORLD_BANK_PROJECTS = "https://search.worldbank.org/api/v2/projects"
_WB_FIELDS = "id,project_name,countryname,totalamt,totalcommamt,boardapprovaldate,closingdate,status,impagency,url"


class WorldBankClient:
    """World Bank projects search: an independent record of money the Bank lent
    or disbursed, which the borrowing ministry cannot edit."""

    def __init__(self, client: httpx.Client | None = None):
        self.http = client or httpx.Client(timeout=30.0, follow_redirects=True)

    def search(self, query: str, country_code: str = "TN", rows: int = 5) -> tuple[str, bytes, list[dict]]:
        """Returns (request URL, raw response bytes, parsed projects)."""
        params = {"format": "json", "qterm": query, "countrycode_exact": country_code, "rows": rows, "fl": _WB_FIELDS}
        resp = self.http.get(WORLD_BANK_PROJECTS, params=params)
        resp.raise_for_status()
        projects = resp.json().get("projects") or {}
        items = list(projects.values()) if isinstance(projects, dict) else list(projects)
        return str(resp.url), resp.content, [p for p in items if isinstance(p, dict)]
