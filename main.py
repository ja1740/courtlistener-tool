# WHAT THIS FILE DOES:
# This is the main entry point of the program.
# When you run "python main.py fetch" or "python main.py search",
# this file reads what you typed and sends it to the right module.
#
# WHY IT EXISTS:
# It acts as the front door - it doesn't do any heavy work itself,
# it just figures out what the user wants and calls the right function.
#
# HOW IT FITS INTO THE PROJECT:
# main.py -> fetcher.py (to search and download cases)
# main.py -> indexer.py (to extract PDF text into the database)
# main.py -> searcher.py (to search the local database)
# main.py -> reporter.py (to write the markdown report)
# main.py -> differ.py  (to compare results and detect changes)

import argparse
import logging
import os
from dotenv import load_dotenv

import fetcher
import indexer
import searcher
import reporter
import differ

# Set up logging so progress messages appear in the terminal
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

def run_fetch(args):
    """
    Runs the full fetch workflow:
    1. Search CourtListener for matching opinions
    2. Download each opinion as a PDF
    3. Extract PDF text and store in local database
    4. Compare results to last run and detect changes
    5. Write a markdown report summarizing everything
    """
    # --- Step 1: Load the API key from the .env file ---
    load_dotenv()
    api_key = os.getenv("COURTLISTENER_API_KEY")
    if not api_key:
        logger.error("No API key found. Please add COURTLISTENER_API_KEY to your .env file.")
        return

    # --- Step 2: Build the search parameters from CLI flags or defaults ---
    params = {
        "query": args.query or fetcher.DEFAULT_QUERY,
        "filed_after": args.filed_after or fetcher.DEFAULT_FILED_AFTER,
        "max_results": args.max_results or fetcher.DEFAULT_MAX_RESULTS,
        "order_by": fetcher.DEFAULT_ORDER_BY,
        "court": args.court or None,
    }
    logger.info(f"Starting fetch with query: {params['query'][:80]}...")

    # --- Step 3: Search the CourtListener API and download PDFs ---
    results, errors = fetcher.search_and_download(params, api_key)
    logger.info(f"Retrieved {len(results)} cases. Download errors: {len(errors)}")

    # --- Step 4: Index the downloaded PDFs into the local database ---
    indexer.index_pdfs("pdfs", "search_index.db")

    # --- Step 5: Load last snapshot and compute what changed ---
    old_snapshot = differ.load_last_snapshot("snapshots")
    changes = differ.diff_snapshots(old_snapshot, results)
    differ.save_snapshot(results, "snapshots")

    # --- Step 6: Write the markdown report ---
    reporter.write_report(results, changes, params, errors, "reports")
    logger.info("Done. Check the reports/ folder for your summary.")


def run_search(args):
    """
    Runs a keyword search across all indexed PDFs.
    Takes the user's search phrase and finds matching cases
    in the local SQLite database, showing a passage from each match.
    """
    if not args.query:
        logger.error("Please provide a search query with --query")
        return

    logger.info(f"Searching local index for: '{args.query}'")
    matches = searcher.search_index(args.query, "search_index.db", args.top)

    if not matches:
        print("No matches found.")
        return

    print(f"\nFound {len(matches)} matching case(s):\n")
    for match in matches:
        print(f"Case:    {match['case_name']}")
        print(f"Court:   {match['court']}")
        print(f"Filed:   {match['date_filed']}")
        print(f"ID:      {match['cluster_id']}")
        print(f"Passage: ...{match['snippet']}...")
        print("-" * 60)


def main():
    """
    Sets up the command-line interface with two subcommands:
    - fetch: search CourtListener and download opinions
    - search: search the locally downloaded and indexed PDFs
    """
    parser = argparse.ArgumentParser(
        description="CourtListener AI Copyright Case Tracker"
    )
    subparsers = parser.add_subparsers(dest="command")

    fetch_parser = subparsers.add_parser("fetch", help="Search and download opinions")
    fetch_parser.add_argument("--query", type=str, help="Search query")
    fetch_parser.add_argument("--filed-after", type=str, help="Only cases filed after YYYY-MM-DD")
    fetch_parser.add_argument("--max-results", type=int, help="Max results to retrieve")
    fetch_parser.add_argument("--court", type=str, help="Filter by court ID")

    search_parser = subparsers.add_parser("search", help="Search downloaded opinions")
    search_parser.add_argument("--query", type=str, required=True, help="Keyword or phrase")
    search_parser.add_argument("--top", type=int, default=10, help="Number of results (default 10)")

    args = parser.parse_args()

    if args.command == "fetch":
        run_fetch(args)
    elif args.command == "search":
        run_search(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
