import requests
import json
import re
import time
from typing import Dict, Set, Union

# ======DEBUG======
DEBUG = True
GRACE_PERIOD = (2/3) #Note: The time is in seconds. 
                     #Also, this is here so you dont crash the server (or just get some 429 errors)
# =================

def dprint(*args):
    if DEBUG:
        print(*args)


def scrape_library() -> Dict[str, str]:
    lib = requests.get("https://winworldpc.com/library/operating-systems")
    lib_links = re.findall(r'"/product/[^"]*"', lib.text)
    lib_links_cleaned = [url.strip('"') for url in lib_links]
    lib_links_dict = {"https://winworldpc.com" + url: "" for url in lib_links_cleaned}

    for link in lib_links_dict:
        try:
            lib_links_dict[link] = requests.get(link).text
            dprint(f"Fetched: {link}")
            time.sleep(GRACE_PERIOD)
        except Exception as e:
            dprint(f"Failed to fetch {link}: {e}")
            lib_links_dict[link] = None

    return lib_links_dict


def update_product_links(lib_links_dict: Dict[str, str]) -> Dict[str, str]:
    updated_dict = {}

    for original_link, html in lib_links_dict.items():
        if not html:
            continue

        match = re.search(r'<meta\s+property="og:url"\s+content="([^"]+)"', html)
        if match:
            new_key = match.group(1)
            updated_dict[new_key] = html
            dprint(f"Updated key: {original_link} -> {new_key}")
        else:
            updated_dict[original_link] = html
            dprint(f"No og:url found for: {original_link}")

    return updated_dict


def extract_download_links(lib_links_dict: Dict[str, str]) -> Set[str]:
    new_links = []

    for link, html in lib_links_dict.items():
        base_path = "/".join(link[22:].split("/")[:3])
        print(base_path)
        new_links.extend(
            [x.strip('"') for x in re.findall(rf'"{re.escape(base_path)}[^"]*"', html)]
        )

    final_links = ["https://winworldpc.com" + link for link in set(new_links)]
    final_links.sort()

    to_remove = [
        # List of links to be removed
    ]

    jk_not_final_links = [link for link in final_links if link not in to_remove]
    return set(jk_not_final_links)


def fetch_download_pages(download_links: Set[str]) -> Dict[str, Union[requests.Response, Exception]]:
    pre_download = {url: "" for url in download_links}

    for url in pre_download:
        time.sleep(GRACE_PERIOD)
        try:
            pre_download[url] = requests.get(url, timeout=10)
        except requests.RequestException as e:
            pre_download[url] = e
            print(f"Error fetching {url}: {e}")

    return pre_download


def extract_server_links(pre_download: Dict[str, Union[requests.Response, Exception]]) -> Dict[str, Dict[str, Set[str]]]:
    
    links = {url: "" for url in pre_download.keys()}
    for link in links.keys():
        links[link] = requests.get(link)
        time.sleep(GRACE_PERIOD)
    return links


def main():
    lib_links_dict = scrape_library()
    lib_links_dict = update_product_links(lib_links_dict)
    download_links = extract_download_links(lib_links_dict)
    pre_download = fetch_download_pages(download_links)
    dprint(pre_download)
    download = extract_server_links(pre_download)
    
    """
    def convert_sets(obj):
        if isinstance(obj, set):
            return list(obj)
        elif isinstance(obj, dict):
            return {k: convert_sets(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_sets(elem) for elem in obj]
        else:
            return obj

    clean_data = [convert_sets(download).keys()].sort()
    """

    with open("download_links.txt", "w") as f:
        almost = list(download.keys())
        almost.sort()
        final = []
        for url in almost:
            slash = re.findall("/", url)
            if len(slash) == 5:
                final.append(url)
                dprint(f"Added {url} to final list")    
        f.write(str(final))


if __name__ == "__main__":
    main()