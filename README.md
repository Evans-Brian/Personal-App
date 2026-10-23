# Personal-App

A small local journal: Python 3.12+, standard-library HTTP and SQLite, and plain HTML/CSS/JavaScript. Core journaling and exact search require no package installation, account, build step, vector database, or AI service. Optional local voice and semantic-search setup scripts install their private runtimes under ignored `data/` folders.

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

The BJJ tab reads a private local instructional library from the `bjj_library` path in `config.local.json`. The manual override is `--bjj-library "C:\path\to\your\BJJLibrary"`. Media, transcripts, indexes, BJJ work state, and vault notes stay outside Git; shared optional runtimes and embedding model caches live under ignored `data/` folders.

## Files and responsibilities

```text
Personal-App/
  app.py                 Loopback-only server and JSON endpoints
  bjj.py                 Private BJJ library, transcript search, notes, and journals
  embeddings.py          Offline BGE inference and binary-vector encoding
  setup_embeddings.py    One-time local FastEmbed/model install and index rebuild
  eval_bjj_search.py     Reproducible hash/BGE/hybrid retrieval evaluation
  prepare_bjj.py         Local BJJ media validation and manifest generation
  transcribe_bjj.py      Restart-safe local BJJ transcription and indexing
  official_chapters.py   BJJ Fanatics chapter starts used by the manifest
  journal.py             Daily Markdown read/update and date-range reads
  oura.py                Separate SQLite schema, upsert, and range reads
  oura_sync.py           OAuth, rotating refresh tokens, hourly daily-summary imports
  secrets_store.py       Windows DPAPI encryption for local credentials
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

This Obsidian Sync workflow edits notes on your phone outside the web interface. For private browser access from other devices, including the mobile BJJ view, see [Private access from other devices](#private-access-from-other-devices). Sync is configured in Obsidian and requires its subscription; the app does not implement a second sync layer. See [Obsidian's setup instructions](https://obsidian.md/help/sync/setup).

Save checks the file revision and writes via a temporary file and atomic replacement. Stale edits are rejected. An external editor or sync process can still race in the tiny interval between the final check and replacement; this is not a distributed locking system. Avoid simultaneous edits to one note across devices, let Sync finish, and retain backups/version history.

## Oura and AI boundaries

Oura connects through an existing developer app requesting `daily` and `spo2` access. Existing daily-only connections still work; blood oxygen remains unavailable until that permission is granted through Reconnect Oura. In Oura's developer portal, add **http://localhost:8765/api/oura/callback** to the app's redirect URIs (preserve existing URIs). Oura requires the literal `localhost` name for HTTP redirects. In the journal's Oura connection settings, enter the client ID and secret, save, then click Connect Oura and authorize the account. Keep the same browser for this flow. Client credentials and rotating tokens are stored in `data/oura-secrets.bin`, encrypted with Windows DPAPI for the signed-in Windows user; they are never returned to the browser. The app sends no journal text to Oura.

After authorization the background worker imports the past 90 days, then checks hourly and refreshes the past 30 days. It resumes checking after startup/wake. Sync now triggers an immediate check. API failures appear in connection status; existing imported records remain available. Activity for today may still be incomplete. Sync the ring with the Oura phone app to make current data available to Oura's API.

The Journal shows a compact Oura row: the selected date and its Sleep, Readiness and Activity scores, with small Sync and Settings controls. Missing scores remain dashes, not zero or readings borrowed from another date. Settings contains connection status, last-sync details, reconnect/disconnect and the developer-app form. Errors and syncing progress remain visible without opening Settings. Detailed sleep periods, HRV and heart-rate breakdowns live in the Sleep dashboard, not duplicated in Journal.

The panel shows daily sleep, readiness, and activity scores plus steps for the selected journal date. Missing values display a dash rather than zero. Raw daily summaries are stored in SQLite by `(kind, id)`, with date and import timestamp, so repeat imports update instead of duplicating records. Disconnect deletes local tokens and stops future fetches, retaining imported history; revoke authorization in your Oura account if desired. Detailed sleep periods are also imported, including sleep duration, stages, efficiency, bedtime/wake time, average HRV, lowest and average sleeping heart rate, and breathing rate. The expandable sleep panel shows each period separately on its Oura-assigned day, using recorded local times. Durations are converted from seconds and rounded to minutes; missing readings stay blank rather than becoming zero. Raw sleep payloads remain in SQLite for later queries. Continuous daytime heart-rate data is not fetched. Existing connections get a one-time 90-day sleep backfill, followed by the normal 30-day refresh window.

The private BJJ search index never includes personal journal text or Oura data. A future answer-generation feature should show exactly which BJJ passages would be supplied and require an explicit send action before any cloud-model integration.

### Sleep dashboard

The Sleep tab shows a local, interactive overnight timeline from 10 p.m. to 2 p.m. the following day; trends for bedtime, estimated onset, final wake, sleep duration, total awake time, awake time during sleep, longest awakenings, latency, stages, HR and HRV; and a selected-night view with awakening clock times and physiological samples. The timeline clips its display to that window without changing stored sleep periods or calculations. Date presets and custom ranges operate on imported records. The detailed table provides a textual alternative to charts. Missing nights create chart gaps and never become zero-valued sleep. Each metric shows its own sample count.

Click a graph or its **Enlarge** button to open a larger chart. Values appear in a persistent readout when moving anywhere across the plot; touch users can tap, and keyboard users can use Left/Right or Home/End. The date and all plotted series are shown together. Enlarged views close with **Close**, Escape, or the backdrop. On narrow screens enlarged plots can scroll horizontally while their value readout stays visible. Trend charts, hourly awakening bars and nightly HR/HRV curves use the same interaction.

An optional `sleep_analysis_start` date (`YYYY-MM-DD`) in the ignored `config.local.json` sets a private analysis baseline. Records before it are ignored across the Sleep dashboard, including charts, summaries, comparisons, coverage, history labels and insights. Presets and custom ranges respect the same cutoff, reflected in the starting date. Imported records remain stored, and importing full history cannot reintroduce them into the analysis. Restart the app after changing this setting. Private interpretation preferences belong in ignored project context.

**Import full Oura history** requests paginated records from 2015 onward rather than only the rolling 90-day window. It runs in the background with visible progress. Repeated imports update existing records. Sleep summaries, detailed sleep, readiness and activity are required; SpO2, bedtime guidance and daytime stress are supplementary and may be unavailable with existing permissions or device history. Failure to fetch a supplementary collection for lack of access is displayed without losing the core import. Raw API records, including stage, movement, HR and HRV series, stay in the ignored SQLite database. No personal readings or generated insights are committed.

One longest `long_sleep` session per Oura day drives nightly trends; naps and additional sessions remain listed in the night view. Thirty-second sleep phases are preferred; five-minute phases are used when needed. Stages `1/2/3/4` mean deep/light/REM/awake per the official API schema. Stage-derived awake-during-sleep excludes wake before the first sleep and after the last sleep. Awakening counts use continuous awake runs of at least five minutes. Disrupted stretches combine awake episodes separated by no more than five minutes of detected sleep, while retaining the actual awake total. Incomplete or mismatched stage series produce unknown awakening metrics. Bedtime plus latency is the fallback for onset, not a fallback for awakenings. Times preserve the recorded UTC offset; nights crossing an offset change are explicitly flagged. These are wearable estimates and descriptive associations, not diagnoses.

Caffeine reports are aligned to the evening preceding the sleep (including after-midnight bedtimes). The selected-night view shows the exact last-intake time, no caffeine, or not logged. Existing after-4-p.m. checkbox answers remain available without inventing a time. Sleep comparisons retain their past-4-p.m. threshold, derived from precise times when available; exactly 4 p.m. is not after 4 p.m. Missing logs are unknown, not no caffeine. Caffeine comparisons require at least five staged nights in each group. Historical morning sleep reports remain available alongside Oura estimates; the daily morning sleep questions have been retired. Journal content is read locally and never sent to Oura. An individual night can disagree with self-report, particularly during quiet wakefulness.

## BJJ library

The BJJ tab adds local course cards, range-streaming playback, chapter jumps, synchronized transcripts, chapter-level related-idea search, exact FTS5 search, timestamped study notes, and a daily training journal. Search can target instructionals, the BJJ training journal, or all BJJ material including timestamped study notes. Personal journals are excluded from ingestion and search. Related ideas is the default: local BGE plus exact terms produce a 15-result shortlist, then TypeSafe Jev scores each query/candidate pair when `TYPESAFE_API_KEY` is available. The interface shows the top five results first and keeps the remaining ten behind an accessible expand control. Exact terms remains available separately. Transcript results show the chapter summary, instructor, volume, official chapter title, and complete chapter start/end timestamp range.

**Past sessions** below the training form lists saved BJJ journal dates, ratings, and note previews. Search matches the complete training note, the rating filter narrows the list, and selecting a date opens a read-only view of its sections. **Edit this session** loads that date into the form; an unsaved draft must be confirmed before switching. Older pages load in groups of 20. This archive reads only `BJJ/Journal` in the configured vault and does not add personal journals to the search index.

On the local BJJ page, open **TypeSafe setup on this computer** to save a TypeSafe key using Windows user-bound encryption. The encrypted credential file is stored under the signed-in user's local app data, outside the repository and BJJ library; the saved key is never returned to the browser. Server-side `TYPESAFE_API_KEY` remains supported and takes precedence. Search sends the query and each of the top 15 candidate contents to TypeSafe when Jev is configured. If Jev is unavailable, search falls back to the local hybrid order; exact FTS5 works without it.

Run `python setup_embeddings.py` after configuring the vault and BJJ library to install/cache `BAAI/bge-small-en-v1.5` under `data/` and rebuild SQLite with one 384-dimensional embedding per chapter. Because BGE-small cannot ingest a long chapter at once, bounded windows spanning the complete transcript plus the title and summary are embedded, mean-pooled, and normalized into that single chapter vector; no transcript tail is silently truncated. The complete transcript remains in the local index for FTS5 and Jev. If the checkout has no `config.local.json`, pass `--bjj-library "C:\path\to\your\BJJLibrary" --vault "C:\path\to\your\ObsidianVault"`. Training-journal and study-note files remain smaller local chunks and refresh after each save.

### How the instructional chapters were summarized

The existing chapter summaries were generated in a one-time batch through a ChatGPT-signed-in Codex CLI, without an API key. To repeat that process after adding or changing transcripts, sign in to Codex CLI with your ChatGPT account and run:

```powershell
python summarize_with_codex.py --bjj-library "C:\path\to\your\BJJLibrary" --vault "C:\path\to\your\ObsidianVault" --rebuild
```

This uses Codex plan usage rather than API credits. It sends each instructional chapter transcript to Codex in batches of six, saves each completed batch by transcript hash under the private library's `work/` folder, and resumes incomplete runs without redoing valid summaries. The script strips API keys from its Codex subprocess environment, uses an ephemeral read-only session, and never places transcripts or summaries in Git. Add `--dry-run` to see how many chapters need summaries, or use `--limit 2 --batch-size 2` for a small pilot.

Private media, transcripts, summary caches, indexes, local configuration, and encrypted credentials are ignored by Git. This checkout also uses a pre-push secret gate; enable it in a fresh clone with `git config --local core.hooksPath .githooks`. Run `python scripts/check_repo_secrets.py --working-tree` before committing to scan tracked and unignored new files without printing any matching secret values. The hook checks every outgoing commit and blocks recognizable credentials or private-data paths; do not bypass it when pushing.

`jev-1.13.0` documents a 32k-token limit for state plus the longest question. The current 119-chapter library was checked before this design was enabled: its longest chapter is 1,794 words / 8,514 UTF-8 bytes, and the largest deliberately padded reranking request was 13,289 bytes. Runtime also rejects any request at 30,000 UTF-8 bytes, before it can reach TypeSafe.

While a video is playing, hold the right side on a phone or hold `F` on desktop to temporarily speed playback; desktop mouse clicks are left to the native video player. The player's ellipsis menu configures the temporary speed for both controls. Study notes are Markdown under `BJJ/Study Notes` in the configured vault, with `bjj://` links that reopen the same video moment. Training entries are Markdown under `BJJ/Journal` and contain General Notes, Session Goals, Problems encountered, What worked, and an optional 1-5 session rating.

Set both vault and library paths in the ignored `config.local.json`:

```json
{
  "vault": "C:\\path\\to\\your\\ObsidianVault",
  "bjj_library": "C:\\path\\to\\your\\BJJLibrary"
}
```

The library's `manifest.json` is the source of truth. It points to the ignored local media, transcript, and index files. Use `BJJ_IMPLEMENTATION_PLAN.md` for the private acquisition, verification, transcription, and rebuild procedure.

Run `python eval_bjj_search.py` to compare the retained 192-dimensional feature-hash baseline, BGE, and hybrid ranking on the checked-in paraphrase/transcription-noise evaluation set. The fixture contains synthetic text only; it never reads or prints private journal content.

## Verify

```powershell
python -m unittest discover -s tests -v
node --check static/app.js
node --check static/bjj.js
node --check static/plans.js
node --check static/restaurants.js
node --check static/voice.js
node --check static/sleep.js
node tests/test_sleep_charts.cjs
node tests/test_caffeine.cjs
node tests/test_oura_summary.cjs
```

This server is for personal use on localhost. It checks Host/Origin, rejects cross-origin writes, serves an explicit asset list, and binds exclusively to loopback. OAuth uses a short-lived one-use state and browser cookie. Journal and SQLite data remain ordinary local files; Oura and BJJ AI credential files are encrypted. DPAPI tests must run as the normal Windows user; a restricted sandbox may not have access to that user's encryption services.



## Morning plans and evening progress
The Priority Tasks morning section starts with four single-line entries, saved as Markdown bullets. Existing answers with up to four nonempty lines open in these fields; longer/custom answers remain in the Markdown editor without truncation. Save the morning entry before reviewing it in the evening. The evening check-in saves standard Markdown task checkboxes and preserves earlier checklist items if morning plans later change. Sleep-interruption questions are no longer shown each morning; earlier saved sleep metadata is preserved when editing old notes, and new notes do not collect it.

Evening includes a **Last caffeine intake** time picker near the top, with quick choices for 3, 4, 5, 6 and 7 p.m., plus **No caffeine** and **Not logged**. Any minute can also be entered. Its `caffeine_last_intake` field is stored in the local evening-habits metadata as `HH:MM`, `none`, or `null` for explicitly not logged. Older `caffeine_after_4pm` answers remain untouched unless the caffeine control is changed; changing it replaces that answer with the new field. Unlogged new entries never fabricate a negative caffeine answer. The time survives saving, browser drafts and switching editor modes.

Evening also includes optional 1–10 day-satisfaction and productivity ratings, and checkboxes for phone/game time before morning and afternoon work. Historical 1–5 ratings are normalized with `1→1`, `2→3`, `3→6`, `4→8`, and `5→10`; explicit scale markers make migration idempotent and let old browser drafts normalize safely. Day satisfaction replaces the older Good day name and asks how satisfying the day felt overall. Every value on both scales has a description. The checkboxes are stored as local metadata in that day's Markdown. Your progress shows 30 days of ratings and a journaling streak. Unrated days remain missing, not zero. The streak counts consecutive days with saved writing, checked tasks, or a rating, starting today or yesterday if today is still unwritten. Browser drafts do not count. Checkmarks and ratings participate in draft recovery and file conflict checks.


Morning also offers Secondary Tasks for lower-priority items to tackle after the priorities, if time and energy allow. Both lists become evening checkboxes. Carry forward reviews unfinished items from the latest earlier saved plan (including across gaps); without an evening checklist, completion is labeled unknown. Choose either list or Skip today. Nothing is added automatically. Choices are saved with the morning entry and recovered with drafts. This is a review of the most recent plan, not a permanent backlog of every skipped task.


### Optional plans and completion history

Secondary Tasks starts with one field; **+ Add item** adds more without a four-item limit. Priority Tasks retains its four-item starting layout. Saved nonempty fields reappear on reload. Both lists remain in the evening checklist.

Carry-forward review includes **Already done**. Tick it and save the morning entry to record completion on that journal date. Once added to today's plans, complete the item in the evening checklist. Carrying an unfinished item does not change the previous night's unchecked box.

**Completed tasks** shows creation and completion dates and is archived at `Tasks/Completed tasks.md` in the configured vault. Explicit carry decisions preserve the original date across days and categories; independently typed tasks are new tasks. For existing entries the creation date is the original journal date, not the file's modification timestamp. The archive is an audit history: previously saved completions remain if a checkbox is subsequently cleared or a note removed. Keep the app-managed metadata comment intact. Journal notes remain the editable source; archive updates run on save and when the task history loads. A failed archive update is reported without undoing a successful journal save.

### Day classification
Each journal note stores `journal_calendar` in its YAML frontmatter: `is_weekend`, `is_work_holiday`, actual and observed holiday names, and the calendar used. The entry API exposes the same information under `calendar`, including for dates without a saved note. Weekend means Saturday/Sunday. Work holidays use recurring US federal holidays and standard Friday/Monday observance per https://www.opm.gov/policy-data-oversight/pay-leave/federal-holidays/. This is a calendar indicator, not your employer's actual time-off schedule; state/company holidays and one-off executive holidays are excluded. Rules target modern journal dates; Juneteenth begins in 2021. Calendar metadata refreshes whenever a note is saved.

### Restaurants

Restaurants is available from the top navigation. Add a restaurant, select its visit date (defaults to the local current date), and expand it to add dishes. Restaurant and dish reviews each include an optional 1–5 score and a single Thoughts field. Legacy review text is merged into Thoughts when opened, then persisted on Save restaurants. **Add Ashley** reveals an independent set of fields for her. Ratings may remain unrated.

Use **Save restaurants** to persist the collection in `Restaurants/restaurants.json` inside the configured vault. Browser drafts are separate from journal drafts and recover after refresh. Atomic writes and revision checks prevent a stale tab from silently overwriting newer saved reviews. This first version has one visit date per restaurant entry; multiple visits can be entered as separate entries. No restaurant data is sent to a third party.

### People

People is available from the top navigation. Add a name and relation, select a person, and save individual dated notes. Dates default to today and can be backdated; the timeline shows newest dates first and supports multiple notes on the same date. Search matches names, relations, and note text. Saved data is local at `People/people.json` in the vault. Each form keeps an unfinished browser draft. Server-side append operations preserve other people's and earlier notes, and stable request IDs prevent duplicate entries if a save is retried. The first version supports adding people and notes, not editing or deleting saved records.

### Evening task edits and follow-ups

Each evening checklist item has **Edit task / add follow-up**. The evening description can describe the portion actually completed; the morning plan remains unchanged and is shown for reference. Tick the revised task when done, enter the remaining work, and click **Add follow-up**, then **Save evening entry**. A follow-up is its own unchecked task in the same category and can itself be edited. Inline Markdown metadata preserves original text and the parent relationship. The next carry-forward review uses edited evening descriptions and includes unfinished follow-ups. Carry-forward still reviews the latest previous entry with plans; a persistent backlog remains a separate proposed feature.

## Recovering the background server on Windows

Run `powershell -ExecutionPolicy Bypass -File .\install-background-task.ps1` once as your normal Windows user. Windows Task Scheduler starts the local server at login and checks every minute to relaunch it if it exits. Only one scheduled instance runs at a time, with no execution time limit or battery shutdown. The desktop launcher still works. The existing login shortcut is harmless: the launcher reuses an already running server.

The server stays local to this PC. It cannot serve requests while the PC is asleep, powered off, or signed out. GitHub stores source code; it does not host the running app. To stop background recovery, disable the **Personal Journal** task in Windows Task Scheduler. Logs are in `data/startup.log` and are never committed.

Evening tasks can be reordered using the dotted drag handle or the up/down arrows beside each task. Save the evening entry to keep the order; drafts also retain it. Moving a task preserves its category, completion checkbox, description, and follow-up relationship. New morning tasks are appended without resetting the saved evening order.

Each evening task has a **Submit** button. Check the task and submit to save the current evening entry and animate the task off the board. Submitted tasks remain checked in the daily Markdown and in Completed tasks; a metadata flag keeps them hidden on reload. Save errors leave the task visible. Reduced-motion preferences skip the animation.

Evening **Do later** offers tomorrow, one week, a custom day count, or a calendar date. Save cooldown saves the evening entry. The task stays visible with its return date, and appears in morning carry-forward when due, even across gaps in journaling. Clear cooldown cancels it. Completion now uses a pop, confetti burst, and smooth collapse; reduced-motion settings skip the effects.

After saving an evening cooldown, **Submit** puts the unchecked task away from that evening board. It remains unfinished and returns to morning carry-forward on its scheduled date; submitting a cooldown does not add a completion record.

## Private access from other devices
The app can stay bound to localhost behind Tailscale Serve. Install Tailscale on each device and sign in to the same personal account. Use `tailscale serve --bg http://127.0.0.1:8765` for private HTTPS; do not enable Funnel. In the ignored `config.local.json`, `remote_access` contains `origin` (the exact HTTPS ts.net address, no trailing slash) and `login` (the authorized Tailscale account). Restart the journal after configuration. Requests must match the configured account identity supplied by Serve and the exact origin. Keep the backend bound to loopback; never expose it directly or trust identity headers from an untrusted proxy.

On iPhone, install Tailscale, connect, then open the private address in Safari and use Share → Add to Home Screen. Use the navigation to switch between Journal, BJJ, Restaurants, and People. The host PC must remain powered on and awake. The journal's scheduled task currently starts at Windows sign-in, so sign into Windows after a reboot. Tailscale runs unattended; Serve persists in the background. Oura reconnect/setup still uses the host PC's localhost callback, so perform that on the host; synced stats are available remotely. Browser drafts are separate for each device and URL; save before switching devices. To disable private sharing: `tailscale serve --https=443 off`.

## Local voice dictation
Run `python setup_voice.py` once on the hosting PC to install faster-whisper and download the English base model into ignored `data/` folders. No paid API or API key is used. The model loads lazily on the CPU and remains in memory until the app exits. Audio is processed in memory and is never written into journal files or audio logs.

Integrated **Dictate** field actions in journal, task, people, restaurant, and BJJ text areas open a recorder; compact icon-only actions are used for single-line fields. The control shows Listening and Transcribing states in place without covering the writing surface or resize handle. Allow microphone access, speak (up to two minutes), tap Stop, and the transcript automatically appends to the original field. Edit it directly there if needed. Existing field text is preserved; normal Save is still required. Cancel discards the panel. Use the private HTTPS URL on iPhone; localhost also works on the host PC. Only the hosting PC needs the transcription model. Permission denial, unsupported recording formats, busy transcription, and connection errors are displayed in the panel. The model is English-only initially; occasional transcription errors need review. Closing the page discards recordings and any transcript not yet added to a field.

Morning tasks, morning carry-over cards, and evening tasks have an × button in the top right. Confirm deletion, then save the current entry. Deletion is recovered with drafts, prevents carry-forward, and does not mark tasks completed. Previously archived completion history remains intact.
