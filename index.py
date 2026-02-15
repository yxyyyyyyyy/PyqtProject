import sys
import os
import random
import struct
import time
import ctypes
import ctypes.util
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QWidget, QMenu, QSystemTrayIcon
from PyQt6.QtCore import Qt, QTimer, QPoint, QEvent, QThread, pyqtSignal, QUrl, QRect
from PyQt6.QtGui import (
    QPixmap,
    QIcon,
    QPainter,
    QPainterPath,
    QAction,
    QRegion,
    QMovie,
    QImageReader,
    QKeySequence,
    QFontMetrics,
    QColor,
    QFont,
    QCursor,
    QBrush,
)
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer, QAudioSource, QMediaDevices, QAudioFormat

def _app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(*parts: str) -> str:
    return str(_app_base_dir().joinpath(*parts))


# ================= 配置区域 =================
# 图片素材根目录
ASSET_FOLDER = resource_path("assets")
GIF_ASSET_FOLDER = resource_path("assets", "gif")
# 默认大小 (根据图片素材调整)
PET_WIDTH = 128
PET_HEIGHT = 128
MIN_SCALE = 0.5
MAX_SCALE = 3.0
SCALE_STEP = 0.1
ROAM_TICK_MS = 16
ROAM_SPEED_PX = 4
CHASE_TICK_MS = 30
CHASE_SPEED_PX = 6
HEART_COUNT = 8
# 动画刷新间隔 (毫秒)
REFRESH_RATE = 80
# 移动速度 (键盘控制时)
MOVE_STEP = 5
SPACE_HOLD_MS = 2000
IDLE_TIMEOUT_MS = 6000
INPUT_DISPLAY_MAX = 24
INPUT_DISPLAY_TIMEOUT_MS = 1500
MIC_CHECK_INTERVAL_MS = 200
MIC_PROCESS_INTERVAL_MS = 80
MIC_ACTIVE_HOLD_MS = 2000
MIC_LEVEL_THRESHOLD = 0.02
MIC_LEVEL_THRESHOLD_OFF = 0.012
MIC_EMA_ALPHA = 0.35
SPACE_AUDIO_PATH = os.path.join(ASSET_FOLDER, "bgaudio", "knock.mp3")
ENABLE_MAC_GLOBAL_HOTKEYS = True
MAC_GLOBAL_HOTKEYS_REQUIRE_ALT = False
ACTION_GIF_MAP = {
    "love": "love.gif",
    "oMygad": "oMygad.gif",
    "look": "look.gif",
    "come": "come.gif",
    "cry": "cry.gif",
    "scold": "scold.gif",
    "wow": "happy.gif",
    "what": "what.gif",
    "sly smile": "Act cute.gif",
    "knock": "knock.gif",
    "Appear": "love.gif",
    "attention": "state.gif",
    "me": "Act cute.gif",
    "xixi": "happy.gif",
    "dajiao": "oMygad.gif",
    "xinxu": "song.gif",
    "ganm": "oMygad.gif",
    "ma": "oMygad.gif",
    "Shocked": "oMygad.gif",
    "eat": "eat.gif",
    "food": "food.gif",
    "marry": "marry.gif",
    "play": "play.gif",
    "song": "song.gif",
}
DEFAULT_ACTION_ORDER = ["attention", "love", "oMygad", "look"]
# ===========================================

ALL_PETS = []

class HeartWidget(QWidget):
    def __init__(self, x, y, size=20, parent=None):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
        self._size = size
        self._vx = random.uniform(-3, 3)
        self._vy = random.uniform(-5, -3)
        self._alpha = 255
        self.resize(size + 20, size + 20)
        self.move(int(x - (size + 20) // 2), int(y - (size + 20) // 2))
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._animate)
        self._timer.start()
        self.show()

    def _animate(self):
        self._vy += 0.15
        self.move(int(self.x() + self._vx), int(self.y() + self._vy))
        self._alpha = max(0, self._alpha - 4)
        if self._alpha <= 0:
            self._timer.stop()
            self.close()
            self.deleteLater()
        else:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(255, 80, 120, self._alpha)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        self._draw_heart(painter, (self.width() - self._size) // 2, (self.height() - self._size) // 2, self._size)

    def _draw_heart(self, painter, x, y, size):
        path = QPainterPath()
        path.moveTo(x + size / 2, y + size / 4)
        path.cubicTo(x + size / 2, y, x, y, x, y + size / 4)
        path.cubicTo(x, y + size / 2, x + size / 2, y + size * 0.75, x + size / 2, y + size)
        path.cubicTo(x + size / 2, y + size * 0.75, x + size, y + size / 2, x + size, y + size / 4)
        path.cubicTo(x + size, y, x + size / 2, y, x + size / 2, y + size / 4)
        painter.drawPath(path)


class MacGlobalKeyListener(QThread):
    keyPressed = pyqtSignal(int)
    textTyped = pyqtSignal(str)
    shortcutTriggered = pyqtSignal(str)
    statusChanged = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._run_loop = None
        self._tap = None
        self._source = None
        self._callback = None

    def stop(self):
        if self._run_loop is not None:
            try:
                self._cf.CFRunLoopStop(self._run_loop)
            except Exception:
                pass
        self.quit()
        self.wait(300)

    def run(self):
        app_services = ctypes.util.find_library("ApplicationServices")
        core_foundation = ctypes.util.find_library("CoreFoundation")
        if not app_services or not core_foundation:
            self.statusChanged.emit(False, "未找到 macOS 系统库，无法启用全局热键")
            return

        self._cg = ctypes.CDLL(app_services)
        self._cf = ctypes.CDLL(core_foundation)

        CGEventTapCallBack = ctypes.CFUNCTYPE(
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )

        kCGSessionEventTap = 1
        kCGHeadInsertEventTap = 0
        kCGEventTapOptionDefault = 0

        kCGEventKeyDown = 10

        self._cg.CGEventGetIntegerValueField.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._cg.CGEventGetIntegerValueField.restype = ctypes.c_longlong
        self._cg.CGEventGetFlags.argtypes = [ctypes.c_void_p]
        self._cg.CGEventGetFlags.restype = ctypes.c_ulonglong
        self._cg.CGEventKeyboardGetUnicodeString.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.c_void_p,
        ]
        self._cg.CGEventKeyboardGetUnicodeString.restype = None

        self._cf.CFRunLoopGetCurrent.restype = ctypes.c_void_p
        self._cf.CFRunLoopAddSource.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        self._cf.CFRunLoopRun.argtypes = []
        self._cf.CFRunLoopStop.argtypes = [ctypes.c_void_p]

        self._cg.CGEventTapCreate.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_ulonglong,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        self._cg.CGEventTapCreate.restype = ctypes.c_void_p

        self._cf.CFMachPortCreateRunLoopSource.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
        self._cf.CFMachPortCreateRunLoopSource.restype = ctypes.c_void_p

        self._cg.CGEventTapEnable.argtypes = [ctypes.c_void_p, ctypes.c_bool]

        self._callback = CGEventTapCallBack(self._handle_event)
        mask = 1 << kCGEventKeyDown
        self._tap = self._cg.CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionDefault,
            ctypes.c_ulonglong(mask),
            self._callback,
            None,
        )
        if not self._tap:
            self.statusChanged.emit(
                False,
                "全局热键初始化失败：请在“系统设置 → 隐私与安全性 → 输入监控”允许当前 Python/终端/IDE",
            )
            return

        self._source = self._cf.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        if not self._source:
            self.statusChanged.emit(False, "全局热键初始化失败：无法创建 RunLoop Source")
            return

        self._run_loop = self._cf.CFRunLoopGetCurrent()
        try:
            mode = ctypes.c_void_p.in_dll(self._cf, "kCFRunLoopCommonModes")
        except Exception:
            mode = ctypes.c_void_p.in_dll(self._cf, "kCFRunLoopDefaultMode")
        self._cf.CFRunLoopAddSource(self._run_loop, self._source, mode)
        self._cg.CGEventTapEnable(self._tap, True)
        if MAC_GLOBAL_HOTKEYS_REQUIRE_ALT:
            self.statusChanged.emit(True, "全局键盘监听已启用（需按住 Option(⌥) 才触发）")
        else:
            self.statusChanged.emit(True, "全局键盘监听已启用")
        self._cf.CFRunLoopRun()

    def _handle_event(self, _proxy, event_type, event, _refcon):
        try:
            if event_type != 10:
                return event
            flags = int(self._cg.CGEventGetFlags(event))
            if MAC_GLOBAL_HOTKEYS_REQUIRE_ALT and not (flags & (1 << 19)):
                return event
            keycode = int(self._cg.CGEventGetIntegerValueField(event, 9))
            if flags & ((1 << 18) | (1 << 20)):
                if keycode == 8:
                    self.shortcutTriggered.emit("copy")
                elif keycode == 9:
                    self.shortcutTriggered.emit("paste")
            qt_key = {
                123: int(Qt.Key.Key_Left),
                124: int(Qt.Key.Key_Right),
                125: int(Qt.Key.Key_Down),
                126: int(Qt.Key.Key_Up),
                49: int(Qt.Key.Key_Space),
                53: int(Qt.Key.Key_Escape),
                13: int(Qt.Key.Key_W),
                0: int(Qt.Key.Key_A),
                1: int(Qt.Key.Key_S),
                2: int(Qt.Key.Key_D),
            }.get(keycode)
            if qt_key is not None:
                self.keyPressed.emit(qt_key)
            max_chars = 8
            actual = ctypes.c_ulong(0)
            buffer = (ctypes.c_ushort * max_chars)()
            self._cg.CGEventKeyboardGetUnicodeString(
                event,
                ctypes.c_ulong(max_chars),
                ctypes.byref(actual),
                buffer,
            )
            if actual.value:
                text = "".join(chr(buffer[i]) for i in range(actual.value))
                if text:
                    self.textTyped.emit(text)
            elif keycode in (51, 117):
                self.textTyped.emit("\b")
            elif keycode in (36, 76):
                self.textTyped.emit("\n")
        except Exception:
            return event
        return event

class DesktopPet(QWidget):
    def __init__(self, is_master=True):
        super().__init__()
        self._is_master = bool(is_master)

       # 1. 窗口设置：无边框、置顶、透明背景
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StaticContents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAutoFillBackground(False)
        self._scale = 1.0
        self.resize(PET_WIDTH, PET_HEIGHT)
        
        # 允许窗口获取焦点以响应键盘事件
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # 2. 状态初始化
        self.actions = {}           # {'action_name': {'type': 'frames'|'movie', ...}}
        self.current_action = None  # 当前动作名称
        self.default_action = None  # 默认待机动作
        self.image_index = 0        # 当前播放的帧索引
        self.action_mode = 'loop'   # 播放模式: 'loop'(循环) 或 'once'(播放一次后切回默认动作)
        self._current_movie = None
        self._movie_action_by_obj = {}
        self._movie_once_seen_nonzero = False
        self._scaled_pixmap_cache = {}
        self._last_move_action = None
        self._once_hold_timer = QTimer(self)
        self._once_hold_timer.setSingleShot(True)
        self._once_hold_timer.timeout.connect(self._end_once_hold)
        self._once_hold_action = None
        self._once_hold_back_to = None
        self._once_hold_ms = None
        self._last_activity_ts = time.monotonic()
        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(0.9)
        self._praise_player = QMediaPlayer(self)
        self._praise_player.setAudioOutput(self._audio_output)
        
        self._space_player = QMediaPlayer(self)
        self._space_player.setAudioOutput(self._audio_output)
        if os.path.exists(SPACE_AUDIO_PATH):
            self._space_player.setSource(QUrl.fromLocalFile(os.path.abspath(SPACE_AUDIO_PATH)))

        self._roam_enabled = False
        self._roam_timer = QTimer(self)
        self._roam_timer.setInterval(int(ROAM_TICK_MS))
        self._roam_timer.timeout.connect(self._on_roam_tick)
        self._roam_target = None
        self._chase_enabled = False
        self._chase_timer = QTimer(self)
        self._chase_timer.setInterval(int(CHASE_TICK_MS))
        self._chase_timer.timeout.connect(self._on_chase_tick)
        self._mouse_down = False
        self._mouse_drag_started = False
        self._double_clicking = False
        self._double_click_hold_until = 0.0
        self._mouse_press_global = QPoint()
        self._input_text = ""
        self._input_display_timer = QTimer(self)
        self._input_display_timer.setSingleShot(True)
        self._input_display_timer.timeout.connect(self._clear_input_text)
        self._last_hover_ts = 0.0
        self._input_action_timer = QTimer(self)
        self._input_action_timer.setSingleShot(True)
        self._input_action_timer.timeout.connect(self._end_input_action)
        self._input_action_name = None
        self._tray_watch_timer = QTimer(self)
        self._tray_watch_timer.setInterval(1000)
        self._tray_watch_timer.timeout.connect(self._ensure_tray_icon_visible)
        self._tray_roam_action = None
        self._tray_chase_action = None
        self._tray_mic_action = None
        self._song_active = False
        self._mic_enabled = True
        self._mic_available = False
        self._mic_active_ts = 0.0
        self._mic_last_action_ts = 0.0
        self._mic_level_ema = 0.0
        self._mic_input = None
        self._mic_io = None
        self._mic_format = None
        self._mic_timer = QTimer(self)
        self._mic_timer.setInterval(int(MIC_CHECK_INTERVAL_MS))
        self._mic_timer.timeout.connect(self._poll_mic)
        
        # 拖拽相关
        self.is_dragging = False
        self.drag_position = QPoint()

        # 3. 加载素材
        self.load_images()
        self._init_mic()
        # 4. 启动动画定时器
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(REFRESH_RATE)

        self._walk_idle_timer = QTimer(self)
        self._walk_idle_timer.setSingleShot(True)
        self._walk_idle_timer.timeout.connect(self._maybe_back_to_idle)

        # 5. 按键持续按下的定时器
        self._key_repeat_timer = QTimer(self)
        self._key_repeat_timer.setInterval(50)  # 50ms触发一次
        self._key_repeat_timer.timeout.connect(self._handle_key_repeat)
        self._current_key = None

        # 5. 右键菜单 & 托盘
        self.init_menu()
        if self._is_master:
            self.init_tray_icon()
            self._tray_watch_timer.start()

        self._global_key_listener = None
        if self._is_master and sys.platform == "darwin" and ENABLE_MAC_GLOBAL_HOTKEYS:
            self._global_key_listener = MacGlobalKeyListener(self)
            self._global_key_listener.keyPressed.connect(self._handle_key)
            self._global_key_listener.textTyped.connect(self._handle_global_text)
            self._global_key_listener.shortcutTriggered.connect(self._handle_global_shortcut)
            self._global_key_listener.statusChanged.connect(self._on_global_hotkey_status)
            self._global_key_listener.start()

        self._idle_timer = QTimer(self)
        self._idle_timer.timeout.connect(self._check_idle)
        self._idle_timer.start(250)

        # 7. 获取屏幕尺寸，将窗口移动到屏幕中央
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        x = screen_geometry.left() + (screen_geometry.width() - self.width()) // 2
        y = screen_geometry.top() + (screen_geometry.height() - self.height()) // 2
        self.move(x, y)
        print(f"窗口位置: x={x}, y={y}, 大小: {self.width()}x{self.height()}")
        
        # 显示窗口
        self.show()
        self.raise_()
        icon = self._build_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        if "attention" in self.actions and self.actions["attention"].get("visible", True):
            self.change_action("attention", mode="loop")
        self._update_mask_for_current_frame()
        self.update()
        ALL_PETS.append(self)
        if self._roam_enabled and not self._roam_timer.isActive():
            self._roam_timer.start()
        if self._is_master:
            for delay in (0, 200, 800):
                QTimer.singleShot(delay, self._ensure_tray_icon_visible)
        
        self._focus_attempts_left = 8
        if self._is_master:
            QTimer.singleShot(0, self.init_focus)
            QTimer.singleShot(0, self._force_first_paint)

    def init_focus(self):
        """初始化焦点，确保窗口能响应键盘事件"""
        if not self._is_master:
            return
        if not self.isVisible():
            self.show()

        self.raise_()
        self._ensure_tray_icon_visible()

        if (QApplication.activeWindow() is self) or self.hasFocus():
            self.update()
            return

        self._focus_attempts_left -= 1
        if self._focus_attempts_left > 0:
            QTimer.singleShot(60, self.init_focus)
        else:
            self.update()

    def _force_first_paint(self):
        if not self.isVisible():
            return
        if self.current_action is not None:
            action = self.actions.get(self.current_action)
            if action and action.get("type") == "movie":
                movie = action.get("movie")
                if isinstance(movie, QMovie):
                    try:
                        movie.jumpToFrame(0)
                    except Exception:
                        pass
        self._update_mask_for_current_frame()
        self.repaint()

    def showEvent(self, event):
        super().showEvent(event)
        if self._is_master:
            QTimer.singleShot(0, self.init_focus)

    def event(self, event):
        if event.type() == QEvent.Type.WindowActivate:
            if self._is_master:
                QTimer.singleShot(0, self.init_focus)
        return super().event(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)

    def closeEvent(self, event):
        if self._global_key_listener is not None:
            self._global_key_listener.stop()
        if self._is_master:
            for pet in list(ALL_PETS):
                if pet is not self:
                    pet.close()
        else:
            for pet in list(ALL_PETS):
                if pet is not self and not getattr(pet, "_is_master", False):
                    pet.close()
        try:
            if self in ALL_PETS:
                ALL_PETS.remove(self)
        except Exception:
            pass
        super().closeEvent(event)

    def _on_global_hotkey_status(self, _ok, message):
        print(message)

    def _mark_user_active(self):
        self._last_activity_ts = time.monotonic()
        if self.current_action == "attention" and self.default_action is not None:
            self.change_action(self.default_action, mode="loop")

    def _check_idle(self):
        if self._roam_enabled:
            return
        if self.is_dragging:
            return
        if self.action_mode == "once":
            return
        if self._song_active:
            return
        if "attention" not in self.actions or not self.actions["attention"].get("visible", True):
            return
        idle_s = (time.monotonic() - self._last_activity_ts)
        if idle_s * 1000 < IDLE_TIMEOUT_MS:
            return
        if self.current_action != "attention":
            self.change_action("attention", mode="loop")

    def _try_create_movie(self, path):
        reader = QImageReader(path)
        if not reader.canRead():
            return None
        if not reader.supportsAnimation():
            return None
        movie = QMovie(path)
        if not movie.isValid():
            return None
        return movie

    def _trigger_once(self, action_name, hold_ms=SPACE_HOLD_MS):
        if action_name not in self.actions:
            return
        if not self.actions[action_name].get("visible", True):
            return
        self.change_action(action_name, mode="once", hold_ms=hold_ms, back_to=self.default_action)

    def _play_praise_audio(self):
        source = self._praise_player.source()
        if not source.isValid():
            QApplication.beep()
            return
        self._praise_player.setPosition(0)
        self._praise_player.play()

    def _build_app_icon(self):
        pixmap = None
        candidates = []
        for name in DEFAULT_ACTION_ORDER:
            gif_name = ACTION_GIF_MAP.get(name)
            if gif_name:
                candidates.append(gif_name)
        for name in ACTION_GIF_MAP.values():
            candidates.append(name)
        for file_name in candidates:
            path = os.path.join(GIF_ASSET_FOLDER, file_name)
            if not os.path.exists(path):
                continue
            reader = QImageReader(path)
            if not reader.canRead():
                continue
            image = reader.read()
            if image.isNull():
                continue
            pixmap = QPixmap.fromImage(image)
            if not pixmap.isNull():
                break
        if pixmap is None or pixmap.isNull():
            return QIcon()
        scaled = pixmap.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        return QIcon(scaled)

    def _trigger_praise(self):
        self._mark_user_active()
        self._trigger_once("wow", hold_ms=1400)
        self._play_praise_audio()

    def _pixmap_has_visible_pixel(self, pixmap):
        if pixmap is None or pixmap.isNull():
            return False
        image = pixmap.toImage()
        if image.isNull() or not image.hasAlphaChannel():
            return True
        w = image.width()
        h = image.height()
        step = 4
        for y in range(0, h, step):
            for x in range(0, w, step):
                if image.pixelColor(x, y).alpha() > 0:
                    return True
        return False
    
    def _frames_have_visible_pixel(self, frames):
        if not frames:
            return False
        n = len(frames)
        probe = []
        for idx in (0, 1, 2, n // 2, n - 2, n - 1):
            if 0 <= idx < n:
                probe.append(frames[idx])
        seen = set()
        for pixmap in probe:
            key = int(pixmap.cacheKey()) if pixmap is not None else 0
            if key in seen:
                continue
            seen.add(key)
            if self._pixmap_has_visible_pixel(pixmap):
                return True
        for pixmap in frames:
            if self._pixmap_has_visible_pixel(pixmap):
                return True
        return False

    def _target_size(self):
        w = max(1, int(PET_WIDTH * float(self._scale)))
        h = max(1, int(PET_HEIGHT * float(self._scale)))
        return w, h

    def _apply_scale(self, new_scale):
        new_scale = float(new_scale)
        new_scale = max(MIN_SCALE, min(new_scale, MAX_SCALE))
        if abs(new_scale - float(self._scale)) < 1e-6:
            return
        self._scale = new_scale
        self._scaled_pixmap_cache.clear()
        w, h = self._target_size()
        self.resize(w, h)
        self._update_mask_for_current_frame()
        self.update()

    def _scale_up(self):
        self._apply_scale(self._scale + SCALE_STEP)

    def _scale_down(self):
        self._apply_scale(self._scale - SCALE_STEP)

    def _scale_reset(self):
        self._apply_scale(1.0)

    def _current_available_geometry(self):
        screen = self.screen() or QApplication.primaryScreen()
        return screen.availableGeometry() if screen is not None else QApplication.primaryScreen().availableGeometry()

    def _roam_pick_target(self):
        g = self._current_available_geometry()
        x = random.randint(g.left(), max(g.left(), g.right() - self.width() + 1))
        y = random.randint(g.top(), max(g.top(), g.bottom() - self.height() + 1))
        return QPoint(x, y)

    def _toggle_roam(self):
        self._roam_enabled = not self._roam_enabled
        if self._tray_roam_action is not None:
            self._tray_roam_action.setChecked(self._roam_enabled)
        if self._roam_enabled:
            self._stop_chase()
            self._roam_target = None
            if not self._roam_timer.isActive():
                self._roam_timer.start()
            return
        if self._roam_timer.isActive():
            self._roam_timer.stop()
        self._roam_target = None
        if not self.is_dragging and self.default_action is not None:
            self.change_action(self.default_action, mode="loop")

    def _stop_roam(self):
        if self._roam_timer.isActive():
            self._roam_timer.stop()
        self._roam_enabled = False
        if self._tray_roam_action is not None:
            self._tray_roam_action.setChecked(False)

    def _toggle_chase(self):
        self._chase_enabled = not self._chase_enabled
        if self._tray_chase_action is not None:
            self._tray_chase_action.setChecked(self._chase_enabled)
        if self._chase_enabled:
            self._stop_roam()
            if not self._chase_timer.isActive():
                self._chase_timer.start()
            return
        self._stop_chase()

    def _stop_chase(self):
        if self._chase_timer.isActive():
            self._chase_timer.stop()
        self._chase_enabled = False
        if self._tray_chase_action is not None:
            self._tray_chase_action.setChecked(False)
        if not self.is_dragging and self.default_action is not None:
            self.change_action(self.default_action, mode="loop")

    def _on_chase_tick(self):
        if not self._chase_enabled:
            return
        if self.is_dragging or self._mouse_down:
            return
        if self.action_mode == "once":
            return
        cursor_pos = QCursor.pos()
        cur = self.pos()
        dx = cursor_pos.x() - cur.x() - self.width() // 2
        dy = cursor_pos.y() - cur.y() - self.height() // 2
        dist = (dx * dx + dy * dy) ** 0.5
        if dist < 10:
            return
        if "come" in self.actions and self.actions["come"].get("visible", True):
            if self.current_action != "come" or self.action_mode != "loop":
                self.change_action("come", mode="loop")
        g = self._current_available_geometry()
        step = int(CHASE_SPEED_PX)
        nx = cur.x() + int(step * dx / dist)
        ny = cur.y() + int(step * dy / dist)
        nx = max(g.left(), min(nx, g.right() - self.width() + 1))
        ny = max(g.top(), min(ny, g.bottom() - self.height() + 1))
        self.move(nx, ny)

    def _spawn_hearts(self):
        center_x = self.x() + self.width() // 2
        center_y = self.y() + self.height() // 2
        for _ in range(HEART_COUNT):
            size = 16 + random.randint(0, 8)
            offset_x = random.randint(-30, 30)
            offset_y = random.randint(-30, 10)
            HeartWidget(center_x + offset_x, center_y + offset_y, size)

    def _start_mic(self):
        if not self._mic_available or self._mic_input is None:
            return
        self._mic_io = self._mic_input.start()
        if self._mic_io:
            self._mic_io.readyRead.connect(self._on_mic_ready)
        if not self._mic_timer.isActive():
            self._mic_timer.start()

    def _stop_mic(self):
        if self._mic_timer.isActive():
            self._mic_timer.stop()
        if self._mic_input is not None:
            try:
                self._mic_input.stop()
            except Exception:
                pass
        self._mic_io = None
        if self._song_active:
            self._song_active = False
            if self.default_action is not None:
                self.change_action(self.default_action, mode="loop")

    def _toggle_mic(self):
        if not self._mic_available:
            return
        self._mic_enabled = not self._mic_enabled
        if self._tray_mic_action is not None:
            self._tray_mic_action.setChecked(self._mic_enabled)
        if self._mic_enabled:
            self._start_mic()
        else:
            self._stop_mic()

    def _init_mic(self):
        if not self._is_master:
            return
        device = QMediaDevices.defaultAudioInput()
        if device.isNull():
            self._mic_available = False
            return
        self._mic_available = True
        fmt = QAudioFormat()
        fmt.setChannelCount(1)
        fmt.setSampleRate(44100)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(fmt):
            fmt = device.preferredFormat()
        try:
            self._mic_input = QAudioSource(device, fmt, self)
            self._mic_format = fmt
        except TypeError:
            self._mic_input = QAudioSource(device, self)
            if hasattr(self._mic_input, "format"):
                try:
                    self._mic_format = self._mic_input.format()
                except Exception:
                    self._mic_format = fmt
            else:
                self._mic_format = fmt
        if self._mic_enabled:
            self._start_mic()

    def _mic_level_from_data(self, data):
        if not data or self._mic_format is None:
            return 0.0
        sample_format = self._mic_format.sampleFormat()
        if sample_format == QAudioFormat.SampleFormat.Int16:
            count = len(data) // 2
            if count == 0:
                return 0.0
            total = 0
            for i in range(0, count * 2, 2):
                total += abs(int.from_bytes(data[i:i + 2], "little", signed=True))
            return (total / count) / 32768.0
        if sample_format == QAudioFormat.SampleFormat.Int32:
            count = len(data) // 4
            if count == 0:
                return 0.0
            total = 0
            for i in range(0, count * 4, 4):
                total += abs(int.from_bytes(data[i:i + 4], "little", signed=True))
            return (total / count) / 2147483648.0
        if sample_format == QAudioFormat.SampleFormat.UInt8:
            count = len(data)
            if count == 0:
                return 0.0
            total = 0
            for b in data:
                total += abs(b - 128)
            return (total / count) / 128.0
        if sample_format == QAudioFormat.SampleFormat.Float:
            count = len(data) // 4
            if count == 0:
                return 0.0
            total = 0.0
            for value in struct.unpack("<" + "f" * count, data[: count * 4]):
                total += abs(value)
            return total / count
        return 0.0

    def _process_mic_data(self, data):
        now = time.monotonic()
        if (now - self._mic_last_action_ts) * 1000 < MIC_PROCESS_INTERVAL_MS:
            return
        level = self._mic_level_from_data(data)
        self._mic_level_ema = (1 - MIC_EMA_ALPHA) * self._mic_level_ema + MIC_EMA_ALPHA * level
        if self._mic_level_ema >= MIC_LEVEL_THRESHOLD:
            self._mic_active_ts = now
            if (
                "song" in self.actions
                and self.actions["song"].get("visible", True)
                and self.action_mode != "once"
                and not self.is_dragging
                and not self._mouse_down
            ):
                if not self._song_active:
                    self._song_active = True
                    if self.current_action != "song" or self.action_mode != "loop":
                        self.change_action("song", mode="loop")
        elif self._mic_level_ema <= MIC_LEVEL_THRESHOLD_OFF:
            pass
        self._mic_last_action_ts = now

    def _poll_mic(self):
        if not self._mic_enabled:
            return
        if not self._mic_io:
            return
        if self._mic_io.bytesAvailable() <= 0:
            self._check_mic_active()
            return
        data = bytes(self._mic_io.readAll())
        if data:
            self._process_mic_data(data)
        self._check_mic_active()

    def _on_mic_ready(self):
        self._poll_mic()

    def _check_mic_active(self):
        if not self._song_active:
            return
        if self.action_mode == "once" or self.is_dragging or self._mouse_down:
            return
        active_ms = (time.monotonic() - self._mic_active_ts) * 1000
        if active_ms < MIC_ACTIVE_HOLD_MS:
            return
        self._song_active = False
        if self.default_action is not None:
            self.change_action(self.default_action, mode="loop")

    def _on_roam_tick(self):
        if not self._roam_enabled:
            return
        if self.is_dragging or self._mouse_down:
            return
        if self.action_mode == "once":
            return
        if self._song_active:
            return
        if "come" in self.actions and self.actions["come"].get("visible", True):
            if self.current_action != "come" or self.action_mode != "loop":
                self.change_action("come", mode="loop")
        g = self._current_available_geometry()
        if self._roam_target is None:
            self._roam_target = self._roam_pick_target()
        cur = self.pos()
        dx = self._roam_target.x() - cur.x()
        dy = self._roam_target.y() - cur.y()
        dist = abs(dx) + abs(dy)
        if dist <= ROAM_SPEED_PX * 2:
            self._roam_target = self._roam_pick_target()
            return
        step = int(ROAM_SPEED_PX)
        nx = cur.x() + (step if dx > 0 else -step if dx < 0 else 0)
        ny = cur.y() + (step if dy > 0 else -step if dy < 0 else 0)
        nx = max(g.left(), min(nx, g.right() - self.width() + 1))
        ny = max(g.top(), min(ny, g.bottom() - self.height() + 1))
        self.move(nx, ny)

    def _current_scaled_pixmap(self):
        if not self.current_action or self.current_action not in self.actions:
            return None

        action = self.actions[self.current_action]
        pixmap = None
        if action.get("type") == "movie":
            movie = action.get("movie")
            if isinstance(movie, QMovie):
                pixmap = movie.currentPixmap()
        else:
            frames = action.get("frames") or []
            if frames:
                frame_index = self.image_index % len(frames)
                pixmap = frames[frame_index]

        if pixmap is None or pixmap.isNull():
            return None

        target_w, target_h = self._target_size()
        if action.get("type") == "movie":
            return pixmap.scaled(
                target_w,
                target_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        key = (self.current_action, int(pixmap.cacheKey()), target_w, target_h)
        cached = self._scaled_pixmap_cache.get(key)
        if cached is not None and not cached.isNull():
            return cached
        scaled = pixmap.scaled(
            target_w,
            target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if not scaled.isNull():
            self._scaled_pixmap_cache[key] = scaled
        return scaled

    def _input_display_text(self):
        if not self._input_text:
            return ""
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSize(max(8, font.pointSize() + 1))
        metrics = QFontMetrics(font)
        max_width = max(20, self.width() - 16)
        return metrics.elidedText(self._input_text, Qt.TextElideMode.ElideLeft, max_width)

    def _input_bubble_rect(self):
        text = self._input_display_text()
        if not text:
            return None
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSize(max(8, font.pointSize() + 1))
        metrics = QFontMetrics(font)
        padding = 6
        text_w = metrics.horizontalAdvance(text)
        text_h = metrics.height()
        rect_w = min(self.width() - 8, text_w + padding * 2)
        rect_h = text_h + padding * 2
        x = max(4, (self.width() - rect_w) // 2)
        pixmap = self._current_scaled_pixmap()
        if pixmap is not None and not pixmap.isNull():
            base_y = (self.height() - pixmap.height()) // 2
            y = max(4, base_y - rect_h - 6)
        else:
            y = 4
        return QRect(int(x), int(y), int(rect_w), int(rect_h))

    def _set_subtitle(self, text, timeout_ms=None):
        pass

    def _clear_subtitle(self):
        pass

    def _show_input_action(self):
        if "love" not in self.actions or not self.actions["love"].get("visible", True):
            return
        self._clear_subtitle()
        self.change_action("love", mode="loop")
        self._input_action_timer.start(int(INPUT_DISPLAY_TIMEOUT_MS))

    def _end_input_action(self):
        if self.current_action == "love" and self.default_action is not None:
            self.change_action(self.default_action, mode="loop")

    def _end_once_hold(self):
        action_name = self._once_hold_action
        back_to = self._once_hold_back_to or self.default_action
        self._once_hold_action = None
        self._once_hold_back_to = None
        self._once_hold_ms = None
        if action_name is None:
            return
        if self.current_action == action_name and self.action_mode == "once":
            self.change_action(back_to, mode="loop")

    def _build_space_actions(self):
        preferred = [
            "xixi",
            "wow",
            "dajiao",
            "Shocked",
            "look",
            "xinxu",
            "me",
            "ganm",
            "ma",
            "cry",
        ]
        actions = []
        for name in preferred:
            meta = self.actions.get(name)
            if meta is not None and meta.get("visible", True):
                actions.append(name)
        if not actions and self.default_action is not None:
            actions.append(self.default_action)
        return actions
        
    def load_images(self):
        if not os.path.exists(GIF_ASSET_FOLDER):
            print(f"错误: 未找到素材文件夹 {GIF_ASSET_FOLDER}，请确保它存在。")
            return

        self.actions.clear()
        self._movie_action_by_obj.clear()
        self._scaled_pixmap_cache.clear()

        for action_name, file_name in ACTION_GIF_MAP.items():
            path = os.path.join(GIF_ASSET_FOLDER, file_name)
            if not os.path.exists(path):
                continue
            movie = self._try_create_movie(path)
            if movie is None:
                continue
            movie.setCacheMode(QMovie.CacheMode.CacheAll)
            movie.frameChanged.connect(self._on_movie_frame_changed)
            movie.finished.connect(self._on_movie_finished)
            self._movie_action_by_obj[movie] = action_name
            self.actions[action_name] = {"type": "movie", "movie": movie, "visible": True}
            print(f"动作 '{action_name}' 加载成功（GIF）")

        if self.actions:
            preferred_defaults = DEFAULT_ACTION_ORDER
            chosen = None
            for name in preferred_defaults:
                meta = self.actions.get(name)
                if meta is not None and meta.get("visible", True):
                    chosen = name
                    break
            if chosen is not None:
                self.default_action = chosen
            else:
                visible_actions = [
                    k
                    for k, v in self.actions.items()
                    if v.get("visible", True) and k != "attention"
                ]
                self.default_action = visible_actions[0] if visible_actions else list(self.actions.keys())[0]
            self.current_action = self.default_action
            print(f"已将 '{self.default_action}' 设为默认待机动作。")
        else:
            print("严重错误: 文件夹里没有任何图片！")

    def _on_movie_frame_changed(self, _frame_number):
        if self._current_movie is None:
            return
        if self.action_mode == "once":
            if _frame_number == 0:
                if self._movie_once_seen_nonzero:
                    self.change_action(self.default_action, mode="loop")
                    return
            else:
                self._movie_once_seen_nonzero = True
        self._update_mask_for_current_frame()
        self.update()

    def _on_movie_finished(self):
        movie = self.sender()
        if movie is None:
            return
        action_name = self._movie_action_by_obj.get(movie)
        if action_name is None:
            return
        if self.current_action != action_name:
            return
        if self.action_mode == "once":
            if (
                self._once_hold_action == action_name
                and self._once_hold_ms is not None
                and not self._once_hold_timer.isActive()
            ):
                self._once_hold_timer.start(int(self._once_hold_ms))
                return
            self.change_action(self.default_action, mode="loop")
        else:
            movie.start()

    def change_action(self, action_name, mode='loop', hold_ms=None, back_to=None):
        """切换当前播放的动作"""
        # 如果动作不存在，或者当前已经是这个动作（且是循环模式），则忽略
        if action_name not in self.actions:
            # print(f"尝试切换到不存在的动作: {action_name}")
            return
        
        if self.current_action == action_name and self.action_mode == 'loop' and mode == 'loop':
            return

        if self._current_movie is not None:
            self._current_movie.stop()
            self._current_movie = None

        if self._once_hold_timer.isActive():
            self._once_hold_timer.stop()
        self._once_hold_action = None
        self._once_hold_back_to = None
        self._once_hold_ms = None

        self.current_action = action_name
        self.action_mode = mode
        self.image_index = 0
        self._scaled_pixmap_cache.clear()
        action = self.actions.get(self.current_action)
        if action and action.get("type") != "movie":
            frames = action.get("frames") or []
            if frames and not self._pixmap_has_visible_pixel(frames[0]):
                for i in range(1, len(frames)):
                    if self._pixmap_has_visible_pixel(frames[i]):
                        self.image_index = i
                        break
        if action and action.get("type") == "movie":
            movie = action.get("movie")
            if isinstance(movie, QMovie):
                self._movie_once_seen_nonzero = False
                if hasattr(movie, "setLoopCount"):
                    movie.setLoopCount(0 if mode == "loop" else 1)
                movie.start()
                try:
                    movie.jumpToFrame(0)
                except Exception:
                    pass
                self._current_movie = movie
        elif mode == "once" and hold_ms is not None:
            self._once_hold_action = action_name
            self._once_hold_back_to = back_to
            self._once_hold_ms = int(hold_ms)
        self._update_mask_for_current_frame()
        self.update()
        # print(f"切换状态: {action_name} ({mode})")

    def update_animation(self):
        """刷新每一帧画面"""
        action = self.actions.get(self.current_action)
        if not action:
            return
        if action.get("type") == "movie":
            return

        frames = action.get("frames") or []
        if not frames:
            return
        self.image_index += 1
        if self.image_index >= len(frames):
            if self.action_mode == 'once':
                if self._once_hold_action == self.current_action and self._once_hold_ms is not None:
                    self.image_index = max(0, len(frames) - 1)
                    if not self._once_hold_timer.isActive():
                        self._once_hold_timer.start(int(self._once_hold_ms))
                    self._update_mask_for_current_frame()
                    self.update()
                    return
                self.change_action(self.default_action, mode='loop')
            else:
                # 循环模式，重置索引
                self.image_index = 0
        
        self._update_mask_for_current_frame()
        self.update()

    def _maybe_back_to_idle(self):
        if (
            not self.is_dragging
            and self._last_move_action is not None
            and self.current_action == self._last_move_action
        ):
            self.change_action(self.default_action, mode='loop')

    def _handle_key(self, key):
        self._mark_user_active()
        if key == int(Qt.Key.Key_Escape):
            self.close()
            return

        new_x = self.x()
        new_y = self.y()
        moved = False
        if key == int(Qt.Key.Key_Left):
            new_x -= MOVE_STEP
            moved = True
        elif key == int(Qt.Key.Key_Right):
            new_x += MOVE_STEP
            moved = True
        elif key == int(Qt.Key.Key_Up):
            new_y -= MOVE_STEP
            moved = True
        elif key == int(Qt.Key.Key_Down):
            new_y += MOVE_STEP
            moved = True

        if moved:
            screen_geometry = self._current_available_geometry()
            min_x = screen_geometry.left()
            max_x = screen_geometry.right() - self.width() + 1
            min_y = screen_geometry.top()
            max_y = screen_geometry.bottom() - self.height() + 1
            new_x = max(min_x, min(new_x, max_x))
            new_y = max(min_y, min(new_y, max_y))
            self.move(new_x, new_y)
            move_action = self.default_action
            if "come" in self.actions and self.actions["come"].get("visible", True):
                move_action = "come"
            self._last_move_action = move_action
            # 无论动作是否变化，都确保窗口显示正确
            if self.current_action != move_action or self.action_mode != 'loop':
                self.change_action(move_action, mode='loop')
            else:
                self.update()
            self._walk_idle_timer.start(2000)
            return

        if key == int(Qt.Key.Key_Space):
            self._trigger_once("knock", hold_ms=SPACE_HOLD_MS)
            if self._space_player.source().isValid():
                self._space_player.setPosition(0)
                self._space_player.play()

    def _append_input_text(self, text, show_action=False):
        if not text:
            return
        self._input_text += text
        if len(self._input_text) > int(INPUT_DISPLAY_MAX):
            self._input_text = self._input_text[-int(INPUT_DISPLAY_MAX):]
        self._input_display_timer.start(int(INPUT_DISPLAY_TIMEOUT_MS))
        if show_action:
            self._show_input_action()
        self.update()

    def _backspace_input_text(self):
        if not self._input_text:
            return
        self._input_text = self._input_text[:-1]
        self._input_display_timer.start(int(INPUT_DISPLAY_TIMEOUT_MS))
        self.update()

    def _clear_input_text(self):
        self._input_text = ""
        self._end_input_action()
        self.update()

    def _handle_global_text(self, text):
        if not text:
            return
        self._mark_user_active()
        if "\b" in text:
            self._trigger_once("cry", hold_ms=1800)
            return
        if "\n" in text or "\r" in text:
            self._trigger_once("marry", hold_ms=1600)
            return
        if "?" in text or "？" in text:
            self._trigger_once("what", hold_ms=1400)

    def _handle_global_shortcut(self, name):
        if name in ("copy", "paste"):
            self._mark_user_active()
            self._trigger_once("look", hold_ms=1200)

    def paintEvent(self, _event):
        """绘图事件"""
        pixmap = self._current_scaled_pixmap()
        if pixmap is None or pixmap.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setClipping(False)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        x = (self.width() - pixmap.width()) // 2
        y = (self.height() - pixmap.height()) // 2
        painter.drawPixmap(x, y, pixmap)
        text = self._input_display_text()
        bubble_rect = self._input_bubble_rect()
        if text and bubble_rect is not None:
            shadow_rect = bubble_rect.adjusted(2, 4, 2, 4)
            painter.setBrush(QColor(0, 0, 0, 28))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(shadow_rect, 12, 12)

            painter.setBrush(QColor(255, 255, 255, 215))
            painter.setPen(QColor(210, 210, 210, 220))
            painter.drawRoundedRect(bubble_rect, 12, 12)

            font = QFont("PingFang SC", 10)
            if not font.exactMatch():
                font = QFont("Microsoft YaHei", 10)
            if not font.exactMatch():
                font = QFont(self.font())
                font.setPointSize(max(10, font.pointSize() + 2))
            
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(50, 50, 50, 255))
            painter.drawText(bubble_rect, Qt.AlignmentFlag.AlignCenter, text)

    def _update_mask_for_current_frame(self):
        pixmap = self._current_scaled_pixmap()
        if pixmap is None or pixmap.isNull():
            self.clearMask()
            return
        
        # 获取掩码
        bitmap = pixmap.mask()
        if bitmap.isNull():
            self.clearMask()
            return
        
        # 设置掩码
        x = (self.width() - pixmap.width()) // 2
        y = (self.height() - pixmap.height()) // 2
        region = QRegion(bitmap)
        region.translate(x, y)
        bubble_rect = self._input_bubble_rect()
        if bubble_rect is not None:
            region = region.united(QRegion(bubble_rect))
        if region.isEmpty():
            self.clearMask()
            return
        self.setMask(region)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._mark_user_active()
            self._mouse_down = True
            self._mouse_drag_started = False
            self._mouse_press_global = event.globalPosition().toPoint()
            self.drag_position = event.globalPosition().toPoint() - self.pos()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._mark_user_active()
            if self._double_clicking:
                self._double_clicking = False
            elif self._mouse_down and not self._mouse_drag_started:
                self.trigger_play()
            elif self._mouse_down and self._mouse_drag_started:
                pass
            self._mouse_down = False
            self._mouse_drag_started = False
            self.is_dragging = False
            if time.monotonic() >= self._double_click_hold_until:
                if self.default_action is not None:
                    self.change_action(self.default_action, mode="loop")
            event.accept()

    def mouseMoveEvent(self, event):
        if self._mouse_down and (event.buttons() & Qt.MouseButton.LeftButton):
            if not self._mouse_drag_started:
                delta = event.globalPosition().toPoint() - self._mouse_press_global
                if delta.manhattanLength() >= 4:
                    self._mouse_drag_started = True
                    self.is_dragging = True
                    if "come" in self.actions and self.actions["come"].get("visible", True):
                        self.change_action("come", mode="loop")
            if self._mouse_drag_started:
                self._mark_user_active()
                new_pos = event.globalPosition().toPoint() - self.drag_position
                g = self._current_available_geometry()
                min_x = g.left()
                max_x = g.right() - self.width() + 1
                min_y = g.top()
                max_y = g.bottom() - self.height() + 1
                new_pos.setX(max(min_x, min(new_pos.x(), max_x)))
                new_pos.setY(max(min_y, min(new_pos.y(), max_y)))
                self.move(new_pos)
                self.update()
                event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._mark_user_active()
            self._double_clicking = True
            total_ms = 4800
            interval_ms = 1600
            self._double_click_hold_until = time.monotonic() + (total_ms / 1000.0)
            times = max(1, total_ms // interval_ms)
            for i in range(times):
                QTimer.singleShot(
                    i * interval_ms,
                    lambda hold=interval_ms: self._trigger_once("sly smile", hold_ms=hold),
                )
            self._spawn_hearts()
            event.accept()

    def enterEvent(self, event):
        self._mark_user_active()
        super().enterEvent(event)

    def _handle_key_repeat(self):
        """处理按键持续按下的情况"""
        if self._current_key is not None:
            self._handle_key(self._current_key)

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            self._scale_up()
        elif event.angleDelta().y() < 0:
            self._scale_down()
        event.accept()

    def keyPressEvent(self, event):
        """键盘按键事件：移动宠物"""
        if not (QApplication.activeWindow() is self or self.hasFocus()):
            event.ignore()
            return
        self._mark_user_active()

        if event.matches(QKeySequence.StandardKey.Copy) or event.matches(QKeySequence.StandardKey.Paste):
            self._trigger_once("look", hold_ms=1200)
            event.accept()
            return

        key = event.key()
        text = event.text()

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._trigger_once("marry", hold_ms=1600)
            self._append_input_text("↵", show_action=False)
            event.accept()
            return

        if key == Qt.Key.Key_Space:
            self._trigger_once("knock", hold_ms=SPACE_HOLD_MS)
            if self._space_player.source().isValid():
                self._space_player.setPosition(0)
                self._space_player.play()
            event.accept()
            return

        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._trigger_once("cry", hold_ms=1800)
            self._backspace_input_text()
            event.accept()
            return

        if text in ("?", "？"):
            self._trigger_once("what", hold_ms=1400)
            event.accept()
            return

        if text and text.isprintable():
            self._append_input_text(text, show_action=True)

        self._current_key = int(key)
        self._handle_key(self._current_key)
        if key in [
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
        ]:
            self._key_repeat_timer.start()
        event.accept()
        return

    def keyReleaseEvent(self, event):
        """按键松开：如果是方向键或WASD键，恢复待机"""
        key = event.key()
        # 停止定时器
        if key in [Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down]:
            self._key_repeat_timer.stop()
            self._current_key = None
            if self._last_move_action is not None and self.current_action == self._last_move_action:
                self.change_action(self.default_action, mode='loop')

    def inputMethodEvent(self, event):
        self._mark_user_active()
        commit_text = event.commitString()
        if commit_text:
            self._append_input_text(commit_text, show_action=True)
        super().inputMethodEvent(event)

    def trigger_play(self):
        self._mark_user_active()
        self._trigger_once("play", hold_ms=1400)

    def trigger_feed(self):
        self._mark_user_active()
        if "eat" in self.actions and self.actions["eat"].get("visible", True):
            self._trigger_once("eat", hold_ms=1200)
        if "food" in self.actions and self.actions["food"].get("visible", True):
            QTimer.singleShot(1200, lambda: self._trigger_once("food", hold_ms=1200))

    def trigger_scold(self):
        self._mark_user_active()
        self._trigger_once("scold", hold_ms=1400)

    def trigger_praise(self):
        self._trigger_praise()

    def _toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            if self._is_master:
                QTimer.singleShot(0, self.init_focus)

    def _quit_app(self):
        for pet in list(ALL_PETS):
            try:
                pet.close()
            except Exception:
                pass
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _populate_action_menu(self, menu, close_on_trigger=False, register_tray=False):
        def wrap(handler):
            if not close_on_trigger:
                return handler
            def _handler():
                handler()
                if menu.isVisible():
                    menu.close()
            return _handler

        play_action = QAction("玩耍", self)
        play_action.triggered.connect(wrap(self.trigger_play))
        menu.addAction(play_action)

        feed_action = QAction("喂食", self)
        feed_action.triggered.connect(wrap(self.trigger_feed))
        menu.addAction(feed_action)

        scold_action = QAction("敲打", self)
        scold_action.triggered.connect(wrap(self.trigger_scold))
        menu.addAction(scold_action)

        praise_action = QAction("赞美", self)
        praise_action.triggered.connect(wrap(self.trigger_praise))
        menu.addAction(praise_action)

        menu.addSeparator()

        roam_action = QAction("自由活动", self)
        roam_action.setCheckable(True)
        roam_action.setChecked(self._roam_enabled)
        roam_action.triggered.connect(wrap(self._toggle_roam))
        menu.addAction(roam_action)
        if register_tray:
            self._tray_roam_action = roam_action

        chase_action = QAction("追逐鼠标", self)
        chase_action.setCheckable(True)
        chase_action.setChecked(self._chase_enabled)
        chase_action.triggered.connect(wrap(self._toggle_chase))
        menu.addAction(chase_action)
        if register_tray:
            self._tray_chase_action = chase_action

        mic_action = QAction("监听麦克风", self)
        mic_action.setCheckable(True)
        mic_action.setChecked(self._mic_enabled)
        mic_action.setEnabled(self._mic_available)
        mic_action.triggered.connect(wrap(self._toggle_mic))
        menu.addAction(mic_action)
        if register_tray:
            self._tray_mic_action = mic_action

        zoom_reset_action = QAction("重置大小", self)
        zoom_reset_action.triggered.connect(wrap(self._scale_reset))
        menu.addAction(zoom_reset_action)

        menu.addSeparator()

        toggle_action = QAction("显示/隐藏", self)
        toggle_action.triggered.connect(wrap(self._toggle_visibility))
        menu.addAction(toggle_action)

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(wrap(self._quit_app))
        menu.addAction(quit_action)

    def _show_context_menu(self, global_pos):
        try:
            if getattr(self, "_context_menu", None) is not None and self._context_menu.isVisible():
                self._context_menu.close()
        except RuntimeError:
            self._context_menu = None
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #FFFFFF;
                border: 1px solid #E0E0E0;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 4px 12px;
                border-radius: 4px;
                color: #333333;
                font-size: 12px;
                font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
            }
            QMenu::item:selected {
                background-color: #F0F0F0;
                color: #000000;
            }
            QMenu::separator {
                height: 1px;
                background: #E0E0E0;
                margin: 4px 10px;
            }
        """)
        menu.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._context_menu = menu
        menu.destroyed.connect(lambda _=None: setattr(self, "_context_menu", None))
        self._populate_action_menu(menu, close_on_trigger=True)
        menu.popup(global_pos)

    def contextMenuEvent(self, event):
        self._show_context_menu(event.globalPos())

    def init_menu(self):
        pass

    def _ensure_tray_icon_visible(self):
        if not self._is_master:
            return
        if getattr(self, "tray_icon", None) is None:
            self.init_tray_icon()
            return
        icon = self.tray_icon.icon()
        if icon.isNull():
            icon = self._build_app_icon()
            if icon.isNull():
                pixmap = QPixmap(16, 16)
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                painter.setBrush(Qt.GlobalColor.blue)
                painter.drawEllipse(2, 2, 12, 12)
                painter.end()
                icon = QIcon(pixmap)
            self.tray_icon.setIcon(icon)
        if not self.tray_icon.isVisible():
            self.tray_icon.setVisible(True)
            self.tray_icon.show()
            if not self.tray_icon.isVisible():
                self.tray_icon.hide()
                self.tray_icon.deleteLater()
                self.init_tray_icon()

    def init_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        icon = self._build_app_icon()
        if icon.isNull():
            pixmap = QPixmap(16, 16)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setBrush(Qt.GlobalColor.blue)
            painter.drawEllipse(2, 2, 12, 12)
            painter.end()
            icon = QIcon(pixmap)
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("桌宠")
        
        tray_menu = QMenu()
        tray_menu.setStyleSheet("""
            QMenu {
                background-color: #FFFFFF;
                border: 1px solid #E0E0E0;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 4px 12px;
                border-radius: 4px;
                color: #333333;
                font-size: 12px;
                font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
            }
            QMenu::item:selected {
                background-color: #F0F0F0;
                color: #000000;
            }
            QMenu::separator {
                height: 1px;
                background: #E0E0E0;
                margin: 4px 10px;
            }
        """)
        
        self._populate_action_menu(tray_menu, close_on_trigger=False, register_tray=True)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.setVisible(True)
        self.tray_icon.show()

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--assets-dir", default=None, help="素材目录路径（默认使用程序同目录下的 assets）")
    args, qt_argv = parser.parse_known_args()

    app = QApplication([sys.argv[0], *qt_argv])
    app.setQuitOnLastWindowClosed(False)
    pet = DesktopPet()
    icon = pet._build_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    sys.exit(app.exec())
