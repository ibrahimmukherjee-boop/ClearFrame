#!/usr/bin/env python3
"""Generate Erasys Governance-as-Code enterprise briefing PDF."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT = Path(__file__).resolve().parent / "Erasys-Governance-as-Code-Enterprise-Briefing.pdf"
BRAND = colors.HexColor("#1a2b6b")
ACCENT = colors.HexColor("#4361ee")
MUTED = colors.HexColor("#475569")
LIGHT = colors.HexColor("#f1f5f9")
LINE = colors.HexColor("#cbd5e1")


def styles():
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=28,
            textColor=BRAND,
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=12,
            leading=16,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=6,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=BRAND,
            spaceBefore=14,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=15,
            textColor=ACCENT,
            spaceBefore=10,
            spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#0f172a"),
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=12.5,
            textColor=colors.HexColor("#0f172a"),
            leftIndent=4,
        ),
        "callout": ParagraphStyle(
            "callout",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=9.5,
            leading=13,
            textColor=BRAND,
            alignment=TA_LEFT,
            spaceBefore=4,
            spaceAfter=8,
        ),
        "footer": ParagraphStyle(
            "footer",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "table_cell": ParagraphStyle(
            "table_cell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#0f172a"),
        ),
        "table_head": ParagraphStyle(
            "table_head",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=colors.white,
        ),
    }


def bullets(items, s):
    return ListFlowable(
        [ListItem(Paragraph(i, s["bullet"]), leftIndent=8, bulletColor=ACCENT) for i in items],
        bulletType="bullet",
        start="•",
        leftIndent=12,
        bulletFontSize=9,
        spaceBefore=2,
        spaceAfter=8,
    )


def kv_table(rows, s, col_widths=None):
    data = [
        [Paragraph(a, s["table_cell"]), Paragraph(b, s["table_cell"])]
        for a, b in rows
    ]
    t = Table(data, colWidths=col_widths or [48 * mm, 122 * mm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return t


def header_table(headers, rows, s, col_widths=None):
    data = [[Paragraph(h, s["table_head"]) for h in headers]]
    for row in rows:
        data.append([Paragraph(c, s["table_cell"]) for c in row])
    t = Table(data, colWidths=col_widths)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("BOX", (0, 0), (-1, -1), 0.4, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
    t.setStyle(TableStyle(style))
    return t


def add_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 12 * mm, A4[0] - 18 * mm, 12 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 7 * mm, "Erasys — Confidential | Enterprise briefing")
    canvas.drawRightString(A4[0] - 18 * mm, 7 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build():
    s = styles()
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title="Erasys Governance-as-Code — Enterprise Briefing",
        author="Erasys",
    )
    story = []

    # Cover
    story.append(Spacer(1, 28 * mm))
    story.append(Paragraph("ERASYS", s["cover_sub"]))
    story.append(
        Paragraph(
            "The Enterprise Standard for<br/>Agentic AI Governance",
            s["cover_title"],
        )
    )
    story.append(
        Paragraph(
            "Governance-as-Code (GaC) — “Agentic AI’s border control.”",
            s["cover_sub"],
        )
    )
    story.append(Spacer(1, 8 * mm))
    story.append(
        Paragraph(
            "Enterprise client briefing: value proposition, strategic positioning, "
            "Minimum Viable Governance, go-to-market, and pilot guidance.",
            s["cover_sub"],
        )
    )
    story.append(Spacer(1, 14 * mm))
    story.append(
        kv_table(
            [
                ("Document type", "Strategic briefing for enterprise clients & partners"),
                ("Positioning", "Governance Overlay — not an ERP / platform replacement"),
                ("Lead product", "GoverUp (Minimum Viable Governance)"),
                ("Audience", "CISO, Infosec, Trust &amp; Technology, AI Platform owners"),
            ],
            s,
            [42 * mm, 128 * mm],
        )
    )
    story.append(PageBreak())

    # 1 Purpose
    story.append(Paragraph("1. Purpose of this document", s["h1"]))
    story.append(
        Paragraph(
            "Explain Erasys <b>Governance-as-Code (GaC)</b> to enterprise clients and establish "
            "<b>trust as the prerequisite for scaling agentic AI</b>. Erasys is the border control "
            "layer for agentic systems: who built the agent, who is operating it, whether it is trusted, "
            "whether outcomes are compliant and consistent, and how rogue activity is detected and tracked.",
            s["body"],
        )
    )
    story.append(
        Paragraph(
            "Pivot: Erasys is not a platform replacement. It is a <b>Governance Overlay</b> that "
            "embeds compliance into agent workflows so Infosec and Trust &amp; Technology teams can "
            "say “yes” to production AI without accumulating security debt.",
            s["callout"],
        )
    )

    # 2 Problem
    story.append(Paragraph("2. Context &amp; problem", s["h1"]))
    story.append(
        Paragraph(
            "Enterprise AI adoption is accelerating; governance is lagging. Agents are treated as "
            "black boxes. Leadership cannot reliably answer: Are agents built for scale? Who is "
            "operating them? Are they trusted? Are results compliant and consistent? Is there rogue "
            "activity—and how proactively can it be detected and continually tracked?",
            s["body"],
        )
    )
    story.append(
        Paragraph(
            "Without an enforcement plane, every new agent increases audit, security, and regulatory "
            "risk. Traditional IAM, EDR, and ERP controls were not designed for autonomous tool-using "
            "agents that change goals mid-session. Erasys provides the connective tissue across "
            "enterprise AI and ERP estates—turning compliance from a blocker into a <b>scaling catalyst</b>.",
            s["body"],
        )
    )

    # 3 Solution
    story.append(Paragraph("3. The solution: Governance-as-Code", s["h1"]))
    story.append(
        Paragraph(
            "An end-to-end governance framework that delivers enterprise-grade confidence, "
            "auditability, and security for agentic workflows. GaC means policies, trust, identity, "
            "and human oversight are expressed as enforceable controls in the runtime path—not "
            "documentation after the fact.",
            s["body"],
        )
    )
    story.append(
        Paragraph(
            "<b>Value statement.</b> Erasys provides a Governance-as-Code layer bridging AI agility "
            "and enterprise control. Automating policy enforcement—from identity verification to risk "
            "interception—transforms compliance from a “No” gatekeeper into a continuous “Yes” "
            "accelerator. We secure agents and give developers the guardrails to scale "
            "production-grade AI without security debt.",
            s["body"],
        )
    )

    story.append(Paragraph("3.1 Product ecosystem", s["h2"]))
    story.append(
        header_table(
            ["Product", "Role in the Governance Overlay"],
            [
                [
                    "Builder",
                    "Token-efficient agent definition with scoped capabilities and templates — the controlled on-ramp.",
                ],
                [
                    "GoverUp",
                    "Regulatory &amp; policy screening firewall. Ingests enterprise and industry frameworks and enforces them in agent operations. <b>Minimum Viable Governance lead.</b>",
                ],
                [
                    "Trust Registry",
                    "Registers agents and issues trust certificates; flags non-compliant workflows for security screening.",
                ],
                [
                    "ClearFrame",
                    "Continual runtime audit of agent sessions for end-to-end enterprise governance.",
                ],
                [
                    "SafePulse",
                    "Multi-layered behavioural biometrics for continuous human/agent identity verification and insider-threat signals without workflow friction.",
                ],
                [
                    "Aegis",
                    "Goal monitoring and human-in-the-loop intervention for high-risk actions — visibility and control at scale.",
                ],
                [
                    "Sonar",
                    "Infosec command centre for monitoring enterprise agentic operations and threat/drift events.",
                ],
            ],
            s,
            [32 * mm, 138 * mm],
        )
    )

    story.append(Paragraph("3.2 Why now &amp; why Erasys", s["h2"]))
    story.append(
        bullets(
            [
                "<b>First-mover on agentic border control:</b> enterprises lack a dedicated enforcement plane for autonomous agents.",
                "<b>Defensible depth:</b> layered products (Swiss-cheese defence) close gaps that single-point IAM or logging tools miss.",
                "<b>Privacy by design:</b> architecture oriented to minimise PII exposure and support GDPR-aligned processing.",
                "<b>Integration posture:</b> designed as an overlay for cloud AI studios, ERP estates, and existing security stacks—not a rip-and-replace.",
                "<b>Aha! for CISOs:</b> GoverUp makes policy enforceable before tools run—immediate risk reduction without a full platform migration.",
            ],
            s,
        )
    )
    story.append(PageBreak())

    # 4 Strategic answers
    story.append(Paragraph("4. Strategic positioning — resolved answers", s["h1"]))
    story.append(
        Paragraph(
            "The following answers replace open clarification questions with a clear enterprise narrative.",
            s["body"],
        )
    )

    story.append(Paragraph("4.1 Existing ERP / cloud AI integration", s["h2"]))
    story.append(
        Paragraph(
            "<b>Position:</b> Erasys is a <b>Governance Overlay</b>, not a competitor to Azure OpenAI, "
            "GCP Vertex AI, AWS Bedrock, Snowflake Cortex, or ERP suites. It plugs into agent runtimes "
            "and orchestration paths via APIs, webhooks, policy hooks, and marketplace-style "
            "embedding—enforcing trust, policy, HITL, and audit around whatever models and tools the "
            "enterprise already uses.",
            s["body"],
        )
    )
    story.append(
        bullets(
            [
                "<b>Azure / OpenAI Studio:</b> wrap agents and tools with GoverUp policy checks and Aegis approval gates before tool execution.",
                "<b>AWS Bedrock / AgentCore-style stacks:</b> sit as the third-party governance layer for tool allow-lists, audit export, and human approval.",
                "<b>GCP Vertex / ADK-style agents:</b> same overlay pattern—identity, policy, runtime audit, Infosec visibility.",
                "<b>Snowflake Cortex / ERP copilots:</b> govern high-risk actions (data export, write-backs, supplier changes) with policy + HITL, not by replacing the ERP.",
            ],
            s,
        )
    )
    story.append(
        Paragraph(
            "Integration model: <b>sidecar / gateway / SDK hooks</b> into the agent control plane. "
            "Erasys does not require migrating models, data platforms, or ERP systems.",
            s["callout"],
        )
    )

    story.append(Paragraph("4.2 Synergy efficiencies — what Erasys complements vs replaces", s["h2"]))
    story.append(
        Paragraph(
            "Erasys does <b>not</b> claim to replace core identity or endpoint platforms. It fills the "
            "<b>agentic governance gap</b> those products were not built for.",
            s["body"],
        )
    )
    story.append(
        header_table(
            ["Category", "Relationship to Erasys"],
            [
                [
                    "IAM / IdP (Ping, Okta, Entra)",
                    "Complement. Erasys consumes enterprise identity via SSO/OIDC; adds agent-level trust, session attestation, and continuous operator verification (SafePulse).",
                ],
                [
                    "EDR / XDR (CrowdStrike, Cisco Secure, etc.)",
                    "Complement. Endpoint agents protect hosts; Erasys governs <b>agent intent, tools, and policy</b> with audit for Infosec (Sonar).",
                ],
                [
                    "SIEM / SOAR",
                    "Complement. Export tamper-evident audit and threat events into existing SIEM; Erasys is the agentic source of truth.",
                ],
                [
                    "Ad-hoc policy docs / manual reviews",
                    "Displace. GoverUp + ClearFrame automate enforcement and evidence that today lives in spreadsheets and after-the-fact reviews.",
                ],
                [
                    "Homegrown agent gateways",
                    "Displace or absorb. Provide a productised, auditable control plane instead of one-off scripts.",
                ],
            ],
            s,
            [48 * mm, 122 * mm],
        )
    )

    story.append(Paragraph("4.3 Ideal pilot profile", s["h2"]))
    story.append(
        Paragraph(
            "<b>Ideal pilot:</b> a regulated or high-stakes business unit inside a mid-to-large enterprise "
            "(typically Finance, Legal, HR, Tax, Procurement, or Customer Operations) that is already "
            "experimenting with agents on legacy ERP / cloud AI stacks and is blocked by Infosec fear—not "
            "by model quality.",
            s["body"],
        )
    )
    story.append(
        bullets(
            [
                "<b>Prefer:</b> legacy ERP / regulated estates (200–20,000+ employees) with clear compliance owners.",
                "<b>Avoid as first logo:</b> pure startups with no Infosec gate—weak aha! and weak reference value.",
                "<b>Success metric:</b> governed agent sessions with policy denials + HITL approvals + exportable audit evidence—not vanity ROI charts.",
                "<b>Scope:</b> one workflow family (e.g. invoice exception agent, HR case triage, supplier risk screen)—not estate-wide day one.",
            ],
            s,
        )
    )

    story.append(Paragraph("4.4 User journey &amp; deployment cycle", s["h2"]))
    story.append(
        header_table(
            ["Phase", "What happens", "Typical timeline"],
            [
                [
                    "0 — Access",
                    "Shared demo tenant: Builder, GoverUp, Trust Registry, ClearFrame, Aegis, Sonar walkthrough.",
                    "Day 0–3",
                ],
                [
                    "1 — MVG pilot",
                    "Deploy GoverUp + ClearFrame + Aegis on one agent workflow; ingest 3–5 policies; enable HITL for high-risk tools.",
                    "2–6 weeks",
                ],
                [
                    "2 — Hardening",
                    "SSO/OIDC, trusted HTTPS, SIEM export, Vault integrations, role model (admin/operator/auditor).",
                    "4–10 weeks",
                ],
                [
                    "3 — Scale-out",
                    "Add SafePulse + Sonar; expand Trust Registry across agent inventory; portfolio playbooks by BU.",
                    "Quarter 2+",
                ],
                [
                    "4 — Standard",
                    "Prescribe Erasys as Governance Overlay in cloud AI marketplaces / GSI reference architectures.",
                    "Ongoing",
                ],
            ],
            s,
            [28 * mm, 95 * mm, 47 * mm],
        )
    )

    story.append(Paragraph("4.5 Portfolio scale-up (&lt;200 vs &gt;2,000)", s["h2"]))
    story.append(
        bullets(
            [
                "<b>&lt;200 employees:</b> lead with SaaS/demo tenant + GoverUp MVG; light SSO; single Infosec owner. Fast proof, limited SIEM depth.",
                "<b>200–2,000:</b> MVG pilot in one BU; OIDC; audit export; 1–2 production workflows under Aegis.",
                "<b>&gt;2,000 / global:</b> Governance Overlay programme with GSI; marketplace embedding (Bedrock/Vertex/Azure); Sonar as Infosec command centre; phased agent inventory via Trust Registry.",
            ],
            s,
        )
    )
    story.append(PageBreak())

    # GTM
    story.append(Paragraph("5. Go-to-market recommendation", s["h1"]))
    story.append(
        Paragraph(
            "Use <b>all three options in sequence</b>, not as mutually exclusive bets. Sequencing "
            "reduces sales cycle risk while building the partner channel.",
            s["body"],
        )
    )

    story.append(Paragraph("5.1 Primary: Option 3 — Compliance-first pilot (ideal entry)", s["h2"]))
    story.append(
        Paragraph(
            "Lead with a high-stakes legacy ERP / regulated BU pilot. Sell the outcome: "
            "<b>compliance as a scaling catalyst</b>. Product wedge: <b>GoverUp + Aegis + ClearFrame</b> "
            "(Minimum Viable Governance). This creates the reference story Red Hat / GSIs / CISOs need.",
            s["body"],
        )
    )

    story.append(Paragraph("5.2 Secondary: Option 1 — Trojan Horse (expand inside the account)", s["h2"]))
    story.append(
        Paragraph(
            "Where identity anxiety is the buying trigger, lead with <b>SafePulse / Aegis</b> for "
            "agentic authentication and high-risk intervention, then land GoverUp and Sonar. Do not "
            "open with the full suite in enterprise RFPs—it invites platform-replacement fear.",
            s["body"],
        )
    )

    story.append(Paragraph("5.3 Parallel: Option 2 — Compliance-first partner / marketplace", s["h2"]))
    story.append(
        Paragraph(
            "Position Erasys as the <b>prescribed third-party Governance Overlay</b> in AWS / Azure / GCP "
            "AI marketplaces and GSI playbooks (Accenture, Deloitte, Red Hat consulting). This is the "
            "scale motion after 2–3 credible pilots—not the day-one motion.",
            s["body"],
        )
    )

    story.append(Paragraph("5.2 Differentiation vs ERP / cloud AI platforms", s["h2"]))
    story.append(
        header_table(
            ["They provide", "Erasys provides"],
            [
                ["Models, data, orchestration, ERP workflows", "Border control for agents acting on those systems"],
                ["Identity of users (sometimes apps)", "Trust of agents + continuous operator verification + HITL"],
                ["Logging / observability of infra", "Policy enforcement + tamper-evident agent audit evidence"],
                ["“Build agents fast”", "“Scale agents safely” — remove Infosec fear factor"],
            ],
            s,
            [75 * mm, 95 * mm],
        )
    )

    # MVG
    story.append(Paragraph("6. Minimum Viable Governance (MVG)", s["h1"]))
    story.append(
        Paragraph(
            "<b>Lead product: GoverUp</b> — the CISO aha! moment. Immediate value: upload enterprise "
            "policies → auto-parse into enforceable rules → deny / require-approval / allow before tools run.",
            s["body"],
        )
    )
    story.append(
        Paragraph(
            "MVG package for pilots: <b>GoverUp + ClearFrame (runtime audit) + Aegis (HITL)</b>. "
            "Builder is included for agent definition. Trust Registry, SafePulse, and Sonar expand in phase 2.",
            s["callout"],
        )
    )
    story.append(
        bullets(
            [
                "Week 1: ingest policies; register one agent; run governed session.",
                "Week 2–3: enable HITL on high-risk tools; export audit evidence.",
                "Week 4–6: attest frameworks (ISO 42001 / EU AI Act / GDPR evidence collection); executive readout.",
            ],
            s,
        )
    )

    # Demo
    story.append(Paragraph("7. Live pilot demo — access &amp; framing", s["h1"]))
    story.append(
        Paragraph(
            "A shared demonstration tenant is available for partner and client evaluation. Frame it "
            "honestly as a <b>governed AI pilot lab</b>, not estate-wide production deployment.",
            s["body"],
        )
    )
    story.append(
        kv_table(
            [
                ("Product name", "Erasys ClearFrame — AI Governance and Safety"),
                ("Demo URL (HTTP)", "http://52.91.66.29"),
                ("Demo DNS", "http://ec2-52-91-66-29.compute-1.amazonaws.com"),
                ("Login", "admin@erasys.local — password issued in ClearFrame-Demo-Access.txt"),
                ("TLS note", "Use HTTP for this pilot host. HTTPS is self-signed and will trigger browser warnings."),
                ("Demo framing", "Governance Overlay pilot — policy, HITL, audit, agent registry"),
                ("What to show", "Builder → GoverUp policy upload → Aegis approve/block → ClearFrame audit → Sonar / Metrics"),
                ("What not to claim", "ISO certification, estate-wide deployment, replacement of IdP/EDR/ERP, fake ROI"),
            ],
            s,
            [40 * mm, 130 * mm],
        )
    )
    story.append(Spacer(1, 3 * mm))
    story.append(
        Paragraph(
            "Rotate credentials after external partner sharing. Frame as a governed AI pilot lab, not production HA.",
            s["body"],
        )
    )

    # Honest limits
    story.append(Paragraph("8. Honest scope (builds trust)", s["h1"]))
    story.append(
        bullets(
            [
                "Single-server / pilot-tenant demonstration is not multi-region HA production.",
                "SSO/OIDC is supported but must be configured per customer IdP.",
                "Trusted HTTPS requires a customer domain and CA-issued certificate.",
                "Platform collects technical evidence for ISO 42001 / EU AI Act / GDPR — it does not confer certification.",
                "LLM backends and ERP connectors are integration workstreams, not magic day-one coverage of every system.",
            ],
            s,
        )
    )

    # Talking point
    story.append(Paragraph("9. Recommended stakeholder paragraph", s["h1"]))
    story.append(
        Paragraph(
            "“Erasys is the Governance-as-Code overlay for agentic AI—border control for who builds, "
            "who operates, what agents are trusted to do, and how every high-risk action is approved "
            "and audited. We do not replace your cloud AI platform or ERP. We make it safe to scale "
            "agents on top of them. Our Minimum Viable Governance entry is GoverUp: your policies "
            "become enforceable controls in the agent path, with human-in-the-loop and tamper-evident "
            "audit—so Infosec can approve production AI without security debt.”",
            s["callout"],
        )
    )

    story.append(Spacer(1, 8 * mm))
    story.append(
        Paragraph(
            "Next step: book a 30-minute MVG demo (GoverUp → Aegis → ClearFrame) with the prospect’s "
            "CISO or AI platform owner, scoped to one Finance / Legal / HR workflow.",
            s["body"],
        )
    )

    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    print(OUT)


if __name__ == "__main__":
    build()
