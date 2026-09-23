# A little room

A small local journal: Python 3.12+, standard-library HTTP and SQLite, and plain HTML/CSS/JavaScript. No package installation, account, build step, vector database, or AI service is required.

## Start

On this computer, double-click **Personal Journal** on the desktop or bookmark **http://127.0.0.1:8765/** in Chrome. A Windows Startup shortcut starts the app quietly when you sign in. It stays available after the browser closes, while the computer is awake and you remain signed in. No terminal window is needed. Reopening the launcher reuses the running app. To disable automatic startup, disable Personal Journal in Windows Startup Apps or remove its shortcut from the Windows Startup folder. The launcher location depends on this project folder remaining in place.

`install-launcher.ps1` installs the desktop and Startup shortcuts, using the installed Python's `pythonw.exe`. `launcher.py --background` starts without opening the browser. The manual alternative is below; stop the background instance before starting another server on the same port.

From this directory:

```powershell
python app.py
```

Open http://127.0.0.1:8765. On this computer, `config.local.json` selects `C:\Obsidian-Personal`. Without that local configuration, the app uses `demo-vault/`. Choose a date, fill in the morning or evening prompts, and click Save. Reload the page to read it back. Saving the other period updates the same file. Changes are saved only when you click Save.

To use your real vault, stop the server with Ctrl+C and restart with its actual path:

```powershell
python app.py --vault "C:\path\to\your\ObsidianVault"
```

Optional: `--port 8766` or `--database "C:\path\outside-vault\oura.sqlite3"`.

For a persistent vault choice, set `{"vault": "C:\\Obsidian-Personal"}` in `config.local.json` next to `app.py`. This file is ignored by Git. The folder must already exist; `--vault` overrides this setting for one launch.

## Files and responsibilities

```text
journal-app/
  app.py                 Loopback-only server and JSON endpoints
  journal.py             Daily Markdown read/update and date-range reads
  oura.py                Separate SQLite schema, upsert, and range reads
  oura_sync.py           OAuth, rotating refresh tokens, hourly daily-summary imports
  secrets_store.py       Windows DPAPI encryption for Oura credentials
  launcher.py            Quiet background launcher, reuses a running instance
  install-launcher.ps1   Desktop and Windows Startup shortcut installation
  static/                Browser interface, styles, and behavior
  tests/test_app.py       Storage and HTTP integration checks
  demo-vault/Journal/     Default local journal (ignored by Git)
  data/oura.sqlite3      Oura database (ignored by Git)
```

Your chosen vault is the canonical journal store. Entries use `Journal/YYYY-MM-DD.md`, with YAML `date`, `type`, and `tags` on new files. The browser edits ordinary `## Morning` and `## Evening` sections. Prompts use `###` headings; answers can include Markdown. Existing frontmatter and text outside the selected section are preserved, including notes without frontmatter. Duplicate session headings require manual correction before editing in the app.

Morning sections open as three answer boxes; evening sections have four main prompts and two optional add-ons in an expandable section. Answer boxes include short writing suggestions. Switch to “Write freely in Markdown” to edit the whole section. Custom sections open in the Markdown editor so their structure is preserved; guided mode is available when the standard prompt headings for that period are present. Both modes save to the same daily file.

The date defaults to your browser's local day. Unsaved drafts are saved on each edit in browser local storage, keyed by vault, date, period, and editing session. Reloading or revisiting that date restores the most recent draft. Each tab writes a separate draft. Click Save to commit it to Markdown. Recovery is specific to this browser/profile and address; clearing site data or using private browsing can remove drafts. The Codex browser and Chrome do not share drafts. If browser storage is unavailable, a warning asks you to save before leaving. Drafts are local plaintext, like your Markdown files.

A recovered draft retains its original file revision: it cannot silently overwrite a note changed in Obsidian. Copy the recovered text before using Reload note to discard the current draft and review the saved version. Browser drafts are not backups. Journal content is never stored in the Oura SQLite database.

Past entries lists saved daily files newest first. Morning/evening indicators show `written` when at least one non-heading answer exists, `blank` for a saved prompt-only section, and `missing` when that section hasn't been saved. These are writing indicators, not a requirement to answer every prompt.

## Phone access with Obsidian Sync

1. Open the chosen folder as a vault in desktop Obsidian.
2. Enable Obsidian Sync and connect the vault to a remote vault.
3. On your phone, use Obsidian Sync to connect to that same remote vault.
4. Keep desktop Obsidian running so its Sync plugin can detect local edits. Write or edit the Markdown on your phone in Obsidian.

The custom browser app runs on your computer only. Phone access uses Obsidian, not this web interface. Sync is configured in Obsidian and requires its subscription; the app does not implement a second sync layer. See [Obsidian's setup instructions](https://obsidian.md/help/sync/setup).

Save checks the file revision and writes via a temporary file and atomic replacement. Stale edits are rejected. An external editor or sync process can still race in the tiny interval between the final check and replacement; this is not a distributed locking system. Avoid simultaneous edits to one note across devices, let Sync finish, and retain backups/version history.

## Oura and future AI queries

Oura connects through an existing developer app using the `daily` scope only. In Oura's developer portal, add **http://localhost:8765/api/oura/callback** to the app's redirect URIs (preserve existing URIs). Oura requires the literal `localhost` name for HTTP redirects. In the journal's Oura connection settings, enter the client ID and secret, save, then click Connect Oura and authorize the account. Keep the same browser for this flow. Client credentials and rotating tokens are stored in `data/oura-secrets.bin`, encrypted with Windows DPAPI for the signed-in Windows user; they are never returned to the browser. The app sends no journal text to Oura.

After authorization the background worker imports the past 90 days, then checks hourly and refreshes the past 30 days. It resumes checking after startup/wake. Sync now triggers an immediate check. API failures appear in connection status; existing imported records remain available. Activity for today may still be incomplete. Sync the ring with the Oura phone app to make current data available to Oura's API.

The panel shows daily sleep, readiness, and activity scores plus steps for the selected journal date. Missing values display a dash rather than zero. Raw daily summaries are stored in SQLite by `(kind, id)`, with date and import timestamp, so repeat imports update instead of duplicating records. Disconnect deletes local tokens and stops future fetches, retaining imported history; revoke authorization in your Oura account if desired. Detailed sleep periods are also imported, including sleep duration, stages, efficiency, bedtime/wake time, average HRV, lowest and average sleeping heart rate, and breathing rate. The expandable sleep panel shows each period separately on its Oura-assigned day, using recorded local times. Durations are converted from seconds and rounded to minutes; missing readings stay blank rather than becoming zero. Raw sleep payloads remain in SQLite for later queries. Continuous daytime heart-rate data is not fetched. Existing connections get a one-time 90-day sleep backfill, followed by the normal 30-day refresh window.

For a later AI feature, use `Journal.read_range(start, end)` and `OuraStore.read_range(start, end)` to gather selected dates directly. Add a preview of exactly what will be sent and an explicit send action before any model integration. There is no indexing or RAG.

## Verify

```powershell
python -m unittest discover -s tests -v
node --check static/app.js
```

This server is for personal use on localhost. It checks Host/Origin, rejects cross-origin writes, serves an explicit asset list, and binds exclusively to loopback. OAuth uses a short-lived one-use state and browser cookie. Journal and SQLite data remain ordinary local files; only the Oura credential file is encrypted. DPAPI tests must run as the normal Windows user; a restricted sandbox may not have access to that user's encryption services.



## Morning plans and evening progress
The good-day morning prompt has four optional single-line entries, saved as Markdown bullets. Existing answers with up to four nonempty lines open in these fields; longer/custom answers remain in the Markdown editor without truncation. Save the morning entry before reviewing it in the evening. The evening check-in saves standard Markdown task checkboxes and preserves earlier checklist items if morning plans later change.

Evening includes optional 1–5 good-day and productivity ratings, stored in a Daily ratings Markdown subsection. Your progress shows 30 days of ratings and a journaling streak. Unrated days remain missing, not zero. The streak counts consecutive days with saved writing, checked tasks, or a rating, starting today or yesterday if today is still unwritten. Browser drafts do not count. Checkmarks and ratings participate in draft recovery and file conflict checks.


Morning also offers four if-time entries. Both lists become evening checkboxes. Carry forward reviews unfinished items from the latest earlier saved plan (including across gaps); without an evening checklist, completion is labeled unknown. Choose either list or Skip today. Nothing is added automatically, and each list remains limited to four. Choices are saved with the morning entry and recovered with drafts. This is a review of the most recent plan, not a permanent backlog of every skipped task.


### Optional plans and completion history

The if-time list starts with one field; **+ Add item** adds more without a four-item limit. Good-day plans retain their four-item limit. Saved nonempty fields reappear on reload. Both lists remain in the evening checklist.

Carry-forward review includes **Already done**. Tick it and save the morning entry to record completion on that journal date. Once added to today's plans, complete the item in the evening checklist. Carrying an unfinished item does not change the previous night's unchecked box.

**Completed tasks** shows creation and completion dates and is archived at `Tasks/Completed tasks.md` in the configured vault. Explicit carry decisions preserve the original date across days and categories; independently typed tasks are new tasks. For existing entries the creation date is the original journal date, not the file's modification timestamp. The archive is an audit history: previously saved completions remain if a checkbox is subsequently cleared or a note removed. Keep the app-managed metadata comment intact. Journal notes remain the editable source; archive updates run on save and when the task history loads. A failed archive update is reported without undoing a successful journal save.

### Day classification
Each journal note stores `journal_calendar` in its YAML frontmatter: `is_weekend`, `is_work_holiday`, actual and observed holiday names, and the calendar used. The entry API exposes the same information under `calendar`, including for dates without a saved note. Weekend means Saturday/Sunday. Work holidays use recurring US federal holidays and standard Friday/Monday observance per https://www.opm.gov/policy-data-oversight/pay-leave/federal-holidays/. This is a calendar indicator, not your employer's actual time-off schedule; state/company holidays and one-off executive holidays are excluded. Rules target modern journal dates; Juneteenth begins in 2021. Calendar metadata refreshes whenever a note is saved.

### Restaurants

The top navigation opens Journal by default, with Restaurants as a separate section. Add a restaurant, select its visit date (defaults to the local current date), and expand it to add dishes. Restaurant and dish reviews each include an optional 1–5 score and a single Thoughts field. Legacy review text is merged into Thoughts when opened, then persisted on Save restaurants. **Add Ashley** reveals an independent set of fields for her. Ratings may remain unrated.

Use **Save restaurants** to persist the collection in `Restaurants/restaurants.json` inside the configured vault. Browser drafts are separate from journal drafts and recover after refresh. Atomic writes and revision checks prevent a stale tab from silently overwriting newer saved reviews. This first version has one visit date per restaurant entry; multiple visits can be entered as separate entries. No restaurant data is sent to a third party.

### People

People is available from the top navigation. Add a name and relation, select a person, and save individual dated notes. Dates default to today and can be backdated; the timeline shows newest dates first and supports multiple notes on the same date. Search matches names, relations, and note text. Saved data is local at `People/people.json` in the vault. Each form keeps an unfinished browser draft. Server-side append operations preserve other people's and earlier notes, and stable request IDs prevent duplicate entries if a save is retried. The first version supports adding people and notes, not editing or deleting saved records.

### Evening task edits and follow-ups

Each evening checklist item has **Edit task / add follow-up**. The evening description can describe the portion actually completed; the morning plan remains unchanged and is shown for reference. Tick the revised task when done, enter the remaining work, and click **Add follow-up**, then **Save evening entry**. A follow-up is its own unchecked task in the same category and can itself be edited. Inline Markdown metadata preserves original text and the parent relationship. The next carry-forward review uses edited evening descriptions and includes unfinished follow-ups. Carry-forward still reviews the latest previous entry with plans; a persistent backlog remains a separate proposed feature.

## Recovering the background server on Windows

Run `powershell -ExecutionPolicy Bypass -File .\install-background-task.ps1` once as your normal Windows user. Windows Task Scheduler starts the local server at login and checks every minute to relaunch it if it exits. Only one scheduled instance runs at a time, with no execution time limit or battery shutdown. The desktop launcher still works. The existing login shortcut is harmless: the launcher reuses an already running server.

The server stays local to this PC. It cannot serve requests while the PC is asleep, powered off, or signed out. GitHub stores source code; it does not host the running app. To stop background recovery, disable the **Personal Journal** task in Windows Task Scheduler. Logs are in `data/startup.log` and are never committed.
