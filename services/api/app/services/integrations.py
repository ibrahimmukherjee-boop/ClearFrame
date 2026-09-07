"""Enterprise integrations — Slack, Jira, Okta, webhooks + AI SOC EDR fan-out.

When credentials are set (env or Vault), calls are real HTTP.
When missing, returns simulated=True so demos stay green and production
can fail closed via CLEARFRAME_INTEGRATIONS_REQUIRE_LIVE=true.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from app.services import connectors as connectors_svc
from app.services import vault as vault_svc


def _secret(key: str) -> str | None:
    try:
        val = vault_svc.get_secret(key)
    except Exception:
        val = None
    return val or os.environ.get(key) or None


def _require_live() -> bool:
    return os.environ.get("CLEARFRAME_INTEGRATIONS_REQUIRE_LIVE", "").lower() in {"1", "true", "yes"}


def status() -> dict[str, Any]:
    """Operator-facing connector health for ClearFrame AI SOC."""
    slack = bool(_secret("SLACK_BOT_TOKEN") or _secret("SLACK_WEBHOOK_URL"))
    jira = bool(_secret("JIRA_BASE_URL") and _secret("JIRA_API_TOKEN") and _secret("JIRA_EMAIL"))
    okta = bool(_secret("OKTA_DOMAIN") and _secret("OKTA_API_TOKEN"))
    webhook = bool(_secret("SOC_WEBHOOK_URL") or _secret("CLEARFRAME_SOC_WEBHOOK_URL"))
    edr = connectors_svc.connector_status()
    core = [
        {
            "id": "slack",
            "label": "Slack",
            "configured": slack,
            "mode": "live" if slack else "simulated",
            "env": ["SLACK_BOT_TOKEN or SLACK_WEBHOOK_URL", "SLACK_SOC_CHANNEL"],
            "category": "notify",
        },
        {
            "id": "jira",
            "label": "Jira",
            "configured": jira,
            "mode": "live" if jira else "simulated",
            "env": ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"],
            "category": "notify",
        },
        {
            "id": "okta",
            "label": "Okta",
            "configured": okta,
            "mode": "live" if okta else "simulated",
            "env": ["OKTA_DOMAIN", "OKTA_API_TOKEN"],
            "category": "identity",
        },
        {
            "id": "webhook",
            "label": "Generic SOC webhook",
            "configured": webhook,
            "mode": "live" if webhook else "simulated",
            "env": ["SOC_WEBHOOK_URL"],
            "category": "notify",
        },
    ]
    connectors = core + edr
    live_count = sum(1 for c in connectors if c.get("configured"))
    return {
        "product": "ClearFrame AI SOC integrations",
        "requireLive": _require_live(),
        "connectors": connectors,
        "liveCount": live_count,
        "categories": {
            "edr": [c for c in connectors if c.get("category") == "edr"],
            "identity": [c for c in connectors if c.get("category") == "identity"],
            "notify": [c for c in connectors if c.get("category") == "notify"],
        },
        "note": "AI-only SOC: live when secrets set, else simulated. Nexus adds SafePulse + managed connectors.",
    }


def notify_slack(text: str, channel: str | None = None) -> dict[str, Any]:
    channel = channel or os.environ.get("SLACK_SOC_CHANNEL", "#soc-tier1")
    webhook = _secret("SLACK_WEBHOOK_URL")
    token = _secret("SLACK_BOT_TOKEN")

    if webhook:
        try:
            r = httpx.post(webhook, json={"text": text}, timeout=8.0)
            return {"ok": r.status_code < 400, "live": True, "channel": channel, "status": r.status_code}
        except Exception as exc:
            return {"ok": False, "live": True, "error": str(exc)[:200]}

    if token:
        try:
            r = httpx.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {token}"},
                json={"channel": channel, "text": text},
                timeout=8.0,
            )
            data = r.json()
            return {"ok": bool(data.get("ok")), "live": True, "channel": channel, "response": data}
        except Exception as exc:
            return {"ok": False, "live": True, "error": str(exc)[:200]}

    if _require_live():
        return {"ok": False, "live": False, "error": "Slack not configured"}
    return {
        "ok": True,
        "simulated": True,
        "live": False,
        "channel": channel,
        "message": text[:500],
        "note": "Set SLACK_BOT_TOKEN or SLACK_WEBHOOK_URL for live notify",
    }


def create_jira_issue(summary: str, description: str, severity: str = "High") -> dict[str, Any]:
    base = (_secret("JIRA_BASE_URL") or "").rstrip("/")
    email = _secret("JIRA_EMAIL")
    token = _secret("JIRA_API_TOKEN")
    project = os.environ.get("JIRA_PROJECT_KEY", "SOC")

    if not (base and email and token):
        if _require_live():
            return {"ok": False, "live": False, "error": "Jira not configured"}
        return {
            "ok": True,
            "simulated": True,
            "live": False,
            "key": f"{project}-SIM",
            "summary": summary,
            "note": "Set JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN for live tickets",
        }

    payload = {
        "fields": {
            "project": {"key": project},
            "summary": summary[:240],
            "description": description[:4000],
            "issuetype": {"name": os.environ.get("JIRA_ISSUE_TYPE", "Task")},
        }
    }
    try:
        r = httpx.post(
            f"{base}/rest/api/2/issue",
            auth=(email, token),
            json=payload,
            timeout=12.0,
        )
        data = r.json() if r.content else {}
        ok = r.status_code < 300
        return {
            "ok": ok,
            "live": True,
            "key": data.get("key"),
            "id": data.get("id"),
            "status": r.status_code,
            "error": None if ok else str(data)[:300],
        }
    except Exception as exc:
        return {"ok": False, "live": True, "error": str(exc)[:200]}


def okta_suspend_user(login: str) -> dict[str, Any]:
    domain = (_secret("OKTA_DOMAIN") or "").rstrip("/")
    token = _secret("OKTA_API_TOKEN")
    if not domain.startswith("http"):
        domain = f"https://{domain}" if domain else ""

    if not (domain and token and login):
        if _require_live():
            return {"ok": False, "live": False, "error": "Okta not configured"}
        return {
            "ok": True,
            "simulated": True,
            "live": False,
            "user": login,
            "action": "suspend",
            "note": "Set OKTA_DOMAIN + OKTA_API_TOKEN for live suspend",
        }

    try:
        r = httpx.get(
            f"{domain}/api/v1/users/{login}",
            headers={"Authorization": f"SSWS {token}", "Accept": "application/json"},
            timeout=10.0,
        )
        if r.status_code >= 400:
            return {"ok": False, "live": True, "error": f"Okta user lookup failed: {r.status_code}", "body": r.text[:200]}
        user_id = r.json().get("id")
        s = httpx.post(
            f"{domain}/api/v1/users/{user_id}/lifecycle/suspend",
            headers={"Authorization": f"SSWS {token}", "Accept": "application/json"},
            timeout=10.0,
        )
        return {"ok": s.status_code < 300, "live": True, "user": login, "userId": user_id, "status": s.status_code}
    except Exception as exc:
        return {"ok": False, "live": True, "error": str(exc)[:200]}


def post_soc_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    url = _secret("SOC_WEBHOOK_URL") or _secret("CLEARFRAME_SOC_WEBHOOK_URL")
    if not url:
        if _require_live():
            return {"ok": False, "live": False, "error": "SOC webhook not configured"}
        return {"ok": True, "simulated": True, "live": False, "payload": payload, "note": "Set SOC_WEBHOOK_URL for live fan-out"}
    try:
        r = httpx.post(url, json=payload, timeout=8.0)
        return {"ok": r.status_code < 400, "live": True, "status": r.status_code}
    except Exception as exc:
        return {"ok": False, "live": True, "error": str(exc)[:200]}


def run_outbound_bundle(
    *,
    case_id: str,
    title: str,
    summary: str,
    severity: str,
    actor_user: str,
    hostname: str = "",
    device_id: str = "",
    isolate_edr: bool = True,
) -> dict[str, Any]:
    """Execute full AI SOC fan-out: notify + IdP + optional EDR isolate + SIEM export."""
    text = f"[ClearFrame AI SOC] {severity.upper()} case {case_id}: {title}\n{summary}"
    slack = notify_slack(text)
    jira = create_jira_issue(
        f"[AI-SOC] {title}",
        f"{summary}\n\nCase: {case_id}\nActor: {actor_user}\nHost: {hostname or '—'}\nSeverity: {severity}",
        severity,
    )
    okta = okta_suspend_user(actor_user) if actor_user else {"ok": False, "error": "no actor"}
    hook = post_soc_webhook(
        {
            "type": "clearframe.ai_soc.case",
            "caseId": case_id,
            "title": title,
            "severity": severity,
            "actor": actor_user,
            "hostname": hostname,
            "summary": summary,
        }
    )
    pager = connectors_svc.page_pagerduty(
        title=f"AI SOC {case_id}: {title}",
        severity="critical" if severity == "critical" else "error",
        details={"caseId": case_id, "actor": actor_user, "hostname": hostname},
    )
    splunk = connectors_svc.export_splunk(
        {
            "caseId": case_id,
            "title": title,
            "severity": severity,
            "actor": actor_user,
            "hostname": hostname,
            "product": "clearframe-ai-soc",
        }
    )

    crowdstrike = {"ok": False, "skipped": True}
    defender = {"ok": False, "skipped": True}
    sentinelone = {"ok": False, "skipped": True}
    if isolate_edr:
        crowdstrike = connectors_svc.crowdstrike_isolate_host(
            device_id=device_id, hostname=hostname, reason=f"ClearFrame case {case_id}"
        )
        defender = connectors_svc.defender_isolate_host(
            device_id=device_id, hostname=hostname, reason=f"ClearFrame case {case_id}"
        )
        sentinelone = connectors_svc.sentinelone_isolate_host(
            hostname=hostname, reason=f"ClearFrame case {case_id}"
        )

    return {
        "slack": slack,
        "jira": jira,
        "okta": okta,
        "webhook": hook,
        "pagerduty": pager,
        "splunk": splunk,
        "crowdstrike": crowdstrike,
        "defender": defender,
        "sentinelone": sentinelone,
    }
