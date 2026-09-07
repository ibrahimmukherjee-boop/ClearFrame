#!/usr/bin/env python3
"""In-process best-in-class smoke: SOC bus, tabletops, integrations, case workflow."""
from __future__ import annotations

import os
import sys
import time

os.environ["CLEARFRAME_DATA_DIR"] = f"/tmp/clearframe-bic-smoke-{os.getpid()}"
os.environ.setdefault("CLEARFRAME_AUTH_REQUIRED", "false")

from app.bootstrap import init_all
from app.services import agents as agents_svc
from app.services import integrations as integrations_svc
from app.services import mandate as mandate_svc
from app.services import policy as policy_svc
from app.services import soc_bus as soc_bus_svc
from app.services import sonar as sonar_svc
from app.services import audit as audit_svc


def must(ok: bool, label: str, detail: object = "") -> None:
    print(("PASS" if ok else "FAIL") + f"  {label}" + (f"  {detail}" if detail != "" else ""))
    if not ok:
        raise SystemExit(1)


def main() -> None:
    t0 = time.time()
    init_all(seed=True)

    # Agent for contain targets
    agent = agents_svc.save_agent(
        {
            "name": "bic-smoke-bot",
            "description": "BIC smoke",
            "capabilities": ["web_search", "email_send"],
            "provider": "ollama",
            "model": "llama3",
        }
    )
    agents_svc.set_current_agent(agent["agentId"])

    # 1) Integrations status
    st = integrations_svc.status()
    must(len(st.get("connectors") or []) >= 8, "integrations status", st.get("liveCount"))
    must(any(c["id"] == "crowdstrike" for c in st["connectors"]), "crowdstrike connector listed")

    # 1b) CrowdStrike sync + isolate (simulated without secrets)
    from app.services import connectors as connectors_svc
    from app.services import ai_soc as ai_soc_svc

    sync = connectors_svc.crowdstrike_sync_to_soc(limit=5)
    must(sync.get("ok") is True, "crowdstrike sync", sync.get("pulled"))
    iso = connectors_svc.crowdstrike_isolate_host(hostname="lap-finance-12")
    must(iso.get("ok") and iso.get("simulated"), "crowdstrike isolate simulated")
    model = ai_soc_svc.operating_model()
    must(len(model.get("layers") or []) >= 5, "ai soc model layers")
    ai_soc_svc.bind_entity(agent_name="bic-smoke-bot", actor_user="edr.user", hostname="ws-22", vendor="crowdstrike")

    # 2) Sonar catalog live-scan each
    for entry in sonar_svc.threat_catalog():
        live = sonar_svc.live_scan_threat(entry["id"])
        must(live.get("ok") and live.get("scan", {}).get("type") != "ok", f"live-scan {entry['id']}")

    # 3) Four tabletops
    for story in ("jailbreak_autocontain", "impossible_travel_exfil", "policy_hard_block", "edr_agent_exfil"):
        out = soc_bus_svc.tabletop(story)
        must(out.get("ok") is True and out.get("case"), f"tabletop {story}", (out.get("case") or {}).get("caseId"))

    # 4) Case workflow: ack → assign → playbook → close
    demo = soc_bus_svc.demo_impossible_travel_and_exfil(actor_user="smoke.user")
    case_id = demo["case"]["caseId"]
    ack = soc_bus_svc.update_case(case_id, status="acknowledged", assignee="analyst@erasys.co.uk", note="ack")
    must(ack.get("ok") and ack["case"]["status"] == "acknowledged", "case acknowledge")
    ran = soc_bus_svc.run_case_playbook(case_id)
    must(ran.get("ok") and ran["case"]["status"] == "contained", "case playbook", ran.get("integrations", {}).get("slack", {}).get("simulated"))
    closed = soc_bus_svc.update_case(case_id, status="closed", note="smoke close")
    must(closed.get("ok") and closed["case"]["status"] == "closed", "case close")

    # 5) CrowdStrike webhook normalize + correlate
    edr = soc_bus_svc.ingest_vendor_webhook(
        "crowdstrike",
        {"detection": "ransomware.behavior", "userName": "edr.user", "hostname": "ws-22", "localIp": "10.1.1.9"},
    )
    must(edr.get("ok") and edr["event"]["source"] == "crowdstrike", "crowdstrike ingest")
    ex = soc_bus_svc.emit_from_sonar(
        threat_type="data_exfiltration",
        severity="critical",
        message="exfil",
        agent_name="bic-smoke-bot",
        actor_user="edr.user",
    )
    must(ex.get("case") is not None, "edr+exfil case", (ex.get("case") or {}).get("caseId"))

    # 6) Policy hard gate still works
    mandate_svc.author("forbid", "shell_exec", name="bic-deny-shell", actor="smoke")
    decision = policy_svc.evaluate("shell_exec", {"command": "rm -rf /"}, {})
    must(decision.get("disposition") in {"deny", "block"} or decision.get("allowed") is False, "policy deny", decision)

    # 7) Audit chain
    chain = audit_svc.verify_chain()
    must(chain.get("valid") is True, "audit chain", chain)

    # 8) Dashboard shape
    dash = soc_bus_svc.dashboard()
    must(dash.get("center") == "cases" and dash.get("totalCases", 0) >= 1, "soc dashboard", dash.get("openCases"))
    must(len(dash.get("tabletops") or []) >= 4, "tabletops listed")
    must("acknowledge" in (dash.get("workflow") or []), "workflow listed")
    must(dash.get("notASiem") is True, "positioned as AI SOC not SIEM")
    must(len(dash.get("layers") or []) >= 4, "model layers on dashboard")
    must("crowdstrike" in (ran.get("integrations") or {}), "playbook includes crowdstrike")

    elapsed = round(time.time() - t0, 3)
    print({"elapsed_sec": elapsed, "cases": dash.get("totalCases"), "events": dash.get("totalEvents"), "connectors": st.get("liveCount")})
    print("BIC SMOKE PASS")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print("FAIL  exception", exc)
        sys.exit(1)
