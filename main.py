import requests
import re
import time
from bs4 import BeautifulSoup
from collections import defaultdict
import json

DEBUG = True
GRACE_PERIOD = 0.555  # ~5/9 seconds between requests


def dprint(*args):
    if DEBUG:
        print(*args)


class WinWorldScraper:
    BASE_URL = "https://winworldpc.com"
    SERVER_1_ID = "/from/c3ae6ee2-8099-713d-3411-c3a6e280947e"
    SERVER_2_ID = "/from/c39ac2af-c381-c2bf-1b25-11c3a4e284a2"

    def __init__(self):
        self.session = requests.Session()

    def fetch(self, url, as_response=False):
        try:
            dprint(f"Fetching: {url}")
            response = self.session.get(url, timeout=100)
            time.sleep(GRACE_PERIOD)
            return response if as_response else response.text
        except Exception as e:
            dprint(f"Fetch failed: {e}")
            return None

    def fetch_multiple(self, urls, as_response=False):
        return {url: self.fetch(url, as_response) for url in urls}

    def scrape_library_index(self):
        url = f"{self.BASE_URL}/library/operating-systems"
        html = self.fetch(url)
        paths = set(re.findall(r'"/product/([^"]+)"', html))
        return [f"{self.BASE_URL}/product/{p}" for p in paths]

    def update_product_links(self, pages):
        updated = {}
        for url, html in pages.items():
            if not html:
                continue
            match = re.search(r'<meta\s+property="og:url"\s+content="([^"]+)"', html)
            new_url = match.group(1) if match else url
            updated[new_url] = html
        return updated

    def extract_os_versions(self, pages):
        found = set()
        for url, html in pages.items():
            if not html or not url.startswith(self.BASE_URL):
                continue
            prefix = "/" + "/".join(url[len(self.BASE_URL):].lstrip("/").split("/")[:2])
            matches = re.findall(rf'"({re.escape(prefix)}[^"]*)"', html)
            found.update(f"{self.BASE_URL}{m}" for m in matches)
        return sorted(found)

    def extract_download_tables(self, urls):
        tables = {}
        for url in urls:
            html = self.fetch(url)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            table = soup.find("table")
            if table:
                tables[url] = self.parse_table(table)
        return tables

    def parse_table(self, table):
        rows = table.find_all("tr")
        headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
        data = []
        for row in rows[1:]:
            cells = []
            for cell in row.find_all(["td", "th"]):
                a = cell.find("a")
                if a and a.has_attr("href"):
                    cells.append({"text": a.get_text(strip=True), "href": f"{self.BASE_URL}{a['href']}"})
                else:
                    cells.append(cell.get_text(strip=True))
            if len(cells) == len(headers):
                data.append(dict(zip(headers, cells)))
        return data

    def build_download_data(self, raw_tables):
        result = defaultdict(list)
        for os_url, entries in raw_tables.items():
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
                    dprint(f"Error parsing entry: {e}")
        return dict(result)

    def enrich_with_servers(self, data):
        for name, entries in data.items():
            for entry in entries:
                href = entry.get("download")
                if not href.startswith(f"{self.BASE_URL}/download/"):
                    continue
                html = self.fetch(href)
                if not html:
                    continue
                download_id = href[len(f"{self.BASE_URL}/download"):]
                servers = {}
                if download_id + self.SERVER_1_ID in html:
                    servers["server 1"] = f"{self.BASE_URL}{download_id}{self.SERVER_1_ID}"
                if download_id + self.SERVER_2_ID in html:
                    servers["server 2"] = f"{self.BASE_URL}{download_id}{self.SERVER_2_ID}"
                if servers:
                    entry["download_with_servers"] = servers

    def save_to_file(self, data, filename="download_links.json"):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    scraper = WinWorldScraper()
    product_urls = scraper.scrape_library_index()
    raw_pages = scraper.fetch_multiple(product_urls)
    updated_pages = scraper.update_product_links(raw_pages)
    os_versions = scraper.extract_os_versions(updated_pages)
    download_tables = scraper.extract_download_tables([url for url in os_versions if url.count("/") == 5])
    parsed_data = scraper.build_download_data(download_tables)
    scraper.enrich_with_servers(parsed_data)
    scraper.save_to_file(parsed_data)
    dprint("Done.")
