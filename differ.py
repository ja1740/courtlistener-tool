# WHAT THIS FILE DOES:
# Gives the tool its memory. After every fetch run it saves a snapshot
# of all the cases found. On the next run it loads that snapshot,
# compares it to the new results, and reports what changed.
#
# WHY IT EXISTS:
# A lawyer running this tool weekly needs to immediately see what is new,
# what disappeared, and what was updated — without reading every case again.
#
# HOW IT FITS INTO THE PROJECT:
# main.py calls load_last_snapshot() before fetching, then diff_snapshots()
# after fetching, then save_snapshot() to store the new results.
# The changes dict is passed to reporter.py to appear in the report.

import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def build_snapshot_record(case):
    """
    Pulls just the key fields out of a case record to store in the snapshot.
    We only save the fields we need for comparison, not the full record.
    Takes one case dictionary. Returns a smaller dictionary for the snapshot.
    """
    return {
        "cluster_id": case.get("cluster_id", ""),
        "case_name": case.get("case_name", "Unknown"),
        "date_filed": case.get("date_filed", ""),
        "court": case.get("court", ""),
        "docket_number": case.get("docket_number", ""),
        "citation": case.get("citation", ""),
    }


def save_snapshot(results, snapshots_dir):
    """
    Saves the current run's results as a JSON file in the snapshots/ folder.
    The filename includes today's date so each run gets its own file.
    Takes the list of case records and the folder path.
    """
    # --- Step 1: Create the snapshots/ folder if it does not exist ---
    os.makedirs(snapshots_dir, exist_ok=True)

    # --- Step 2: Build the snapshot filename with today's date ---
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot_filename = f"snapshot_{today}.json"
    snapshot_path = os.path.join(snapshots_dir, snapshot_filename)

    # --- Step 3: Build a list of snapshot records from the results ---
    snapshot_data = [build_snapshot_record(case) for case in results]

    # --- Step 4: Write the snapshot to disk as a JSON file ---
    with open(snapshot_path, "w", encoding="utf-8") as snapshot_file:
        json.dump(snapshot_data, snapshot_file, indent=2)

    logger.info(f"Snapshot saved to: {snapshot_path}")


def load_last_snapshot(snapshots_dir):
    """
    Finds and loads the most recent snapshot file from the snapshots/ folder.
    Returns a list of case records from the last run, or None if no snapshots exist.
    This is how the tool remembers what it found last time.
    """
    # --- Step 1: Check if the snapshots folder even exists ---
    if not os.path.exists(snapshots_dir):
        logger.info("No snapshots folder found. This appears to be the first run.")
        return None

    # --- Step 2: Get a list of all snapshot files ---
    snapshot_files = [
        filename for filename in os.listdir(snapshots_dir)
        if filename.startswith("snapshot_") and filename.endswith(".json")
    ]

    if not snapshot_files:
        logger.info("No snapshot files found. This appears to be the first run.")
        return None

    # --- Step 3: Sort by filename (which includes the date) to find the most recent ---
    snapshot_files.sort()
    most_recent_file = snapshot_files[-1]
    snapshot_path = os.path.join(snapshots_dir, most_recent_file)

    # --- Step 4: Load and return the snapshot data ---
    try:
        with open(snapshot_path, "r", encoding="utf-8") as snapshot_file:
            snapshot_data = json.load(snapshot_file)
        logger.info(f"Loaded prior snapshot: {most_recent_file} ({len(snapshot_data)} cases)")
        return snapshot_data
    except Exception as error:
        logger.error(f"Could not read snapshot file {most_recent_file}: {error}")
        return None


def diff_snapshots(old_snapshot, new_results):
    """
    Compares the previous snapshot to the new results and finds what changed.
    Takes the old snapshot (list of dicts) and new results (list of dicts).
    Returns a dictionary with three lists: new cases, dropped cases, updated cases.
    Returns None if there is no old snapshot to compare against.
    """
    # If there is no prior snapshot, there is nothing to compare
    if old_snapshot is None:
        return None

    # --- Step 1: Build lookup dictionaries keyed by cluster_id ---
    # This makes it fast to check if a case exists in either set
    old_by_id = {case["cluster_id"]: case for case in old_snapshot}
    new_by_id = {case["cluster_id"]: build_snapshot_record(case) for case in new_results}

    # --- Step 2: Find new cases (in new results but not in old snapshot) ---
    new_cases = [
        new_by_id[cluster_id]
        for cluster_id in new_by_id
        if cluster_id not in old_by_id
    ]

    # --- Step 3: Find dropped cases (in old snapshot but not in new results) ---
    dropped_cases = [
differ.py        for cluster_id in old_by_id
        if cluster_id not in new_by_id
    ]

    # --- Step 4: Find updated cases (same cluster_id but different field values) ---
    updated_cases = []
    for cluster_id in new_by_id:
        if cluster_id in old_by_id:
            old_case = old_by_id[cluster_id]
            new_case = new_by_id[cluster_id]

            # Check each field we care about for changes
            changed_fields = []
            for field in ["date_filed", "docket_number", "citation"]:
                if old_case.get(field) != new_case.get(field):
                    changed_fields.append(field)

            # If any fields changed, record this case as updated
            if changed_fields:
                updated_case = new_case.copy()
                updated_case["change_note"] = f"changed fields: {', '.join(changed_fields)}"
                updated_cases.append(updated_case)

    logger.info(
        f"Diff complete: {len(new_cases)} new, "
        f"{len(dropped_cases)} dropped, "
        f"{len(updated_cases)} updated."
    )

    return {
        "new": new_cases,
        "dropped": dropped_cases,
        "updated": updated_cases,
    }
