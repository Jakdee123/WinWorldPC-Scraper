import requests
import re
import time
from bs4 import BeautifulSoup
from collections import defaultdict
import json

#-=====-CONFIG-=====-
DEBUG = True
GRACE_PERIOD = 5/9  # seconds to wait between requests
#-=====--------=====-

class completion_Status(Exception): pass

def dprint(*args):
            if DEBUG:
                print(*args)

class functions():
    class not_done():
        list2=[]

    class func:
        @staticmethod
        def format_func_list(func):
            func_names = [f.__name__ + "()" for f in functions.not_done.list2]
            if not func:
                return ["",False]
            elif len(func_names) == 1:
                return [func_names[0], False]
            elif len(func_names) == 2:
                return [f"{func_names[0]} and {func_names[1]}", True]
            else:
                return [f"{', '.join(func_names[:-1])}, and {func_names[-1]}", True]

        @staticmethod
        def uncomp(func):
            formatted = functions.func.format_func_list(func)
            if formatted[1]:
                raise completion_Status(f"The functions: {formatted[0]} are not completed. Exiting...")
            else:
                raise completion_Status(f"The function: {formatted[0]} is not completed. Exiting...")
        

        def fetch_text(urls):
            dprint("Starting fetch_text...")
            out = {}
            for url in urls:
                try:
                    dprint(f"Fetching: {url}")
                    out[url] = requests.get(url).text
                    dprint(f"Fetched (text): {url}")
                except Exception as e:
                    dprint(f"Failed (text): {url} — {e}")
                    out[url] = None
                time.sleep(GRACE_PERIOD)
            dprint("Completed fetch_text.")
            return out

        def fetch_response(urls, timeout=100):
            dprint("Starting fetch_response...")
            out = {}
            for url in urls:
                try:
                    dprint(f"Fetching (resp): {url}")
                    out[url] = requests.get(url, timeout=timeout)
                    dprint(f"Fetched (resp): {url}")
                except Exception as e:
                    dprint(f"Failed (resp): {url} — {e}")
                    out[url] = e
                time.sleep(GRACE_PERIOD)
            dprint("Completed fetch_response.")
            return out

        def table_to_dicts(html_table):
            dprint("Parsing HTML table...")
            soup = BeautifulSoup(html_table, "html.parser")
            table = soup.find("table")
            rows = table.find_all("tr")
            headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
            dprint(f"Table headers: {headers}")
            data = []

            for i, row in enumerate(rows[1:], 1):
                cells = []
                for cell in row.find_all(["td", "th"]):
                    a = cell.find("a")
                    if a and a.has_attr("href"):
                        href = a["href"]
                        text = a.get_text(strip=True)
                        cells.append({"text": text, "href": ("https://winworldpc.com"+href)})
                    else:
                        cells.append(cell.get_text(strip=True))
                if len(cells) == len(headers):
                    data.append(dict(zip(headers, cells)))
                else:
                    dprint(f"Skipped row {i}: Mismatched columns")
            dprint(f"Parsed {len(data)} rows from table.")
            return data

        def scrape_library():
            dprint("Scraping OS library page...")
            base = "https://winworldpc.com"
            idx_html = requests.get(f"{base}/library/operating-systems").text
            paths = set(re.findall(r'"/product/([^"]+)"', idx_html))
            dprint(f"Found {len(paths)} product paths.")
            product_urls = [f"{base}/product/{p}" for p in paths]
            return functions.func.fetch_text(product_urls)

        def update_product_links(pages):
            dprint("Updating product links...")
            updated = {}
            for orig_url, html in pages.items():
                if not html:
                    dprint(f"Skipped empty HTML from {orig_url}")
                    continue
                m = re.search(r'<meta\s+property="og:url"\s+content="([^"]+)"', html)
                new_url = m.group(1) if m else orig_url
                updated[new_url] = html
                dprint(f"Updated key: {orig_url} → {new_url}")
            return updated

        def extract_os_versions(pages):
            dprint("Extracting OS versions...")
            base = "https://winworldpc.com"
            found = set()
            for url, html in pages.items():
                if not html or not url.startswith(base):
                    dprint(f"Skipping invalid page: {url}")
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
            dprint(f"Found {len(found)} OS version URLs.")
            return set(sorted(found))

        def extract_os_versions_html(pre_download):
            dprint("Fetching OS version HTML...")
            return functions.func.fetch_response(pre_download.keys())

        def extract_downloads(not_final):
            dprint("Extracting download tables...")
            download_tables = {}
            for url in not_final:
                try:
                    dprint(f"Fetching: {url}")
                    response = requests.get(url)
                    html = response.text
                    soup = BeautifulSoup(html, "html.parser")
                    tables = soup.find_all("table")
                    if tables:
                        download_tables[url] = functions.func.table_to_dicts(str(tables[0]))
                        dprint(f"Extracted table from {url}")
                    else:
                        download_tables[url] = []
                        dprint(f"No tables found in {url}")
                except Exception as e:
                    dprint(f"Failed to fetch or parse {url}: {e}")
                    download_tables[url] = []
                time.sleep(GRACE_PERIOD)
            dprint("Completed extraction of download tables.")
            return download_tables

        def almost_final2(data):
            dprint("Building almost_final structure...")
            result = defaultdict(list)
            for os_url, entries in data.items():
                for entry in entries:
                    try:
                        name = entry["Download name"]["text"]
                        result[name].append({
                            "os": os_url,
                            "download": entry["Download name"]["href"],
                            "version": entry.get("Version", ""),
                            "language": entry.get("Language", "")
                        })
                    except Exception as e:
                        dprint(f"Failed parsing entry in {os_url}: {e}")
            dprint(f"Created almost_final with {len(result)} entries.")
            return dict(result)

        def final2(data):
            dprint("Adding server links to downloads...")
            a = 0
            SERVER_1_ID = "/from/c3ae6ee2-8099-713d-3411-c3a6e280947e"
            SERVER_2_ID = "/from/c39ac2af-c381-c2bf-1b25-11c3a4e284a2"
            BASE_URL = "https://winworldpc.com"

            for name, info_list in data.items():
                for info in info_list:
                    time.sleep(GRACE_PERIOD)
                    href = info.get("download", "")
                    if not href.startswith("https://winworldpc.com/download/"):
                        dprint(f"Skipping unexpected href: {href}")
                        continue

                    try:
                        dprint(f"Fetching download page: {href}")
                        resp = requests.get(href)
                        if resp.status_code != 200:
                            dprint(f"Non-200 status: {resp.status_code} for {href}")
                            continue
                        html = resp.text
                    except Exception as e:
                        dprint(f"Request failed for {href}: {e}")
                        continue

                    dprint(f"Processing {href}")
                    a += 1
                    dprint(f"Checked downloads: {a}")
                    download_id = href[22:]

                    servers = {}
                    if download_id + SERVER_1_ID in html:
                        servers["server 1"] = BASE_URL + download_id + SERVER_1_ID
                    if download_id + SERVER_2_ID in html:
                        servers["server 2"] = BASE_URL + download_id + SERVER_2_ID

                    if servers:
                        info["download_with_servers"] = servers
                        dprint(f"Added servers to {name}")

def main():

    # 1) scrape product pages
    lib = functions.func.scrape_library()
    dprint(lib)
    # 2) normalize to real product URLs
    lib = functions.func.update_product_links(lib)
    dprint(lib)
    # 3) pull out all the “download” links
    download_links = functions.func.extract_os_versions(lib)
    dprint(download_links)
    # 4) pre‐download stage (Response or Exception)
    pre_download = functions.func.fetch_response(download_links)
    dprint(pre_download)
    # 5) actual server‐link fetch (again)
    download = functions.func.extract_os_versions_html(pre_download)
    dprint(download)
    # 6) write out only those URLs with exactly 5 slashes
    not_final = sorted(u for u in download if u.count("/") == 5)
    dprint(not_final)

    tables = functions.func.extract_downloads(not_final)
    dprint(tables)

    almost_final = functions.func.almost_final2(tables)
    dprint(almost_final)

    functions.func.final2(almost_final)
    dprint(almost_final)

    with open("download_links.json", "w", encoding="utf-8") as f:
        almost_final_json_ready = {k: list(v) if isinstance(v, set) else v for k, v in almost_final.items()}
        json.dump(almost_final_json_ready, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    functions.not_done.list2=[functions.func.almost_final2, functions.func.final2]

    if not functions.not_done.list2 or DEBUG:
        main()
    else:
        functions.func.uncomp(functions.not_done.list2)
