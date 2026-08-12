"""Policy documents, cards, hierarchy, and regulatory frameworks."""
from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

from app.database import get_conn

CATEGORIES = ("external_law", "internal", "supplier")

EXTERNAL_LAW_SEED = [
    {
        "title": "ISO/IEC 42001:2023 — AI Management System",
        "content": "International standard for establishing, implementing, maintaining and continually improving an AI management system.",
        "framework": "iso42001",
    },
    {
        "title": "EU Artificial Intelligence Act (Regulation 2024/1689)",
        "content": "Risk-based regulatory framework for AI systems in the European Union. Prohibits unacceptable-risk AI; imposes obligations on high-risk systems.",
        "framework": "eu_ai_act",
    },
    {
        "title": "GDPR (Regulation 2016/679)",
        "content": "General Data Protection Regulation. Governs processing of personal data. Requires lawful basis, data minimisation, DPIAs for high-risk processing.",
        "framework": "gdpr",
    },
]

FRAMEWORK_META = {
    "iso42001": {"name": "ISO/IEC 42001", "label": "AI Management System", "color": "purple"},
    "eu_ai_act": {"name": "EU AI Act", "label": "European AI Regulation", "color": "blue"},
    "gdpr": {"name": "GDPR", "label": "Data Protection", "color": "green"},
}


def init_policy_hub_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS policy_documents (
                doc_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                content TEXT,
                file_name TEXT,
                version TEXT DEFAULT '1.0',
                hierarchy_level INTEGER DEFAULT 0,
                parent_doc_id TEXT,
                enforced INTEGER DEFAULT 1,
                framework TEXT,
                created_at REAL,
                updated_at REAL
            );
            CREATE TABLE IF NOT EXISTS policy_cards (
                card_id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                priority INTEGER DEFAULT 50,
                hierarchy_order INTEGER DEFAULT 0,
                parent_card_id TEXT,
                enforce INTEGER DEFAULT 1,
                tags TEXT,
                created_at REAL
            );
            CREATE TABLE IF NOT EXISTS framework_status (
                framework_id TEXT PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
                attested INTEGER DEFAULT 0,
                score INTEGER DEFAULT 0,
                last_assessed REAL,
                notes TEXT
            );
            """
        )
        for fid in FRAMEWORK_META:
            conn.execute(
                "INSERT OR IGNORE INTO framework_status (framework_id, enabled, attested, score) VALUES (?, 1, 0, 0)",
                (fid,),
            )
        ext_count = conn.execute("SELECT COUNT(*) AS c FROM policy_documents WHERE category = 'external_law'").fetchone()["c"]
        if not ext_count:
            for law in EXTERNAL_LAW_SEED:
                did = f"law-{law['framework']}"
                conn.execute(
                    """INSERT INTO policy_documents (doc_id, title, category, content, framework, enforced, hierarchy_level, created_at, updated_at)
                       VALUES (?, ?, 'external_law', ?, ?, 1, 0, ?, ?)""",
                    (did, law["title"], law["content"], law["framework"], time.time(), time.time()),
                )
                _seed_cards_for_framework(conn, did, law["framework"])
        int_count = conn.execute("SELECT COUNT(*) AS c FROM policy_documents WHERE category = 'internal'").fetchone()["c"]
        if not int_count:
            internal_seeds = [
                ("AI Acceptable Use Policy", "All personnel must use AI agents only within declared capability scopes. Unauthorized tool access is prohibited.", 0),
                ("Training & Competence Policy", "All operators must complete SafePulse enrollment and annual AI governance training before running agent sessions.", 1),
                ("Data Handling & Privacy Policy", "Personal data must not be exfiltrated. All processing must comply with GDPR lawful basis requirements.", 1),
            ]
            for title, content, level in internal_seeds:
                conn.execute(
                    """INSERT INTO policy_documents (doc_id, title, category, content, enforced, hierarchy_level, created_at, updated_at)
                       VALUES (?, ?, 'internal', ?, 1, ?, ?, ?)""",
                    (f"doc-{uuid.uuid4().hex[:8]}", title, content, level, time.time(), time.time()),
                )


def _seed_cards_for_framework(conn, doc_id: str, framework: str) -> None:
    cards_map = {
        "iso42001": [
            ("AI system scope defined", "All AI agents must be registered with documented purpose and capabilities.", 100, None),
            ("Human oversight required", "High-risk tool calls require human-in-the-loop approval before execution.", 95, None),
            ("Risk assessment process", "AI risks identified, assessed, and monitored continuously via Sonar.", 90, None),
            ("Audit trail integrity", "Tamper-evident HMAC audit chain maintained for all agent actions.", 100, None),
        ],
        "eu_ai_act": [
            ("Transparency obligation", "Users must be informed when interacting with an AI system.", 80, None),
            ("High-risk conformity", "High-risk AI systems require conformity assessment before deployment.", 95, None),
            ("Human oversight (Art. 14)", "Natural persons must be able to override or stop AI system output.", 100, None),
            ("Logging (Art. 12)", "Automatic recording of events during operation; logs kept for traceability.", 90, None),
        ],
        "gdpr": [
            ("Lawful basis for processing", "Personal data processed only with valid lawful basis (Art. 6).", 100, None),
            ("Data minimisation", "Only data necessary for the stated purpose is collected or processed.", 90, None),
            ("Right to explanation", "Data subjects may request meaningful information about automated decisions.", 85, None),
            ("DPIA for high-risk processing", "Data Protection Impact Assessment required for high-risk processing (Art. 35).", 95, None),
        ],
    }
    for i, (title, content, priority, parent) in enumerate(cards_map.get(framework, [])):
        cid = f"card-{uuid.uuid4().hex[:8]}"
        conn.execute(
            """INSERT INTO policy_cards (card_id, doc_id, title, content, priority, hierarchy_order, parent_card_id, enforce, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (cid, doc_id, title, content, priority, i, parent, time.time()),
        )


def parse_content_into_rules(content: str) -> list[tuple[str, str]]:
    """Parse markdown or plain text into enforceable policy cards."""
    cards: list[tuple[str, str]] = []
    text = content.strip()
    if not text:
        return cards

    sections = re.split(r'\n(?=##\s+)', text)
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if section.startswith('#'):
            first, _, rest = section.partition('\n')
            title = first.lstrip('#').strip()
            body = rest.strip() or title
            if title:
                cards.append((title, body))

    if not cards:
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            if re.match(r'^(\d+[\.\)]\s|[-*]\s|Rule\s+\d+)', line, re.I):
                cards.append((line[:120], line))

    if not cards:
        first_line = text.split('\n')[0].strip()[:100]
        cards.append((first_line or 'Policy requirement', text[:800]))

    return cards[:25]


def upload_document(title: str, category: str, content: str, file_name: str = "", version: str = "1.0", parent_doc_id: str | None = None, hierarchy_level: int = 0) -> dict[str, Any]:
    if category not in CATEGORIES:
        raise ValueError(f"Invalid category: {category}")
    doc_id = f"doc-{uuid.uuid4().hex[:8]}"
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO policy_documents (doc_id, title, category, content, file_name, version, hierarchy_level, parent_doc_id, enforced, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (doc_id, title, category, content, file_name, version, hierarchy_level, parent_doc_id, time.time(), time.time()),
        )
    rules = parse_content_into_rules(content)
    for i, (rule_title, rule_body) in enumerate(rules):
        create_card(doc_id, rule_title, rule_body, priority=max(50, 95 - i * 5), hierarchy_order=i, enforce=True)
    return get_document(doc_id)


def get_document(doc_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM policy_documents WHERE doc_id = ?", (doc_id,)).fetchone()
    if not row:
        return {}
    return _serialize_doc(dict(row))


def list_documents(category: str | None = None) -> list[dict[str, Any]]:
    with get_conn() as conn:
        if category:
            rows = conn.execute("SELECT * FROM policy_documents WHERE category = ? ORDER BY hierarchy_level, title", (category,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM policy_documents ORDER BY category, hierarchy_level, title").fetchall()
    return [_serialize_doc(dict(r)) for r in rows]


def _serialize_doc(row: dict[str, Any]) -> dict[str, Any]:
    cards = list_cards(row["doc_id"])
    return {
        "docId": row["doc_id"],
        "title": row["title"],
        "category": row["category"],
        "content": row["content"] or "",
        "fileName": row["file_name"] or "",
        "version": row["version"],
        "hierarchyLevel": row["hierarchy_level"],
        "parentDocId": row["parent_doc_id"],
        "enforced": bool(row["enforced"]),
        "framework": row.get("framework"),
        "cardCount": len(cards),
        "cards": cards,
        "createdAt": row["created_at"],
    }


def create_card(doc_id: str, title: str, content: str, priority: int = 50, parent_card_id: str | None = None, hierarchy_order: int = 0, enforce: bool = True, tags: list[str] | None = None) -> dict[str, Any]:
    card_id = f"card-{uuid.uuid4().hex[:8]}"
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO policy_cards (card_id, doc_id, title, content, priority, hierarchy_order, parent_card_id, enforce, tags, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (card_id, doc_id, title, content, priority, hierarchy_order, parent_card_id, int(enforce), json.dumps(tags or []), time.time()),
        )
    return get_card(card_id)


def get_card(card_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM policy_cards WHERE card_id = ?", (card_id,)).fetchone()
    return _serialize_card(dict(row)) if row else {}


def list_cards(doc_id: str | None = None) -> list[dict[str, Any]]:
    with get_conn() as conn:
        if doc_id:
            rows = conn.execute("SELECT * FROM policy_cards WHERE doc_id = ? ORDER BY hierarchy_order, priority DESC", (doc_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM policy_cards ORDER BY priority DESC").fetchall()
    return [_serialize_card(dict(r)) for r in rows]


def _serialize_card(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "cardId": row["card_id"],
        "docId": row["doc_id"],
        "title": row["title"],
        "content": row["content"],
        "priority": row["priority"],
        "hierarchyOrder": row["hierarchy_order"],
        "parentCardId": row["parent_card_id"],
        "enforce": bool(row["enforce"]),
        "tags": json.loads(row["tags"] or "[]"),
    }


def update_card_hierarchy(card_id: str, parent_card_id: str | None, hierarchy_order: int, enforce: bool | None = None) -> dict[str, Any]:
    with get_conn() as conn:
        if enforce is not None:
            conn.execute(
                "UPDATE policy_cards SET parent_card_id = ?, hierarchy_order = ?, enforce = ? WHERE card_id = ?",
                (parent_card_id, hierarchy_order, int(enforce), card_id),
            )
        else:
            conn.execute(
                "UPDATE policy_cards SET parent_card_id = ?, hierarchy_order = ? WHERE card_id = ?",
                (parent_card_id, hierarchy_order, card_id),
            )
    return get_card(card_id)


def set_document_enforced(doc_id: str, enforced: bool) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE policy_documents SET enforced = ?, updated_at = ? WHERE doc_id = ?", (int(enforced), time.time(), doc_id))


def attest_framework(framework_id: str, attested: bool = True, notes: str = "") -> dict[str, Any]:
    from app.services import compliance as compliance_svc
    from app.services import eu_ai_act as eu_svc

    score = 0
    if framework_id == "iso42001":
        score = compliance_svc.run_iso42001_assessment()["complianceScore"]
    elif framework_id == "eu_ai_act":
        score = eu_svc.assess_portfolio()["portfolioScore"]
    elif framework_id == "gdpr":
        score = _assess_gdpr()

    with get_conn() as conn:
        conn.execute(
            "UPDATE framework_status SET attested = ?, score = ?, last_assessed = ?, notes = ? WHERE framework_id = ?",
            (int(attested), score, time.time(), notes, framework_id),
        )
        row = conn.execute("SELECT * FROM framework_status WHERE framework_id = ?", (framework_id,)).fetchone()
    return _serialize_framework(dict(row), framework_id)


def _assess_gdpr() -> int:
    docs = list_documents("external_law")
    gdpr = next((d for d in docs if d.get("framework") == "gdpr"), None)
    if not gdpr:
        return 0
    enforced = sum(1 for c in gdpr.get("cards", []) if c["enforce"])
    total = len(gdpr.get("cards", []))
    internal = len(list_documents("internal"))
    return min(100, round((enforced / total * 60 if total else 0) + min(internal * 10, 40)))


def get_frameworks() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM framework_status").fetchall()
    return [_serialize_framework(dict(r), r["framework_id"]) for r in rows]


def _serialize_framework(row: dict[str, Any], fid: str) -> dict[str, Any]:
    meta = FRAMEWORK_META.get(fid, {})
    law_doc = next((d for d in list_documents("external_law") if d.get("framework") == fid), None)
    return {
        "frameworkId": fid,
        "name": meta.get("name", fid),
        "label": meta.get("label", ""),
        "enabled": bool(row["enabled"]),
        "attested": bool(row["attested"]),
        "score": row["score"],
        "lastAssessed": row["last_assessed"],
        "notes": row["notes"] or "",
        "lawDocument": law_doc,
    }


def get_governance_hub() -> dict[str, Any]:
    from app.services import governance as gov_svc
    from app.services import compliance as compliance_svc

    frameworks = get_frameworks()
    return {
        "frameworks": frameworks,
        "externalLaw": list_documents("external_law"),
        "internalPolicies": list_documents("internal"),
        "supplierPolicies": list_documents("supplier"),
        "allCards": list_cards(),
        "governance": gov_svc.get_dashboard(),
        "isoAssessment": compliance_svc.run_iso42001_assessment(),
    }
