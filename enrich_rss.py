import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote
import json
import os

RSS_URL = "https://www.sport-video.org.ua/rss.xml"
BASE_TORRENT_URL = "https://www.sport-video.org.ua/"
GIST_ID = os.environ["GIST_ID"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]

def fetch_rss():
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(RSS_URL, headers=headers, timeout=15)
    response.raise_for_status()
    return response.text

def build_torrent_url(title):
    filename = title.strip() + ".mkv.torrent"
    return BASE_TORRENT_URL + quote(filename)

def enrich_rss(raw_xml):
    # Parse the original RSS
    ET.register_namespace("", "")
    root = ET.fromstring(raw_xml)

    # Find the channel
    channel = root.find("channel")

    new_feed_lines = []
    new_feed_lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    new_feed_lines.append('<rss version="2.0">')
    new_feed_lines.append('  <channel>')
    new_feed_lines.append('    <title>Football Torrents - sport-video.org.ua</title>')
    new_feed_lines.append('    <link>https://www.sport-video.org.ua/football.html</link>')
    new_feed_lines.append('    <description>Football match torrents auto-enriched from sport-video.org.ua</description>')

    for item in channel.findall("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pub_date_el = item.find("pubDate")
        desc_el = item.find("description")

        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        link = link_el.text.strip() if link_el is not None and link_el.text else ""
        pub_date = pub_date_el.text.strip() if pub_date_el is not None and pub_date_el.text else ""
        desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ""

        torrent_url = build_torrent_url(title)

        new_feed_lines.append('    <item>')
        new_feed_lines.append(f'      <title>{title}</title>')
        new_feed_lines.append(f'      <link>{torrent_url}</link>')
        new_feed_lines.append(f'      <guid>{torrent_url}</guid>')
        if pub_date:
            new_feed_lines.append(f'      <pubDate>{pub_date}</pubDate>')
        if desc:
            new_feed_lines.append(f'      <description>{desc}</description>')
        new_feed_lines.append(f'      <enclosure url="{torrent_url}" type="application/x-bittorrent"/>')
        new_feed_lines.append('    </item>')

    new_feed_lines.append('  </channel>')
    new_feed_lines.append('</rss>')

    return "\n".join(new_feed_lines)

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
    gist_data = response.json()
    raw_url = gist_data["files"]["football_torrents.rss"]["raw_url"]
    print(f"📡 Raw RSS URL: {raw_url}")

if __name__ == "__main__":
    print("📥 Fetching RSS feed...")
    raw_xml = fetch_rss()
    print("🔧 Enriching with torrent links...")
    enriched = enrich_rss(raw_xml)
    print("☁️  Pushing to Gist...")
    push_to_gist(enriched)
