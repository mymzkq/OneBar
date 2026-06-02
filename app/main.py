import sys
import ctypes

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from clipboard_history import ClipboardHistoryManager
from config import load_settings, save_settings
from file_hub import FileHubManager
from favorites import FavoritesManager
from island_window import IslandWindow
from logger import log_info
from paths import asset_path
from settings_window import SettingsWindow
from tray import TrayController


def _set_windows_app_user_model_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RainbowYX.OneBar")
    except Exception:
        pass


def main() -> int:
    _set_windows_app_user_model_id()
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("OneBar")
    app.setQuitOnLastWindowClosed(False)
    icon_path = asset_path("icon.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    log_info("OneBar starting")
    settings = load_settings()
    save_settings(settings)

    clipboard_manager = ClipboardHistoryManager(settings.get("clipboard"))
    clipboard_manager.start()
    file_hub_manager = FileHubManager()
    file_hub_manager.start()
    favorites_manager = FavoritesManager()
    favorites_manager.start()

    island = IslandWindow(
        settings.get("appearance"),
        settings.get("behavior"),
        settings.get("status"),
        settings.get("language", "zh-CN"),
        settings.get("search"),
        settings.get("hotkey"),
        clipboard_manager,
        file_hub_manager,
        favorites_manager,
    )
    island.show()

    tray_controller: TrayController | None = None

    def handle_language_changed() -> None:
        island.apply_language_settings(settings.get("language", "zh-CN"))
        if tray_controller is not None:
            tray_controller.rebuild_menu()

    def handle_appearance_changed() -> None:
        island.apply_appearance(settings.get("appearance", {}))

    def handle_behavior_changed() -> None:
        island.apply_behavior_settings(settings.get("behavior", {}))

    def handle_status_changed() -> None:
        island.apply_status_settings(settings.get("status", {}))

    def handle_search_changed() -> None:
        island.apply_search_settings(settings.get("search", {}))

    def handle_hotkey_changed() -> None:
        island.apply_hotkey_settings(settings.get("hotkey", {}))
        settings["_hotkey_error"] = island.search_hotkey_error
        settings_window._sync_hotkey_controls()

    def handle_clipboard_changed() -> None:
        clipboard_manager.apply_settings(settings.get("clipboard", {}))
        island.apply_clipboard_settings(settings.get("clipboard", {}))
        island.refresh_clipboard_history()

    def handle_clipboard_clear() -> None:
        clipboard_manager.clear()

    settings_window = SettingsWindow(
        settings,
        handle_language_changed,
        handle_appearance_changed,
        handle_behavior_changed,
        handle_status_changed,
        handle_search_changed,
        handle_hotkey_changed,
        handle_clipboard_changed,
        handle_clipboard_clear,
    )
    island.set_open_settings_callback(settings_window.show_settings)

    tray_controller = TrayController(
        app=app,
        settings=settings,
        island_window=island,
        open_settings=settings_window.show_settings,
    )

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
