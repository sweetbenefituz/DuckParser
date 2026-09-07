# DuckParser

A small desktop log viewer for people who stare at log files for a living.

Point it at a `.log` file and it keeps reading as the file grows, colours every
error red and every warning amber, and gives you a tab per file so you can watch
several at once. Nothing to configure, nothing to install alongside it.

It was written for Unreal and Unity game logs, but it does not care what
produced the file: the level of a line is decided by the words in the line
itself, so any plain-text log from any project works — a game build, a server,
a build script, a crash dump someone pasted into a `.txt`.

![DuckParser](docs/screenshot.png)

## What it does

**Live tailing.** The file stays open. New lines appear as they are written, so
you can leave DuckParser next to a running build or a running game and watch the
log fill up in real time. When a new run recreates the log from scratch,
DuckParser notices and starts following the new file instead of waiting forever
at the end of the old one.

**Load whole file.** Tailing shows what is written from now on, which leaves a
finished log looking empty. The `Load whole file` button next to `Clear tab`
reads the file from its first line, then keeps tailing. On the `All` tab it
reloads every open file at once.

**Errors and warnings, separated.** Three tabs across the top — `All`, `Errors`,
`Warnings`. A line is a warning if it contains "warning", an error if it
contains "error" or "fail", whichever word comes first. Errors and warnings also
stay colour-coded in the `All` tab, so you can spot them while scrolling
everything.

**Several files side by side.** Every opened file gets its own tab, and the
leftmost `All` tab merges all of them into one stream with the file name in
front of each line. Open two builds' logs and compare them without alt-tabbing.
Two files with the same name are fine — the second becomes `LogOutput.log (1)`.

**Right-click a file tab** to open its containing folder, or to close it. Hover
it to see where the file actually lives; how much of the path the tooltip shows
is up to you (`Settings → Tab path`: the full path, or just the last 2–5
folders).

**Search.** `Ctrl+F` opens a search window of its own, centred over the log. It
says how many hits there are and which one you are on (`Found: 3 / 47`),
highlights all of them at once, and takes `Match case` and `Search backwards`.
Enter steps to the next hit and wraps around at the ends; `Esc` closes it.

**Filter by text.** The box in the top right hides every line that does not
contain what you type — across all three tabs at once, and the counters follow
it. Empty it to get everything back.

**Counters on the tabs.** `Errors (17)`, `Warnings (43)`: whether a build is
clean is visible without switching tabs.

**Your own keywords.** A line's level is decided by the words it contains, and
the words are yours: `Settings → Error words` / `Warning words` take a
comma-separated list, so Unreal's `Fatal` and `Assertion`, or Unity's
`Exception`, get coloured like everything else. Changing them re-colours the
lines already on screen.

**Status line.** The bottom of the window shows the full path of the current
file, whether it is still being tailed, and how many lines are on screen.

**Jump back to context.** Right-click any error or warning in a filtered tab and
choose *Open in "All" log* — it switches to the `All` tab and scrolls to that
exact line, so you can read what happened around it.

**Clearing without losing anything.** `Clear tab` empties the current view but
keeps errors and warnings alive in their own tabs. `File → Clear all tabs`
wipes everything.

**Auto-scroll that gets out of the way.** The view follows the newest line until
you scroll up, then it stops and stays where you put it. A button in the corner
takes you back to the bottom.

**Drag and drop.** Drop a log from Explorer anywhere on the window to open it.
`File → Recent files` keeps the last ten, newest first.

**A ceiling on memory.** A multi-gigabyte log would otherwise fill the RAM until
the program dies, so only the newest lines are kept — 200 000 per file by
default, changeable in `Settings → Line limit`, up to no limit at all.

**Themes and languages.** Dark and light themes; English, Russian and Ukrainian
interface. `Always on top` pins the window over the game or editor.

**It remembers.** Language, theme, the folder you last opened a log from, the
recent files list, and the files you had open are all restored on the next
launch.

## Getting it

Grab the `.exe` from [Releases](../../releases) and run it. No installer, no
dependencies, no admin rights. Settings live in
`%APPDATA%\DuckParser\settings.json`, so the program never writes anything next
to itself — putting the `.exe` on your desktop leaves your desktop alone.

## Running from source

Requires Python 3.10+ and PySide6.

```
pip install PySide6
python app.py
```

Building the `.exe` yourself:

```
pip install pyinstaller
pyinstaller DuckParser.spec
```

The result lands in `dist/`.

## Tests

```
pip install pytest
pytest
```

The suite is deliberately small and checks the things that broke before:
level detection, the theme files, the settings location, that every file the
build bundles actually exists, that loading a whole file finds the lines already
in it, and that tailing survives a new run recreating the log.

## Layout

| Path | What lives there |
| --- | --- |
| `app.py` | Window, icon, entry point |
| `ui/` | Main window, tab bars, the log view widget |
| `parser/` | Level detection and the background file-tailing thread |
| `models/` | In-memory storage of parsed lines |
| `settings/` | Reading and writing `settings.json` |
| `localization/` | `en` / `ru` / `ua` strings |
| `themes/` | One stylesheet, two palettes |

## License

[PolyForm Noncommercial 1.0.0](LICENSE).

Free for anything that isn't commercial: personal use, hobby projects, study,
research, schools, charities and government. Fork it, change it, share it.

Selling it, or using it as part of something you sell, is not permitted.
