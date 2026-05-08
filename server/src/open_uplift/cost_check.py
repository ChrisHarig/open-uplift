"""Best-effort API-key billing/credit lookup.

Both Anthropic and OpenAI publish credit/usage data only on admin-scoped
keys (`sk-ant-admin-...`, `sk-admin-...`). Regular API keys can't reach those
endpoints, so this module returns a structured "not accessible" result instead
of throwing — the UI shows whatever it gets.

Only anthropic and openai are supported. Other providers (openrouter etc.)
return a "provider not supported" note.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx


def fetch_key_cost(provider: str, api_key: str, timeout_s: float = 8.0) -> dict:
    """Best-effort lookup. Returns dict with whatever fields we can populate."""
    if provider == "anthropic":
        return _anthropic_cost(api_key, timeout_s)
    if provider == "openai":
        return _openai_cost(api_key, timeout_s)
    return {"note": f"Cost lookup not supported for provider {provider!r}."}


def _anthropic_cost(api_key: str, timeout_s: float) -> dict:
    """Try the Admin API usage report. Regular keys will get 401/403."""
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    end = datetime.now(timezone.utc).replace(microsecond=0)
    start = end - timedelta(days=30)
    params = {
        "starting_at": start.isoformat().replace("+00:00", "Z"),
        "ending_at": end.isoformat().replace("+00:00", "Z"),
    }
    try:
        with httpx.Client(timeout=timeout_s) as client:
            r = client.get(
                "https://api.anthropic.com/v1/organizations/cost_report",
                headers=headers,
                params=params,
            )
        if r.status_code in (401, 403):
            return {
                "note": "Anthropic billing data requires an admin key (sk-ant-admin-...). "
                        "This is a regular API key, so balance and spend are not accessible."
            }
        if r.status_code != 200:
            return {"error": f"Anthropic cost endpoint returned {r.status_code}: {r.text[:200]}"}
        body = r.json()
        spend_cents = 0
        for bucket in body.get("data", []):
            for result in bucket.get("results", []):
                spend_cents += result.get("amount", {}).get("amount", 0) or 0
        return {
            "spend_usd": round(spend_cents / 100, 2),
            "window_days": 30,
            "currency": "USD",
            "note": "Last 30 days (admin-key data).",
        }
    except httpx.HTTPError as e:
        return {"error": f"Anthropic cost lookup failed: {e}"}


def _openai_cost(api_key: str, timeout_s: float) -> dict:
    """Try the OpenAI usage endpoint. Regular keys typically get 401."""
    headers = {"Authorization": f"Bearer {api_key}"}
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=30)
    try:
        with httpx.Client(timeout=timeout_s) as client:
            r = client.get(
                "https://api.openai.com/v1/organization/costs",
                headers=headers,
                params={
                    "start_time": int(datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp()),
                    "end_time": int(datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc).timestamp()),
                },
            )
        if r.status_code in (401, 403):
            return {
                "note": "OpenAI billing data requires an admin key (sk-admin-...). "
                        "This is a regular API key, so balance and spend are not accessible."
            }
        if r.status_code != 200:
            return {"error": f"OpenAI cost endpoint returned {r.status_code}: {r.text[:200]}"}
        body = r.json()
        spend_cents = 0
        for bucket in body.get("data", []):
            for result in bucket.get("results", []):
                spend_cents += result.get("amount", {}).get("value", 0) or 0
        return {
            "spend_usd": round(spend_cents / 100, 2),
            "window_days": 30,
            "currency": "USD",
            "note": "Last 30 days (admin-key data).",
        }
    except httpx.HTTPError as e:
        return {"error": f"OpenAI cost lookup failed: {e}"}
