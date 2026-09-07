"""Enterprise connectors for the ClearFrame AI SOC.

Focus: protect AI agents — not replace a SIEM.
Live HTTP when credentials are configured (env/Vault); otherwise clearly simulated.
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx

from app.services import vault as vault_svc


def _secret(key: str) -> str | None:
    try:
        val = vault_svc.get_secret(key)
    except Exception:
        val = None
    return val or os.environ.get(key) or None


def _require_live() -> bool:
    return os.environ.get("CLEARFRAME_INTEGRATIONS_REQUIRE_LIVE", "").lower() in {"1", "true", "yes"}


def _sim(ok: bool = True, **extra: Any) -> dict[str, Any]:
    if _require_live() and not ok:
        return {"ok": False, "live": False, "simulated": False, **extra}
    return {"ok": True, "live": False, "simulated": True, **extra}


# ── CrowdStrike Falcon ──────────────────────────────────────────────────────


def crowdstrike_configured() -> bool:
    return bool(_secret("FALCON_CLIENT_ID") and _secret("FALCON_CLIENT_SECRET"))


def _falcon_base() -> str:
    return (_secret("FALCON_BASE_URL") or "https://api.crowdstrike.com").rstrip("/")


def falcon_token() -> dict[str, Any]:
    """OAuth2 client-credentials token for Falcon."""
    cid = _secret("FALCON_CLIENT_ID")
    secret = _secret("FALCON_CLIENT_SECRET")
    if not (cid and secret):
        return _sim(note="Set FALCON_CLIENT_ID + FALCON_CLIENT_SECRET", token=None)
    try:
        r = httpx.post(
            f"{_falcon_base()}/oauth2/token",
            data={"client_id": cid, "client_secret": secret},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=12.0,
        )
        data = r.json() if r.content else {}
        token = data.get("access_token")
        return {
            "ok": bool(token) and r.status_code < 400,
            "live": True,
            "token": token,
            "expiresIn": data.get("expires_in"),
            "status": r.status_code,
            "error": None if token else str(data)[:300],
        }
    except Exception as exc:
        return {"ok": False, "live": True, "error": str(exc)[:200], "token": None}


def crowdstrike_isolate_host(
    *,
    device_id: str = "",
    hostname: str = "",
    reason: str = "ClearFrame AI SOC containment",
) -> dict[str, Any]:
    """Network-contain a host via Falcon device actions (contain)."""
    if not crowdstrike_configured():
        return _sim(
            action="contain",
            deviceId=device_id or "sim-device",
            hostname=hostname or "unknown",
            reason=reason,
            note="Set FALCON_CLIENT_ID + FALCON_CLIENT_SECRET for live isolate",
        )

    auth = falcon_token()
    if not auth.get("ok") or not auth.get("token"):
        return {"ok": False, "live": True, "error": auth.get("error") or "Falcon auth failed"}

    did = device_id
    headers = {"Authorization": f"Bearer {auth['token']}", "Content-Type": "application/json"}
    try:
        if not did and hostname:
            q = httpx.get(
                f"{_falcon_base()}/devices/queries/devices/v1",
                params={"filter": f"hostname:'{hostname}'"},
                headers=headers,
                timeout=12.0,
            )
            ids = (q.json() or {}).get("resources") or []
            did = ids[0] if ids else ""
        if not did:
            return {"ok": False, "live": True, "error": "No Falcon device id / hostname match"}

        r = httpx.post(
            f"{_falcon_base()}/devices/entities/devices-actions/v2",
            params={"action_name": "contain"},
            headers=headers,
            json={"ids": [did]},
            timeout=15.0,
        )
        data = r.json() if r.content else {}
        ok = r.status_code < 400
        return {
            "ok": ok,
            "live": True,
            "action": "contain",
            "deviceId": did,
            "hostname": hostname,
            "reason": reason,
            "status": r.status_code,
            "response": data,
            "error": None if ok else str(data)[:300],
        }
    except Exception as exc:
        return {"ok": False, "live": True, "error": str(exc)[:200]}


def crowdstrike_list_detections(limit: int = 20) -> dict[str, Any]:
    """Pull recent Falcon detections (or simulated AI-relevant fixtures)."""
    if not crowdstrike_configured():
        now = time.time()
        fixtures = [
            {
                "detectionId": "sim-cs-1",
                "hostname": "lap-finance-12",
                "userName": "edr.exfil",
                "tactic": "Exfiltration",
                "technique": "Exfiltration Over Web Service",
                "severity": "critical",
                "ts": now - 120,
                "simulated": True,
            },
            {
                "detectionId": "sim-cs-2",
                "hostname": "dev-agent-runner-03",
                "userName": "svc-agent",
                "tactic": "Execution",
                "technique": "Command and Scripting Interpreter",
                "severity": "high",
                "ts": now - 300,
                "simulated": True,
            },
        ]
        return _sim(detections=fixtures[:limit], count=len(fixtures[:limit]), note="Simulated Falcon detections")

    auth = falcon_token()
    if not auth.get("ok") or not auth.get("token"):
        return {"ok": False, "live": True, "error": auth.get("error") or "Falcon auth failed", "detections": []}

    headers = {"Authorization": f"Bearer {auth['token']}", "Content-Type": "application/json"}
    try:
        q = httpx.get(
            f"{_falcon_base()}/detects/queries/detects/v1",
            params={"limit": min(limit, 100), "sort": "last_behavior|desc"},
            headers=headers,
            timeout=15.0,
        )
        ids = (q.json() or {}).get("resources") or []
        if not ids:
            return {"ok": True, "live": True, "detections": [], "count": 0}
        s = httpx.post(
            f"{_falcon_base()}/detects/entities/summaries/GET/v1",
            headers=headers,
            json={"ids": ids[:limit]},
            timeout=15.0,
        )
        resources = (s.json() or {}).get("resources") or []
        detections = []
        for d in resources:
            device = d.get("device") or {}
            behavior = (d.get("behaviors") or [{}])[0]
            detections.append(
                {
                    "detectionId": d.get("detection_id") or d.get("id"),
                    "hostname": device.get("hostname"),
                    "userName": behavior.get("user_name") or device.get("last_login_user"),
                    "tactic": behavior.get("tactic"),
                    "technique": behavior.get("technique"),
                    "severity": (d.get("max_severity_displayname") or "high").lower(),
                    "ts": time.time(),
                    "raw": {"status": d.get("status"), "cid": d.get("cid")},
                }
            )
        return {"ok": True, "live": True, "detections": detections, "count": len(detections)}
    except Exception as exc:
        return {"ok": False, "live": True, "error": str(exc)[:200], "detections": []}


def crowdstrike_sync_to_soc(limit: int = 10) -> dict[str, Any]:
    """Ingest Falcon detections into the AI SOC bus and correlate with agent threats."""
    from app.services import soc_bus as soc_bus_svc

    pulled = crowdstrike_list_detections(limit=limit)
    ingested = []
    cases = []
    for d in pulled.get("detections") or []:
        out = soc_bus_svc.ingest_vendor_webhook(
            "crowdstrike",
            {
                "detection": d.get("technique") or d.get("tactic") or "malware.detection",
                "userName": d.get("userName") or "unknown",
                "hostname": d.get("hostname") or "endpoint",
                "severity": d.get("severity") or "high",
                "type": "DetectionSummaryEvent",
                "detectionId": d.get("detectionId"),
                "localIp": "",
            },
        )
        ingested.append(out.get("event"))
        if out.get("case"):
            cases.append(out["case"])
    return {
        "ok": pulled.get("ok", True),
        "live": bool(pulled.get("live")),
        "simulated": bool(pulled.get("simulated")),
        "pulled": pulled.get("count", 0),
        "ingested": len(ingested),
        "cases": cases,
        "events": ingested,
        "error": pulled.get("error"),
    }


# ── Microsoft Defender ───────────────────────────────────────────────────────


def defender_configured() -> bool:
    return bool(
        _secret("DEFENDER_TENANT_ID")
        and _secret("DEFENDER_CLIENT_ID")
        and _secret("DEFENDER_CLIENT_SECRET")
    )


def defender_isolate_host(*, device_id: str = "", hostname: str = "", reason: str = "") -> dict[str, Any]:
    if not defender_configured():
        return _sim(
            action="isolate",
            deviceId=device_id or "sim-mdatp",
            hostname=hostname or "unknown",
            reason=reason or "ClearFrame AI SOC",
            note="Set DEFENDER_TENANT_ID + DEFENDER_CLIENT_ID + DEFENDER_CLIENT_SECRET",
        )
    # Live path: Graph security APIs require token dance — invoke when configured
    tenant = _secret("DEFENDER_TENANT_ID")
    cid = _secret("DEFENDER_CLIENT_ID")
    secret = _secret("DEFENDER_CLIENT_SECRET")
    try:
        tok = httpx.post(
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            data={
                "client_id": cid,
                "client_secret": secret,
                "scope": "https://api.securitycenter.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
            timeout=12.0,
        )
        access = (tok.json() or {}).get("access_token")
        if not access:
            return {"ok": False, "live": True, "error": "Defender token failed", "body": tok.text[:200]}
        machine = device_id
        headers = {"Authorization": f"Bearer {access}", "Content-Type": "application/json"}
        if not machine and hostname:
            q = httpx.get(
                "https://api.securitycenter.microsoft.com/api/machines",
                params={"$filter": f"computerDnsName eq '{hostname}'"},
                headers=headers,
                timeout=12.0,
            )
            vals = (q.json() or {}).get("value") or []
            machine = (vals[0] or {}).get("id") if vals else ""
        if not machine:
            return {"ok": False, "live": True, "error": "No Defender machine id"}
        r = httpx.post(
            f"https://api.securitycenter.microsoft.com/api/machines/{machine}/isolate",
            headers=headers,
            json={"Comment": reason or "ClearFrame AI SOC isolate", "IsolationType": "Full"},
            timeout=15.0,
        )
        return {
            "ok": r.status_code < 400,
            "live": True,
            "action": "isolate",
            "deviceId": machine,
            "hostname": hostname,
            "status": r.status_code,
        }
    except Exception as exc:
        return {"ok": False, "live": True, "error": str(exc)[:200]}


# ── SentinelOne ──────────────────────────────────────────────────────────────


def sentinelone_configured() -> bool:
    return bool(_secret("S1_API_TOKEN") and _secret("S1_BASE_URL"))


def sentinelone_isolate_host(*, agent_id: str = "", hostname: str = "", reason: str = "") -> dict[str, Any]:
    if not sentinelone_configured():
        return _sim(
            action="disconnect",
            agentId=agent_id or "sim-s1",
            hostname=hostname or "unknown",
            reason=reason,
            note="Set S1_BASE_URL + S1_API_TOKEN for live isolate",
        )
    base = (_secret("S1_BASE_URL") or "").rstrip("/")
    token = _secret("S1_API_TOKEN")
    headers = {"Authorization": f"ApiToken {token}", "Content-Type": "application/json"}
    try:
        aid = agent_id
        if not aid and hostname:
            q = httpx.get(
                f"{base}/web/api/v2.1/agents",
                params={"computerName__contains": hostname},
                headers=headers,
                timeout=12.0,
            )
            data = (q.json() or {}).get("data") or []
            aid = (data[0] or {}).get("id") if data else ""
        if not aid:
            return {"ok": False, "live": True, "error": "No SentinelOne agent id"}
        r = httpx.post(
            f"{base}/web/api/v2.1/agents/actions/disconnect",
            headers=headers,
            json={"filter": {"ids": [aid]}},
            timeout=15.0,
        )
        return {"ok": r.status_code < 400, "live": True, "action": "disconnect", "agentId": aid, "status": r.status_code}
    except Exception as exc:
        return {"ok": False, "live": True, "error": str(exc)[:200]}


# ── PagerDuty / Splunk ───────────────────────────────────────────────────────


def pagerduty_configured() -> bool:
    return bool(_secret("PAGERDUTY_ROUTING_KEY") or _secret("PAGERDUTY_API_KEY"))


def page_pagerduty(*, title: str, severity: str = "critical", details: dict[str, Any] | None = None) -> dict[str, Any]:
    routing = _secret("PAGERDUTY_ROUTING_KEY")
    if not routing:
        return _sim(title=title, severity=severity, note="Set PAGERDUTY_ROUTING_KEY for live pages")
    payload = {
        "routing_key": routing,
        "event_action": "trigger",
        "payload": {
            "summary": title[:1024],
            "severity": severity if severity in {"critical", "error", "warning", "info"} else "error",
            "source": "clearframe-ai-soc",
            "custom_details": details or {},
        },
    }
    try:
        r = httpx.post("https://events.pagerduty.com/v2/enqueue", json=payload, timeout=10.0)
        data = r.json() if r.content else {}
        return {"ok": r.status_code < 400, "live": True, "dedupKey": data.get("dedup_key"), "status": r.status_code}
    except Exception as exc:
        return {"ok": False, "live": True, "error": str(exc)[:200]}


def splunk_configured() -> bool:
    return bool(_secret("SPLUNK_HEC_URL") and _secret("SPLUNK_HEC_TOKEN"))


def export_splunk(event: dict[str, Any]) -> dict[str, Any]:
    url = _secret("SPLUNK_HEC_URL")
    token = _secret("SPLUNK_HEC_TOKEN")
    if not (url and token):
        return _sim(event=event, note="Set SPLUNK_HEC_URL + SPLUNK_HEC_TOKEN for SIEM export")
    try:
        r = httpx.post(
            url.rstrip("/"),
            headers={"Authorization": f"Splunk {token}"},
            json={"event": event, "sourcetype": "clearframe:ai_soc", "source": "clearframe"},
            timeout=10.0,
        )
        return {"ok": r.status_code < 400, "live": True, "status": r.status_code}
    except Exception as exc:
        return {"ok": False, "live": True, "error": str(exc)[:200]}


def connector_status() -> list[dict[str, Any]]:
    """Full AI SOC connector registry for operator UI."""
    rows = [
        ("crowdstrike", "CrowdStrike Falcon", crowdstrike_configured(), ["FALCON_CLIENT_ID", "FALCON_CLIENT_SECRET", "FALCON_BASE_URL"], "EDR isolate + detection sync"),
        ("defender", "Microsoft Defender", defender_configured(), ["DEFENDER_TENANT_ID", "DEFENDER_CLIENT_ID", "DEFENDER_CLIENT_SECRET"], "Endpoint isolate"),
        ("sentinelone", "SentinelOne", sentinelone_configured(), ["S1_BASE_URL", "S1_API_TOKEN"], "Agent disconnect"),
        ("pagerduty", "PagerDuty", pagerduty_configured(), ["PAGERDUTY_ROUTING_KEY"], "On-call page"),
        ("splunk", "Splunk HEC", splunk_configured(), ["SPLUNK_HEC_URL", "SPLUNK_HEC_TOKEN"], "SIEM export (optional)"),
    ]
    out = []
    for cid, label, configured, env, role in rows:
        out.append(
            {
                "id": cid,
                "label": label,
                "configured": configured,
                "mode": "live" if configured else "simulated",
                "env": env,
                "role": role,
                "category": "edr" if cid in {"crowdstrike", "defender", "sentinelone"} else "notify",
            }
        )
    return out
