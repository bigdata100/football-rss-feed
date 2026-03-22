import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
from datetime import datetime, timezone
import json
import os
import re

BASE_URL = "https://www.sport-video.org.ua"
FOOTBALL_PAGE = f"{BASE_URL}/football.html"
GIST_ID = os.environ["GIST_ID"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
}

PROXY_TEMPLATES = [
    "https://api.allorigins.win/raw?url={url}",
    "https://corsproxy.io/?{url}",
    "https://api.codetabs.com/v1/proxy?quest={url}",
    "https://thingproxy.freeboard.io/fetch/{url}",
]

def fetch_page(target_url):
    encoded = quote(target_url, safe="")

    print(f"🌐 Trying direct fetch...")
    try:
        r = requests.get(target_url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            print("✅ Direct fetch succeeded!")
            return r.text
        print(f"⚠️  Direct fetch returned {r.status_code}")
    except Exception as e:
        print(f"⚠️  Direct fetch failed: {e}")

    for template in PROXY_TEMPLATES:
        proxy_url = template.format(url=encoded)
        print(f"🔄 Trying proxy: {proxy_url[:60]}...")
        try:
            r = requests.get(proxy_url, headers=HEADERS, timeout=20)
            if r.status_code == 200 and len(r.text) > 500:
                print("✅ Proxy fetch succeeded!")
                return r.text
            print(f"⚠️  Got {r.status_code}, trying next...")
        except Exception as e:
            print(f"⚠️  Proxy failed: {e}, trying next...")

    raise Exception("❌ All proxies failed.")

def parse_torrents(html):
    soup = BeautifulSoup(html, "html.parser")
    items = []

    for link in soup.find_all("a", href=True):
        href = link["href"]
        if not href.endswith(".torrent"):
            continue

        # The page structure is: <b>Match Title</b> <a href="...">TORRENT</a>
        # So we look at the previous sibling elements to find the bold title
        title = ""

        # Walk backwards through previous siblings to find a <b> or <strong> tag
        for sibling in link.previous_siblings:
            if sibling.name in ("b", "strong"):
                title = sibling.get_text(strip=True)
                break
            # Also check if sibling is a tag containing bold
            if hasattr(sibling, "find"):
                bold = sibling.find(["b", "strong"])
                if bold:
                    title = bold.get_text(strip=True)
                    break

        # Fallback: extract from filename
        if not title or title.upper() == "TORRENT":
            title = href.split("/")[-1].replace(".mkv.torrent", "").replace("%20", " ").replace("+", " ")

        # Build absolute torrent URL
        if href.startswith("http"):
            torrent_url = href
        else:
            torrent_url = BASE_URL + "/" + href.lstrip("/")

        torrent_url = torrent_url.replace(" ", "%20").replace("&", "%26")

        # Extract date from title
        date_match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", title)
        if date_match:
            day, month, year = date_match.groups()
            pub_date_str = datetime(int(year), int(month), int(day), tzinfo=timezone.utc).strftime("%a, %d %b %Y 00:00:00 +0000")
        else:
            pub_date_str = datetime.now(timezone.utc).strftime("%a, %d %b %Y 00:00:00 +0000")

        print(f"  📌 {title}")
        items.append({"title": title, "torrent_url": torrent_url, "pub_date": pub_date_str})

    print(f"✅ Found {len(items)} torrents")
    return items

def build_rss(items):
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        '  <channel>',
        '    <title>Football Torrents - sport-video.org.ua</title>',
        '    <link>https://www.sport-video.org.ua/football.html</link>',
        '    <description>Football match torrents scraped from sport-video.org.ua</description>',
        f'    <lastBuildDate>{datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")}</lastBuildDate>',
    ]
    for item in items:
        lines += [
            '    <item>',
            f'      <title>{item["title"]}</title>',
            f'      <link>{item["torrent_url"]}</link>',
            f'      <guid>{item["torrent_url"]}</guid>',
            f'      <pubDate>{item["pub_date"]}</pubDate>',
            f'      <enclosure url="{item["torrent_url"]}" type="application/x-bittorrent"/>',
            '    </item>',
        ]
    lines += ['  </channel>', '</rss>']
    return "\n".join(lines)

def push_to_gist(content):
    url = f"https://api.github.com/gists/{GIST_ID}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {"files": {"football_torrents.rss": {"content": content}}}
    r = requests.patch(url, headers=headers, data=json.dumps(payload), timeout=15)
    r.raise_for_status()
    raw_url = r.json()["files"]["football_torrents.rss"]["raw_url"]
    print(f"✅ Gist updated! RSS URL: {raw_url}")

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
