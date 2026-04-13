# WHAT THIS FILE DOES:
# Handles all communication with the CourtListener API.
# It searches for court opinions, paginates through results,
# and downloads each opinion as a PDF file.
#
# WHY IT EXISTS:
# Keeping all API logic in one place makes it easy to find and
# understand every line that touches the internet.
#
# HOW IT FITS INTO THE PROJECT:
# main.py calls search_and_download() from this file.
# The results (a list of cases) are passed to reporter.py and differ.py.
# The downloaded PDFs are later read by indexer.py.

import os
import time
import logging
import requests

logger = logging.getLogger(__name__)

# --- Default search constants ---
# These are used when the user runs the tool without any flags.
# Change these values here to update the default behavior.

# The search query sent to CourtListener.
# The AI side covers all ways courts describe AI technology.
# The copyright side anchors results to copyright law.
DEFAULT_QUERY = (
    '("artificial intelligence" OR "generative AI" OR "AI-generated" '
    'OR "machine learning" OR "large language model" OR "LLM" '
    'OR "diffusion model" OR "training data" OR "neural network") '
    'AND ("copyright" OR "infringement" OR "fair use" '
    'OR "derivative work" OR "DMCA" OR "authorship" OR "originality")'
)

# Only retrieve cases filed after this date
DEFAULT_FILED_AFTER = "2019-01-01"

# Maximum number of cases to retrieve in one run
DEFAULT_MAX_RESULTS = 100

# Sort by relevance so the most on-point cases appear first
DEFAULT_ORDER_BY = "score"

# The base URL for all CourtListener API requests
BASE_URL = "https://www.courtlistener.com/api/rest/v3"


def build_search_params(params):
    """
    Builds the dictionary of parameters to send to the CourtListener search API.
    Takes the user-supplied params dict and maps them to the API's expected field names.
    Returns a dictionary ready to be sent as query parameters in the HTTP request.
    """
    # Start with the required parameters
    api_params = {
        "q": params["query"],
        "type": "o",  # 'o' means opinions only
        "order_by": params["order_by"],
        "filed_after": params["filed_after"],
        "format": "json",
    }

    # Add court filter only if the user specified one
    if params.get("court"):
        api_params["court"] = params["court"]

    return api_params


def fetch_one_page(url, api_params, api_key):
    """
    Sends a single GET request to the CourtListener search API.
    Takes the URL, parameters, and API key.
    Returns the parsed JSON response as a Python dictionary.
    Raises an exception if the request fails.
    """
    # Set the authorization header using the API key
    headers = {"Authorization": f"Token {api_key}"}

    # Send the request and check for HTTP errors
    response = requests.get(url, params=api_params, headers=headers, timeout=30)
    response.raise_for_status()  # Raises an error if status is 4xx or 5xx

    return response.json()


def extract_case_record(result):
    """
    Pulls the fields we care about out of a single API result.
    Takes one result dictionary from the API response.
    Returns a cleaner dictionary with just the fields we need.
    """
    return {
        "cluster_id": str(result.get("cluster_id", "")),
        "case_name": result.get("caseName", "Unknown"),
        "citation": result.get("citation", ["N/A"])[0] if result.get("citation") else "N/A",
        "court": result.get("court", "Unknown"),
        "date_filed": result.get("dateFiled", "Unknown"),
        "docket_number": result.get("docketNumber", "N/A"),
        "download_url": result.get("download_url", ""),
        "absolute_url": result.get("absolute_url", ""),
        "doc_count": result.get("sibling_ids", []),
    }


def download_pdf(cluster_id, download_url, absolute_url, api_key, pdfs_dir):
    """
    Downloads one opinion PDF and saves it to the pdfs/ folder.
    Tries the direct download_url first, then falls back to the absolute_url.
    Returns a status string: 'downloaded', 'skipped', or an error message.
    """
    # Build the local file path where we will save this PDF
    pdf_path = os.path.join(pdfs_dir, f"{cluster_id}.pdf")

    # Skip if we already downloaded this file in a previous run
    if os.path.exists(pdf_path):
        return "skipped (already exists)"

    headers = {"Authorization": f"Token {api_key}"}

    # Try downloading from the direct URL first
    url_to_try = download_url or f"https://www.courtlistener.com{absolute_url}"

    try:
        response = requests.get(url_to_try, headers=headers, timeout=60)
        response.raise_for_status()

        # Save the PDF content to disk
        with open(pdf_path, "wb") as pdf_file:
            pdf_file.write(response.content)

        return "downloaded"

    except Exception as error:
        return f"error: {str(error)}"


def search_and_download(params, api_key):
    """
    The main function called by main.py.
    Searches CourtListener for matching opinions, paginates through all pages
    of results up to max_results, and downloads each opinion as a PDF.
    Returns two lists: (case_records, errors).
    - case_records: list of dicts, one per case
    - errors: list of dicts describing any download failures
    """
    # --- Step 1: Create the pdfs/ folder if it doesn't exist yet ---
    pdfs_dir = "pdfs"
    os.makedirs(pdfs_dir, exist_ok=True)

    # --- Step 2: Build the initial API request parameters ---
    api_params = build_search_params(params)
    max_results = params.get("max_results", DEFAULT_MAX_RESULTS)

    all_case_records = []  # We will collect all results here
    all_errors = []        # We will collect any download errors here
    next_url = f"{BASE_URL}/search/"  # Start with the first page

    # --- Step 3: Loop through pages of results until we have enough ---
    while next_url and len(all_case_records) < max_results:
        try:
            logger.info(f"Fetching page of results... ({len(all_case_records)} so far)")

            # Fetch one page of results from the API
            page_data = fetch_one_page(next_url, api_params, api_key)

            # Extract the list of results from this page
            results_on_page = page_data.get("results", [])

            if not results_on_page:
                break  # No more results, stop looping

            # --- Step 4: Process each result on this page ---
            for result in results_on_page:
                if len(all_case_records) >= max_results:
                    break  # Stop if we have hit the limit

                # Pull out the fields we care about
                case_record = extract_case_record(result)

                # Download the PDF for this case
                pdf_status = download_pdf(
                    case_record["cluster_id"],
                    case_record["download_url"],
                    case_record["absolute_url"],
                    api_key,
                    pdfs_dir
                )
                case_record["pdf_status"] = pdf_status

                # Log any download errors separately
                if pdf_status.startswith("error"):
                    all_errors.append({
                        "cluster_id": case_record["cluster_id"],
                        "case_name": case_record["case_name"],
                        "error": pdf_status
                    })

                all_case_records.append(case_record)

            # --- Step 5: Get the URL for the next page ---
            next_url = page_data.get("next")  # None if this was the last page
            api_params = {}  # Clear params after first request (URL carries them)

            # Be polite to the API and avoid rate limiting
            time.sleep(0.5)

        except Exception as error:
            logger.error(f"Failed to fetch page: {error}")
            break

    logger.info(f"Finished. Retrieved {len(all_case_records)} cases total.")
    return all_case_records, all_errors
