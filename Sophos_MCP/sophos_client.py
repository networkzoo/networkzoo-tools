"""
Sophos Central Partner API client.
Handles OAuth token lifecycle and partner-scoped API calls.
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

TOKEN_URL  = "https://id.sophos.com/api/v2/oauth2/token"
PARTNER_URL = "https://api.central.sophos.com"


class SophosClient:
    def __init__(self):
        self.client_id     = os.getenv("SOPHOS_CLIENT_ID")
        self.client_secret = os.getenv("SOPHOS_CLIENT_SECRET")
        if not self.client_id or not self.client_secret:
            raise ValueError("SOPHOS_CLIENT_ID and SOPHOS_CLIENT_SECRET must be set in .env")

        self._token: str | None = None
        self._token_expiry: float = 0
        self._partner_id: str | None = None
        self._api_host: str | None = None

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 30:
            return self._token

        resp = httpx.post(TOKEN_URL, data={
            "grant_type":    "client_credentials",
            "client_id":     self.client_id,
            "client_secret": self.client_secret,
            "scope":         "token",
        }, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        self._token        = data["access_token"]
        self._token_expiry = time.time() + data.get("expires_in", 3600)
        return self._token

    def _headers(self) -> dict:
        headers = {"Authorization": f"Bearer {self._get_token()}"}
        if self._partner_id:
            headers["X-Partner-ID"] = self._partner_id
        return headers

    # ── Whoami / partner context ──────────────────────────────────────────────

    def get_whoami(self) -> dict:
        resp = httpx.get(f"{PARTNER_URL}/whoami/v1", headers=self._headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        self._partner_id = data.get("id")
        self._api_host   = data.get("apiHosts", {}).get("global", PARTNER_URL)
        return data

    def _ensure_partner_context(self):
        if not self._partner_id:
            self.get_whoami()

    # ── Tenants ───────────────────────────────────────────────────────────────

    def get_tenants(self) -> list[dict]:
        self._ensure_partner_context()
        tenants = []
        url = f"{self._api_host}/partner/v1/tenants"
        params = {"pageSize": 100}

        while url:
            resp = httpx.get(url, headers=self._headers(), params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            tenants.extend(data.get("items", []))
            next_key = data.get("pages", {}).get("nextKey")
            params = {"pageSize": 100, "pageFromKey": next_key} if next_key else None
            url = url if next_key else None

        return tenants

    # ── Licenses ──────────────────────────────────────────────────────────────

    def get_tenant_detail(self, tenant_id: str) -> dict:
        """Fetch full detail for one tenant, including its products list."""
        self._ensure_partner_context()
        resp = httpx.get(
            f"{self._api_host}/partner/v1/tenants/{tenant_id}",
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def get_all_tenant_products(self) -> list[dict]:
        """
        Returns a flat list of { tenantId, tenantName, productCode } for every
        active product across all tenants. Uses a thread pool to fetch all
        tenant details in parallel.
        """
        tenants = self.get_tenants()

        def fetch_one(t: dict) -> list[dict]:
            tid   = t["id"]
            tname = t.get("name", tid)
            try:
                detail = self.get_tenant_detail(tid)
                return [
                    {"tenantId": tid, "tenantName": tname, "productCode": p.get("code", "")}
                    for p in detail.get("products", [])
                ]
            except Exception:
                return []

        results = []
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {pool.submit(fetch_one, t): t for t in tenants}
            for future in as_completed(futures):
                results.extend(future.result())
        return results

    def probe_endpoint(self, url: str, extra_headers: dict = None) -> dict:
        """Make a raw GET request and return status + body for debugging."""
        self._ensure_partner_context()
        headers = {**self._headers(), **(extra_headers or {})}
        resp = httpx.get(url, headers=headers, timeout=30)
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return {"status": resp.status_code, "body": body}

    def get_tenant_licenses(self, tenant_id: str, tenant_api_host: str) -> list[dict]:
        """Fetch all active licenses for a single tenant via partner API."""
        self._ensure_partner_context()
        licenses = []

        # Try partner-scoped endpoint first
        candidates = [
            (f"{self._api_host}/partner/v1/tenants/{tenant_id}/licenses", {}),
            (f"{self._api_host}/partner/v1/tenants/{tenant_id}/usages", {}),
            (f"{tenant_api_host}/licensing/v1/licences", {"X-Tenant-ID": tenant_id}),
            (f"{tenant_api_host}/licensing/v1/accountLicences", {"X-Tenant-ID": tenant_id}),
        ]

        for url, extra in candidates:
            headers = {**self._headers(), **extra}
            resp = httpx.get(url, headers=headers, params={"pageSize": 100}, timeout=30)
            if resp.status_code in (404, 403, 405):
                continue
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items") or data.get("licences") or data.get("licenses") or []
                if items:
                    licenses.extend(items)
                    # Store which URL worked for pagination
                    next_key = data.get("pages", {}).get("nextKey")
                    params = {"pageSize": 100}
                    while next_key:
                        params["pageFromKey"] = next_key
                        r2 = httpx.get(url, headers=headers, params=params, timeout=30)
                        d2 = r2.json()
                        licenses.extend(d2.get("items") or d2.get("licences") or d2.get("licenses") or [])
                        next_key = d2.get("pages", {}).get("nextKey")
                    return licenses
            break  # unexpected status — stop trying

        return licenses

    def get_all_tenant_licenses(self) -> dict[str, list[dict]]:
        """
        Returns { tenant_name: [license, ...], ... } for all tenants.
        Each license dict includes the tenant name/id for easy cross-referencing.
        """
        tenants = self.get_tenants()
        result = {}
        for tenant in tenants:
            tid   = tenant["id"]
            tname = tenant.get("name", tid)
            thost = tenant.get("apiHost", self._api_host)
            try:
                licenses = self.get_tenant_licenses(tid, thost)
                if licenses:
                    result[tname] = licenses
            except httpx.HTTPStatusError as e:
                result[tname] = [{"error": str(e)}]
        return result
