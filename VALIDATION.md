# Validation

- 37 automated tests passed with the prepared Python 3.12 runtime and optional libraries.
- The suite uses temporary folders, isolated SQLite databases and mocked external services.
- Real file operations, undo, stale-plan detection, exclusive destination creation, PDF generation/merge/split/extraction, CSV/XLSX exports, a temporary Git repository, and the loopback HTTP API were exercised.
- Browser checks passed for dashboard navigation, tool search, password generation, folder rename preview/apply, local CSV upload, cleanup preview and creating a cleaned CSV download.
- Browser console checks reported no errors or warnings at that point.
- A final browser reload after minor label/logo layout adjustments was blocked by declined browser access. That final visual recheck was not completed.
- Live SMTP/IMAP, Telegram/Discord, Ollama, Tesseract engine execution, MQTT and physical smart devices were not exercised with real credentials or hardware. Their service contracts are covered with mocks where applicable; configure and test the services you use.

Run the included suite from this folder:

```sh
python -m unittest discover -s tests -v
```
