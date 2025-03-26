# Calendar to Notion Sync Tool

This project is a sophisticated calendar synchronization tool that fetches events from multiple Google Calendar accounts, consolidates duplicate events, and syncs them to a Notion database. It's designed to handle both personal and work calendars while avoiding duplicate entries.

## Features

- Multi-account Google Calendar integration
- Automatic duplicate event detection and consolidation
- SQLite database for intermediate storage
- Notion database synchronization
- HTML to Markdown conversion for event notes
- Efficient sync tracking to avoid redundant updates

## Project Structure

The project consists of several key components:

1. **Calendar to SQLite (`cal_to_sqlite_to_md_comp.py`)**
   - Fetches events from Google Calendar
   - Stores events in a SQLite database
   - Handles authentication for multiple accounts
   - Consolidates duplicate events

2. **SQLite to Notion Sync (`sqlite_events_to_notion_comp.py`)**
   - Reads consolidated events from SQLite
   - Converts event data to Notion format
   - Handles HTML to Markdown conversion
   - Manages sync state to avoid duplicates

3. **Supporting Files**
   - `events2.db`: SQLite database storing calendar events
   - `personal_credentials.json` & `work_credentials.json`: Google OAuth credentials
   - `personal_token.json` & `work_token.json`: OAuth tokens
   - `upcoming_events.md`: Markdown output of events
   - `doit.sh`: Shell script for running the sync

## Setup

1. **Google Calendar Setup**
   - Create OAuth 2.0 credentials for each Google account
   - Save credentials as `personal_credentials.json` and `work_credentials.json`
   - First run will prompt for authentication

2. **Notion Setup**
   - Create a Notion database with the following properties:
     - Title (title)
     - Event ID (rich text)
     - Calendar (multi-select)
     - Start (date)
     - End (date)
   - Set up environment variables:
     - `NOTION_API_KEY`
     - `NOTION_DATABASE_ID`

## Usage

1. **Initial Setup**
   ```bash
   # Run the calendar sync
   python cal_to_sqlite_to_md_comp.py
   
   # Sync to Notion
   python sqlite_events_to_notion_comp.py
   ```

2. **Regular Updates**
   - Use the provided `doit.sh` script or set up a cron job
   - Example cron entry:
     ```
     0 * * * * /path/to/doit.sh
     ```

## Database Schema

### Raw Events Table
```sql
CREATE TABLE raw_events (
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
```

### Consolidated Events Table
```sql
CREATE TABLE consolidated_events (
    composite_id TEXT PRIMARY KEY,
    account TEXT,
    calendar_names TEXT,
    summary TEXT,
    start TEXT,
    end TEXT,
    notes TEXT
)
```

### Notion Synced Events Table
```sql
CREATE TABLE notion_synced_events (
    composite_id TEXT PRIMARY KEY,
    synced_at TEXT
)
```

## Features in Detail

### Duplicate Detection
- Uses MD5 hashing of event details to identify duplicates
- Combines events from multiple calendars if they represent the same event
- Preserves all calendar sources in the consolidated event

### HTML to Markdown Conversion
- Converts HTML formatting in event notes to Markdown
- Handles links, bold text, italic text, and basic formatting
- Splits long notes into manageable chunks for Notion

### Sync Management
- Tracks which events have been synced to Notion
- Prevents duplicate creation of Notion pages
- Maintains sync state between runs

## Security

- OAuth tokens are stored locally
- API keys should be managed via environment variables
- Credentials are stored in separate files for different accounts

## Dependencies

- Google Calendar API
- Notion API
- SQLite3
- Python standard library
- OAuth2 authentication libraries

## Notes

- The tool is designed to handle both personal and work calendars
- Duplicate events are automatically consolidated
- Event notes are preserved and formatted appropriately
- The sync process is incremental and efficient 