import sys
import os
import random
import re
import time
import ctypes
import ctypes.util
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QWidget, QMenu, QSystemTrayIcon
from PyQt6.QtCore import Qt, QTimer, QPoint, QEvent, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import (
    QPixmap,
    QIcon,
    QPainter,
    QCursor,
    QAction,
    QRegion,
    QMovie,
    QImageReader,
    QKeySequence,
)
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

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
# 默认大小 (根据图片素材调整)
PET_WIDTH = 128
PET_HEIGHT = 128
# 动画刷新间隔 (毫秒)
REFRESH_RATE = 80
# 移动速度 (键盘控制时)
MOVE_STEP = 5
SPACE_HOLD_MS = 2000
IDLE_TIMEOUT_MS = 6000
PRAISE_AUDIO_PATH = os.path.join(ASSET_FOLDER, "bgaudio", "long-typing-on-the-keyboard.mp3")
ENABLE_MAC_GLOBAL_HOTKEYS = True
MAC_GLOBAL_HOTKEYS_REQUIRE_ALT = False
# ===========================================

class MacGlobalKeyListener(QThread):
    keyPressed = pyqtSignal(int)
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
        self.statusChanged.emit(True, "全局热键已启用（默认需按住 Option(⌥) 才触发）")
        self._cf.CFRunLoopRun()

    def _handle_event(self, proxy, event_type, event, refcon):
        try:
            if event_type != 10:
                return event
            flags = int(self._cg.CGEventGetFlags(event))
            if MAC_GLOBAL_HOTKEYS_REQUIRE_ALT and not (flags & (1 << 19)):
                return event
            keycode = int(self._cg.CGEventGetIntegerValueField(event, 9))
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
        except Exception:
            return event
        return event

class DesktopPet(QWidget):
    def __init__(self):
        super().__init__()

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
        self._last_scaled_pixmap_by_action = {}
        self._last_move_action = None
        self._once_hold_timer = QTimer(self)
        self._once_hold_timer.setSingleShot(True)
        self._once_hold_timer.timeout.connect(self._end_once_hold)
        self._once_hold_action = None
        self._once_hold_back_to = None
        self._last_activity_ts = time.monotonic()
        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(0.9)
        self._praise_player = QMediaPlayer(self)
        self._praise_player.setAudioOutput(self._audio_output)
        self._mouse_down = False
        self._mouse_drag_started = False
        self._mouse_press_global = QPoint()
        
        # 拖拽相关
        self.is_dragging = False
        self.drag_position = QPoint()

        # 3. 加载素材
        self.load_images()
        if os.path.exists(PRAISE_AUDIO_PATH):
            self._praise_player.setSource(QUrl.fromLocalFile(os.path.abspath(PRAISE_AUDIO_PATH)))

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
        self.init_tray_icon()

        self._global_key_listener = None
        if sys.platform == "darwin" and ENABLE_MAC_GLOBAL_HOTKEYS:
            self._global_key_listener = MacGlobalKeyListener(self)
            self._global_key_listener.keyPressed.connect(self._handle_key)
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
        
        self._focus_attempts_left = 8
        QTimer.singleShot(0, self.init_focus)

    def init_focus(self):
        """初始化焦点，确保窗口能响应键盘事件"""
        if not self.isVisible():
            self.show()

        self.raise_()
        self.setWindowState(self.windowState() | Qt.WindowState.WindowActive)
        self.activateWindow()
        QApplication.instance().setActiveWindow(self)
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        self.grabKeyboard()

        if (QApplication.activeWindow() is self) or self.hasFocus():
            self.update()
            return

        self._focus_attempts_left -= 1
        if self._focus_attempts_left > 0:
            QTimer.singleShot(60, self.init_focus)
        else:
            self.update()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.init_focus)

    def event(self, event):
        if event.type() == QEvent.Type.WindowActivate:
            QTimer.singleShot(0, self.init_focus)
        return super().event(event)

    def closeEvent(self, event):
        if self._global_key_listener is not None:
            self._global_key_listener.stop()
        self.releaseKeyboard()
        super().closeEvent(event)

    def _on_global_hotkey_status(self, ok, message):
        print(message)

    def _mark_user_active(self):
        self._last_activity_ts = time.monotonic()
        if self.current_action == "attention" and self.default_action is not None:
            self.change_action(self.default_action, mode="loop")

    def _check_idle(self):
        if self.is_dragging:
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

    def _trigger_praise(self):
        self._mark_user_active()
        self._trigger_once("wow", hold_ms=1400)
        self._play_praise_audio()

    def _is_apng_file(self, path):
        try:
            with open(path, "rb") as f:
                header = f.read(8)
                if header != b"\x89PNG\r\n\x1a\n":
                    return False
                while True:
                    length_bytes = f.read(4)
                    if len(length_bytes) != 4:
                        return False
                    length = int.from_bytes(length_bytes, "big")
                    chunk_type = f.read(4)
                    if len(chunk_type) != 4:
                        return False
                    if chunk_type == b"acTL":
                        return True
                    if chunk_type in (b"IDAT", b"IEND"):
                        return False
                    f.seek(length + 4, os.SEEK_CUR)
        except Exception:
            return False

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
            cached = self._last_scaled_pixmap_by_action.get(self.current_action)
            if cached is not None and not cached.isNull():
                return cached
            return None

        scaled = pixmap.scaled(
            PET_WIDTH,
            PET_HEIGHT,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if not scaled.isNull():
            self._last_scaled_pixmap_by_action[self.current_action] = scaled
        return scaled

    def _end_once_hold(self):
        action_name = self._once_hold_action
        back_to = self._once_hold_back_to or self.default_action
        self._once_hold_action = None
        self._once_hold_back_to = None
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
        """加载 assets 文件夹下的所有图片文件作为动作"""
        if not os.path.exists(ASSET_FOLDER):
            print(f"错误: 未找到素材文件夹 {ASSET_FOLDER}，请确保它存在。")
            return

        self.actions.clear()
        self._movie_action_by_obj.clear()

        entries = sorted(os.listdir(ASSET_FOLDER))
        frame_idx_re = re.compile(r"^(?P<base>.*?)(?P<idx>\d+)$")
        for entry in entries:
            folder_path = os.path.join(ASSET_FOLDER, entry)
            if not os.path.isdir(folder_path):
                continue

            frame_files = sorted(
                [
                    f
                    for f in os.listdir(folder_path)
                    if f.lower().endswith((".png", ".jpg", ".jpeg"))
                ]
            )
            if not frame_files:
                continue

            items = []
            for f in frame_files:
                stem = os.path.splitext(f)[0]
                match = frame_idx_re.match(stem)
                idx = int(match.group("idx")) if match else None
                items.append((idx, f))
            items.sort(key=lambda t: (t[0] is None, t[0] if t[0] is not None else 0, t[1]))

            frames = []
            for _, f in items:
                pixmap = QPixmap(os.path.join(folder_path, f))
                if pixmap.isNull():
                    continue
                frames.append(
                    pixmap.scaled(
                        PET_WIDTH,
                        PET_HEIGHT,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )

            if frames:
                self.actions[entry] = {
                    "type": "frames",
                    "frames": frames,
                    "visible": self._pixmap_has_visible_pixel(frames[0]),
                }
                print(f"动作 '{entry}' 加载成功，共 {len(frames)} 帧")

        files = sorted(
            [
                f
                for f in os.listdir(ASSET_FOLDER)
                if f.lower().endswith((".png", ".gif", ".jpg", ".jpeg"))
            ]
        )

        seq_re = re.compile(r"^(?P<name>.+)_(?P<idx>\d+)$")
        seq_digits_re = re.compile(r"^(?P<name>.*?)(?P<idx>\d+)$")
        seq_frames = {}
        single_images = {}
        movies = {}

        for file in files:
            stem, ext = os.path.splitext(file)
            path = os.path.join(ASSET_FOLDER, file)
            if stem in self.actions:
                continue
            movie = self._try_create_movie(path)
            if movie is not None:
                movies[stem] = movie
                continue

            match = seq_re.match(stem)
            if match:
                action_name = match.group("name")
                idx = int(match.group("idx"))
                seq_frames.setdefault(action_name, []).append((idx, path))
            else:
                match = seq_digits_re.match(stem)
                if match and match.group("name") and not match.group("name").isdigit():
                    action_name = match.group("name")
                    idx = int(match.group("idx"))
                    seq_frames.setdefault(action_name, []).append((idx, path))
                else:
                    single_images[stem] = path

        for action_name, items in seq_frames.items():
            if action_name in self.actions:
                continue
            frames = []
            for _, path in sorted(items, key=lambda t: t[0]):
                pixmap = QPixmap(path)
                if pixmap.isNull():
                    continue
                frames.append(
                    pixmap.scaled(
                        PET_WIDTH,
                        PET_HEIGHT,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            if frames:
                self.actions[action_name] = {
                    "type": "frames",
                    "frames": frames,
                    "visible": self._pixmap_has_visible_pixel(frames[0]),
                }
                print(f"动作 '{action_name}' 加载成功，共 {len(frames)} 帧")

        for action_name, path in single_images.items():
            if action_name in self.actions:
                continue
            pixmap = QPixmap(path)
            if pixmap.isNull():
                continue
            pixmap = pixmap.scaled(
                PET_WIDTH,
                PET_HEIGHT,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.actions[action_name] = {
                "type": "frames",
                "frames": [pixmap],
                "visible": self._pixmap_has_visible_pixel(pixmap),
            }
            print(f"动作 '{action_name}' 加载成功，共 1 帧")

        for action_name, movie in movies.items():
            if action_name in self.actions:
                continue
            movie.setCacheMode(QMovie.CacheMode.CacheAll)
            movie.frameChanged.connect(self._on_movie_frame_changed)
            movie.finished.connect(self._on_movie_finished)
            self._movie_action_by_obj[movie] = action_name
            self.actions[action_name] = {"type": "movie", "movie": movie, "visible": True}
            print(f"动作 '{action_name}' 加载成功（GIF）")

        # 使用第一个加载的动作作为默认待机动作
        if self.actions:
            if "look" in self.actions and self.actions["look"].get("visible", True):
                self.default_action = "look"
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
            if self._once_hold_action == action_name and self._once_hold_timer.isActive():
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

        self.current_action = action_name
        self.action_mode = mode
        self.image_index = 0
        action = self.actions.get(self.current_action)
        if action and action.get("type") == "movie":
            movie = action.get("movie")
            if isinstance(movie, QMovie):
                self._movie_once_seen_nonzero = False
                if hasattr(movie, "setLoopCount"):
                    movie.setLoopCount(0 if mode == "loop" else 1)
                movie.start()
                self._current_movie = movie
        elif mode == "once" and hold_ms is not None:
            self._once_hold_action = action_name
            self._once_hold_back_to = back_to
            self._once_hold_timer.start(int(hold_ms))
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
                if self._once_hold_action == self.current_action:
                    self.image_index = max(0, len(frames) - 1)
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
        moved_direction = None

        if key == int(Qt.Key.Key_Left) or key == int(Qt.Key.Key_A):
            new_x -= MOVE_STEP
            moved = True
            moved_direction = "left"
        elif key == int(Qt.Key.Key_Right) or key == int(Qt.Key.Key_D):
            new_x += MOVE_STEP
            moved = True
            moved_direction = "right"
        elif key == int(Qt.Key.Key_Up) or key == int(Qt.Key.Key_W):
            new_y -= MOVE_STEP
            moved = True
            moved_direction = "up"
        elif key == int(Qt.Key.Key_Down) or key == int(Qt.Key.Key_S):
            new_y += MOVE_STEP
            moved = True
            moved_direction = "down"

        if moved:
            screen_geometry = QApplication.primaryScreen().availableGeometry()
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
            self._trigger_once("look", hold_ms=SPACE_HOLD_MS)

    def paintEvent(self, event):
        """绘图事件"""
        pixmap = self._current_scaled_pixmap()
        if pixmap is None or pixmap.isNull():
            return

        painter = QPainter(self)
        painter.setClipping(False)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        x = (self.width() - pixmap.width()) // 2
        y = (self.height() - pixmap.height()) // 2
        painter.drawPixmap(x, y, pixmap)

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

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._mark_user_active()
            if self._mouse_down and not self._mouse_drag_started:
                self.trigger_play()
            self._mouse_down = False
            self._mouse_drag_started = False
            self.is_dragging = False
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
                self.move(event.globalPosition().toPoint() - self.drag_position)
                self.update()
                event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._mark_user_active()
            self.trigger_play()
            event.accept()

    def _handle_key_repeat(self):
        """处理按键持续按下的情况"""
        if self._current_key is not None:
            self._handle_key(self._current_key)

    def keyPressEvent(self, event):
        """键盘按键事件：移动宠物"""
        self._mark_user_active()

        if event.matches(QKeySequence.StandardKey.Copy) or event.matches(QKeySequence.StandardKey.Paste):
            self._trigger_once("guilty conscience", hold_ms=1200)
            event.accept()
            return

        key = event.key()
        text = event.text()

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._trigger_once("sly smile", hold_ms=1600)
            event.accept()
            return

        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._trigger_once("cry", hold_ms=1800)
            event.accept()
            return

        if text in ("?", "？"):
            self._trigger_once("questioned", hold_ms=1400)
            event.accept()
            return

        self._current_key = int(key)
        self._handle_key(self._current_key)
        if key in [
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
            Qt.Key.Key_W,
            Qt.Key.Key_A,
            Qt.Key.Key_S,
            Qt.Key.Key_D,
        ]:
            self._key_repeat_timer.start()
        event.accept()
        return

    def keyReleaseEvent(self, event):
        """按键松开：如果是方向键或WASD键，恢复待机"""
        key = event.key()
        # 停止定时器
        if key in [Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_W, Qt.Key.Key_A, Qt.Key.Key_S, Qt.Key.Key_D]:
            self._key_repeat_timer.stop()
            self._current_key = None
            if self._last_move_action is not None and self.current_action == self._last_move_action:
                self.change_action(self.default_action, mode='loop')

    def random_behavior(self):
        """随机行为"""
        # 只有在待机状态且没被拖拽时才触发随机行为
        if not self.is_dragging and self.current_action == self.default_action:
            # 30% 概率做个小动作（如果有的话）
            if random.random() < 0.3:
                candidates = []
                for name in ["look", "xinxu", "wow", "xixi", "me", "ganm", "ma", "cry", "Shocked", "dajiao"]:
                    meta = self.actions.get(name)
                    if meta is not None and meta.get("visible", True) and name != self.default_action:
                        candidates.append(name)
                if candidates:
                    self.change_action(random.choice(candidates), mode="once", hold_ms=1100, back_to=self.default_action)

    def _choose_action(self, candidates):
        for name in candidates:
            if name in self.actions:
                return name
        return None

    def trigger_play(self):
        self._mark_user_active()
        self._trigger_once("Appear", hold_ms=1400)

    def trigger_scold(self):
        self._mark_user_active()
        self._trigger_once("scold", hold_ms=1400)

    def trigger_praise(self):
        self._trigger_praise()

    def contextMenuEvent(self, event):
        """右键菜单"""
        menu = QMenu(self)
        play_action = QAction("玩耍", self)
        play_action.triggered.connect(self.trigger_play)
        menu.addAction(play_action)

        scold_action = QAction("敲打", self)
        scold_action.triggered.connect(self.trigger_scold)
        menu.addAction(scold_action)

        praise_action = QAction("赞美", self)
        praise_action.triggered.connect(self.trigger_praise)
        menu.addAction(praise_action)

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)
        menu.exec(event.globalPos())

    def init_menu(self):
        pass

    def init_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        # 简单绘制一个托盘图标
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setBrush(Qt.GlobalColor.blue)
        painter.drawEllipse(2, 2, 12, 12)
        painter.end()
        self.tray_icon.setIcon(QIcon(pixmap))
        
        tray_menu = QMenu()
        play_action = QAction("玩耍", self)
        play_action.triggered.connect(self.trigger_play)
        tray_menu.addAction(play_action)

        scold_action = QAction("敲打", self)
        scold_action.triggered.connect(self.trigger_scold)
        tray_menu.addAction(scold_action)

        praise_action = QAction("赞美", self)
        praise_action.triggered.connect(self.trigger_praise)
        tray_menu.addAction(praise_action)

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.close)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--assets-dir", default=None, help="素材目录路径（默认使用程序同目录下的 assets）")
    args, qt_argv = parser.parse_known_args()

    if args.assets_dir:
        ASSET_FOLDER = str(Path(args.assets_dir).expanduser().resolve())
        PRAISE_AUDIO_PATH = os.path.join(ASSET_FOLDER, "bgaudio", "long-typing-on-the-keyboard.mp3")

    app = QApplication([sys.argv[0], *qt_argv])
    pet = DesktopPet()
    sys.exit(app.exec())
