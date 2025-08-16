from bs4 import BeautifulSoup as bs
import requests as req
import time
import os
from re import findall
#===== CONFIGURATION =====

GRACE_PERIOD = 5/2   # seconds

DEBUG = True

#=========================

def dprint(*args):
    if DEBUG:
        print(*args)


main_lib = req.get('https://winworldpc.com/library/operating-systems')
main_lib = bs(main_lib.text, 'html.parser')
main_lib_links = []
for link in main_lib.find_all('a'):
    main_lib_links.append((link.get('href')))

temp = main_lib_links
main_lib_links = []

for link in temp:
    if link.startswith('/product/'):
        main_lib_links.append('https://winworldpc.com' + link)

del temp

main_lib_links = list(set(main_lib_links))
main_lib_links.sort()

version_links = {}

for link1 in main_lib_links:
    html = bs((req.get(link1).text), 'html.parser')
    links = [(link.get('href')) for link in html.find_all('a')]
    good_links = []
    for link2 in links:
        if link2.startswith(link1[22:]):
            good_links.append('https://winworldpc.com' + link2)
    version_links[link1] = good_links
    dprint(f'Found {len(good_links)} version links in {link1}.')
    time.sleep(GRACE_PERIOD)

download_tables = {}

for link, versions in version_links.items():
    for version in versions:
        html = bs((req.get(version).text), 'html.parser')
        table = html.find('table', {'id': 'downloadsTable'})
        if table is None:
            dprint(f'No download table found for {version}.')
            continue
        else:
            download_tables[version] = table
            dprint(f'Found {len(table.find_all("tr"))} downloads for {version}')
        time.sleep(GRACE_PERIOD)

downloads = {}

for link in download_tables:
    table = bs(str(download_tables[link]), 'html.parser')
    rows = table.find_all('tr')[1:]  # skip header row
    for row in rows:
        tds = row.find_all('td')
        if not tds:
            continue
        a_tag = tds[0].find('a')
        if not a_tag:
            continue
        file_name = a_tag.get('title')
        download_link = "https://winworldpc.com" + a_tag.get('href')
        dprint(file_name, download_link)
        downloads[link] = {"name": file_name, "link": download_link}


ontinue = input("Download files? Y/N: ")
if ontinue.lower() == 'n':
    exit()
elif ontinue.lower() != 'y':
    print("Invalid input. Exiting.")
    exit()
print("Downloading files...")

print(downloads)

if not os.path.exists('/downloads'):
    os.makedirs('/downloads')

for link, data in downloads.items():
    amount = len(findall("/", link))
    if amount != 5:
        pass
    else:
        base_folder = link.split('/')[4]
        if not os.path.exists('/downloads/'+base_folder):
            os.makedirs('/downloads/'+base_folder)
        secondary_folder = link.split('/')[5]
        if not os.path.exists(f'/downloads/{base_folder}/{secondary_folder}'):
            os.makedirs(f'/downloads/{base_folder}/{secondary_folder}')

