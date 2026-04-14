import os
import logging
import sqlite3

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def ensure_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE IF NOT EXISTS cases (
        cluster_id TEXT PRIMARY KEY,
        case_name  TEXT,
        court      TEXT,
        date_filed TEXT,
        text       TEXT
    )""")
    conn.commit()
    conn.close()


def extract_text_from_pdf(pdf_path):
    try:
        doc  = fitz.open(pdf_path)
        text = "".join(page.get_text() for page in doc)
        doc.close()
        return text
    except Exception as e:
        logger.error(f"Could not extract text from {pdf_path}: {e}")
        return ""


def extract_text_from_file(file_path):
    """Extract text from either a .txt or .pdf opinion file."""
    if file_path.endswith(".txt"):
        with open(file_path, encoding="utf-8") as f:
            return f.read()
    return extract_text_from_pdf(file_path)


def is_already_indexed(cluster_id, db_path):
    conn = sqlite3.connect(db_path)
    row  = conn.execute(
        "SELECT 1 FROM cases WHERE cluster_id = ? AND case_name != 'See snapshot'",
        (cluster_id,),
    ).fetchone()
    conn.close()
    return row is not None


def save_to_db(cluster_id, case_name, court, date_filed, text, db_path):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO cases (cluster_id, case_name, court, date_filed, text) "
        "VALUES (?, ?, ?, ?, ?)",
        (cluster_id, case_name, court, date_filed, text),
    )
    conn.commit()
    conn.close()


def cleanup_db(current_cluster_ids, db_path):
    """Remove DB records whose cluster_ids are no longer in the current result set."""
    if not os.path.exists(db_path) or not current_cluster_ids:
        return
    conn = sqlite3.connect(db_path)
    placeholders = ",".join("?" * len(current_cluster_ids))
    deleted = conn.execute(
        f"DELETE FROM cases WHERE cluster_id NOT IN ({placeholders})",
        current_cluster_ids,
    ).rowcount
    conn.commit()
    conn.close()
    if deleted:
        logger.info(f"Removed {deleted} stale record(s) from DB.")


def cleanup_opinions(current_cluster_ids, opinions_dir):
    """Delete opinion files (.txt/.pdf) whose cluster_ids are no longer current."""
    if not os.path.exists(opinions_dir):
        return
    current = set(current_cluster_ids)
    removed = 0
    for filename in os.listdir(opinions_dir):
        if not (filename.endswith(".txt") or filename.endswith(".pdf")):
            continue
        cluster_id = filename.rsplit(".", 1)[0]
        if cluster_id not in current:
            os.remove(os.path.join(opinions_dir, filename))
            removed += 1
    if removed:
        logger.info(f"Removed {removed} stale opinion file(s) from {opinions_dir}.")


def index_opinions(opinions_dir, db_path, case_records=None):
    """Index all .txt and .pdf opinion files into the SQLite database."""
    ensure_db(db_path)
    if not os.path.exists(opinions_dir):
        logger.warning(f"Opinions folder not found: {opinions_dir}")
        return
    meta = {str(c["cluster_id"]): c for c in (case_records or [])}
    opinion_files = [
        f for f in os.listdir(opinions_dir)
        if f.endswith(".pdf") or f.endswith(".txt")
    ]
    logger.info(f"Found {len(opinion_files)} opinion file(s) to index.")
    indexed, skipped = 0, 0
    for filename in opinion_files:
        cluster_id = filename.rsplit(".", 1)[0]
        if is_already_indexed(cluster_id, db_path):
            skipped += 1
            continue
        text = extract_text_from_file(os.path.join(opinions_dir, filename))
        if not text.strip():
            logger.warning(f"No text extracted from {filename}")
        case = meta.get(cluster_id, {})
        save_to_db(
            cluster_id,
            case.get("case_name", "Unknown"),
            case.get("court",      "Unknown"),
            case.get("date_filed", "Unknown"),
            text,
            db_path,
        )
        indexed += 1
        logger.info(f"Indexed: {filename}")
    logger.info(f"Indexing complete. Indexed: {indexed}, Skipped: {skipped}")
