from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skyminer.config import SkyMinerConfig
from skyminer.persistence.database import Database
from skyminer.utils.io import ensure_dir, safe_filename


@dataclass(frozen=True)
class EmailPacket:
    run_id: str
    out_dir: Path
    draft_txt: Path
    draft_md: Path
    recipients_md: Path
    manifest_json: Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(s: str | None) -> dict[str, Any]:
    if not s:
        return {}
    try:
        return json.loads(s)
    except Exception:
        return {}


def prepare_email_packet(
    cfg: SkyMinerConfig,
    *,
    run_id: str,
    max_candidates: int = 8,
) -> EmailPacket:
    """Prepare a submission-oriented email draft + attachment packet for a run.

    This does not send email. It creates files under outputs/emails/run_<run_id>/.
    """

    outputs = ensure_dir(cfg.paths.outputs_dir)
    out_dir = ensure_dir(outputs / "emails" / f"run_{run_id}")
    packet_dir = ensure_dir(out_dir / "packet")

    reports_dir = outputs / "reports"
    plots_dir = outputs / "plots"
    candidates_dir = outputs / "candidates"

    db = Database(cfg.paths.db_path)
    with db.connect() as conn:
        pr = conn.execute(
            "SELECT started_at, mode, params_json FROM pipeline_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if pr is None:
            raise ValueError(f"Unknown run_id: {run_id}")
        started_at = str(pr["started_at"])
        mode = str(pr["mode"])
        params = _load_json(pr["params_json"])

        cand_rows = conn.execute(
            """
            SELECT candidate_id, source, target_id, total_score, validation_json
            FROM candidates
            WHERE run_id = ?
            ORDER BY total_score DESC, candidate_id ASC
            LIMIT ?
            """,
            (run_id, int(max_candidates)),
        ).fetchall()

        candidates: list[dict[str, Any]] = []
        for r in cand_rows:
            v = _load_json(r["validation_json"])
            candidates.append(
                {
                    "candidate_id": str(r["candidate_id"]),
                    "source": str(r["source"]),
                    "target_id": str(r["target_id"]),
                    "total_score": float(r["total_score"]),
                    "validation_status": v.get("status"),
                    "matched_name": v.get("matched_name"),
                    "matched_type": v.get("matched_type"),
                }
            )

    # Attach key run artifacts (if present).
    attachments: list[dict[str, str]] = []

    def add_attachment(p: Path, label: str) -> None:
        if not p.exists():
            return
        dest = packet_dir / p.name
        try:
            shutil.copy2(p, dest)
        except Exception:
            # If copy fails, keep original reference.
            dest = p
        attachments.append({"label": label, "path": str(dest)})

    add_attachment(reports_dir / f"run_summary_{run_id}.html", "Run summary (HTML)")
    add_attachment(reports_dir / f"run_summary_{run_id}.json", "Run summary (JSON)")
    add_attachment(candidates_dir / f"ranked_{run_id}.json", "Ranked candidates (JSON)")

    for c in candidates:
        cid = c["candidate_id"]
        base = safe_filename(cid)
        add_attachment(reports_dir / f"{base}.md", f"Candidate report (MD): {cid}")
        add_attachment(reports_dir / f"{base}.json", f"Candidate JSON: {cid}")
        add_attachment(plots_dir / f"{base}_lightcurve.png", f"Light curve plot: {cid}")
        add_attachment(plots_dir / f"{base}_periodogram.png", f"Periodogram plot: {cid}")

    recipients_md = out_dir / "recipients.md"
    recipients_md.write_text(
        """# Potential Recipients / Submission Channels (Verify Before Sending)

SkyMiner produces **candidates**, not confirmed discoveries. Where to send depends on what the object likely is.

## Variable Stars / Stellar Variability
- **AAVSO VSX (Variable Star Index)**: common community catalog for variable star submissions.
  - Typical workflow is a submission form/portal, not necessarily email.

## Catalog Cross-Match / Metadata Issues
- **MAST Help Desk** (if you believe a product/metadata issue exists in MAST).

## If the signal looks exoplanet-like (transits)
- **TESS Follow-up Observing Program (TFOP)**: has its own vetting and submission channels.

## Internal Review
- Your internal team distribution list for a first-pass sanity check.

Note: addresses and portals change. Use official websites to confirm the correct submission path.
""",
        encoding="utf-8",
    )

    table_lines = []
    for c in candidates:
        table_lines.append(
            f"- {c['candidate_id']}: score={c['total_score']:.3f}, validation={c.get('validation_status')}, match={c.get('matched_name') or 'N/A'}"
        )
    cand_block = "\n".join(table_lines) if table_lines else "- (No candidates in this run.)"

    draft_txt = out_dir / "email_draft.txt"
    draft_md = out_dir / "email_draft.md"

    subject = f"SkyMiner candidate triage - run {run_id} - {started_at}"
    body = f"""Subject: {subject}

Hello,

This is a SkyMiner **candidate** triage packet from an automated run.

Run details:
- Run ID: {run_id}
- Started at (UTC): {started_at}
- Mode: {mode}
- Inputs: {json.dumps(params, default=str)}

Top candidates (preliminary, not confirmed):
{cand_block}

Attachments:
{chr(10).join([f"- {a['label']}: {a['path']}" for a in attachments]) if attachments else "- (No attachments found.)"}

Cautions:
- These are **candidates** only. SkyMiner does not confirm discoveries.
- “No match” in catalogs is not proof of novelty; it is only a prioritization signal.

Suggested next steps:
1. Review the attached run summary HTML and the top candidate plots.
2. Manually validate with additional catalogs and context (proper motion, blends, systematics).
3. If still compelling, prepare a formal submission through the appropriate channel (see recipients.md).

Generated at (UTC): {_utc_now()}
"""

    draft_txt.write_text(body, encoding="utf-8")
    draft_md.write_text("```\n" + body + "\n```", encoding="utf-8")

    manifest = {
        "run_id": run_id,
        "generated_at_utc": _utc_now(),
        "attachments": attachments,
        "candidates": candidates,
        "notes": "Verify recipients/submission channels before sending.",
    }
    manifest_json = out_dir / "manifest.json"
    manifest_json.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    readme = out_dir / "README.txt"
    readme.write_text(
        "This folder contains a draft email and a packet/ directory with attachments for run "
        + run_id
        + ".\n\nOpen email_draft.txt, review candidates, then use recipients.md to choose the right submission path.\n",
        encoding="utf-8",
    )

    return EmailPacket(
        run_id=run_id,
        out_dir=out_dir,
        draft_txt=draft_txt,
        draft_md=draft_md,
        recipients_md=recipients_md,
        manifest_json=manifest_json,
    )

