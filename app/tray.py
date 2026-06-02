from typing import Callable

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

import autostart
from i18n import tr
from paths import asset_path


class TrayController(QObject):
    def __init__(
        self,
        app: QApplication,
        settings: dict,
        island_window,
        open_settings: Callable[[], None],
    ) -> None:
        super().__init__()
        self.app = app
        self.settings = settings
        self.island_window = island_window
        self.open_settings = open_settings
        self.menu: QMenu | None = None

        self.tray = QSystemTrayIcon(self._load_icon(), self)
        self.tray.setToolTip("OneBar")
        self.rebuild_menu()
        self.tray.show()

    def rebuild_menu(self) -> None:
        language = self.settings.get("language")
        menu = QMenu()

        open_action = menu.addAction(tr(language, "open_settings"))
        open_action.triggered.connect(self.open_settings)

        visibility_key = "hide_onebar" if self.island_window.isVisible() else "show_onebar"
        visibility_action = menu.addAction(tr(language, visibility_key))
        visibility_action.triggered.connect(self._toggle_island_visibility)

        autostart_key = "autostart_on" if autostart.is_enabled() else "autostart_off"
        autostart_action = menu.addAction(tr(language, autostart_key))
        autostart_action.triggered.connect(self._toggle_autostart)

        menu.addSeparator()
        quit_action = menu.addAction(tr(language, "quit"))
        quit_action.triggered.connect(self._quit)

        self.menu = menu
        self.tray.setContextMenu(menu)

    def _toggle_island_visibility(self) -> None:
        if self.island_window.isVisible():
            self.island_window.hide()
        else:
            self.island_window.reposition()
            self.island_window.show()
            self.island_window.raise_()
        self.rebuild_menu()

    def _toggle_autostart(self) -> None:
        language = self.settings.get("language")
        try:
            autostart.set_enabled(not autostart.is_enabled())
        except Exception as exc:
            self.tray.showMessage(
                tr(language, "autostart_error_title"),
                str(exc),
                QSystemTrayIcon.MessageIcon.Warning,
                5000,
            )
        self.rebuild_menu()

    def _quit(self) -> None:
        self.tray.hide()
        self.app.quit()

    def _load_icon(self) -> QIcon:
        icon_path = asset_path("icon.ico")
        if icon_path.exists():
            icon = QIcon(str(icon_path))
            if not icon.isNull():
                return icon
        return self._fallback_icon()

    @staticmethod
    def _fallback_icon() -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QColor("#000000"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(6, 10, 52, 44, 10, 10)

        font = QFont("Segoe UI", 24)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "1")
        painter.end()

        return QIcon(pixmap)
