#!/usr/bin/env python3
"""
Fetch citation data from Elsevier Scopus API for Panggah Prabawa.
Outputs _data/scopus_citations.yml for use in Jekyll site.
"""
import json
import os
import urllib.request
import urllib.parse
import sys
import time

API_KEY = os.environ.get("ELSEVIER_SCOPUS_API_KEY", "")
if not API_KEY:
    print("ERROR: ELSEVIER_SCOPUS_API_KEY environment variable not set.", file=sys.stderr)
    print("Set it via: export ELSEVIER_SCOPUS_API_KEY=your_key", file=sys.stderr)
    sys.exit(1)
BASE_URL = "https://api.elsevier.com/content"

HEADERS = {
    "X-ELS-APIKey": API_KEY,
    "Accept": "application/json",
}

# Known papers by DOI for per-article citation count
PAPERS = [
    {"doi": "10.1109/ACCESS.2020.2980544", "key": "prabawa2020multiagent"},
    {"doi": "10.1109/ACCESS.2021.3109621", "key": "prabawa2021hierarchical"},
    {"doi": "10.1016/j.apenergy.2024.124170", "key": "prabawa2024safe"},
    {"doi": "10.1016/j.egyr.2024.03.025", "key": "prabawa2024distributionally"},
    {"doi": "10.1016/j.egyr.2025.12.033", "key": "prabawa2025carbonaware"},
    {"doi": "10.1016/j.apenergy.2024.124944", "key": "lee2025joint"},
]


def api_get(path, params=None):
    """Make a GET request to the Elsevier API."""
    url = f"{BASE_URL}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"  HTTP {e.code} for {url}", file=sys.stderr)
        if body:
            print(f"  Response: {body[:300]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  Error: {e} for {url}", file=sys.stderr)
        return None


def search_author():
    """Search for Panggah Prabawa at Chung-Ang University."""
    query = 'AUTHLASTNAME(Prabawa) AND AUTHFIRST(Panggah) AND AFFIL(Chung-Ang)'
    params = {"query": query, "count": 5}
    result = api_get("/search/author", params)
    if not result:
        return None

    entries = result.get("search-results", {}).get("entry", [])
    if not entries:
        print("No author found in Scopus.", file=sys.stderr)
        return None

    for entry in entries:
        name = entry.get("preferred-name", {})
        given = name.get("given-name", "")
        surname = name.get("surname", "")
        print(f"  Found: {given} {surname} — ID: {entry.get('dc:identifier', '')}", file=sys.stderr)

    # Take first match
    entry = entries[0]
    scopus_id = entry.get("dc:identifier", "").replace("AUTHOR_ID:", "")
    # Also get document count
    doc_count = entry.get("document-count", "0")
    return {"id": scopus_id, "name": f"{name.get('given-name', '')} {name.get('surname', '')}",
            "document_count": doc_count}


def get_author_metrics(scopus_id):
    """Get h-index and citation count for the author."""
    params = {"view": "METRICS"}
    result = api_get(f"/author/author_id/{scopus_id}", params)
    if not result:
        return None

    metrics = {}
    try:
        arr = result.get("author-retrieval-response", [])
        if isinstance(arr, list) and arr:
            item = arr[0]
            coredata = item.get("coredata", {})
            metrics["h_index"] = item.get("h-index", "N/A")          # top-level
            metrics["citation_count"] = coredata.get("citation-count", "N/A")
            metrics["document_count"] = coredata.get("document-count", "N/A")
    except Exception:
        pass
    return metrics


def get_article_citation_count(doi):
    """Get citation count and title for a specific article by DOI."""
    encoded_doi = urllib.parse.quote(doi)
    params = {"view": "FULL"}  # Get all fields including title
    result = api_get(f"/abstract/doi/{encoded_doi}", params)
    if not result:
        return None

    try:
        resp = result.get("abstracts-retrieval-response", {})
        coredata = resp.get("coredata", {})
        count = coredata.get("citedby-count", "0")
        title = coredata.get("dc:title", "")
        return {"count": int(count) if count else 0, "title": title}
    except Exception:
        return None


def main():
    print("=== Scopus API Integration for Panggah Prabawa ===\n", file=sys.stderr)

    # 1. Find author
    print("1. Searching for author...", file=sys.stderr)
    author = search_author()
    if not author:
        print("ERROR: Could not find author. Check name/affiliation.", file=sys.stderr)
        sys.exit(1)
    time.sleep(0.5)

    # 2. Get metrics
    print(f"\n2. Fetching metrics for Scopus ID: {author['id']}...", file=sys.stderr)
    metrics = get_author_metrics(author["id"])
    time.sleep(0.5)

    # 3. Get per-article citations
    print(f"\n3. Fetching per-article citation counts ({len(PAPERS)} papers)...", file=sys.stderr)
    article_data = []
    total_from_articles = 0
    for paper in PAPERS:
        doi = paper["doi"]
        print(f"   {doi}...", file=sys.stderr)
        result = get_article_citation_count(doi)
        if result:
            print(f"     → {result['count']} citations: {result['title'][:80]}", file=sys.stderr)
            article_data.append({
                "bib_key": paper["key"],
                "doi": doi,
                "citations": result["count"],
                "title": result["title"],
            })
            total_from_articles += result["count"]
        else:
            print(f"     → Could not fetch", file=sys.stderr)
            article_data.append({
                "bib_key": paper["key"],
                "doi": doi,
                "citations": "N/A",
                "title": "N/A",
            })
        time.sleep(0.3)

    # 4. Build output
    output = {
        "author": {
            "name": author["name"],
            "scopus_id": author["id"],
            "h_index": metrics.get("h_index", "N/A") if metrics else "N/A",
            "total_citations": metrics.get("citation_count", str(total_from_articles)) if metrics else str(total_from_articles),
            "document_count": metrics.get("document_count", str(len(PAPERS))) if metrics else str(len(PAPERS)),
            "affiliation": "Chung-Ang University, Seoul, South Korea",
            "last_updated": time.strftime("%Y-%m-%d"),
        },
        "articles": article_data,
    }

    print("\n=== Results ===", file=sys.stderr)
    print(f"Author: {output['author']['name']}", file=sys.stderr)
    print(f"Scopus ID: {output['author']['scopus_id']}", file=sys.stderr)
    print(f"H-index: {output['author']['h_index']}", file=sys.stderr)
    print(f"Total Citations: {output['author']['total_citations']}", file=sys.stderr)
    print(f"Documents: {output['author']['document_count']}", file=sys.stderr)

    # Write YAML data file for Jekyll
    PROJECT_ROOT = os.environ.get("AL_FOLIO_ROOT", os.getcwd())
    data_dir = os.path.join(PROJECT_ROOT, "_data")
    os.makedirs(data_dir, exist_ok=True)
    yaml_path = os.path.join(data_dir, "scopus_citations.yml")
    write_yaml(yaml_path, output)
    print(f"\nWrote: {yaml_path}", file=sys.stderr)

    # Also print JSON to stdout for piping
    print(json.dumps(output, indent=2))


def write_yaml(path, data):
    """Write data dict as YAML to file."""
    lines = []
    lines.append("# Scopus citation data for Panggah Prabawa")
    lines.append("# Auto-generated by bin/fetch_scopus_citations.py")
    lines.append(f"# Last updated: {data['author']['last_updated']}")
    lines.append("")

    author = data["author"]
    lines.append("author:")
    for k in ["name", "scopus_id", "affiliation", "h_index", "total_citations", "document_count", "last_updated"]:
        v = author.get(k, "")
        if isinstance(v, str) and ":" in v:
            lines.append(f'  {k}: "{v}"')
        else:
            lines.append(f"  {k}: {v}")
    lines.append("")

    lines.append("articles:")
    for art in data["articles"]:
        lines.append(f"  - bib_key: {art['bib_key']}")
        lines.append(f'    doi: "{art["doi"]}"')
        lines.append(f"    citations: {art['citations']}")
        title = art.get("title", "").replace('"', "'")
        lines.append(f'    title: "{title}"')
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
