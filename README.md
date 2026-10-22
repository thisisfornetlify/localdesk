# LocalDesk

One Python application, one local browser interface, **32 tools**. Files, trackers, automations, developer utilities, creative tools, document search, local AI, strategy testing, and smart devices share the same SQLite workspace.

Use the light/dark mode button in the top bar to switch the entire interface. The choice is saved in your browser; until you choose, LocalDesk follows your system theme.

## Start

On this Windows computer, double-click **Start.cmd**. It detects an installed Python, a project virtual environment, or the Codex bundled Python runtime. The app opens **http://127.0.0.1:8765**. Leave its terminal running; use Ctrl+C to stop it. For a different port: `Start.cmd --port 8766`.

On any computer with Python 3.11 or newer:

```sh
cd localdesk
python -m pip install -r requirements.txt
python app.py
```

The browser UI, SQLite database, trackers, CSV tools, developer tools, Wordle, game, and other standard-library features run without installing packages. `.packages/` contains optional pure-Python libraries prepared for this copy, with their license and distribution metadata. Image, PDF and Excel features require their corresponding packages; the Codex runtime on this computer already provides Pillow, pypdf, reportlab and openpyxl. **Install-Features.cmd** installs all Python features into `.packages/` on another Windows installation. On macOS/Linux, use `python3` in the commands above or `sh start.sh`.

Optional programs/services: **Git** for repository stats; **Tesseract OCR** plus language data for receipts; **Ollama** plus installed models for semantic search and document chat. Email, bots, and smart devices need your own credentials and endpoints.

## First things to try

1. Open **Table cleaner** and upload `examples/messy.csv`. Set date columns to `date`, preview, then export.
2. Open **Log analyzer** and upload `examples/server.log`.
3. Open **Markdown converter** and upload `examples/document.md`.
4. Open **Knowledge search → Index folder** and paste the full path of `examples/notes`. Choose keyword mode. Search for “workshop hours”.
5. Open **Strategy lab** and upload `examples/sample-prices.csv`. It contains fictional prices, suitable only for trying the interface.
6. Open **Playlist insights** and upload `examples/spotify-history.json`.
7. Add a habit, check in using its ID, or start a focus session. Click an ID in results to copy it.

File tools use **absolute folder paths on the computer running Python**. Browser file uploads are copied into local app storage. Uploads are not automatically deleted. All generated downloads are separate files; converters and cleaners do not change inputs.

## Feature coverage

| Area | Tool | Implementation and boundaries |
| --- | --- | --- |
| Files | Bulk renamer | Pattern fields, sequence, modification or EXIF date, recursive option, preview/apply and undo. EXIF falls back to modification time. Conflicts stop the plan. |
| Files | Duplicate finder | Size grouping and SHA-256 verification; first alphabetical path kept. Cleanup moves other copies to recoverable app trash. |
| Files | Clipboard history | Search, manual snippets, copy and clear. Opt-in polling captures text only; disabled on every app start. 1,000 automatic entries retained. |
| Security | Password lab | Cryptographic random passwords and passphrases. Hash-prefix Pwned Passwords checks with padded responses. No password history. |
| Files | Downloads organizer | Automatically categorizes immediate files into type folders, then previews the moves for review. |
| Files | Markdown converter | HTML with tables/fenced code; script/network-blocking policy in export. PDF mode renders headings and text, rather than full HTML/CSS fidelity. |
| Daily | Expense tracker | SQLite records, per-currency monthly totals and category charts, CSV export, delete. No bank connection. |
| Daily | Focus timer | Persistent start/stop sessions, countdown, completion notification, weekly task totals and CSV reports. Timer runs until explicitly stopped. |
| Daily | Website monitor | Saved text snapshots, optional CSS selector, unified diff, in-app alerts, optional SMTP email and recurring checks. Server HTML only. |
| Daily | Habit tracker | Idempotent dated check-ins, current/longest daily streaks, recent counts and history. |
| Daily | News digest | RSS and Atom, deduplication, CSV, SMTP email and daily schedules. Feed order retained; dates shown as supplied. |
| Daily | PDF toolkit | Merge in specified path order; split selected pages to ZIP; select pages; lossless stream compression; embedded text extraction; encrypted PDF passwords. Already-compressed PDFs may not shrink. |
| Developer | Log analyzer | Levels, normalized error patterns, hourly spikes and common IPs. Generic text logs; format-specific parsing is heuristic. |
| Developer | API workbench | Methods, JSON headers, raw bodies, timing/status, save/load request definitions. Responses capped at 15 MB. Saved requests can contain secrets. |
| Developer | Git insights | Author commits, weekday/date activity, file churn using local Git history. Default lookback: 365 days. |
| Developer | Config checker | Missing/extra/empty/duplicate keys and different values in `.env` files. Values omitted from output. Simple single-line dotenv syntax. |
| Developer | TODO scanner | TODO/FIXME/HACK/XXX in common source files; file/line/text report and CSV. Text matching can include strings and prose. |
| Developer | Project starter | Download ZIPs for a Python CLI, standard-library web server, or CSV data project. No arbitrary shell execution. |
| Data | Scheduled scraper | CSS row selectors and named columns, `@href`/`@src` extraction, robots.txt checks, CSV and SQLite run history, recurring jobs. Does not execute page JavaScript. |
| Data | Table cleaner | CSV/TSV and `.xlsx`, trim, header normalization, missing-cell fill, duplicate removal, specified date parsing, preview and CSV/XLSX exports. Legacy `.xls` is not supported. |
| Data | Personal dashboard | Tasks, weather via Open-Meteo city lookup, `.ics` calendar import, habits and timer. Calendar is an import, not account sync; recurring events show original starts only. |
| Data | Email sorter | IMAP From/Subject substring rules, recent messages, preview and explicit apply. Copies matches to folders and flags originals Deleted. No expunge; review in your mail client. |
| Data | Receipt reader | Tesseract OCR on images, likely total lines and date candidates, text download. Heuristic extraction needs review. Does not directly book expenses. |
| Creative | Bot studio | Telegram messages, polls, quizzes, allowlisted chat commands and timed reminders via local polling. Discord outgoing webhook messages/polls. Discord inbound commands are not implemented. |
| Creative | Lantern Vault | Persistent browser-controlled text dungeon, movement, enemies, potions, three treasures and a win condition. |
| Creative | Wordle companion | Exact gray/yellow/green filtering including repeated letters; bounded entropy-ranked probes. Starter dictionary plus custom five-letter word lists. |
| Creative | ASCII studio | Image brightness to text, adjustable width/ramp, invert, transparent image compositing, text export. |
| Creative | Playlist insights | Spotify legacy/extended listening history JSON or CSV; artist/track frequency, hours, months, skip count, optional audio-feature averages. Uses exports, not live Spotify authorization. |
| Advanced | Knowledge search | Index Markdown, text and text PDFs; local weighted keyword ranking or Ollama embeddings with cosine similarity. Up to 5,000 chunks per index operation. |
| Advanced | Document assistant | Ollama retrieval-augmented answers with source passages and bracketed citations. No hosted AI API. Generated answers can be wrong. |
| Advanced | Strategy lab | Historical `date,close` CSV; long-only moving-average crossover or buy/hold, one-bar delayed execution, fractional shares, fees, slippage, equity curve, drawdown and CSV. No live trading. |
| Advanced | Home hub | Saved HTTP or MQTT device endpoints; explicit commands, per-device token environment variables, event history and schedules. Network acknowledgement does not confirm physical state. |

## Integrations

Copy `.env.example` to `.env`, enter the needed settings, and restart. Settings shows package availability and which integration variables are present. Credentials are never returned by the settings API. `.env` and the database are plain local files: keep them private. Existing OS environment variables take precedence over `.env`. Values support simple `KEY=value`, with optional surrounding quotes; no interpolation or multiline values.

- **SMTP:** host/from/to, optional username/password. Port 587 uses STARTTLS, 465 uses TLS. Run Email digest or select website email alerts explicitly. Schedules can repeat those actions.
- **IMAP:** TLS host, username and app password. Configure From/Subject substring rules. Apply a preview within 15 minutes. Failed or partial apply is recorded in SQLite as `email_history`; inspect source and destination folders before retrying.
- **Telegram:** BotFather token and chat ID. Start a chat with your bot first. Schedule **Poll Telegram commands** every 15 seconds. `/remind 5 Take a break`, `/quiz`, `/poll`, `/help` are supported. Only the configured chat ID can issue commands.
- **Discord:** a channel webhook URL. Messages and polls only; use Telegram for quizzes and inbound bot commands.
- **Ollama:** pull your chat and embedding models, e.g. `ollama pull llama3.2`, `ollama pull embeddinggemma`, then run Ollama. Match `.env` model names. Index in semantic mode before semantic search; keyword search needs no model. Changing an embedding model requires reindexing.
- **Tesseract:** install the executable from an official distribution and set `TESSERACT_CMD` if it is not on PATH. Install the desired language packs. The Python wrapper alone does not include the engine.
- **Home devices:** HTTP endpoint and method, or MQTT topic plus broker credentials. For HTTP authorization, set a token variable in `.env` and enter its name in the device form. Home Assistant works through its normal HTTP service API with its bearer token. Use your device's documented payload format.

Reference contracts: [Pwned Passwords range API](https://haveibeenpwned.com/API/v3#PwnedPasswords), [Ollama embeddings](https://docs.ollama.com/api/embed), [Telegram Bot API](https://core.telegram.org/bots/api), [Open-Meteo API](https://open-meteo.com/en/docs).

## Storage, schedules and file recovery

The default data folder is `data/` next to `app.py`, or `LOCALDESK_DATA` when configured. It contains SQLite, uploads, exports and recoverable trash. Back up the whole folder with the app stopped. Deleting generated uploads/exports is a manual maintenance task; the app never empties recoverable trash automatically.

File previews expire after one hour. Applying rechecks source content and destination conflicts, creates destinations exclusively, copies/verifies contents, preserves file metadata and removes the original. Cross-volume moves can take time and temporarily require extra disk space. A failed batch attempts to undo completed moves. Review recovery records in File history if rollback is incomplete. Close files in other applications before moving them. Keep external programs from changing the same files during a batch.

**File history → Preview undo** reverses applied moves. Copy the journal ID from history, generate an undo preview, then apply it. If the old filename is occupied or the moved file is missing, resolve the conflict before retrying. Undo previews never overwrite an existing file.

Recurring jobs and bot reminders run only while Python is running. You may close the browser. Jobs persist in SQLite; overdue jobs run once rather than replaying missed intervals. One-time schedules use Repeat = Once. Interrupted external jobs are paused after restart and need review before resuming. Failed recurring jobs retry at their normal interval; check notifications and pause unwanted repeats. Local notifications appear in the UI; browser notifications require you to enable them in Settings and leave a browser tab open. No email is sent without SMTP configuration and an explicit email action/alert selection.

The server accepts loopback hosts, rejects foreign origins, and requires a per-process token for mutations. It has **no multi-user authentication** and can access files your Python process can access. Do not expose it through a tunnel or bind it publicly. Local data is not encrypted. CSV/XLSX exports neutralize leading formula characters. External requests retain normal TLS certificate checking.

## Tests

```sh
python -m unittest discover -s tests -v
```

Tests use temporary folders and an isolated SQLite database. They cover all tool families, actual file recovery, stale/colliding plans, money aggregation, streaks, timer reports, PDF operations, CSV/XLSX, real temporary Git history, Wordle repeat letters, knowledge indexing, delayed strategy signals, scheduler persistence, and HTTP origin/token checks. External integrations use mocks; the tests do **not** send real email, messages or device commands. Service credentials, local model execution, Tesseract binary availability and actual smart devices must be checked in your own setup.

## Source layout

`app.py` hosts the loopback HTTP server. `localdesk/core.py` owns storage, file plans, networking and exports. `localdesk/catalog.py` declares the forms and action catalog. `localdesk/engine.py` dispatches tools and runs background workers. Domain implementations live under `localdesk/tools/`; the framework-free browser UI is in `static/`. No Node build step, cloud deployment, or frontend package installation is needed.
