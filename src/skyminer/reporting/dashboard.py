from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skyminer.config import SkyMinerConfig
from skyminer.persistence.database import Database
from skyminer.utils.io import ensure_dir, safe_filename


@dataclass(frozen=True)
class RunRow:
    run_id: str
    started_at: str
    mode: str
    params: dict[str, Any]
    targets_ingested: int
    candidates_total: int
    candidates_scored: int
    candidates_interesting: int
    candidates_rejected: int
    top_score: float | None
    newest_data_release_utc: str | None


def _read_json(p: Path) -> dict[str, Any] | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _try_extract_release(meta: dict[str, Any] | None) -> str | None:
    if not meta:
        return None
    for k in ("mast_product_release_utc", "generated_at_utc", "downloaded_at_utc"):
        v = meta.get(k)
        if v:
            return str(v)
    return None


def _html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def generate_dashboard(cfg: SkyMinerConfig, *, limit_runs: int = 30, top_k_per_run: int = 15) -> Path:
    """Generate a static HTML dashboard under outputs/dashboard/.

    This is intentionally not a web app: just a local HTML file with links to artifacts.
    """

    outputs = ensure_dir(cfg.paths.outputs_dir)
    dash_dir = ensure_dir(outputs / "dashboard")
    reports_dir = ensure_dir(outputs / "reports")
    plots_dir = ensure_dir(outputs / "plots")
    emails_dir = ensure_dir(outputs / "emails")

    db = Database(cfg.paths.db_path)
    rows: list[RunRow] = []

    with db.connect() as conn:
        run_rows = conn.execute(
            """
            SELECT run_id, started_at, mode, params_json
            FROM pipeline_runs
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (int(limit_runs),),
        ).fetchall()

        for r in run_rows:
            run_id = str(r["run_id"])
            started_at = str(r["started_at"])
            mode = str(r["mode"])
            try:
                params = json.loads(r["params_json"]) if r["params_json"] else {}
            except Exception:
                params = {}

            counts = conn.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN score_json IS NOT NULL THEN 1 ELSE 0 END) AS scored,
                       MAX(total_score) AS top_score
                FROM candidates
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            total = int(counts["total"] or 0)
            scored = int(counts["scored"] or 0)
            top_score = float(counts["top_score"]) if counts["top_score"] is not None else None

            # Prefer the run_summary JSON (it captures ingestion counts deterministically).
            run_summary_json = reports_dir / f"run_summary_{run_id}.json"
            summary = _read_json(run_summary_json) or {}
            targets_ingested = int(summary.get("targets_ingested") or 0)
            candidates_interesting = int(summary.get("candidates_interesting") or 0)
            candidates_rejected = int(summary.get("candidates_rejected") or 0)

            newest_release: str | None = None
            top = conn.execute(
                """
                SELECT source, target_id
                FROM candidates
                WHERE run_id = ?
                ORDER BY total_score DESC, candidate_id ASC
                LIMIT ?
                """,
                (run_id, int(top_k_per_run)),
            ).fetchall()
            for c in top:
                t = conn.execute(
                    "SELECT meta_json FROM targets WHERE source = ? AND target_id = ?",
                    (str(c["source"]), str(c["target_id"])),
                ).fetchone()
                meta = None
                if t and t["meta_json"]:
                    try:
                        meta = json.loads(t["meta_json"])
                    except Exception:
                        meta = None
                rel = _try_extract_release(meta)
                if rel and (newest_release is None or str(rel) > str(newest_release)):
                    newest_release = str(rel)

            rows.append(
                RunRow(
                    run_id=run_id,
                    started_at=started_at,
                    mode=mode,
                    params=params,
                    targets_ingested=targets_ingested,
                    candidates_total=total,
                    candidates_scored=scored,
                    candidates_interesting=candidates_interesting,
                    candidates_rejected=candidates_rejected,
                    top_score=top_score,
                    newest_data_release_utc=newest_release,
                )
            )

    cards_html = []
    for rr in rows:
        run_summary_html = reports_dir / f"run_summary_{rr.run_id}.html"
        ranked_json = outputs / "candidates" / f"ranked_{rr.run_id}.json"
        email_dir = emails_dir / f"run_{rr.run_id}"

        links = []
        if run_summary_html.exists():
            links.append(f"<a href='../reports/{run_summary_html.name}'>Run summary</a>")
        if ranked_json.exists():
            links.append(f"<a href='../candidates/{ranked_json.name}'>Ranked JSON</a>")
        if email_dir.exists():
            links.append(f"<a href='../emails/run_{rr.run_id}/'>Email packet</a>")

        params_pretty = _html_escape(json.dumps(rr.params, indent=2, default=str))
        freshness = rr.newest_data_release_utc or "N/A"
        top_score = f"{rr.top_score:.3f}" if rr.top_score is not None else "N/A"

        cards_html.append(
            f"""
            <article class="run-card">
              <header class="run-head">
                <div class="run-title">
                  <div class="rid">Run <code>{_html_escape(rr.run_id)}</code></div>
                  <div class="meta">{_html_escape(rr.started_at)} (mode: <code>{_html_escape(rr.mode)}</code>)</div>
                </div>
                <div class="kpis">
                  <div class="kpi"><div class="k">Ingested</div><div class="v">{rr.targets_ingested}</div></div>
                  <div class="kpi"><div class="k">Scored</div><div class="v">{rr.candidates_scored}</div></div>
                  <div class="kpi"><div class="k">Interesting</div><div class="v">{rr.candidates_interesting}</div></div>
                  <div class="kpi"><div class="k">Top score</div><div class="v">{top_score}</div></div>
                  <div class="kpi"><div class="k">Newest publish</div><div class="v">{_html_escape(freshness)}</div></div>
                </div>
              </header>

              <div class="links">{' | '.join(links) if links else '<span class="na">No artifacts found</span>'}</div>

              <details>
                <summary>Inputs (click to expand)</summary>
                <pre class="code">{params_pretty}</pre>
              </details>
            </article>
            """
        )

    generated_at = datetime.now(timezone.utc).isoformat()
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SkyMiner Dashboard</title>
  <style>
    :root {{
      --bg: #0b1020;
      --panel: rgba(255,255,255,0.06);
      --border: rgba(255,255,255,0.10);
      --text: rgba(255,255,255,0.92);
      --muted: rgba(255,255,255,0.68);
      --accent: #7dd3fc;
      --good: #34d399;
      --warn: #fbbf24;
      --bad: #fb7185;
      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      --sans: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
    }}
    body {{
      margin: 0;
      font-family: var(--sans);
      color: var(--text);
      background:
        radial-gradient(900px 600px at 15% 15%, rgba(125,211,252,0.18), transparent 60%),
        radial-gradient(900px 600px at 85% 20%, rgba(52,211,153,0.12), transparent 60%),
        radial-gradient(900px 700px at 40% 85%, rgba(251,113,133,0.10), transparent 60%),
        var(--bg);
    }}
    header.page {{
      padding: 22px 22px 12px 22px;
      position: sticky;
      top: 0;
      backdrop-filter: blur(10px);
      background: linear-gradient(to bottom, rgba(11,16,32,0.92), rgba(11,16,32,0.70));
      border-bottom: 1px solid var(--border);
      z-index: 10;
    }}
    .brand {{
      display: flex;
      align-items: baseline;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .brand h1 {{ margin: 0; font-size: 18px; letter-spacing: 0.2px; }}
    .brand .sub {{ color: var(--muted); font-size: 13px; }}
    .toolbar {{
      margin-top: 10px;
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }}
    input[type="search"] {{
      width: min(520px, 100%);
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.06);
      color: var(--text);
      outline: none;
    }}
    input[type="search"]::placeholder {{ color: rgba(255,255,255,0.55); }}
    main {{
      padding: 18px 22px 60px 22px;
      max-width: 1200px;
      margin: 0 auto;
    }}
    .run-card {{
      border: 1px solid var(--border);
      background: var(--panel);
      border-radius: 18px;
      padding: 14px 14px 12px 14px;
      margin: 14px 0;
    }}
    .run-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .rid {{ font-weight: 700; }}
    code {{ font-family: var(--mono); font-size: 12.5px; background: rgba(0,0,0,0.25); padding: 2px 6px; border-radius: 8px; }}
    .meta {{ color: var(--muted); font-size: 13px; margin-top: 4px; }}
    .kpis {{
      display: grid;
      grid-template-columns: repeat(5, minmax(120px, 1fr));
      gap: 10px;
      min-width: min(560px, 100%);
    }}
    .kpi {{
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 10px 10px;
      background: rgba(0,0,0,0.15);
    }}
    .kpi .k {{ color: var(--muted); font-size: 12px; }}
    .kpi .v {{ font-weight: 750; margin-top: 2px; }}
    .links {{ margin-top: 10px; color: var(--muted); }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    details {{ margin-top: 10px; }}
    summary {{ cursor: pointer; color: var(--muted); }}
    pre.code {{
      white-space: pre-wrap;
      background: rgba(0,0,0,0.22);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 10px 12px;
      overflow: auto;
      font-family: var(--mono);
      color: rgba(255,255,255,0.86);
      margin: 10px 0 0 0;
    }}
    .na {{ color: rgba(255,255,255,0.55); }}
    footer {{
      color: var(--muted);
      font-size: 12px;
      margin-top: 26px;
    }}
    @media (max-width: 900px) {{
      .kpis {{ grid-template-columns: repeat(2, minmax(120px, 1fr)); }}
    }}
  </style>
</head>
<body>
  <header class="page">
    <div class="brand">
      <h1>SkyMiner Dashboard</h1>
      <div class="sub">Local static dashboard. Generated at (UTC): <code>{generated_at}</code></div>
    </div>
    <div class="toolbar">
      <input id="filter" type="search" placeholder="Filter runs by run id / mode / JSON params…" />
      <div class="sub">Tip: newest “publish” timestamps come from <code>mast_product_release_utc</code> when available.</div>
    </div>
  </header>

  <main id="runs">
    {''.join(cards_html) if cards_html else '<p class="na">No runs found yet. Run the pipeline once, then re-generate the dashboard.</p>'}
    <footer>
      This dashboard is for triage and workflow. It does not confirm discoveries. Always validate before submission.
    </footer>
  </main>

  <script>
    const input = document.getElementById('filter');
    const runs = document.getElementById('runs');
    input.addEventListener('input', () => {{
      const q = input.value.toLowerCase().trim();
      for (const card of runs.querySelectorAll('.run-card')) {{
        const t = card.innerText.toLowerCase();
        card.style.display = (!q || t.includes(q)) ? '' : 'none';
      }}
    }});
  </script>
</body>
</html>
"""

    out_path = dash_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path
