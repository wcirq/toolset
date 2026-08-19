from .common import *
from .effects import Particle
from .detection import CameraThread
from .ui.chat import ChatOverlay
from .ui.preview import CameraPreview
from .ui.dialogs import AuthDialog, SettingsDialog

# ======================== 小猫主窗口 ========================
class CatWindow(QWidget):
    """无边框透明置顶的小猫悬浮窗口"""

    # 状态枚举
    IDLE = "idle"
    HAPPY = "happy"
    SLEEP = "sleep"
    PLAY = "play"
    DRAG = "drag"

    def __init__(self):
        super().__init__()

        # ---------- 加载配置 ----------
        self.config = load_config()
        self.cat_scale = max(0.6, min(2.0, float(self.config["cat_scale"])))
        self._monitoring_requested = True       # 每次启动默认启用监控
        self._monitor_auto_paused = False
        self.camera_thread = None
        self._previous_window_hwnd = None
        # 开机启动状态 (从注册表读取)
        self._autostart_on = is_autostart_enabled()

        self._setup_window()
        self._init_state()
        self.chat = ChatOverlay(self)
        self._setup_tray()
        self._apply_scale(self.cat_scale, keep_center=False)

        # ---------- 摄像头人体检测 ----------
        self.cam_ok = None                     # None=初始化中 True/False
        self.preview = CameraPreview(self)
        self.preview.hide()
        self.longpress_active = False           # 长按显示预览中
        self._multi_triggered = False           # 防止重复触发 VS 切换
        self._last_auto_switch_at = None         # 上次自动触发切换的单调时间

        self.return_timer = QTimer(self)
        self.return_timer.setSingleShot(True)
        self.return_timer.timeout.connect(self._return_to_previous_window)

        self._start_camera_thread()

        self.fullscreen_timer = QTimer(self)
        self.fullscreen_timer.timeout.connect(self._check_auto_pause)
        self.fullscreen_timer.start(2000)

        # 长按检测计时器 (500ms 未移动未释放 → 长按)
        self.press_timer = QTimer(self)
        self.press_timer.setSingleShot(True)
        self.press_timer.timeout.connect(self._on_long_press)

        # ---------- 全局快捷键 ----------
        self.hotkey_mgr = HotkeyManager(self._on_hotkey)
        QApplication.instance().installNativeEventFilter(self.hotkey_mgr)
        self._apply_hotkey()

        self._start_timer()

    # ---------- 全局快捷键 / 目标程序切换 ----------

    def _apply_hotkey(self):
        """按当前配置注册全局快捷键"""
        try:
            hwnd = int(self.winId())
            enabled = self.config.get("hotkey_enabled", True)
            ok = self.hotkey_mgr.register(
                hwnd, self.config.get("hotkey", "Ctrl+Alt+V"), enabled)
            if not ok and enabled:
                self._say("快捷键被占用了...")
        except Exception as e:
            _log(f"快捷键注册异常: {e}\n{traceback.format_exc()}")

    def _on_hotkey(self):
        """有原窗口时优先切回; 否则立即切换到目标程序。"""
        _log("全局快捷键触发")
        self._set_state(self.PLAY, 45)
        if self._previous_window_hwnd and user32.IsWindow(self._previous_window_hwnd):
            self._return_to_previous_window(manual=True)
        else:
            self._do_switch_target("切!")

    def _do_switch_target(self, tip=""):
        """执行切换到目标程序 (配置中的 target_exe / target_title)"""
        before_hwnd = user32.GetForegroundWindow()
        if tip:
            self._say(tip, 80)
        ok, msg = switch_to_target(
            title_keyword=self.config.get("target_title", ""),
            exe_keyword=self.config.get("target_exe", ""),
            maximize=bool(self.config.get("maximize_target", False)),
        )
        _log(f"切换目标程序: ok={ok} msg={msg}")
        after_hwnd = user32.GetForegroundWindow()
        if ok and before_hwnd and before_hwnd != after_hwnd:
            self._previous_window_hwnd = before_hwnd
            _log(f"已记录切换前窗口: hwnd={before_hwnd}")
        if not ok:
            self._say(f"{msg[:16]}...", 120)

    def _return_to_previous_window(self, manual=False):
        """切回最近一次切换前的窗口; 成功后清除记录。"""
        self.return_timer.stop()
        hwnd = self._previous_window_hwnd
        if not hwnd or not user32.IsWindow(hwnd):
            self._previous_window_hwnd = None
            if manual:
                self._say("没有可切回的窗口~", 100)
            return
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        ok = _force_foreground(hwnd)
        _log(f"切回原窗口: hwnd={hwnd} ok={ok}")
        if ok:
            self._previous_window_hwnd = None
            self._say("已切回原窗口~", 90)
        else:
            self._say("切回被系统拦住了...", 110)

    # ---------- 摄像头线程管理 ----------

    def _start_camera_thread(self):
        """按当前配置创建并启动摄像头检测线程"""
        if not self._monitoring_requested or self._monitor_auto_paused:
            self.camera_thread = None
            return
        cfg = self.config
        self.camera_thread = CameraThread(
            camera_index=cfg["camera_index"],
            model=cfg["model"],
            yolo_model=cfg["yolo_model"],
            yolo_conf=cfg["yolo_conf"],
            pose_kpt_conf=cfg.get("pose_kpt_conf", 0.5),
            trigger_count=cfg["trigger_count"],
            sustain_sec=cfg["sustain_sec"],
            debug_save=cfg.get("debug_save", False),
            dedup_iou=cfg.get("dedup_iou", 0.55),
        )
        self.camera_thread.frame_ready.connect(self._on_camera_frame)
        self.camera_thread.person_count_changed.connect(self._on_person_count)
        self.camera_thread.camera_error.connect(self._on_camera_error)
        self.camera_thread.start()

    def _stop_camera_thread(self):
        thread = self.camera_thread
        self.camera_thread = None
        if thread is not None and thread.isRunning():
            thread.stop()

    def _sync_monitoring(self):
        should_run = self._monitoring_requested and not self._monitor_auto_paused
        is_running = self.camera_thread is not None and self.camera_thread.isRunning()
        if should_run and not is_running:
            self._start_camera_thread()
        elif not should_run and self.camera_thread is not None:
            self._stop_camera_thread()
            self.preview.hide()
            self._multi_triggered = False
            self.return_timer.stop()
        if hasattr(self, "_tray_monitor_act"):
            self._tray_monitor_act.setText(
                "暂停监控" if self._monitoring_requested else "启用监控")

    def _toggle_monitoring(self):
        self._monitoring_requested = not self._monitoring_requested
        self._sync_monitoring()
        if self._monitoring_requested and self._monitor_auto_paused:
            self._say("当前全屏中，退出后恢复监控~", 130)
        else:
            self._say("监控已启用~" if self._monitoring_requested else "监控已暂停~", 100)

    def _check_auto_pause(self):
        enabled = bool(self.config.get("auto_pause_fullscreen", False))
        paused = enabled and is_foreground_fullscreen(int(self.winId()))
        if paused == self._monitor_auto_paused:
            return
        self._monitor_auto_paused = paused
        _log("全屏状态触发自动暂停监控" if paused else "全屏结束, 恢复监控")
        self._sync_monitoring()

    def _restart_camera_thread(self):
        """配置修改后重启检测线程"""
        self._stop_camera_thread()
        self._sync_monitoring()

    # ---------- 设置对话框 ----------

    def _apply_visual_settings(self, cfg, show_preview=False):
        """实时预览小猫外观和预览窗口; 不写入配置文件。"""
        saved_scale = self.config.get("cat_scale", self.cat_scale)
        self._apply_scale(cfg.get("cat_scale", self.cat_scale))
        self.config["cat_scale"] = saved_scale

        self.style_idx = max(0, min(len(CAT_STYLES) - 1,
                                   int(cfg.get("cat_style", 0))))
        self.style = CAT_STYLES[self.style_idx]
        self.color_idx = max(0, min(len(COLORS) - 1,
                                   int(cfg.get("cat_color", 0))))
        self.c = COLORS[self.color_idx]

        self.preview.window_opacity = max(0.2, min(
            1.0, float(cfg.get("preview_window_opacity", 0.85))))
        self.preview.video_opacity = max(0.2, min(
            1.0, float(cfg.get("preview_video_opacity", 0.85))))
        self.preview.overlay_opacity = max(0.2, min(
            1.0, float(cfg.get("preview_overlay_opacity", 1.0))))
        self.update()
        self.preview.update()
        if show_preview:
            self._show_preview()

    def _apply_settings_config(self, new_cfg):
        """保存并应用设置, 设置窗口保持打开。"""
        old = dict(self.config)
        self.config = dict(new_cfg)
        save_config(self.config)
        self._apply_visual_settings(self.config, show_preview=False)
        # _apply_visual_settings 为防止实时预览污染配置会恢复缩放,
        # 正式保存后在内存配置中确保保留新值。
        self.config["cat_scale"] = new_cfg["cat_scale"]

        cam_keys = ("model", "yolo_model", "yolo_conf", "pose_kpt_conf",
                    "trigger_count", "sustain_sec", "camera_index", "dedup_iou")
        if any(new_cfg[k] != old.get(k) for k in cam_keys):
            model_name = "YOLOv26" if new_cfg["model"] == "yolo" else "HOG"
            self._say(f"已切换 {model_name} 检测~")
            self._restart_camera_thread()

        if any(new_cfg[k] != old.get(k) for k in ("hotkey", "hotkey_enabled")):
            self._apply_hotkey()
            hk = new_cfg["hotkey"] if new_cfg["hotkey_enabled"] else "快捷键已关闭"
            self._say(f"{hk}~", 90)

        if (new_cfg.get("debug_save", False) != old.get("debug_save", False)
                and self.camera_thread is not None):
            self.camera_thread.debug_save = new_cfg["debug_save"]

        if new_cfg.get("auto_pause_fullscreen", False) != old.get(
                "auto_pause_fullscreen", False):
            self._check_auto_pause()

        if any(new_cfg[k] != old.get(k) for k in ("target_exe", "target_title")):
            name = new_cfg["target_exe"] or new_cfg["target_title"] or "未设置"
            self._say(f"目标程序: {name}", 120)

    def _open_settings(self):
        try:
            # ---------- 密码验证 (哈希比对) ----------
            cur_hash = self.config.get("settings_password_hash",
                                       DEFAULT_CONFIG["settings_password_hash"])
            auth = AuthDialog(cur_hash, parent=self)
            if auth.exec_() != QDialog.Accepted:
                return

            # 检查 ultralytics 是否可用 (用于对话框提示)
            yolo_ok = False
            try:
                import ultralytics  # noqa
                yolo_ok = True
            except Exception:
                # ImportError: 未安装; OSError/WinError 1114: DLL 加载失败
                pass

            dlg = SettingsDialog(self.config, yolo_ok, parent=self)
            dlg.exec_()
        except Exception as e:
            _log(f"!!! 设置对话框异常: {e}\n{traceback.format_exc()}")

    # ---------- 小猫尺寸缩放 ----------

    def _apply_scale(self, scale, keep_center=True):
        """按倍率缩放小猫窗口 (绘制时用 painter 变换)"""
        scale = max(0.6, min(2.0, float(scale)))
        old_w, old_h = self.width(), self.height()
        # 以当前中心为锚点缩放
        cx = self.x() + old_w // 2
        cy = self.y() + old_h // 2
        new_w, new_h = int(W * scale), int(H * scale)
        self.cat_scale = scale
        self.resize(new_w, new_h)
        if keep_center:
            self.move(cx - new_w // 2, cy - new_h // 2)
        self.config["cat_scale"] = scale
        self.update()

    def _change_cat_size(self, delta):
        """右键菜单 +/- 快速调整尺寸 (每次 20%)"""
        new_scale = self.cat_scale + delta
        new_scale = max(0.6, min(2.0, new_scale))
        if abs(new_scale - self.cat_scale) > 0.001:
            self._apply_scale(new_scale)
            save_config(self.config)
            self._say(f"{int(self.cat_scale * 100)}% 大啦~", 90)

    # ---------- 摄像头回调 ----------

    def _on_camera_frame(self, qimg, boxes, confs=None, skipped=None, kpts=None):
        self.cam_ok = True
        self.preview.update_frame(qimg, boxes, confs, skipped, kpts)

    def _on_camera_error(self, msg):
        self.cam_ok = False
        _log(f"摄像头错误: {msg}")
        if "YOLO" in msg or "ultralytics" in msg:
            self._say("YOLO不可用, 用HOG检测~")
        else:
            self._say("摄像头打不开...")

    def _on_person_count(self, count):
        _log(f"人数变化: {count}")
        threshold = self.config.get("trigger_count", 2)
        if count >= threshold:
            self.return_timer.stop()
            if not self._multi_triggered:
                self._multi_triggered = True
                now = time.monotonic()
                cooldown = max(0.0, float(
                    self.config.get("trigger_cooldown_sec", 10.0)))
                if (self._last_auto_switch_at is not None and cooldown > 0 and
                        now - self._last_auto_switch_at < cooldown):
                    remaining = cooldown - (now - self._last_auto_switch_at)
                    _log(f"触发处于冷却期, 剩余 {remaining:.1f} 秒, 忽略本次切换")
                    return
                self._last_auto_switch_at = now
                self._spawn_particles("sparkle", 5)
                self._do_switch_target("有别人来了! 切换!")
        else:
            # 人离开, 重置触发标记
            self._multi_triggered = False
            if (self._previous_window_hwnd
                    and self.config.get("auto_return_enabled", False)):
                delay_ms = int(max(1.0, float(self.config.get(
                    "auto_return_delay_sec", 10.0))) * 1000)
                if not self.return_timer.isActive():
                    self.return_timer.start(delay_ms)
                    _log(f"人员离开, {delay_ms / 1000:.1f} 秒后自动切回")

    # ---------- 长按显示/隐藏预览 ----------

    def _on_long_press(self):
        """左键按住 500ms 且未拖动 → 显示摄像头预览"""
        if self.dragging and self.drag_distance < 8:
            self.longpress_active = True
            self._set_state(self.PLAY, 0)
            self._say("看看谁在偷看~")
            self._show_preview()

    def _show_preview(self):
        self._position_preview()
        self.preview.show()
        self.preview.raise_()

    def _hide_preview(self):
        self.preview.hide()
        self.longpress_active = False
        if self.state == self.PLAY:
            self._set_state(self.IDLE, 0)

    def _position_preview(self):
        """将预览窗口放到小猫旁边 (优先右侧, 空间不足放左侧)"""
        pw, ph = self.preview.width(), self.preview.height()
        screen = QApplication.primaryScreen().geometry()
        margin = 16

        px = self.x() + self.width() + margin
        if px + pw > screen.width():
            px = self.x() - pw - margin
        py = self.y() - (ph - self.height()) // 2
        py = max(8, min(screen.height() - ph - 8, py))
        px = max(8, px)
        self.preview.move(px, py)

    # ---------- 初始化 ----------

    def _setup_window(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        sw = int(W * self.cat_scale)
        sh = int(H * self.cat_scale)
        self.resize(sw, sh)
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - sw - 60, screen.height() - sh - 40)

    def _init_state(self):
        self.state = self.IDLE
        self.prev_state = self.IDLE
        # 颜色从配置读取 (上次选的), 越界则回退橘猫
        idx = int(self.config.get("cat_color", 0))
        self.color_idx = idx if 0 <= idx < len(COLORS) else 0
        self.c = COLORS[self.color_idx]
        style_idx = int(self.config.get("cat_style", 0))
        self.style_idx = style_idx if 0 <= style_idx < len(CAT_STYLES) else 0
        self.style = CAT_STYLES[self.style_idx]

        self.frame = 0
        self.state_frame = 0
        self._state_duration = 0

        # 眨眼
        self.blink_cd = random.randint(120, 300)
        self.blink_left = 0

        # 眼睛跟随鼠标
        self.eye_x = 0.0
        self.eye_y = 0.0
        self.eye_tx = 0.0
        self.eye_ty = 0.0

        # 弹跳
        self.bounce = 0.0

        # 尾巴
        self.tail_phase = 0.0
        self.tail_speed = 0.04

        # 粒子
        self.particles = []

        # 对话
        self.speech = ""
        self.speech_left = 0
        self.speech_cd = random.randint(400, 800)

        # 拖拽
        self.dragging = False
        self.drag_start = QPoint(0, 0)
        self.drag_offset = QPoint(0, 0)
        self.drag_distance = 0.0
        self.shake = 0

        # 跟随鼠标
        self.follow = False

        # 闲置计时
        self.idle_time = 0

        # 贴边吸附
        self.snap_edge = None       # None / "left" / "right" / "top" / "bottom"
        self.snap_anim = 1.0        # 0=隐藏 1=完全可见
        self.snap_target = 1.0      # 动画目标值
        self.snap_pos = 0           # 吸附时的次要坐标 (左右吸附记录Y, 上下吸附记录X)
        self.peek_size = 55         # 兜底探出像素 (实际由 _peek_amount() 动态计算)

    def _peek_amount(self):
        """
        贴边后屏幕内可见的窗口厚度。
        上/下边缘露出当前窗口高度的 1/4;
        左/右边缘露出当前窗口宽度的 1/4。
        """
        if self.snap_edge in ("left", "right"):
            return max(1, int(round(self.width() * 0.25)))
        if self.snap_edge in ("top", "bottom"):
            return max(1, int(round(self.height() * 0.25)))
        return max(1, int(round(min(self.width(), self.height()) * 0.25)))

    def _setup_tray(self):
        """系统托盘图标"""
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(QIcon(self._make_tray_icon()))
        self.tray.setToolTip("桌面小猫 - 双击图标显示")
        self.tray.show()

        menu = QMenu()
        menu.addAction("显示小猫", self.show_cat)
        self._tray_monitor_act = menu.addAction("暂停监控", self._toggle_monitoring)
        interact = menu.addMenu("与小猫互动")
        interact.addAction("摸摸猫", self._pet)
        interact.addAction("玩耍", lambda: self._set_state(self.PLAY, 180))
        interact.addAction("睡觉/起床", self._toggle_sleep)
        interact.addAction("跟随鼠标", self._toggle_follow)
        menu.addAction("设置...", self._open_settings)
        # 开机启动 (勾选状态在弹出时刷新)
        self._tray_autostart_act = menu.addAction("开机启动")
        self._tray_autostart_act.setCheckable(True)
        self._tray_autostart_act.setChecked(self._autostart_on)
        self._tray_autostart_act.triggered.connect(self._toggle_autostart)
        menu.aboutToShow.connect(
            lambda: self._tray_autostart_act.setChecked(self._autostart_on))
        menu.addSeparator()
        menu.addAction("退出", self._quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)

    def _make_tray_icon(self):
        """生成托盘图标 pixmap"""
        pix = QPixmap(64, 64)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        # 耳朵
        p.setBrush(QBrush(QColor("#FFB347")))
        p.setPen(Qt.NoPen)
        ear_l = QPainterPath()
        ear_l.moveTo(14, 22)
        ear_l.lineTo(18, 4)
        ear_l.lineTo(28, 18)
        ear_l.closeSubpath()
        p.drawPath(ear_l)
        ear_r = QPainterPath()
        ear_r.moveTo(50, 22)
        ear_r.lineTo(46, 4)
        ear_r.lineTo(36, 18)
        ear_r.closeSubpath()
        p.drawPath(ear_r)
        # 头
        p.drawEllipse(QRectF(10, 16, 44, 44))
        # 眼睛
        p.setBrush(QBrush(QColor("#2C2C2C")))
        p.drawEllipse(QRectF(22, 30, 7, 10))
        p.drawEllipse(QRectF(35, 30, 7, 10))
        # 高光
        p.setBrush(QBrush(QColor(255, 255, 255, 220)))
        p.drawEllipse(QRectF(23, 31, 2.5, 3))
        p.drawEllipse(QRectF(36, 31, 2.5, 3))
        # 鼻子
        p.setBrush(QBrush(QColor("#FF6B9D")))
        nose = QPainterPath()
        nose.moveTo(29, 40)
        nose.lineTo(35, 40)
        nose.lineTo(32, 44)
        nose.closeSubpath()
        p.drawPath(nose)
        p.end()
        return pix

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_cat()

    def show_cat(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _quit(self):
        # 注销全局快捷键
        try:
            self.hotkey_mgr.unregister()
        except Exception:
            pass
        # 停止摄像头线程
        if self.camera_thread is not None and self.camera_thread.isRunning():
            self.camera_thread.stop()
        self.preview.hide()
        self.tray.hide()
        QApplication.quit()

    # ---------- 状态管理 ----------

    def _toggle_autostart(self, checked):
        """右键菜单: 开启/取消开机启动 (写注册表 HKCU Run)"""
        ok = set_autostart(bool(checked))
        if ok:
            self._autostart_on = bool(checked)
            self._say("开机启动已开启~" if checked else "开机启动已取消", 120)
        else:
            # 失败则回滚菜单勾选状态
            self._autostart_on = is_autostart_enabled()
            self._say("设置开机启动失败!", 120)

    def _set_state(self, state, duration=0):
        """切换状态, duration>0 表示持续时间(帧)后自动回到IDLE"""
        if state == self.state and duration == 0:
            return
        self.prev_state = self.state
        self.state = state
        self.state_frame = 0
        self._state_duration = duration
        self.idle_time = 0

    def _say(self, text, duration=150):
        self.speech = text
        self.speech_left = duration

    def _spawn_particles(self, kind, count, x=None, y=None):
        px = x if x is not None else CX
        py = y if y is not None else CY - 10
        for _ in range(count):
            self.particles.append(Particle(
                px + random.uniform(-25, 25),
                py + random.uniform(-15, 5),
                kind
            ))

    def _pet(self):
        self._set_state(self.HAPPY, 120)
        self._spawn_particles("heart", 6)
        self._say(random.choice(SPEECHES["happy"]), 120)

    def _toggle_follow(self):
        self.follow = not self.follow
        if self.follow:
            self._say("来追我呀~")
        else:
            self._say("不追了~")

    def _toggle_chat(self):
        # 聊天输入功能暂时禁用 (chat_enabled 配置控制, 恢复设 True 即可)
        if not self.config.get("chat_enabled", False):
            if self.chat.isVisible():
                self.chat.hide()
            self._say("聊天功能暂停中~", 90)
            return
        _log(f"_toggle_chat 调用, chat.isVisible={self.chat.isVisible()}")
        try:
            if self.chat.isVisible():
                self.chat.hide()
                _log("_toggle_chat: 隐藏聊天框")
            else:
                self.chat.messages.clear()
                self.chat.show()
                _log("_toggle_chat: 显示聊天框")
        except Exception as e:
            _log(f"!!! _toggle_chat 异常: {e}\n{traceback.format_exc()}")

    def _toggle_sleep(self):
        if self.state == self.SLEEP:
            self._set_state(self.IDLE, 0)
            self._say("醒啦~")
        else:
            self._set_state(self.SLEEP, 0)
            self._say("晚安~")

    def _change_color(self):
        self.color_idx = (self.color_idx + 1) % len(COLORS)
        self.c = COLORS[self.color_idx]
        # 写入配置, 下次启动生效
        try:
            self.config["cat_color"] = self.color_idx
            save_config(self.config)
        except Exception as e:
            _log(f"保存颜色失败: {e}")
        self._say("我是" + self.c["name"] + "!", 120)
        self._spawn_particles("sparkle", 8)

    # ---------- 动画循环 ----------

    def _start_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000 // FPS)

    def _tick(self):
        try:
            self.frame += 1
            self.state_frame += 1

            # 自动状态回归
            if self._state_duration > 0 and self.state_frame >= self._state_duration:
                self._set_state(self.IDLE, 0)

            self._update_blink()
            self._update_eyes()
            self._update_bounce()
            self.tail_phase += self.tail_speed
            self._update_particles()
            self._update_speech()

            if self.follow:
                self._update_follow()

            # 闲置自动睡觉 (40秒)
            if self.state == self.IDLE:
                self.idle_time += 1
                if self.idle_time > 2400:
                    self._set_state(self.SLEEP, 0)
            else:
                self.idle_time = 0

            # 睡觉时产�� Z 粒子
            if self.state == self.SLEEP and self.frame % 50 == 0:
                self.particles.append(Particle(CX + 30, CY - 20, "z"))

            # 玩耍时产生星星粒子
            if self.state == self.PLAY and self.frame % 12 == 0:
                self.particles.append(Particle(
                    CX + random.uniform(-35, 35),
                    CY + random.uniform(-25, 25),
                    random.choice(["star", "sparkle"])
                ))

            if self.shake > 0:
                self.shake -= 1

            self._update_snap()
            self._check_snap_hover()

            self.update()
        except Exception as e:
            _log(f"!!! CatWindow._tick 异常 (frame={self.frame}): {e}\n{traceback.format_exc()}")

    def _update_blink(self):
        if self.state == self.SLEEP:
            return
        if self.blink_left > 0:
            self.blink_left -= 1
        else:
            self.blink_cd -= 1
            if self.blink_cd <= 0:
                self.blink_left = 8
                self.blink_cd = random.randint(120, 360)

    def _update_eyes(self):
        if self.state in (self.SLEEP, self.HAPPY):
            return
        mouse = self.mapFromGlobal(QCursor.pos())
        # 屏幕坐标 → 逻辑画布坐标 (除以缩放倍率)
        mx = mouse.x() / self.cat_scale
        my = mouse.y() / self.cat_scale
        dx = mx - CX
        dy = my - CY
        dist = max(1.0, math.sqrt(dx * dx + dy * dy))
        max_off = 4.0
        self.eye_tx = (dx / dist) * min(max_off, dist / 20)
        self.eye_ty = (dy / dist) * min(max_off, dist / 20)
        self.eye_x += (self.eye_tx - self.eye_x) * 0.15
        self.eye_y += (self.eye_ty - self.eye_y) * 0.15

    def _update_bounce(self):
        if self.state == self.HAPPY:
            self.bounce = abs(math.sin(self.frame * 0.18)) * 10
            self.tail_speed = 0.12
        elif self.state == self.PLAY:
            self.bounce = abs(math.sin(self.frame * 0.22)) * 16
            self.tail_speed = 0.15
        elif self.state == self.SLEEP:
            self.bounce = math.sin(self.frame * 0.025) * 2
            self.tail_speed = 0.01
        elif self.state == self.DRAG:
            self.bounce = math.sin(self.frame * 0.4) * 3
            self.tail_speed = 0.08
        else:
            self.bounce = math.sin(self.frame * 0.04) * 1.5
            self.tail_speed = 0.04

    def _update_particles(self):
        self.particles = [p for p in self.particles if p.alive]
        for p in self.particles:
            p.update()

    def _update_speech(self):
        if self.speech_left > 0:
            self.speech_left -= 1
        else:
            self.speech = ""
        if not self.speech:
            self.speech_cd -= 1
            if self.speech_cd <= 0:
                if self.state in SPEECHES:
                    self._say(random.choice(SPEECHES[self.state]), 120)
                self.speech_cd = random.randint(500, 1200)

    def _update_follow(self):
        mouse = QCursor.pos()
        win_w, win_h = self.width(), self.height()
        target_x = mouse.x() - win_w // 2
        target_y = mouse.y() - win_h // 2
        cx, cy = self.x(), self.y()
        dx = target_x - cx
        dy = target_y - cy
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > 5:
            speed = min(dist * 0.06, 12)
            new_x = int(cx + dx / dist * speed)
            new_y = int(cy + dy / dist * speed)
            screen = QApplication.primaryScreen().geometry()
            new_x = max(-50, min(screen.width() - win_w + 50, new_x))
            new_y = max(-50, min(screen.height() - win_h + 50, new_y))
            self.move(new_x, new_y)

    # ======================== 贴边吸附 ========================

    def _check_snap(self):
        """拖拽释放时检测是否应该吸附到屏幕边缘"""
        screen = QApplication.primaryScreen().geometry()
        x, y = self.x(), self.y()
        win_w, win_h = self.width(), self.height()
        threshold = 80

        snap_to = None
        if x < threshold:
            snap_to = "left"
            self.snap_pos = y
        elif x + win_w > screen.width() - threshold:
            snap_to = "right"
            self.snap_pos = y
        elif y < threshold:
            snap_to = "top"
            self.snap_pos = x
        elif y + win_h > screen.height() - threshold:
            snap_to = "bottom"
            self.snap_pos = x

        if snap_to:
            self.snap_edge = snap_to
            self.snap_anim = 1.0
            self.snap_target = 0.0  # 开始向边缘缩入
            self._say("嗖~", 80)
        else:
            self.snap_edge = None
            self.snap_anim = 1.0
            self.snap_target = 1.0

    def _update_snap(self):
        """贴边吸附动画更新"""
        if self.snap_edge is None:
            return

        # 平滑动画
        speed = 0.12
        self.snap_anim += (self.snap_target - self.snap_anim) * speed

        screen = QApplication.primaryScreen().geometry()
        win_w, win_h = self.width(), self.height()

        if self.snap_edge == "left":
            full_x = 0
            hidden_x = self._peek_amount() - win_w
            new_x = hidden_x + (full_x - hidden_x) * self.snap_anim
            self.move(int(new_x), self.snap_pos)

        elif self.snap_edge == "right":
            full_x = screen.width() - win_w
            hidden_x = screen.width() - self._peek_amount()
            new_x = hidden_x + (full_x - hidden_x) * self.snap_anim
            self.move(int(new_x), self.snap_pos)

        elif self.snap_edge == "top":
            full_y = 0
            hidden_y = self._peek_amount() - win_h
            new_y = hidden_y + (full_y - hidden_y) * self.snap_anim
            self.move(self.snap_pos, int(new_y))

        elif self.snap_edge == "bottom":
            full_y = screen.height() - win_h
            hidden_y = screen.height() - self._peek_amount()
            new_y = hidden_y + (full_y - hidden_y) * self.snap_anim
            self.move(self.snap_pos, int(new_y))

    def _check_snap_hover(self):
        """检测鼠标是否悬停到吸附的猫上，悬停时弹出"""
        if self.snap_edge is None:
            return
        if self.dragging:
            return

        mouse = QCursor.pos()
        # 扩展检测区域，方便触发
        rect = self.geometry().adjusted(-15, -15, 15, 15)
        if rect.contains(mouse):
            self.snap_target = 1.0  # 弹出
            if self.snap_anim > 0.9 and random.random() < 0.005:
                self._say("喵~", 60)
        else:
            self.snap_target = 0.0  # 缩入

    # ======================== 绘制 ========================

    def paintEvent(self, event):
        try:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)

            sx = sy = 0
            if self.shake > 0:
                sx = random.uniform(-3, 3)
                sy = random.uniform(-3, 3)
            p.save()
            p.translate(sx, sy)
            # 尺寸缩放变换: 所有绘制仍用逻辑坐标 (W×H 画布)
            p.scale(self.cat_scale, self.cat_scale)

            # 贴边完全缩入后: 不画猫身, 只画"猫眼+耳朵"贴边特效
            edge_face = self.snap_edge is not None and self.snap_anim < 0.3
            if not edge_face:
                self._draw_shadow(p)
                self._draw_tail(p)
                self._draw_body(p)
                self._draw_head(p)

                for prt in self.particles:
                    prt.draw(p)

                if self.speech:
                    self._draw_speech(p)

            p.restore()

            if edge_face:
                # 眨巴的猫眼 + 微摆的耳朵 (像素坐标绘制)
                self._draw_edge_face(p)
            elif self.snap_edge and self.snap_anim < 0.9:
                # 缩入过程中: 贴边视觉指示器
                self._draw_snap_indicator(p)

            if p.isActive():
                p.end()
        except Exception as e:
            _log(f"!!! CatWindow.paintEvent 异常: {e}\n{traceback.format_exc()}")

    def _draw_shadow(self, p):
        """地面阴影"""
        p.setBrush(QBrush(QColor(0, 0, 0, 40)))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(CX, BODY_CY + BODY_RY + 25), 42, 7)

    def _draw_tail(self, p):
        """尾巴 - 摆动曲线"""
        wag = math.sin(self.tail_phase) * (8 if self.state != self.SLEEP else 2)
        wag2 = math.sin(self.tail_phase + 1.5) * (10 if self.state != self.SLEEP else 3)

        body_rx = self.style["body_rx"]
        tail_len = self.style["tail_len"]
        start_x = BODY_CX + body_rx - 5
        start_y = BODY_CY + 5
        path = QPainterPath()
        path.moveTo(start_x, start_y)
        path.cubicTo(
            start_x + 25, start_y + 5 + wag,
            start_x + 38, start_y - 30 + wag2,
            start_x + 28, start_y - tail_len + wag2
        )
        pen = QPen(QColor(self.c["body"]), self.style["tail_w"],
                   Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.drawPath(path)

        # 尾巴尖端深色圆
        p.setBrush(QBrush(QColor(self.c["dark"])))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(start_x + 28, start_y - tail_len + wag2), 6, 6)

    def _draw_body(self, p):
        """身体 + 肚子 + 前爪"""
        breath = 1.0 + math.sin(self.frame * 0.04) * 0.025
        by = BODY_CY - self.bounce
        body_rx = self.style["body_rx"]
        body_ry = self.style["body_ry"]

        # 身体
        grad = QRadialGradient(BODY_CX - 8, by - 8, body_rx * 2)
        grad.setColorAt(0, QColor(self.c["body"]))
        grad.setColorAt(1, QColor(self.c["dark"]))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(BODY_CX, by), body_rx * breath, body_ry * breath)

        # 肚子
        p.setBrush(QBrush(QColor(self.c["belly"])))
        p.drawEllipse(QPointF(BODY_CX, by + 5), body_rx * 0.6, body_ry * 0.65)

        breed = self.style.get("breed", "tabby")
        if breed == "tabby":
            # 田园猫背部虎斑
            stripe = QColor(self.c["dark"])
            stripe.setAlpha(150)
            p.setPen(QPen(stripe, 4, Qt.SolidLine, Qt.RoundCap))
            for dx in (-20, -10, 10, 20):
                p.drawLine(QPointF(BODY_CX + dx, by - body_ry + 8),
                           QPointF(BODY_CX + dx * 0.75, by - body_ry + 17))
        elif breed == "ragdoll":
            # 布偶猫蓬松的白色胸毛
            chest = QPainterPath()
            chest.moveTo(BODY_CX - 18, by - 12)
            chest.lineTo(BODY_CX - 10, by + 13)
            chest.lineTo(BODY_CX, by + 7)
            chest.lineTo(BODY_CX + 10, by + 13)
            chest.lineTo(BODY_CX + 18, by - 12)
            chest.closeSubpath()
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(self.c["belly"])))
            p.drawPath(chest)

        # 前爪
        paw_y = by + body_ry - 3
        p.setBrush(QBrush(QColor(self.c["body"])))
        p.drawEllipse(QPointF(BODY_CX - 16, paw_y), 10, 7)
        p.drawEllipse(QPointF(BODY_CX + 16, paw_y), 10, 7)
        if breed == "siamese":
            # 暹罗猫重点色脚爪
            p.setBrush(QBrush(QColor(self.c["dark"])))
            p.drawEllipse(QPointF(BODY_CX - 16, paw_y), 10, 7)
            p.drawEllipse(QPointF(BODY_CX + 16, paw_y), 10, 7)
        # 爪垫
        p.setBrush(QBrush(QColor(self.c["ear"])))
        p.drawEllipse(QPointF(BODY_CX - 16, paw_y + 1), 4, 3)
        p.drawEllipse(QPointF(BODY_CX + 16, paw_y + 1), 4, 3)

    def _draw_head(self, p):
        """头部 + 耳朵 + 五官"""
        hy = CY - self.bounce

        self._draw_ears(p, hy)

        # 头部
        head_rx = self.style["head_rx"]
        head_ry = self.style["head_ry"]
        if self.style.get("breed") == "ragdoll":
            # 长毛脸颊轮廓
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(self.c["body"])))
            for side in (-1, 1):
                tuft = QPainterPath()
                tuft.moveTo(CX + side * 38, hy + 12)
                tuft.lineTo(CX + side * 62, hy + 20)
                tuft.lineTo(CX + side * 48, hy + 30)
                tuft.lineTo(CX + side * 58, hy + 39)
                tuft.lineTo(CX + side * 31, hy + 42)
                tuft.closeSubpath()
                p.drawPath(tuft)
        grad = QRadialGradient(CX - 10, hy - 10, max(head_rx, head_ry) * 2)
        grad.setColorAt(0, QColor(self.c["body"]))
        grad.setColorAt(1, QColor(self.c["dark"]))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(CX, hy), head_rx, head_ry)

        self._draw_breed_face(p, hy)

        self._draw_eyes(p, hy)
        self._draw_face(p, hy)
        self._draw_whiskers(p, hy)

        # 腮红 (开心/玩耍时)
        if self.state in (self.HAPPY, self.PLAY):
            blush = QColor(255, 150, 160, 120)
            p.setBrush(QBrush(blush))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(CX - 28, hy + 8), 8, 5)
            p.drawEllipse(QPointF(CX + 28, hy + 8), 8, 5)

    def _draw_ears(self, p, hy):
        ear_x = self.style["ear_x"]
        ear_h = self.style["ear_h"]
        ear_type = self.style.get("ear_type", "upright")
        if ear_type == "folded":
            # 苏格兰折耳: 耳尖向前下方折叠, 不使用直立三角耳
            for side in (-1, 1):
                outer = QPainterPath()
                outer.moveTo(CX + side * 28, hy - 35)
                outer.lineTo(CX + side * ear_x, hy - ear_h)
                outer.lineTo(CX + side * 52, hy - 29)
                outer.lineTo(CX + side * 34, hy - 19)
                outer.closeSubpath()
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(QColor(self.c["body"])))
                p.drawPath(outer)
                fold = QPainterPath()
                fold.moveTo(CX + side * 34, hy - 35)
                fold.lineTo(CX + side * 46, hy - 51)
                fold.lineTo(CX + side * 45, hy - 29)
                fold.closeSubpath()
                p.setBrush(QBrush(QColor(self.c["ear"])))
                p.drawPath(fold)
            return
        # 左耳外
        path = QPainterPath()
        path.moveTo(CX - 40, hy - 30)
        path.lineTo(CX - ear_x, hy - ear_h)
        path.lineTo(CX - 14, hy - 42)
        path.closeSubpath()
        p.setBrush(QBrush(QColor(self.c["body"])))
        p.setPen(Qt.NoPen)
        p.drawPath(path)
        # 左耳内
        inner = QPainterPath()
        inner.moveTo(CX - 38, hy - 35)
        inner.lineTo(CX - ear_x + 4, hy - ear_h + 8)
        inner.lineTo(CX - 22, hy - 44)
        inner.closeSubpath()
        p.setBrush(QBrush(QColor(self.c["ear"])))
        p.drawPath(inner)

        # 右耳外
        path = QPainterPath()
        path.moveTo(CX + 40, hy - 30)
        path.lineTo(CX + ear_x, hy - ear_h)
        path.lineTo(CX + 14, hy - 42)
        path.closeSubpath()
        p.setBrush(QBrush(QColor(self.c["body"])))
        p.drawPath(path)
        # 右耳内
        inner = QPainterPath()
        inner.moveTo(CX + 38, hy - 35)
        inner.lineTo(CX + ear_x - 4, hy - ear_h + 8)
        inner.lineTo(CX + 22, hy - 44)
        inner.closeSubpath()
        p.setBrush(QBrush(QColor(self.c["ear"])))
        p.drawPath(inner)

    def _draw_breed_face(self, p, hy):
        """绘制能区分品种的脸部毛色、纹路和毛发特征。"""
        breed = self.style.get("breed", "tabby")
        dark = QColor(self.c["dark"])
        belly = QColor(self.c["belly"])
        p.setPen(Qt.NoPen)

        if breed == "tabby":
            # 额头 M 字和两侧虎斑
            dark.setAlpha(185)
            p.setPen(QPen(dark, 4, Qt.SolidLine, Qt.RoundCap))
            m = QPainterPath()
            m.moveTo(CX - 16, hy - 38)
            m.lineTo(CX - 8, hy - 25)
            m.lineTo(CX, hy - 36)
            m.lineTo(CX + 8, hy - 25)
            m.lineTo(CX + 16, hy - 38)
            p.drawPath(m)
            for side in (-1, 1):
                p.drawLine(QPointF(CX + side * 34, hy - 17),
                           QPointF(CX + side * 46, hy - 12))
                p.drawLine(QPointF(CX + side * 36, hy - 6),
                           QPointF(CX + side * 48, hy - 2))
        elif breed == "siamese":
            # 暹罗重点色面罩; 五官稍后绘制在其上
            dark.setAlpha(210)
            mask = QPainterPath()
            mask.moveTo(CX, hy - 35)
            mask.cubicTo(CX - 35, hy - 28, CX - 34, hy + 22, CX, hy + 34)
            mask.cubicTo(CX + 34, hy + 22, CX + 35, hy - 28, CX, hy - 35)
            mask.closeSubpath()
            p.setBrush(QBrush(dark))
            p.drawPath(mask)
            # 重点色耳罩
            p.setBrush(QBrush(QColor(self.c["dark"])))
            for side in (-1, 1):
                ear = QPainterPath()
                ear.moveTo(CX + side * 39, hy - 31)
                ear.lineTo(CX + side * self.style["ear_x"], hy - self.style["ear_h"])
                ear.lineTo(CX + side * 17, hy - 43)
                ear.closeSubpath()
                p.drawPath(ear)
        elif breed == "ragdoll":
            # 布偶猫标志性的白色倒 V 面纹和口鼻区
            blaze = QPainterPath()
            blaze.moveTo(CX, hy - 45)
            blaze.lineTo(CX - 25, hy + 13)
            blaze.quadTo(CX, hy + 5, CX + 25, hy + 13)
            blaze.closeSubpath()
            p.setBrush(QBrush(belly))
            p.drawPath(blaze)
            p.drawEllipse(QPointF(CX, hy + 20), 25, 19)
        elif breed == "fold":
            # 折耳常见的圆形腮帮与鼻梁浅纹
            belly.setAlpha(150)
            p.setBrush(QBrush(belly))
            p.drawEllipse(QPointF(CX - 27, hy + 16), 18, 16)
            p.drawEllipse(QPointF(CX + 27, hy + 16), 18, 16)
            dark.setAlpha(90)
            p.setPen(QPen(dark, 3, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(CX, hy - 37), QPointF(CX, hy - 25))

    def _draw_eyes(self, p, hy):
        """根据状态绘制不同眼睛"""
        eye_y = hy - 2
        lex = CX - self.style["eye_x"]
        rex = CX + self.style["eye_x"]

        if self.state == self.HAPPY:
            # ^ ^ 开心眯眼
            pen = QPen(QColor("#2C2C2C"), 2.5)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            for ex in (lex, rex):
                path = QPainterPath()
                path.moveTo(ex - 7, eye_y + 3)
                path.quadTo(ex, eye_y - 5, ex + 7, eye_y + 3)
                p.drawPath(path)

        elif self.state == self.SLEEP:
            # ︶ ︶ 闭眼
            pen = QPen(QColor("#2C2C2C"), 2.5)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            for ex in (lex, rex):
                path = QPainterPath()
                path.moveTo(ex - 7, eye_y - 3)
                path.quadTo(ex, eye_y + 5, ex + 7, eye_y - 3)
                p.drawPath(path)

        elif self.state == self.DRAG:
            # O O 惊讶大眼
            p.setBrush(QBrush(QColor("#2C2C2C")))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(lex, eye_y), 7, 9)
            p.drawEllipse(QPointF(rex, eye_y), 7, 9)
            p.setBrush(QBrush(QColor(255, 255, 255, 220)))
            p.drawEllipse(QPointF(lex - 2, eye_y - 3), 2, 3)
            p.drawEllipse(QPointF(rex - 2, eye_y - 3), 2, 3)

        elif self.state == self.PLAY:
            # 星星眼
            p.setBrush(QBrush(QColor("#2C2C2C")))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(lex, eye_y), 8, 10)
            p.drawEllipse(QPointF(rex, eye_y), 8, 10)
            p.setBrush(QBrush(QColor(255, 220, 80)))
            for ex in (lex, rex):
                sp = QPainterPath()
                s = 3.5
                for i in range(4):
                    a1 = math.radians(i * 90 - 90)
                    a2 = math.radians(i * 90 - 45)
                    x1, y1 = math.cos(a1) * s, math.sin(a1) * s
                    x2, y2 = math.cos(a2) * s * 0.4, math.sin(a2) * s * 0.4
                    if i == 0:
                        sp.moveTo(ex + x1, eye_y + y1)
                    else:
                        sp.lineTo(ex + x1, eye_y + y1)
                    sp.lineTo(ex + x2, eye_y + y2)
                sp.closeSubpath()
                p.drawPath(sp)

        else:
            # IDLE: 圆眼跟随鼠标 + 眨眼
            blinking = self.blink_left > 0
            if blinking:
                pen = QPen(QColor("#2C2C2C"), 2.5)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                for ex in (lex, rex):
                    path = QPainterPath()
                    path.moveTo(ex - 7, eye_y)
                    path.lineTo(ex + 7, eye_y)
                    p.drawPath(path)
            else:
                p.setBrush(QBrush(QColor("#2C2C2C")))
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(lex + self.eye_x, eye_y + self.eye_y), 7, 9)
                p.drawEllipse(QPointF(rex + self.eye_x, eye_y + self.eye_y), 7, 9)
                # 高光
                p.setBrush(QBrush(QColor(255, 255, 255, 230)))
                p.drawEllipse(QPointF(lex + self.eye_x - 2, eye_y + self.eye_y - 3), 2.5, 3.5)
                p.drawEllipse(QPointF(rex + self.eye_x - 2, eye_y + self.eye_y - 3), 2.5, 3.5)

    def _draw_face(self, p, hy):
        """鼻子和嘴巴"""
        nose_y = hy + 12

        # 鼻子
        p.setBrush(QBrush(QColor("#FF6B9D")))
        p.setPen(Qt.NoPen)
        nose = QPainterPath()
        nose.moveTo(CX - 4, nose_y)
        nose.lineTo(CX + 4, nose_y)
        nose.lineTo(CX, nose_y + 5)
        nose.closeSubpath()
        p.drawPath(nose)

        mouth_y = nose_y + 5
        pen = QPen(QColor("#5C3D2E"), 1.8)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        if self.state == self.HAPPY:
            # 大笑 + 舌头
            path = QPainterPath()
            path.moveTo(CX, mouth_y)
            path.quadTo(CX - 4, mouth_y + 8, CX - 10, mouth_y + 5)
            path.moveTo(CX, mouth_y)
            path.quadTo(CX + 4, mouth_y + 8, CX + 10, mouth_y + 5)
            p.drawPath(path)
            p.setBrush(QBrush(QColor("#FF9999")))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(CX, mouth_y + 6), 4, 3)

        elif self.state == self.SLEEP:
            # 小o嘴 (呼吸)
            breath = 1.0 + math.sin(self.frame * 0.04) * 0.3
            p.setBrush(QBrush(QColor("#5C3D2E")))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(CX, mouth_y + 3), 3 * breath, 4 * breath)

        elif self.state == self.PLAY:
            # 开心张嘴
            path = QPainterPath()
            path.moveTo(CX, mouth_y)
            path.quadTo(CX - 5, mouth_y + 10, CX - 12, mouth_y + 6)
            path.moveTo(CX, mouth_y)
            path.quadTo(CX + 5, mouth_y + 10, CX + 12, mouth_y + 6)
            p.drawPath(path)

        elif self.state == self.DRAG:
            # O嘴
            p.setBrush(QBrush(QColor("#5C3D2E")))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(CX, mouth_y + 4), 4, 5)

        else:
            # 正常猫嘴 :3
            path = QPainterPath()
            path.moveTo(CX, mouth_y)
            path.quadTo(CX - 3, mouth_y + 5, CX - 7, mouth_y + 3)
            path.moveTo(CX, mouth_y)
            path.quadTo(CX + 3, mouth_y + 5, CX + 7, mouth_y + 3)
            p.drawPath(path)

    def _draw_whiskers(self, p, hy):
        """胡须"""
        pen = QPen(QColor(255, 255, 255, 180), 1.2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        wy = hy + 14
        for i, (dy, length) in enumerate([(0, 28), (5, 30), (10, 26)]):
            # 左
            path = QPainterPath()
            path.moveTo(CX - 28, wy + dy)
            path.lineTo(CX - 28 - length, wy + dy - 3 + i * 2)
            p.drawPath(path)
            # 右
            path = QPainterPath()
            path.moveTo(CX + 28, wy + dy)
            path.lineTo(CX + 28 + length, wy + dy - 3 + i * 2)
            p.drawPath(path)

    def _draw_speech(self, p):
        """对话气泡"""
        font = QFont("Microsoft YaHei", 9, QFont.Medium)
        p.setFont(font)
        fm = p.fontMetrics()
        text_w = fm.horizontalAdvance(self.speech)
        text_h = fm.height()

        bw = text_w + 24
        bh = text_h + 12
        bx = CX - bw / 2
        by = CY - HEAD_R - bh - 25

        bx = max(5, min(W - bw - 5, bx))
        by = max(5, by)

        # 气泡背景
        p.setBrush(QBrush(QColor(255, 255, 255, 235)))
        p.setPen(QPen(QColor(200, 200, 200, 150), 1))
        p.drawRoundedRect(QRectF(bx, by, bw, bh), 10, 10)

        # 气泡尾巴
        tail_x = max(bx + 10, min(bx + bw - 10, CX))
        tail_path = QPainterPath()
        tail_path.moveTo(tail_x - 6, by + bh)
        tail_path.lineTo(tail_x + 6, by + bh)
        tail_path.lineTo(tail_x, by + bh + 8)
        tail_path.closeSubpath()
        p.setBrush(QBrush(QColor(255, 255, 255, 235)))
        p.drawPath(tail_path)

        # 文字
        p.setPen(QPen(QColor(80, 80, 80)))
        p.drawText(QRectF(bx, by, bw, bh), Qt.AlignCenter, self.speech)

    def _draw_edge_face(self, p):
        """按屏幕边缘方向绘制与当前品种一致的半身探头猫。"""
        t = time.time()
        win_w, win_h = self.width(), self.height()

        fade = (0.3 - self.snap_anim) / 0.3
        alpha = int(max(0.0, min(1.0, fade)) * 255)
        ph = t % 3.6
        blink = 0.0
        if ph < 0.18:
            blink = 1.0 - abs(ph - 0.09) / 0.09

        p.save()
        if self.snap_edge == "bottom":
            # 从屏幕底部向上探头: 正立、双眼水平
            p.translate(win_w / 2, 0)
        elif self.snap_edge == "top":
            # 从屏幕上方倒挂探头: 眼睛在上、耳朵在下
            p.translate(win_w / 2, win_h)
            p.scale(1, -1)
        elif self.snap_edge == "left":
            # 从左侧横着探头
            p.translate(win_w, win_h / 2)
            p.rotate(90)
        elif self.snap_edge == "right":
            # 从右侧横着探头
            p.translate(0, win_h / 2)
            p.rotate(-90)
        self._draw_edge_cat(p, alpha, blink, t)
        p.restore()

    def _draw_edge_cat(self, p, alpha, blink, t):
        """以下边缘正立探头为标准坐标, 由 _draw_edge_face 做方向变换。"""
        # 贴边形象采用抽象缩略图, 不再绘制完整脸部
        p.scale(0.62, 0.62)
        def color(value, a=alpha):
            c = QColor(value)
            c.setAlpha(a)
            return c

        body = color(self.c["body"])
        dark = color(self.c["dark"])
        ear = color(self.c["ear"])
        belly = color(self.c["belly"])
        ink = QColor(42, 42, 46, alpha)
        eye_white = QColor(255, 252, 245, alpha)
        breed = self.style.get("breed", "tabby")

        # 布偶猫的蓬松脸颊先画在头部后方
        if breed == "ragdoll":
            p.setPen(Qt.NoPen)
            p.setBrush(body)
            for side in (-1, 1):
                tuft = QPainterPath()
                tuft.moveTo(side * 31, 49)
                tuft.lineTo(side * 52, 57)
                tuft.lineTo(side * 40, 67)
                tuft.lineTo(side * 50, 77)
                tuft.lineTo(side * 27, 80)
                tuft.closeSubpath()
                p.drawPath(tuft)

        # 耳朵: 折耳使用向下弯折的短耳, 其他品种使用不同高度的立耳
        for side, phase in ((-1, 0.0), (1, 2.4)):
            p.save()
            p.translate(side * 25, 30)
            p.rotate(math.sin(t * 2.3 + phase) * 5)
            ep = QPainterPath()
            if self.style.get("ear_type") == "folded":
                ep.moveTo(-side * 15, 2)
                ep.lineTo(side * 5, -13)
                ep.lineTo(side * 17, 4)
                ep.lineTo(side * 7, 13)
            else:
                eh = 30 if self.style.get("ear_type") == "large" else 25
                ep.moveTo(-10, 5)
                ep.lineTo(0, -eh)
                ep.lineTo(10, 5)
            ep.closeSubpath()
            p.setPen(Qt.NoPen)
            p.setBrush(dark if breed == "siamese" else body)
            p.drawPath(ep)
            inner = QPainterPath()
            inner.moveTo(-5, 3); inner.lineTo(0, -14); inner.lineTo(5, 3)
            inner.closeSubpath()
            p.setBrush(ear)
            p.drawPath(inner)
            p.restore()

        # 半颗圆头超出可见边缘, 自然被窗口裁剪
        p.setPen(Qt.NoPen)
        p.setBrush(body)
        p.drawEllipse(QPointF(0, 63), 46, 43)

        # 品种特征简化到贴边小头上
        if breed == "siamese":
            mask = QColor(dark); mask.setAlpha(int(alpha * 0.9))
            p.setBrush(mask)
            p.drawEllipse(QPointF(0, 57), 31, 27)
        elif breed == "ragdoll":
            blaze = QPainterPath()
            blaze.moveTo(0, 25); blaze.lineTo(-20, 65)
            blaze.quadTo(0, 55, 20, 65); blaze.closeSubpath()
            p.setBrush(belly); p.drawPath(blaze)
        elif breed == "tabby":
            p.setPen(QPen(dark, 3, Qt.SolidLine, Qt.RoundCap))
            m = QPainterPath()
            m.moveTo(-12, 32); m.lineTo(-6, 42); m.lineTo(0, 34)
            m.lineTo(6, 42); m.lineTo(12, 32)
            p.drawPath(m)
        elif breed == "fold":
            soft = QColor(belly); soft.setAlpha(int(alpha * 0.55))
            p.setPen(Qt.NoPen); p.setBrush(soft)
            p.drawEllipse(QPointF(-24, 68), 14, 12)
            p.drawEllipse(QPointF(24, 68), 14, 12)

        # 双眼始终保持在同一水平线
        for ex in (-14, 14):
            if blink > 0.75:
                p.setPen(QPen(ink, 2.2)); p.setBrush(Qt.NoBrush)
                eye = QPainterPath()
                eye.moveTo(ex - 7, 52); eye.quadTo(ex, 56, ex + 7, 52)
                p.drawPath(eye)
            else:
                ry = max(1.5, 9 * (1.0 - 0.92 * blink))
                p.setPen(Qt.NoPen); p.setBrush(eye_white)
                p.drawEllipse(QPointF(ex, 52), 8, ry)
                p.setBrush(ink)
                p.drawEllipse(QPointF(ex, 52), 2.7, max(1.0, ry * 0.72))
                p.setBrush(QColor(255, 255, 255, alpha))
                p.drawEllipse(QPointF(ex - 2, 49), 1.5, 2)

        # 两只小圆爪作为“搭边”的最小提示
        for px in (-27, 27):
            p.setPen(Qt.NoPen); p.setBrush(body)
            p.drawEllipse(QPointF(px, 88), 10, 8)
            p.setBrush(ear)
            p.drawEllipse(QPointF(px, 89), 3, 2)

    def _draw_snap_indicator(self, p):
        """贴边隐藏时在可见边缘绘制猫色提示条"""
        alpha = int((1.0 - self.snap_anim) * 220)
        if alpha <= 0:
            return

        # 用实际窗口像素尺寸 (逻辑 W/H × cat_scale), 否则缩放后画到窗口外
        win_w, win_h = self.width(), self.height()

        color = QColor(self.c["body"])
        color.setAlpha(alpha)
        gradient_color = QColor(self.c["dark"])
        gradient_color.setAlpha(0)

        if self.snap_edge == "left":
            # 右侧可见，在右边缘画提示条
            bar_x = win_w - 8
            grad = QRadialGradient(bar_x, win_h // 2, 40)
            grad.setColorAt(0, color)
            grad.setColorAt(1, gradient_color)
            p.setBrush(QBrush(grad))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(bar_x - 5, win_h // 2 - 35, 10, 70), 5, 5)

        elif self.snap_edge == "right":
            # 左侧可见，在左边缘画提示条
            grad = QRadialGradient(8, win_h // 2, 40)
            grad.setColorAt(0, color)
            grad.setColorAt(1, gradient_color)
            p.setBrush(QBrush(grad))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(-5, win_h // 2 - 35, 10, 70), 5, 5)

        elif self.snap_edge == "top":
            # 下边缘可见
            bar_y = win_h - 8
            grad = QRadialGradient(win_w // 2, bar_y, 40)
            grad.setColorAt(0, color)
            grad.setColorAt(1, gradient_color)
            p.setBrush(QBrush(grad))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(win_w // 2 - 35, bar_y - 5, 70, 10), 5, 5)

        elif self.snap_edge == "bottom":
            # 上边缘可见
            grad = QRadialGradient(win_w // 2, 8, 40)
            grad.setColorAt(0, color)
            grad.setColorAt(1, gradient_color)
            p.setBrush(QBrush(grad))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(win_w // 2 - 35, -5, 70, 10), 5, 5)

    # ======================== 鼠标交互 ========================

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_start = QPoint(event.globalPos())
            self.drag_offset = QPoint(event.pos())
            self.drag_distance = 0.0
            # 启动长按计时器: 500ms 内未拖动未释放 → 长按显示摄像头
            if not self.longpress_active:
                self.press_timer.start(500)
            # 如果处于吸附状态，拖拽时先弹出再拖动
            if self.snap_edge:
                self.snap_target = 1.0
                self.snap_anim = 1.0
                self.snap_edge = None
            if self.state != self.SLEEP:
                self._set_state(self.DRAG, 0)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.press_timer.stop()

            # 长按预览状态 → 松开隐藏预览, 不触发点击逻辑
            if self.longpress_active:
                self._hide_preview()
                self.dragging = False
                if self.state == self.DRAG:
                    self._set_state(self.IDLE, 0)
                return

            was_dragging = self.dragging
            self.dragging = False
            if self.state == self.DRAG:
                self._set_state(self.IDLE, 0)
            # 短距离释放 = 点击
            if was_dragging and self.drag_distance < 8:
                # 判断点击位置：头部附近 → 聊天框，身体 → 摸猫
                # 屏幕坐标 → 逻辑画布坐标 (除以缩放倍率)
                click_x = event.pos().x() / self.cat_scale
                click_y = event.pos().y() / self.cat_scale
                dx = click_x - CX
                dy = click_y - (CY - self.bounce)
                dist = math.sqrt(dx * dx + dy * dy)
                _log(f"点击检测: pos=({click_x},{click_y}) dist_to_head={dist:.1f} head_r*1.15={HEAD_R * 1.15}")
                if dist < HEAD_R * 1.15:
                    _log("→ 判定为猫头点击, 调用 _toggle_chat")
                    self._toggle_chat()
                else:
                    _log("→ 判定为身体点击, 调用 _pet")
                    self._pet()
            elif was_dragging and self.drag_distance >= 8:
                # 拖拽释放后检查贴边吸附
                self._check_snap()

    def mouseMoveEvent(self, event):
        if self.dragging:
            dx = event.globalPos().x() - self.drag_start.x()
            dy = event.globalPos().y() - self.drag_start.y()
            self.drag_distance = math.sqrt(dx * dx + dy * dy)
            # 拖动超过阈值 → 取消长按判定 (是拖拽不是长按)
            if self.drag_distance >= 8 and not self.longpress_active:
                self.press_timer.stop()
            if not self.longpress_active:
                new_pos = QPoint(event.globalPos() - self.drag_offset)
                self.move(new_pos)
                self.shake = 3
                # 预览显示中则跟随小猫移动
                if self.preview.isVisible():
                    self._position_preview()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_sleep()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: white;
                border: 1px solid #ccc;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 30px 6px 20px;
                border-radius: 4px;
                font-size: 13px;
            }
            QMenu::item:selected {
                background: #FFE0B0;
            }
            QMenu::separator {
                height: 1px;
                background: #e0e0e0;
                margin: 4px 8px;
            }
        """)

        state_names = {
            "idle": "闲逛中", "happy": "开心",
            "sleep": "睡觉中", "play": "玩耍中", "drag": "被抓住"
        }
        header = menu.addAction(
            self.style["name"] + " · " + self.c["name"] +
            " (" + state_names.get(self.state, "") + ")")
        header.setEnabled(False)
        menu.addSeparator()
        interact = menu.addMenu("与小猫互动")
        interact.addAction("摸摸猫", self._pet)
        interact.addAction("玩耍", lambda: self._set_state(self.PLAY, 180))
        interact.addAction("睡觉/起床", self._toggle_sleep)
        follow_text = "取消跟随" if self.follow else "跟随鼠标"
        interact.addAction(follow_text, self._toggle_follow)
        monitor_text = "暂停监控" if self._monitoring_requested else "启用监控"
        menu.addAction(monitor_text, self._toggle_monitoring)
        cam_text = "隐藏摄像头预览" if self.preview.isVisible() else "摄像头预览 (或长按小猫)"
        menu.addAction(cam_text, self._toggle_preview)
        menu.addAction("切换到目标程序", lambda: self._do_switch_target("切!"))
        menu.addAction("小猫与检测设置...", self._open_settings)
        menu.addSeparator()
        # 开机启动 (带勾选状态, 点击切换)
        autostart_act = menu.addAction("开机启动")
        autostart_act.setCheckable(True)
        autostart_act.setChecked(self._autostart_on)
        autostart_act.triggered.connect(self._toggle_autostart)
        menu.addSeparator()
        menu.addAction("退出", self._quit)
        menu.exec_(event.globalPos())

    def _toggle_preview(self):
        """手动切换摄像头预览显示状态"""
        if self.preview.isVisible():
            self.preview.hide()
            self.longpress_active = False
        else:
            self.longpress_active = False
            self._show_preview()

    # ======================== 窗口事件 ========================

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "桌面小猫",
            "小猫藏在系统托盘里啦~ 双击图标重新显示",
            QSystemTrayIcon.Information, 2000
        )
