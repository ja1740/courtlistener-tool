# WHAT THIS FILE DOES:
# Builds the markdown report that summarizes each run.
# It takes the list of cases found, any changes detected, and
# any download errors, and writes them into a readable .md file.
#
# WHY IT EXISTS:
# A lawyer running this tool weekly needs a clean, readable summary
# they can open and scan immediately. This file produces that output.
#
# HOW IT FITS INTO THE PROJECT:
# main.py calls write_report() after fetcher.py and differ.py have
# finished. The report is saved to the reports/ folder.

import os
from datetime import datetime


def format_case_table(results):
    """
    Creates a markdown table listing every case that was retrieved.
    Takes the list of case records from fetcher.py.
    Returns a multi-line string containing the formatted markdown table.
    """
    # Table header row
    table_lines = [
        "| Case Name | Citation | Court | Date Filed | Docket No. | Documents | PDF Status |",
        "|-----------|----------|-------|------------|------------|-----------|------------|",
    ]

    # Add one row per case
    for case in results:
        # Count how many documents are in this cluster
        doc_count = len(case.get("doc_count", []))

        # Truncate long case names so the table stays readable
        case_name = case.get("case_name", "Unknown")[:60]

        row = (
            f"| {case_name} "
            f"| {case.get(\'citation\', \'N/A\')} "
            f"| {case.get(\'court\', \'Unknown\')} "
            f"| {case.get(\'date_filed\', \'Unknown\')} "
            f"| {case.get(\'docket_number\', \'N/A\')} "
            f"| {doc_count} "
            f"| {case.get(\'pdf_status\', \'Unknown\')} |"
        )
        table_lines.append(row)

    return "\n".join(table_lines)


def format_changes_section(changes):
    """
    Creates the \'Changes Since Last Run\' section of the report.
    Takes the changes dictionary produced by differ.py.
    Returns a formatted markdown string listing new, dropped, and updated cases.
    """
    # If this is the first run, there is nothing to compare
    if changes is None:
        return "## Changes Since Last Run\n\nThis is the first run. No prior results to compare.\n"

    new_cases = changes.get("new", [])
    dropped_cases = changes.get("dropped", [])
    updated_cases = changes.get("updated", [])

    lines = ["## Changes Since Last Run\n"]

    # List new cases
    lines.append(f"### New Cases ({len(new_cases)})")
    if new_cases:
        for case in new_cases:
            lines.append(f"- {case.get(\'case_name\', \'Unknown\')} ({case.get(\'date_filed\', \'Unknown\')})")
    else:
        lines.append("- None")

    lines.append("")

    # List dropped cases
    lines.append(f"### Dropped Cases ({len(dropped_cases)})")
    if dropped_cases:
        for case in dropped_cases:
            lines.append(f"- {case.get(\'case_name\', \'Unknown\')} ({case.get(\'date_filed\', \'Unknown\')})")
    else:
        lines.append("- None")

    lines.append("")

    # List updated cases
    lines.append(f"### Updated Cases ({len(updated_cases)})")
    if updated_cases:
        for case in updated_cases:
            lines.append(f"- {case.get(\'case_name\', \'Unknown\')} — {case.get(\'change_note\', \'fields changed\')}")
    else:
        lines.append("- None")

    return "\n".join(lines)


def format_errors_section(errors):
    """
    Creates a section listing any PDFs that failed to download.
    Takes the list of error records from fetcher.py.
    Returns a formatted markdown string.
    """
    if not errors:
        return "## Download Errors\n\nNo errors.\n"

    lines = [f"## Download Errors ({len(errors)} total)\n"]
    for error_record in errors:
        lines.append(f"- **{error_record.get(\'case_name\', \'Unknown\')}** ({error_record.get(\'cluster_id\', \'\')}): {error_record.get(\'error\', \'Unknown error\')}")

    return "\n".join(lines)


def write_report(results, changes, params, errors, reports_dir):
    """
    The main function called by main.py.
    Assembles all sections into a single markdown file and saves it.
    Takes the results, changes, search params, errors, and output folder.
    """
    # --- Step 1: Create the reports/ folder if it does not exist ---
    os.makedirs(reports_dir, exist_ok=True)

    # --- Step 2: Build the report filename using today\'s date ---
    today = datetime.now().strftime("%Y-%m-%d")
    run_time = datetime.now().strftime("%Y-%m-%d at %H:%M:%S")
    report_filename = f"report_{today}.md"
    report_path = os.path.join(reports_dir, report_filename)

    # --- Step 3: Build each section of the report ---
    header = f"""# CourtListener AI Copyright Case Tracker
## Run Report — {run_time}

## Search Parameters
- **Query:** {params.get(\'query\', \'N/A\')[:200]}
- **Filed After:** {params.get(\'filed_after\', \'N/A\')}
- **Max Results:** {params.get(\'max_results\', \'N/A\')}
- **Court Filter:** {params.get(\'court\') or \'None (all courts)\'}
- **Total Cases Retrieved:** {len(results)}
- **Download Errors:** {len(errors)}
"""

    case_table = f"## Cases Retrieved\n\n{format_case_table(results)}\n"
    changes_section = format_changes_section(changes)
    errors_section = format_errors_section(errors)

    # --- Step 4: Combine all sections into the final report ---
    full_report = "\n".join([header, case_table, changes_section, errors_section])

    # --- Step 5: Write the report file to disk ---
    with open(report_path, "w", encoding="utf-8") as report_file:
        report_file.write(full_report)

    print(f"Report saved to: {report_path}")
