"""Window corner attachment, independent from the pet animation and screen snap."""
import time

from PyQt5.QtCore import QObject, QPoint, QRect, Qt, QTimer
from PyQt5.QtGui import QColor, QCursor, QPainter, QPen
from PyQt5.QtWidgets import QApplication, QWidget

from ..platform.attachment import (ANCHOR_NAMES, NativeWindows, anchor_placements,
                                   attachment_position, default_placement)
from ..platform.explorer import ExplorerReader
from ..platform.folder_lock import ExplorerFolderLock


CORNERS = {key: ANCHOR_NAMES[key] for key in
           ('top-left', 'top-right', 'bottom-left', 'bottom-right')}
ANCHORS = tuple(ANCHOR_NAMES)


def placement_label(anchor, placement):
    x, y = placement
    horizontal = ('左侧', '压边', '右侧')[x + 1]
    vertical = ('上侧', '压边', '下侧')[y + 1]
    if anchor in ('top', 'bottom'):
        inside = y > 0 if anchor == 'top' else y < 0
        return '软件内' if inside else ('压住边缘' if y == 0 else '软件外')
    if anchor in ('left', 'right'):
        inside = x > 0 if anchor == 'left' else x < 0
        return '软件内' if inside else ('压住边缘' if x == 0 else '软件外')
    x_inside = x > 0 if anchor.endswith('left') else x < 0
    y_inside = y > 0 if anchor.startswith('top') else y < 0
    x_text = '水平向内' if x_inside else ('水平压角' if x == 0 else '水平向外')
    y_text = '垂直向内' if y_inside else ('垂直压角' if y == 0 else '垂直向外')
    return x_text + ' / ' + y_text


def secondary_selection_zone(target_rect, pet_size, anchor, tolerance=35, edge_ratio=None):
    """Union of an anchor's landing rectangles; edge strips span their axis."""
    zone = QRect()
    for placement in anchor_placements(anchor):
        rect = QRect(attachment_position(target_rect, pet_size, anchor, placement,
                                         edge_ratio=edge_ratio), pet_size)
        zone = rect if zone.isNull() else zone.united(rect)
    if '-' not in anchor:
        if anchor in ('left', 'right'):
            zone.setTop(target_rect.top())
            zone.setBottom(target_rect.bottom())
        else:
            zone.setLeft(target_rect.left())
            zone.setRight(target_rect.right())
    return zone.adjusted(-tolerance, -tolerance, tolerance, tolerance)


class AttachmentPreview(QWidget):
    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.target = None
        self.target_rect = QRect()
        self.markers = {}
        self.anchor = self.placement = None
        self.origin = QPoint()

    def display(self, target, size, anchor, placement, edge_ratio=None):
        self.target, self.anchor, self.placement = target, anchor, placement
        margin_x, margin_y = size.width() + 60, size.height() + 60
        bounds = target.rect.adjusted(-margin_x, -margin_y, margin_x, margin_y)
        self.origin = bounds.topLeft()
        if self.geometry() != bounds:
            self.setGeometry(bounds)
        self.target_rect = target.rect.translated(-self.origin)
        self.markers = {}
        if anchor:
            self.markers = {cell: QRect(attachment_position(
                                target.rect, size, anchor, cell, edge_ratio=edge_ratio), size)
                            .translated(-self.origin)
                            for cell in anchor_placements(anchor)}
        if not self.isVisible():
            self.show()
        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor('#54b9ff'), 2))
        painter.drawRoundedRect(self.target_rect.adjusted(1, 1, -2, -2), 6, 6)
        for cell, rect in self.markers.items():
            chosen = cell == self.placement
            painter.setPen(QPen(QColor('#35c5ff' if chosen else '#79cfff'),
                                3 if chosen else 1,
                                Qt.SolidLine if chosen else Qt.DashLine))
            painter.setBrush(QColor(65, 175, 255, 90 if chosen else 18))
            painter.drawRoundedRect(rect.adjusted(2, 2, -3, -3), 7, 7)
        # Keep the title below the top grids so it cannot dim/select-cover them.
        title_rect = QRect(self.target_rect.left() + 10, self.target_rect.top() + 55,
                           max(0, self.target_rect.width() - 20), 48)
        painter.fillRect(title_rect, QColor(20, 35, 55, 220))
        painter.setPen(Qt.white)
        hint = ('吸附到：' + self.target.title[:55] + '  ·  Esc 取消')
        if self.anchor and self.placement is not None:
            hint += '\n' + ANCHOR_NAMES[self.anchor] + ' · ' + placement_label(self.anchor, self.placement)
        elif self.anchor:
            hint += '\n' + ANCHOR_NAMES[self.anchor] + ' · 将宠物移入一个矩形'
        painter.drawText(title_rect.adjusted(6, 3, -6, -3), Qt.AlignLeft | Qt.AlignVCenter, hint)


class WindowAttachment(QObject):
    def __init__(self, pet, backend=None):
        super().__init__(pet)
        self.pet = pet
        self.backend = backend or NativeWindows()
        self.preview = AttachmentPreview()
        self.target = None
        self.corner = 'bottom-right'
        self.placement = default_placement(self.corner)
        self.edge_ratio = None
        self.candidate = None
        self.candidate_corner = None
        self.candidate_placement = None
        self.candidate_edge_ratio = None
        self.dragging = False
        self.cancelled = False
        self.manual_hidden = False
        self.auto_hidden = False
        self.enabled = True
        self.generation = 0
        self.folder_name = self.folder_path = ''
        self.folder_at = 0.0
        self.next_folder = 0.0
        self.next_scan = 0.0
        self.reader = ExplorerReader(self)
        self.reader.ready.connect(self._folder_ready)
        self.folder_lock = ExplorerFolderLock(self)
        self.folder_lock.changed.connect(self._lock_changed)
        self.lock_state = self.lock_path = self.lock_error = ''
        self._tab_away = False
        self._tab_hidden = False
        self._tab_happy_until = 0.0
        self._focus_away = False
        self._focus_hidden = False
        self._focus_happy_until = 0.0
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)
        pet.setAttribute(Qt.WA_ShowWithoutActivating)

    def begin_drag(self):
        self.dragging, self.cancelled = True, False
        self.start_pos = QPoint(self.pet.pos())
        self.next_scan = 0.0
        self.pet.follow = False

    def update_drag(self, force=False):
        if self.cancelled or not self.enabled:
            return
        now = time.monotonic()
        if not force and now < self.next_scan:
            return
        self.next_scan = now + .10
        cursor = QCursor.pos()
        # First eligible window under the pointer wins; never select a window
        # behind it just because that hidden window has a closer corner.
        targets = self.backend.all()
        candidate = None
        # Once a corner/edge opened its second-level grid, that window owns the
        # whole grid (including cells outside its frame). Do this BEFORE hit
        # testing the window below the cursor, otherwise an outside cell can be
        # mistaken for a request to attach to a neighbouring/background app.
        if self.candidate and self.candidate_corner:
            previous = next((t for t in targets if t.hwnd == self.candidate.hwnd), None)
            if previous and secondary_selection_zone(
                    previous.rect, self.pet.size(), self.candidate_corner,
                    edge_ratio=self.candidate_edge_ratio).contains(cursor):
                candidate = previous
        if candidate is None:
            candidate = next((t for t in targets if t.rect.contains(cursor)), None)
        if candidate is None and self.candidate and not self.candidate_corner:
            candidate = next((t for t in targets if t.hwnd == self.candidate.hwnd and
                              t.rect.adjusted(-self.pet.width(), -self.pet.height(),
                                              self.pet.width(), self.pet.height()).contains(cursor)), None)
        if candidate is None:
            candidate = next((t for t in targets if t.rect.adjusted(-40, -40, 40, 40).contains(cursor)), None)
        self.candidate = candidate
        corner = placement = None
        edge_ratio = None
        if candidate:
            edge_ratios = {}
            for edge in ('top', 'left', 'right', 'bottom'):
                if edge in ('left', 'right'):
                    travel = max(1, candidate.rect.height() - self.pet.height())
                    ratio = (self.pet.y() - candidate.rect.top()) / travel
                else:
                    travel = max(1, candidate.rect.width() - self.pet.width())
                    ratio = (self.pet.x() - candidate.rect.left()) / travel
                edge_ratios[edge] = max(0.0, min(1.0, ratio))

            choices = {(key, cell): (attachment_position(
                           candidate.rect, self.pet.size(), key, cell,
                           edge_ratio=edge_ratios.get(key)) - self.pet.pos()).manhattanLength()
                       for key in ANCHORS for cell in anchor_placements(key)}
            if choices:
                # At an edge endpoint, corner and sliding-edge coordinates can
                # coincide. Prefer the corner so entering an endpoint reliably
                # opens its 2 x 2 selector as requested.
                nearest = min(choices, key=lambda choice: (
                    choices[choice], '-' not in choice[0]))
                proximity = max(45, int(min(self.pet.width(), self.pet.height()) * .35))
                select_limit = proximity
                if choices[nearest] <= proximity:
                    corner = nearest[0]
                    edge_ratio = edge_ratios.get(corner)
                    if choices[nearest] <= select_limit:
                        placement = nearest[1]
            self.preview.display(candidate, self.pet.size(), corner, placement, edge_ratio)
        else:
            self.preview.hide()
        self.candidate_corner = corner
        self.candidate_placement = placement
        self.candidate_edge_ratio = edge_ratio

    def end_drag(self, distance):
        """Return True when application attachment consumed this release."""
        if self.cancelled:
            self.dragging = False
            self.cancelled = False
            return True
        if distance >= 8:
            self.update_drag(force=True)
        self.dragging = False
        self.preview.hide()
        if self.target and distance < 40:
            self.tick()
            return True
        if distance >= 8 and self.candidate and self.candidate_corner and self.candidate_placement:
            return self.attach(self.candidate, self.candidate_corner,
                               self.candidate_placement, self.candidate_edge_ratio)
        if self.target and distance >= 40:
            self.detach(reveal=False)
        self.candidate = None
        self.candidate_corner = None
        self.candidate_placement = None
        self.candidate_edge_ratio = None
        return False

    def cancel_drag(self):
        self.cancelled = True
        self.preview.hide()
        self.pet.move(self.start_pos)
        self.pet.press_timer.stop()
        if getattr(self.pet, 'longpress_active', False):
            self.pet._hide_preview()
        self.pet.dragging = False
        self.dragging = False
        self.candidate = None
        self.candidate_corner = None
        self.candidate_placement = None
        self.candidate_edge_ratio = None
        if self.pet.state == self.pet.DRAG:
            self.pet._set_state(self.pet.IDLE, 0)
        self.tick()

    def attach(self, target, corner, placement=None, edge_ratio=None):
        current = self.backend.get(target.hwnd)
        if not current or current.pid != target.pid or not current.visible:
            return False
        if not self.target or (current.hwnd, current.pid) != (self.target.hwnd, self.target.pid):
            self.unlock_folder(notify=False)
            self._reset_focus_behavior()
        self.generation += 1
        self.target, self.corner = current, corner
        self.placement = placement or default_placement(corner)
        self.edge_ratio = edge_ratio if '-' not in corner else None
        self.manual_hidden = False
        self.pet.follow = False
        self.pet.snap_edge = None
        self.pet.snap_anim = self.pet.snap_target = 1.0
        self.folder_name = self.folder_path = ''
        self.pet.setToolTip(current.title + '\n' + ANCHOR_NAMES[corner] + ' · ' +
                            placement_label(corner, self.placement))
        self.next_folder = 0.0
        self.tick()
        return True

    def detach(self, reveal=True):
        self.unlock_folder(notify=False)
        self._reset_focus_behavior()
        self.generation += 1
        self.target = None
        self.folder_name = self.folder_path = ''
        self.pet.setToolTip('')
        self.preview.hide()
        if reveal or (self.auto_hidden and not self.manual_hidden):
            screen = QApplication.screenAt(self.pet.pos()) or QApplication.primaryScreen()
            area = screen.availableGeometry()
            self.pet.move(max(area.left(), min(self.pet.x(), area.right() - self.pet.width() + 1)),
                          max(area.top(), min(self.pet.y(), area.bottom() - self.pet.height() + 1)))
            self.pet.show()
        self.auto_hidden = False
        if reveal:
            self.manual_hidden = False

    def tick(self):
        if self.dragging:
            if self.backend.escape_pressed():
                self.cancel_drag()
            return
        if not self.target:
            return
        current = self.backend.get(self.target.hwnd)
        if not current or current.pid != self.target.pid or current.kind != self.target.kind:
            self.detach(reveal=False)
            return
        self.target = current
        self._sync_tab_behavior()
        self._sync_focus_behavior(self.backend.active(current))
        visible = (current.visible and not self._focus_hidden
                   and not self.manual_hidden and not self._tab_hidden)
        if not visible:
            if self.pet.isVisible():
                self.pet.hide()
                if hasattr(self.pet, 'preview'):
                    self.pet.preview.hide()
                self.auto_hidden = not self.manual_hidden
            return
        self.pet.move(attachment_position(current.rect, self.pet.size(),
                                          self.corner, self.placement,
                                          edge_ratio=self.edge_ratio))
        if self.auto_hidden:
            self.pet.show()  # WA_ShowWithoutActivating: don't steal target focus.
            self.auto_hidden = False
        now = time.monotonic()
        if current.kind in ('CabinetWClass', 'ExploreWClass') and now >= self.next_folder:
            self.next_folder = now + 1.0
            self.reader.request(current.hwnd, self.generation, self.backend.api.IsWindowVisible)

    def _folder_ready(self, hwnd, generation, name, path):
        if self.target and self.target.hwnd == hwnd and self.generation == generation:
            self.folder_name, self.folder_path = name, path
            self.folder_at = time.monotonic()
            self.pet.setToolTip(self.target.title + '\n' + (path or name))

    def add_menu(self, parent):
        menu = parent.addMenu('软件窗口吸附')
        menu.aboutToShow.connect(lambda: self.populate_menu(menu))
        self.populate_menu(menu)

    def populate_menu(self, menu):
        menu.clear()
        enabled = menu.addAction('拖动时显示吸附提示')
        enabled.setCheckable(True)
        enabled.setChecked(self.enabled)
        enabled.toggled.connect(self._set_enabled)
        if not self.target:
            menu.addAction('拖动宠物至软件窗口四角，松开吸附').setEnabled(False)
            return
        menu.addAction(('已吸附：' + self.target.title).replace('&', '&&')).setEnabled(False)
        menu.addAction('脱离软件窗口', lambda: self.detach())
        positions = menu.addMenu('吸附位置')
        for key, label in ANCHOR_NAMES.items():
            anchor_menu = positions.addMenu(label + (' ✓' if key == self.corner else ''))
            for placement in anchor_placements(key):
                selected = key == self.corner and placement == self.placement
                action = anchor_menu.addAction(placement_label(key, placement) + (' ✓' if selected else ''))
                action.triggered.connect(
                    lambda checked=False, key=key, placement=placement:
                    self.attach(self.target, key, placement))
        if self.target.kind in ('CabinetWClass', 'ExploreWClass'):
            menu.addSeparator()
            fresh = time.monotonic() - self.folder_at < 3.0
            label = (self.folder_path or self.folder_name) if fresh else '正在读取当前目录…'
            menu.addAction(label.replace('&', '&&')).setEnabled(False)
            copy = menu.addAction('复制当前目录路径', self.copy_folder)
            copy.setEnabled(bool(fresh and self.folder_path))
            menu.addSeparator()
            if self.lock_state:
                states = {'pending': '正在确认标签页…', 'locked': '目录已锁定',
                          'paused': '其他标签页使用中，锁定检查暂停',
                          'restoring': '正在退回锁定目录'}
                menu.addAction(states.get(self.lock_state, self.lock_state)).setEnabled(False)
                if self.lock_path:
                    item = menu.addAction(('锁定目录：' + self.lock_path).replace('&', '&&'))
                    item.setEnabled(False)
                menu.addAction('解除目录锁定', lambda: self.unlock_folder())
            else:
                lock = menu.addAction('锁定当前标签页目录（导航后退回）', self.lock_folder)
                lock.setEnabled(bool(fresh and self.folder_path))
                if self.lock_error:
                    menu.addAction(self.lock_error.replace('&', '&&')).setEnabled(False)

    def lock_folder(self):
        if not self.target or self.target.kind not in ('CabinetWClass', 'ExploreWClass'):
            return
        self.lock_state, self.lock_path, self.lock_error = 'pending', '', ''
        # Capture a fresh active tab/path on its own COM worker, not the cached
        # folder text which might belong to a previously selected tab.
        self.folder_lock.start(self.target.hwnd, self.backend.api.IsWindowVisible)

    def unlock_folder(self, notify=True):
        was_locked = bool(self.lock_state)
        self.folder_lock.stop()
        self.lock_state = self.lock_path = self.lock_error = ''
        self._tab_away = self._tab_hidden = False
        self._tab_happy_until = 0.0
        self.pet._tab_mood = ''
        if notify and was_locked:
            self.pet._say('目录锁定已解除~', 100)

    def _lock_changed(self, token, state, detail):
        if token != self.folder_lock.token or not self.target:
            return
        if state == 'error':
            self.unlock_folder(notify=False)
            self.lock_error = detail
            self.pet._say(detail, 180)
            return
        was_pending = self.lock_state == 'pending'
        self.lock_state, self.lock_path = state, detail
        if was_pending and state == 'locked':
            self.pet._say('当前标签页目录已锁定~', 140)

    def _sync_tab_behavior(self):
        mode = getattr(self.pet, 'config', {}).get('locked_tab_behavior', 'emotion')
        away = self.lock_state == 'paused'
        now = time.monotonic()
        if mode == 'emotion' and self._tab_away and self.lock_state in ('locked', 'restoring'):
            self._tab_happy_until = now + 2.5
        if mode != 'emotion' or not self.lock_state:
            self._tab_happy_until = 0.0
        self.pet._tab_mood = ('angry' if away else
                              'happy' if now < self._tab_happy_until else '') if mode == 'emotion' else ''
        self._tab_hidden = mode == 'hide' and away
        self._tab_away = away

    def _reset_focus_behavior(self):
        self._focus_away = self._focus_hidden = False
        self._focus_happy_until = 0.0
        self.pet._tab_mood = ''

    def _sync_focus_behavior(self, active):
        mode = getattr(self.pet, 'config', {}).get('attached_focus_behavior', 'hide')
        if mode not in ('hide', 'emotion', 'none'):
            mode = 'hide'
        now = time.monotonic()
        if mode == 'emotion' and self._focus_away and active:
            self._focus_happy_until = now + 2.5
        if mode != 'emotion':
            self._focus_happy_until = 0.0
        focus_mood = ('angry' if not active else
                      'happy' if now < self._focus_happy_until else '') if mode == 'emotion' else ''
        tab_mood = getattr(self.pet, '_tab_mood', '')
        # The two independent rules compose: hide wins over display, and an
        # outstanding angry condition wins over either return's happy cue.
        if 'angry' in (focus_mood, tab_mood):
            self.pet._tab_mood = 'angry'
        else:
            self.pet._tab_mood = tab_mood or focus_mood
        self._focus_hidden = mode == 'hide' and not active
        self._focus_away = not active

    def copy_folder(self):
        # Refresh instead of copying an old path after a navigation/tab change.
        if not self.target:
            return
        if self.reader.busy:
            self.pet._say('目录正在读取，请稍后重试~', 100)
            return
        hwnd, generation = self.target.hwnd, self.generation
        def copy_when_ready(got_hwnd, got_generation, name, path):
            self.reader.ready.disconnect(copy_when_ready)
            if (self.target and self.target.hwnd == got_hwnd == hwnd
                    and self.generation == got_generation == generation):
                if path:
                    QApplication.clipboard().setText(path)
                    self.pet._say('目录路径已复制~', 100)
                else:
                    self.pet._say(name or '当前目录暂不可用', 120)
        self.reader.ready.connect(copy_when_ready)
        self.reader.request(hwnd, generation, self.backend.api.IsWindowVisible)

    def _set_enabled(self, enabled):
        self.enabled = enabled
        if not enabled:
            self.preview.hide()
            self.candidate = None
            self.candidate_corner = None
            self.candidate_placement = None
            self.candidate_edge_ratio = None

    def close(self):
        self.unlock_folder(notify=False)
        self._reset_focus_behavior()
        self.timer.stop()
        self.reader.closed = True
        self.preview.close()
