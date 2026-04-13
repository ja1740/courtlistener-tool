# WHAT THIS FILE DOES:
# Reads each downloaded PDF and extracts the text from it.
# Stores that text in a local SQLite database so that keyword
# searches are fast and do not require re-reading PDFs every time.
#
# WHY IT EXISTS:
# PDFs are binary files - you cannot search them directly with
# a simple text search. This file converts them into searchable text
# and stores that text in a structured database.
#
# HOW IT FITS INTO THE PROJECT:
# main.py calls index_pdfs() after fetcher.py downloads the PDFs.
# searcher.py then queries the database that this file creates.

import os
import sqlite3
import logging
import fitz  # This is PyMuPDF - the library we use to read PDFs

logger = logging.getLogger(__name__)


def ensure_db(db_path):
    """
    Creates the SQLite database and the cases table if they do not exist yet.
    Takes the file path where the database should be stored.
    Safe to call multiple times - it will not overwrite existing data.
    """
    # Connect to the database (creates the file if it does not exist)
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    # Create the cases table to store extracted PDF text
    # cluster_id is the unique identifier from CourtListener
    cursor.execute("""CREATE TABLE IF NOT EXISTS cases (
        cluster_id TEXT PRIMARY KEY,
        case_name  TEXT,
        court      TEXT,
        date_filed TEXT,
        text       TEXT
    )""")

    connection.commit()
    connection.close()


def extract_text_from_pdf(pdf_path):
    """
    Opens a PDF file and extracts all the text from every page.
    Takes the file path to the PDF.
    Returns all the text as a single string, or an empty string if it fails.
    """
    try:
        # Open the PDF using PyMuPDF
        pdf_document = fitz.open(pdf_path)
        all_text = ""

        # Loop through every page and extract the text
        for page in pdf_document:
            all_text += page.get_text()

        pdf_document.close()
        return all_text

    except Exception as error:
        logger.error(f"Could not extract text from {pdf_path}: {error}")
        return ""


def is_already_indexed(cluster_id, db_path):
    """
    Checks whether a case has already been added to the database.
    Takes the cluster_id and database path.
    Returns True if it already exists, False if it needs to be added.
    """
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    # Look for a row with this cluster_id
    cursor.execute("SELECT 1 FROM cases WHERE cluster_id = ?", (cluster_id,))
    result = cursor.fetchone()

    connection.close()
    return result is not None


def save_to_db(cluster_id, case_name, court, date_filed, text, db_path):
    """
    Saves one case's extracted text into the database.
    Takes all the case metadata and the extracted text.
    Uses INSERT OR IGNORE so it skips cases already in the database.
    """
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    # Insert the case record - if it already exists, skip it silently
    cursor.execute(
        "INSERT OR IGNORE INTO cases (cluster_id, case_name, court, date_filed, text) VALUES (?, ?, ?, ?, ?)",
        (cluster_id, case_name, court, date_filed, text)
    )

    connection.commit()
    connection.close()


def index_pdfs(pdfs_dir, db_path):
    """
    The main function called by main.py.
    Loops through every PDF in the pdfs/ folder, extracts the text,
    and stores it in the database. Skips PDFs already in the database.
    """
    # --- Step 1: Make sure the database and table exist ---
    ensure_db(db_path)

    # --- Step 2: Check that the pdfs/ folder exists ---
    if not os.path.exists(pdfs_dir):
        logger.warning(f"PDFs folder not found: {pdfs_dir}")
        return

    # --- Step 3: Get a list of all PDF files in the folder ---
    pdf_files = [f for f in os.listdir(pdfs_dir) if f.endswith(".pdf")]
    logger.info(f"Found {len(pdf_files)} PDFs to index.")

    indexed_count = 0
    skipped_count = 0
indexer.py    # --- Step 4: Process each PDF one by one ---
    for pdf_filename in pdf_files:
        # The cluster_id is the filename without the .pdf extension
        cluster_id = pdf_filename.replace(".pdf", "")

        # Skip this PDF if it is already in the database
        if is_already_indexed(cluster_id, db_path):
            skipped_count += 1
            continue

        # Build the full path to this PDF file
        pdf_path = os.path.join(pdfs_dir, pdf_filename)

        # Extract the text from the PDF
        text = extract_text_from_pdf(pdf_path)

        if not text.strip():
            # The PDF had no extractable text (it may be a scanned image)
            logger.warning(f"No text extracted from {pdf_filename} - may be a scanned PDF")

        # Save to the database with placeholder metadata
        # (Full metadata is available in the snapshot files)
        save_to_db(
            cluster_id=cluster_id,
            case_name="See snapshot for case name",
            court="See snapshot",
            date_filed="See snapshot",
            text=text,
            db_path=db_path
        )
        indexed_count += 1
        logger.info(f"Indexed: {pdf_filename}")

    logger.info(f"Indexing complete. Indexed: {indexed_count}, Skipped: {skipped_count}")
