import ctypes
import ctypes.wintypes
import concurrent.futures
import math
import os
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from PySide6.QtCore import QElapsedTimer, QEvent, QFileInfo, QMimeData, QPoint, QPointF, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QBrush, QConicalGradient, QCursor, QDrag, QFont, QFontMetrics, QGuiApplication, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QFileIconProvider, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMenu, QPushButton, QVBoxLayout, QWidget

from config import DEFAULT_APPEARANCE, DEFAULT_BEHAVIOR, DEFAULT_HOTKEY, DEFAULT_SEARCH, DEFAULT_STATUS
from i18n import tr
from layout_metrics import ResponsiveMetrics, compute_responsive_metrics
from logger import log_error
from media_control import MediaController, MediaSnapshot
from paths import asset_path
from search_service import build_search_url, detect_url, open_query, open_search_result, prewarm_search_indexes, search_local_results
from system_stats import SystemStatsSampler


BODY_WIDTH = 340
BODY_HEIGHT = 34
FONT_UI = "Microsoft YaHei UI"
FONT_FALLBACK = "Segoe UI"
SHADOW_MARGIN_X = 4
SHADOW_MARGIN_BOTTOM = 6
WINDOW_WIDTH = BODY_WIDTH + SHADOW_MARGIN_X * 2
WINDOW_HEIGHT = BODY_HEIGHT + SHADOW_MARGIN_BOTTOM
RADIUS = 5
VISIBLE_HANDLE_HEIGHT = 4
AUTO_WIDTH_MAX = 720
AUTO_WIDTH_EXTRA_PADDING = 32
WIDTH_CHANGE_THRESHOLD = 6
MOTION = {
    "container_expand": 390,
    "container_collapse": 300,
    "content_enter": 180,
    "content_exit": 130,
    "page_switch": 210,
    "search_focus": 220,
    "search_ring_sweep": 920,
    "hover": 150,
    "press": 90,
    "hidden": 170,
    "width": 210,
    "url_prompt": 460,
}
HOVER_DURATION_MS = MOTION["hover"]
PRESS_DURATION_MS = MOTION["press"]
WIDTH_ANIMATION_DURATION_MS = MOTION["width"]
EXPAND_ANIMATION_DURATION_MS = MOTION["container_expand"]
COLLAPSE_ANIMATION_DURATION_MS = MOTION["container_collapse"]
HIDDEN_ANIMATION_DURATION_MS = MOTION["hidden"]
PAGE_SWITCH_DURATION_MS = MOTION["page_switch"]
CONTENT_FADE_DURATION_MS = MOTION["content_enter"]
CONTENT_EXIT_DURATION_MS = MOTION["content_exit"]
FOCUS_RING_DURATION_MS = MOTION["search_focus"]
FOCUS_RING_FADE_MS = 170
SEARCH_SWEEP_DURATION_MS = MOTION["search_ring_sweep"]
FEATURE_HOVER_DURATION_MS = MOTION["hover"]
SEARCH_FOCUS_FLOW_PERIOD_MS = 5200
SEARCH_FLOW_FRAME_INTERVAL_MS = 33
SEARCH_FOCUS_FLOAT_PX = 3
SEARCH_RING_COLORS = (
    "#38BDF8",
    "#60A5FA",
    "#818CF8",
    "#A78BFA",
    "#22D3EE",
    "#2DD4BF",
)
URL_PROMPT_DURATION_MS = 5000
URL_PROMPT_SHAKE_DURATION_MS = MOTION["url_prompt"]
URL_PROMPT_SHAKE_PX = 4
MUSIC_PREVIEW_WIDTH = 460
MUSIC_PREVIEW_HEIGHT = 104
MUSIC_PREVIEW_ANIMATION_MS = 150
MUSIC_PREVIEW_POLL_MS = 1500
CLIPBOARD_DRAG_HOLD_MS = 320
STATUS_GAP = 12
TARGET_ANIMATION_FPS = 120
TARGET_FRAME_INTERVAL_MS = 8
FALLBACK_ANIMATION_FPS = 60
FALLBACK_FRAME_INTERVAL_MS = 16
OUTSIDE_CLICK_INTERVAL_MS = 40
OUTSIDE_CLICK_ARM_DELAY_MS = 80
DEBUG_PERFORMANCE = False
TOP_GUARD_HEIGHT = 2

STATUS_SLOT_TEMPLATES = {
    "network": "↓ 999KB/s ↑ 999KB/s",
    "cpu": "CPU 100%",
    "memory": "RAM 100%",
    "time": "00:00",
}

STATE_COLLAPSED = "collapsed"
STATE_HIDDEN = "hidden"
STATE_EXPANDED = "expanded"

COLLAPSED = {
    "body_width": BODY_WIDTH,
    "body_height": BODY_HEIGHT,
    "window_width": WINDOW_WIDTH,
    "window_height": WINDOW_HEIGHT,
    "radius": RADIUS,
}

HIDDEN = {
    "handle_height": VISIBLE_HANDLE_HEIGHT,
}

EXPANDED = {
    "body_width": 720,
    "body_height": 360,
    "window_width": 728,
    "window_height": 366,
    "radius": 18,
}

VIEW_HOME = "home"
VIEW_DETAIL = "detail"

FEATURE_CLIPBOARD = "clipboard"
FEATURE_FILES = "files"
FEATURE_FAVORITES = "favorites"
FEATURE_ICON_TILE_SIZE = 76
FEATURE_ICON_RADIUS = 20
FEATURE_ICON_SIZE = 44

HEADER_HEIGHT = 54
SEARCH_HEIGHT = 44
SEARCH_BOTTOM_MARGIN = 34
SEARCH_SIDE_MARGIN = 60
SEARCH_RADIUS = 20
SEARCH_RING_WIDTH = 3.1
SEARCH_RING_GLOW_WIDTH = 8.0
SEARCH_RING_ACTIVE_ALPHA = 255
SEARCH_RING_GLOW_ALPHA = 90
SEARCH_RING_FLOW_ALPHA = 252
SEARCH_RING_SWEEP_ALPHA = 255
SEARCH_DEBOUNCE_MS = 150
DRIVE_PROMPT_DURATION_MS = 7000
SEARCH_MAX_LOCAL_RESULTS = 50
SEARCH_WEB_SUGGESTION_MAX = 5
SEARCH_WEB_PANEL_HEIGHT = 204
SEARCH_RESULT_ROW_HEIGHT = 42
SEARCH_RESULT_ROW_GAP = 7
FEATURE_PULSE_PERIOD_MS = 1900
FEATURE_PULSE_FRAME_INTERVAL_MS = 33


@dataclass
class AnimationChannel:
    value: float = 0.0
    start: float = 0.0
    end: float = 0.0
    duration_ms: int = 180
    elapsed_ms: float = 0.0
    active: bool = False
    easing: str = "out_cubic"


@dataclass(frozen=True)
class VisualLayout:
    body_width: int
    body_height: int
    radius: int
    window_width: int
    window_height: int
    body_x: int = SHADOW_MARGIN_X


def build_notch_path(rect: QRectF, radius: float) -> QPainterPath:
    x = rect.x()
    y = rect.y()
    w = rect.width()
    h = rect.height()
    r = max(0.0, min(radius, h / 2))

    path = QPainterPath()
    path.moveTo(x, y)
    path.lineTo(x + w, y)
    path.lineTo(x + w, y + h - r)
    path.quadTo(x + w, y + h, x + w - r, y + h)
    path.lineTo(x + r, y + h)
    path.quadTo(x, y + h, x, y + h - r)
    path.lineTo(x, y)
    path.closeSubpath()
    return path


def ease_out_quint(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - pow(1 - t, 5)


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - pow(1 - t, 3)


def ease_in_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 4 * t * t * t
    return 1 - pow(-2 * t + 2, 3) / 2


def ease_smoother(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * t * (t * (t * 6 - 15) + 10)


def search_focus_lift_offset(progress: float) -> float:
    return -SEARCH_FOCUS_FLOAT_PX * ease_out_cubic(progress)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def remap_progress(t: float, start: float, end: float) -> float:
    return clamp((t - start) / max(0.001, end - start), 0.0, 1.0)


def staged_expand_width(t: float) -> float:
    return ease_out_quint(remap_progress(t, 0.00, 0.56))


def staged_expand_height(t: float) -> float:
    return ease_out_quint(remap_progress(t, 0.14, 1.00))


def staged_expand_radius(t: float) -> float:
    return ease_out_cubic(remap_progress(t, 0.08, 0.90))


def staged_expand_shadow(t: float) -> float:
    return ease_out_cubic(remap_progress(t, 0.20, 1.00))


def staged_expand_header_alpha(t: float) -> float:
    return ease_out_cubic(remap_progress(t, 0.35, 0.72))


def staged_expand_content_alpha(t: float) -> float:
    return ease_out_cubic(remap_progress(t, 0.78, 1.00))


def staged_expand_search_alpha(t: float) -> float:
    return ease_out_cubic(remap_progress(t, 0.84, 1.00))


def expand_soft_deform(t: float) -> dict[str, float]:
    p = remap_progress(t, 0.70, 1.0)
    if p <= 0.0:
        return {"width_extra": 0.0, "height_extra": 0.0, "bottom_stretch": 0.0, "shadow_boost": 0.0}
    wave = math.sin(p * math.pi) * (1.0 - p)
    return {
        "width_extra": wave * 4.0,
        "height_extra": wave * 2.6,
        "bottom_stretch": wave * 2.0,
        "shadow_boost": wave * 0.16,
    }


def expanded_radius_from_user_radius(radius: float) -> int:
    return int(round(clamp(radius * 2.4, 12, 32)))


def _is_global_left_button_down() -> bool:
    try:
        state = ctypes.windll.user32.GetAsyncKeyState(0x01)
        return bool(state & 0x8000)
    except Exception:
        return bool(QApplication.mouseButtons() & Qt.MouseButton.LeftButton)


WM_HOTKEY = 0x0312
HOTKEY_ID_SEARCH = 0x4F42
WM_DEVICECHANGE = 0x0219
DBT_DEVICEARRIVAL = 0x8000
DBT_DEVICEREMOVECOMPLETE = 0x8004
DBT_DEVTYP_VOLUME = 0x00000002
DRIVE_REMOVABLE = 2
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000


def _parse_hotkey_text(text: str) -> tuple[int, int] | None:
    if not isinstance(text, str):
        return None
    tokens = [part.strip() for part in text.split("+") if part.strip()]
    if len(tokens) < 2:
        return None
    modifiers = 0
    key_vk: int | None = None
    for token in tokens:
        lowered = token.lower()
        if lowered in ("ctrl", "control"):
            modifiers |= MOD_CONTROL
        elif lowered == "alt":
            modifiers |= MOD_ALT
        elif lowered == "shift":
            modifiers |= MOD_SHIFT
        elif lowered in ("win", "meta", "super"):
            modifiers |= MOD_WIN
        elif lowered == "space":
            key_vk = 0x20
        elif lowered.startswith("f") and lowered[1:].isdigit() and 1 <= int(lowered[1:]) <= 12:
            key_vk = 0x70 + int(lowered[1:]) - 1
        elif len(token) == 1 and token.isalpha():
            key_vk = ord(token.upper())
        elif len(token) == 1 and token.isdigit():
            key_vk = ord(token)
        else:
            return None
    if key_vk is None or modifiers == 0:
        return None
    return modifiers | MOD_NOREPEAT, key_vk


class DEV_BROADCAST_HDR(ctypes.Structure):
    _fields_ = [
        ("dbch_size", ctypes.wintypes.DWORD),
        ("dbch_devicetype", ctypes.wintypes.DWORD),
        ("dbch_reserved", ctypes.wintypes.DWORD),
    ]


class DEV_BROADCAST_VOLUME(ctypes.Structure):
    _fields_ = [
        ("dbcv_size", ctypes.wintypes.DWORD),
        ("dbcv_devicetype", ctypes.wintypes.DWORD),
        ("dbcv_reserved", ctypes.wintypes.DWORD),
        ("dbcv_unitmask", ctypes.wintypes.DWORD),
        ("dbcv_flags", ctypes.wintypes.WORD),
    ]


class FavoriteUrlDialog(QDialog):
    def __init__(self, language: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.language = language
        self.title_value = ""
        self.url_value = ""
        self.setWindowTitle(tr(language, "favorite_add_url"))
        self.setModal(True)
        self.setFixedSize(420, 260)
        self.setStyleSheet(
            """
            QDialog { background: #111113; color: #F5F5F7; }
            QLabel { color: #F5F5F7; font: 13px "Microsoft YaHei UI"; }
            QLabel#Hint { color: #A1A1AA; }
            QLabel#Error { color: #FFB86B; }
            QLineEdit {
                background: #232329;
                color: #F5F5F7;
                border: 1px solid #2D2D33;
                border-radius: 8px;
                padding: 8px 10px;
                font: 13px "Microsoft YaHei UI";
            }
            QLineEdit:focus { border: 1px solid #38BDF8; }
            QPushButton {
                background: #2A2A30;
                color: #F5F5F7;
                border: 1px solid #34343B;
                border-radius: 8px;
                padding: 8px 14px;
                font: 13px "Microsoft YaHei UI";
            }
            QPushButton#Primary {
                background: #0EA5E9;
                border: 1px solid #38BDF8;
                color: white;
            }
            QPushButton:hover { background: #33333A; }
            QPushButton#Primary:hover { background: #0284C7; }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(12)

        title = QLabel(tr(language, "favorite_add_url"))
        title.setStyleSheet('font: 18px "Microsoft YaHei UI"; font-weight: 700;')
        root.addWidget(title)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(tr(language, "favorite_title_label"))
        root.addWidget(self.title_edit)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(tr(language, "favorite_url_label"))
        root.addWidget(self.url_edit)

        self.error_label = QLabel("")
        self.error_label.setObjectName("Error")
        self.error_label.setFixedHeight(22)
        root.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_btn = QPushButton(tr(language, "action_cancel"))
        add_btn = QPushButton(tr(language, "action_add"))
        add_btn.setObjectName("Primary")
        add_btn.setDefault(True)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(add_btn)
        root.addLayout(buttons)

        cancel_btn.clicked.connect(self.reject)
        add_btn.clicked.connect(self._submit)

    def _submit(self) -> None:
        raw_url = self.url_edit.text().strip()
        normalized = detect_url(raw_url)
        if not normalized:
            self.error_label.setText(tr(self.language, "favorite_url_invalid"))
            self.url_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        self.title_value = self.title_edit.text().strip()
        self.url_value = normalized
        self.accept()


class IslandWindow(QWidget):
    def __init__(
        self,
        appearance: dict[str, Any] | None = None,
        behavior: dict[str, Any] | None = None,
        status: dict[str, Any] | None = None,
        language: str = "zh-CN",
        search: dict[str, Any] | None = None,
        hotkey: dict[str, Any] | None = None,
        clipboard_manager: Any | None = None,
        file_hub_manager: Any | None = None,
        favorites_manager: Any | None = None,
    ) -> None:
        super().__init__()
        self.state = STATE_COLLAPSED
        self.is_expanded = False
        self.is_collapsed_hidden = False
        self.expand_target_state: str | None = None
        self.expand_direction: str | None = None
        self._schedule_auto_hide_after_collapse = True
        self.hover_progress = 0.0
        self.press_progress = 0.0
        self.hidden_progress = 0.0
        self.expand_progress = 0.0
        self.page_transition_progress = 1.0
        self.content_fade_progress = 0.0
        self.focus_ring_progress = 0.0
        self.search_sweep_progress = 0.0
        self.search_focus_flow_phase = 0.0
        self.feature_hover_progress = 0.0
        self.feature_hovered = False
        self.feature_pulse_phase = 0.0
        self.url_prompt_progress = 1.0
        self.language = language
        self.current_time = self._format_time()

        self.appearance = dict(DEFAULT_APPEARANCE)
        self.behavior = dict(DEFAULT_BEHAVIOR)
        self.status = dict(DEFAULT_STATUS)
        self.search = dict(DEFAULT_SEARCH)
        self.hotkey = dict(DEFAULT_HOTKEY)
        self.brand_text = DEFAULT_APPEARANCE["brand_text"]
        self.open_settings_callback: Callable[[], None] | None = None
        self.auto_hide_enabled = False
        self.auto_hide_delay_seconds = 5
        self.collapse_on_outside_click = True
        self.usb_drive_prompt_enabled = True
        self.show_time = True
        self.show_cpu = False
        self.show_memory = False
        self.show_network = False
        self.status_update_interval_ms = 1000
        self.default_search_engine = DEFAULT_SEARCH["default_engine"]
        self.search_hotkey_enabled = False
        self.search_hotkey_text = DEFAULT_HOTKEY["search_hotkey"]
        self.search_hotkey_registered = False
        self.search_hotkey_error = ""
        self.url_open_prompt_enabled = True
        self.music_preview_enabled = True
        self.clipboard_manager = clipboard_manager
        if self.clipboard_manager is not None:
            self.clipboard_manager.on_changed = self._handle_clipboard_history_changed
            self.clipboard_manager.on_url_copied = self.handle_copied_url
        self.file_hub_manager = file_hub_manager
        if self.file_hub_manager is not None:
            self.file_hub_manager.on_changed = self._handle_file_hub_changed
        self.favorites_manager = favorites_manager
        if self.favorites_manager is not None:
            self.favorites_manager.on_changed = self._handle_favorites_changed
        self.stats_sampler = SystemStatsSampler()
        self.status_values = {
            "cpu": None,
            "memory": None,
            "network": None,
        }
        self.media_controller = MediaController()
        self.media_snapshot = MediaSnapshot()
        self.media_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="OneBarMedia")
        self.media_future: concurrent.futures.Future | None = None
        self.music_preview_progress = 0.0
        self.music_preview_requested = False
        self.music_button_rects: dict[str, QRectF] = {}
        self.music_button_hover: str | None = None
        self.media_cover_source_pixmap: QPixmap | None = None
        self.media_cover_source_key: tuple | None = None
        self.media_cover_render_pixmap: QPixmap | None = None
        self.media_cover_render_key: tuple | None = None
        self.default_media_cover_pixmap: QPixmap | None = None
        self.default_media_cover_key: tuple | None = None

        self.user_body_width = BODY_WIDTH
        self.user_body_height = BODY_HEIGHT
        self.user_radius = RADIUS
        self.responsive_metrics = compute_responsive_metrics(
            self.user_body_width,
            self.user_body_height,
            self.user_radius,
            1920,
            1080,
            1.0,
        )
        self._screen_signal_connected = False
        self._connected_screen_ids: set[int] = set()

        self.base_body_width = BODY_WIDTH
        self.base_body_height = BODY_HEIGHT
        self.base_radius = RADIUS
        self.current_body_width = BODY_WIDTH
        self.current_body_height = BODY_HEIGHT
        self.current_radius = RADIUS
        self.auto_body_width_target = BODY_WIDTH
        self.window_width = WINDOW_WIDTH
        self.window_height = WINDOW_HEIGHT
        self._shape_start = (BODY_WIDTH, BODY_HEIGHT, RADIUS)
        self._shape_target = (BODY_WIDTH, BODY_HEIGHT, RADIUS)
        self._shape_motion_mode = "linear"
        self._path_cache_key: tuple[int, int, int, int, float] | None = None
        self._path_cache = QPainterPath()
        self._last_visual_layout: VisualLayout | None = None
        self._prewarm_done = False
        self._prewarmed_paths: dict[str, QPainterPath] = {}
        self.panel_placeholder_text = ""
        self._outside_prev_left_down = False
        self.pending_hide_after_collapse = False
        self.current_view = VIEW_HOME
        self.features = [FEATURE_CLIPBOARD, FEATURE_FILES, FEATURE_FAVORITES]
        self.current_feature_index = 0
        self.search_text = ""
        self.search_query = ""
        self.local_search_results: list[dict] = []
        self.web_suggestions: list[dict] = []
        self.selected_search_index = 0
        self.search_scroll_offset = 0
        self.search_is_loading = False
        self.search_query_id = 0
        self.search_result_rects: list[tuple[int, QRectF]] = []
        self.web_suggestion_rects: list[tuple[int, QRectF]] = []
        self.search_focused = False
        self._search_edit_rect = QRectF()
        self.expanded_hit_rects: dict[str, QRectF] = {}
        self.feature_hit_rect = QRectF()
        self.feature_dot_rects: list[tuple[int, QRectF]] = []
        self.action_button_rects: list[tuple[str, QRectF]] = []
        self.settings_icon_rect = QRectF()
        self.clipboard_item_rects: list[tuple[int, QRectF]] = []
        self.file_item_rects: list[tuple[int, QRectF]] = []
        self.favorite_item_rects: list[tuple[int, QRectF]] = []
        self.clipboard_scroll_offset = 0
        self.clipboard_scroll_y = 0.0
        self.clipboard_list_viewport_rect = QRectF()
        self.clipboard_scrollbar_track_rect = QRectF()
        self.clipboard_scrollbar_thumb_rect = QRectF()
        self.clipboard_scrollbar_dragging = False
        self.clipboard_scrollbar_drag_start_y = 0.0
        self.clipboard_scrollbar_drag_start_scroll_y = 0.0
        self.file_scroll_offset = 0
        self.favorites_scroll_offset = 0
        self.clipboard_pressed_index: int | None = None
        self.clipboard_press_pos = QPointF()
        self.clipboard_long_press_ready = False
        self.clipboard_drag_started = False
        self.clipboard_drag_consumed = False
        self.file_drag_index: int | None = None
        self.file_press_pos = QPointF()
        self.file_drop_active = False
        self.file_drop_paths: list[str] = []
        self.url_prompt_active = False
        self.url_prompt_url = ""
        self.last_prompted_url = ""
        self.drive_prompt_active = False
        self.drive_prompt_path = ""
        self.drive_prompt_name = ""
        self.last_prompted_drive = ""
        self.last_prompted_drive_time = 0.0
        self._known_removable_drives = self._current_removable_drives()

        self._build_paint_cache()
        self.file_icon_provider = QFileIconProvider()
        self._file_icon_cache: dict[tuple[str, int], QPixmap] = {}
        self.search_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="OneBarSearch")
        self.search_future: concurrent.futures.Future | None = None
        self.search_future_query: tuple[int, str] | None = None
        self.search_prewarm_future: concurrent.futures.Future | None = None
        self._paint_count = 0
        self._tick_count = 0
        self._paint_total_ms = 0.0
        self._debug_last_tick = time.monotonic()
        self._perf_window_start = time.monotonic()
        self._perf_tick_count = 0
        self._low_tick_fps_seconds = 0
        self.high_refresh_enabled = True
        self.current_animation_interval_ms = TARGET_FRAME_INTERVAL_MS

        self.animation_clock = QElapsedTimer()
        self.animation_channels = {
            "hover": AnimationChannel(self.hover_progress),
            "press": AnimationChannel(self.press_progress),
            "hidden": AnimationChannel(self.hidden_progress),
            "expand": AnimationChannel(self.expand_progress),
            "page": AnimationChannel(self.page_transition_progress),
            "content": AnimationChannel(self.content_fade_progress),
            "focus_ring": AnimationChannel(self.focus_ring_progress),
            "search_sweep": AnimationChannel(self.search_sweep_progress),
            "feature_hover": AnimationChannel(self.feature_hover_progress),
            "url_prompt": AnimationChannel(self.url_prompt_progress),
            "music_preview": AnimationChannel(self.music_preview_progress),
            "width": AnimationChannel(1.0),
        }

        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setWindowTitle("OneBar")
        icon_path = asset_path("icon.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.search_edit = QLineEdit(self)
        self.search_edit.setFrame(False)
        self.search_edit.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.search_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.search_edit.setStyleSheet("QLineEdit { background: transparent; border: none; color: #F5F5F7; selection-background-color: #3A3A42; }")
        self.search_edit.setFont(self.search_font)
        self.search_edit.setPlaceholderText(tr(self.language, "feature_search_placeholder"))
        self.search_edit.hide()
        self.search_edit.installEventFilter(self)
        self.search_edit.textChanged.connect(self._handle_search_text_changed)

        self.animation_timer = QTimer(self)
        self.animation_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.animation_timer.timeout.connect(self._on_animation_tick)

        if DEBUG_PERFORMANCE:
            self.debug_timer = QTimer(self)
            self.debug_timer.timeout.connect(self._print_performance_debug)
            self.debug_timer.start(1000)

        self.auto_hide_timer = QTimer(self)
        self.auto_hide_timer.setSingleShot(True)
        self.auto_hide_timer.timeout.connect(self._handle_auto_hide_timeout)

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._update_status_snapshot)

        self.outside_click_timer = QTimer(self)
        self.outside_click_timer.setTimerType(Qt.TimerType.CoarseTimer)
        self.outside_click_timer.timeout.connect(self._check_outside_click)

        self.url_prompt_timer = QTimer(self)
        self.url_prompt_timer.setSingleShot(True)
        self.url_prompt_timer.timeout.connect(self._clear_url_prompt)

        self.drive_prompt_timer = QTimer(self)
        self.drive_prompt_timer.setSingleShot(True)
        self.drive_prompt_timer.timeout.connect(self._clear_drive_prompt)

        self.media_poll_timer = QTimer(self)
        self.media_poll_timer.setInterval(MUSIC_PREVIEW_POLL_MS)
        self.media_poll_timer.setTimerType(Qt.TimerType.CoarseTimer)
        self.media_poll_timer.timeout.connect(self._request_media_snapshot)

        self.media_result_poll_timer = QTimer(self)
        self.media_result_poll_timer.setInterval(80)
        self.media_result_poll_timer.setTimerType(Qt.TimerType.CoarseTimer)
        self.media_result_poll_timer.timeout.connect(self._poll_media_future)

        self.clipboard_drag_timer = QTimer(self)
        self.clipboard_drag_timer.setSingleShot(True)
        self.clipboard_drag_timer.timeout.connect(self._mark_clipboard_long_press_ready)

        self.search_debounce_timer = QTimer(self)
        self.search_debounce_timer.setSingleShot(True)
        self.search_debounce_timer.timeout.connect(self._refresh_search_results)

        self.search_result_poll_timer = QTimer(self)
        self.search_result_poll_timer.setInterval(45)
        self.search_result_poll_timer.timeout.connect(self._poll_search_future)

        self.apply_appearance(appearance or DEFAULT_APPEARANCE)
        self.apply_behavior_settings(behavior or DEFAULT_BEHAVIOR)
        self.apply_status_settings(status or DEFAULT_STATUS)
        self.apply_search_settings(search or DEFAULT_SEARCH)
        self.apply_hotkey_settings(hotkey or DEFAULT_HOTKEY)
        if self.clipboard_manager is not None:
            self.apply_clipboard_settings(self.clipboard_manager.settings)

    def showEvent(self, event) -> None:  # noqa: N802
        if self.state == STATE_EXPANDED:
            self.set_expanded(False, schedule_auto_hide=False)
        self._attach_screen_signals()
        self._refresh_responsive_metrics()
        self.apply_visual_geometry()
        self._restart_status_timer()
        self._schedule_auto_hide_if_needed()
        super().showEvent(event)
        if not self._prewarm_done:
            self._prewarm_done = True
            QTimer.singleShot(300, self._prewarm_animation_cache)
            QTimer.singleShot(900, self._prewarm_search_indexes)

    def hideEvent(self, event) -> None:  # noqa: N802
        self.auto_hide_timer.stop()
        self.status_timer.stop()
        self.outside_click_timer.stop()
        self.url_prompt_timer.stop()
        self.drive_prompt_timer.stop()
        self.media_poll_timer.stop()
        self.media_result_poll_timer.stop()
        self.clipboard_drag_timer.stop()
        self.search_debounce_timer.stop()
        self.search_result_poll_timer.stop()
        self._clear_url_prompt(update_width=False)
        self._clear_drive_prompt(update_width=False)
        self.search_edit.clearFocus()
        self.search_edit.hide()
        if self.state == STATE_EXPANDED:
            self._collapse_immediately()
        else:
            self._stop_animations()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.auto_hide_timer.stop()
        self.status_timer.stop()
        self.outside_click_timer.stop()
        self.url_prompt_timer.stop()
        self.drive_prompt_timer.stop()
        self.media_poll_timer.stop()
        self.media_result_poll_timer.stop()
        self.clipboard_drag_timer.stop()
        self.search_debounce_timer.stop()
        self.search_result_poll_timer.stop()
        self._unregister_search_hotkey()
        self.search_executor.shutdown(wait=False, cancel_futures=True)
        self.media_executor.shutdown(wait=False, cancel_futures=True)
        self._clear_url_prompt(update_width=False)
        self._clear_drive_prompt(update_width=False)
        self.search_edit.clearFocus()
        self.search_edit.hide()
        self._stop_animations()
        super().closeEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        if self._favorites_detail_active():
            index = self._favorite_item_at(event.pos())
            if index is not None:
                self._show_favorite_item_menu(index, self.mapToGlobal(event.pos()))
                event.accept()
                return
        if self._file_hub_detail_active():
            index = self._file_item_at(event.pos())
            if index is not None:
                self._show_file_item_menu(index, self.mapToGlobal(event.pos()))
                event.accept()
                return
        if self._clipboard_detail_active():
            index = self._clipboard_item_at(event.pos())
            if index is not None:
                self._show_clipboard_item_menu(index, self.mapToGlobal(event.pos()))
                event.accept()
                return
        event.accept()

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        paths = self._local_paths_from_mime(event.mimeData())
        if paths:
            self.file_drop_paths = paths
            event.acceptProposedAction()
            if self.state == STATE_COLLAPSED and not self.file_drop_active:
                self._start_file_drop_preview()
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if self._local_paths_from_mime(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._cancel_file_drop_preview()
        event.accept()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = self._local_paths_from_mime(event.mimeData())
        if paths and self.file_hub_manager is not None:
            self.file_hub_manager.add_paths(paths)
            event.acceptProposedAction()
        else:
            event.ignore()
        self._cancel_file_drop_preview()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.search_edit:
            event_type = event.type()
            if event_type == QEvent.Type.FocusIn:
                self.search_focused = True
                self.search_focus_flow_phase = 0.0
                self.search_sweep_progress = 0.0
                self.animation_channels["search_sweep"].value = 0.0
                self._animate_channel("focus_ring", 1.0, FOCUS_RING_DURATION_MS, "out_cubic")
                self._animate_channel("search_sweep", 1.0, SEARCH_SWEEP_DURATION_MS, "out_cubic")
                self._request_update()
                return False
            if event_type == QEvent.Type.FocusOut:
                self.search_focused = False
                self._animate_channel("focus_ring", 0.0, FOCUS_RING_FADE_MS, "out_cubic")
                self.animation_channels["search_sweep"].active = False
                self.animation_channels["search_sweep"].value = 0.0
                self.search_sweep_progress = 0.0
                self._request_update()
                return False
            if event_type == QEvent.Type.KeyPress:
                key = event.key()
                if key == Qt.Key.Key_Escape:
                    self._handle_escape_key()
                    event.accept()
                    return True
                if key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self._search_results_active():
                    self._move_search_selection(1 if key == Qt.Key.Key_Down else -1)
                    event.accept()
                    return True
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    self._execute_search()
                    event.accept()
                    return True
        return super().eventFilter(watched, event)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.auto_hide_timer.stop()
        self._animate_channel("hover", 1.0, HOVER_DURATION_MS, "out_cubic")
        self._maybe_start_music_preview()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._animate_channel("hover", 0.0, HOVER_DURATION_MS, "out_cubic")
        self._set_feature_hovered(False)
        self._schedule_hide_music_preview()
        self._schedule_auto_hide_if_needed()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self._update_music_button_hover(event.position())
        if self._music_preview_draw_active() and not self._media_preview_rect().contains(event.position()):
            self._hide_music_preview()
        if self.clipboard_scrollbar_dragging:
            self._drag_clipboard_scrollbar(event.position())
            event.accept()
            return
        if self._maybe_start_file_drag(event.position()):
            event.accept()
            return
        if self._maybe_start_clipboard_drag(event.position()):
            event.accept()
            return
        self._update_feature_hover(event.position())
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton and self._favorites_detail_active():
            index = self._favorite_item_at(event.position())
            if index is not None:
                self._show_favorite_item_menu(index, self.mapToGlobal(event.position().toPoint()))
                event.accept()
                return
        if event.button() == Qt.MouseButton.RightButton and self._clipboard_detail_active():
            index = self._clipboard_item_at(event.position())
            if index is not None:
                self._show_clipboard_item_menu(index, self.mapToGlobal(event.position().toPoint()))
                event.accept()
                return
        if event.button() == Qt.MouseButton.RightButton and self._file_hub_detail_active():
            index = self._file_item_at(event.position())
            if index is not None:
                self._show_file_item_menu(index, self.mapToGlobal(event.position().toPoint()))
                event.accept()
                return
        if event.button() == Qt.MouseButton.LeftButton and self.state != STATE_HIDDEN:
            if self._clipboard_detail_active() and self.clipboard_scrollbar_thumb_rect.contains(event.position()):
                self.clipboard_scrollbar_dragging = True
                self.clipboard_scrollbar_drag_start_y = event.position().y()
                self.clipboard_scrollbar_drag_start_scroll_y = self.clipboard_scroll_y
                event.accept()
                return
            if self._file_hub_detail_active():
                self.file_drag_index = self._file_item_at(event.position())
                self.file_press_pos = QPointF(event.position())
            self._prepare_clipboard_drag(event.position())
            self._animate_channel("press", 1.0, PRESS_DURATION_MS, "out_cubic")
            event.accept()
            return
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.clipboard_scrollbar_dragging:
            self.clipboard_scrollbar_dragging = False
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.state != STATE_HIDDEN:
            self._animate_channel("press", 0.0, PRESS_DURATION_MS, "out_cubic")
            if self.clipboard_drag_started or self.clipboard_drag_consumed:
                self._reset_clipboard_drag_state()
                event.accept()
                return
            self.file_drag_index = None
            self.clipboard_drag_timer.stop()
            if self.state == STATE_EXPANDED and self.expand_target_state is None:
                self._handle_expanded_click(event.position())
            else:
                if self._handle_music_preview_click(event.position()):
                    event.accept()
                    return
                if self.url_prompt_active and self.state == STATE_COLLAPSED:
                    self._open_url_prompt()
                    event.accept()
                    return
                if self.drive_prompt_active and self.state == STATE_COLLAPSED:
                    self._open_drive_prompt()
                    event.accept()
                    return
                self.toggle_expanded()
            event.accept()
            return
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            if self._favorites_detail_active() and self._favorite_item_at(event.position()) is not None:
                event.accept()
                return
            if self._clipboard_detail_active() and self._clipboard_item_at(event.position()) is not None:
                event.accept()
                return
            if self._file_hub_detail_active() and self._file_item_at(event.position()) is not None:
                event.accept()
                return
            if self.state == STATE_EXPANDED:
                self.hide_after_collapse()
            else:
                self.toggle_hidden()
            event.accept()
            return
        event.accept()

    def wheelEvent(self, event) -> None:  # noqa: N802
        if self.state == STATE_EXPANDED and self._search_results_active():
            delta = event.angleDelta().y()
            self._scroll_search_results(-1 if delta > 0 else 1)
            event.accept()
            return
        if self._clipboard_detail_active():
            delta = event.angleDelta().y()
            self._scroll_clipboard_items(-delta)
            event.accept()
            return
        if self._file_hub_detail_active():
            delta = event.angleDelta().y()
            self._scroll_file_items(-1 if delta > 0 else 1)
            event.accept()
            return
        if self._favorites_detail_active():
            delta = event.angleDelta().y()
            self._scroll_favorite_items(-1 if delta > 0 else 1)
            event.accept()
            return
        if self.state == STATE_EXPANDED and self.current_view == VIEW_HOME:
            delta = event.angleDelta().y()
            if delta < 0:
                self._switch_feature(1)
            elif delta > 0:
                self._switch_feature(-1)
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            if self._handle_escape_key():
                event.accept()
                return

        if self.state != STATE_EXPANDED:
            super().keyPressEvent(event)
            return

        key = event.key()
        if self.search_edit.hasFocus() or self.search_focused:
            super().keyPressEvent(event)
            return
        if self.current_view == VIEW_HOME and key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            self._switch_feature(1 if key == Qt.Key.Key_Down else -1)
            event.accept()
            return
        super().keyPressEvent(event)

    def _handle_escape_key(self) -> bool:
        if self.search_edit.hasFocus() or self.search_focused:
            self.search_edit.clearFocus()
            self.search_focused = False
            self.setFocus(Qt.FocusReason.OtherFocusReason)
            self._request_update()
            return True
        if self.url_prompt_active:
            self._clear_url_prompt()
            return True
        if self._music_preview_draw_active():
            self._hide_music_preview()
            return True
        if self.state == STATE_EXPANDED:
            if self.current_view == VIEW_DETAIL:
                self.current_view = VIEW_HOME
                self._animate_channel("page", 1.0, PAGE_SWITCH_DURATION_MS, "out_cubic")
                self._request_update()
                return True
            self.set_expanded(False)
            return True
        return False

    def reposition(self) -> None:
        self.apply_visual_geometry()

    def _current_screen(self):
        return self.screen() or QGuiApplication.primaryScreen()

    def _refresh_responsive_metrics(self) -> ResponsiveMetrics:
        screen = self._current_screen()
        if screen is None:
            metrics = compute_responsive_metrics(
                self.user_body_width,
                self.user_body_height,
                self.user_radius,
                1920,
                1080,
                1.0,
            )
        else:
            geometry = screen.geometry()
            dpi_scale = max(0.5, float(screen.logicalDotsPerInch()) / 96.0)
            metrics = compute_responsive_metrics(
                self.user_body_width,
                self.user_body_height,
                self.user_radius,
                int(geometry.width()),
                int(geometry.height()),
                dpi_scale,
            )
        self.responsive_metrics = metrics
        self.base_body_width = metrics.collapsed_width
        self.base_body_height = metrics.collapsed_height
        self.base_radius = metrics.collapsed_radius
        return metrics

    def _expanded_target_metrics(self) -> tuple[int, int, int]:
        metrics = self.responsive_metrics
        return metrics.expanded_width, metrics.expanded_height, metrics.expanded_radius

    def _screen_safe_body_width(self, width: int) -> int:
        metrics = self.responsive_metrics
        return int(max(1, min(int(width), metrics.collapsed_max_width)))

    def _attach_screen_signals(self) -> None:
        window = self.windowHandle()
        if window is not None and not self._screen_signal_connected:
            window.screenChanged.connect(lambda _screen: self._handle_screen_metrics_changed())
            self._screen_signal_connected = True
        app = QGuiApplication.instance()
        if app is not None and not getattr(self, "_app_screen_signals_connected", False):
            app.screenAdded.connect(lambda _screen: self._handle_screen_metrics_changed())
            app.screenRemoved.connect(lambda _screen: self._handle_screen_metrics_changed())
            self._app_screen_signals_connected = True
        screen = self._current_screen()
        if screen is not None and id(screen) not in self._connected_screen_ids:
            screen.geometryChanged.connect(lambda _geometry: self._handle_screen_metrics_changed())
            screen.logicalDotsPerInchChanged.connect(lambda _dpi: self._handle_screen_metrics_changed())
            self._connected_screen_ids.add(id(screen))

    def _handle_screen_metrics_changed(self) -> None:
        self._refresh_responsive_metrics()
        self._path_cache_key = None
        self.media_cover_render_pixmap = None
        self.media_cover_render_key = None
        self.default_media_cover_pixmap = None
        self.default_media_cover_key = None
        if self.state == STATE_EXPANDED or self.expand_target_state == STATE_EXPANDED:
            width, height, radius = self._expanded_target_metrics()
            self._shape_target = (width, height, radius)
            if self.expand_target_state is None:
                self._set_shape_metrics(width, height, radius, request_update=False)
        else:
            self._update_auto_width(force=True, duration=0 if not self.animation_enabled else WIDTH_ANIMATION_DURATION_MS)
        layout = self.apply_visual_geometry()
        if self.state == STATE_EXPANDED:
            self._sync_search_edit_geometry(self._expanded_rects(layout)["search"], self.search_edit.isVisible())
        self._request_update()

    def apply_appearance(self, appearance: dict[str, Any]) -> None:
        merged = dict(DEFAULT_APPEARANCE)
        merged.update(appearance or {})
        self.appearance = merged

        self.user_body_width = int(merged["body_width"])
        self.user_body_height = int(merged["body_height"])
        self.user_radius = int(merged["radius"])
        self._refresh_responsive_metrics()
        self.shadow_enabled = bool(merged["shadow_enabled"])
        self.animation_enabled = bool(merged["animation_enabled"])
        brand_text = str(merged.get("brand_text", DEFAULT_APPEARANCE["brand_text"])).strip()
        self.brand_text = brand_text[:12] if brand_text else DEFAULT_APPEARANCE["brand_text"]

        if not self.animation_enabled:
            self._sync_motion_to_current_state()

        if self.state == STATE_EXPANDED:
            self._animate_shape_to(*self._expanded_target_metrics())
        else:
            self._update_auto_width(force=True)
        self._request_update()

    def apply_behavior_settings(self, behavior: dict[str, Any]) -> None:
        merged = dict(DEFAULT_BEHAVIOR)
        merged.update(behavior or {})
        self.behavior = merged
        self.auto_hide_enabled = bool(merged.get("auto_hide_enabled", False))
        self.auto_hide_delay_seconds = int(merged.get("auto_hide_delay_seconds", 5))
        self.collapse_on_outside_click = bool(merged.get("collapse_on_outside_click", True))
        self.music_preview_enabled = bool(merged.get("music_preview_enabled", True))
        self.usb_drive_prompt_enabled = bool(merged.get("usb_drive_prompt_enabled", True))
        if not self.music_preview_enabled:
            self._hide_music_preview(immediate=True)
        if not self.usb_drive_prompt_enabled:
            self._clear_drive_prompt()

        if not self.auto_hide_enabled:
            self.auto_hide_timer.stop()
        self._sync_outside_click_watch()
        if not self.auto_hide_enabled:
            return
        self._schedule_auto_hide_if_needed()

    def apply_status_settings(self, status: dict[str, Any]) -> None:
        merged = dict(DEFAULT_STATUS)
        merged.update(status or {})
        self.status = merged
        self.show_time = bool(merged.get("show_time", True))
        self.show_cpu = bool(merged.get("show_cpu", False))
        self.show_memory = bool(merged.get("show_memory", False))
        self.show_network = bool(merged.get("show_network", False))
        self.status_update_interval_ms = int(merged.get("update_interval_ms", 1000))
        self._update_status_snapshot()
        self._update_auto_width(force=True)
        self._restart_status_timer()

    def apply_search_settings(self, search: dict[str, Any]) -> None:
        merged = dict(DEFAULT_SEARCH)
        merged.update(search or {})
        self.search = merged
        self.default_search_engine = str(merged.get("default_engine", DEFAULT_SEARCH["default_engine"]))
        if self.search_query:
            self.web_suggestions = self._build_web_suggestions(self.search_query)
        self._request_update()

    def apply_hotkey_settings(self, hotkey: dict[str, Any]) -> None:
        merged = dict(DEFAULT_HOTKEY)
        merged.update(hotkey or {})
        self.hotkey = merged
        enabled = bool(merged.get("search_hotkey_enabled", False))
        shortcut = str(merged.get("search_hotkey", DEFAULT_HOTKEY["search_hotkey"])).strip()
        changed = enabled != self.search_hotkey_enabled or shortcut != self.search_hotkey_text
        self.search_hotkey_enabled = enabled
        self.search_hotkey_text = shortcut or DEFAULT_HOTKEY["search_hotkey"]
        if changed:
            self._unregister_search_hotkey()
        if not self.search_hotkey_enabled:
            self.search_hotkey_error = ""
            return
        if self.search_hotkey_enabled:
            self._register_search_hotkey()

    def nativeEvent(self, event_type, message):  # noqa: N802
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and int(msg.wParam) == HOTKEY_ID_SEARCH:
                self._activate_search_hotkey()
                return True, 0
            if msg.message == WM_DEVICECHANGE:
                self._handle_device_change(int(msg.wParam), int(msg.lParam))
        except Exception:
            pass
        return super().nativeEvent(event_type, message)

    def _register_search_hotkey(self) -> None:
        if self.search_hotkey_registered or not self.search_hotkey_enabled:
            return
        parsed = _parse_hotkey_text(self.search_hotkey_text)
        if parsed is None:
            self.search_hotkey_error = "invalid"
            log_error("Hotkey register failed", ValueError("Invalid search hotkey"))
            return
        modifiers, vk = parsed
        try:
            ok = ctypes.windll.user32.RegisterHotKey(int(self.winId()), HOTKEY_ID_SEARCH, modifiers, vk)
        except Exception as exc:
            self.search_hotkey_error = "failed"
            log_error("Hotkey register failed", exc)
            return
        if not ok:
            self.search_hotkey_error = "failed"
            log_error("Hotkey register failed", OSError("RegisterHotKey returned false"))
            return
        self.search_hotkey_error = ""
        self.search_hotkey_registered = True

    def _unregister_search_hotkey(self) -> None:
        if not self.search_hotkey_registered:
            return
        try:
            ctypes.windll.user32.UnregisterHotKey(int(self.winId()), HOTKEY_ID_SEARCH)
        except Exception as exc:
            log_error("Hotkey unregister failed", exc)
        self.search_hotkey_registered = False

    def _activate_search_hotkey(self) -> None:
        if not self.isVisible():
            self.show()
        if self.state == STATE_HIDDEN:
            self.set_hidden(False)
        if self.state != STATE_EXPANDED or self.expand_target_state is not None:
            self.set_expanded(True)
            QTimer.singleShot(EXPAND_ANIMATION_DURATION_MS + 80, self._focus_search_box)
            return
        self._focus_search_box()

    def _focus_search_box(self) -> None:
        if self.state != STATE_EXPANDED:
            return
        self.search_edit.show()
        layout = self._last_visual_layout or self.compute_visual_layout()
        search_rect = self._expanded_rects(layout)["search"].translated(0, self._search_focus_offset())
        self._sync_search_edit_geometry(search_rect, True)
        self.search_focus_flow_phase = 0.0
        self.search_sweep_progress = 0.0
        self.animation_channels["search_sweep"].value = 0.0
        self._animate_channel("focus_ring", 1.0, FOCUS_RING_DURATION_MS, "out_cubic")
        self._animate_channel("search_sweep", 1.0, SEARCH_SWEEP_DURATION_MS, "out_cubic")
        self.search_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_edit.selectAll()
        self.search_focused = True
        self._request_update()

    def _handle_device_change(self, wparam: int, lparam: int) -> None:
        if wparam == DBT_DEVICEREMOVECOMPLETE:
            QTimer.singleShot(300, self._refresh_known_removable_drives)
            return
        if wparam != DBT_DEVICEARRIVAL:
            return
        candidates = self._drives_from_device_broadcast(lparam)
        QTimer.singleShot(700, lambda paths=candidates: self._process_drive_arrival(paths))

    def _drives_from_device_broadcast(self, lparam: int) -> list[str]:
        if not lparam:
            return []
        try:
            header = DEV_BROADCAST_HDR.from_address(lparam)
            if int(header.dbch_devicetype) != DBT_DEVTYP_VOLUME:
                return []
            volume = DEV_BROADCAST_VOLUME.from_address(lparam)
            mask = int(volume.dbcv_unitmask)
            return [f"{chr(65 + index)}:\\" for index in range(26) if mask & (1 << index)]
        except Exception:
            return []

    def _process_drive_arrival(self, candidate_paths: list[str]) -> None:
        current = self._current_removable_drives()
        candidates = set(candidate_paths) if candidate_paths else current - self._known_removable_drives
        self._known_removable_drives = current
        for drive_path in sorted(candidates):
            if drive_path not in current:
                continue
            self.handle_drive_inserted(drive_path, self._drive_display_name(drive_path))
            break

    def _refresh_known_removable_drives(self) -> None:
        self._known_removable_drives = self._current_removable_drives()

    @staticmethod
    def _current_removable_drives() -> set[str]:
        drives: set[str] = set()
        try:
            mask = ctypes.windll.kernel32.GetLogicalDrives()
            for index in range(26):
                if not (mask & (1 << index)):
                    continue
                root = f"{chr(65 + index)}:\\"
                try:
                    if ctypes.windll.kernel32.GetDriveTypeW(root) == DRIVE_REMOVABLE:
                        drives.add(root)
                except Exception:
                    continue
        except Exception:
            return drives
        return drives

    @staticmethod
    def _drive_display_name(drive_path: str) -> str:
        letter = drive_path.rstrip("\\")
        volume = ctypes.create_unicode_buffer(261)
        try:
            ok = ctypes.windll.kernel32.GetVolumeInformationW(
                drive_path,
                volume,
                len(volume),
                None,
                None,
                None,
                None,
                0,
            )
            label = volume.value.strip() if ok else ""
        except Exception:
            label = ""
        return f"{label} ({letter})" if label else letter

    def apply_clipboard_settings(self, clipboard: dict[str, Any]) -> None:
        self.url_open_prompt_enabled = bool(clipboard.get("url_open_prompt_enabled", True))
        if not self.url_open_prompt_enabled:
            self._clear_url_prompt()

    def _handle_search_text_changed(self, text: str) -> None:
        self.search_text = text
        self.search_query = text.strip()
        self.selected_search_index = 0
        self.search_scroll_offset = 0
        if self.search_query:
            self._set_feature_hovered(False)
        if not self.search_query:
            self.search_debounce_timer.stop()
            self.local_search_results = []
            self.web_suggestions = []
            self.search_is_loading = False
            self.apply_visual_geometry()
            self._request_update()
            return
        self.local_search_results = []
        self.search_is_loading = True
        self.web_suggestions = self._build_web_suggestions(self.search_query)
        if self.search_debounce_timer.isActive():
            self.search_debounce_timer.stop()
        self.search_debounce_timer.start(SEARCH_DEBOUNCE_MS)
        self.apply_visual_geometry()
        self._request_update()

    def _execute_search(self) -> None:
        self.execute_search_selection(allow_web_selection=False)

    def execute_search_selection(self, allow_web_selection: bool = True) -> bool:
        query = self.search_edit.text().strip()
        if not query:
            return False
        opened = False
        try:
            if self._search_results_active() and self.selected_search_index < len(self.local_search_results):
                opened = self._open_local_search_result(self.selected_search_index)
            elif self._search_results_active() and allow_web_selection:
                web_index = self.selected_search_index - len(self.local_search_results)
                if 0 <= web_index < len(self.web_suggestions):
                    opened = self._open_web_suggestion(web_index)
            if not opened:
                opened = open_query(query, self.default_search_engine)
        except Exception as exc:
            log_error("Search execute failed", exc)
            return False
        if opened:
            self.reset_search_after_execute()
        return opened

    def reset_search_after_execute(self) -> None:
        self.search_debounce_timer.stop()
        if self.search_future is not None and not self.search_future.done():
            self.search_future.cancel()
        self.search_future = None
        self.search_future_query = None
        self.search_result_poll_timer.stop()
        previous_block = self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(previous_block)
        self.search_text = ""
        self.search_query = ""
        self.local_search_results = []
        self.web_suggestions = []
        self.search_result_rects = []
        self.web_suggestion_rects = []
        self.selected_search_index = 0
        self.search_scroll_offset = 0
        self.search_is_loading = False
        self.search_focused = False
        self.search_edit.clearFocus()
        self.search_edit.hide()
        if self.state == STATE_EXPANDED or self.expand_target_state == STATE_EXPANDED:
            self.set_expanded(False)
        else:
            self._update_auto_width(force=True)
            self._request_update()

    def _refresh_search_results(self) -> None:
        query = self.search_edit.text().strip()
        if query != self.search_query:
            return
        if not query:
            self.local_search_results = []
            self.web_suggestions = []
        else:
            self.search_query_id += 1
            if self.search_future is not None and not self.search_future.done():
                self.search_future.cancel()
            self.search_future = self.search_executor.submit(search_local_results, query, SEARCH_MAX_LOCAL_RESULTS)
            self.search_future_query = (self.search_query_id, query)
            if not self.search_result_poll_timer.isActive():
                self.search_result_poll_timer.start()
            return
        self.selected_search_index = min(self.selected_search_index, max(0, self._search_selection_count() - 1))
        self.apply_visual_geometry()
        self._request_update()

    def _handle_search_results_ready(self, query_id: int, query: str, results: list) -> None:
        if query_id != self.search_query_id or query != self.search_query:
            return
        self.local_search_results = list(results)
        self.search_is_loading = False
        self.search_scroll_offset = 0
        self.web_suggestions = self._build_web_suggestions(query)
        self.selected_search_index = min(self.selected_search_index, max(0, self._search_selection_count() - 1))
        self.apply_visual_geometry()
        self._request_update()

    def _poll_search_future(self) -> None:
        if self.search_future is None or self.search_future_query is None:
            self.search_result_poll_timer.stop()
            return
        if not self.search_future.done():
            return
        query_id, query = self.search_future_query
        try:
            results = self.search_future.result()
        except Exception as exc:
            log_error("Search worker failed", exc)
            results = []
        self.search_future = None
        self.search_future_query = None
        self.search_result_poll_timer.stop()
        self._handle_search_results_ready(query_id, query, results)

    def _handle_clipboard_history_changed(self) -> None:
        if self.state == STATE_EXPANDED and self.current_view == VIEW_DETAIL and self._current_feature() == FEATURE_CLIPBOARD:
            self._request_update()

    def refresh_clipboard_history(self) -> None:
        self._handle_clipboard_history_changed()

    def _handle_file_hub_changed(self) -> None:
        if self.state == STATE_EXPANDED and self.current_view == VIEW_DETAIL and self._current_feature() == FEATURE_FILES:
            self._request_update()

    def _handle_favorites_changed(self) -> None:
        if self.state == STATE_EXPANDED and self.current_view == VIEW_DETAIL and self._current_feature() == FEATURE_FAVORITES:
            self._request_update()

    @staticmethod
    def _local_paths_from_mime(mime: QMimeData | None) -> list[str]:
        if mime is None or not mime.hasUrls():
            return []
        paths = []
        for url in mime.urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                if path and path not in paths:
                    paths.append(path)
        return paths

    def _start_file_drop_preview(self) -> None:
        self._clear_url_prompt()
        self.file_drop_active = True
        self.auto_hide_timer.stop()
        preview_width = self._screen_safe_body_width(max(220, self.base_body_width))
        preview_height = min(120, max(96, self.base_body_height))
        self._animate_shape_to(preview_width, preview_height, max(12, self.base_radius + 5), WIDTH_ANIMATION_DURATION_MS)
        self._request_update()

    def _cancel_file_drop_preview(self) -> None:
        if not self.file_drop_active:
            return
        self.file_drop_active = False
        self.file_drop_paths = []
        if self.state == STATE_COLLAPSED:
            self._update_auto_width(force=True)
            self._schedule_auto_hide_if_needed()
        self._request_update()

    def handle_copied_url(self, url: str) -> None:
        if not self._should_show_url_prompt(url):
            return
        self._hide_music_preview(immediate=True)
        self._clear_drive_prompt(update_width=False)
        self.url_prompt_active = True
        self.url_prompt_url = url
        self.last_prompted_url = url
        if self.url_prompt_timer.isActive():
            self.url_prompt_timer.stop()
        self.url_prompt_timer.start(URL_PROMPT_DURATION_MS)
        self.url_prompt_progress = 0.0
        self.animation_channels["url_prompt"].value = 0.0
        self._animate_channel("url_prompt", 1.0, URL_PROMPT_SHAKE_DURATION_MS, "out_cubic")
        self._update_auto_width(force=True, duration=WIDTH_ANIMATION_DURATION_MS)
        self._request_update()

    def _should_show_url_prompt(self, url: str) -> bool:
        parsed = urlparse(url)
        return (
            self.url_open_prompt_enabled
            and parsed.scheme in ("http", "https")
            and bool(parsed.netloc)
            and url != self.last_prompted_url
            and self.state == STATE_COLLAPSED
            and self.expand_target_state is None
            and not self.is_collapsed_hidden
            and not self._music_preview_draw_active()
            and not self.music_preview_requested
            and self.isVisible()
            and self.clipboard_manager is not None
            and self.clipboard_manager.enabled
            and not self.clipboard_manager.paused
        )

    def _clear_url_prompt(self, update_width: bool = True) -> None:
        if not self.url_prompt_active and not self.url_prompt_url:
            return
        self.url_prompt_active = False
        self.url_prompt_url = ""
        self.url_prompt_timer.stop()
        self.url_prompt_progress = 1.0
        if "url_prompt" in self.animation_channels:
            self.animation_channels["url_prompt"].active = False
            self.animation_channels["url_prompt"].value = 1.0
        if update_width:
            self._update_auto_width(force=True, duration=WIDTH_ANIMATION_DURATION_MS)
            self._request_update()

    def _open_url_prompt(self) -> None:
        url = self.url_prompt_url
        self._clear_url_prompt()
        if not url:
            return
        try:
            webbrowser.open(url)
        except Exception as exc:
            log_error("Copied URL open failed", exc)

    def handle_drive_inserted(self, drive_path: str, drive_name: str) -> None:
        if not self._should_show_drive_prompt(drive_path):
            return
        self._hide_music_preview(immediate=True)
        self.drive_prompt_active = True
        self.drive_prompt_path = drive_path
        self.drive_prompt_name = drive_name
        self.last_prompted_drive = drive_path
        self.last_prompted_drive_time = time.monotonic()
        if self.drive_prompt_timer.isActive():
            self.drive_prompt_timer.stop()
        self.drive_prompt_timer.start(DRIVE_PROMPT_DURATION_MS)
        self.url_prompt_progress = 0.0
        self.animation_channels["url_prompt"].value = 0.0
        self._animate_channel("url_prompt", 1.0, URL_PROMPT_SHAKE_DURATION_MS, "out_cubic")
        self._update_auto_width(force=True, duration=WIDTH_ANIMATION_DURATION_MS)
        self._request_update()

    def _should_show_drive_prompt(self, drive_path: str) -> bool:
        return (
            self.usb_drive_prompt_enabled
            and bool(drive_path)
            and not self.url_prompt_active
            and not self.drive_prompt_active
            and self.state == STATE_COLLAPSED
            and self.expand_target_state is None
            and not self.is_collapsed_hidden
            and self.isVisible()
            and not (
                drive_path == self.last_prompted_drive
                and time.monotonic() - self.last_prompted_drive_time < 20
            )
        )

    def _clear_drive_prompt(self, update_width: bool = True) -> None:
        if not self.drive_prompt_active and not self.drive_prompt_path:
            return
        self.drive_prompt_active = False
        self.drive_prompt_path = ""
        self.drive_prompt_name = ""
        self.drive_prompt_timer.stop()
        if not self.url_prompt_active:
            self.url_prompt_progress = 1.0
            self.animation_channels["url_prompt"].active = False
            self.animation_channels["url_prompt"].value = 1.0
        if update_width:
            self._update_auto_width(force=True, duration=WIDTH_ANIMATION_DURATION_MS)
            self._request_update()

    def _open_drive_prompt(self) -> None:
        path = self.drive_prompt_path
        self._clear_drive_prompt()
        if not path:
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception as exc:
            log_error("USB drive open failed", exc)

    def _music_preview_draw_active(self) -> bool:
        return (
            self.state == STATE_COLLAPSED
            and self.expand_target_state is None
            and not self.is_collapsed_hidden
            and not self.url_prompt_active
            and not self.drive_prompt_active
            and self.music_preview_progress > 0.001
        )

    def _music_preview_allowed(self) -> bool:
        return (
            self.music_preview_enabled
            and self.media_controller.available
            and self.state == STATE_COLLAPSED
            and self.expand_target_state is None
            and not self.is_collapsed_hidden
            and not self.url_prompt_active
            and not self.drive_prompt_active
            and self.isVisible()
        )

    def _maybe_start_music_preview(self) -> None:
        if not self._music_preview_allowed():
            return
        if not self.media_poll_timer.isActive():
            self.media_poll_timer.start()
        self._request_media_snapshot()
        if self.media_snapshot.has_media and self.media_snapshot.is_playing:
            self._show_music_preview()

    def _schedule_hide_music_preview(self) -> None:
        if self.music_preview_progress <= 0.001 and not self.music_preview_requested:
            return
        self._hide_music_preview()

    def _show_music_preview(self) -> None:
        if not self._music_preview_allowed():
            return
        self.music_preview_requested = True
        self._animate_channel("music_preview", 1.0, MUSIC_PREVIEW_ANIMATION_MS, "out_cubic")

    def _hide_music_preview(self, immediate: bool = False) -> None:
        self.music_preview_requested = False
        self.media_poll_timer.stop()
        self.music_button_hover = None
        if immediate or not self.animation_enabled:
            self.music_preview_progress = 0.0
            if "music_preview" in self.animation_channels:
                self.animation_channels["music_preview"].active = False
                self.animation_channels["music_preview"].value = 0.0
            self.apply_visual_geometry()
            self._request_update()
            return
        self._animate_channel("music_preview", 0.0, MUSIC_PREVIEW_ANIMATION_MS, "out_cubic")

    def _request_media_snapshot(self) -> None:
        if not self._music_preview_allowed() or self.media_future is not None:
            return
        self.media_future = self.media_executor.submit(self.media_controller.get_snapshot)
        if not self.media_result_poll_timer.isActive():
            self.media_result_poll_timer.start()

    def _poll_media_future(self) -> None:
        if self.media_future is None:
            self.media_result_poll_timer.stop()
            return
        if not self.media_future.done():
            return
        try:
            snapshot = self.media_future.result()
        except Exception as exc:
            log_error("Media result failed", exc)
            snapshot = MediaSnapshot(available=False)
        self.media_future = None
        self.media_result_poll_timer.stop()
        self.media_snapshot = snapshot
        self._prepare_media_cover_source(snapshot)
        if self._music_preview_allowed() and snapshot.has_media and snapshot.is_playing and self.underMouse():
            self._show_music_preview()
        elif self.music_preview_progress > 0.001:
            self._hide_music_preview()
        self._request_update()

    def _media_preview_rect(self) -> QRectF:
        layout = self._last_visual_layout or self.compute_visual_layout()
        return QRectF(layout.body_x, 0, layout.body_width, layout.body_height)

    def _handle_music_preview_click(self, pos: QPointF) -> bool:
        if not self._music_preview_draw_active() or self.music_preview_progress < 0.75:
            return False
        if not self._media_preview_rect().contains(pos):
            return False
        for action, rect in self.music_button_rects.items():
            if rect.contains(pos):
                if action == "prev" and not self.media_snapshot.can_previous:
                    return True
                if action == "next" and not self.media_snapshot.can_next:
                    return True
                if action == "play" and not (self.media_snapshot.can_pause if self.media_snapshot.is_playing else self.media_snapshot.can_play):
                    return True
                if action == "play":
                    self.media_executor.submit(self.media_controller.play_pause)
                elif action == "prev":
                    self.media_executor.submit(self.media_controller.previous)
                elif action == "next":
                    self.media_executor.submit(self.media_controller.next)
                QTimer.singleShot(250, self._request_media_snapshot)
                return True
        return pos.y() > self.base_body_height

    def _update_music_button_hover(self, pos: QPointF) -> None:
        if not self._music_preview_draw_active():
            if self.music_button_hover is not None:
                self.music_button_hover = None
                self._request_update()
            return
        hovered = None
        for action, rect in self.music_button_rects.items():
            if rect.contains(pos):
                hovered = action
                break
        if hovered != self.music_button_hover:
            self.music_button_hover = hovered
            self._request_update()

    def _update_feature_hover(self, pos: QPoint) -> None:
        hover = (
            self.state == STATE_EXPANDED
            and self.current_view == VIEW_HOME
            and not self._search_results_active()
            and self.expand_progress >= 0.96
            and self.content_fade_progress > 0.01
            and self.expanded_hit_rects.get("feature_area", QRectF()).contains(pos)
        )
        self._set_feature_hovered(hover)

    def _set_feature_hovered(self, hovered: bool) -> None:
        if self.feature_hovered == hovered:
            return
        self.feature_hovered = hovered
        if hovered:
            self.feature_pulse_phase = 0.0
        self._animate_channel(
            "feature_hover",
            1.0 if hovered else 0.0,
            FEATURE_HOVER_DURATION_MS,
            "out_cubic",
        )

    def apply_language_settings(self, language: str) -> None:
        self.language = language
        if self.state == STATE_COLLAPSED:
            self._update_auto_width(force=True)
        self.panel_placeholder_text = tr(self.language, "panel_placeholder")
        self.search_edit.setPlaceholderText(tr(self.language, "feature_search_placeholder"))
        self._request_update()

    def set_open_settings_callback(self, callback: Callable[[], None]) -> None:
        self.open_settings_callback = callback

    def toggle_expanded(self) -> None:
        if self.state == STATE_HIDDEN:
            return
        if self.expand_target_state == STATE_EXPANDED:
            self.set_expanded(False)
            return
        self.set_expanded(self.state != STATE_EXPANDED)

    def set_expanded(self, expanded: bool, schedule_auto_hide: bool = True) -> None:
        self.auto_hide_timer.stop()
        self.outside_click_timer.stop()
        if expanded:
            from_music_preview = self._music_preview_draw_active()
            start_layout = self.compute_visual_layout() if from_music_preview else None
            if from_music_preview:
                self.music_preview_requested = False
                self.media_poll_timer.stop()
                self.music_button_hover = None
                self.music_preview_progress = 0.0
                self.animation_channels["music_preview"].active = False
                self.animation_channels["music_preview"].value = 0.0
                if start_layout is not None:
                    self.current_body_width = float(start_layout.body_width)
                    self.current_body_height = float(start_layout.body_height)
                    self.current_radius = float(start_layout.radius)
                    self._shape_start = (
                        float(start_layout.body_width),
                        float(start_layout.body_height),
                        float(start_layout.radius),
                    )
                    self._path_cache_key = None
            else:
                self._hide_music_preview(immediate=True)
            self._clear_url_prompt()
            self._clear_drive_prompt()
            self.pending_hide_after_collapse = False
            if self.state == STATE_EXPANDED and self.expand_target_state is None:
                return
            self.current_view = VIEW_HOME
            self.search_focused = False
            self.search_edit.clearFocus()
            self.search_edit.hide()
            self.content_fade_progress = 0.0
            self.focus_ring_progress = 0.0
            self.search_sweep_progress = 0.0
            self.search_focus_flow_phase = 0.0
            self.feature_hovered = False
            self.feature_hover_progress = 0.0
            self.feature_pulse_phase = 0.0
            self.page_transition_progress = 1.0
            self.animation_channels["content"].value = 0.0
            self.animation_channels["content"].active = False
            self.animation_channels["focus_ring"].value = 0.0
            self.animation_channels["focus_ring"].active = False
            self.animation_channels["search_sweep"].value = 0.0
            self.animation_channels["search_sweep"].active = False
            self.animation_channels["feature_hover"].value = 0.0
            self.animation_channels["feature_hover"].active = False
            self.animation_channels["page"].value = 1.0
            self.animation_channels["page"].active = False
            self.expand_target_state = STATE_EXPANDED
            self.expand_direction = "expand"
            self.is_expanded = False
            self.is_collapsed_hidden = False
            self.animation_channels["width"].active = False
            self._animate_channel("hidden", 0.0, HIDDEN_ANIMATION_DURATION_MS, "smoother")
            self._animate_channel("expand", 1.0, EXPAND_ANIMATION_DURATION_MS, "linear")
            self._animate_shape_to(
                *self._expanded_target_metrics(),
                EXPAND_ANIMATION_DURATION_MS,
            )
            if not self.animation_enabled or not self.isVisible():
                self._finish_expand_transition()
            return

        if self.state == STATE_COLLAPSED and self.expand_target_state is None:
            return

        self.is_expanded = False
        self._clear_url_prompt()
        self._clear_drive_prompt()
        self.search_focused = False
        self.search_edit.clearFocus()
        self.search_edit.hide()
        self.content_fade_progress = max(0.0, min(1.0, self.content_fade_progress))
        self.focus_ring_progress = 0.0
        self.search_sweep_progress = 0.0
        self.search_focus_flow_phase = 0.0
        self.feature_hovered = False
        self.feature_hover_progress = 0.0
        self.feature_pulse_phase = 0.0
        self._animate_channel("content", 0.0, CONTENT_EXIT_DURATION_MS, "out_cubic")
        self.animation_channels["focus_ring"].active = False
        self.animation_channels["focus_ring"].value = 0.0
        self.animation_channels["search_sweep"].active = False
        self.animation_channels["search_sweep"].value = 0.0
        self.animation_channels["feature_hover"].active = False
        self.animation_channels["feature_hover"].value = 0.0
        self.expand_target_state = STATE_COLLAPSED
        self.expand_direction = "collapse"
        self.animation_channels["hidden"].active = False
        self.hidden_progress = 0.0
        self.animation_channels["hidden"].value = 0.0
        self._animate_channel("expand", 0.0, COLLAPSE_ANIMATION_DURATION_MS, "linear")
        self._update_status_snapshot()
        collapsed_width = self._calculate_auto_body_width()
        self.auto_body_width_target = collapsed_width
        self._animate_shape_to(
            collapsed_width,
            self.base_body_height,
            self.base_radius,
            COLLAPSE_ANIMATION_DURATION_MS,
        )
        self._schedule_auto_hide_after_collapse = schedule_auto_hide
        if not self.animation_enabled or not self.isVisible():
            self._finish_collapse_transition()

    def hide_after_collapse(self) -> None:
        self.auto_hide_timer.stop()
        self.outside_click_timer.stop()
        if not self.animation_enabled or not self.isVisible():
            self.pending_hide_after_collapse = False
            self._collapse_immediately()
            self.set_hidden(True)
            return
        self.pending_hide_after_collapse = True
        self.set_expanded(False, schedule_auto_hide=False)

    def toggle_hidden(self) -> None:
        self.set_hidden(not self.is_collapsed_hidden)

    def set_hidden(self, hidden: bool) -> None:
        self.auto_hide_timer.stop()
        self.outside_click_timer.stop()
        if hidden and (self.state == STATE_EXPANDED or self.expand_target_state is not None):
            self.pending_hide_after_collapse = True
            if not self.animation_enabled or not self.isVisible():
                self.pending_hide_after_collapse = False
                self._collapse_immediately()
            else:
                self.set_expanded(False, schedule_auto_hide=False)
                return
        else:
            self.pending_hide_after_collapse = False
        self.is_collapsed_hidden = hidden
        self.state = STATE_HIDDEN if hidden else STATE_COLLAPSED
        self.expand_target_state = None
        self.expand_direction = None
        if hidden:
            self._clear_url_prompt()
            self._hide_music_preview(immediate=True)
            self.search_edit.clearFocus()
            self.search_edit.hide()
        self._restart_status_timer()
        target = 1.0 if hidden else 0.0
        self._animate_channel("hidden", target, HIDDEN_ANIMATION_DURATION_MS, "smoother")
        if hidden:
            self._update_auto_width(force=True)
        else:
            self._schedule_auto_hide_if_needed()

    def paintEvent(self, event) -> None:  # noqa: N802
        paint_started = time.perf_counter()
        if DEBUG_PERFORMANCE:
            self._paint_count += 1
        self._last_visual_layout = self.compute_visual_layout()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        self._clear_transparent_background(painter)
        path = self._body_path()

        if self.shadow_enabled:
            expanded_shadow = self.state == STATE_EXPANDED or self.expand_progress > 0.35
            deform = self._expand_soft_deform()
            shadow_stage = staged_expand_shadow(self.expand_progress) if self.expand_direction == "expand" else 1.0
            shadow_intensity = 0.9 + shadow_stage * 0.1 + deform["shadow_boost"] + max(self.hover_progress, self.focus_ring_progress) * 0.1
            self.draw_island_shadow(painter, path, expanded=expanded_shadow, intensity=shadow_intensity)
        painter.fillPath(path, self.body_color)
        self._paint_top_guard(painter, self._last_visual_layout)

        self._paint_content(painter)
        painter.end()
        if DEBUG_PERFORMANCE:
            self._paint_total_ms += (time.perf_counter() - paint_started) * 1000

    def _clear_transparent_background(self, painter: QPainter) -> None:
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.restore()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    def _paint_top_guard(self, painter: QPainter, layout: VisualLayout) -> None:
        if (
            self.expand_target_state is None
            and not self.animation_channels["width"].active
        ):
            return
        visual_rect = self._visual_body_rect(layout)
        painter.fillRect(QRectF(visual_rect.x(), 0, visual_rect.width(), TOP_GUARD_HEIGHT), self.body_color)

    def compute_visual_layout(self) -> VisualLayout:
        metrics = self.responsive_metrics
        max_body_width = max(1, metrics.expanded_width, metrics.collapsed_max_width)
        body_width = int(round(self.current_body_width))
        visible_height = int(round(self._visible_body_height()))
        radius = int(round(self.current_radius))
        if self._music_preview_draw_active():
            p = max(0.0, min(1.0, self.music_preview_progress))
            preview_width = min(MUSIC_PREVIEW_WIDTH, max_body_width)
            body_width = int(round(max(body_width, preview_width * p + body_width * (1.0 - p))))
            visible_height = int(round(visible_height + (MUSIC_PREVIEW_HEIGHT - visible_height) * p))
            radius = max(radius, int(round((radius + 7) * p + radius * (1.0 - p))))
        body_width = int(max(1, min(body_width, max_body_width)))
        radius = int(round(max(0, min(radius, visible_height / 2))))
        window_width = body_width + SHADOW_MARGIN_X * 2
        body_x = SHADOW_MARGIN_X
        extra_height = 0
        if self._web_suggestions_visible():
            extra_height = min(
                SEARCH_WEB_PANEL_HEIGHT,
                max(0, metrics.screen_height - visible_height - SHADOW_MARGIN_BOTTOM),
            )
        return VisualLayout(
            body_width=max(1, body_width),
            body_height=max(1, visible_height),
            radius=max(0, radius),
            window_width=max(1, window_width),
            window_height=max(1, visible_height + SHADOW_MARGIN_BOTTOM + extra_height),
            body_x=max(0, body_x),
        )

    def apply_visual_geometry(self, layout: VisualLayout | None = None) -> VisualLayout:
        layout = layout or self.compute_visual_layout()
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            target_x = 0
            target_y = 0
        else:
            geometry = screen.geometry()
            available_width = int(max(1, geometry.width()))
            safe_window_width = int(min(layout.window_width, available_width))
            target_x = int(geometry.x() + max(0, (available_width - safe_window_width) / 2))
            target_y = int(geometry.y())
        target_x += self._prompt_shake_offset()

        if (
            self.x() != target_x
            or self.y() != target_y
            or self.width() != layout.window_width
            or self.height() != layout.window_height
        ):
            self.setGeometry(target_x, target_y, layout.window_width, layout.window_height)
        self.window_width = layout.window_width
        self.window_height = layout.window_height
        self._last_visual_layout = layout
        return layout

    def _prompt_shake_offset(self) -> int:
        if not (self.url_prompt_active or self.drive_prompt_active):
            return 0
        t = max(0.0, min(1.0, self.url_prompt_progress))
        return int(round(math.sin(t * math.pi * 4) * (1.0 - t) * URL_PROMPT_SHAKE_PX))

    def _body_path(self) -> QPainterPath:
        layout = self._last_visual_layout or self.compute_visual_layout()
        visual_rect = self._visual_body_rect(layout)
        cache_key = (
            round(visual_rect.x(), 2),
            round(visual_rect.width(), 2),
            round(visual_rect.height(), 2),
            layout.radius,
        )
        if cache_key != self._path_cache_key:
            self._path_cache = build_notch_path(visual_rect, float(layout.radius))
            self._path_cache_key = cache_key
        return self._path_cache

    def _expand_soft_deform(self) -> dict[str, float]:
        if (
            self.expand_direction != "expand"
            or self.expand_target_state != STATE_EXPANDED
            or not self.animation_channels["expand"].active
        ):
            return {"width_extra": 0.0, "height_extra": 0.0, "bottom_stretch": 0.0, "shadow_boost": 0.0}
        return expand_soft_deform(self.expand_progress)

    def _visual_body_rect(self, layout: VisualLayout) -> QRectF:
        deform = self._expand_soft_deform()
        width_extra = min(5.0, max(0.0, deform["width_extra"]))
        height_extra = min(4.0, max(0.0, deform["height_extra"] + deform["bottom_stretch"] * 0.35))
        return QRectF(
            layout.body_x - width_extra / 2,
            0,
            layout.body_width + width_extra,
            layout.body_height + height_extra,
        )

    def _visible_body_height(self) -> float:
        handle_height = float(HIDDEN["handle_height"])
        return self.current_body_height + (handle_height - self.current_body_height) * self.hidden_progress

    def draw_island_shadow(
        self,
        painter: QPainter,
        body_path: QPainterPath,
        expanded: bool = False,
        intensity: float = 1.0,
    ) -> None:
        hidden_scale = 1.0 - self.hidden_progress * 0.35
        animation_scale = 0.86 if self.expand_target_state is not None else 1.0
        safe_intensity = max(0.0, min(1.1, intensity)) * hidden_scale * animation_scale
        layers = ((1, 26), (2, 18), (3, 12)) if expanded else ((1, 22), (2, 16), (3, 10))
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setClipRect(QRectF(0, 1, self.width(), self.height() - 1))
        for dy, alpha in layers:
            effective_alpha = int(alpha * safe_intensity)
            if effective_alpha <= 0:
                continue
            painter.save()
            painter.translate(0, dy)
            painter.fillPath(body_path, QColor(0, 0, 0, effective_alpha))
            painter.restore()
        painter.restore()

    def _paint_content(self, painter: QPainter) -> None:
        opacity = max(0.0, min(1.0, 1.0 - self.hidden_progress * 1.4))
        if opacity <= 0.02:
            return

        if self.file_drop_active and self.state == STATE_COLLAPSED:
            self._paint_file_drop_prompt(painter, opacity)
            return

        collapsed_opacity = opacity * self._collapsed_content_alpha()
        expanded_opacity = opacity * max(
            self._expanded_header_alpha(),
            self._expanded_main_alpha(),
            self._expanded_search_alpha(),
        )
        if collapsed_opacity > 0.02:
            self._paint_collapsed_content(painter, collapsed_opacity)
        if self._music_preview_draw_active() and self.music_preview_progress > 0.02:
            self._paint_music_preview(painter, opacity * self.music_preview_progress)
        if expanded_opacity > 0.02:
            self._paint_expanded_content(painter, expanded_opacity)

    def _collapse_progress(self) -> float:
        if self.expand_direction != "collapse":
            return 0.0
        return 1.0 - max(0.0, min(1.0, self.expand_progress))

    def _collapsed_content_alpha(self) -> float:
        t = max(0.0, min(1.0, self.expand_progress))
        if self.expand_direction == "expand" or self.expand_target_state == STATE_EXPANDED:
            return 1.0 - ease_out_cubic(remap_progress(t, 0.00, 0.12))
        if self.expand_direction == "collapse" or self.expand_target_state == STATE_COLLAPSED:
            return ease_out_cubic(remap_progress(self._collapse_progress(), 0.86, 1.00))
        return 1.0 if self.state == STATE_COLLAPSED else 0.0

    def _expanded_header_alpha(self) -> float:
        if self.expand_direction == "collapse" or self.expand_target_state == STATE_COLLAPSED:
            return 1.0 - ease_out_cubic(remap_progress(self._collapse_progress(), 0.06, 0.26))
        if self.expand_direction == "expand" or self.expand_target_state == STATE_EXPANDED:
            return staged_expand_header_alpha(self.expand_progress)
        return 1.0 if self.state == STATE_EXPANDED else 0.0

    def _expanded_main_alpha(self) -> float:
        if self.expand_direction == "collapse" or self.expand_target_state == STATE_COLLAPSED:
            return 1.0 - ease_out_cubic(remap_progress(self._collapse_progress(), 0.00, 0.18))
        if self.expand_direction == "expand" or self.expand_target_state == STATE_EXPANDED:
            return min(self.content_fade_progress, staged_expand_content_alpha(self.expand_progress))
        return self.content_fade_progress if self.state == STATE_EXPANDED else 0.0

    def _expanded_search_alpha(self) -> float:
        if self.expand_direction == "collapse" or self.expand_target_state == STATE_COLLAPSED:
            return 1.0 - ease_out_cubic(remap_progress(self._collapse_progress(), 0.00, 0.16))
        if self.expand_direction == "expand" or self.expand_target_state == STATE_EXPANDED:
            return min(self.content_fade_progress, staged_expand_search_alpha(self.expand_progress))
        return self.content_fade_progress if self.state == STATE_EXPANDED else 0.0

    def _panel_alpha(self, start: float) -> float:
        if self.expand_direction == "collapse":
            fade_out_end = 0.80 if start < 0.60 else 0.84
            if self.expand_progress <= fade_out_end:
                return 0.0
            return ease_out_cubic((self.expand_progress - fade_out_end) / max(0.001, 1.0 - fade_out_end))
        if self.expand_progress <= start:
            return 0.0
        return ease_out_cubic((self.expand_progress - start) / max(0.001, 1.0 - start))

    def _panel_content_offset(self, alpha: float) -> float:
        return (1.0 - alpha) * 8.0

    def _search_focus_offset(self) -> float:
        return search_focus_lift_offset(self.focus_ring_progress)

    def _expanded_radius(self) -> int:
        return int(self.responsive_metrics.expanded_radius)

    def _sync_search_edit_geometry(self, rect: QRectF, visible: bool) -> None:
        self._search_edit_rect = rect
        if not visible or self.state != STATE_EXPANDED:
            if self.search_edit.isVisible():
                self.search_edit.hide()
            return
        edit_rect = QRectF(rect.x() + 48, rect.y() + 6, rect.width() - 66, rect.height() - 12)
        geometry = edit_rect.toAlignedRect()
        if self.search_edit.geometry() != geometry:
            self.search_edit.setGeometry(geometry)
        placeholder = tr(self.language, "feature_search_placeholder")
        if self.search_edit.placeholderText() != placeholder:
            self.search_edit.setPlaceholderText(placeholder)
        if not self.search_edit.isVisible():
            self.search_edit.show()
        self.search_edit.raise_()

    def _paint_collapsed_content(self, painter: QPainter, opacity: float) -> None:
        if self.url_prompt_active:
            self._paint_url_prompt_content(painter, opacity)
            return
        if self.drive_prompt_active:
            self._paint_drive_prompt_content(painter, opacity)
            return
        layout = self._last_visual_layout or self.compute_visual_layout()
        painter.save()
        painter.setOpacity(opacity)
        painter.translate(0, self.press_progress - self.hover_progress)

        body_x = layout.body_x
        center_y = (self.base_body_height if self._music_preview_draw_active() else layout.body_height) / 2
        horizontal_padding = 22
        brightness = 232 + int(self.hover_progress * 20) - int(self.press_progress * 8)
        text_color = QColor(brightness, brightness, brightness)
        dot_base = 236 + int(self.hover_progress * 17) - int(self.press_progress * 8)
        dot_color = QColor(dot_base, dot_base, min(255, dot_base + 2))

        dot_radius = 3
        dot_center_x = body_x + horizontal_padding + dot_radius
        painter.setBrush(dot_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(dot_center_x - dot_radius, center_y - dot_radius, 6, 6))

        painter.setFont(self.brand_font)
        painter.setPen(text_color)
        brand = self.brand_text
        brand_x = dot_center_x + dot_radius + 10
        brand_y = int(center_y + (self.brand_metrics.ascent() - self.brand_metrics.descent()) / 2)
        painter.drawText(brand_x, brand_y, brand)

        status_available_width = max(0, int(layout.body_width - self._left_content_width() - 22 * 2 - 18))
        status_items = self._visible_status_items(status_available_width)
        if status_items:
            self._draw_status_items(painter, status_items, body_x + layout.body_width - horizontal_padding, center_y, text_color)
        painter.restore()

    def _paint_music_preview(self, painter: QPainter, opacity: float) -> None:
        snapshot = self.media_snapshot
        layout = self._last_visual_layout or self.compute_visual_layout()
        body_x = layout.body_x
        if layout.body_height < self.base_body_height + 26:
            return
        painter.save()
        painter.setOpacity(max(0.0, min(1.0, opacity)))
        painter.setClipRect(QRectF(body_x, self.base_body_height - 1, layout.body_width, layout.body_height - self.base_body_height + 1))

        album_size = 56
        album_radius = 12
        cover_rect = QRectF(
            int(body_x + 22),
            int(self.base_body_height + 16),
            album_size,
            album_size,
        )
        if cover_rect.bottom() > layout.body_height - 12:
            cover_rect.moveTop(int(max(self.base_body_height + 8, layout.body_height - album_size - 12)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 18))
        painter.drawRoundedRect(cover_rect, album_radius, album_radius)

        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        pixmap = self._media_cover_pixmap(album_size, album_radius)
        album_clip_path = QPainterPath()
        album_clip_path.addRoundedRect(cover_rect, album_radius, album_radius)
        painter.save()
        painter.setClipPath(album_clip_path)
        if pixmap is not None and not pixmap.isNull():
            painter.drawPixmap(cover_rect.toAlignedRect(), pixmap)
        else:
            painter.drawPixmap(cover_rect.toAlignedRect(), self._default_media_cover_pixmap(album_size, album_radius))
        painter.restore()

        text_x = cover_rect.right() + 14
        button_area_w = 108
        text_w = max(80, int(body_x + layout.body_width - text_x - button_area_w - 28))
        title = snapshot.title.strip() or tr(self.language, "media_now_playing")
        artist = snapshot.artist.strip() or snapshot.album.strip() or snapshot.app_name.strip() or tr(self.language, "media_unknown_artist")
        painter.setFont(self.brand_font)
        painter.setPen(QColor(245, 245, 247))
        painter.drawText(
            QRectF(text_x, cover_rect.y() + 8, text_w, 22),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.brand_metrics.elidedText(title, Qt.TextElideMode.ElideRight, text_w),
        )
        painter.setFont(self.status_font)
        painter.setPen(QColor(170, 170, 180))
        painter.drawText(
            QRectF(text_x, cover_rect.y() + 34, text_w, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.status_metrics.elidedText(artist, Qt.TextElideMode.ElideRight, text_w),
        )

        button_y = cover_rect.y() + 14
        button_x = body_x + layout.body_width - 116
        self.music_button_rects = {
            "prev": QRectF(button_x, button_y, 28, 28),
            "play": QRectF(button_x + 36, button_y - 4, 36, 36),
            "next": QRectF(button_x + 82, button_y, 28, 28),
        }
        for action, rect in self.music_button_rects.items():
            enabled = True
            if action == "prev":
                enabled = snapshot.can_previous
            elif action == "next":
                enabled = snapshot.can_next
            elif action == "play":
                enabled = snapshot.can_pause if snapshot.is_playing else snapshot.can_play
            self._draw_music_button(
                painter,
                rect,
                action,
                hovered=self.music_button_hover == action and enabled,
                playing=snapshot.is_playing,
                enabled=enabled,
            )
        painter.restore()

    def _prepare_media_cover_source(self, snapshot: MediaSnapshot) -> None:
        data = snapshot.thumbnail
        if not data:
            self.media_cover_source_pixmap = None
            self.media_cover_source_key = None
            self.media_cover_render_pixmap = None
            self.media_cover_render_key = None
            return
        key = (snapshot.title, snapshot.artist, snapshot.album, len(data), hash(data))
        if key == self.media_cover_source_key:
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self.media_cover_source_pixmap = pixmap
            self.media_cover_source_key = key
        else:
            self.media_cover_source_pixmap = None
            self.media_cover_source_key = None
        self.media_cover_render_pixmap = None
        self.media_cover_render_key = None

    def _media_cover_pixmap(self, logical_size: int, radius: int) -> QPixmap | None:
        source = self.media_cover_source_pixmap
        if source is None or source.isNull():
            return None
        dpr = max(1.0, float(self.devicePixelRatioF()))
        key = (self.media_cover_source_key, int(logical_size), int(radius), round(dpr, 2))
        if key != self.media_cover_render_key or self.media_cover_render_pixmap is None:
            self.media_cover_render_pixmap = self._make_rounded_album_art(source, logical_size, radius, dpr)
            self.media_cover_render_key = key
        return self.media_cover_render_pixmap

    def _make_rounded_album_art(self, source: QPixmap, logical_size: int, radius: int, dpr: float) -> QPixmap:
        target_px = max(1, int(round(logical_size * dpr)))
        result = QPixmap(target_px, target_px)
        result.fill(Qt.GlobalColor.transparent)
        source_w = max(1, source.width())
        source_h = max(1, source.height())
        scale = max(target_px / source_w, target_px / source_h)
        draw_w = source_w * scale
        draw_h = source_h * scale
        target_rect = QRectF((target_px - draw_w) / 2, (target_px - draw_h) / 2, draw_w, draw_h)

        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        clip_path = QPainterPath()
        clip_path.addRoundedRect(QRectF(0, 0, target_px, target_px), radius * dpr, radius * dpr)
        painter.setClipPath(clip_path)
        painter.drawPixmap(target_rect, source, QRectF(0, 0, source_w, source_h))
        painter.end()
        result.setDevicePixelRatio(dpr)
        return result

    def _default_media_cover_pixmap(self, logical_size: int, radius: int) -> QPixmap:
        dpr = max(1.0, float(self.devicePixelRatioF()))
        key = (int(logical_size), int(radius), round(dpr, 2))
        if self.default_media_cover_pixmap is not None and self.default_media_cover_key == key:
            return self.default_media_cover_pixmap

        target_px = max(1, int(round(logical_size * dpr)))
        pixmap = QPixmap(target_px, target_px)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        rect = QRectF(0, 0, target_px, target_px)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, QColor(96, 165, 250, 150))
        gradient.setColorAt(1.0, QColor(167, 139, 250, 130))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        inset = 3 * dpr
        painter.drawRoundedRect(rect.adjusted(inset, inset, -inset, -inset), radius * dpr, radius * dpr)
        painter.setPen(QPen(QColor(245, 245, 247, 220), 3 * dpr, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        x = (rect.center().x() - 5 * dpr)
        y = (rect.center().y() - 10 * dpr)
        painter.drawLine(QPointF(x, y), QPointF(x, y + 22 * dpr))
        painter.drawLine(QPointF(x, y), QPointF(x + 15 * dpr, y - 4 * dpr))
        painter.setBrush(QColor(245, 245, 247, 220))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(x - 8 * dpr, y + 17 * dpr, 12 * dpr, 10 * dpr))
        painter.end()
        pixmap.setDevicePixelRatio(dpr)
        self.default_media_cover_pixmap = pixmap
        self.default_media_cover_key = key
        return pixmap

    def _draw_music_button(self, painter: QPainter, rect: QRectF, action: str, hovered: bool, playing: bool, enabled: bool = True) -> None:
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 24 if hovered else (12 if enabled else 5)))
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        icon_color = QColor(245, 245, 247, 230 if enabled else 78)
        painter.setBrush(icon_color)
        painter.setPen(Qt.PenStyle.NoPen)
        cx = rect.center().x()
        cy = rect.center().y()
        if action == "play" and playing:
            painter.drawRoundedRect(QRectF(cx - 7, cy - 9, 5, 18), 2, 2)
            painter.drawRoundedRect(QRectF(cx + 2, cy - 9, 5, 18), 2, 2)
        elif action == "play":
            path = QPainterPath()
            path.moveTo(cx - 5, cy - 10)
            path.lineTo(cx + 9, cy)
            path.lineTo(cx - 5, cy + 10)
            path.closeSubpath()
            painter.fillPath(path, icon_color)
        else:
            path = QPainterPath()
            if action == "prev":
                painter.drawRoundedRect(QRectF(cx - 8, cy - 9, 3, 18), 1, 1)
                path.moveTo(cx - 5, cy)
                path.lineTo(cx + 7, cy - 9)
                path.lineTo(cx + 7, cy + 9)
            else:
                path.moveTo(cx + 5, cy)
                path.lineTo(cx - 7, cy - 9)
                path.lineTo(cx - 7, cy + 9)
            path.closeSubpath()
            painter.fillPath(path, icon_color)
            if action == "next":
                painter.drawRoundedRect(QRectF(cx + 5, cy - 9, 3, 18), 1, 1)
        painter.restore()

    def _paint_url_prompt_content(self, painter: QPainter, opacity: float) -> None:
        layout = self._last_visual_layout or self.compute_visual_layout()
        painter.save()
        painter.setOpacity(opacity)
        painter.translate(0, self.press_progress * 0.5)
        body_x = layout.body_x
        center_y = layout.body_height / 2
        horizontal_padding = 20
        text_color = QColor(245, 245, 247)
        dot_color = QColor(120, 205, 255)

        dot_radius = 3
        dot_center_x = body_x + horizontal_padding + dot_radius
        painter.setBrush(dot_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(dot_center_x - dot_radius, center_y - dot_radius, 6, 6))

        title = tr(self.language, "url_prompt_title")
        action = tr(self.language, "url_prompt_action")
        title_x = dot_center_x + dot_radius + 10
        action_w = self.status_metrics.horizontalAdvance(action)
        title_available = int(layout.body_width - (title_x - body_x) - action_w - 42)

        painter.setFont(self.brand_font)
        painter.setPen(text_color)
        title_text = self.brand_metrics.elidedText(title, Qt.TextElideMode.ElideRight, max(30, title_available))
        title_y = int(center_y + (self.brand_metrics.ascent() - self.brand_metrics.descent()) / 2)
        painter.drawText(int(title_x), title_y, title_text)

        painter.setFont(self.status_font)
        painter.setPen(QColor(160, 220, 255))
        action_y = int(center_y + (self.status_metrics.ascent() - self.status_metrics.descent()) / 2)
        painter.drawText(int(body_x + layout.body_width - horizontal_padding - action_w), action_y, action)
        painter.restore()

    def _paint_drive_prompt_content(self, painter: QPainter, opacity: float) -> None:
        layout = self._last_visual_layout or self.compute_visual_layout()
        painter.save()
        painter.setOpacity(opacity)
        painter.translate(0, self.press_progress * 0.5)
        body_x = layout.body_x
        center_y = layout.body_height / 2
        horizontal_padding = 20
        dot_radius = 3
        dot_center_x = body_x + horizontal_padding + dot_radius
        painter.setBrush(QColor(120, 210, 255))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(dot_center_x - dot_radius, center_y - dot_radius, 6, 6))

        title = tr(self.language, "drive_prompt_title").format(name=self.drive_prompt_name or self.drive_prompt_path)
        action = tr(self.language, "drive_prompt_action")
        title_x = dot_center_x + dot_radius + 10
        action_w = self.status_metrics.horizontalAdvance(action)
        title_available = int(layout.body_width - (title_x - body_x) - action_w - 42)

        painter.setFont(self.brand_font)
        painter.setPen(QColor(245, 245, 247))
        title_text = self.brand_metrics.elidedText(title, Qt.TextElideMode.ElideRight, max(30, title_available))
        title_y = int(center_y + (self.brand_metrics.ascent() - self.brand_metrics.descent()) / 2)
        painter.drawText(int(title_x), title_y, title_text)

        painter.setFont(self.status_font)
        painter.setPen(QColor(160, 220, 255))
        action_y = int(center_y + (self.status_metrics.ascent() - self.status_metrics.descent()) / 2)
        painter.drawText(int(body_x + layout.body_width - horizontal_padding - action_w), action_y, action)
        painter.restore()

    def _paint_file_drop_prompt(self, painter: QPainter, opacity: float) -> None:
        layout = self._last_visual_layout or self.compute_visual_layout()
        painter.save()
        painter.setOpacity(opacity)
        body_x = layout.body_x
        center_x = body_x + layout.body_width / 2
        center_y = layout.body_height / 2
        pulse = 0.5 + 0.5 * math.sin(time.monotonic() * math.tau / 1.8)
        icon_rect = QRectF(center_x - 18, center_y - 31, 36, 30)
        painter.setPen(QPen(QColor(110, 210, 255, 190 + int(40 * pulse)), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(QColor(48, 120, 150, 42))
        folder = QPainterPath()
        folder.addRoundedRect(icon_rect.adjusted(0, 8, 0, 0), 7, 7)
        painter.drawPath(folder)
        painter.drawLine(int(icon_rect.x() + 6), int(icon_rect.y() + 8), int(icon_rect.x() + 15), int(icon_rect.y() + 2))
        painter.drawLine(int(icon_rect.x() + 15), int(icon_rect.y() + 2), int(icon_rect.x() + 24), int(icon_rect.y() + 8))
        text = tr(self.language, "file_drop_prompt")
        painter.setFont(self.feature_desc_font)
        painter.setPen(QColor(236, 248, 255))
        text_w = self.feature_desc_metrics.horizontalAdvance(text)
        painter.drawText(int(center_x - text_w / 2), int(center_y + 27), text)
        painter.restore()

    def _paint_expanded_content(self, painter: QPainter, opacity: float) -> None:
        layout = self._last_visual_layout or self.compute_visual_layout()
        painter.save()
        painter.setOpacity(opacity)
        painter.translate(0, self.press_progress * 0.6)

        rects = self._expanded_rects(layout)
        content_alpha = self._expanded_main_alpha()
        search_alpha = self._expanded_search_alpha()
        content_visible = content_alpha > 0.01
        search_visible = search_alpha > 0.35
        self.expanded_hit_rects = {
            "header": rects["header"],
            "feature_area": rects["feature_area"],
            "search": rects["search"],
            "back": rects["back"],
            "settings": rects["settings"],
        }
        self.feature_hit_rect = rects["feature_area"]
        self.feature_dot_rects = []
        self.action_button_rects = []
        self.clipboard_item_rects = []
        self.file_item_rects = []
        self.favorite_item_rects = []
        self.search_result_rects = []
        self.web_suggestion_rects = []

        header_alpha = self._expanded_header_alpha()
        if header_alpha > 0.02:
            painter.save()
            painter.setOpacity(opacity * header_alpha)
            self._paint_expanded_header(painter, layout, rects)
            painter.restore()

        if content_alpha > 0.02:
            painter.save()
            painter.setOpacity(opacity * content_alpha * self.page_transition_progress)
            painter.translate(0, self._panel_content_offset(content_alpha) + (1.0 - self.page_transition_progress) * 6.0)
            self._paint_feature_area(painter, layout, rects)
            painter.restore()

        if search_alpha > 0.02:
            search_rect = rects["search"].translated(
                0,
                self._panel_content_offset(search_alpha) + self._search_focus_offset(),
            )
            self._sync_search_edit_geometry(search_rect, search_visible)
            painter.save()
            painter.setOpacity(opacity * search_alpha)
            self._paint_floating_search(painter, search_rect)
            painter.restore()
            if self._web_suggestions_visible():
                painter.save()
                painter.setOpacity(opacity * search_alpha)
                self._paint_web_suggestions(painter, search_rect)
                painter.restore()
        else:
            self._sync_search_edit_geometry(rects["search"], False)
        painter.restore()

    def _expanded_rects(self, layout: VisualLayout) -> dict[str, QRectF]:
        body_x = layout.body_x
        body_w = layout.body_width
        body_h = layout.body_height
        metrics = self.responsive_metrics
        search_w = int(round(min(metrics.search_width, max(1, body_w - 80))))
        search_x = int(round(body_x + (body_w - search_w) / 2))
        search_h = int(metrics.search_height)
        search_bottom_margin = int(metrics.search_bottom_margin)
        search_y = int(round(max(HEADER_HEIGHT + 90.0, body_h - search_bottom_margin - search_h)))
        feature_bottom = int(round(max(HEADER_HEIGHT + 130.0, search_y - 22.0)))
        return {
            "header": QRectF(body_x, 0, body_w, HEADER_HEIGHT),
            "feature_area": QRectF(body_x + 34, HEADER_HEIGHT + 16, max(1, body_w - 68), max(80, feature_bottom - HEADER_HEIGHT - 16)),
            "search": QRectF(search_x, search_y, search_w, search_h),
            "back": QRectF(body_x + 18, 13, 34, 30),
            "settings": QRectF(body_x + body_w - 49, 13, 32, 30),
        }

    def _paint_expanded_header(self, painter: QPainter, layout: VisualLayout, rects: dict[str, QRectF]) -> None:
        body_x = layout.body_x
        body_w = layout.body_width
        painter.setPen(self.separator_color)
        painter.drawLine(int(body_x + 22), HEADER_HEIGHT, int(body_x + body_w - 22), HEADER_HEIGHT)

        if self.current_view == VIEW_DETAIL:
            back_rect = rects["back"]
            painter.setPen(QPen(self.panel_title_color, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            cy = back_rect.center().y()
            painter.drawLine(int(back_rect.x() + 21), int(cy - 8), int(back_rect.x() + 12), int(cy))
            painter.drawLine(int(back_rect.x() + 12), int(cy), int(back_rect.x() + 21), int(cy + 8))

            title = self._feature_title(self._current_feature())
            painter.setFont(self.header_title_font)
            painter.setPen(self.panel_title_color)
            title_w = self.header_title_metrics.horizontalAdvance(title)
            painter.drawText(int(body_x + (body_w - title_w) / 2), 35, title)
            self._paint_action_buttons(painter, layout)
            return

        painter.setFont(self.panel_title_font)
        painter.setPen(self.panel_title_color)
        brand = self.panel_title_metrics.elidedText(self.brand_text, Qt.TextElideMode.ElideRight, int(body_w * 0.34))
        painter.drawText(int(body_x + 28), 35, brand)

        settings_rect = rects["settings"]
        self.settings_icon_rect = settings_rect
        hover = settings_rect.contains(self.mapFromGlobal(QCursor.pos()))
        self._draw_settings_icon(painter, settings_rect, hover)

        painter.setFont(self.time_font)
        painter.setPen(self.panel_title_color)
        status = self.current_time
        status_w = self.time_metrics.horizontalAdvance(status)
        painter.drawText(int(settings_rect.left() - status_w - 8), 35, status)

    def _draw_settings_icon(self, painter: QPainter, rect: QRectF, hover: bool = False) -> None:
        painter.save()
        center = rect.center()
        color = QColor(238, 238, 242, 210 if hover else 150)
        painter.setPen(QPen(color, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        r_outer = 6.5
        for index in range(8):
            angle = math.tau * index / 8.0
            x1 = center.x() + math.cos(angle) * (r_outer + 1.2)
            y1 = center.y() + math.sin(angle) * (r_outer + 1.2)
            x2 = center.x() + math.cos(angle) * (r_outer + 3.2)
            y2 = center.y() + math.sin(angle) * (r_outer + 3.2)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        painter.drawEllipse(center, r_outer, r_outer)
        painter.drawEllipse(center, 2.3, 2.3)
        painter.restore()

    def _paint_action_buttons(self, painter: QPainter, layout: VisualLayout) -> None:
        actions = self._feature_actions(self._current_feature())
        if not actions:
            return
        self.action_button_rects = []
        x = layout.body_x + layout.body_width - 24
        for key in reversed(actions):
            label = tr(self.language, key)
            width = self.action_metrics.horizontalAdvance(label) + 22
            rect = QRectF(x - width, 14, width, 28)
            self.action_button_rects.append((key, rect))
            painter.setPen(QPen(self.soft_border_color, 1))
            painter.setBrush(self.control_fill_color)
            painter.drawRoundedRect(rect, 10, 10)
            painter.setFont(self.action_font)
            painter.setPen(self.panel_title_color)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
            x -= width + 8

    def _paint_feature_area(self, painter: QPainter, layout: VisualLayout, rects: dict[str, QRectF]) -> None:
        if self._search_results_active():
            self._paint_local_search_results(painter, rects["feature_area"])
            return
        if self.current_view == VIEW_DETAIL:
            self._paint_detail_area(painter, rects["feature_area"])
            return
        self._paint_home_feature(painter, layout, rects["feature_area"])

    def _paint_home_feature(self, painter: QPainter, layout: VisualLayout, area: QRectF) -> None:
        feature = self._current_feature()
        center = QPointF(area.center().x(), min(area.center().y() + 16, area.bottom() - 72))
        hover_progress = self.feature_hover_progress
        plate_size = FEATURE_ICON_TILE_SIZE
        icon_rect = QRectF(
            int(round(center.x() - plate_size / 2)),
            int(round(center.y() - 104)),
            int(round(plate_size)),
            int(round(plate_size)),
        )
        self._draw_feature_icon(painter, feature, icon_rect)

        title = self._feature_title(feature)
        desc = self._feature_description(feature)
        painter.setFont(self.feature_title_font)
        title_base = 226 + int(24 * hover_progress)
        painter.setPen(QColor(title_base, title_base, min(255, title_base + 3)))
        title_w = self.feature_title_metrics.horizontalAdvance(title)
        painter.drawText(int(center.x() - title_w / 2), int(center.y() + 18), title)

        painter.setFont(self.feature_desc_font)
        painter.setPen(self.panel_text_color)
        desc_w = self.feature_desc_metrics.horizontalAdvance(desc)
        painter.drawText(int(center.x() - desc_w / 2), int(center.y() + 48), desc)
        self._paint_feature_dots(painter, layout, area)

    def _paint_detail_area(self, painter: QPainter, area: QRectF) -> None:
        if self._current_feature() == FEATURE_CLIPBOARD:
            self._paint_clipboard_detail_area(painter, area)
            return
        if self._current_feature() == FEATURE_FILES:
            self._paint_file_hub_detail_area(painter, area)
            return
        if self._current_feature() == FEATURE_FAVORITES:
            self._paint_favorites_detail_area(painter, area)
            return

        feature = self._current_feature()
        title = self._feature_title(feature)
        detail = tr(self.language, self._feature_detail_key(feature))
        center = area.center()

        painter.setPen(QPen(self.soft_border_color, 1))
        painter.setBrush(self.detail_card_color)
        card = QRectF(area.x() + 44, center.y() - 46, area.width() - 88, 92)
        painter.drawRoundedRect(card, 16, 16)

        painter.setFont(self.feature_title_font)
        painter.setPen(self.panel_title_color)
        title_w = self.feature_title_metrics.horizontalAdvance(title)
        painter.drawText(int(center.x() - title_w / 2), int(center.y() - 8), title)

        painter.setFont(self.feature_desc_font)
        painter.setPen(self.panel_text_color)
        detail_w = self.feature_desc_metrics.horizontalAdvance(detail)
        painter.drawText(int(center.x() - detail_w / 2), int(center.y() + 22), detail)

    def _search_results_active(self) -> bool:
        return self.state == STATE_EXPANDED and bool(self.search_query)

    def _web_suggestions_visible(self) -> bool:
        return self._search_results_active() and bool(self.web_suggestions)

    def _build_web_suggestions(self, query: str) -> list[dict]:
        text = query.strip()
        if not text:
            return []
        keys = [
            "web_suggestion_more",
            "web_suggestion_download",
            "web_suggestion_tutorial",
            "web_suggestion_official",
            "web_suggestion_how_open",
        ]
        return [
            {"title": tr(self.language, key).format(query=text), "query": tr(self.language, key).format(query=text)}
            for key in keys
        ][:SEARCH_WEB_SUGGESTION_MAX]

    def _search_engine_display_name(self) -> str:
        key = str(getattr(self, "default_search_engine", DEFAULT_SEARCH["default_engine"]))
        return tr(self.language, f"engine_{key}")

    def _web_suggestion_engine_label(self) -> str:
        return tr(self.language, "web_suggestion_engine_label").format(
            engine=self._search_engine_display_name()
        )

    def _search_selection_count(self) -> int:
        return len(self.local_search_results) + len(self.web_suggestions)

    def _move_search_selection(self, delta: int) -> None:
        count = self._search_selection_count()
        if count <= 0:
            return
        self.selected_search_index = (self.selected_search_index + delta) % count
        if self.selected_search_index < len(self.local_search_results):
            self._ensure_selected_search_visible()
        self._request_update()

    def _scroll_search_results(self, direction: int) -> None:
        visible_count = max(1, len(self.search_result_rects))
        max_offset = max(0, len(self.local_search_results) - visible_count)
        next_offset = max(0, min(max_offset, self.search_scroll_offset + direction))
        if next_offset == self.search_scroll_offset:
            return
        self.search_scroll_offset = next_offset
        self._request_update()

    def _ensure_selected_search_visible(self) -> None:
        visible_count = max(1, len(self.search_result_rects))
        if self.selected_search_index < self.search_scroll_offset:
            self.search_scroll_offset = self.selected_search_index
        elif self.selected_search_index >= self.search_scroll_offset + visible_count:
            self.search_scroll_offset = max(0, self.selected_search_index - visible_count + 1)

    def _open_selected_search_item(self) -> bool:
        if not self.search_query:
            return False
        if self.selected_search_index < len(self.local_search_results):
            return self._open_local_search_result(self.selected_search_index)
        web_index = self.selected_search_index - len(self.local_search_results)
        if 0 <= web_index < len(self.web_suggestions):
            return self._open_web_suggestion(web_index)
        return False

    def _open_local_search_result(self, index: int) -> bool:
        if index < 0 or index >= len(self.local_search_results):
            return False
        try:
            return open_search_result(self.local_search_results[index])
        except Exception as exc:
            log_error("Local search result open failed", exc)
            return False

    def _open_web_suggestion(self, index: int) -> bool:
        if index < 0 or index >= len(self.web_suggestions):
            return False
        query = str(self.web_suggestions[index].get("query", "")).strip()
        if not query:
            return False
        try:
            return bool(webbrowser.open(build_search_url(query, self.default_search_engine)))
        except Exception as exc:
            log_error("Web suggestion open failed", exc)
            return False

    def _paint_local_search_results(self, painter: QPainter, area: QRectF) -> None:
        self.search_result_rects = []
        painter.save()
        painter.setFont(self.status_font)
        painter.setPen(self.panel_text_color)
        x = int(area.x() + 28)
        y = int(area.y() + 4)
        width = int(area.width() - 56)

        if self.search_is_loading:
            painter.drawText(QRectF(x, y, width, 30), Qt.AlignmentFlag.AlignVCenter, tr(self.language, "search_loading"))
            painter.restore()
            return

        if not self.local_search_results:
            painter.drawText(QRectF(x, y, width, 30), Qt.AlignmentFlag.AlignVCenter, tr(self.language, "search_no_local_results"))
            painter.restore()
            return

        row_h = SEARCH_RESULT_ROW_HEIGHT
        gap = SEARCH_RESULT_ROW_GAP
        max_y = int(area.bottom() - 2)
        first = True
        last_type = ""
        visible_index = 0
        max_possible_rows = max(1, int((max_y - y) // (row_h + gap)))
        max_offset = max(0, len(self.local_search_results) - max_possible_rows)
        self.search_scroll_offset = max(0, min(self.search_scroll_offset, max_offset))
        for index, result in enumerate(self.local_search_results[self.search_scroll_offset:]):
            index += self.search_scroll_offset
            result_type = str(result.get("type", ""))
            if first:
                section = tr(self.language, "search_section_best")
            elif result_type != last_type:
                section = tr(self.language, f"search_section_{result_type}")
            else:
                section = ""
            if section:
                if y + 18 + row_h > max_y:
                    break
                painter.setFont(self.status_font)
                painter.setPen(self.panel_text_color)
                painter.drawText(QRectF(x, y, width, 18), Qt.AlignmentFlag.AlignVCenter, section)
                y += 22
            if y + row_h > max_y:
                break
            rect = QRectF(x, y, width, row_h)
            self.search_result_rects.append((index, rect))
            selected = self.selected_search_index == index
            self._paint_search_result_row(painter, rect, result, selected)
            y += row_h + gap
            first = False
            last_type = result_type
            visible_index += 1
        painter.restore()

    def _paint_search_result_row(self, painter: QPainter, rect: QRectF, result: dict, selected: bool) -> None:
        painter.save()
        painter.setPen(QPen(self.soft_border_color, 1))
        painter.setBrush(QColor(255, 255, 255, 28 if selected else 12))
        painter.drawRoundedRect(rect, 12, 12)

        icon_rect = QRectF(rect.x() + 10, rect.y() + 7, 28, 28)
        self._paint_search_result_icon(painter, icon_rect, result)

        title = str(result.get("title", ""))
        subtitle = str(result.get("subtitle", "")) or tr(self.language, f"result_type_{result.get('type', 'file')}")
        title_w = int(rect.width() - 58)
        painter.setFont(self.list_title_font)
        painter.setPen(self.panel_title_color)
        painter.drawText(QRectF(rect.x() + 48, rect.y() + 6, title_w, 18), Qt.AlignmentFlag.AlignVCenter, self.list_title_metrics.elidedText(title, Qt.TextElideMode.ElideRight, title_w))
        painter.setFont(self.list_subtitle_font)
        painter.setPen(self.panel_text_color)
        painter.drawText(QRectF(rect.x() + 48, rect.y() + 23, title_w, 16), Qt.AlignmentFlag.AlignVCenter, self.list_subtitle_metrics.elidedText(subtitle, Qt.TextElideMode.ElideRight, title_w))
        painter.restore()

    def _paint_search_result_icon(self, painter: QPainter, rect: QRectF, result: dict) -> None:
        result_type = str(result.get("type", ""))
        path = result.get("path")
        if result_type in ("app", "file", "folder") and path:
            pixmap = self._file_pixmap(str(path), 24)
            painter.drawPixmap(int(rect.center().x() - 12), int(rect.center().y() - 12), pixmap)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if result_type == "setting":
            painter.setPen(QPen(QColor(130, 210, 255), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(QColor(70, 120, 170, 54))
            painter.drawEllipse(rect.adjusted(4, 4, -4, -4))
            painter.drawEllipse(rect.adjusted(10, 10, -10, -10))
        elif result_type == "uwp":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(104, 150, 255, 76))
            painter.drawRoundedRect(rect.adjusted(4, 4, -4, -4), 7, 7)
            painter.setBrush(QColor(232, 240, 255, 220))
            painter.drawRoundedRect(QRectF(rect.x() + 9, rect.y() + 9, 8, 8), 2, 2)
            painter.drawRoundedRect(QRectF(rect.x() + 19, rect.y() + 9, 8, 8), 2, 2)
            painter.drawRoundedRect(QRectF(rect.x() + 9, rect.y() + 19, 8, 8), 2, 2)
            painter.drawRoundedRect(QRectF(rect.x() + 19, rect.y() + 19, 8, 8), 2, 2)
        else:
            painter.setPen(QPen(QColor(180, 205, 255), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(QColor(110, 130, 220, 54))
            painter.drawRoundedRect(rect.adjusted(3, 5, -3, -5), 6, 6)
            painter.drawLine(int(rect.x() + 9), int(rect.center().y()), int(rect.right() - 9), int(rect.center().y()))
        painter.restore()

    def _file_pixmap(self, path: str, size: int) -> QPixmap:
        key = (path, size)
        cached = self._file_icon_cache.get(key)
        if cached is not None:
            return cached
        pixmap = self.file_icon_provider.icon(QFileInfo(path)).pixmap(size, size)
        self._file_icon_cache[key] = pixmap
        return pixmap

    def _paint_favorite_item_icon(self, painter: QPainter, rect: QRectF, item: dict) -> None:
        item_type = str(item.get("type", ""))
        target = str(item.get("target", ""))
        if item_type in ("file", "folder", "app") and target:
            pixmap = self._file_pixmap(target, 34)
            painter.drawPixmap(int(rect.center().x() - 17), int(rect.center().y() - 17), pixmap)
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        gradient = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.bottom())
        gradient.setColorAt(0.0, QColor(255, 214, 120, 232))
        gradient.setColorAt(1.0, QColor(142, 103, 255, 230))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        star = QPainterPath()
        cx = rect.center().x()
        cy = rect.center().y()
        outer = min(rect.width(), rect.height()) / 2 - 4
        inner = outer * 0.48
        for i in range(10):
            angle = -math.pi / 2 + i * math.pi / 5
            radius = outer if i % 2 == 0 else inner
            point = QPointF(cx + math.cos(angle) * radius, cy + math.sin(angle) * radius)
            if i == 0:
                star.moveTo(point)
            else:
                star.lineTo(point)
        star.closeSubpath()
        painter.drawPath(star)
        painter.restore()

    def _paint_web_suggestions(self, painter: QPainter, search_rect: QRectF) -> None:
        self.web_suggestion_rects = []
        layout = self._last_visual_layout or self.compute_visual_layout()
        panel_w = int(round(max(360.0, min(layout.body_width - 54.0, search_rect.width() + 42.0))))
        panel_x = int(round(layout.body_x + (layout.body_width - panel_w) / 2))
        panel_y = int(round(layout.body_height + 12))
        row_h = 28
        label_h = 22
        panel_h = 20 + label_h + min(len(self.web_suggestions), SEARCH_WEB_SUGGESTION_MAX) * row_h
        panel = QRectF(panel_x, panel_y, panel_w, panel_h)

        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 46))
        painter.drawRoundedRect(panel.translated(0, 5), 16, 16)
        painter.setPen(QPen(QColor(255, 255, 255, 24), 1))
        painter.setBrush(QColor(18, 18, 22, 226))
        painter.drawRoundedRect(panel, 16, 16)

        painter.setFont(self.status_font)
        painter.setPen(self.panel_muted_color)
        painter.drawText(
            QRectF(panel.x() + 22, panel.y() + 9, panel.width() - 44, 16),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._web_suggestion_engine_label(),
        )
        for index, suggestion in enumerate(self.web_suggestions[:SEARCH_WEB_SUGGESTION_MAX]):
            rect = QRectF(panel.x() + 12, panel.y() + 10 + label_h + index * row_h, panel.width() - 24, row_h - 3)
            combined_index = len(self.local_search_results) + index
            selected = self.selected_search_index == combined_index
            self.web_suggestion_rects.append((index, rect))
            if selected:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(255, 255, 255, 24))
                painter.drawRoundedRect(rect, 9, 9)
            painter.setPen(self.panel_title_color if selected else self.panel_text_color)
            painter.drawText(rect.adjusted(10, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, str(suggestion.get("title", "")))
        painter.restore()

    def _paint_clipboard_detail_area(self, painter: QPainter, area: QRectF) -> None:
        self.clipboard_item_rects = []
        self.clipboard_list_viewport_rect = QRectF()
        self.clipboard_scrollbar_track_rect = QRectF()
        self.clipboard_scrollbar_thumb_rect = QRectF()
        items = self.clipboard_manager.items if self.clipboard_manager is not None else []
        if self.clipboard_manager is not None and self.clipboard_manager.paused:
            paused_text = tr(self.language, "clipboard_paused")
            painter.setFont(self.feature_desc_font)
            painter.setPen(QColor(255, 214, 120, 210))
            painter.drawText(QRectF(area.x(), area.y() + 2, area.width(), 24), Qt.AlignmentFlag.AlignCenter, paused_text)

        if not items:
            painter.setFont(self.feature_desc_font)
            painter.setPen(self.panel_text_color)
            painter.drawText(area, Qt.AlignmentFlag.AlignCenter, tr(self.language, "clipboard_empty"))
            return

        row_h = 42
        spacing = 8
        count_text = tr(self.language, "clipboard_recent_count").format(count=len(items))
        painter.setFont(self.status_font)
        painter.setPen(self.panel_text_color)
        painter.drawText(
            QRectF(area.x() + 32, area.y() + 2, area.width() - 64, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            count_text,
        )

        list_top = int(area.y() + 26)
        list_height = max(1, int(area.bottom() - list_top - 4))
        viewport = QRectF(int(area.x() + 32), list_top, int(area.width() - 68), list_height)
        self.clipboard_list_viewport_rect = viewport
        content_height = max(0, len(items) * (row_h + spacing) - spacing)
        self.clipboard_scroll_y = self._clamp_clipboard_scroll(self.clipboard_scroll_y, content_height, viewport.height())
        metrics = self.feature_desc_metrics
        painter.setFont(self.feature_desc_font)

        painter.save()
        painter.setClipRect(viewport)
        content_top = viewport.y() - self.clipboard_scroll_y
        for item_index, item in enumerate(items):
            rect = QRectF(viewport.x(), content_top + item_index * (row_h + spacing), viewport.width() - 8, row_h)
            if rect.bottom() < viewport.top():
                continue
            if rect.top() > viewport.bottom():
                break
            self.clipboard_item_rects.append((item_index, rect))
            painter.setPen(QPen(self.soft_border_color, 1))
            painter.setBrush(self.detail_card_color)
            painter.drawRoundedRect(rect, 12, 12)
            text = str(item.get("text", "")).replace("\r", " ").replace("\n", " ")
            elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, int(rect.width() - 24))
            painter.setPen(self.panel_title_color)
            painter.drawText(rect.adjusted(12, 0, -12, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)
        painter.restore()

        if content_height > viewport.height():
            track_w = 5
            track = QRectF(area.right() - 26, viewport.y(), track_w, viewport.height())
            max_scroll = max(1.0, content_height - viewport.height())
            thumb_h = max(24.0, viewport.height() * viewport.height() / max(1.0, content_height))
            thumb_y = track.y() + (self.clipboard_scroll_y / max_scroll) * (track.height() - thumb_h)
            thumb = QRectF(track.x(), thumb_y, track.width(), thumb_h)
            self.clipboard_scrollbar_track_rect = track
            self.clipboard_scrollbar_thumb_rect = thumb
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 14))
            painter.drawRoundedRect(track, 3, 3)
            painter.setBrush(QColor(255, 255, 255, 82 if self.clipboard_scrollbar_dragging else 48))
            painter.drawRoundedRect(thumb, 3, 3)
            painter.restore()

    def _paint_file_hub_detail_area(self, painter: QPainter, area: QRectF) -> None:
        self.file_item_rects = []
        if self.file_hub_manager is None:
            return
        self.file_hub_manager.refresh_exists()
        items = self.file_hub_manager.items
        count_text = tr(self.language, "file_hub_count_label").format(count=len(items))
        painter.setFont(self.status_font)
        painter.setPen(self.panel_text_color)
        painter.drawText(
            QRectF(area.x() + 32, area.y() + 2, area.width() - 64, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            count_text,
        )
        if getattr(self.file_hub_manager, "last_status", "") == "limit":
            painter.setPen(QColor(255, 214, 120, 210))
            painter.drawText(
                QRectF(area.x() + 32, area.y() + 22, area.width() - 64, 18),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                tr(self.language, "file_hub_limit_note"),
            )
        if not items:
            painter.setFont(self.feature_desc_font)
            painter.setPen(self.panel_text_color)
            painter.drawText(area, Qt.AlignmentFlag.AlignCenter, tr(self.language, "file_hub_empty"))
            return

        tile_w = 92
        tile_h = 86
        gap = 12
        columns = max(1, int((area.width() - 50) // (tile_w + gap)))
        start_x = int(area.x() + (area.width() - (columns * tile_w + (columns - 1) * gap)) / 2)
        start_y = int(area.y() + 44)
        rows_visible = max(1, int(max(1, area.bottom() - start_y - 4) // (tile_h + gap)))
        visible_slots = max(1, columns * rows_visible)
        max_offset = max(0, len(items) - visible_slots)
        self.file_scroll_offset = max(0, min(self.file_scroll_offset, max_offset))
        painter.setFont(self.feature_desc_font)
        for visible_index, item in enumerate(items[self.file_scroll_offset:self.file_scroll_offset + visible_slots]):
            index = self.file_scroll_offset + visible_index
            row = visible_index // columns
            col = visible_index % columns
            rect = QRectF(start_x + col * (tile_w + gap), start_y + row * (tile_h + gap), tile_w, tile_h)
            if rect.bottom() > area.bottom() - 4:
                break
            self.file_item_rects.append((index, rect))
            exists = bool(item.get("exists", True))
            painter.setPen(QPen(self.soft_border_color, 1))
            painter.setBrush(QColor(255, 255, 255, 12 if exists else 6))
            painter.drawRoundedRect(rect, 14, 14)
            path = str(item.get("path", ""))
            pixmap = self._file_pixmap(path, 32)
            painter.drawPixmap(int(rect.center().x() - 16), int(rect.y() + 12), pixmap)
            name = str(item.get("name", path))
            elided = self.feature_desc_metrics.elidedText(name, Qt.TextElideMode.ElideRight, int(rect.width() - 12))
            painter.setPen(self.panel_title_color if exists else QColor(255, 150, 150))
            painter.drawText(QRectF(rect.x() + 6, rect.y() + 52, rect.width() - 12, 26), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, elided)

    def _paint_favorites_detail_area(self, painter: QPainter, area: QRectF) -> None:
        self.favorite_item_rects = []
        if self.favorites_manager is None:
            return
        items = self.favorites_manager.items
        count_text = tr(self.language, "favorites_count_label").format(count=len(items))
        painter.setFont(self.status_font)
        painter.setPen(self.panel_text_color)
        painter.drawText(
            QRectF(area.x() + 32, area.y() + 2, area.width() - 64, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            count_text,
        )
        if not items:
            painter.setFont(self.feature_desc_font)
            painter.setPen(self.panel_text_color)
            painter.drawText(area, Qt.AlignmentFlag.AlignCenter, tr(self.language, "favorites_empty"))
            return

        tile_w = 96
        tile_h = 98
        gap = 12
        columns = max(1, int((area.width() - 50) // (tile_w + gap)))
        start_x = int(area.x() + (area.width() - (columns * tile_w + (columns - 1) * gap)) / 2)
        start_y = int(area.y() + 30)
        rows_visible = max(1, int(max(1, area.bottom() - start_y - 4) // (tile_h + gap)))
        visible_slots = max(1, columns * rows_visible)
        max_offset = max(0, len(items) - visible_slots)
        self.favorites_scroll_offset = max(0, min(self.favorites_scroll_offset, max_offset))
        painter.setFont(self.feature_desc_font)
        for visible_index, item in enumerate(items[self.favorites_scroll_offset:self.favorites_scroll_offset + visible_slots]):
            index = self.favorites_scroll_offset + visible_index
            row = visible_index // columns
            col = visible_index % columns
            rect = QRectF(start_x + col * (tile_w + gap), start_y + row * (tile_h + gap), tile_w, tile_h)
            if rect.bottom() > area.bottom() - 4:
                break
            self.favorite_item_rects.append((index, rect))
            painter.setPen(QPen(self.soft_border_color, 1))
            painter.setBrush(QColor(255, 255, 255, 13))
            painter.drawRoundedRect(rect, 15, 15)
            icon_rect = QRectF(rect.center().x() - 20, rect.y() + 12, 40, 40)
            self._paint_favorite_item_icon(painter, icon_rect, item)
            title = str(item.get("title", ""))
            category = tr(self.language, f"favorite_category_{item.get('category', item.get('type', 'file'))}")
            title_elided = self.feature_desc_metrics.elidedText(title, Qt.TextElideMode.ElideRight, int(rect.width() - 12))
            painter.setPen(self.panel_title_color)
            painter.drawText(QRectF(rect.x() + 6, rect.y() + 56, rect.width() - 12, 20), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, title_elided)
            painter.setFont(self.status_font)
            painter.setPen(self.panel_text_color)
            painter.drawText(QRectF(rect.x() + 6, rect.y() + 76, rect.width() - 12, 16), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, category)
            painter.setFont(self.feature_desc_font)

    def _paint_feature_dots(self, painter: QPainter, layout: VisualLayout, area: QRectF) -> None:
        self.feature_dot_rects = []
        x = layout.body_x + layout.body_width - 28
        start_y = area.center().y() - (len(self.features) - 1) * 9
        painter.setPen(Qt.PenStyle.NoPen)
        for index, _feature in enumerate(self.features):
            active = index == self.current_feature_index
            radius = 4 if active else 3
            color = QColor(245, 245, 247, 220 if active else 90)
            y = start_y + index * 18
            rect = QRectF(x - 8, y - 8, 16, 16)
            self.feature_dot_rects.append((index, rect))
            painter.setBrush(color)
            painter.drawEllipse(QRectF(x - radius, y - radius, radius * 2, radius * 2))

    def _paint_floating_search(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        rect = QRectF(round(rect.x()), round(rect.y()), round(rect.width()), round(rect.height()))
        if self.focus_ring_progress > 0.01:
            ring_inset = SEARCH_RING_WIDTH / 2 + 0.35
            ring_rect = rect.adjusted(ring_inset, ring_inset, -ring_inset, -ring_inset)
            self._draw_search_ring_glow(painter, ring_rect, self.focus_ring_progress, self.search_focus_flow_phase)

        lift = min(1.0, abs(self._search_focus_offset()) / SEARCH_FOCUS_FLOAT_PX)
        for offset, alpha in ((6, 42 + int(22 * lift)), (3, 26 + int(16 * lift))):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawRoundedRect(rect.translated(0, offset), SEARCH_RADIUS, SEARCH_RADIUS)

        border_alpha = 28 + int(24 * self.focus_ring_progress)
        painter.setPen(QPen(QColor(255, 255, 255, border_alpha), 1))
        painter.setBrush(QColor(22, 22, 26, 235))
        painter.drawRoundedRect(rect, SEARCH_RADIUS, SEARCH_RADIUS)

        top_highlight = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.top() + 16)
        top_highlight.setColorAt(0.0, QColor(255, 255, 255, 12 + int(8 * self.focus_ring_progress)))
        top_highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(top_highlight))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -18), SEARCH_RADIUS - 2, SEARCH_RADIUS - 2)

        if self.focus_ring_progress > 0.01:
            self.draw_search_focus_ring(
                painter,
                rect,
                self.focus_ring_progress,
                self.search_sweep_progress,
                self.search_focus_flow_phase,
            )

        icon_x = rect.x() + 23
        icon_y = rect.center().y()
        painter.setPen(QPen(self.panel_text_color, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawEllipse(QRectF(icon_x - 6, icon_y - 7, 12, 12))
        painter.drawLine(int(icon_x + 5), int(icon_y + 5), int(icon_x + 11), int(icon_y + 11))
        painter.restore()

    def draw_search_focus_ring(self, painter: QPainter, rect: QRectF, focus_progress: float, sweep_progress: float, flow_phase: float) -> None:
        progress = max(0.0, min(1.0, focus_progress))
        if progress <= 0.01:
            return
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        rect = QRectF(round(rect.x()), round(rect.y()), round(rect.width()), round(rect.height()))
        ring_inset = SEARCH_RING_WIDTH / 2 + 0.35
        ring_rect = rect.adjusted(ring_inset, ring_inset, -ring_inset, -ring_inset)
        self._draw_search_static_ring(painter, ring_rect, progress, flow_phase)
        if sweep_progress < 0.999:
            self._draw_search_ring_segments(
                painter,
                ring_rect,
                progress,
                sweep_progress,
                True,
                SEARCH_RING_WIDTH,
                SEARCH_RING_SWEEP_ALPHA,
            )
        painter.restore()

    def _search_ring_gradient(self, rect: QRectF, alpha: int, flow_phase: float) -> QConicalGradient:
        gradient = QConicalGradient(rect.center(), -360 * flow_phase)
        stops = [
            (0.00, QColor(SEARCH_RING_COLORS[0])),
            (0.18, QColor(SEARCH_RING_COLORS[1])),
            (0.36, QColor(SEARCH_RING_COLORS[2])),
            (0.54, QColor(SEARCH_RING_COLORS[3])),
            (0.74, QColor(SEARCH_RING_COLORS[4])),
            (0.90, QColor(SEARCH_RING_COLORS[5])),
            (1.00, QColor(SEARCH_RING_COLORS[0])),
        ]
        for pos, color in stops:
            c = QColor(color)
            c.setAlpha(alpha)
            gradient.setColorAt(pos, c)
        return gradient

    def _draw_search_ring_glow(self, painter: QPainter, rect: QRectF, progress: float, flow_phase: float) -> None:
        alpha = int(SEARCH_RING_GLOW_ALPHA * progress)
        if alpha <= 0:
            return
        glow_rect = rect.adjusted(-0.6, -0.6, 0.6, 0.6)
        painter.setPen(QPen(
            QBrush(self._search_ring_gradient(glow_rect, alpha, flow_phase)),
            SEARCH_RING_GLOW_WIDTH,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        ))
        painter.drawRoundedRect(glow_rect, SEARCH_RADIUS, SEARCH_RADIUS)

    def _draw_search_static_ring(self, painter: QPainter, rect: QRectF, progress: float, flow_phase: float) -> None:
        active_alpha = SEARCH_RING_FLOW_ALPHA + (SEARCH_RING_ACTIVE_ALPHA - SEARCH_RING_FLOW_ALPHA) * progress
        gradient = self._search_ring_gradient(rect, int(active_alpha * progress), flow_phase)
        painter.setPen(QPen(QBrush(gradient), SEARCH_RING_WIDTH, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawRoundedRect(rect, SEARCH_RADIUS - 1, SEARCH_RADIUS - 1)

    def _draw_search_ring_segments(
        self,
        painter: QPainter,
        rect: QRectF,
        progress: float,
        phase: float,
        sweep: bool,
        width: float | None = None,
        alpha_base: int | None = None,
    ) -> None:
        if sweep:
            segment_count = 86
            segment_span = 0.30
            line_width = SEARCH_RING_WIDTH if width is None else width
            start = phase
            end = phase + segment_span
        else:
            segment_count = 128
            segment_span = 1.0
            line_width = SEARCH_RING_WIDTH if width is None else width
            start = phase
            end = phase + 1.0
        base_alpha = 255 if alpha_base is None and sweep else 168 if alpha_base is None else alpha_base
        last_point: QPointF | None = None
        last_raw = start
        for index in range(segment_count + 1):
            local = index / segment_count
            raw = start + (segment_span * local if sweep else local)
            t = raw % 1.0
            point = self._rounded_rect_point(rect, t)
            if index > 0 and int(raw) != int(last_raw):
                last_point = None
            if last_point is not None:
                color = self._ring_color(t)
                alpha = int(base_alpha * progress)
                if sweep:
                    alpha = int(alpha * math.sin(math.pi * local))
                color.setAlpha(max(0, alpha))
                painter.setPen(QPen(color, line_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                painter.drawLine(last_point, point)
            last_point = point
            last_raw = raw

    def _rounded_rect_point(self, rect: QRectF, t: float) -> QPointF:
        r = min(SEARCH_RADIUS, rect.width() / 2, rect.height() / 2)
        straight_w = max(0.0, rect.width() - 2 * r)
        straight_h = max(0.0, rect.height() - 2 * r)
        arc = math.pi * r / 2
        perimeter = 2 * (straight_w + straight_h) + 4 * arc
        distance = (t % 1.0) * perimeter
        x0, y0, x1, y1 = rect.left(), rect.top(), rect.right(), rect.bottom()

        if distance <= straight_w:
            return QPointF(x0 + r + distance, y0)
        distance -= straight_w
        if distance <= arc:
            a = -math.pi / 2 + distance / arc * math.pi / 2
            return QPointF(x1 - r + math.cos(a) * r, y0 + r + math.sin(a) * r)
        distance -= arc
        if distance <= straight_h:
            return QPointF(x1, y0 + r + distance)
        distance -= straight_h
        if distance <= arc:
            a = 0 + distance / arc * math.pi / 2
            return QPointF(x1 - r + math.cos(a) * r, y1 - r + math.sin(a) * r)
        distance -= arc
        if distance <= straight_w:
            return QPointF(x1 - r - distance, y1)
        distance -= straight_w
        if distance <= arc:
            a = math.pi / 2 + distance / arc * math.pi / 2
            return QPointF(x0 + r + math.cos(a) * r, y1 - r + math.sin(a) * r)
        distance -= arc
        if distance <= straight_h:
            return QPointF(x0, y1 - r - distance)
        distance -= straight_h
        a = math.pi + distance / arc * math.pi / 2
        return QPointF(x0 + r + math.cos(a) * r, y0 + r + math.sin(a) * r)

    @staticmethod
    def _ring_color(t: float) -> QColor:
        stops = [
            (0.00, QColor(SEARCH_RING_COLORS[0])),
            (0.20, QColor(SEARCH_RING_COLORS[1])),
            (0.40, QColor(SEARCH_RING_COLORS[2])),
            (0.58, QColor(SEARCH_RING_COLORS[3])),
            (0.78, QColor(SEARCH_RING_COLORS[4])),
            (0.92, QColor(SEARCH_RING_COLORS[5])),
            (1.00, QColor(SEARCH_RING_COLORS[0])),
        ]
        value = t % 1.0
        for index in range(len(stops) - 1):
            left_pos, left_color = stops[index]
            right_pos, right_color = stops[index + 1]
            if left_pos <= value <= right_pos:
                ratio = (value - left_pos) / max(0.001, right_pos - left_pos)
                return QColor(
                    int(left_color.red() + (right_color.red() - left_color.red()) * ratio),
                    int(left_color.green() + (right_color.green() - left_color.green()) * ratio),
                    int(left_color.blue() + (right_color.blue() - left_color.blue()) * ratio),
                )
        return QColor(SEARCH_RING_COLORS[0])

    def _draw_feature_icon(self, painter: QPainter, feature: str, rect: QRectF) -> None:
        painter.save()
        hover_progress = max(0.0, min(1.0, self.feature_hover_progress))
        pulse = 0.5 + 0.5 * math.sin(self.feature_pulse_phase * math.tau)
        pulse_strength = hover_progress * (0.75 + 0.25 * pulse)
        scale = 1.0 + 0.035 * pulse_strength
        center = rect.center()
        painter.translate(center)
        painter.scale(scale, scale)
        painter.translate(-center)
        self._draw_feature_tile(painter, rect, feature, hover_progress, pulse_strength)
        icon_size = FEATURE_ICON_SIZE + hover_progress * 1.2
        icon_rect = QRectF(
            rect.center().x() - icon_size / 2,
            rect.center().y() - icon_size / 2,
            icon_size,
            icon_size,
        )
        if feature == FEATURE_CLIPBOARD:
            self._draw_clipboard_icon(painter, icon_rect, hover_progress)
        elif feature == FEATURE_FILES:
            self._draw_file_hub_icon(painter, icon_rect, hover_progress)
        else:
            self._draw_favorites_icon(painter, icon_rect, hover_progress)
        painter.restore()

    def _draw_feature_tile(self, painter: QPainter, rect: QRectF, feature: str, hover_progress: float, pulse_strength: float = 0.0) -> None:
        painter.save()
        shadow_alpha = 28 + int(18 * hover_progress)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, shadow_alpha))
        painter.drawRoundedRect(rect.translated(0, 5), FEATURE_ICON_RADIUS, FEATURE_ICON_RADIUS)

        if hover_progress > 0.01:
            glow_alpha = int(18 + 34 * pulse_strength)
            painter.setBrush(QColor(255, 255, 255, glow_alpha))
            painter.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), FEATURE_ICON_RADIUS + 2, FEATURE_ICON_RADIUS + 2)

        gradient = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.bottom())
        if feature == FEATURE_CLIPBOARD:
            gradient.setColorAt(0.0, QColor(78, 68, 196))
            gradient.setColorAt(0.48, QColor(92, 111, 232))
            gradient.setColorAt(1.0, QColor(142, 100, 255))
        elif feature == FEATURE_FILES:
            gradient.setColorAt(0.0, QColor(0, 111, 126))
            gradient.setColorAt(0.55, QColor(0, 178, 155))
            gradient.setColorAt(1.0, QColor(56, 228, 184))
        else:
            gradient.setColorAt(0.0, QColor(91, 77, 202))
            gradient.setColorAt(0.50, QColor(154, 105, 255))
            gradient.setColorAt(1.0, QColor(255, 190, 94))

        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor(255, 255, 255, 34 + int(42 * hover_progress)), 1))
        painter.drawRoundedRect(rect, FEATURE_ICON_RADIUS, FEATURE_ICON_RADIUS)

        highlight = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.top() + rect.height() * 0.55)
        highlight.setColorAt(0.0, QColor(255, 255, 255, 54 + int(22 * hover_progress)))
        highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(highlight))
        painter.drawRoundedRect(rect.adjusted(2, 2, -2, -rect.height() * 0.44), FEATURE_ICON_RADIUS - 2, FEATURE_ICON_RADIUS - 2)
        painter.restore()

    def _draw_clipboard_icon(self, painter: QPainter, rect: QRectF, hover_progress: float) -> None:
        cx = rect.center().x()
        cy = rect.center().y()
        painter.setPen(Qt.PenStyle.NoPen)
        shadow = QRectF(cx - 15, cy - 13, 30, 34)
        painter.setBrush(QColor(17, 24, 84, 58))
        painter.drawRoundedRect(shadow.translated(0, 2), 8, 8)

        paper = QRectF(cx - 15, cy - 15, 30, 35)
        paper_gradient = QLinearGradient(paper.left(), paper.top(), paper.right(), paper.bottom())
        paper_gradient.setColorAt(0.0, QColor(252, 254, 255, 246))
        paper_gradient.setColorAt(0.55, QColor(219, 232, 255, 242))
        paper_gradient.setColorAt(1.0, QColor(171, 195, 255, 236))
        painter.setBrush(QBrush(paper_gradient))
        painter.drawRoundedRect(paper, 8, 8)

        side_glow = QLinearGradient(paper.left(), paper.top(), paper.left() + 8, paper.bottom())
        side_glow.setColorAt(0.0, QColor(104, 124, 255, 70))
        side_glow.setColorAt(1.0, QColor(104, 124, 255, 0))
        painter.setBrush(QBrush(side_glow))
        painter.drawRoundedRect(QRectF(paper.left(), paper.top() + 3, 8, paper.height() - 6), 5, 5)

        clip = QRectF(cx - 11, cy - 23, 22, 12)
        clip_gradient = QLinearGradient(clip.left(), clip.top(), clip.right(), clip.bottom())
        clip_gradient.setColorAt(0.0, QColor(255, 255, 255, 252))
        clip_gradient.setColorAt(0.55, QColor(229, 236, 255, 246))
        clip_gradient.setColorAt(1.0, QColor(166, 181, 255, 238))
        painter.setBrush(QBrush(clip_gradient))
        painter.drawRoundedRect(clip, 6, 6)
        painter.setBrush(QColor(88, 104, 224, 86 + int(28 * hover_progress)))
        painter.drawRoundedRect(QRectF(cx - 5.5, cy - 20.5, 11, 4), 2, 2)

        line_color = QColor(66, 84, 174, 144 + int(64 * hover_progress))
        painter.setBrush(line_color)
        painter.drawRoundedRect(QRectF(cx - 8, cy - 2, 16, 3.2), 1.6, 1.6)
        painter.drawRoundedRect(QRectF(cx - 8, cy + 7, 16, 3.2), 1.6, 1.6)
        painter.drawRoundedRect(QRectF(cx - 8, cy + 16, 10, 3.2), 1.6, 1.6)

    def _draw_file_hub_icon(self, painter: QPainter, rect: QRectF, hover_progress: float) -> None:
        cx = rect.center().x()
        cy = rect.center().y()
        painter.setPen(Qt.PenStyle.NoPen)
        folder_back = QPainterPath()
        folder_back.addRoundedRect(QRectF(cx - 20, cy - 11, 40, 28), 8, 8)
        back_gradient = QLinearGradient(cx - 20, cy - 12, cx + 20, cy + 18)
        back_gradient.setColorAt(0.0, QColor(202, 255, 240, 225))
        back_gradient.setColorAt(1.0, QColor(88, 232, 198, 220))
        painter.setBrush(QBrush(back_gradient))
        painter.drawPath(folder_back)

        tab = QPainterPath()
        tab.addRoundedRect(QRectF(cx - 20, cy - 18, 22, 12), 5, 5)
        painter.setBrush(QColor(216, 255, 246, 232))
        painter.drawPath(tab)

        front = QPainterPath()
        front.moveTo(cx - 22, cy - 5)
        front.quadTo(cx - 22, cy - 12, cx - 15, cy - 12)
        front.lineTo(cx + 18, cy - 12)
        front.quadTo(cx + 23, cy - 12, cx + 23, cy - 6)
        front.lineTo(cx + 20, cy + 18)
        front.quadTo(cx + 19, cy + 22, cx + 14, cy + 22)
        front.lineTo(cx - 17, cy + 22)
        front.quadTo(cx - 22, cy + 22, cx - 23, cy + 17)
        front.closeSubpath()
        front_gradient = QLinearGradient(cx - 22, cy - 12, cx + 22, cy + 22)
        front_gradient.setColorAt(0.0, QColor(146, 255, 226, 236))
        front_gradient.setColorAt(1.0, QColor(34, 193, 168, 236))
        painter.setBrush(QBrush(front_gradient))
        painter.drawPath(front)

        arrow = QPainterPath()
        arrow.moveTo(cx, cy + 12)
        arrow.lineTo(cx, cy - 7)
        arrow.lineTo(cx - 7, cy)
        arrow.lineTo(cx - 3, cy)
        arrow.lineTo(cx - 3, cy + 12)
        arrow.lineTo(cx + 3, cy + 12)
        arrow.lineTo(cx + 3, cy)
        arrow.lineTo(cx + 7, cy)
        arrow.closeSubpath()
        painter.setBrush(QColor(238, 255, 250, 236 + int(19 * hover_progress)))
        painter.drawPath(arrow)

    def _draw_favorites_icon(self, painter: QPainter, rect: QRectF, hover_progress: float) -> None:
        cx = rect.center().x()
        cy = rect.center().y()
        painter.setPen(Qt.PenStyle.NoPen)
        bookmark = QPainterPath()
        bookmark.addRoundedRect(QRectF(cx - 17, cy - 18, 34, 36), 8, 8)
        cut = QPainterPath()
        cut.moveTo(cx - 7, cy + 8)
        cut.lineTo(cx, cy + 15)
        cut.lineTo(cx + 7, cy + 8)
        cut.lineTo(cx + 7, cy + 20)
        cut.lineTo(cx - 7, cy + 20)
        cut.closeSubpath()
        bookmark = bookmark.subtracted(cut)
        body_gradient = QLinearGradient(cx - 17, cy - 18, cx + 17, cy + 18)
        body_gradient.setColorAt(0.0, QColor(255, 245, 210, 242))
        body_gradient.setColorAt(1.0, QColor(255, 190, 105, 232))
        painter.setBrush(QBrush(body_gradient))
        painter.drawPath(bookmark)

        star = QPainterPath()
        outer = 9
        inner = 4.3
        for i in range(10):
            angle = -math.pi / 2 + i * math.pi / 5
            radius = outer if i % 2 == 0 else inner
            point = QPointF(cx + math.cos(angle) * radius, cy - 1 + math.sin(angle) * radius)
            if i == 0:
                star.moveTo(point)
            else:
                star.lineTo(point)
        star.closeSubpath()
        painter.setBrush(QColor(122, 83, 210, 210 + int(35 * hover_progress)))
        painter.drawPath(star)

        painter.setBrush(QColor(255, 255, 255, 90 + int(35 * hover_progress)))
        painter.drawRoundedRect(QRectF(cx - 11, cy - 13, 22, 4), 2, 2)

    def _clipboard_detail_active(self) -> bool:
        return (
            self.state == STATE_EXPANDED
            and self.current_view == VIEW_DETAIL
            and self._current_feature() == FEATURE_CLIPBOARD
            and self.clipboard_manager is not None
        )

    def _clipboard_item_at(self, pos: QPointF | QPoint) -> int | None:
        if not self._clipboard_detail_active():
            return None
        for index, rect in self.clipboard_item_rects:
            if rect.contains(pos):
                return index
        return None

    def _file_hub_detail_active(self) -> bool:
        return (
            self.state == STATE_EXPANDED
            and self.current_view == VIEW_DETAIL
            and self._current_feature() == FEATURE_FILES
            and self.file_hub_manager is not None
        )

    def _file_item_at(self, pos: QPointF | QPoint) -> int | None:
        if not self._file_hub_detail_active():
            return None
        for index, rect in self.file_item_rects:
            if rect.contains(pos):
                return index
        return None

    def _favorites_detail_active(self) -> bool:
        return (
            self.state == STATE_EXPANDED
            and self.current_view == VIEW_DETAIL
            and self._current_feature() == FEATURE_FAVORITES
            and self.favorites_manager is not None
        )

    def _favorite_item_at(self, pos: QPointF | QPoint) -> int | None:
        if not self._favorites_detail_active():
            return None
        for index, rect in self.favorite_item_rects:
            if rect.contains(pos):
                return index
        return None

    def _show_favorite_item_menu(self, index: int, global_pos: QPoint) -> None:
        if self.favorites_manager is None:
            return
        menu = QMenu(self)
        open_action = menu.addAction(tr(self.language, "favorite_menu_open"))
        edit_action = menu.addAction(tr(self.language, "favorite_menu_edit"))
        delete_action = menu.addAction(tr(self.language, "favorite_menu_delete"))
        self.outside_click_timer.stop()
        try:
            selected = menu.exec(global_pos)
            if selected == open_action:
                self.favorites_manager.open_item(index)
            elif selected == edit_action:
                self._edit_favorite_dialog(index)
            elif selected == delete_action:
                self.favorites_manager.remove(index)
        finally:
            self._restore_detail_page(FEATURE_FAVORITES)
        self._request_update()

    def _show_file_item_menu(self, index: int, global_pos: QPoint) -> None:
        if self.file_hub_manager is None:
            return
        menu = QMenu(self)
        open_action = menu.addAction(tr(self.language, "file_menu_open"))
        location_action = menu.addAction(tr(self.language, "file_menu_open_location"))
        copy_path_action = menu.addAction(tr(self.language, "file_menu_copy_path"))
        remove_action = menu.addAction(tr(self.language, "file_menu_remove"))
        self.outside_click_timer.stop()
        try:
            selected = menu.exec(global_pos)
            if selected == open_action:
                self.file_hub_manager.open_item(index)
            elif selected == location_action:
                self.file_hub_manager.open_location(index)
            elif selected == copy_path_action:
                QApplication.clipboard().setText(self.file_hub_manager.copy_path(index))
            elif selected == remove_action:
                self.file_hub_manager.remove(index)
        finally:
            self._restore_detail_page(FEATURE_FILES)
        self._request_update()

    def _maybe_start_file_drag(self, pos: QPointF) -> bool:
        if self.file_drag_index is None or self.file_hub_manager is None:
            return False
        if (pos - self.file_press_pos).manhattanLength() < QApplication.startDragDistance():
            return False
        urls = self.file_hub_manager.urls_for_index(self.file_drag_index)
        if not urls:
            self.file_drag_index = None
            return False
        drag = QDrag(self)
        mime = QMimeData()
        mime.setUrls(urls)
        drag.setMimeData(mime)
        self.file_drag_index = None
        drag.exec(Qt.DropAction.CopyAction)
        return True

    def _show_clipboard_item_menu(self, index: int, global_pos: QPoint) -> None:
        if self.clipboard_manager is None:
            return
        menu = QMenu(self)
        copy_action = menu.addAction(tr(self.language, "clipboard_menu_copy"))
        delete_action = menu.addAction(tr(self.language, "clipboard_menu_delete"))
        self.outside_click_timer.stop()
        try:
            selected = menu.exec(global_pos)
            if selected == copy_action:
                self.clipboard_manager.copy_to_clipboard(index)
            elif selected == delete_action:
                self.clipboard_manager.delete_item(index)
                self.clipboard_scroll_y = self._clamp_clipboard_scroll(self.clipboard_scroll_y)
        finally:
            self._restore_detail_page(FEATURE_CLIPBOARD)
        self._request_update()

    def _clipboard_content_height(self) -> float:
        if self.clipboard_manager is None:
            return 0.0
        row_h = 42
        spacing = 8
        return max(0.0, len(self.clipboard_manager.items) * (row_h + spacing) - spacing)

    def _clamp_clipboard_scroll(self, value: float, content_height: float | None = None, viewport_height: float | None = None) -> float:
        content_height = self._clipboard_content_height() if content_height is None else content_height
        viewport_height = self.clipboard_list_viewport_rect.height() if viewport_height is None else viewport_height
        max_scroll = max(0.0, content_height - max(1.0, viewport_height))
        return max(0.0, min(max_scroll, float(value)))

    def _scroll_clipboard_items(self, delta_pixels: int) -> None:
        if self.clipboard_manager is None:
            return
        next_y = self._clamp_clipboard_scroll(self.clipboard_scroll_y + delta_pixels * 0.42)
        if abs(next_y - self.clipboard_scroll_y) < 0.5:
            return
        self.clipboard_scroll_y = next_y
        self._request_update()

    def _drag_clipboard_scrollbar(self, pos: QPointF) -> None:
        if not self.clipboard_scrollbar_track_rect.isValid() or self.clipboard_scrollbar_thumb_rect.height() <= 0:
            return
        content_height = self._clipboard_content_height()
        viewport_height = max(1.0, self.clipboard_list_viewport_rect.height())
        max_scroll = max(0.0, content_height - viewport_height)
        movable = max(1.0, self.clipboard_scrollbar_track_rect.height() - self.clipboard_scrollbar_thumb_rect.height())
        delta = pos.y() - self.clipboard_scrollbar_drag_start_y
        next_y = self.clipboard_scrollbar_drag_start_scroll_y + (delta / movable) * max_scroll
        next_y = self._clamp_clipboard_scroll(next_y, content_height, viewport_height)
        if abs(next_y - self.clipboard_scroll_y) < 0.5:
            return
        self.clipboard_scroll_y = next_y
        self._request_update()

    def _scroll_file_items(self, direction: int) -> None:
        if self.file_hub_manager is None:
            return
        visible_count = max(1, len(self.file_item_rects))
        max_offset = max(0, len(self.file_hub_manager.items) - visible_count)
        next_offset = max(0, min(max_offset, self.file_scroll_offset + direction))
        if next_offset == self.file_scroll_offset:
            return
        self.file_scroll_offset = next_offset
        self._request_update()

    def _scroll_favorite_items(self, direction: int) -> None:
        if self.favorites_manager is None:
            return
        visible_count = max(1, len(self.favorite_item_rects))
        max_offset = max(0, len(self.favorites_manager.items) - visible_count)
        next_offset = max(0, min(max_offset, self.favorites_scroll_offset + direction))
        if next_offset == self.favorites_scroll_offset:
            return
        self.favorites_scroll_offset = next_offset
        self._request_update()

    def _prepare_clipboard_drag(self, pos: QPointF) -> None:
        self._reset_clipboard_drag_state()
        index = self._clipboard_item_at(pos)
        if index is None:
            return
        self.clipboard_pressed_index = index
        self.clipboard_press_pos = QPointF(pos)
        self.clipboard_long_press_ready = False
        self.clipboard_drag_started = False
        self.clipboard_drag_consumed = False
        self.clipboard_drag_timer.start(CLIPBOARD_DRAG_HOLD_MS)

    def _mark_clipboard_long_press_ready(self) -> None:
        if self.clipboard_pressed_index is not None:
            self.clipboard_long_press_ready = True

    def _reset_clipboard_drag_state(self) -> None:
        self.clipboard_drag_timer.stop()
        self.clipboard_pressed_index = None
        self.clipboard_long_press_ready = False
        self.clipboard_drag_started = False
        self.clipboard_drag_consumed = False

    def _maybe_start_clipboard_drag(self, pos: QPointF) -> bool:
        if self.clipboard_pressed_index is None or self.clipboard_manager is None:
            return False
        distance = (pos - self.clipboard_press_pos).manhattanLength()
        if distance < QApplication.startDragDistance() and not self.clipboard_long_press_ready:
            return False
        if self.clipboard_pressed_index >= len(self.clipboard_manager.items):
            self._reset_clipboard_drag_state()
            return False
        text = str(self.clipboard_manager.items[self.clipboard_pressed_index].get("text", ""))
        if not text:
            self._reset_clipboard_drag_state()
            return False
        self.clipboard_drag_started = True
        mime = QMimeData()
        mime.setText(text)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)
        self.clipboard_drag_timer.stop()
        self.clipboard_pressed_index = None
        self.clipboard_long_press_ready = False
        self.clipboard_drag_consumed = True
        return True

    def _handle_expanded_click(self, pos: QPoint) -> None:
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if self.expanded_hit_rects.get("search", QRectF()).contains(pos):
            self.search_focused = True
            self.search_edit.show()
            self.search_edit.setFocus(Qt.FocusReason.MouseFocusReason)
            self._request_update()
            return

        self.search_focused = False
        self.search_edit.clearFocus()
        if self.current_view == VIEW_HOME and self.expanded_hit_rects.get("settings", QRectF()).contains(pos):
            self._open_settings_from_header()
            return
        if self._search_results_active():
            for index, rect in self.search_result_rects:
                if rect.contains(pos):
                    self.selected_search_index = index
                    self.execute_search_selection()
                    return
            for index, rect in self.web_suggestion_rects:
                if rect.contains(pos):
                    self.selected_search_index = len(self.local_search_results) + index
                    self.execute_search_selection()
                    return
            if self.expanded_hit_rects.get("feature_area", QRectF()).contains(pos):
                self._request_update()
                return
        if self.current_view == VIEW_DETAIL:
            if self.expanded_hit_rects.get("back", QRectF()).contains(pos):
                self.current_view = VIEW_HOME
                self._restart_page_transition()
                self._request_update()
                return
            for key, rect in self.action_button_rects:
                if rect.contains(pos):
                    self._handle_action(key)
                    return
            if self._current_feature() == FEATURE_CLIPBOARD:
                for index, rect in self.clipboard_item_rects:
                    if rect.contains(pos):
                        if self.clipboard_manager is not None:
                            self.clipboard_manager.copy_to_clipboard(index)
                        self._request_update()
                        return
            if self._current_feature() == FEATURE_FILES:
                for index, rect in self.file_item_rects:
                    if rect.contains(pos):
                        if self.file_hub_manager is not None:
                            self.file_hub_manager.open_item(index)
                        self._request_update()
                        return
            if self._current_feature() == FEATURE_FAVORITES:
                for index, rect in self.favorite_item_rects:
                    if rect.contains(pos):
                        if self.favorites_manager is not None:
                            self.favorites_manager.open_item(index)
                        self._request_update()
                        return
            if self.expanded_hit_rects.get("header", QRectF()).contains(pos):
                self._request_update()
                return
            self._request_update()
            return

        for index, rect in self.feature_dot_rects:
            if rect.contains(pos):
                self.current_feature_index = index
                self._restart_feature_switch_animation()
                self._request_update()
                return
        if self.feature_hit_rect.contains(pos):
            self.enter_feature_detail(self._current_feature())
            return
        if self.expanded_hit_rects.get("header", QRectF()).contains(pos):
            self.set_expanded(False)
            return
        self._request_update()

    def _open_settings_from_header(self) -> None:
        self.search_edit.clearFocus()
        self.search_focused = False
        if self.open_settings_callback is not None:
            self.open_settings_callback()
        self._request_update()

    def enter_feature_detail(self, feature: str) -> None:
        if feature not in self.features:
            return
        self.current_feature_index = self.features.index(feature)
        self.current_view = VIEW_DETAIL
        self.clipboard_scroll_offset = 0
        self.clipboard_scroll_y = 0.0
        self.clipboard_scrollbar_dragging = False
        self.file_scroll_offset = 0
        self.favorites_scroll_offset = 0
        self.search_focused = False
        self.search_edit.clearFocus()
        self._restart_page_transition()
        self._request_update()

    def _switch_feature(self, direction: int) -> None:
        if not self.features:
            return
        self.current_feature_index = (self.current_feature_index + direction) % len(self.features)
        self._restart_feature_switch_animation()
        self._request_update()

    def _restart_feature_switch_animation(self) -> None:
        self._restart_page_transition()

    def _restart_page_transition(self) -> None:
        self.page_transition_progress = 0.0
        channel = self.animation_channels["page"]
        channel.value = 0.0
        self._animate_channel("page", 1.0, PAGE_SWITCH_DURATION_MS, "out_cubic")

    def _current_feature(self) -> str:
        return self.features[self.current_feature_index % len(self.features)]

    def _feature_title(self, feature: str) -> str:
        return tr(self.language, f"feature_{feature}_title")

    def _feature_description(self, feature: str) -> str:
        return tr(self.language, f"feature_{feature}_description")

    @staticmethod
    def _feature_detail_key(feature: str) -> str:
        return f"feature_{feature}_detail"

    def _handle_action(self, key: str) -> None:
        if self._current_feature() == FEATURE_CLIPBOARD and self.clipboard_manager is not None:
            if key == "action_clear":
                self.clipboard_manager.clear()
            elif key in ("action_pause", "action_resume"):
                self.clipboard_manager.toggle_paused()
        elif self._current_feature() == FEATURE_FILES and self.file_hub_manager is not None:
            if key == "action_clear":
                self.file_hub_manager.clear()
            elif key == "action_add":
                self.outside_click_timer.stop()
                try:
                    paths, _ = QFileDialog.getOpenFileNames(self, tr(self.language, "file_hub_add_files"))
                    if paths:
                        self.file_hub_manager.add_paths(paths)
                finally:
                    self._restore_detail_page(FEATURE_FILES)
        elif self._current_feature() == FEATURE_FAVORITES and self.favorites_manager is not None:
            if key == "action_add":
                self._add_favorite_dialog()
        self._request_update()

    def _restore_detail_page(self, feature: str) -> None:
        if self.state != STATE_EXPANDED or feature not in self.features:
            return
        self.current_feature_index = self.features.index(feature)
        self.current_view = VIEW_DETAIL
        self.search_edit.clearFocus()
        self.search_focused = False
        self._sync_outside_click_watch()
        self._request_update()

    def _feature_actions(self, feature: str) -> list[str]:
        if feature == FEATURE_CLIPBOARD:
            if self.clipboard_manager is not None and self.clipboard_manager.paused:
                return ["action_clear", "action_resume"]
            return ["action_clear", "action_pause"]
        if feature == FEATURE_FILES:
            return ["action_clear", "action_add"]
        if feature == FEATURE_FAVORITES:
            return ["action_add"]
        return []

    def _add_favorite_dialog(self) -> None:
        if self.favorites_manager is None:
            return
        menu = QMenu(self)
        url_action = menu.addAction(tr(self.language, "favorite_add_url"))
        file_action = menu.addAction(tr(self.language, "favorite_add_file"))
        folder_action = menu.addAction(tr(self.language, "favorite_add_folder"))
        app_action = menu.addAction(tr(self.language, "favorite_add_app"))
        self.outside_click_timer.stop()
        try:
            selected = menu.exec(QCursor.pos())
            if selected == url_action:
                dialog = FavoriteUrlDialog(self.language, self)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    self.favorites_manager.add_url(dialog.title_value, dialog.url_value)
            elif selected == file_action:
                path, _ = QFileDialog.getOpenFileName(self, tr(self.language, "favorite_add_file"))
                if path:
                    self.favorites_manager.add_path(path, "file")
            elif selected == folder_action:
                path = QFileDialog.getExistingDirectory(self, tr(self.language, "favorite_add_folder"))
                if path:
                    self.favorites_manager.add_path(path, "folder")
            elif selected == app_action:
                path, _ = QFileDialog.getOpenFileName(
                    self,
                    tr(self.language, "favorite_add_app"),
                    "",
                    "Applications (*.exe *.lnk);;All Files (*)",
                )
                if path:
                    self.favorites_manager.add_path(path, "app")
        finally:
            self._restore_detail_page(FEATURE_FAVORITES)

    def _edit_favorite_dialog(self, index: int) -> None:
        if self.favorites_manager is None or index < 0 or index >= len(self.favorites_manager.items):
            return
        item = self.favorites_manager.items[index]
        title, ok = QInputDialog.getText(
            self,
            tr(self.language, "favorite_menu_edit"),
            tr(self.language, "favorite_title_label"),
            text=str(item.get("title", "")),
        )
        if not ok:
            return
        target, ok = QInputDialog.getText(
            self,
            tr(self.language, "favorite_menu_edit"),
            tr(self.language, "favorite_target_label"),
            text=str(item.get("target", "")),
        )
        if ok and target.strip():
            self.favorites_manager.update_item(index, title, target)

    def _draw_status_items(self, painter: QPainter, items: list[tuple[str, str]], right_x: float, center_y: float, color: QColor) -> None:
        cursor = right_x
        for key, text in reversed(items):
            font = self.time_font if key == "time" else self.status_font
            metrics = self.time_metrics if key == "time" else self.status_metrics
            painter.setFont(font)
            painter.setPen(color)
            width = metrics.horizontalAdvance(text)
            x = int(cursor - width)
            y = int(center_y + (metrics.ascent() - metrics.descent()) / 2)
            painter.drawText(x, y, text)
            cursor = x - STATUS_GAP

    def _animate_channel(self, name: str, target: float, duration_ms: int, easing: str = "out_cubic") -> None:
        channel = self.animation_channels[name]
        target = float(target)
        if channel.active and abs(channel.end - target) < 0.001:
            return
        if abs(channel.value - target) < 0.001:
            channel.value = target
            channel.active = False
            self._apply_channel_value(name, target)
            self._handle_channel_finished(name)
            self._stop_animation_tick_if_idle()
            return
        if not self.animation_enabled or not self.isVisible():
            channel.value = target
            channel.active = False
            self._apply_channel_value(name, target)
            self._handle_channel_finished(name)
            self._request_update()
            self._stop_animation_tick_if_idle()
            return

        channel.start = channel.value
        channel.end = target
        channel.duration_ms = max(1, int(duration_ms))
        channel.elapsed_ms = 0.0
        channel.easing = easing
        channel.active = True
        self._ensure_animation_tick()

    def _animate_shape_to(self, body_width: int, body_height: int, radius: int, duration: int = WIDTH_ANIMATION_DURATION_MS) -> None:
        max_body_width = max(1, self.responsive_metrics.expanded_width, self.responsive_metrics.collapsed_max_width)
        safe_width = int(max(1, min(int(body_width), max_body_width)))
        safe_height = int(max(1, body_height))
        safe_radius = int(max(0, min(int(radius), safe_height / 2)))
        target = (safe_width, safe_height, safe_radius)
        current = (round(self.current_body_width), round(self.current_body_height), round(self.current_radius))
        if current == target:
            self._shape_motion_mode = "linear"
            self._set_shape_metrics(*target)
            return
        if self.animation_channels["width"].active and self._shape_target == target:
            return
        self._shape_start = (self.current_body_width, self.current_body_height, self.current_radius)
        self._shape_target = target
        if duration == EXPAND_ANIMATION_DURATION_MS and target[1] >= round(self.current_body_height):
            self._shape_motion_mode = "expand"
        elif duration == COLLAPSE_ANIMATION_DURATION_MS and target[1] <= round(self.current_body_height):
            self._shape_motion_mode = "collapse"
        else:
            self._shape_motion_mode = "linear"
        width_channel = self.animation_channels["width"]
        width_channel.value = 0.0
        if not self.animation_enabled or not self.isVisible():
            width_channel.active = False
            self._set_shape_metrics(*target)
            self._stop_animation_tick_if_idle()
            return

        width_channel.start = 0.0
        width_channel.end = 1.0
        width_channel.duration_ms = max(1, int(duration))
        width_channel.elapsed_ms = 0.0
        width_channel.easing = "linear" if self._shape_motion_mode in ("expand", "collapse") else "out_cubic"
        width_channel.active = True
        self._ensure_animation_tick()

    def _apply_channel_value(self, name: str, value: float) -> None:
        clamped = max(0.0, min(1.0, float(value)))
        if name == "hover":
            self.hover_progress = clamped
        elif name == "press":
            self.press_progress = clamped
        elif name == "hidden":
            self.hidden_progress = clamped
        elif name == "expand":
            self.expand_progress = clamped
        elif name == "page":
            self.page_transition_progress = clamped
        elif name == "content":
            self.content_fade_progress = clamped
        elif name == "focus_ring":
            self.focus_ring_progress = clamped
        elif name == "search_sweep":
            self.search_sweep_progress = clamped
        elif name == "feature_hover":
            self.feature_hover_progress = clamped
        elif name == "url_prompt":
            self.url_prompt_progress = clamped
        elif name == "music_preview":
            self.music_preview_progress = clamped
        elif name == "width":
            self._apply_shape_progress(clamped)

    def _apply_shape_progress(self, progress: float) -> None:
        t = max(0.0, min(1.0, progress))
        if self._shape_motion_mode == "expand":
            width_progress = staged_expand_width(t)
            height_progress = staged_expand_height(t)
            radius_progress = staged_expand_radius(t)
        elif self._shape_motion_mode == "collapse":
            width_progress = ease_in_out_cubic(remap_progress(t, 0.22, 1.00))
            height_progress = ease_in_out_cubic(remap_progress(t, 0.00, 0.78))
            radius_progress = ease_in_out_cubic(remap_progress(t, 0.12, 1.00))
        else:
            width_progress = t
            height_progress = t
            radius_progress = t
        eased_width = self._shape_start[0] + (self._shape_target[0] - self._shape_start[0]) * width_progress
        eased_height = self._shape_start[1] + (self._shape_target[1] - self._shape_start[1]) * height_progress
        eased_radius = self._shape_start[2] + (self._shape_target[2] - self._shape_start[2]) * radius_progress
        self._set_shape_metrics(eased_width, eased_height, eased_radius, request_update=False)

    def _set_shape_metrics(self, body_width: float, body_height: float, radius: float, request_update: bool = True) -> None:
        max_body_width = max(1, self.responsive_metrics.expanded_width, self.responsive_metrics.collapsed_max_width)
        safe_height = max(1.0, float(body_height))
        self.current_body_width = max(1, min(float(body_width), float(max_body_width)))
        self.current_body_height = safe_height
        self.current_radius = max(0, min(float(radius), safe_height / 2.0))
        if request_update:
            self.apply_visual_geometry()
            self._request_update()

    def _ensure_animation_tick(self) -> None:
        if not self.animation_enabled or not self.isVisible():
            self._stop_animation_tick_if_idle()
            return
        interval = self._target_tick_interval()
        if not self.animation_timer.isActive():
            self.animation_clock.restart()
            self.animation_timer.start(interval)
        elif self.animation_timer.interval() != interval:
            self.animation_timer.setInterval(interval)

    def _stop_animation_tick_if_idle(self) -> None:
        if not self._has_active_animations():
            self.animation_timer.stop()
            return
        if self.animation_timer.isActive():
            interval = self._target_tick_interval()
            if self.animation_timer.interval() != interval:
                self.animation_timer.setInterval(interval)

    def _target_tick_interval(self) -> int:
        if any(channel.active for channel in self.animation_channels.values()):
            return self.current_animation_interval_ms
        if self._feature_pulse_active():
            return FEATURE_PULSE_FRAME_INTERVAL_MS
        if self._search_focus_flow_active():
            return SEARCH_FLOW_FRAME_INTERVAL_MS
        return self.current_animation_interval_ms

    def _has_active_animations(self) -> bool:
        return (
            any(channel.active for channel in self.animation_channels.values())
            or self._search_focus_flow_active()
            or self._feature_pulse_active()
        )

    def _search_focus_flow_active(self) -> bool:
        return (
            self.animation_enabled
            and self.search_focused
            and self.state == STATE_EXPANDED
            and self.search_edit.isVisible()
            and self.focus_ring_progress > 0.98
        )

    def _feature_pulse_active(self) -> bool:
        return (
            self.animation_enabled
            and self.feature_hovered
            and self.state == STATE_EXPANDED
            and self.current_view == VIEW_HOME
            and self.content_fade_progress > 0.98
            and self.feature_hover_progress > 0.98
        )

    def _on_animation_tick(self) -> None:
        if not self.animation_enabled or not self.isVisible():
            self._stop_animations()
            return

        elapsed_ms = max(1, self.animation_clock.restart())
        self._tick_count += 1
        self._perf_tick_count += 1
        changed = False

        active_names = [name for name, channel in self.animation_channels.items() if channel.active]
        for name in active_names:
            channel = self.animation_channels[name]
            if not channel.active:
                continue
            channel.elapsed_ms += elapsed_ms
            raw_progress = min(1.0, channel.elapsed_ms / channel.duration_ms)
            eased = self._ease(raw_progress, channel.easing)
            channel.value = channel.start + (channel.end - channel.start) * eased
            if raw_progress >= 1.0:
                channel.value = channel.end
                channel.active = False
            self._apply_channel_value(name, channel.value)
            changed = True
            if not channel.active:
                self._handle_channel_finished(name)

        if self._search_focus_flow_active():
            self.search_focus_flow_phase = (
                self.search_focus_flow_phase + elapsed_ms / SEARCH_FOCUS_FLOW_PERIOD_MS
            ) % 1.0
            changed = True

        if self._feature_pulse_active():
            self.feature_pulse_phase = (
                self.feature_pulse_phase + elapsed_ms / FEATURE_PULSE_PERIOD_MS
            ) % 1.0
            changed = True

        if self.expand_direction == "expand" and self.expand_target_state == STATE_EXPANDED and self.expand_progress >= 0.92:
            self.state = STATE_EXPANDED
            self._start_content_fade()

        self._maybe_downgrade_animation_tick()
        if changed:
            self.apply_visual_geometry()
            self._request_update()
        self._stop_animation_tick_if_idle()

    def _maybe_downgrade_animation_tick(self) -> None:
        if not self.high_refresh_enabled:
            return

        now = time.monotonic()
        elapsed = now - self._perf_window_start
        if elapsed < 1.0:
            return

        tick_fps = self._perf_tick_count / max(0.001, elapsed)
        self._perf_tick_count = 0
        self._perf_window_start = now

        if tick_fps < 90:
            self._low_tick_fps_seconds += 1
        else:
            self._low_tick_fps_seconds = 0

        if self._low_tick_fps_seconds >= 2:
            self.high_refresh_enabled = False
            self.current_animation_interval_ms = FALLBACK_FRAME_INTERVAL_MS
            if self.animation_timer.isActive():
                self.animation_timer.setInterval(self.current_animation_interval_ms)

    @staticmethod
    def _ease(progress: float, easing: str) -> float:
        t = max(0.0, min(1.0, progress))
        if easing == "out_quint":
            return ease_out_quint(t)
        if easing == "out_cubic":
            return ease_out_cubic(t)
        if easing == "in_out_cubic":
            return ease_in_out_cubic(t)
        if easing == "smoother":
            return ease_smoother(t)
        if easing == "linear":
            return t
        return 1 - (1 - t) ** 3

    def _handle_channel_finished(self, name: str) -> None:
        if name == "expand":
            if self.expand_target_state == STATE_EXPANDED and self.expand_progress >= 1.0:
                self._finish_expand_transition()
            elif self.expand_target_state == STATE_COLLAPSED and self.expand_progress <= 0.0:
                self._finish_collapse_transition()

    def _start_content_fade(self) -> None:
        if self.expand_direction == "collapse" or self.state != STATE_EXPANDED:
            return
        if self.content_fade_progress >= 0.999 or self.animation_channels["content"].active:
            return
        if not self.animation_enabled or not self.isVisible():
            self.content_fade_progress = 1.0
            self.animation_channels["content"].value = 1.0
            self._request_update()
            return
        self._animate_channel("content", 1.0, CONTENT_FADE_DURATION_MS, "out_cubic")

    def _finish_expand_transition(self) -> None:
        self.state = STATE_EXPANDED
        self.is_expanded = True
        self.is_collapsed_hidden = False
        self.expand_target_state = None
        self.expand_direction = None
        self.expand_progress = 1.0
        self.hidden_progress = 0.0
        width, height, radius = self._expanded_target_metrics()
        self.current_body_width = float(width)
        self.current_body_height = float(height)
        self.current_radius = float(radius)
        self._shape_motion_mode = "linear"
        self.animation_channels["expand"].value = 1.0
        self.animation_channels["hidden"].value = 0.0
        self.animation_channels["width"].value = 1.0
        self.apply_visual_geometry()
        self._start_content_fade()
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        self._outside_prev_left_down = _is_global_left_button_down()
        QTimer.singleShot(OUTSIDE_CLICK_ARM_DELAY_MS, self._start_outside_click_watch)

    def _finish_collapse_transition(self) -> None:
        self.state = STATE_COLLAPSED
        self.is_expanded = False
        self.expand_target_state = None
        self.expand_direction = None
        self.expand_progress = 0.0
        collapsed_width = self._calculate_auto_body_width()
        self.auto_body_width_target = collapsed_width
        self.current_body_width = float(collapsed_width)
        self.current_body_height = float(self.base_body_height)
        self.current_radius = float(self.base_radius)
        self._shape_motion_mode = "linear"
        self.animation_channels["expand"].value = 0.0
        self.animation_channels["width"].value = 1.0
        self.apply_visual_geometry()
        if self.pending_hide_after_collapse:
            self.pending_hide_after_collapse = False
            self.set_hidden(True)
            return
        if self._schedule_auto_hide_after_collapse:
            self._schedule_auto_hide_if_needed()

    def _schedule_auto_hide_if_needed(self) -> None:
        if not self.auto_hide_enabled:
            self.auto_hide_timer.stop()
            return
        if not self.isVisible() or self.state != STATE_COLLAPSED:
            self.auto_hide_timer.stop()
            return
        if self.underMouse():
            self.auto_hide_timer.stop()
            return
        delay_ms = self.auto_hide_delay_seconds * 1000
        if self.auto_hide_timer.isActive() and self.auto_hide_timer.interval() == delay_ms:
            return
        self.auto_hide_timer.start(delay_ms)

    def _handle_auto_hide_timeout(self) -> None:
        if not self.auto_hide_enabled:
            return
        if not self.isVisible() or self.underMouse() or self.state != STATE_COLLAPSED:
            return
        self.set_hidden(True)

    def _sync_outside_click_watch(self) -> None:
        if self.state == STATE_EXPANDED and self.collapse_on_outside_click and self.isVisible():
            self._start_outside_click_watch()
        else:
            self.outside_click_timer.stop()
            self._outside_prev_left_down = False

    def _start_outside_click_watch(self) -> None:
        if self.state == STATE_EXPANDED and self.collapse_on_outside_click and self.isVisible():
            self._outside_prev_left_down = _is_global_left_button_down()
            if not self.outside_click_timer.isActive():
                self.outside_click_timer.start(OUTSIDE_CLICK_INTERVAL_MS)

    def _check_outside_click(self) -> None:
        if self.state != STATE_EXPANDED or not self.collapse_on_outside_click or not self.isVisible():
            self.outside_click_timer.stop()
            self._outside_prev_left_down = False
            return

        left_down = _is_global_left_button_down()
        if left_down and not self._outside_prev_left_down and not self.frameGeometry().contains(QCursor.pos()):
            self.outside_click_timer.stop()
            self._outside_prev_left_down = left_down
            self.set_expanded(False)
            return
        self._outside_prev_left_down = left_down

    def _status_enabled(self) -> bool:
        return self.show_time or self.show_cpu or self.show_memory or self.show_network

    def _restart_status_timer(self) -> None:
        if self.isVisible() and self.state != STATE_HIDDEN and self._status_enabled():
            if self.status_timer.interval() != self.status_update_interval_ms:
                self.status_timer.setInterval(self.status_update_interval_ms)
            if not self.status_timer.isActive():
                self.status_timer.start()
            return
        self.status_timer.stop()

    def _update_status_snapshot(self) -> None:
        if not self.isVisible() and self.status_timer.isActive():
            return
        changed = False
        if self.show_time:
            next_time = self._format_time()
            if next_time != self.current_time:
                self.current_time = next_time
                changed = True
        if self.show_cpu or self.show_memory or self.show_network:
            snapshot = self.stats_sampler.sample(self.show_cpu, self.show_memory, self.show_network)
            next_values = {
                "cpu": snapshot.cpu_text,
                "memory": snapshot.memory_text,
                "network": snapshot.network_text,
            }
        else:
            next_values = {"cpu": None, "memory": None, "network": None}

        for key, value in next_values.items():
            if self.status_values.get(key) != value:
                self.status_values[key] = value
                changed = True

        if (
            changed
            and self.isVisible()
            and self.state == STATE_COLLAPSED
            and self.expand_target_state is None
            and not self.is_collapsed_hidden
        ):
            self._request_update()

    def _update_auto_width(self, force: bool = False, duration: int = WIDTH_ANIMATION_DURATION_MS) -> None:
        target_width = self._calculate_auto_body_width()
        shape_target = (target_width, self.base_body_height, self.base_radius)
        if self.expand_target_state is not None:
            self.auto_body_width_target = target_width
            return
        if self.state == STATE_EXPANDED:
            self.auto_body_width_target = target_width
            return

        if self.animation_channels["width"].active and self._shape_target == shape_target:
            return

        target_delta = abs(target_width - self.auto_body_width_target)
        height_delta = abs(round(self.current_body_height) - self.base_body_height)
        radius_delta = abs(round(self.current_radius) - self.base_radius)
        expected_window_width = int(round(self.current_body_width + SHADOW_MARGIN_X * 2))
        expected_window_height = int(round(self.current_body_height + SHADOW_MARGIN_BOTTOM))
        geometry_matches = self.width() == expected_window_width and self.height() == expected_window_height
        if target_delta < WIDTH_CHANGE_THRESHOLD and height_delta == 0 and radius_delta == 0 and geometry_matches:
            self.auto_body_width_target = target_width
            return

        self.auto_body_width_target = target_width
        self._animate_shape_to(target_width, self.base_body_height, self.base_radius, duration)

    def _calculate_auto_body_width(self) -> int:
        max_auto_width = min(AUTO_WIDTH_MAX, self.responsive_metrics.collapsed_max_width)
        if self.url_prompt_active or self.drive_prompt_active:
            title = tr(self.language, "url_prompt_title")
            action = tr(self.language, "url_prompt_action")
            if self.drive_prompt_active:
                title = tr(self.language, "drive_prompt_title").format(
                    name=self.drive_prompt_name or self.drive_prompt_path
                )
                action = tr(self.language, "drive_prompt_action")
            prompt_width = 6 + 10 + self.brand_metrics.horizontalAdvance(title)
            prompt_width += self.status_metrics.horizontalAdvance(action) + 22 * 2 + AUTO_WIDTH_EXTRA_PADDING
            target = min(max_auto_width, max(self.base_body_width, int(prompt_width)))
            return int(min(max_auto_width, (target + 3) // 4 * 4))
        full_status_width = self._measure_status_items(self._status_slot_items())
        required = self._left_content_width() + full_status_width + 22 * 2 + AUTO_WIDTH_EXTRA_PADDING
        target = min(max_auto_width, max(self.base_body_width, int(required)))
        return int(min(max_auto_width, (target + 3) // 4 * 4))

    def _status_available_width(self) -> int:
        return max(0, int(self.current_body_width - self._left_content_width() - 22 * 2 - 18))

    def _left_content_width(self) -> int:
        return 6 + 10 + self.brand_metrics.horizontalAdvance(self.brand_text)

    def _status_slot_items(self) -> list[tuple[str, str]]:
        items = []
        if self.show_network:
            items.append(("network", STATUS_SLOT_TEMPLATES["network"]))
        if self.show_cpu:
            items.append(("cpu", STATUS_SLOT_TEMPLATES["cpu"]))
        if self.show_memory:
            items.append(("memory", STATUS_SLOT_TEMPLATES["memory"]))
        if self.show_time:
            items.append(("time", STATUS_SLOT_TEMPLATES["time"]))
        return items

    def _status_items_full(self) -> list[tuple[str, str]]:
        items = []
        network = self.status_values.get("network")
        cpu = self.status_values.get("cpu")
        memory = self.status_values.get("memory")
        if self.show_network and network:
            items.append(("network", network))
        if self.show_cpu and cpu:
            items.append(("cpu", cpu))
        if self.show_memory and memory:
            items.append(("memory", memory))
        if self.show_time:
            items.append(("time", self.current_time))
        return items

    def _visible_status_items(self, max_width: int) -> list[tuple[str, str]]:
        items = self._status_items_full()
        for key in ("memory", "cpu", "network", "time"):
            if self._measure_status_items(items) <= max_width:
                return items
            if key == "time" and self.show_time:
                items = [item for item in items if item[0] != key]
            elif key != "time":
                items = [item for item in items if item[0] != key]
        return items if self._measure_status_items(items) <= max_width else []

    def _measure_status_items(self, items: list[tuple[str, str]]) -> int:
        if not items:
            return 0
        total = 0
        for key, text in items:
            metrics = self.time_metrics if key == "time" else self.status_metrics
            total += metrics.horizontalAdvance(text)
        total += STATUS_GAP * max(0, len(items) - 1)
        return total

    @staticmethod
    def _make_ui_font(pixel_size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
        font = QFont()
        try:
            font.setFamilies([FONT_UI, FONT_FALLBACK, "Segoe UI Emoji"])
        except Exception:
            font.setFamily(FONT_UI)
        font.setPixelSize(pixel_size)
        font.setWeight(weight)
        try:
            font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
            font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        except Exception:
            pass
        return font

    def _build_paint_cache(self) -> None:
        self.brand_font = self._make_ui_font(13, QFont.Weight.DemiBold)
        self.brand_metrics = QFontMetrics(self.brand_font)

        self.status_font = self._make_ui_font(11, QFont.Weight.Normal)
        self.status_metrics = QFontMetrics(self.status_font)

        self.time_font = self._make_ui_font(14, QFont.Weight.Bold)
        self.time_metrics = QFontMetrics(self.time_font)

        self.panel_title_font = self._make_ui_font(18, QFont.Weight.DemiBold)
        self.panel_title_metrics = QFontMetrics(self.panel_title_font)

        self.header_title_font = self._make_ui_font(15, QFont.Weight.DemiBold)
        self.header_title_metrics = QFontMetrics(self.header_title_font)

        self.feature_title_font = self._make_ui_font(23, QFont.Weight.Bold)
        self.feature_title_metrics = QFontMetrics(self.feature_title_font)

        self.feature_desc_font = self._make_ui_font(13, QFont.Weight.Normal)
        self.feature_desc_metrics = QFontMetrics(self.feature_desc_font)

        self.list_title_font = self._make_ui_font(13, QFont.Weight.DemiBold)
        self.list_title_metrics = QFontMetrics(self.list_title_font)

        self.list_subtitle_font = self._make_ui_font(11, QFont.Weight.Normal)
        self.list_subtitle_metrics = QFontMetrics(self.list_subtitle_font)

        self.search_font = self._make_ui_font(14, QFont.Weight.Normal)
        self.search_metrics = QFontMetrics(self.search_font)

        self.action_font = self._make_ui_font(12, QFont.Weight.DemiBold)
        self.action_metrics = QFontMetrics(self.action_font)

        self.panel_placeholder_font = self._make_ui_font(13, QFont.Weight.DemiBold)
        self.panel_placeholder_metrics = QFontMetrics(self.panel_placeholder_font)

        self.body_color = QColor("#000000")
        self.panel_title_color = QColor("#f4f4f5")
        self.panel_text_color = QColor("#a1a1aa")
        self.panel_muted_color = QColor(126, 126, 135)
        self.separator_color = QColor(28, 28, 32)
        self.icon_color = QColor(226, 226, 232)
        self.icon_hover_color = QColor(248, 248, 250)
        self.icon_plate_color = QColor(255, 255, 255, 12)
        self.icon_plate_hover_color = QColor(255, 255, 255, 20)
        self.soft_border_color = QColor(255, 255, 255, 28)
        self.control_fill_color = QColor(32, 32, 36, 170)
        self.detail_card_color = QColor(18, 18, 22, 190)
        self.search_fill_color = QColor(28, 28, 32, 180)
        self.search_highlight_color = QColor(255, 255, 255, 22)
        self.search_bottom_shade_color = QColor(0, 0, 0, 26)
        self.search_line_color = QColor(255, 255, 255, 18)
        self.search_border_color = QColor(255, 255, 255, 28)
        self.search_border_focused = QColor(245, 245, 247, 86)
        self.panel_placeholder_text = tr(self.language, "panel_placeholder")

    def _request_update(self) -> None:
        if self.isVisible():
            self.update()

    def _print_performance_debug(self) -> None:
        now = time.monotonic()
        elapsed = max(0.001, now - self._debug_last_tick)
        avg_paint_ms = self._paint_total_ms / self._paint_count if self._paint_count else 0.0
        layout = self._last_visual_layout or self.compute_visual_layout()
        print(
            f"[OneBar perf] paint_fps={self._paint_count / elapsed:.1f} "
            f"tick_fps={self._tick_count / elapsed:.1f} "
            f"active_animations={self._active_animation_count()} "
            f"avg_paint_ms={avg_paint_ms:.2f} "
            f"expand_progress={self.expand_progress:.2f} "
            f"collapsed_content_alpha={self._collapsed_content_alpha():.2f} "
            f"expanded_header_alpha={self._expanded_header_alpha():.2f} "
            f"expanded_main_alpha={self._expanded_main_alpha():.2f} "
            f"expanded_search_alpha={self._expanded_search_alpha():.2f} "
            f"target_interval_ms={self.current_animation_interval_ms} "
            f"current_state={self.state} "
            f"active_motion_channels={self._active_motion_channels()} "
            f"animation_timer_active={self.animation_timer.isActive()} "
            f"outside_timer_active={self.outside_click_timer.isActive()} "
            f"status_timer_active={self.status_timer.isActive()} "
            f"search_debounce_active={self.search_debounce_timer.isActive()} "
            f"search_result_timer_active={self.search_result_poll_timer.isActive()} "
            f"url_prompt_timer_active={self.url_prompt_timer.isActive()} "
            f"drive_prompt_timer_active={self.drive_prompt_timer.isActive()} "
            f"media_timer_active={self.media_poll_timer.isActive()} "
            f"media_result_timer_active={self.media_result_poll_timer.isActive()} "
            f"visual_body_width={layout.body_width}"
        )
        self._paint_count = 0
        self._tick_count = 0
        self._paint_total_ms = 0.0
        self._debug_last_tick = now

    def _stop_animations(self) -> None:
        for channel in self.animation_channels.values():
            channel.active = False
            channel.elapsed_ms = 0.0
        self.animation_timer.stop()

    def _active_animation_count(self) -> int:
        return sum(1 for channel in self.animation_channels.values() if channel.active)

    def _active_motion_channels(self) -> str:
        channels = [name for name, channel in self.animation_channels.items() if channel.active]
        if self._search_focus_flow_active():
            channels.append("search_flow")
        if self._feature_pulse_active():
            channels.append("feature_pulse")
        return ",".join(channels) if channels else "none"

    def _collapse_immediately(self) -> None:
        self._stop_animations()
        self.outside_click_timer.stop()
        self.is_expanded = False
        self.is_collapsed_hidden = False
        self.state = STATE_COLLAPSED
        self.expand_target_state = None
        self.expand_direction = None
        self.expand_progress = 0.0
        self.hidden_progress = 0.0
        self.content_fade_progress = 0.0
        self.page_transition_progress = 1.0
        self.focus_ring_progress = 0.0
        self.search_sweep_progress = 0.0
        self.search_focus_flow_phase = 0.0
        self.feature_hovered = False
        self.feature_hover_progress = 0.0
        self.feature_pulse_phase = 0.0
        self.animation_channels["expand"].value = 0.0
        self.animation_channels["hidden"].value = 0.0
        self.animation_channels["content"].value = 0.0
        self.animation_channels["page"].value = 1.0
        self.animation_channels["focus_ring"].value = 0.0
        self.animation_channels["search_sweep"].value = 0.0
        self.animation_channels["feature_hover"].value = 0.0
        self.animation_channels["width"].value = 1.0
        self._shape_motion_mode = "linear"
        target_width = self._calculate_auto_body_width()
        self.auto_body_width_target = target_width
        self._set_shape_metrics(target_width, self.base_body_height, self.base_radius)

    def _sync_motion_to_current_state(self) -> None:
        self._stop_animations()
        self.hover_progress = 1.0 if self.underMouse() else 0.0
        self.press_progress = 0.0
        self.hidden_progress = 1.0 if self.state == STATE_HIDDEN else 0.0
        self.expand_progress = 1.0 if self.state == STATE_EXPANDED else 0.0
        self.content_fade_progress = 1.0 if self.state == STATE_EXPANDED else 0.0
        self.page_transition_progress = 1.0
        self.focus_ring_progress = 0.0
        self.search_sweep_progress = 0.0
        self.search_focus_flow_phase = 0.0
        self.feature_hovered = False
        self.feature_hover_progress = 0.0
        self.feature_pulse_phase = 0.0
        self.animation_channels["hover"].value = self.hover_progress
        self.animation_channels["press"].value = self.press_progress
        self.animation_channels["hidden"].value = self.hidden_progress
        self.animation_channels["expand"].value = self.expand_progress
        self.animation_channels["content"].value = self.content_fade_progress
        self.animation_channels["page"].value = self.page_transition_progress
        self.animation_channels["focus_ring"].value = self.focus_ring_progress
        self.animation_channels["search_sweep"].value = self.search_sweep_progress
        self.animation_channels["feature_hover"].value = self.feature_hover_progress
        self.animation_channels["width"].value = 1.0
        self._shape_motion_mode = "linear"

    def _prewarm_animation_cache(self) -> None:
        try:
            collapsed_width = int(self._calculate_auto_body_width())
            collapsed = VisualLayout(
                body_width=collapsed_width,
                body_height=int(self.base_body_height),
                radius=int(self.base_radius),
                window_width=int(collapsed_width + SHADOW_MARGIN_X * 2),
                window_height=int(self.base_body_height + SHADOW_MARGIN_BOTTOM),
            )
            expanded_width, expanded_height, expanded_radius = self._expanded_target_metrics()
            expanded = VisualLayout(
                body_width=int(expanded_width),
                body_height=int(expanded_height),
                radius=int(expanded_radius),
                window_width=int(expanded_width + SHADOW_MARGIN_X * 2),
                window_height=int(expanded_height + SHADOW_MARGIN_BOTTOM),
            )
            hidden = VisualLayout(
                body_width=collapsed.body_width,
                body_height=int(HIDDEN["handle_height"]),
                radius=int(self.base_radius),
                window_width=int(collapsed.window_width),
                window_height=int(HIDDEN["handle_height"] + SHADOW_MARGIN_BOTTOM),
            )
            self._prewarmed_paths["collapsed"] = build_notch_path(
                QRectF(SHADOW_MARGIN_X, 0, collapsed.body_width, collapsed.body_height),
                float(collapsed.radius),
            )
            self._prewarmed_paths["expanded"] = build_notch_path(
                QRectF(SHADOW_MARGIN_X, 0, expanded.body_width, expanded.body_height),
                float(expanded.radius),
            )
            self._prewarmed_paths["hidden"] = build_notch_path(
                QRectF(SHADOW_MARGIN_X, 0, hidden.body_width, hidden.body_height),
                float(hidden.radius),
            )
            self.brand_metrics.horizontalAdvance(self.brand_text)
            self.time_metrics.horizontalAdvance("00:00")
            self.status_metrics.horizontalAdvance(STATUS_SLOT_TEMPLATES["network"])
            tr(self.language, "settings")
            tr(self.language, "status")
            self.panel_placeholder_text = tr(self.language, "panel_placeholder")
            self.panel_placeholder_metrics.horizontalAdvance(self.panel_placeholder_text)
            pixmap = QPixmap(expanded.window_width, expanded.window_height)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.fillPath(self._prewarmed_paths["expanded"], self.body_color)
            painter.end()
        except Exception:
            pass

    def _prewarm_search_indexes(self) -> None:
        if self.search_prewarm_future is not None and not self.search_prewarm_future.done():
            return
        try:
            self.search_prewarm_future = self.search_executor.submit(prewarm_search_indexes)
        except RuntimeError:
            pass

    @staticmethod
    def _format_time() -> str:
        return datetime.now().strftime("%H:%M")
