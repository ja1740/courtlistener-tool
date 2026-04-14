import os
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

_EASTERN = ZoneInfo("America/New_York")

logger = logging.getLogger(__name__)


def _case_key(case):
    """Stable dedup key: prefer docket number, fall back to case_name|court."""
    docket = (case.get("docket_number") or "").strip()
    if docket and docket != "N/A":
        return docket
    return f"{case.get('case_name', '')}|{case.get('court', '')}"


def load_master(master_path):
    if not os.path.exists(master_path):
        return {}
    with open(master_path, encoding="utf-8") as f:
        return json.load(f)


def merge_into_master(master, new_results):
    """Add cases not already in master. Returns list of newly added cases."""
    added = []
    for case in new_results:
        key = _case_key(case)
        if key not in master:
            master[key] = {
                "case_name":     case.get("case_name", "Unknown"),
                "citation":      case.get("citation", "N/A"),
                "court":         case.get("court", "Unknown"),
                "date_filed":    case.get("date_filed", "Unknown"),
                "docket_number": case.get("docket_number", "N/A"),
            }
            added.append(master[key])
        else:
            existing = master[key]
            if (not existing.get("citation") or existing["citation"] == "N/A") \
                    and case.get("citation") and case["citation"] != "N/A":
                existing["citation"] = case["citation"]
    return added


def save_master(master, master_path):
    with open(master_path, "w", encoding="utf-8") as f:
        json.dump(master, f, indent=2)
    logger.info(f"Master list saved: {len(master)} unique case(s).")


def format_case_table(cases):
    sorted_cases = sorted(cases, key=lambda c: c.get("date_filed", ""), reverse=True)
    lines = [
        "| Case Name | Citation | Court | Date Filed | Docket No. |",
        "|-----------|----------|-------|------------|------------|",
    ]
    for case in sorted_cases:
        name = (case.get("case_name") or "Unknown")[:60]
        lines.append(
            f"| {name} "
            f"| {case.get('citation', 'N/A')} "
            f"| {case.get('court', 'Unknown')} "
            f"| {case.get('date_filed', 'Unknown')} "
            f"| {case.get('docket_number', 'N/A')} |"
        )
    return "\n".join(lines)


def format_new_cases_section(added):
    if not added:
        return "## New Cases This Run\n\nNone.\n"
    lines = [f"## New Cases This Run ({len(added)})\n"]
    for c in sorted(added, key=lambda x: x.get("date_filed", ""), reverse=True):
        lines.append(
            f"- **{c.get('case_name', 'Unknown')}** — "
            f"{c.get('court', '')} ({c.get('date_filed', '')})"
        )
    return "\n".join(lines)


def format_errors_section(errors):
    if not errors:
        return "## Download Errors\n\nNone.\n"
    seen, deduped = set(), []
    for e in errors:
        name = e.get("case_name", "Unknown")
        if name not in seen:
            seen.add(name)
            deduped.append(e)
    lines = [f"## Download Errors ({len(deduped)} case(s) affected)\n"]
    for e in deduped:
        raw = e.get("error", "?")
        if "404" in raw:
            reason = "404 — document not publicly available (may require court login)"
        elif "403" in raw:
            reason = "403 — court website blocked automated access"
        elif "SSL" in raw or "certificate" in raw.lower():
            reason = "SSL error — certificate issue with court's server"
        else:
            reason = raw[:120]
        lines.append(f"- **{e.get('case_name', 'Unknown')}**: {reason}")
    return "\n".join(lines)


def cleanup_reports(reports_dir, keep=30):
    """Keep only the most recent `keep` report files; delete the rest."""
    if not os.path.exists(reports_dir):
        return
    reports = sorted(
        f for f in os.listdir(reports_dir)
        if f.startswith("report_") and f.endswith(".md")
    )
    to_delete = reports[:-keep] if len(reports) > keep else []
    for filename in to_delete:
        os.remove(os.path.join(reports_dir, filename))
    if to_delete:
        logger.info(f"Removed {len(to_delete)} old report(s).")


def write_report(master, added, query, filed_after, max_results, court, errors, reports_dir):
    os.makedirs(reports_dir, exist_ok=True)
    now      = datetime.now(tz=_EASTERN)
    run_time = now.strftime("%Y-%m-%d at %I:%M %p ET")
    today    = now.strftime("%Y-%m-%d")
    path     = os.path.join(reports_dir, f"report_{today}.md")
    header = f"""# CourtListener AI Copyright Case Tracker
## Run Report — {run_time}

## Search Parameters
- **Query:** {query[:200]}
- **Filed After:** {filed_after}
- **Max Results per Run:** {max_results}
- **Court Filter:** {court or 'None (all courts)'}
- **Total Unique Cases on Record:** {len(master)}
- **Added This Run:** {len(added)}
"""
    full_report = "\n".join([
        header,
        f"## All Cases\n\n{format_case_table(list(master.values()))}\n",
        format_new_cases_section(added),
        format_errors_section(errors),
    ])
    with open(path, "w", encoding="utf-8") as f:
        f.write(full_report)
    logger.info(f"Report saved to: {path}")
    return path
