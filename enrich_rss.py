import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
from datetime import datetime, timezone
import json
import os
import time
import re

BASE_URL = "https://www.sport-video.org.ua"
FOOTBALL_PAGE = f"{BASE_URL}/football.html"
GIST_ID = os.environ["GIST_ID"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]

# Use a public CORS/scraping proxy to bypass IP blocks on GitHub Actions
PROXY_URL = "https://api.allorigins.win/raw?url="

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
}

def fetch_page(url):
    proxied = PROXY_URL + quote(url, safe="")
    print(f"🌐 Fetching via proxy: {url}")
    response = requests.get(proxied, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text

def parse_torrents(html):
    soup = BeautifulSoup(html, "html.parser")
    items = []

    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.endswith(".torrent"):
            # Get the title from the bold text before the link, or from link text
            title = ""
            parent = link.find_parent()
            if parent:
                bold = parent.find("b") or parent.find("strong")
                if bold:
                    title = bold.get_text(strip=True)
            if not title:
                title = link.get_text(strip=True)
            if not title:
                # Extract title from the filename
                filename = href.split("/")[-1].replace(".mkv.torrent", "").replace("%20", " ")
                title = filename

            # Build absolute torrent URL
            if href.startswith("http"):
                torrent_url = href
            else:
                torrent_url = BASE_URL + "/" + href.lstrip("/")

            # URL-encode spaces and special characters
            torrent_url = torrent_url.replace(" ", "%20").replace("&", "%26")

            # Try to extract date from title (format: DD.MM.YYYY)
            date_match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", title)
            if date_match:
                day, month, year = date_match.groups()
                pub_date = datetime(int(year), int(month), int(day), tzinfo=timezone.utc)
                pub_date_str = pub_date.strftime("%a, %d %b %Y 00:00:00 +0000")
            else:
                pub_date_str = datetime.now(timezone.utc).strftime("%a, %d %b %Y 00:00:00 +0000")

            items.append({
                "title": title,
                "torrent_url": torrent_url,
                "pub_date": pub_date_str,
            })

    print(f"✅ Found {len(items)} torrents")
    return items

def build_rss(items):
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<rss version="2.0">')
    lines.append('  <channel>')
    lines.append('    <title>Football Torrents - sport-video.org.ua</title>')
    lines.append('    <link>https://www.sport-video.org.ua/football.html</link>')
    lines.append('    <description>Football match torrents scraped from sport-video.org.ua</description>')
    lines.append(f'    <lastBuildDate>{datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")}</lastBuildDate>')

    for item in items:
        lines.append('    <item>')
        lines.append(f'      <title>{item["title"]}</title>')
        lines.append(f'      <link>{item["torrent_url"]}</link>')
        lines.append(f'      <guid>{item["torrent_url"]}</guid>')
        lines.append(f'      <pubDate>{item["pub_date"]}</pubDate>')
        lines.append(f'      <enclosure url="{item["torrent_url"]}" type="application/x-bittorrent"/>')
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
    print("📥 Fetching football page...")
    html = fetch_page(FOOTBALL_PAGE)

    print("🔍 Parsing torrent links...")
    items = parse_torrents(html)

    if not items:
        raise Exception("❌ No torrents found — page structure may have changed.")

    print("🔧 Building RSS feed...")
    rss = build_rss(items)

    print("☁️  Pushing to Gist...")
    push_to_gist(rss)
