import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote
import json
import os
import time
import random

RSS_URL = "https://www.sport-video.org.ua/rss.xml"
BASE_TORRENT_URL = "https://www.sport-video.org.ua/"
GIST_ID = os.environ["GIST_ID"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.sport-video.org.ua/",
}

def fetch_rss(retries=5):
    for attempt in range(retries):
        try:
            delay = random.uniform(3, 8)
            print(f"⏳ Waiting {delay:.1f}s before request (attempt {attempt + 1}/{retries})...")
            time.sleep(delay)

            session = requests.Session()
            # Visit homepage first to get cookies, like a real browser would
            session.get("https://www.sport-video.org.ua/", headers=HEADERS, timeout=15)
            time.sleep(random.uniform(1, 3))

            response = session.get(RSS_URL, headers=HEADERS, timeout=15)
            response.raise_for_status()
            print("✅ RSS fetched successfully!")
            return response.text

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < retries - 1:
                wait = (attempt + 1) * 15  # 15s, 30s, 45s, 60s...
                print(f"⚠️  Rate limited (429). Waiting {wait}s before retry...")
                time.sleep(wait)
            else:
                raise
    raise Exception("❌ Failed to fetch RSS after all retries.")

def build_torrent_url(title):
    filename = title.strip() + ".mkv.torrent"
    return BASE_TORRENT_URL + quote(filename)

def enrich_rss(raw_xml):
    root = ET.fromstring(raw_xml)
    channel = root.find("channel")

    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<rss version="2.0">')
    lines.append('  <channel>')
    lines.append('    <title>Football Torrents - sport-video.org.ua</title>')
    lines.append('    <link>https://www.sport-video.org.ua/football.html</link>')
    lines.append('    <description>Football match torrents auto-enriched from sport-video.org.ua</description>')

    for item in channel.findall("item"):
        title_el    = item.find("title")
        pub_date_el = item.find("pubDate")
        desc_el     = item.find("description")

        title    = title_el.text.strip()    if title_el    is not None and title_el.text    else ""
        pub_date = pub_date_el.text.strip() if pub_date_el is not None and pub_date_el.text else ""
        desc     = desc_el.text.strip()     if desc_el     is not None and desc_el.text     else ""

        torrent_url = build_torrent_url(title)

        lines.append('    <item>')
        lines.append(f'      <title>{title}</title>')
        lines.append(f'      <link>{torrent_url}</link>')
        lines.append(f'      <guid>{torrent_url}</guid>')
        if pub_date:
            lines.append(f'      <pubDate>{pub_date}</pubDate>')
        if desc:
            lines.append(f'      <description>{desc}</description>')
        lines.append(f'      <enclosure url="{torrent_url}" type="application/x-bittorrent"/>')
        lines.append('    </item>')

    lines.append('  </channel>')
    lines.append('</rss>')
    return "\n".join(lines)

def push_to_gist(content):
    url = f"https://api.github.com/gists/{GIST_ID}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {
        "files": {
            "football_torrents.rss": {
                "content": content
            }
        }
    }
    response = requests.patch(url, headers=headers, data=json.dumps(payload), timeout=15)
    response.raise_for_status()
    print("✅ Gist updated successfully!")
    raw_url = response.json()["files"]["football_torrents.rss"]["raw_url"]
    print(f"📡 Raw RSS URL: {raw_url}")

if __name__ == "__main__":
    print("📥 Fetching RSS feed...")
    raw_xml = fetch_rss()
    print("🔧 Enriching with torrent links...")
    enriched = enrich_rss(raw_xml)
    print("☁️  Pushing to Gist...")
    push_to_gist(enriched)
