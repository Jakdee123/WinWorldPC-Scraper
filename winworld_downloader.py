"""
winworld_downloader.py

This script takes the winworld_os_metadata.json file and downloads each file to:
    ./<second to last slash in version_url>/<final slash in version_url>/<file_name>

Rules:
- Every 50 downloads, wait for all active downloads to finish, then run: nordvpn -c <random number>, and wait 10 seconds for VPN to change.
- Only 3 downloads per server at a time (server 1 and server 2). If a file has only one server and that server already has 3 downloads running, wait until one of that server's downloads completes.

Requirements:
    pip install requests
    (NordVPN CLI in PATH)
"""

import json
import os
import random
import subprocess
import threading
import time
import requests

# Config
INPUT_JSON = 'winworld_os_metadata.json'
BASE_DIR = '.'
MAX_PER_SERVER = 3
NORDVPN_SWITCH_INTERVAL = 50  # downloads
SERVERS = ["server 1", "server 2"]

# Thread control
active_downloads = {srv: 0 for srv in SERVERS}
active_lock = threading.Lock()
download_count = 0
count_lock = threading.Lock()
threads = []
threads_lock = threading.Lock()

def run_nordvpn_switch():
    server_num = random.randint(1, 100)
    print(f"[NordVPN] Waiting for all downloads to finish before switching...")
    with threads_lock:
        for t in threads:
            t.join()
        threads.clear()
    print(f"[NordVPN] Switching to server #{server_num}")
    try:
        subprocess.run(["nordvpn", "-c", str(server_num)], check=True)
        print("[NordVPN] Waiting 10 seconds for VPN to stabilize...")
        time.sleep(10)
    except Exception as e:
        print(f"[NordVPN] Failed to switch server: {e}")

def wait_for_slot(server_name):
    while True:
        with active_lock:
            if active_downloads[server_name] < MAX_PER_SERVER:
                active_downloads[server_name] += 1
                return
        time.sleep(0.5)

def release_slot(server_name):
    with active_lock:
        active_downloads[server_name] -= 1

def download_file(url, dest_path, server_name):
    global download_count
    try:
        wait_for_slot(server_name)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        print(f"[Download] {url} -> {dest_path}")
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        print(f"[Done] {dest_path}")
    except Exception as e:
        print(f"[Error] {url}: {e}")
    finally:
        release_slot(server_name)
        with count_lock:
            download_count += 1
            if download_count % NORDVPN_SWITCH_INTERVAL == 0:
                run_nordvpn_switch()

def main():
    global threads
    with open(INPUT_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)
    for os_entry in data:
        for version in os_entry.get('versions', []):
            v_url = version.get('version_url', '')
            parts = v_url.strip('/').split('/')
            if len(parts) < 2:
                continue
            dir_path = os.path.join(BASE_DIR, parts[-2], parts[-1])
            for file_entry in version.get('files', []):
                file_name = file_entry.get('file_name', 'unknown')
                servers = file_entry.get('servers', {})
                if not servers:
                    continue
                for server_name, link in servers.items():
                    t = threading.Thread(
                        target=download_file,
                        args=(link, os.path.join(dir_path, file_name), server_name)
                    )
                    with threads_lock:
                        threads.append(t)
                    t.start()
    with threads_lock:
        for t in threads:
            t.join()
    print("All downloads complete.")

if __name__ == '__main__':
    main()
