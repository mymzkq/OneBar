from pathlib import Path
from typing import Callable
import webbrowser

from PySide6.QtCore import QEvent, QSignalBlocker, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config import (
    APPEARANCE_LIMITS,
    APPEARANCE_STEPS,
    CONFIG_DIR,
    CONFIG_FILE,
    DATA_DIR,
    DEFAULT_APPEARANCE,
    DEFAULT_CLIPBOARD,
    DEFAULT_HOTKEY,
    DEFAULT_SEARCH,
    DEFAULT_STATUS,
    SEARCH_ENGINE_KEYS,
    save_settings,
)
from i18n import SUPPORTED_LANGUAGES, tr
from paths import asset_path


GITHUB_PROFILE_URL = "https://github.com/mymzkq"


class LinkRow(QFrame):
    def __init__(self, on_click: Callable[[], None]) -> None:
        super().__init__()
        self.on_click = on_click
        self.setObjectName("linkRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        self.icon_label = QLabel()
        self.icon_label.setObjectName("linkIcon")
        self.icon_label.setFixedSize(22, 22)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setText("GH")

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)
        self.title_label = QLabel()
        self.title_label.setObjectName("linkTitle")
        self.title_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.url_label = QLabel("github.com/mymzkq")
        self.url_label.setObjectName("linkUrl")
        self.url_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.url_label)

        layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text_layout, 1)

    def set_title(self, text: str) -> None:
        self.title_label.setText(text)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_click()
            event.accept()
            return
        super().mousePressEvent(event)


class Stepper(QWidget):
    def __init__(
        self,
        key: str,
        minimum: int,
        maximum: int,
        step: int,
        on_change: Callable[[str, int], None],
    ) -> None:
        super().__init__()
        self.key = key
        self.minimum = minimum
        self.maximum = maximum
        self.step = step
        self.on_change = on_change
        self.value = minimum
        self.language = "zh-CN"

        self.minus_button = QPushButton("-")
        self.value_label = QLabel()
        self.plus_button = QPushButton("+")

        self.minus_button.setObjectName("stepButton")
        self.plus_button.setObjectName("stepButton")
        self.value_label.setObjectName("stepValue")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self.minus_button.setFixedSize(34, 30)
        self.plus_button.setFixedSize(34, 30)
        self.value_label.setFixedSize(92, 30)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.minus_button)
        layout.addWidget(self.value_label)
        layout.addWidget(self.plus_button)

        self.minus_button.clicked.connect(lambda: self._step(-self.step))
        self.plus_button.clicked.connect(lambda: self._step(self.step))
        self._refresh()

    def set_language(self, language: str) -> None:
        self.language = language
        self._refresh()

    def set_value(self, value: int) -> None:
        self.value = max(self.minimum, min(self.maximum, int(value)))
        self._refresh()

    def _step(self, delta: int) -> None:
        next_value = max(self.minimum, min(self.maximum, self.value + delta))
        if next_value == self.value:
            return
        self.value = next_value
        self._refresh()
        self.on_change(self.key, self.value)

    def _refresh(self) -> None:
        self.value_label.setText(f"{self.value} {tr(self.language, 'px')}")
        self.minus_button.setEnabled(self.value > self.minimum)
        self.plus_button.setEnabled(self.value < self.maximum)


class SettingsWindow(QWidget):
    def __init__(
        self,
        settings: dict,
        on_language_changed: Callable[[], None],
        on_appearance_changed: Callable[[], None],
        on_behavior_changed: Callable[[], None],
        on_status_changed: Callable[[], None],
        on_search_changed: Callable[[], None],
        on_hotkey_changed: Callable[[], None],
        on_clipboard_changed: Callable[[], None],
        on_clipboard_clear: Callable[[], None],
    ) -> None:
        super().__init__()
        self.settings = settings
        self.on_language_changed = on_language_changed
        self.on_appearance_changed = on_appearance_changed
        self.on_behavior_changed = on_behavior_changed
        self.on_status_changed = on_status_changed
        self.on_search_changed = on_search_changed
        self.on_hotkey_changed = on_hotkey_changed
        self.on_clipboard_changed = on_clipboard_changed
        self.on_clipboard_clear = on_clipboard_clear
        self.current_page = 0

        self.setObjectName("settingsWindow")
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowTitle(tr(self.settings.get("language"), "settings"))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setMinimumSize(680, 460)
        self.resize(760, 520)
        self.setStyleSheet(self._style())
        self.asset_icon_path = asset_path("icon.ico")
        self.asset_icon_preview_path = asset_path("icon_256.png")
        if self.asset_icon_path.exists():
            self.setWindowIcon(QIcon(str(self.asset_icon_path)))

        self.nav_buttons: list[QPushButton] = []
        self.pages = QStackedWidget()

        self.width_label = self._label()
        self.height_label = self._label()
        self.radius_label = self._label()
        self.shadow_label = self._label()
        self.animation_label = self._label()
        self.brand_text_label = self._label()
        self.brand_text_hint_label = self._label("muted")
        self.brand_text_error_label = self._label("muted")
        self.brand_text_edit = QLineEdit()
        self.brand_text_edit.setObjectName("textInput")
        self.brand_text_edit.setMaxLength(12)
        self.brand_text_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.brand_text_edit.textEdited.connect(self._handle_brand_text_edited)
        self.brand_text_default_button = QPushButton()
        self.brand_text_default_button.setObjectName("secondaryButton")
        self.brand_text_default_button.clicked.connect(self._restore_brand_text_default)
        self.appearance_title = self._label("title")
        self.appearance_description = self._label("muted")
        self.shape_note_label = self._label("muted")

        self.behavior_title = self._label("title")
        self.behavior_description = self._label("muted")
        self.auto_hide_label = self._label()
        self.auto_hide_help_label = self._label("muted")
        self.auto_hide_button = QPushButton()
        self.auto_hide_button.setObjectName("toggleButton")
        self.auto_hide_button.setCheckable(True)
        self.auto_hide_button.clicked.connect(
            lambda: self._update_behavior("auto_hide_enabled", self.auto_hide_button.isChecked())
        )
        self.collapse_on_outside_click_label = self._label()
        self.collapse_on_outside_click_help_label = self._label("muted")
        self.collapse_on_outside_click_button = QPushButton()
        self.collapse_on_outside_click_button.setObjectName("toggleButton")
        self.collapse_on_outside_click_button.setCheckable(True)
        self.collapse_on_outside_click_button.clicked.connect(
            lambda: self._update_behavior(
                "collapse_on_outside_click",
                self.collapse_on_outside_click_button.isChecked(),
            )
        )
        self.music_preview_label = self._label()
        self.music_preview_help_label = self._label("muted")
        self.music_preview_button = QPushButton()
        self.music_preview_button.setObjectName("toggleButton")
        self.music_preview_button.setCheckable(True)
        self.music_preview_button.clicked.connect(
            lambda: self._update_behavior("music_preview_enabled", self.music_preview_button.isChecked())
        )
        self.usb_drive_prompt_label = self._label()
        self.usb_drive_prompt_help_label = self._label("muted")
        self.usb_drive_prompt_button = QPushButton()
        self.usb_drive_prompt_button.setObjectName("toggleButton")
        self.usb_drive_prompt_button.setCheckable(True)
        self.usb_drive_prompt_button.clicked.connect(
            lambda: self._update_behavior("usb_drive_prompt_enabled", self.usb_drive_prompt_button.isChecked())
        )

        self.status_title = self._label("title")
        self.status_description = self._label("muted")
        self.show_time_label = self._label()
        self.show_cpu_label = self._label()
        self.show_memory_label = self._label()
        self.show_network_label = self._label()
        self.show_time_button = self._toggle_button()
        self.show_cpu_button = self._toggle_button()
        self.show_memory_button = self._toggle_button()
        self.show_network_button = self._toggle_button()
        self.show_time_button.clicked.connect(
            lambda: self._update_status("show_time", self.show_time_button.isChecked())
        )
        self.show_cpu_button.clicked.connect(
            lambda: self._update_status("show_cpu", self.show_cpu_button.isChecked())
        )
        self.show_memory_button.clicked.connect(
            lambda: self._update_status("show_memory", self.show_memory_button.isChecked())
        )
        self.show_network_button.clicked.connect(
            lambda: self._update_status("show_network", self.show_network_button.isChecked())
        )

        self.search_title = self._label("title")
        self.search_description = self._label("muted")
        self.search_engine_label = self._label()
        self.search_usage_label = self._label("muted")
        self.search_hotkey_label = self._label()
        self.search_hotkey_current_label = self._label("muted")
        self.search_hotkey_button = self._toggle_button()
        self.search_hotkey_record_button = QPushButton()
        self.search_hotkey_record_button.setObjectName("secondaryButton")
        self.hotkey_recording = False
        self.search_hotkey_status_label = self._label("muted")
        self.search_hotkey_help_label = self._label("muted")
        self.search_engine_combo = QComboBox()
        self.search_engine_combo.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.search_engine_combo.currentIndexChanged.connect(self._handle_search_engine_change)
        self.search_hotkey_button.clicked.connect(
            lambda: self._update_hotkey("search_hotkey_enabled", self.search_hotkey_button.isChecked())
        )
        self.search_hotkey_record_button.clicked.connect(self._begin_hotkey_recording)
        self.search_hotkey_record_button.installEventFilter(self)

        self.clipboard_title = self._label("title")
        self.clipboard_description = self._label("muted")
        self.clipboard_history_label = self._label()
        self.clipboard_persist_label = self._label()
        self.clipboard_url_prompt_label = self._label()
        self.clipboard_usage_label = self._label("muted")
        self.clipboard_history_button = self._toggle_button()
        self.clipboard_persist_button = self._toggle_button()
        self.clipboard_url_prompt_button = self._toggle_button()
        self.clipboard_clear_button = QPushButton()
        self.clipboard_clear_button.setObjectName("secondaryButton")
        self.clipboard_history_button.clicked.connect(
            lambda: self._update_clipboard("history_enabled", self.clipboard_history_button.isChecked())
        )
        self.clipboard_persist_button.clicked.connect(
            lambda: self._update_clipboard("persist_enabled", self.clipboard_persist_button.isChecked())
        )
        self.clipboard_url_prompt_button.clicked.connect(
            lambda: self._update_clipboard("url_open_prompt_enabled", self.clipboard_url_prompt_button.isChecked())
        )
        self.clipboard_clear_button.clicked.connect(self._clear_clipboard_history)

        self.width_stepper = self._stepper("body_width")
        self.height_stepper = self._stepper("body_height")
        self.radius_stepper = self._stepper("radius")

        self.shadow_button = QPushButton()
        self.shadow_button.setObjectName("toggleButton")
        self.shadow_button.setCheckable(True)
        self.animation_button = QPushButton()
        self.animation_button.setObjectName("toggleButton")
        self.animation_button.setCheckable(True)
        self.reset_button = QPushButton()
        self.reset_button.setObjectName("secondaryButton")

        self.shadow_button.clicked.connect(
            lambda: self._update_appearance("shadow_enabled", self.shadow_button.isChecked())
        )
        self.animation_button.clicked.connect(
            lambda: self._update_appearance("animation_enabled", self.animation_button.isChecked())
        )
        self.reset_button.clicked.connect(self._reset_appearance_defaults)

        self.language_title = self._label("title")
        self.language_hint_label = self._label("muted")
        self.language_label = self._label()
        self.language_combo = QComboBox()
        self.language_combo.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.language_combo.currentIndexChanged.connect(self._handle_language_change)

        self.placeholder_about = self._label("muted")
        self.about_icon_label = QLabel()
        self.about_icon_label.setObjectName("aboutIcon")
        self.about_icon_label.setFixedSize(72, 72)
        self.about_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._refresh_about_icon()
        self.about_app_name_label = self._label("title")
        self.about_positioning_label = self._label("hero")
        self.about_author_label = self._label("normal")
        self.about_github_row = LinkRow(self._open_github_profile)
        self.about_status_label = self._label("muted")
        self.about_tech_title_label = self._label("section")
        self.about_tech_label = self._label("muted")
        self.about_privacy_title_label = self._label("section")
        self.version_label = self._label("muted")
        self.config_path_label = self._label("muted")
        self.data_path_label = self._label("muted")
        self.privacy_label = self._label("muted")
        self.license_label = self._label("muted")
        self.file_hub_usage_label = self._label("muted")
        self.favorites_usage_label = self._label("muted")

        self.close_button = QPushButton()
        self.close_button.setObjectName("primaryButton")
        self.close_button.clicked.connect(self.close)

        self._build_layout()
        self.retranslate()
        self._sync_appearance_controls()

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        event.accept()

    def show_settings(self) -> None:
        self.retranslate()
        self._sync_appearance_controls()
        self.show()
        self.raise_()
        self.activateWindow()

    def retranslate(self) -> None:
        language = self.settings.get("language")
        self.setWindowTitle(tr(language, "settings"))

        nav_labels = [
            "appearance",
            "behavior",
            "status",
            "search_settings",
            "clipboard_settings",
            "language",
            "about",
        ]
        for button, key in zip(self.nav_buttons, nav_labels):
            button.setText(tr(language, key))

        self.appearance_title.setText(tr(language, "appearance"))
        self.appearance_description.setText(tr(language, "appearance_description"))
        self.width_label.setText(tr(language, "body_width"))
        self.height_label.setText(tr(language, "body_height"))
        self.radius_label.setText(tr(language, "radius"))
        self.shadow_label.setText(tr(language, "shadow_enabled"))
        self.animation_label.setText(tr(language, "animation_enabled"))
        self.brand_text_label.setText(tr(language, "brand_text_label"))
        self.brand_text_hint_label.setText(tr(language, "brand_text_description"))
        self.brand_text_error_label.setText(tr(language, "brand_text_error"))
        self.brand_text_default_button.setText(tr(language, "brand_text_restore_default"))
        self.reset_button.setText(tr(language, "reset_appearance_defaults"))
        self.shape_note_label.setText(tr(language, "shape_note"))

        self.behavior_title.setText(tr(language, "behavior"))
        self.behavior_description.setText(tr(language, "behavior_description"))
        self.auto_hide_label.setText(tr(language, "auto_hide_enabled"))
        self.auto_hide_help_label.setText(tr(language, "auto_hide_description"))
        self.collapse_on_outside_click_label.setText(tr(language, "collapse_on_outside_click"))
        self.collapse_on_outside_click_help_label.setText(tr(language, "collapse_on_outside_click_description"))
        self.music_preview_label.setText(tr(language, "music_preview_enabled"))
        self.music_preview_help_label.setText(tr(language, "music_preview_description"))
        self.usb_drive_prompt_label.setText(tr(language, "usb_drive_prompt_enabled"))
        self.usb_drive_prompt_help_label.setText(tr(language, "usb_drive_prompt_description"))

        self.status_title.setText(tr(language, "status"))
        self.status_description.setText(tr(language, "status_description"))
        self.show_time_label.setText(tr(language, "show_time"))
        self.show_cpu_label.setText(tr(language, "show_cpu"))
        self.show_memory_label.setText(tr(language, "show_memory"))
        self.show_network_label.setText(tr(language, "show_network"))

        self.search_title.setText(tr(language, "search_settings"))
        self.search_description.setText(tr(language, "search_settings_description"))
        self.search_engine_label.setText(tr(language, "default_search_engine"))
        self.search_usage_label.setText(tr(language, "search_usage_hint"))
        self.search_hotkey_label.setText(tr(language, "search_hotkey_enabled"))
        self.search_hotkey_status_label.setText(tr(language, "search_hotkey_register_failed"))
        self.search_hotkey_help_label.setText(tr(language, "search_hotkey_supported_keys"))

        self.clipboard_title.setText(tr(language, "clipboard_settings"))
        self.clipboard_description.setText(tr(language, "clipboard_settings_description"))
        self.clipboard_history_label.setText(tr(language, "clipboard_history_enabled"))
        self.clipboard_persist_label.setText(tr(language, "clipboard_persist_enabled"))
        self.clipboard_url_prompt_label.setText(tr(language, "clipboard_url_prompt_enabled"))
        self.clipboard_usage_label.setText(tr(language, "clipboard_usage_hint"))
        self.clipboard_clear_button.setText(tr(language, "clipboard_clear_history"))

        self.language_title.setText(tr(language, "language"))
        self.language_label.setText(tr(language, "language"))
        self.language_hint_label.setText(tr(language, "placeholder_language"))
        self.placeholder_about.setText(tr(language, "placeholder_about"))
        self.about_app_name_label.setText("OneBar")
        self.about_positioning_label.setText(tr(language, "about_positioning"))
        self.about_author_label.setText(f'{tr(language, "author_label")}: RainbowYX')
        self.about_github_row.set_title(tr(language, "github_profile"))
        self.about_status_label.setText(tr(language, "about_status"))
        self.about_tech_title_label.setText(tr(language, "tech_stack_title"))
        self.about_tech_label.setText(tr(language, "tech_stack_body"))
        self.about_privacy_title_label.setText(tr(language, "privacy_title"))
        self.version_label.setText(f'{tr(language, "current_version")}: {tr(language, "version_value")}')
        self.config_path_label.setText(f'{tr(language, "config_path")}: {CONFIG_FILE}')
        self.data_path_label.setText(f'{tr(language, "data_path")}: {DATA_DIR}')
        self.privacy_label.setText(tr(language, "privacy_note"))
        self.file_hub_usage_label.setText(tr(language, "file_hub_usage_hint"))
        self.favorites_usage_label.setText(tr(language, "favorites_usage_hint"))
        project_license = Path(__file__).resolve().parents[1] / "LICENSE"
        license_text = tr(language, "license_mit") if project_license.exists() else tr(language, "license_missing")
        self.license_label.setText(f'{tr(language, "license_label")}: {license_text}')
        self.close_button.setText(tr(language, "close"))

        for stepper in (self.width_stepper, self.height_stepper, self.radius_stepper):
            stepper.set_language(language)

        self._sync_language_combo()
        self._refresh_toggle_texts()
        self._sync_behavior_controls()
        self._sync_status_controls()
        self._sync_search_controls()
        self._sync_hotkey_controls()
        self._sync_clipboard_controls()
        self._apply_tooltips()
        self._set_page(self.current_page)

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        content_area = QWidget()
        content_layout = QHBoxLayout(content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(160)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 18, 14, 18)
        sidebar_layout.setSpacing(8)

        for index in range(7):
            button = QPushButton()
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, page=index: self._set_page(page))
            self.nav_buttons.append(button)
            sidebar_layout.addWidget(button)
        sidebar_layout.addStretch(1)

        self.pages.addWidget(self._scroll_page(self._appearance_page()))
        self.pages.addWidget(self._scroll_page(self._behavior_page()))
        self.pages.addWidget(self._scroll_page(self._status_page()))
        self.pages.addWidget(self._scroll_page(self._search_page()))
        self.pages.addWidget(self._scroll_page(self._clipboard_page()))
        self.pages.addWidget(self._scroll_page(self._language_page()))
        self.pages.addWidget(self._scroll_page(self._about_page()))

        content_layout.addWidget(sidebar)
        content_layout.addWidget(self.pages, 1)
        root.addWidget(content_area, 1)

        bottom_bar = QFrame()
        bottom_bar.setObjectName("bottomBar")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(24, 12, 24, 12)
        bottom_layout.addStretch(1)
        bottom_layout.addWidget(self.close_button)
        root.addWidget(bottom_bar)

        self._set_page(0)

    def _appearance_page(self) -> QWidget:
        page = self._page()
        layout = page.layout()
        layout.addWidget(self.appearance_title)
        layout.addWidget(self.appearance_description)
        layout.addSpacing(8)
        self.brand_text_row = self._setting_row(self.brand_text_label, self.brand_text_edit)
        self.width_row = self._setting_row(self.width_label, self.width_stepper)
        self.height_row = self._setting_row(self.height_label, self.height_stepper)
        self.radius_row = self._setting_row(self.radius_label, self.radius_stepper)
        self.shadow_row = self._setting_row(self.shadow_label, self.shadow_button)
        self.animation_row = self._setting_row(self.animation_label, self.animation_button)
        layout.addWidget(self._card([
            self.brand_text_row,
            self.width_row,
            self.height_row,
            self.radius_row,
            self.shadow_row,
            self.animation_row,
        ]))
        layout.addWidget(self.brand_text_hint_label)
        layout.addWidget(self.brand_text_error_label)
        layout.addWidget(self.brand_text_default_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addSpacing(4)
        layout.addWidget(self.reset_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        layout.addWidget(self.shape_note_label)
        return page

    def _behavior_page(self) -> QWidget:
        page = self._page()
        layout = page.layout()
        layout.addWidget(self.behavior_title)
        layout.addWidget(self.behavior_description)
        layout.addSpacing(8)
        self.auto_hide_row = self._setting_row(self.auto_hide_label, self.auto_hide_button)
        self.collapse_on_outside_click_row = self._setting_row(
            self.collapse_on_outside_click_label,
            self.collapse_on_outside_click_button,
        )
        self.music_preview_row = self._setting_row(self.music_preview_label, self.music_preview_button)
        self.usb_drive_prompt_row = self._setting_row(self.usb_drive_prompt_label, self.usb_drive_prompt_button)
        layout.addWidget(self._card([
            self.auto_hide_row,
            self.collapse_on_outside_click_row,
            self.music_preview_row,
            self.usb_drive_prompt_row,
        ]))
        layout.addStretch(1)
        return page

    def _status_page(self) -> QWidget:
        page = self._page()
        layout = page.layout()
        layout.addWidget(self.status_title)
        layout.addWidget(self.status_description)
        layout.addSpacing(8)
        self.show_time_row = self._setting_row(self.show_time_label, self.show_time_button)
        self.show_cpu_row = self._setting_row(self.show_cpu_label, self.show_cpu_button)
        self.show_memory_row = self._setting_row(self.show_memory_label, self.show_memory_button)
        self.show_network_row = self._setting_row(self.show_network_label, self.show_network_button)
        layout.addWidget(self._card([
            self.show_time_row,
            self.show_cpu_row,
            self.show_memory_row,
            self.show_network_row,
        ]))
        layout.addStretch(1)
        return page

    def _search_page(self) -> QWidget:
        page = self._page()
        layout = page.layout()
        layout.addWidget(self.search_title)
        layout.addWidget(self.search_description)
        layout.addSpacing(8)
        self.search_engine_row = self._setting_row(self.search_engine_label, self.search_engine_combo)
        self.search_hotkey_row = self._setting_row(self.search_hotkey_label, self.search_hotkey_button)
        self.search_hotkey_record_row = self._setting_row(
            self.search_hotkey_current_label,
            self.search_hotkey_record_button,
        )
        layout.addWidget(self._card([
            self.search_engine_row,
            self.search_hotkey_row,
            self.search_hotkey_record_row,
        ]))
        layout.addWidget(self.search_hotkey_status_label)
        layout.addWidget(self.search_hotkey_help_label)
        layout.addWidget(self.search_usage_label)
        layout.addStretch(1)
        return page

    def _clipboard_page(self) -> QWidget:
        page = self._page()
        layout = page.layout()
        layout.addWidget(self.clipboard_title)
        layout.addWidget(self.clipboard_description)
        layout.addSpacing(8)
        self.clipboard_history_row = self._setting_row(self.clipboard_history_label, self.clipboard_history_button)
        self.clipboard_persist_row = self._setting_row(self.clipboard_persist_label, self.clipboard_persist_button)
        self.clipboard_url_prompt_row = self._setting_row(self.clipboard_url_prompt_label, self.clipboard_url_prompt_button)
        layout.addWidget(self._card([
            self.clipboard_history_row,
            self.clipboard_persist_row,
            self.clipboard_url_prompt_row,
        ]))
        layout.addWidget(self.clipboard_usage_label)
        layout.addSpacing(4)
        layout.addWidget(self.clipboard_clear_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        return page

    def _language_page(self) -> QWidget:
        page = self._page()
        layout = page.layout()
        layout.addWidget(self.language_title)
        layout.addWidget(self.language_hint_label)
        layout.addSpacing(8)
        layout.addWidget(self._card([self._setting_row(self.language_label, self.language_combo)]))
        layout.addStretch(1)
        return page

    def _about_page(self) -> QWidget:
        page = self._page()
        layout = page.layout()
        layout.addWidget(self._page_title("about"))

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(16)
        header_layout.addWidget(self.about_icon_label, 0, Qt.AlignmentFlag.AlignTop)
        header_text = QVBoxLayout()
        header_text.setContentsMargins(0, 0, 0, 0)
        header_text.setSpacing(4)
        header_text.addWidget(self.about_app_name_label)
        header_text.addWidget(self.version_label)
        header_text.addWidget(self.about_author_label)
        header_text.addWidget(self.about_github_row)
        header_layout.addLayout(header_text, 1)
        layout.addWidget(header)

        layout.addWidget(self.about_positioning_label)
        layout.addSpacing(4)
        layout.addWidget(self.placeholder_about)
        layout.addSpacing(8)
        layout.addWidget(self.about_status_label)
        layout.addSpacing(8)
        layout.addWidget(self.about_tech_title_label)
        layout.addWidget(self.about_tech_label)
        layout.addSpacing(8)
        layout.addWidget(self.about_privacy_title_label)
        layout.addWidget(self.privacy_label)
        layout.addSpacing(4)
        layout.addWidget(self.config_path_label)
        layout.addWidget(self.data_path_label)
        layout.addWidget(self.file_hub_usage_label)
        layout.addWidget(self.favorites_usage_label)
        layout.addWidget(self.license_label)
        layout.addStretch(1)
        return page

    def _placeholder_page(self, label: QLabel, title_key: str) -> QWidget:
        page = self._page()
        layout = page.layout()
        layout.addWidget(self._page_title(title_key))
        layout.addWidget(label)
        layout.addStretch(1)
        return page

    def _page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        return page

    def _scroll_page(self, page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(page)
        return scroll

    def _page_title(self, key: str) -> QLabel:
        label = self._label("title")
        label.setText(tr(self.settings.get("language"), key))
        return label

    def _card(self, rows: list[QWidget]) -> QWidget:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        for row in rows:
            layout.addWidget(row)
        return card

    def _setting_row(self, label: QLabel, control: QWidget) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        label.setMinimumWidth(120)
        layout.addWidget(label)
        layout.addStretch(1)
        layout.addWidget(control)
        return row

    def _set_row_tooltip(self, row: QWidget, label: QLabel, control: QWidget, text: str) -> None:
        row.setToolTip(text)
        label.setToolTip(text)
        control.setToolTip(text)

    def _apply_tooltips(self) -> None:
        language = self.settings.get("language")
        self._set_row_tooltip(
            self.brand_text_row,
            self.brand_text_label,
            self.brand_text_edit,
            tr(language, "brand_text_description"),
        )
        self.brand_text_default_button.setToolTip(tr(language, "brand_text_restore_default"))
        self._set_row_tooltip(
            self.shadow_row,
            self.shadow_label,
            self.shadow_button,
            tr(language, "tooltip_shadow"),
        )
        self._set_row_tooltip(
            self.animation_row,
            self.animation_label,
            self.animation_button,
            tr(language, "tooltip_animation"),
        )
        self.reset_button.setToolTip(tr(language, "tooltip_reset_appearance_defaults"))
        self._set_row_tooltip(
            self.auto_hide_row,
            self.auto_hide_label,
            self.auto_hide_button,
            tr(language, "tooltip_auto_hide"),
        )
        self._set_row_tooltip(
            self.collapse_on_outside_click_row,
            self.collapse_on_outside_click_label,
            self.collapse_on_outside_click_button,
            tr(language, "tooltip_collapse_on_outside_click"),
        )
        self._set_row_tooltip(
            self.music_preview_row,
            self.music_preview_label,
            self.music_preview_button,
            tr(language, "tooltip_music_preview"),
        )
        self._set_row_tooltip(
            self.usb_drive_prompt_row,
            self.usb_drive_prompt_label,
            self.usb_drive_prompt_button,
            tr(language, "tooltip_usb_drive_prompt"),
        )
        self._set_row_tooltip(
            self.show_time_row,
            self.show_time_label,
            self.show_time_button,
            tr(language, "tooltip_show_time"),
        )
        self._set_row_tooltip(
            self.show_cpu_row,
            self.show_cpu_label,
            self.show_cpu_button,
            tr(language, "tooltip_show_cpu"),
        )
        self._set_row_tooltip(
            self.show_memory_row,
            self.show_memory_label,
            self.show_memory_button,
            tr(language, "tooltip_show_memory"),
        )
        self._set_row_tooltip(
            self.show_network_row,
            self.show_network_label,
            self.show_network_button,
            tr(language, "tooltip_show_network"),
        )
        self._set_row_tooltip(
            self.search_engine_row,
            self.search_engine_label,
            self.search_engine_combo,
            tr(language, "tooltip_default_search_engine"),
        )
        self._set_row_tooltip(
            self.search_hotkey_row,
            self.search_hotkey_label,
            self.search_hotkey_button,
            tr(language, "tooltip_search_hotkey"),
        )
        self._set_row_tooltip(
            self.search_hotkey_record_row,
            self.search_hotkey_current_label,
            self.search_hotkey_record_button,
            tr(language, "tooltip_search_hotkey"),
        )
        self._set_row_tooltip(
            self.clipboard_history_row,
            self.clipboard_history_label,
            self.clipboard_history_button,
            tr(language, "tooltip_clipboard_history_enabled"),
        )
        self._set_row_tooltip(
            self.clipboard_persist_row,
            self.clipboard_persist_label,
            self.clipboard_persist_button,
            tr(language, "tooltip_clipboard_persist_enabled"),
        )
        self._set_row_tooltip(
            self.clipboard_url_prompt_row,
            self.clipboard_url_prompt_label,
            self.clipboard_url_prompt_button,
            tr(language, "tooltip_clipboard_url_prompt_enabled"),
        )
        self.clipboard_clear_button.setToolTip(tr(language, "tooltip_clipboard_clear_history"))
    def _set_page(self, index: int) -> None:
        self.current_page = max(0, min(index, self.pages.count() - 1))
        self.pages.setCurrentIndex(self.current_page)
        for i, button in enumerate(self.nav_buttons):
            with QSignalBlocker(button):
                button.setChecked(i == self.current_page)

    def _handle_language_change(self) -> None:
        language = self.language_combo.currentData()
        if not language or language == self.settings.get("language"):
            return

        self.settings["language"] = language
        self.settings["shapeMode"] = "attached"
        save_settings(self.settings)
        self.retranslate()
        self.on_language_changed()

    def _sync_language_combo(self) -> None:
        language = self.settings.get("language")
        with QSignalBlocker(self.language_combo):
            self.language_combo.clear()
            labels = {
                "zh-CN": tr(language, "zh_cn"),
                "zh-TW": tr(language, "zh_tw"),
                "en-US": tr(language, "en_us"),
            }
            for code in SUPPORTED_LANGUAGES:
                self.language_combo.addItem(labels[code], code)

            index = self.language_combo.findData(language)
            self.language_combo.setCurrentIndex(max(0, index))

    def _sync_appearance_controls(self) -> None:
        appearance = self.settings.get("appearance", {})
        self.width_stepper.set_value(int(appearance.get("body_width", DEFAULT_APPEARANCE["body_width"])))
        self.height_stepper.set_value(int(appearance.get("body_height", DEFAULT_APPEARANCE["body_height"])))
        self.radius_stepper.set_value(int(appearance.get("radius", DEFAULT_APPEARANCE["radius"])))
        with QSignalBlocker(self.brand_text_edit):
            self.brand_text_edit.setText(str(appearance.get("brand_text", DEFAULT_APPEARANCE["brand_text"])))
        self.brand_text_error_label.setVisible(False)
        with QSignalBlocker(self.shadow_button), QSignalBlocker(self.animation_button):
            self.shadow_button.setChecked(bool(appearance.get("shadow_enabled", True)))
            self.animation_button.setChecked(bool(appearance.get("animation_enabled", True)))
        self._refresh_toggle_texts()

    def _sync_behavior_controls(self) -> None:
        behavior = self.settings.get("behavior", {})
        with (
            QSignalBlocker(self.auto_hide_button),
            QSignalBlocker(self.collapse_on_outside_click_button),
            QSignalBlocker(self.music_preview_button),
            QSignalBlocker(self.usb_drive_prompt_button),
        ):
            self.auto_hide_button.setChecked(bool(behavior.get("auto_hide_enabled", False)))
            self.collapse_on_outside_click_button.setChecked(
                bool(behavior.get("collapse_on_outside_click", True))
            )
            self.music_preview_button.setChecked(bool(behavior.get("music_preview_enabled", True)))
            self.usb_drive_prompt_button.setChecked(bool(behavior.get("usb_drive_prompt_enabled", True)))
        self._refresh_toggle_texts()

    def _sync_status_controls(self) -> None:
        status = self.settings.get("status", {})
        with (
            QSignalBlocker(self.show_time_button),
            QSignalBlocker(self.show_cpu_button),
            QSignalBlocker(self.show_memory_button),
            QSignalBlocker(self.show_network_button),
        ):
            self.show_time_button.setChecked(bool(status.get("show_time", DEFAULT_STATUS["show_time"])))
            self.show_cpu_button.setChecked(bool(status.get("show_cpu", DEFAULT_STATUS["show_cpu"])))
            self.show_memory_button.setChecked(bool(status.get("show_memory", DEFAULT_STATUS["show_memory"])))
            self.show_network_button.setChecked(bool(status.get("show_network", DEFAULT_STATUS["show_network"])))
        self._refresh_toggle_texts()

    def _sync_search_controls(self) -> None:
        language = self.settings.get("language")
        search = self.settings.get("search", {})
        current_engine = search.get("default_engine", DEFAULT_SEARCH["default_engine"])
        with QSignalBlocker(self.search_engine_combo):
            self.search_engine_combo.clear()
            for key in SEARCH_ENGINE_KEYS:
                self.search_engine_combo.addItem(tr(language, f"engine_{key}"), key)
            index = self.search_engine_combo.findData(current_engine)
            self.search_engine_combo.setCurrentIndex(max(0, index))

    def _sync_hotkey_controls(self) -> None:
        language = self.settings.get("language")
        hotkey = self.settings.get("hotkey", {})
        shortcut = hotkey.get("search_hotkey", DEFAULT_HOTKEY["search_hotkey"])
        with QSignalBlocker(self.search_hotkey_button):
            self.search_hotkey_button.setChecked(
                bool(hotkey.get("search_hotkey_enabled", DEFAULT_HOTKEY["search_hotkey_enabled"]))
            )
        self.search_hotkey_current_label.setText(f"{tr(language, 'search_hotkey_current')}: {shortcut}")
        self.search_hotkey_record_button.setText(
            tr(language, "search_hotkey_recording") if self.hotkey_recording else tr(language, "search_hotkey_record")
        )
        has_error = bool(self.settings.get("_hotkey_error"))
        self.search_hotkey_status_label.setVisible(has_error)
        if has_error:
            self.search_hotkey_status_label.setText(tr(language, "search_hotkey_register_failed"))
        self._refresh_toggle_texts()

    def _sync_clipboard_controls(self) -> None:
        clipboard = self.settings.get("clipboard", {})
        with (
            QSignalBlocker(self.clipboard_history_button),
            QSignalBlocker(self.clipboard_persist_button),
            QSignalBlocker(self.clipboard_url_prompt_button),
        ):
            self.clipboard_history_button.setChecked(
                bool(clipboard.get("history_enabled", DEFAULT_CLIPBOARD["history_enabled"]))
            )
            self.clipboard_persist_button.setChecked(
                bool(clipboard.get("persist_enabled", DEFAULT_CLIPBOARD["persist_enabled"]))
            )
            self.clipboard_url_prompt_button.setChecked(
                bool(clipboard.get("url_open_prompt_enabled", DEFAULT_CLIPBOARD["url_open_prompt_enabled"]))
            )
        self._refresh_toggle_texts()

    def _update_appearance(self, key: str, value) -> None:
        self.settings.setdefault("appearance", {})
        self.settings["appearance"][key] = value
        self.settings["shapeMode"] = "attached"
        save_settings(self.settings)
        self._sync_appearance_controls()
        self.on_appearance_changed()

    def _handle_brand_text_edited(self, value: str) -> None:
        text = value.strip()
        if not text:
            self.brand_text_error_label.setText(tr(self.settings.get("language"), "brand_text_error"))
            self.brand_text_error_label.setVisible(True)
            return
        self.brand_text_error_label.setVisible(False)
        self.settings.setdefault("appearance", {})
        if self.settings["appearance"].get("brand_text") == text:
            return
        self.settings["appearance"]["brand_text"] = text
        self.settings["shapeMode"] = "attached"
        save_settings(self.settings)
        self.on_appearance_changed()

    def _restore_brand_text_default(self) -> None:
        self.brand_text_error_label.setVisible(False)
        self.settings.setdefault("appearance", {})
        self.settings["appearance"]["brand_text"] = DEFAULT_APPEARANCE["brand_text"]
        self.settings["shapeMode"] = "attached"
        save_settings(self.settings)
        self._sync_appearance_controls()
        self.on_appearance_changed()

    def _update_behavior(self, key: str, value) -> None:
        self.settings.setdefault("behavior", {})
        self.settings["behavior"][key] = value
        self.settings["shapeMode"] = "attached"
        save_settings(self.settings)
        self._sync_behavior_controls()
        self.on_behavior_changed()

    def _update_status(self, key: str, value) -> None:
        self.settings.setdefault("status", {})
        self.settings["status"][key] = value
        self.settings["shapeMode"] = "attached"
        save_settings(self.settings)
        self._sync_status_controls()
        self.on_status_changed()

    def _handle_search_engine_change(self) -> None:
        engine = self.search_engine_combo.currentData()
        if not engine:
            return
        self._update_search("default_engine", engine)

    def _update_search(self, key: str, value) -> None:
        self.settings.setdefault("search", {})
        if self.settings["search"].get(key) == value:
            return
        self.settings["search"][key] = value
        self.settings["shapeMode"] = "attached"
        save_settings(self.settings)
        self._sync_search_controls()
        self.on_search_changed()

    def _update_hotkey(self, key: str, value) -> None:
        self.settings.setdefault("hotkey", dict(DEFAULT_HOTKEY))
        if self.settings["hotkey"].get(key) == value:
            return
        self.settings["hotkey"][key] = value
        self.settings["shapeMode"] = "attached"
        save_settings(self.settings)
        self._sync_hotkey_controls()
        self.on_hotkey_changed()

    def _begin_hotkey_recording(self) -> None:
        self.hotkey_recording = True
        self.search_hotkey_record_button.setFocus(Qt.FocusReason.OtherFocusReason)
        self._sync_hotkey_controls()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.search_hotkey_record_button and self.hotkey_recording:
            if event.type() == QEvent.Type.KeyPress:
                self._handle_hotkey_record_key(event)
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self.hotkey_recording:
            if self._handle_hotkey_record_key(event):
                return
        super().keyPressEvent(event)

    def _handle_hotkey_record_key(self, event) -> bool:
        if event.key() == Qt.Key.Key_Escape:
            self.hotkey_recording = False
            self._sync_hotkey_controls()
            event.accept()
            return True
        shortcut = self._hotkey_text_from_event(event)
        if shortcut:
            self.hotkey_recording = False
            self._update_hotkey("search_hotkey", shortcut)
            event.accept()
            return True
        event.accept()
        return True

    @staticmethod
    def _hotkey_text_from_event(event) -> str:
        key = event.key()
        if key in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
        ):
            return ""
        modifiers = event.modifiers()
        parts: list[str] = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            parts.append("Win")
        if not parts:
            return ""
        key_value = key.value if hasattr(key, "value") else int(key)
        key_a = Qt.Key.Key_A.value
        key_z = Qt.Key.Key_Z.value
        key_0 = Qt.Key.Key_0.value
        key_9 = Qt.Key.Key_9.value
        if key_a <= key_value <= key_z:
            parts.append(chr(ord("A") + key_value - key_a))
        elif key_0 <= key_value <= key_9:
            parts.append(chr(ord("0") + key_value - key_0))
        elif key == Qt.Key.Key_Space:
            parts.append("Space")
        elif Qt.Key.Key_F1.value <= key_value <= Qt.Key.Key_F12.value:
            parts.append(f"F{key_value - Qt.Key.Key_F1.value + 1}")
        else:
            return ""
        return "+".join(parts)

    def _update_clipboard(self, key: str, value) -> None:
        self.settings.setdefault("clipboard", {})
        self.settings["clipboard"][key] = value
        self.settings["shapeMode"] = "attached"
        save_settings(self.settings)
        self._sync_clipboard_controls()
        self.on_clipboard_changed()

    def _clear_clipboard_history(self) -> None:
        self.on_clipboard_clear()

    def _reset_appearance_defaults(self) -> None:
        brand_text = self.settings.get("appearance", {}).get("brand_text", DEFAULT_APPEARANCE["brand_text"])
        self.settings["appearance"] = dict(DEFAULT_APPEARANCE)
        self.settings["appearance"]["brand_text"] = brand_text
        self.settings["shapeMode"] = "attached"
        save_settings(self.settings)
        self._sync_appearance_controls()
        self.on_appearance_changed()

    def _refresh_toggle_texts(self) -> None:
        language = self.settings.get("language")
        self.shadow_button.setText(
            tr(language, "enabled") if self.shadow_button.isChecked() else tr(language, "disabled")
        )
        self.animation_button.setText(
            tr(language, "enabled") if self.animation_button.isChecked() else tr(language, "disabled")
        )
        self.auto_hide_button.setText(
            tr(language, "enabled") if self.auto_hide_button.isChecked() else tr(language, "disabled")
        )
        self.collapse_on_outside_click_button.setText(
            tr(language, "enabled")
            if self.collapse_on_outside_click_button.isChecked()
            else tr(language, "disabled")
        )
        self.music_preview_button.setText(
            tr(language, "enabled") if self.music_preview_button.isChecked() else tr(language, "disabled")
        )
        self.usb_drive_prompt_button.setText(
            tr(language, "enabled") if self.usb_drive_prompt_button.isChecked() else tr(language, "disabled")
        )
        for button in (
            self.show_time_button,
            self.show_cpu_button,
            self.show_memory_button,
            self.show_network_button,
            self.search_hotkey_button,
            self.clipboard_history_button,
            self.clipboard_persist_button,
            self.clipboard_url_prompt_button,
        ):
            button.setText(tr(language, "enabled") if button.isChecked() else tr(language, "disabled"))

    def _stepper(self, key: str) -> Stepper:
        minimum, maximum = APPEARANCE_LIMITS[key]
        return Stepper(key, minimum, maximum, APPEARANCE_STEPS[key], self._update_appearance)

    @staticmethod
    def _toggle_button() -> QPushButton:
        button = QPushButton()
        button.setObjectName("toggleButton")
        button.setCheckable(True)
        return button

    @staticmethod
    def _label(kind: str = "normal") -> QLabel:
        label = QLabel()
        label.setProperty("kind", kind)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        label.setWordWrap(kind in ("muted", "hero"))
        return label

    def _refresh_about_icon(self) -> None:
        if self.asset_icon_preview_path.exists():
            pixmap = QIcon(str(self.asset_icon_preview_path)).pixmap(72, 72)
        elif self.asset_icon_path.exists():
            pixmap = QIcon(str(self.asset_icon_path)).pixmap(72, 72)
        else:
            return
        if not pixmap.isNull():
            self.about_icon_label.setPixmap(pixmap)

    def _open_github_profile(self) -> None:
        try:
            webbrowser.open(GITHUB_PROFILE_URL)
        except Exception:
            pass

    @staticmethod
    def _style() -> str:
        return """
        QWidget#settingsWindow {
            background: #111113;
            color: #F5F5F7;
            font-family: "Microsoft YaHei UI", "Segoe UI";
            font-size: 13px;
        }
        QFrame#sidebar {
            background: #18181B;
            border-right: 1px solid #2D2D33;
        }
        QWidget#page {
            background: #111113;
        }
        QFrame#bottomBar {
            background: #111113;
            border-top: 1px solid #2D2D33;
        }
        QFrame#card {
            background: #202024;
            border: 1px solid #2D2D33;
            border-radius: 8px;
        }
        QScrollArea#pageScroll {
            background: #111113;
            border: none;
        }
        QScrollArea#pageScroll > QWidget > QWidget {
            background: #111113;
        }
        QScrollBar:vertical {
            background: #111113;
            width: 8px;
            margin: 8px 2px 8px 0;
        }
        QScrollBar::handle:vertical {
            background: #3F3F46;
            border-radius: 3px;
            min-height: 28px;
        }
        QScrollBar::handle:vertical:hover {
            background: #52525B;
        }
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical,
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {
            background: transparent;
            border: none;
            height: 0;
        }
        QLabel {
            color: #F5F5F7;
            background: transparent;
        }
        QLabel[kind="title"] {
            color: #F5F5F7;
            font-size: 22px;
            font-weight: 700;
            min-height: 32px;
        }
        QLabel[kind="muted"] {
            color: #A1A1AA;
            line-height: 150%;
        }
        QLabel[kind="hero"] {
            color: #67E8F9;
            background: #18181B;
            border: 1px solid #224A5A;
            border-radius: 10px;
            padding: 14px 16px;
            font-size: 16px;
            font-weight: 800;
            line-height: 155%;
        }
        QLabel[kind="section"] {
            color: #F5F5F7;
            font-size: 15px;
            font-weight: 700;
            margin-top: 8px;
        }
        QLabel#aboutIcon {
            background: #18181B;
            border: 1px solid #2D2D33;
            border-radius: 14px;
        }
        QFrame#linkRow {
            background: #18181B;
            border: 1px solid #2D2D33;
            border-radius: 10px;
        }
        QFrame#linkRow:hover {
            background: #202024;
            border-color: #38BDF8;
        }
        QLabel#linkIcon {
            color: #E0F2FE;
            background: #111827;
            border: 1px solid #2D2D33;
            border-radius: 11px;
            font-size: 13px;
            font-weight: 700;
        }
        QLabel#linkTitle {
            color: #F5F5F7;
            font-size: 13px;
            font-weight: 700;
        }
        QLabel#linkUrl {
            color: #67E8F9;
            font-size: 12px;
        }
        QLabel#stepValue {
            color: #F5F5F7;
            background: #111113;
            border: 1px solid #2D2D33;
            border-radius: 7px;
        }
        QPushButton {
            background: #202024;
            color: #F5F5F7;
            border: 1px solid #2D2D33;
            border-radius: 7px;
            padding: 7px 14px;
            min-height: 18px;
        }
        QPushButton:hover {
            background: #2A2A30;
            border-color: #3F3F46;
        }
        QPushButton:pressed {
            background: #18181B;
        }
        QPushButton:disabled {
            color: #71717A;
            background: #18181B;
            border-color: #27272A;
        }
        QPushButton#navButton {
            text-align: left;
            background: transparent;
            border: none;
            color: #A1A1AA;
            padding: 10px 12px;
            min-height: 18px;
        }
        QPushButton#navButton:hover {
            background: #202024;
            color: #F5F5F7;
        }
        QPushButton#navButton:checked {
            background: #2A2A30;
            color: #F5F5F7;
        }
        QPushButton#stepButton {
            min-width: 34px;
            max-width: 34px;
            padding: 0;
            font-size: 16px;
            font-weight: 600;
        }
        QPushButton#toggleButton:checked,
        QPushButton#primaryButton {
            background: #F5F5F7;
            color: #111113;
            border-color: #F5F5F7;
        }
        QComboBox {
            background: #202024;
            color: #F5F5F7;
            border: 1px solid #2D2D33;
            border-radius: 7px;
            padding: 7px 12px;
            min-width: 180px;
        }
        QComboBox QAbstractItemView {
            background: #202024;
            color: #F5F5F7;
            selection-background-color: #2A2A30;
            border: 1px solid #2D2D33;
        }
        QLineEdit#textInput {
            background: #202024;
            color: #F5F5F7;
            border: 1px solid #2D2D33;
            border-radius: 7px;
            padding: 7px 12px;
            min-width: 180px;
            selection-background-color: #3B82F6;
        }
        QLineEdit#textInput:focus {
            border-color: #52525B;
            background: #24242A;
        }
        QToolTip {
            color: #F5F5F7;
            background-color: #202024;
            border: 1px solid #2D2D33;
            padding: 6px;
            border-radius: 6px;
        }
        """
