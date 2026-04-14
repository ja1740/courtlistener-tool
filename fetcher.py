import os
import time
import logging
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://www.courtlistener.com/api/rest/v4"


def build_search_params(query, filed_after, order_by, court=None):
    api_params = {
        "q":           query,
        "type":        "o",
        "order_by":    order_by,
        "filed_after": filed_after,
    }
    if court:
        api_params["court"] = court
    return api_params


def fetch_one_page(url, api_params, api_key):
    headers = {"Authorization": f"Token {api_key}", "Accept": "application/json"}
    response = requests.get(url, params=api_params, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def extract_case_record(result):
    opinions = result.get("opinions") or [{}]
    return {
        "cluster_id":    str(result.get("cluster_id", "")),
        "case_name":     result.get("caseName", "Unknown"),
        "citation":      result.get("citation", ["N/A"])[0] if result.get("citation") else "N/A",
        "court":         result.get("court", "Unknown"),
        "date_filed":    result.get("dateFiled", "Unknown"),
        "docket_number": result.get("docketNumber", "N/A"),
        "opinion_id":    str(opinions[0].get("id", "")) if opinions else "",
        "download_url":  opinions[0].get("download_url", "") if opinions else "",
        "absolute_url":  result.get("absolute_url", ""),
        "doc_count":     result.get("sibling_ids", []),
    }


def fetch_opinion_text(opinion_id, api_key):
    """Fetch the plain text of an opinion directly from CourtListener's API."""
    if not opinion_id:
        return None
    url = f"{BASE_URL}/opinions/{opinion_id}/"
    headers = {"Authorization": f"Token {api_key}", "Accept": "application/json"}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json().get("plain_text") or None
    except Exception as e:
        logger.debug(f"CourtListener text API failed for opinion {opinion_id}: {e}")
        return None


def download_opinion(cluster_id, opinion_id, download_url, absolute_url, api_key, pdfs_dir):
    """Fetch the opinion and save it locally.

    Strategy:
      1. CourtListener plain-text API  → saves as <cluster_id>.txt  (avoids external court URLs)
      2. External download_url / absolute_url fallback → saves as <cluster_id>.pdf
    """
    txt_path = os.path.join(pdfs_dir, f"{cluster_id}.txt")
    pdf_path = os.path.join(pdfs_dir, f"{cluster_id}.pdf")

    if os.path.exists(txt_path) or os.path.exists(pdf_path):
        return "skipped (already exists)"

    text = fetch_opinion_text(opinion_id, api_key)
    if text and text.strip():
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)
        return "fetched (CourtListener text API)"

    url_to_try = download_url or f"https://www.courtlistener.com{absolute_url}"
    try:
        headers = {"Authorization": f"Token {api_key}"}
        response = requests.get(url_to_try, headers=headers, timeout=60)
        response.raise_for_status()
        with open(pdf_path, "wb") as f:
            f.write(response.content)
        return "downloaded (external URL)"
    except Exception as e:
        return f"error: {e}"


def search_and_download(query, filed_after, order_by, max_results, court, api_key, pdfs_dir):
    os.makedirs(pdfs_dir, exist_ok=True)
    api_params = build_search_params(query, filed_after, order_by, court)
    all_records, all_errors = [], []
    next_url = f"{BASE_URL}/search/"

    while next_url and len(all_records) < max_results:
        try:
            logger.info(f"Fetching page... ({len(all_records)} cases so far)")
            page_data   = fetch_one_page(next_url, api_params, api_key)
            page_results = page_data.get("results", [])
            if not page_results:
                break
            for result in page_results:
                if len(all_records) >= max_results:
                    break
                record = extract_case_record(result)
                status = download_opinion(
                    record["cluster_id"], record["opinion_id"],
                    record["download_url"], record["absolute_url"],
                    api_key, pdfs_dir,
                )
                record["pdf_status"] = status
                if status.startswith("error"):
                    all_errors.append({
                        "cluster_id": record["cluster_id"],
                        "case_name":  record["case_name"],
                        "error":      status,
                    })
                all_records.append(record)
            next_url   = page_data.get("next")
            api_params = {}
            time.sleep(0.5)
        except Exception as e:
            logger.error(f"Failed to fetch page: {e}")
            break

    logger.info(f"Retrieved {len(all_records)} cases total.")
    return all_records, all_errors
