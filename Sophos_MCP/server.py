"""
Sophos Central MCP Server
Exposes partner tenant and license data to Claude for monthly billing reconciliation.
"""
import csv
import io
import json
from mcp.server.fastmcp import FastMCP
from sophos_client import SophosClient

mcp    = FastMCP("Sophos Central")
client = SophosClient()


@mcp.tool()
def get_whoami() -> str:
    """Return the partner identity and API host info for the authenticated account."""
    data = client.get_whoami()
    return json.dumps(data, indent=2)


@mcp.tool()
def get_tenants() -> str:
    """
    List all managed tenants under this partner account.
    Returns id, name, dataGeography, apiHost, and status for each.
    """
    tenants = client.get_tenants()
    summary = [
        {
            "id":       t["id"],
            "name":     t.get("name", ""),
            "status":   t.get("status", ""),
            "region":   t.get("dataGeography", ""),
            "apiHost":  t.get("apiHost", ""),
        }
        for t in tenants
    ]
    return json.dumps(summary, indent=2)


@mcp.tool()
def get_tenant_licenses(tenant_id: str, tenant_api_host: str) -> str:
    """
    Get active licenses for a specific tenant.

    Args:
        tenant_id: The tenant UUID (from get_tenants)
        tenant_api_host: The tenant's apiHost (from get_tenants)
    """
    licenses = client.get_tenant_licenses(tenant_id, tenant_api_host)
    return json.dumps(licenses, indent=2)


@mcp.tool()
def get_all_licenses() -> str:
    """
    Fetch licenses for ALL tenants and return a flat summary suitable for
    comparison against a Climb invoice CSV.

    Returns a list of { tenant, sku, productName, quantity, type, startDate, endDate }.
    """
    all_licenses = client.get_all_tenant_licenses()
    flat = []
    for tenant_name, licenses in all_licenses.items():
        for lic in licenses:
            if "error" in lic:
                continue
            flat.append({
                "tenant":      tenant_name,
                "sku":         lic.get("licenceId", ""),
                "productName": lic.get("productName", ""),
                "quantity":    lic.get("quantity", 0),
                "type":        lic.get("licenceType", ""),
                "startDate":   lic.get("startsAt", ""),
                "endDate":     lic.get("expiresAt", ""),
            })
    return json.dumps(flat, indent=2)


@mcp.tool()
def compare_csv_to_central(csv_text: str) -> str:
    """
    Compare a Climb invoice CSV (pasted as text) against live Central license data.

    Identifies:
    - NEW: in CSV but not in Central config
    - MISSING: in Central but not on this invoice
    - QTY_CHANGE: quantity differs between Central and invoice
    - MATCH: all good

    Args:
        csv_text: Full contents of the Climb CSV file
    """
    # Parse CSV
    reader = csv.DictReader(io.StringIO(csv_text))
    invoice_rows = list(reader)

    # Normalise headers (case-insensitive lookup)
    def find_col(row: dict, candidates: list[str]) -> str | None:
        for k in row:
            if k.strip().lower() in [c.lower() for c in candidates]:
                return k
        return None

    if not invoice_rows:
        return json.dumps({"error": "CSV appears empty"})

    sample = invoice_rows[0]
    col_client = find_col(sample, ["End User Name", "Client", "Customer"])
    col_sku    = find_col(sample, ["Sku", "SKU", "Product SKU"])
    col_qty    = find_col(sample, ["Qty", "Quantity"])

    if not all([col_client, col_sku, col_qty]):
        return json.dumps({"error": f"Could not locate required columns. Found: {list(sample.keys())}"})

    # Build invoice map: (tenant_name, sku) -> qty
    invoice_map: dict[tuple, int] = {}
    for row in invoice_rows:
        tenant = (row.get(col_client) or "").strip()
        sku    = (row.get(col_sku)    or "").strip()
        qty    = int(float(row.get(col_qty) or 0))
        if tenant and sku:
            key = (tenant, sku)
            invoice_map[key] = invoice_map.get(key, 0) + qty

    # Pull Central data
    all_licenses = client.get_all_tenant_licenses()

    # Build Central map: (tenant_name, sku) -> qty
    # Note: Central licenceId may not match Climb SKU directly — we match on productName
    # as a fallback and include both for review.
    central_map: dict[tuple, dict] = {}
    for tenant_name, licenses in all_licenses.items():
        for lic in licenses:
            if "error" in lic:
                continue
            sku = lic.get("licenceId", "")
            qty = lic.get("quantity", 0)
            key = (tenant_name, sku)
            central_map[key] = {
                "quantity":    qty,
                "productName": lic.get("productName", ""),
            }

    results = {
        "match":      [],
        "qty_change": [],
        "new":        [],
        "missing":    [],
    }

    # Check invoice against Central
    for (tenant, sku), inv_qty in invoice_map.items():
        if (tenant, sku) in central_map:
            cen_qty = central_map[(tenant, sku)]["quantity"]
            if inv_qty == cen_qty:
                results["match"].append({"tenant": tenant, "sku": sku, "qty": inv_qty})
            else:
                results["qty_change"].append({
                    "tenant":   tenant,
                    "sku":      sku,
                    "invoice_qty": inv_qty,
                    "central_qty": cen_qty,
                })
        else:
            results["new"].append({"tenant": tenant, "sku": sku, "qty": inv_qty})

    # Check Central against invoice (find what's licensed but not billed)
    for (tenant, sku), info in central_map.items():
        if (tenant, sku) not in invoice_map:
            results["missing"].append({
                "tenant":      tenant,
                "sku":         sku,
                "central_qty": info["quantity"],
                "productName": info["productName"],
            })

    summary = {
        "matched":    len(results["match"]),
        "qty_changes": len(results["qty_change"]),
        "new_on_invoice": len(results["new"]),
        "missing_from_invoice": len(results["missing"]),
        "details": results,
    }
    return json.dumps(summary, indent=2)


@mcp.tool()
def get_tenant_catalog() -> str:
    """
    Fetch every tenant's active product codes from Sophos Central.
    Returns a list of { tenantId, tenantName, productCode } — one entry per
    product per tenant.  Use this to build the client catalog in the web app.
    """
    catalog = client.get_all_tenant_products()
    return json.dumps(catalog, indent=2)


@mcp.tool()
def probe_api(url: str, tenant_id: str = "") -> str:
    """
    Make a raw GET request to any Sophos API URL for debugging.
    Optionally pass a tenant_id to add X-Tenant-ID header.

    Args:
        url: Full URL to probe (e.g. https://api.central.sophos.com/partner/v1/tenants/xxx/licenses)
        tenant_id: Optional tenant UUID to include as X-Tenant-ID header
    """
    extra = {"X-Tenant-ID": tenant_id} if tenant_id else {}
    result = client.probe_endpoint(url, extra)
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    mcp.run()
