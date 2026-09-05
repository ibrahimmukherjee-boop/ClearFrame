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
    """NLP-lite parse of markdown/plain text into hierarchical enforceable cards.

    Extracts: markdown headings, numbered rules, MUST/SHALL/MUST NOT statements,
    and bullet obligations — the patterns auditors actually write into policies.
    """
    cards: list[tuple[str, str]] = []
    text = (content or "").strip()
    if not text:
        return cards

    # Strip simple PDF/DOCX binary noise if raw bytes were decoded poorly
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)

    sections = re.split(r"\n(?=#{1,3}\s+)", text)
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if section.startswith("#"):
            first, _, rest = section.partition("\n")
            title = first.lstrip("#").strip()
            body = rest.strip() or title
            if title:
                cards.append((title[:160], body[:1200]))

    # Obligation sentences (MUST / SHALL / MUST NOT / PROHIBITED)
    for m in re.finditer(
        r"(?im)^(?:[-*]\s+)?((?:agents?|operators?|users?|systems?|personnel)?[^.\n]{0,40}"
        r"(?:must not|must|shall not|shall|prohibited|forbidden|required to)[^.\n]{10,200}\.?)",
        text,
    ):
        line = m.group(1).strip()
        if len(line) > 20:
            cards.append((line[:120], line))

    if not cards:
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if re.match(r"^(\d+[\.\)]\s|[-*]\s|Rule\s+\d+)", line, re.I):
                cards.append((line[:120], line))

    if not cards:
        first_line = text.split("\n")[0].strip()[:100]
        cards.append((first_line or "Policy requirement", text[:800]))

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for t, b in cards:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append((t, b))
    return unique[:40]


def extract_text_from_upload(file_name: str, raw: bytes | str) -> str:
    """Extract text from .md/.txt/.pdf/.docx uploads for policy NLP."""
    name = (file_name or "").lower()
    if isinstance(raw, str):
        data = raw.encode("utf-8", errors="ignore")
        text = raw
    else:
        data = raw
        text = raw.decode("utf-8", errors="ignore")

    if name.endswith((".md", ".txt", ".text", ".csv")):
        return text
    if name.endswith(".pdf"):
        # Minimal PDF text extraction without heavy deps: pull printable strings
        chunks = re.findall(rb"\((?:\\.|[^\\)]){4,}\)", data)
        decoded = []
        for c in chunks:
            try:
                s = c[1:-1].decode("utf-8", errors="ignore")
                s = s.replace("\\n", "\n").replace("\\t", " ")
                if any(ch.isalpha() for ch in s):
                    decoded.append(s)
            except Exception:
                continue
        return "\n".join(decoded) if decoded else text
    if name.endswith((".docx", ".doc")):
        # DOCX is a zip of XML; pull <w:t> text nodes if present
        try:
            import zipfile
            import io
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
            return "\n".join(re.findall(r"<w:t[^>]*>([^<]+)</w:t>", xml))
        except Exception:
            return text
    return text


def enforced_cards() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT c.* FROM policy_cards c
               JOIN policy_documents d ON d.doc_id = c.doc_id
               WHERE c.enforce = 1 AND d.enforced = 1
               ORDER BY c.priority DESC"""
        ).fetchall()
    return [_serialize_card(dict(r)) for r in rows]


def hierarchy_tree() -> list[dict[str, Any]]:
    """Nested document → card tree for the console."""
    docs = list_documents()
    by_parent: dict[str | None, list[dict[str, Any]]] = {}
    for d in docs:
        by_parent.setdefault(d.get("parentDocId"), []).append(d)

    def walk(parent_id: str | None, level: int = 0) -> list[dict[str, Any]]:
        nodes = []
        for d in by_parent.get(parent_id, []):
            cards = d.get("cards") or []
            # Nest cards by parentCardId
            card_children: dict[str | None, list] = {}
            for c in cards:
                card_children.setdefault(c.get("parentCardId"), []).append(c)
            def walk_cards(pid: str | None) -> list:
                out = []
                for c in card_children.get(pid, []):
                    out.append({**c, "children": walk_cards(c["cardId"])})
                return out
            nodes.append({
                **{k: v for k, v in d.items() if k != "cards"},
                "level": level,
                "cards": walk_cards(None),
                "children": walk(d["docId"], level + 1),
            })
        return nodes

    return walk(None)


def upload_document(title: str, category: str, content: str, file_name: str = "", version: str = "1.0", parent_doc_id: str | None = None, hierarchy_level: int = 0) -> dict[str, Any]:
    if category not in CATEGORIES:
        raise ValueError(f"Invalid category: {category}")
    # If content looks like a path placeholder with binary already extracted upstream, parse filename
    if file_name:
        content = extract_text_from_upload(file_name, content) or content
    doc_id = f"doc-{uuid.uuid4().hex[:8]}"
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO policy_documents (doc_id, title, category, content, file_name, version, hierarchy_level, parent_doc_id, enforced, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (doc_id, title, category, content, file_name, version, hierarchy_level, parent_doc_id, time.time(), time.time()),
        )
    rules = parse_content_into_rules(content)
    parent_card = None
    for i, (rule_title, rule_body) in enumerate(rules):
        # First card is root; subsequent MUST NOT cards nest under root for hierarchy display
        card = create_card(
            doc_id, rule_title, rule_body,
            priority=max(40, 100 - i * 3),
            hierarchy_order=i,
            parent_card_id=parent_card if i > 0 and i < 4 else None,
            enforce=True,
            tags=["nlp-parsed", "enforced"],
        )
        if i == 0:
            parent_card = card.get("cardId")
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
