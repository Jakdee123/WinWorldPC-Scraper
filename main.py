"""
winworld_scraper_gui.py
PySide6 GUI scraper for WinWorldPC OS library metadata.

Requirements:
    pip install pyside6 requests beautifulsoup4

Outputs:
    - winworld_os_metadata.json
    - scraper_errors.log

Notes:
    - Sleeps exactly 5/9 seconds between requests to avoid 429s.
    - Deduplicates OSes by canonical <meta property="og:url">.
    - Grabs file name, size, architecture (from img title), and server links.
    - Servers are stored as { "server 1": url, "server 2": url }.
    - Runs scraping in a QThread so the GUI stays responsive.
"""

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton,
    QTextEdit, QProgressBar, QLabel, QHBoxLayout, QFileDialog, QMessageBox
)
from PySide6.QtCore import QThread, Signal, Qt
import sys
import time
import json
import logging
from fractions import Fraction
from urllib.parse import urljoin
import re
import requests
from bs4 import BeautifulSoup
import traceback

# === Constants ===
BASE_URL = "https://winworldpc.com"
LIBRARY_URL = "https://winworldpc.com/library/operating-systems"
OUTPUT_JSON = "winworld_os_metadata.json"
ERROR_LOG = "scraper_errors.log"
# Exact fraction 5/9 seconds per user instruction
SLEEP_BETWEEN_REQUESTS = float(Fraction(5, 9))  # 0.555555...

# Map server UUIDs -> readable names
SERVER_MAP = {
    "c3ae6ee2-8099-7139-713d-3411-c3a6e280947e": "server 1",  # careful: keep original mapping
    # NOTE: above UUID intentionally kept similar to avoid accidental mismatches; we will also match known ones below
    "c39ac2af-c381-c2bf-1b25-11c3a4e284a2": "server 2",
    "c3ae6ee2-8099-713d-3411-c3a6e280947e": "server 1",
}

# Configure logging to file
logging.basicConfig(
    filename=ERROR_LOG,
    level=logging.ERROR,
    format='%(asctime)s [%(levelname)s] %(message)s'
)


class ScraperThread(QThread):
    log = Signal(str)
    overall_progress = Signal(int)  # 0-100
    sub_progress = Signal(int)      # 0-100 for inner tasks
    finished_scrape = Signal(object)  # emit final data (dict/list)
    errored = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_requested = False
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'winworld-scraper/1.0 (+https://example.com)'
        })

    def request_stop(self):
        self._stop_requested = True

    def stopped(self):
        return self._stop_requested

    def polite_sleep(self):
        # Sleep in small slices to remain responsive to stop requests
        total = SLEEP_BETWEEN_REQUESTS
        step = 0.05
        elapsed = 0.0
        while elapsed < total:
            if self.stopped():
                return
            time.sleep(min(step, total - elapsed))
            elapsed += step

    def safe_get(self, url):
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return resp
        except Exception as e:
            logging.exception(f'HTTP GET failed for {url}: {e}')
            self.log.emit(f"ERROR: Failed request {url}: {e}")
            raise

    def run(self):
        try:
            self.log.emit("Starting scrape of WinWorldPC OS library...")

            # Step 1: fetch library page
            self.log.emit(f"Fetching library page: {LIBRARY_URL}")
            r = self.safe_get(LIBRARY_URL)
            soup = BeautifulSoup(r.text, "html.parser")
            # Extract product links (hrefs that start with /product/)
            product_anchors = soup.select('a[href^="/product/"]')
            raw_links = []
            for a in product_anchors:
                href = a.get('href')
                if href:
                    raw_links.append(href.strip())

            self.log.emit(f"Found {len(raw_links)} raw product links (may include duplicates)")

            # Resolve canonical URLs and dedupe
            canonical_map = {}  # canonical_url -> original href
            unique_product_urls = []

            for idx, rel in enumerate(raw_links, start=1):
                if self.stopped():
                    self.log.emit("Stop requested — aborting before canonical resolution")
                    return
                full = urljoin(BASE_URL, rel)
                try:
                    r = self.safe_get(full)
                except Exception:
                    continue
                s = BeautifulSoup(r.text, 'html.parser')
                og = s.find('meta', property='og:url')
                if og and og.get('content'):
                    can = og['content'].strip()
                else:
                    # fallback to the fetched URL
                    can = r.url
                if can not in canonical_map:
                    canonical_map[can] = rel
                    unique_product_urls.append(can)
                    self.log.emit(f"[canon] {can}")
                else:
                    self.log.emit(f"Duplicate canonical skipped: {can}")

                # polite sleep between requests
                self.polite_sleep()

            total_os = len(unique_product_urls)
            self.log.emit(f"Total unique OS products to process: {total_os}")
            data = []

            for i, product_url in enumerate(unique_product_urls, start=1):
                if self.stopped():
                    self.log.emit("Stop requested — aborting main loop")
                    return

                pct = int((i - 1) / max(1, total_os) * 100)
                self.overall_progress.emit(pct)
                self.log.emit(f"[ {pct:3d}% ] Processing OS {i}/{total_os}: {product_url}")

                try:
                    r = self.safe_get(product_url)
                except Exception:
                    continue
                s = BeautifulSoup(r.text, 'html.parser')

                # Get OS name
                h1 = s.find('h1')
                if h1:
                    os_name = h1.get_text(strip=True)
                else:
                    title = s.title.string if s.title else product_url
                    os_name = title.strip()

                # Find releases list
                releases_nav = s.find('ul', id='releasesList')
                version_links = []
                if releases_nav:
                    for a in releases_nav.find_all('a', href=True):
                        href = a['href'].strip()
                        # normalize to absolute
                        version_links.append(urljoin(BASE_URL, href))
                else:
                    self.log.emit(f"No releasesList found for {product_url}")

                # Deduplicate version links
                version_links = list(dict.fromkeys(version_links))
                self.log.emit(f"Found {len(version_links)} versions for {os_name}")

                versions_data = []
                for vi, version_url in enumerate(version_links, start=1):
                    if self.stopped():
                        return
                    sub_pct = int((vi - 1) / max(1, len(version_links)) * 100)
                    self.sub_progress.emit(sub_pct)
                    self.log.emit(f"  [ {sub_pct:3d}% ] Version {vi}/{len(version_links)}: {version_url}")

                    try:
                        rv = self.safe_get(version_url)
                    except Exception:
                        continue
                    sv = BeautifulSoup(rv.text, 'html.parser')

                    # Parse downloads table
                    table = sv.find('table', id='downloadsTable')
                    files = []
                    if table:
                        tbody = table.find('tbody') or table
                        rows = tbody.find_all('tr')
                        for fi, row in enumerate(rows, start=1):
                            if self.stopped():
                                return
                            # columns may vary; attempt to find file name, size, arch
                            cols = row.find_all(['td', 'th'])
                            file_name = None
                            size = None
                            architecture = None
                            download_rel = None

                            # heuristics: first column often has file link/name
                            if cols:
                                # find link to /download/
                                link = row.find('a', href=re.compile(r'^/download/'))
                                if link and link.get('href'):
                                    download_rel = link['href'].strip()
                                    file_name = link.get_text(strip=True) or link['href']
                                # size may be in a column with text like "720 KB"
                                # look for typical size pattern
                                size_text = None
                                for c in cols:
                                    txt = c.get_text(" ", strip=True)
                                    if re.search(r'\d+\s*(KB|MB|GB|bytes|B)', txt, re.I):
                                        size_text = txt
                                        break
                                size = size_text
                                # architecture image title
                                img = row.find('img', title=True)
                                if img and img.get('title'):
                                    architecture = img['title'].strip()
                                else:
                                    # fallback: look for alt or file name hints
                                    img2 = row.find('img', alt=True)
                                    if img2 and img2.get('alt'):
                                        architecture = img2['alt'].strip()

                            if not download_rel:
                                # no download link in this row; skip
                                continue

                            file_id = None
                            m = re.match(r'^/download/(\d+)', download_rel)
                            if m:
                                file_id = m.group(1)
                            else:
                                # Try extract entire path
                                file_id = download_rel.split('/download/')[-1].strip('/')

                            # Build file entry
                            file_entry = {
                                'file_name': file_name or f'download_{file_id}',
                                'size': size,
                                'architecture': architecture,
                                'servers': {}
                            }

                            # Visit download page to find servers
                            dl_page = urljoin(BASE_URL, download_rel)
                            try:
                                rd = self.safe_get(dl_page)
                            except Exception:
                                files.append(file_entry)
                                continue
                            sd = BeautifulSoup(rd.text, 'html.parser')

                            # find server links like /download/<id>/from/<uuid>
                            server_links = {}
                            for a2 in sd.find_all('a', href=re.compile(r'/download/.+/from/')):
                                href = a2['href'].strip()
                                full_srv = urljoin(BASE_URL, href)
                                # extract uuid
                                m2 = re.search(r'/from/([0-9a-fA-F\-]+)', href)
                                if m2:
                                    uid = m2.group(1)
                                    name = SERVER_MAP.get(uid, f'server_{uid}')
                                else:
                                    name = f'server_unknown'
                                server_links[name] = full_srv

                            # ensure server 1/2 keys exist if present
                            if server_links:
                                file_entry['servers'] = server_links

                            files.append(file_entry)

                            # emit file-level log
                            self.log.emit(f"    File {fi}/{len(rows)}: {file_entry['file_name']} ({file_entry.get('size')})")

                            # polite sleep after each download page
                            self.polite_sleep()

                    else:
                        self.log.emit(f"  No downloadsTable found at {version_url}")

                    versions_data.append({
                        'version_url': version_url,
                        'files': files
                    })

                    # polite sleep between version requests
                    self.polite_sleep()

                data.append({
                    'product_url': product_url,
                    'os_name': os_name,
                    'versions': versions_data
                })

                # emit overall progress update
                pct = int(i / max(1, total_os) * 100)
                self.overall_progress.emit(pct)

                # polite sleep between product requests
                self.polite_sleep()

            # Done
            self.overall_progress.emit(100)
            self.sub_progress.emit(100)
            self.log.emit("Scrape complete — emitting data and saving JSON")

            # Save JSON to file
            try:
                with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                self.log.emit(f"Saved metadata to {OUTPUT_JSON}")
            except Exception as e:
                logging.exception('Failed to write output JSON')
                self.log.emit(f"ERROR: Failed to write {OUTPUT_JSON}: {e}")

            self.finished_scrape.emit(data)

        except Exception as e:
            logging.exception('Unhandled exception in scraper thread')
            tb = traceback.format_exc()
            self.errored.emit(str(e) + '\n' + tb)
            self.log.emit(f"Unhandled error: {e}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('WinWorldPC Scraper')
        self.resize(900, 600)

        self.thread = None

        # Widgets
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton('Start Scrape')
        self.stop_btn = QPushButton('Stop')
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        layout.addLayout(btn_layout)

        self.overall_label = QLabel('Overall Progress')
        layout.addWidget(self.overall_label)
        self.overall_bar = QProgressBar()
        self.overall_bar.setRange(0, 100)
        layout.addWidget(self.overall_bar)

        self.sub_label = QLabel('Subtask Progress')
        layout.addWidget(self.sub_label)
        self.sub_bar = QProgressBar()
        self.sub_bar.setRange(0, 100)
        layout.addWidget(self.sub_bar)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)

        # Connections
        self.start_btn.clicked.connect(self.start_scrape)
        self.stop_btn.clicked.connect(self.stop_scrape)

    def append_log(self, text):
        timestamp = time.strftime('%H:%M:%S')
        self.log_view.append(f"[{timestamp}] {text}")
        # auto-scroll
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def start_scrape(self):
        if self.thread and self.thread.isRunning():
            QMessageBox.warning(self, 'Already running', 'Scrape is already running')
            return
        self.thread = ScraperThread()
        self.thread.log.connect(self.append_log)
        self.thread.overall_progress.connect(self.overall_bar.setValue)
        self.thread.sub_progress.connect(self.sub_bar.setValue)
        self.thread.finished_scrape.connect(self.on_finished)
        self.thread.errored.connect(self.on_error)
        self.thread.start()
        self.append_log('Scraper thread started')
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def stop_scrape(self):
        if self.thread:
            self.thread.request_stop()
            self.append_log('Stop requested — waiting for thread to finish...')
            self.stop_btn.setEnabled(False)

    def on_finished(self, data):
        self.append_log('Scrape finished successfully')
        # Offer to save JSON (it's already saved by thread)
        QMessageBox.information(self, 'Done', f'Scrape complete. Metadata saved to {OUTPUT_JSON}')
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def on_error(self, err):
        self.append_log('Scraper encountered an error')
        logging.error(err)
        QMessageBox.critical(self, 'Error', f'Scraper error:\n{err}')
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
