# OneBar

OneBar is a native Windows desktop utility built with Python and PySide6. It stays attached to the top of the primary screen and provides a compact entry point for search, clipboard history, file staging, favorites, status display, and media preview.

**OneBar 的价值是“Windows 顶部效率入口”，不是又一个聊天框。**

## Features

- Top-attached black island window with native `QPainter` rendering.
- System tray menu, show/hide control, and autostart toggle.
- Local search entry with app, file, folder, setting, and web suggestions.
- Text clipboard history with local persistence and drag-out support.
- File Hub for staging file paths.
- Favorites for common links, files, folders, and apps.
- Optional time, CPU, memory, and network status display.
- Media preview through Windows media controls when supported by the player.
- USB drive prompt when removable drives are detected.
- Global search hotkey support.
- Simplified Chinese, Traditional Chinese, and English.
- Local JSON settings and data storage.

## Requirements

- Windows
- Python 3.10 or newer

## Run

```powershell
python -m pip install -r requirements.txt
python app/main.py
```

Or double-click:

```text
run.bat
```

## Icon

The application icon is generated from project code and does not use third-party brand assets:

```powershell
python tools/generate_icon.py
```

This writes:

```text
assets/icon_256.png
assets/icon.ico
```

## Build EXE

Install PyInstaller if it is not already available, then build `dist/OneBar/OneBar.exe`:

```powershell
.\build.ps1
```

Development mode may appear as `python.exe` in Task Manager. The packaged build appears as `OneBar.exe`.

## Build Installer

Install Inno Setup 6, then run:

```powershell
.\package.ps1
```

The installer supports Simplified Chinese, Traditional Chinese, and English. Chinese installer language files are stored in the project under `installer/languages/`, so packaging does not depend on the local Inno Setup `Languages` directory.

If these files are missing, download them from the Inno Setup source repository and place them in `installer/languages/`:

- `Files/Languages/Unofficial/ChineseSimplified.isl`
- `Files/Languages/Unofficial/ChineseTraditional.isl`

## Privacy

OneBar stores data locally by default.

- It does not upload clipboard content, search text, file paths, or media information.
- Logs should not include clipboard text, search queries, or full file paths.
- Local runtime data is stored under `%APPDATA%\OneBar`.
- Local settings, cache, logs, clipboard history, file hub data, and favorites should not be committed to the repository.

## Known Limitations

- OneBar is currently a preview build and is still evolving quickly.
- Media preview depends on the player supporting Windows media controls; some players may not provide artwork or respond to control buttons.
- File Hub stores file paths only; it does not copy file contents.
- The icon is an early project icon and may be refined later.
- Installer generation requires Inno Setup 6.

## Roadmap

- Improve packaging and installation.
- Refine the application icon and visual assets.
- Continue improving responsive layout and multi-display behavior.
- Improve local search providers and result ranking.
- Add safer import/export options for local data.
- Add documentation for contributors.

## Project Structure

```text
app/
  main.py             Application entry
  island_window.py    Top island window, drawing, animation, and interactions
  settings_window.py  Settings window
  tray.py             System tray menu
  i18n.py             Translation dictionary
  config.py           Local settings load/save
  autostart.py        Windows registry autostart toggle
  system_stats.py     CPU, memory, and network sampling
  media_control.py    Windows media control integration
assets/
  icon.ico            Application icon
  icon_256.png        256px source preview created with tools/generate_icon.py
requirements.txt      Python dependencies
run.bat               Convenience launcher
build.ps1             PyInstaller build script
package.ps1           PyInstaller + Inno Setup package script
tools/
  generate_icon.py    Reproducible icon generation script
installer/
  OneBar.iss          Inno Setup installer definition
```

## Author

RainbowYX

GitHub: https://github.com/mymzkq

## License

MIT License. See [LICENSE](LICENSE).
