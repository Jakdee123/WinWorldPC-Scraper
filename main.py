import requests
import re
import time
from bs4 import BeautifulSoup

DEBUG = True
GRACE_PERIOD = 2/3  # seconds to wait between requests

def dprint(*args):
    if DEBUG:
        print(*args)

def fetch_text(urls):
    """Fetch each URL and return a dict URL → HTML text (or None on error)."""
    out = {}
    for url in urls:
        try:
            out[url] = requests.get(url).text
            dprint(f"Fetched (text): {url}")
        except Exception as e:
            dprint(f"Failed (text): {url} — {e}")
            out[url] = None
        time.sleep(GRACE_PERIOD)
    return out

def fetch_response(urls, timeout=100):
    """Fetch each URL and return a dict URL → Response or Exception."""
    out = {}
    for url in urls:
        try:
            out[url] = requests.get(url, timeout=timeout)
            dprint(f"Fetched (resp): {url}")
        except Exception as e:
            dprint(f"Failed (resp): {url} — {e}")
            out[url] = e
        time.sleep(GRACE_PERIOD)
    return out

def table_to_dicts(html_table):
    soup = BeautifulSoup(html_table, "html.parser")
    table = soup.find("table")
    rows = table.find_all("tr")

    # Extract headers (from the first row)
    headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]

    # Extract data rows
    data = []
    for row in rows[1:]:
        cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
        if len(cells) == len(headers):  # Skip malformed rows
            data.append(dict(zip(headers, cells)))

    return data


def scrape_library():
    base = "https://winworldpc.com"
    idx_html = requests.get(f"{base}/library/operating-systems").text
    paths = set(re.findall(r'"/product/([^"]+)"', idx_html))
    product_urls = [f"{base}/product/{p}" for p in paths]
    return fetch_text(product_urls)

def update_product_links(pages):
    """Replace each key by its og:url content if present."""
    updated = {}
    for orig_url, html in pages.items():
        if not html:
            continue
        m = re.search(r'<meta\s+property="og:url"\s+content="([^"]+)"', html)
        new_url = m.group(1) if m else orig_url
        updated[new_url] = html
        dprint(f"Key: {orig_url} → {new_url}")
    return updated

def extract_os_versions(pages):
    base = "https://winworldpc.com"
    found = set()
    for url, html in pages.items():
        if not html or not url.startswith(base):
            continue

        rel = url[len(base):].lstrip("/")
        prefix = "/"+"/".join(rel.split("/")[:2])
        dprint(f"[{url}] → Prefix: {prefix}")

        matches = re.findall(rf'"({re.escape(prefix)}[^"]*)"', html)
        if not matches:
            dprint(f"No matches for prefix '{prefix}' in {url}")
        for match in matches:
            full_url = base + match
            found.add(full_url)
    return set(sorted(found))


def extract_os_versions_html(pre_download):
    """Ignore the pre_download dict and re-fetch each URL to get a fresh Response."""
    return fetch_response(pre_download.keys())

def find(text, var):
    return re.findall(text, var, re.DOTALL)

def extract_downloads(not_final):
    download_tables = {}
    for url in not_final:
        try:
            response = requests.get(url)
            html = response.text  # Extract the HTML text from the Response object
            soup = BeautifulSoup(html, "html.parser")
            tables = soup.find_all("table")
            if tables:
                # Process the first table (or adjust to handle multiple tables if needed)
                download_tables[url] = table_to_dicts(str(tables[0]))
                dprint(f"Extracted table from {url}")
            else:
                download_tables[url] = []
                dprint(f"No tables found in {url}")
            time.sleep(GRACE_PERIOD)
        except Exception as e:
            dprint(f"Failed to fetch or parse {url}: {e}")
            download_tables[url] = []
        time.sleep(GRACE_PERIOD)
    return download_tables

def main():
    # 1) scrape product pages
    lib = scrape_library()
    dprint(lib)
    # 2) normalize to real product URLs
    lib = update_product_links(lib)
    dprint(lib)
    # 3) pull out all the “download” links
    download_links = extract_os_versions(lib)
    dprint(download_links)
    # 4) pre‐download stage (Response or Exception)
    pre_download = fetch_response(download_links)
    dprint(pre_download)
    # 5) actual server‐link fetch (again)
    download = extract_os_versions_html(pre_download)
    dprint(download)
    # 6) write out only those URLs with exactly 5 slashes
    not_final = sorted(u for u in download if u.count("/") == 5)
    dprint(not_final)
    final7 = extract_downloads(not_final)
    dprint(final7)
    with open("download_links.txt", "w") as f:
        f.write(str(final7))

if __name__ == "__main__":
    main()
