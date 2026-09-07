"""Enterprise integrations — Slack, Jira, Okta, generic webhooks.

When credentials are set (env or Vault), calls are real HTTP.
When missing, returns simulated=True so demos stay green and production
can fail closed via CLEARFRAME_INTEGRATIONS_REQUIRE_LIVE=true.
"""
from __future__ import annotations

import os
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


def status() -> dict[str, Any]:
    """Operator-facing connector health for ClearFrame vs Nexus pitch."""
    slack = bool(_secret("SLACK_BOT_TOKEN") or _secret("SLACK_WEBHOOK_URL"))
    jira = bool(_secret("JIRA_BASE_URL") and _secret("JIRA_API_TOKEN") and _secret("JIRA_EMAIL"))
    okta = bool(_secret("OKTA_DOMAIN") and _secret("OKTA_API_TOKEN"))
    webhook = bool(_secret("SOC_WEBHOOK_URL") or _secret("CLEARFRAME_SOC_WEBHOOK_URL"))
    return {
        "product": "ClearFrame integrations",
        "requireLive": _require_live(),
        "connectors": [
            {
                "id": "slack",
                "label": "Slack",
                "configured": slack,
                "mode": "live" if slack else "simulated",
                "env": ["SLACK_BOT_TOKEN or SLACK_WEBHOOK_URL", "SLACK_SOC_CHANNEL"],
            },
            {
                "id": "jira",
                "label": "Jira",
                "configured": jira,
                "mode": "live" if jira else "simulated",
                "env": ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"],
            },
            {
                "id": "okta",
                "label": "Okta",
                "configured": okta,
                "mode": "live" if okta else "simulated",
                "env": ["OKTA_DOMAIN", "OKTA_API_TOKEN"],
            },
            {
                "id": "webhook",
                "label": "Generic SOC webhook",
                "configured": webhook,
                "mode": "live" if webhook else "simulated",
                "env": ["SOC_WEBHOOK_URL"],
            },
        ],
        "liveCount": sum(1 for c in [slack, jira, okta, webhook] if c),
        "note": "Configure env/Vault secrets for live actions. Nexus Protocol adds managed connectors + SafePulse.",
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
        # Resolve user by login
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
) -> dict[str, Any]:
    """Execute Slack + Jira + Okta + generic webhook for a case."""
    text = f"[ClearFrame SOC] {severity.upper()} case {case_id}: {title}\n{summary}"
    slack = notify_slack(text)
    jira = create_jira_issue(f"[SOC] {title}", f"{summary}\n\nCase: {case_id}\nActor: {actor_user}\nSeverity: {severity}", severity)
    okta = okta_suspend_user(actor_user) if actor_user else {"ok": False, "error": "no actor"}
    hook = post_soc_webhook(
        {
            "type": "clearframe.soc.case",
            "caseId": case_id,
            "title": title,
            "severity": severity,
            "actor": actor_user,
            "summary": summary,
        }
    )
    return {"slack": slack, "jira": jira, "okta": okta, "webhook": hook}
