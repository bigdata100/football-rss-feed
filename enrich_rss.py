import requests
from bs4 import BeautifulSoup
from urllib.parse import quote, unquote
from datetime import datetime, timezone
import json
import os
import re
import time

BASE_URL = "https://www.sport-video.org.ua"
FOOTBALL_PAGE = f"{BASE_URL}/football.html"
GIST_ID = os.environ["GIST_ID"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]

# Detail pages look like /EWUW090626.html (uppercase code + DDMMYY)
DETAIL_RE = re.compile(r"/([A-Z][A-Za-z]{0,11}\d{6})\.html$")

MAX_DETAIL_PAGES = 25  # safety cap on extra fetches per run

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
}

PROXY_TEMPLATES = [
    "https://api.allorigins.win/raw?url={url}",
    "https://corsproxy.io/?{url}",
    "https://api.codetabs.com/v1/proxy?quest={url}",
    "https://thingproxy.freeboard.io/fetch/{url}",
]


def is_valid_page(text):
    """Reject proxy junk: a real sport-video page contains its builder markup
    or torrent links. Length alone is not enough (allorigins once returned a
    200 error page that passed the old len>500 check)."""
    if not text or len(text) < 1000:
        return False
    t = text.lower()
    return ".torrent" in t or "wb_layoutgrid" in t or "sport-video" in t


def fetch_page(target_url):
    encoded = quote(target_url, safe="")

    print(f"🌐 Fetching {target_url}")
    try:
        r = requests.get(target_url, headers=HEADERS, timeout=15)
        if r.status_code == 200 and is_valid_page(r.text):
            print("✅ Direct fetch succeeded!")
            return r.text
        print(f"⚠️  Direct fetch returned {r.status_code} (or invalid content)")
    except Exception as e:
        print(f"⚠️  Direct fetch failed: {e}")

    for template in PROXY_TEMPLATES:
        proxy_url = template.format(url=encoded)
        print(f"🔄 Trying proxy: {proxy_url[:60]}...")
        try:
            r = requests.get(proxy_url, headers=HEADERS, timeout=20)
            if r.status_code == 200 and is_valid_page(r.text):
                print("✅ Proxy fetch succeeded!")
                return r.text
            print(f"⚠️  Got {r.status_code} or invalid content, trying next...")
        except Exception as e:
            print(f"⚠️  Proxy failed: {e}, trying next...")

    raise Exception(f"❌ All fetch methods failed for {target_url}")


def absolutize(href):
    href = href.strip()
    if href.startswith("http"):
        return href
    return BASE_URL + "/" + href.lstrip("./").lstrip("/")


def title_from_torrent_url(url):
    """Derive a clean title from the torrent filename, e.g.
    'England%20Women%20vs%20Ukraine%20Women%2009.06.2026.mkv.torrent'
    -> 'England Women vs Ukraine Women 09.06.2026'"""
    name = unquote(url.split("/")[-1])
    name = re.sub(r"\.(mkv|mp4|avi|ts)\.torrent$", "", name, flags=re.I)
    name = re.sub(r"\.torrent$", "", name, flags=re.I)
    return name.replace("_", " ").replace("+", " ").strip()


def make_item(torrent_url):
    torrent_url = torrent_url.replace(" ", "%20").replace("&", "%26")
    title = title_from_torrent_url(torrent_url)

    date_match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", title)
    if date_match:
        day, month, year = date_match.groups()
        try:
            pub_date_str = datetime(int(year), int(month), int(day), tzinfo=timezone.utc).strftime(
                "%a, %d %b %Y 00:00:00 +0000")
        except ValueError:
            pub_date_str = datetime.now(timezone.utc).strftime("%a, %d %b %Y 00:00:00 +0000")
    else:
        pub_date_str = datetime.now(timezone.utc).strftime("%a, %d %b %Y 00:00:00 +0000")

    return {"title": title, "torrent_url": torrent_url, "pub_date": pub_date_str}


def parse_listing(html):
    """Returns (direct_torrent_urls, detail_page_urls), order-preserving, deduped."""
    soup = BeautifulSoup(html, "html.parser")
    torrents, details = [], []
    seen_t, seen_d = set(), set()

    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        absu = absolutize(href)
        if href.lower().endswith(".torrent"):
            if absu not in seen_t:
                seen_t.add(absu)
                torrents.append(absu)
        elif DETAIL_RE.search(absu.split("?")[0]):
            if absu not in seen_d:
                seen_d.add(absu)
                details.append(absu)

    return torrents, details


def torrent_from_detail_page(html):
    """A detail page has one TORRENT button -> first .torrent link wins."""
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("a", href=True):
        if link["href"].strip().lower().endswith(".torrent"):
            return absolutize(link["href"])
    return None


def collect_items(listing_html):
    direct, details = parse_listing(listing_html)
    print(f"🔗 Listing: {len(direct)} direct torrent links, {len(details)} detail pages")

    items = []
    seen_urls = set()

    for url in direct:
        if url not in seen_urls:
            seen_urls.add(url)
            item = make_item(url)
            print(f"  📌 {item['title']}")
            items.append(item)

    for page_url in details[:MAX_DETAIL_PAGES]:
        try:
            html = fetch_page(page_url)
        except Exception as e:
            print(f"  ⚠️  Skipping {page_url}: {e}")
            continue
        torrent_url = torrent_from_detail_page(html)
        if not torrent_url:
            print(f"  ⚠️  No torrent link on {page_url}")
            continue
        if torrent_url in seen_urls:
            continue
        seen_urls.add(torrent_url)
        item = make_item(torrent_url)
        print(f"  📌 {item['title']}")
        items.append(item)
        time.sleep(1)  # be polite between detail-page fetches

    print(f"✅ Found {len(items)} torrents total")
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
    items = collect_items(html)

    if not items:
        raise Exception("❌ No torrents found — page structure may have changed.")

    print("🔧 Building RSS feed...")
    rss = build_rss(items)

    print("☁️  Pushing to Gist...")
    push_to_gist(rss)
