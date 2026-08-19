from ..common import *

# ======================== 摄像头检测线程 ========================
class CameraThread(QThread):
    """
    后台线程: 持续读取摄像头视频流并运行人体检测。
    支持两种模型:
      - "hog":  HOG 行人 + Haar 人脸 (传统检测, 无需额外依赖)
      - "yolo": YOLOv26 深度学习模型 (需要 ultralytics 包)
    每帧发射 frame_ready(QImage, list) 信号;
    人数变化时发射 person_count_changed(int) 信号。
    检测结果: [(x, y, w, h, is_main), ...]  is_main=True 为最大框(主人)
    """
    frame_ready = pyqtSignal(object, list, list, list, list)   # QImage, boxes, confs, skipped, kpts
    person_count_changed = pyqtSignal(int)
    camera_error = pyqtSignal(str)

    # 检测参数
    DETECT_WIDTH = 480        # 检测用缩放宽度 (越小越快)
    DETECT_INTERVAL = 3       # 每 N 帧检测一次
    MIN_BOX_AREA = 80 * 160   # 过滤太小的框 (HOG 模式)

    def __init__(self, camera_index=0, model="hog", yolo_model="yolo26n.pt",
                 yolo_conf=0.4, trigger_count=2, sustain_sec=1.5,
                 pose_kpt_conf=0.5, debug_save=False, dedup_iou=0.55):
        super().__init__()
        self.camera_index = camera_index
        self.model = model                       # "hog" / "yolo"
        self.yolo_model = yolo_model
        self.yolo_conf = yolo_conf
        self.pose_kpt_conf = max(0.05, min(0.95, float(pose_kpt_conf)))
        self.dedup_iou = max(0.2, min(0.95, float(dedup_iou)))  # 重复框合并阈值
        self.trigger_count = max(2, int(trigger_count))   # 触发人数阈值
        self.sustain_sec = max(0.0, float(sustain_sec))   # 持续秒数
        self.debug_save = bool(debug_save)       # 调试: 触发切换时保存标注图片

        self._running = False
        self._mutex = QMutex()

        # HOG 行人检测器 (全身, 适合站立的行人)
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

        # Haar 正脸检测器 (近距离坐着的上半身用户)
        cascade_path = os.path.join(
            cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        self.face_cascade = cv2.CascadeClassifier(cascade_path)

        # YOLO 模型 (懒加载, run() 中初始化)
        self.yolo = None
        self.pose_mode = False   # True = pose 模型, 按"头部关键点"计数

        # 缓存最近一次检测结果 (供跳帧期间绘制)
        self._last_boxes = []
        self._last_confs = []    # 与 _last_boxes 对齐的置信度 (无则 -1)
        self._last_skipped = []  # pose 模式被头部阈值过滤掉的人 [(x,y,w,h,head_conf), ...]
        self._last_kpts = []     # pose 模式头部关键点 [(x, y, conf), ...] 原图坐标
        self._last_display = None   # 最近一帧标注后的图 (调试存图用)
        # 多人确认计时
        self._multi_since = None
        self._multi_emitted = False

    def _init_yolo(self):
        """加载 YOLO 模型; 失败时返回错误信息"""
        try:
            from ultralytics import YOLO
            # 所有内置权重统一放在 assets/models。给 YOLO 传绝对路径后，
            # Ultralytics 在文件缺失时也会直接下载到该路径，而不是当前目录。
            model_dir = os.path.join(BASE_DIR, "assets", "models")
            os.makedirs(model_dir, exist_ok=True)
            requested = os.path.basename(str(self.yolo_model).strip()) or "yolo26n.pt"
            names = [requested, "yolo11n.pt", "yolov8n.pt"]
            candidates = [os.path.join(model_dir, name) for name in names]
            tried = []
            for name in candidates:
                if name in tried:
                    continue
                tried.append(name)
                try:
                    self.yolo = YOLO(name)
                    # 识别是否为 pose 模型 (任务类型或文件名判断)
                    task = getattr(self.yolo, "task", "") or ""
                    self.pose_mode = ("pose" in str(task).lower()
                                      or "pose" in os.path.basename(str(name)).lower())
                    mode_text = " [pose 模式: 按头部关键点计数]" if self.pose_mode else ""
                    _log(f"YOLO 模型加载成功: {name}{mode_text}")
                    return None
                except Exception as e:
                    _log(f"YOLO 权重 {name} 加载失败: {e}")
            return f"YOLO 模型均加载失败: {tried}"
        except ImportError:
            return "未安装 ultralytics 包 (pip install ultralytics)"
        except Exception as e:
            return f"YOLO 初始化异常: {e}"

    # ---------- 线程主循环 ----------

    def run(self):
        # YOLO 模式先加载模型
        if self.model == "yolo":
            err = self._init_yolo()
            if err:
                _log(f"YOLO 不可用, 回退到 HOG 模式: {err}")
                self.camera_error.emit(err + " | 已回退到 HOG 检测")
                self.model = "hog"

        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            self.camera_error.emit(f"无法打开摄像头 {self.camera_index}")
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        _log(f"摄像头 {self.camera_index} 已打开")

        self._running = True
        frame_idx = 0

        while self._running:
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            # 水平镜像翻转 (前置摄像头自拍效果, 画面更直观)
            frame = cv2.flip(frame, 1)

            frame_idx += 1
            h, w = frame.shape[:2]

            # ---------- 检测 (每 DETECT_INTERVAL 帧一次) ----------
            need_report = False
            if frame_idx % self.DETECT_INTERVAL == 0:
                boxes = self._detect(frame, w, h)
                self._last_boxes = boxes
                need_report = True
            boxes = self._last_boxes

            # ---------- 绘制检测框并转 QImage ----------
            display = self._draw_boxes(frame.copy(), boxes, self._last_confs,
                                       self._last_skipped, self._last_kpts)
            self._last_display = display
            # 先画完本帧再上报人数, 保证触发时的调试存图
            # 与触发判断用的是同一帧 (含全部框/SKIP/关键点)
            if need_report:
                self._report_count(len(boxes))
            rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
            qimg = QImage(rgb.data, rgb.shape[1], rgb.shape[0],
                          rgb.strides[0], QImage.Format_RGB888)
            # 拷贝一份, 防止底层缓冲被复用
            qimg = qimg.copy()
            self.frame_ready.emit(qimg, boxes, list(self._last_confs),
                                  list(self._last_skipped),
                                  list(self._last_kpts))

            self.msleep(33)  # ~30 FPS

        cap.release()
        _log("摄像头已释放")

    def stop(self):
        self._running = False
        self.wait(3000)

    # ---------- 检测逻辑 ----------

    def _detect(self, frame, orig_w, orig_h):
        """
        根据当前模型分发检测。
        内部返回 [(x, y, w, h, conf), ...]
        最终设置 self._last_confs 并返回 [(x, y, w, h, is_main), ...]
        """
        if self.model == "yolo" and self.yolo is not None:
            self._last_skipped = []
            self._last_kpts = []
            raw = self._detect_yolo(frame, orig_w, orig_h)
        else:
            self._last_skipped = []
            self._last_kpts = []
            raw = self._detect_hog(frame, orig_w, orig_h)

        # 同一人被识别成多个几乎重叠的框 → 合并去重
        raw = self._dedup_boxes(raw)

        if not raw:
            self._last_confs = []
            return []

        # 找最大面积框 → 主人(绿框)
        areas = [b[2] * b[3] for b in raw]
        main_idx = int(np.argmax(areas)) if raw else -1
        result = []
        confs = []
        for i, b in enumerate(raw):
            result.append((b[0], b[1], b[2], b[3], i == main_idx))
            c = b[4] if len(b) > 4 else -1.0
            confs.append(float(c) if c is not None else -1.0)
        self._last_confs = confs
        return result

    # ---------- 重复框合并 ----------

    @staticmethod
    def _iou(b1, b2):
        """两框 IoU + 包含率: 返回 max(IoU, 交集/较小框面积)
        后者用于捕获"嵌套框"(大框套小框, IoU 不高但明显是同一人)"""
        x1 = max(b1[0], b2[0]); y1 = max(b1[1], b2[1])
        x2 = min(b1[0] + b1[2], b2[0] + b2[2])
        y2 = min(b1[1] + b1[3], b2[1] + b2[3])
        if x2 <= x1 or y2 <= y1:
            return 0.0
        inter = (x2 - x1) * (y2 - y1)
        a1 = b1[2] * b1[3]; a2 = b2[2] * b2[3]
        union = a1 + a2 - inter
        return max(inter / union if union > 0 else 0.0,
                   inter / min(a1, a2) if min(a1, a2) > 0 else 0.0)

    def _dedup_boxes(self, boxes):
        """贪心去重: 按置信度降序保留, 与已保留框重叠率(IoU/包含率)
        >= dedup_iou 的框视为同一人, 丢弃。"""
        if len(boxes) <= 1:
            return boxes
        items = sorted(boxes, key=lambda b: (b[4] if len(b) > 4 else 0.0),
                       reverse=True)
        kept = []
        for b in items:
            if all(self._iou(b, k) < self.dedup_iou for k in kept):
                kept.append(b)
        return kept

    def _detect_yolo(self, frame, orig_w, orig_h):
        """YOLOv26 人体检测 (class 0 = person); pose 模型按头部关键点过滤"""
        try:
            scale = self.DETECT_WIDTH / orig_w
            small = cv2.resize(frame, (self.DETECT_WIDTH,
                                       int(orig_h * scale)))
            if self.pose_mode:
                return self._detect_yolo_pose(small, scale)
            results = self.yolo.predict(
                small, classes=[0], conf=self.yolo_conf,
                verbose=False, imgsz=self.DETECT_WIDTH
            )
            boxes = []
            for r in results:
                for b in r.boxes:
                    x1, y1, x2, y2 = b.xyxy[0].tolist()
                    conf = float(b.conf[0]) if b.conf is not None and len(b.conf) else -1.0
                    bx = int(x1 / scale)
                    by = int(y1 / scale)
                    bw = int((x2 - x1) / scale)
                    bh = int((y2 - y1) / scale)
                    if bw > 10 and bh > 10:
                        boxes.append([bx, by, bw, bh, conf])
            return boxes
        except Exception as e:
            _log(f"YOLO 检测异常: {e}")
            return self._last_boxes and [list(b[:4]) for b in self._last_boxes] or []

    # COCO 17 关键点中的头部点: 0=鼻, 1=左眼, 2=右眼, 3=左耳, 4=右耳
    HEAD_KPT_IDS = (0, 1, 2, 3, 4)

    def _detect_yolo_pose(self, small, scale):
        """
        pose 模型检测: 每个检出的人, 只有当其头部关键点(鼻/眼/耳)中
        置信度最高者 >= pose_kpt_conf 时才算一个"出现的头", 计入人数。
        身体被遮挡但头部可见的人也能被正确计数。
        """
        results = self.yolo.predict(
            small, conf=self.yolo_conf, verbose=False,
            imgsz=self.DETECT_WIDTH
        )
        boxes = []
        for r in results:
            kpts = getattr(r, "keypoints", None)
            n = len(r.boxes)
            for i in range(n):
                head_ok = False
                head_confs = []
                if kpts is not None and kpts.data is not None and len(kpts.data) > i:
                    try:
                        # data: (17, 3) 每行 [x, y, conf]
                        kdata = kpts.data[i]
                        if kdata.shape[0] >= 5:
                            head_confs = [float(kdata[k][2])
                                          for k in self.HEAD_KPT_IDS]
                            head_ok = (max(head_confs) >= self.pose_kpt_conf)
                    except Exception as e:
                        _log(f"关键点解析异常: {e}")
                        head_ok = False
                if not head_ok:
                    # 不计数, 但保留框用于调试绘制 (灰色 SKIP)
                    x1, y1, x2, y2 = r.boxes[i].xyxy[0].tolist()
                    sk = (int(x1 / scale), int(y1 / scale),
                          int((x2 - x1) / scale), int((y2 - y1) / scale),
                          max(head_confs) if head_confs else -1.0)
                    if sk[2] > 10 and sk[3] > 10:
                        self._last_skipped.append(sk)
                    continue   # 头部不可见/置信度低 → 不计数
                # 标注用置信度 = 头部关键点最高置信度 (更有参考意义)
                head_conf = max(head_confs) if head_confs else -1.0
                # 头部关键点 (原图坐标) 用于调试绘制
                for k in self.HEAD_KPT_IDS:
                    try:
                        kx = float(kdata[k][0]) / scale
                        ky = float(kdata[k][1]) / scale
                        kc = float(kdata[k][2])
                        if kc > 0.01 and 0 <= kx and 0 <= ky:
                            self._last_kpts.append((int(kx), int(ky), kc))
                    except Exception:
                        pass
                x1, y1, x2, y2 = r.boxes[i].xyxy[0].tolist()
                bx = int(x1 / scale)
                by = int(y1 / scale)
                bw = int((x2 - x1) / scale)
                bh = int((y2 - y1) / scale)
                if bw > 10 and bh > 10:
                    boxes.append([bx, by, bw, bh, head_conf])
        return boxes

    def _detect_hog(self, frame, orig_w, orig_h):
        """
        融合检测: HOG 全身行人 + Haar 正脸。
        脸落在 HOG 框内 → 同一个人; 框外的脸视为额外的人 (近距离坐姿用户)。
        """
        scale = self.DETECT_WIDTH / orig_w
        small = cv2.resize(frame, (self.DETECT_WIDTH,
                                   int(orig_h * scale)))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        boxes = []

        # ---------- HOG 全身行人 ----------
        try:
            rects, weights = self.hog.detectMultiScale(
                small, winStride=(8, 8), padding=(4, 4), scale=1.05
            )
            for (x, y, w, h), wt in zip(rects, weights):
                wt = float(wt)
                if wt < 0.3:   # 置信度过滤
                    continue
                bx, by = int(x / scale), int(y / scale)
                bw, bh = int(w / scale), int(h / scale)
                if bw * bh >= self.MIN_BOX_AREA:
                    boxes.append([bx, by, bw, bh, min(1.0, wt)])
        except cv2.error as e:
            _log(f"HOG 检测异常: {e}")

        # NMS 合并 HOG 重叠框
        boxes = self._nms(boxes, 0.4)

        # ---------- Haar 人脸 (补充近距离坐姿用户) ----------
        try:
            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.15, minNeighbors=5, minSize=(36, 36)
            )
        except cv2.error:
            faces = []

        for (fx, fy, fw, fh) in faces:
            cx = fx + fw / 2
            cy = fy + fh / 2
            # 该脸的中心是否已落在某个 HOG 框内 (small 坐标系比较)
            inside = any(
                x <= cx <= x + w and y <= cy <= y + h
                for (x, y, w, h) in [
                    (b[0] * scale, b[1] * scale, b[2] * scale, b[3] * scale)
                    for b in boxes
                ]
            )
            if inside:
                continue
            # 框外的脸 → 独立的人, 估算上半身框 (脸向下扩展)
            ex = int((fx - fw * 0.5) / scale)
            ey = int((fy - fh * 0.3) / scale)
            ew = int(fw * 2.0 / scale)
            eh = int(fh * 3.0 / scale)
            # 限制在画面内
            ex = max(0, min(ex, orig_w - 1))
            ey = max(0, min(ey, orig_h - 1))
            ew = min(ew, orig_w - ex)
            eh = min(eh, orig_h - ey)
            boxes.append([ex, ey, ew, eh, -1.0])   # Haar 无置信度

        return boxes

    @staticmethod
    def _nms(boxes, threshold):
        """简单非极大值抑制"""
        if not boxes:
            return []
        arr = np.array(boxes, dtype=float)
        x1, y1 = arr[:, 0], arr[:, 1]
        x2, y2 = arr[:, 0] + arr[:, 2], arr[:, 1] + arr[:, 3]
        areas = arr[:, 2] * arr[:, 3]
        order = areas.argsort()[::-1]

        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
            iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
            order = order[1:][iou < threshold]

        return [list(boxes[int(i)]) for i in keep]

    # ---------- 人数上报 ----------

    def _report_count(self, count):
        now = datetime.now()
        if count >= self.trigger_count:
            if self.sustain_sec <= 0:
                # 立即触发模式
                if not self._multi_emitted:
                    self._multi_emitted = True
                    self._save_debug_shot(count)
                    self.person_count_changed.emit(count)
            else:
                if self._multi_since is None:
                    self._multi_since = now
                    self._multi_emitted = False
                elif (not self._multi_emitted and
                      (now - self._multi_since).total_seconds() >= self.sustain_sec):
                    # 确认多人 → 只发射一次
                    self._multi_emitted = True
                    self._save_debug_shot(count)
                    self.person_count_changed.emit(count)
        else:
            # 人离开 → 重置, 下次再次检出多人会重新触发
            if self._multi_since is not None or self._multi_emitted:
                self._multi_since = None
                self._multi_emitted = False
                self.person_count_changed.emit(count)

    # ---------- 调试存图 ----------

    def _save_debug_shot(self, count):
        """
        调试模式: 满足切换条件时, 把最近一帧 (已绘制检测框+置信度)
        保存到 debug_shots/ 目录, 文件名含时间戳和检出数量。
        """
        if not self.debug_save or self._last_display is None:
            return
        try:
            root_dir = os.path.join(BASE_DIR, "debug_shots")
            day_name = datetime.now().strftime("%Y%m%d")
            out_dir = os.path.join(root_dir, day_name)
            os.makedirs(out_dir, exist_ok=True)
            # 只清理由本程序创建的 YYYYMMDD 日期目录, 最多保留最近 3 天。
            day_dirs = sorted(
                name for name in os.listdir(root_dir)
                if len(name) == 8 and name.isdigit()
                and os.path.isdir(os.path.join(root_dir, name)))
            for old_day in day_dirs[:-3]:
                old_path = os.path.join(root_dir, old_day)
                try:
                    import shutil
                    shutil.rmtree(old_path)
                    _log(f"[调试] 已清理过期截图目录: {old_day}")
                except Exception as cleanup_error:
                    _log(f"[调试] 清理 {old_day} 失败: {cleanup_error}")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            unit = "head" if self.pose_mode else "person"
            path = os.path.join(out_dir, f"trigger_{ts}_{count}{unit}.jpg")
            ok, buf = cv2.imencode(".jpg", self._last_display,
                                   [cv2.IMWRITE_JPEG_QUALITY, 90])
            if ok:
                with open(path, "wb") as f:
                    f.write(buf.tobytes())
                _log(f"[调试] 已保存触发截图: {os.path.basename(path)}")
            else:
                _log("[调试] 截图编码失败")
        except Exception as e:
            _log(f"[调试] 保存触发截图失败: {e}")

    # ---------- 绘制 ----------

    @staticmethod
    def _draw_boxes(frame, boxes, confs=None, skipped=None, kpts=None):
        """
        主人体绿框, 其他红框; confs 对齐时显示置信度。
        skipped: pose 模式被过滤的人 → 灰色 SKIP 框 (head_conf)
        kpts:    pose 模式头部关键点 → 黄色圆点, 达阈值画实心
        """
        # 先画被过滤的 (底层), 再画计入的 (上层)
        if skipped:
            for (x, y, w, h, c) in skipped:
                cv2.rectangle(frame, (x, y), (x + w, y + h),
                              (160, 160, 160), 1)
                label = f"SKIP {c:.2f}" if c is not None and c >= 0 else "SKIP"
                cv2.putText(frame, label, (x + 3, y + 16),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 160, 160), 1)
        for idx, (x, y, w, h, is_main) in enumerate(boxes):
            color = (0, 255, 0) if is_main else (0, 0, 255)  # BGR
            thickness = 3 if is_main else 2
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, thickness)
            label = "MAIN" if is_main else "PERSON"
            if confs and idx < len(confs) and confs[idx] is not None and confs[idx] >= 0:
                label += f" {confs[idx]:.2f}"
            # 标签背景
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            ty = y if y - th - 10 >= 0 else y + th + 10   # 贴顶时标签放框内下方
            cv2.rectangle(frame, (x, ty - th - 10), (x + tw + 10, ty), color, -1)
            cv2.putText(frame, label, (x + 5, ty - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        # 头部关键点: 黄色圆点 (实心=conf≥0.5, 空心=低置信度)
        if kpts:
            for (kx, ky, kc) in kpts:
                r, thick = (4, -1) if kc >= 0.5 else (4, 1)
                cv2.circle(frame, (kx, ky), r, (0, 255, 255), thick)
        return frame
