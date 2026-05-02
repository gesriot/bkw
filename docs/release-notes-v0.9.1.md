# BKW 0.9.1

This release focuses on desktop UI localization and release packaging updates.

## Downloads

- **macOS (Apple Silicon):** `BKW-0.9.1-macos-arm64.dmg`
- **Windows (x64):** `BKW-0.9.1-windows-x64.exe`
- **Linux (x64):** `BKW-0.9.1-linux-x64.tar.gz` (standalone bundle)

## What's New

### English / Russian UI

- Added built-in English and Russian localization for the desktop app.
- English is now the default UI language.
- Russian can be selected from the `Language` menu.
- The selected language is saved with `QSettings` and restored on the next launch.
- Localization is implemented in Python code, so there are no external `.ts` / `.qm` translation files to ship separately.

### Live Language Switching

- Language changes apply immediately without restarting the app.
- Tabs, labels, buttons, placeholders, tooltips, validation messages, dialogs, status text, table headers, and graph labels are re-rendered when the language changes.
- Source-mode combo box values now keep stable internal IDs (`template` / `import`) while displaying localized labels.

## Fixes

- Progress/status messages now store stable translation keys instead of already-rendered text, so in-flight statuses update correctly after switching languages.
- PNG export confirmation now uses localized `Yes` / `No` buttons in Russian mode.

## Notes

- Scientific identifiers and domain notation such as `BKWDATA`, `TDF`, `bkw`, `isp`, `Hugoniot`, `Isentrope`, `wt`, `mol`, and legacy option values are intentionally kept stable where they represent file formats, engine modes, or technical parameters.
