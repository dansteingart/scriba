##Author: 
##Date Started:
##Notes:

import os
import sqlite3
import datetime
import hashlib

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
import settings

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
DB_FILE = settings.db_file
CREDENTIALS_FOLDER = settings.creds_folder
# -----------------------------
# Phase 1: Pull All Events into raw_events
# -----------------------------

def init_raw_events_table():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS raw_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account TEXT,
            calendar_id TEXT,
            calendar_name TEXT,
            event_id TEXT,
            summary TEXT,
            start TEXT,
            end TEXT,
            notes TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_service(account_name):
    creds_path = os.path.join(CREDENTIALS_FOLDER, f'{account_name}_credentials.json')
    token_path = os.path.join(CREDENTIALS_FOLDER, f'{account_name}_token.json')
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, 'w') as token_file:
            token_file.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)

def pull_raw_events(account_name):
    service = get_service(account_name)
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    future = (datetime.datetime.utcnow() + datetime.timedelta(days=7)).isoformat() + 'Z'
    
    calendars = service.calendarList().list().execute().get('items', [])
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for cal in calendars:
        calendar_id = cal['id']
        calendar_name = cal.get('summary', '')
        try:
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=now,
                timeMax=future,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])
            for event in events:
                summary = event.get('summary', 'No Title')
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                notes = event.get('description', '')
                event_id = event.get('id', '')
                c.execute('''
                    INSERT INTO raw_events (account, calendar_id, calendar_name, event_id, summary, start, end, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (account_name, calendar_id, calendar_name, event_id, summary, start, end, notes))
        except HttpError as error:
            print(f"Error fetching events for calendar {calendar_name}: {error}")
    conn.commit()
    conn.close()

# -----------------------------
# Phase 2: Consolidate Duplicate Events
# -----------------------------

def init_consolidated_events_table():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS consolidated_events (
            composite_id TEXT PRIMARY KEY,
            account TEXT,
            calendar_names TEXT,
            summary TEXT,
            start TEXT,
            end TEXT,
            notes TEXT
        )
    ''')
    conn.commit()
    conn.close()

def compute_composite_id(summary, start, end, notes):
    """
    Compute a composite MD5 hash from key event fields.
    This hash is used to detect duplicates (even if native event IDs differ).
    """
    composite_str = f"{summary}||{start}||{end}||{notes}"
    return hashlib.md5(composite_str.encode('utf-8')).hexdigest()

def consolidate_raw_events():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Read all events from raw_events.
    c.execute("SELECT account, calendar_name, summary, start, end, notes FROM raw_events")
    rows = c.fetchall()
    
    # Use a dictionary to consolidate events by composite_id.
    consolidated = {}
    for row in rows:
        account, calendar_name, summary, start, end, notes = row
        composite_id = compute_composite_id(summary, start, end, notes)
        if composite_id in consolidated:
            # Add calendar_name if not already in the list.
            existing_calendars = set(consolidated[composite_id]['calendar_names'].split(',')) if consolidated[composite_id]['calendar_names'] else set()
            existing_calendars.add(calendar_name)
            consolidated[composite_id]['calendar_names'] = ','.join(sorted(existing_calendars))
        else:
            consolidated[composite_id] = {
                'account': account,
                'calendar_names': calendar_name,
                'summary': summary,
                'start': start,
                'end': end,
                'notes': notes
            }
    
    # Insert or update the consolidated events.
    for composite_id, data in consolidated.items():
        c.execute('''
            INSERT OR REPLACE INTO consolidated_events (composite_id, account, calendar_names, summary, start, end, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (composite_id, data['account'], data['calendar_names'], data['summary'], data['start'], data['end'], data['notes']))
    conn.commit()
    conn.close()
    print("Consolidation complete. Total consolidated events:", len(consolidated))

# -----------------------------
# Main Execution
# -----------------------------

if __name__ == '__main__':
    # Initialize both tables.
    init_raw_events_table()
    init_consolidated_events_table()
    
    # Replace these with your Google account identifiers.
    accounts = ['personal', 'work']
    for acct in accounts:
        pull_raw_events(acct)
    
    # Now consolidate duplicates from raw_events into consolidated_events.
    consolidate_raw_events()