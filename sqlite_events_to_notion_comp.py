##Author: 
##Date Started:
##Notes:

import os
import sqlite3
import requests
import re
import html
import datetime
import settings

# Set your Notion API key and Notion Database ID via environment variables or hardcode them.
NOTION_API_KEY = os.environ.get("NOTION_API_KEY", settings.token)
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", settings.db)

HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

SQLITE_DB = 'events2.db'

def html_to_markdown(html_text):
    """
    Convert HTML to Markdown-style formatted text.
    - Converts <a href="...">text</a> to [text](url)
    - Converts <b>/<strong> to **bold**
    - Converts <i>/<em> to *italic*
    - Replaces <br> with newlines and </p> with double newlines
    - Removes any remaining tags and unescapes entities.
    """
    markdown = re.sub(
        r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        r'[\2](\1)',
        html_text,
        flags=re.IGNORECASE | re.DOTALL
    )
    markdown = re.sub(r'<\s*(b|strong)\s*>(.*?)<\s*/\s*\1\s*>', r'**\2**', markdown, flags=re.IGNORECASE | re.DOTALL)
    markdown = re.sub(r'<\s*(i|em)\s*>(.*?)<\s*/\s*\1\s*>', r'*\2*', markdown, flags=re.IGNORECASE | re.DOTALL)
    markdown = re.sub(r'<br\s*/?>', '\n', markdown, flags=re.IGNORECASE)
    markdown = re.sub(r'</p\s*>', '\n\n', markdown, flags=re.IGNORECASE)
    markdown = re.sub(r'<p\s*>', '', markdown, flags=re.IGNORECASE)
    markdown = re.sub(r'<[^>]+>', '', markdown)
    return html.unescape(markdown)

def fetch_consolidated_events():
    """Retrieve all rows from the consolidated_events table."""
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    c.execute("SELECT composite_id, account, calendar_names, summary, start, end, notes FROM consolidated_events")
    rows = c.fetchall()
    conn.close()
    
    events = []
    for row in rows:
        events.append({
            "composite_id": row[0],
            "account": row[1],
            "calendar_names": row[2],
            "summary": row[3],
            "start": row[4],
            "end": row[5],
            "notes": row[6]
        })
    return events

def init_notion_synced_table():
    """Create a table to track composite events that have already been added to Notion."""
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS notion_synced_events (
            composite_id TEXT PRIMARY KEY,
            synced_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

def is_event_synced(composite_id):
    """Check if the composite_id is already in the notion_synced_events table."""
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    c.execute("SELECT composite_id FROM notion_synced_events WHERE composite_id = ?", (composite_id,))
    row = c.fetchone()
    conn.close()
    return row is not None

def mark_event_synced(composite_id):
    """Mark a composite event as synced by inserting it into notion_synced_events."""
    conn = sqlite3.connect(SQLITE_DB)
    c = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    c.execute("INSERT OR REPLACE INTO notion_synced_events (composite_id, synced_at) VALUES (?, ?)", (composite_id, now))
    conn.commit()
    conn.close()

def query_notion_page(composite_id):
    """Query the Notion database to see if a page with the given composite_id already exists."""
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    payload = {
        "filter": {
            "property": "Event ID",
            "rich_text": {
                "equals": composite_id
            }
        }
    }
    response = requests.post(url, headers=HEADERS, json=payload)
    if response.status_code != 200:
        print("Error querying Notion database:", response.text)
        return []
    data = response.json()
    return data.get("results", [])

def split_text(text, max_length=2000):
    """Split text into chunks no longer than max_length characters."""
    return [text[i:i+max_length] for i in range(0, len(text), max_length)]

def create_notion_page(event):
    """Create a new Notion page for the event, using a multi-select for Calendar."""
    url = "https://api.notion.com/v1/pages"
    
    calendar_options = []
    if event["calendar_names"]:
        for cal in event["calendar_names"].split(','):
            cal = cal.strip()
            if cal:
                calendar_options.append({"name": cal})
    
    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Event ID": {
                "rich_text": [{"text": {"content": event["composite_id"]}}]
            },
            "Title": {
                "title": [{"text": {"content": event["summary"]}}]
            },
            "Calendar": {
                "multi_select": calendar_options
            },
            "Start": {
                "date": {"start": event["start"]}
            },
            "End": {
                "date": {"start": event["end"]}
            }
        },
        "children": []
    }
    
    if event["notes"]:
        converted_notes = html_to_markdown(event["notes"])
        note_chunks = split_text(converted_notes)
        paragraph_blocks = []
        for chunk in note_chunks:
            paragraph_blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": chunk}}]
                }
            })
        toggle_block = {
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": [{"type": "text", "text": {"content": "Notes"}}],
                "children": paragraph_blocks
            }
        }
        payload["children"].append(toggle_block)
    
    response = requests.post(url, headers=HEADERS, json=payload)
    if response.status_code != 200:
        print("Error creating Notion page for event:", event["summary"])
        print("Response:", response.text)
        return False
    else:
        print(f"Created Notion page for event: {event['summary']}")
        return True

def update_notion_database():
    """Update the Notion table based on the consolidated_events table, using a local sync table to speed up updates."""
    init_notion_synced_table()
    events = fetch_consolidated_events()
    for event in events:
        composite_id = event["composite_id"]
        # If we've already synced this composite event, skip it.
        if is_event_synced(composite_id):
            print(f"Skipping already synced event: {event['summary']}")
            continue
        
        # Otherwise, check if it already exists in Notion.
        existing = query_notion_page(composite_id)
        if existing and len(existing) > 0:
            print(f"Event already in Notion, marking as synced: {event['summary']}")
            mark_event_synced(composite_id)
        else:
            # Create the Notion page and if successful, mark it as synced.
            if create_notion_page(event):
                mark_event_synced(composite_id)

if __name__ == '__main__':
    update_notion_database()