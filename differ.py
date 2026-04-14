import os
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

_EASTERN = ZoneInfo("America/New_York")

logger = logging.getLogger(__name__)


def build_snapshot_record(case):
    return {
        "cluster_id":    case.get("cluster_id", ""),
        "case_name":     case.get("case_name", "Unknown"),
        "date_filed":    case.get("date_filed", ""),
        "court":         case.get("court", ""),
        "docket_number": case.get("docket_number", ""),
        "citation":      case.get("citation", ""),
    }


def save_snapshot(results, snapshots_dir):
    os.makedirs(snapshots_dir, exist_ok=True)
    today = datetime.now(tz=_EASTERN).strftime("%Y-%m-%d")
    path  = os.path.join(snapshots_dir, f"snapshot_{today}.json")
    data  = [build_snapshot_record(c) for c in results]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Snapshot saved to: {path}")


def cleanup_snapshots(snapshots_dir, keep=30):
    """Keep only the most recent `keep` snapshot files; delete the rest."""
    if not os.path.exists(snapshots_dir):
        return
    files = sorted(
        f for f in os.listdir(snapshots_dir)
        if f.startswith("snapshot_") and f.endswith(".json")
    )
    to_delete = files[:-keep] if len(files) > keep else []
    for filename in to_delete:
        os.remove(os.path.join(snapshots_dir, filename))
    if to_delete:
        logger.info(f"Removed {len(to_delete)} old snapshot(s).")


def load_last_snapshot(snapshots_dir):
    if not os.path.exists(snapshots_dir):
        return None
    files = sorted(
        f for f in os.listdir(snapshots_dir)
        if f.startswith("snapshot_") and f.endswith(".json")
    )
    if not files:
        return None
    path = os.path.join(snapshots_dir, files[-1])
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"Loaded prior snapshot: {files[-1]} ({len(data)} cases)")
        return data
    except Exception as e:
        logger.error(f"Could not read snapshot {files[-1]}: {e}")
        return None
