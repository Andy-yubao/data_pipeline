#!/usr/bin/env python
# ==============================================================================
# 环境声明: Python 3.12
# 核心依赖: tkinter（Python 内置）
# 脚本身份: AutoCar 数据处理面板 - 统一 GUI 启动器
# 核心逻辑: 主页面选择功能 → 独立二级页面分别执行
# ==============================================================================

import os
import sys
import shutil
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import glob as _glob

from data_reviewer import run_reviewer
from data_processor import create_tub
from data_merger import merge_datasets


# ==========================================
# 模块级工具函数
# ==========================================

def _resolve(rel_path):
    """将相对于项目根目录的路径转为绝对路径"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root = os.path.normpath(os.path.join(script_dir, '..'))
    return os.path.normpath(os.path.join(root, rel_path))


def _default_input():
    """返回默认数据集目录（第一个存在的候选）"""
    candidates = [
        "E:/autonomous_driving/datas_ot1",
        _resolve("user/clockwise-v1/datas"),
        _resolve("user/anticlockwise-v1/datas"),
    ]
    for p in candidates:
        if os.path.isdir(p):
            return os.path.normpath(p)
    return ""


def _default_trash(input_dir=None):
    """返回默认垃圾箱目录

    规则: 数据集同级目录下的 trash/
    例: user/clockwise-v1/datas → user/clockwise-v1/trash
    """
    if input_dir and os.path.isdir(input_dir):
        parent = os.path.dirname(os.path.normpath(input_dir))
        return os.path.join(parent, "trash")
    # 回退：用于初始加载时 input_dir 无效的情况
    return _resolve("user/trash")


def _compute_tub_path(input_dir):
    """根据数据集目录计算强制 tub 输出路径

    clockwise-v1/datas → clockwise-v1/tub
    anticlockwise-v1/datas → anticlockwise-v1/tub
    """
    if not input_dir or not os.path.isdir(input_dir):
        return ""
    project_dir = os.path.dirname(os.path.normpath(input_dir))
    return os.path.join(project_dir, "tub")


def _find_tub_dirs(input_dir):
    """扫描数据集父目录下的 tub* 目录列表"""
    if not input_dir or not os.path.isdir(input_dir):
        return []
    parent = os.path.dirname(os.path.normpath(input_dir))
    tub_dirs = []
    try:
        for name in os.listdir(parent):
            full = os.path.join(parent, name)
            if os.path.isdir(full) and name.startswith('tub'):
                tub_dirs.append(full)
    except OSError:
        pass
    return sorted(tub_dirs)


def _count_classes(input_dir):
    """统计目录中各类别图片数量

    Returns:
        dict {"FW": n, "TL": n, "TR": n} 或 None（目录无效）
    """
    if not input_dir or not os.path.isdir(input_dir):
        return None
    counts = {"FW": 0, "TL": 0, "TR": 0}
    for f in _glob.glob(os.path.join(input_dir, '*.jpg')):
        name = os.path.basename(f)
        parts = name.split('_')
        if len(parts) >= 3:
            cmd = parts[-1].split('.')[0]
            if cmd in counts:
                counts[cmd] += 1
    return counts


# ==========================================
# 日志重定向器（线程安全）
# ==========================================

class LogRedirector:
    """将 print 输出安全地重定向到 tkinter Text 组件（线程安全）"""

    def __init__(self, root, write_callback):
        self.root = root
        self.write_callback = write_callback
        self._buffer = ""

    def write(self, s):
        self._buffer += s
        if '\n' in self._buffer:
            lines = self._buffer.split('\n')
            for line in lines[:-1]:
                if line.strip():
                    self.root.after(0, self.write_callback, line)
            self._buffer = lines[-1]

    def flush(self):
        if self._buffer.strip():
            self.root.after(0, self.write_callback, self._buffer)
            self._buffer = ""


# ==========================================
# 通用日志面板 Mixin（供各二级页面复用）
# ==========================================

class _LogMixin:
    """为页面提供日志 Text 组件和 log() 方法"""

    def _build_log_frame(self, parent):
        """构建日志区域，返回 (log_frame, log_text)"""
        log_frame = ttk.LabelFrame(parent, text="日志", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 10))

        log_text = tk.Text(log_frame, height=10, wrap=tk.WORD,
                           font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4",
                           insertbackground="white")
        log_text.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_text, command=log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        log_text.config(yscrollcommand=scrollbar.set)

        return log_frame, log_text

    def log(self, msg):
        """追加日志行"""
        try:
            self._log_text.insert(tk.END, msg + "\n")
            self._log_text.see(tk.END)
            self.update_idletasks()
        except tk.TclError:
            pass  # 窗口已销毁


# ==========================================
# 主启动器页面
# ==========================================

class DataLauncher:
    """GUI 主启动器：提供三个功能入口按钮"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AutoCar 数据处理面板")
        self.root.geometry("500x350")
        self.root.minsize(400, 280)
        self.root.resizable(True, True)

        # 页面引用（防重复打开）
        self._review_page = None
        self._augment_page = None
        self._merge_page = None

        # ---- 顶部标题 ----
        header = ttk.Label(
            self.root,
            text="自动驾驶数据流水线 — 请选择功能",
            font=("", 11, "bold"),
        )
        header.pack(pady=(16, 20))

        # ---- 三个功能按钮 ----
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(expand=True)

        btn_style = {"width": 36, "padding": 12}

        ttk.Button(
            btn_frame, text="数据清洗\n人工审核标记垃圾图片",
            command=self._open_review, **btn_style
        ).pack(pady=8)

        ttk.Button(
            btn_frame, text="数据增强与均衡\n标准化处理 + 数据增强 + 类别均衡",
            command=self._open_augment, **btn_style
        ).pack(pady=8)

        ttk.Button(
            btn_frame, text="数据合并\n多数据源按比例采样合并",
            command=self._open_merge, **btn_style
        ).pack(pady=8)

    # ---- 打开二级页面 ----

    def _open_review(self):
        if self._review_page is not None and self._review_page.winfo_exists():
            self._review_page.lift()
            self._review_page.focus_force()
            return
        self._review_page = ReviewPage(self.root)

    def _open_augment(self):
        if self._augment_page is not None and self._augment_page.winfo_exists():
            self._augment_page.lift()
            self._augment_page.focus_force()
            return
        self._augment_page = AugmentPage(self.root)

    def _open_merge(self):
        if self._merge_page is not None and self._merge_page.winfo_exists():
            self._merge_page.lift()
            self._merge_page.focus_force()
            return
        self._merge_page = MergePage(self.root)


# ==========================================
# 二级页面：数据清洗
# ==========================================

class ReviewPage(tk.Toplevel, _LogMixin):
    """数据清洗页面 — 人工审核标记垃圾图片"""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("数据清洗 - 人工审核")
        self.geometry("600x520")
        self.minsize(500, 360)
        self.transient(parent)

        # ---- 目录设置 ----
        dir_frame = ttk.LabelFrame(self, text="目录设置", padding=10)
        dir_frame.pack(fill=tk.X, padx=12, pady=(10, 8))

        # 数据集目录
        row0 = ttk.Frame(dir_frame)
        row0.pack(fill=tk.X, pady=2)
        ttk.Label(row0, text="数据集目录:", width=14).pack(side=tk.LEFT)
        self.input_var = tk.StringVar(value=_default_input())
        ttk.Entry(row0, textvariable=self.input_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(row0, text="浏览...", width=7,
                   command=self._browse_input).pack(side=tk.RIGHT)

        # 垃圾箱目录（默认: 数据集同级目录下的 trash/）
        row1 = ttk.Frame(dir_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="垃圾箱目录:", width=14).pack(side=tk.LEFT)
        self.trash_var = tk.StringVar(
            value=_default_trash(self.input_var.get()))
        ttk.Entry(row1, textvariable=self.trash_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(row1, text="浏览...", width=7,
                   command=self._browse_trash).pack(side=tk.RIGHT)

        # 数据集目录变更时自动更新垃圾箱路径
        self.input_var.trace_add('write', lambda *_: self._auto_update_trash())

        # ---- 操作按钮 ----
        self.btn_review = ttk.Button(
            self, text="开始审核", width=16,
            command=self._on_review
        )
        self.btn_review.pack(pady=(6, 4))

        # ---- 日志 ----
        _, self._log_text = self._build_log_frame(self)
        self.log("就绪。选择目录后点击「开始审核」。")

    # ---- 浏览按钮 ----
    def _browse_input(self):
        path = filedialog.askdirectory(title="选择数据集目录")
        if path:
            self.input_var.set(os.path.normpath(path))

    def _browse_trash(self):
        path = filedialog.askdirectory(title="选择垃圾箱目录")
        if path:
            self.trash_var.set(os.path.normpath(path))

    def _auto_update_trash(self):
        """输入目录变更时自动计算默认垃圾箱路径

        仅在 trash 未被用户手动修改时自动覆盖；用户手动设定的路径不受影响。
        """
        input_dir = self.input_var.get().strip()
        new_default = _default_trash(input_dir) if input_dir else ""
        current = self.trash_var.get().strip()

        # 如果当前值为空、或与旧默认值一致，则自动更新
        if not current or not hasattr(self, '_last_trash_default') \
                or current == getattr(self, '_last_trash_default', ''):
            if new_default:
                self.trash_var.set(new_default)
        self._last_trash_default = new_default

    # ---- 审核流程 ----
    def _on_review(self):
        input_dir = self.input_var.get().strip()
        trash_dir = self.trash_var.get().strip()

        if not input_dir or not os.path.isdir(input_dir):
            messagebox.showerror("错误", f"数据集目录不存在:\n{input_dir or '(空)'}")
            return

        jpg_count = len(_glob.glob(os.path.join(input_dir, '*.jpg')))
        if jpg_count == 0:
            messagebox.showwarning("警告", f"该目录中没有找到 .jpg 图片:\n{input_dir}")
            return

        self.log(f"[审核] 启动 → {input_dir}")
        self.log(f"[审核] 共 {jpg_count} 张图片，垃圾箱: {trash_dir}")

        # 确认回调
        def gui_confirm(count, trash):
            return messagebox.askyesno(
                "确认移动",
                f"你一共标记了 {count} 张垃圾图片。\n\n"
                f"是否将它们移动到垃圾箱？\n{trash}"
            )

        # 隐藏本窗口，交由 OpenCV 接管
        self.withdraw()
        try:
            run_reviewer(input_dir, trash_dir, confirm_callback=gui_confirm)
        finally:
            try:
                self.deiconify()
                self.log("[审核] 完成。")
            except tk.TclError:
                pass


# ==========================================
# 二级页面：数据增强与均衡
# ==========================================

class AugmentPage(tk.Toplevel, _LogMixin):
    """数据增强与均衡页面 — 标准化处理 + 数据增强 + 类别均衡"""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("数据增强与均衡")
        self.geometry("720x640")
        self.minsize(600, 480)
        self.transient(parent)

        # ---- 目录设置 ----
        dir_frame = ttk.LabelFrame(self, text="目录设置", padding=10)
        dir_frame.pack(fill=tk.X, padx=12, pady=(10, 8))

        # 数据集目录
        row0 = ttk.Frame(dir_frame)
        row0.pack(fill=tk.X, pady=2)
        ttk.Label(row0, text="数据集目录:", width=14).pack(side=tk.LEFT)
        self.input_var = tk.StringVar(value=_default_input())
        ttk.Entry(row0, textvariable=self.input_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(row0, text="浏览...", width=7,
                   command=self._browse_input).pack(side=tk.RIGHT)

        # Tub 输出目录（默认: 数据集同级目录下的 tub/，不存在则自动创建）
        row1 = ttk.Frame(dir_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Tub 输出目录:", width=14).pack(side=tk.LEFT)
        self.output_var = tk.StringVar(
            value=_compute_tub_path(self.input_var.get()))
        ttk.Entry(row1, textvariable=self.output_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(row1, text="浏览...", width=7,
                   command=self._browse_output).pack(side=tk.RIGHT)

        # 数据集目录变更时自动更新 tub 输出路径
        self.input_var.trace_add('write', lambda *_: self._auto_update_output())

        # ---- 增强选项 + 均衡 + 操作按钮 ----
        action_frame = ttk.Frame(self)
        action_frame.pack(fill=tk.X, padx=12, pady=4)

        # -- 数据增强 --
        aug_frame = ttk.LabelFrame(action_frame, text="数据增强", padding=6)
        aug_frame.pack(side=tk.LEFT)

        # 高斯模糊
        blur_row = ttk.Frame(aug_frame)
        blur_row.pack(anchor=tk.W, pady=1)
        self.blur_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(blur_row, text="高斯模糊", variable=self.blur_var,
                        width=14).pack(side=tk.LEFT)
        ttk.Label(blur_row, text=" 概率").pack(side=tk.LEFT)
        self.blur_prob_var = tk.IntVar(value=10)
        ttk.Spinbox(blur_row, from_=1, to=100, width=3,
                    textvariable=self.blur_prob_var).pack(side=tk.LEFT)
        ttk.Label(blur_row, text="%").pack(side=tk.LEFT)

        # 亮度/对比度
        bc_row = ttk.Frame(aug_frame)
        bc_row.pack(anchor=tk.W, pady=1)
        self.bc_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bc_row, text="亮度/对比度", variable=self.bc_var,
                        width=14).pack(side=tk.LEFT)
        ttk.Label(bc_row, text=" 概率").pack(side=tk.LEFT)
        self.bc_prob_var = tk.IntVar(value=10)
        ttk.Spinbox(bc_row, from_=1, to=100, width=3,
                    textvariable=self.bc_prob_var).pack(side=tk.LEFT)
        ttk.Label(bc_row, text="%").pack(side=tk.LEFT)

        # 覆盖原图
        self.replace_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(aug_frame, text="覆盖原图（不保留原始帧）",
                        variable=self.replace_var).pack(anchor=tk.W, pady=2)

        # -- 数据均衡 --
        bal_frame = ttk.LabelFrame(action_frame, text="数据均衡", padding=6)
        bal_frame.pack(side=tk.LEFT, padx=8)

        # 启用开关
        self.balance_enabled_var = tk.BooleanVar(value=False)
        self.balance_mode_var = tk.StringVar(value='downsample')

        bal_top = ttk.Frame(bal_frame)
        bal_top.pack(anchor=tk.W, pady=1)
        ttk.Checkbutton(bal_top, text="启用类别均衡",
                        variable=self.balance_enabled_var,
                        command=self._toggle_balance).pack(side=tk.LEFT)

        # 各类张数显示
        self.bal_count_var = tk.StringVar(value="(未扫描)")
        count_row = ttk.Frame(bal_frame)
        count_row.pack(anchor=tk.W, pady=1)
        ttk.Label(count_row, text="当前:", foreground="gray").pack(side=tk.LEFT)
        ttk.Label(count_row, textvariable=self.bal_count_var,
                  foreground="gray").pack(side=tk.LEFT)

        # 建议比例按钮
        suggest_row = ttk.Frame(bal_frame)
        suggest_row.pack(anchor=tk.W, pady=1)
        self._bal_suggest_btn = ttk.Button(
            suggest_row, text="建议比例", width=9,
            command=self._suggest_ratio, state=tk.DISABLED)
        self._bal_suggest_btn.pack(side=tk.LEFT)
        self._bal_suggest_label = ttk.Label(
            suggest_row, text="", foreground="gray")
        self._bal_suggest_label.pack(side=tk.LEFT, padx=4)

        # 比例设置
        self.balance_fw_var = tk.IntVar(value=2)
        self.balance_tl_var = tk.IntVar(value=2)
        self.balance_tr_var = tk.IntVar(value=1)

        ratio_row = ttk.Frame(bal_frame)
        ratio_row.pack(anchor=tk.W, pady=1)
        self._bal_ratio_widgets = []
        for label, var in [("FW", self.balance_fw_var),
                           ("TL", self.balance_tl_var),
                           ("TR", self.balance_tr_var)]:
            ttk.Label(ratio_row, text=f" {label}").pack(side=tk.LEFT)
            sb = ttk.Spinbox(ratio_row, from_=1, to=10, width=3,
                             textvariable=var, state=tk.DISABLED)
            sb.pack(side=tk.LEFT)
            self._bal_ratio_widgets.append(sb)

        # 模式选择
        mode_row = ttk.Frame(bal_frame)
        mode_row.pack(anchor=tk.W, pady=1)
        self._bal_radio_ds = ttk.Radiobutton(
            mode_row, text="降采样", value="downsample",
            variable=self.balance_mode_var, state=tk.DISABLED)
        self._bal_radio_ds.pack(side=tk.LEFT)
        self._bal_radio_us = ttk.Radiobutton(
            mode_row, text="升采样", value="upsample",
            variable=self.balance_mode_var, state=tk.DISABLED)
        self._bal_radio_us.pack(side=tk.LEFT)
        self._bal_mode_widgets = [self._bal_radio_ds, self._bal_radio_us]

        # -- 操作按钮 --
        btn_frame = ttk.Frame(action_frame)
        btn_frame.pack(side=tk.RIGHT)

        self.btn_process = ttk.Button(btn_frame, text="标准化处理", width=14,
                                      command=self._on_process)
        self.btn_process.pack(side=tk.LEFT, padx=3)

        # ---- 日志 ----
        _, self._log_text = self._build_log_frame(self)
        self.log("就绪。设置参数后点击「标准化处理」。")

        # 初始化各类计数
        self._refresh_counts()

    # ---- 浏览按钮 ----
    def _browse_input(self):
        path = filedialog.askdirectory(title="选择数据集目录")
        if path:
            self.input_var.set(os.path.normpath(path))

    def _browse_output(self):
        path = filedialog.askdirectory(title="选择 Tub 输出目录（不存在将自动创建）")
        if path:
            self.output_var.set(os.path.normpath(path))

    # ---- 自动更新输出路径 ----
    def _auto_update_output(self):
        """输入目录变更时自动计算并更新 tub 输出路径和各类计数

        仅在 output 未被用户手动修改时自动覆盖。
        """
        input_dir = self.input_var.get()
        new_default = _compute_tub_path(input_dir)
        current = self.output_var.get().strip()

        # 如果当前值为空、或与旧默认值一致，则自动更新
        if not current or not hasattr(self, '_last_output_default') \
                or current == getattr(self, '_last_output_default', ''):
            if new_default:
                self.output_var.set(new_default)
        self._last_output_default = new_default

        self._refresh_counts()
        self._bal_suggest_label.config(text="")

    # ---- 均衡控件状态 ----
    def _toggle_balance(self):
        """启用/禁用均衡控件的可编辑状态"""
        enabled = self.balance_enabled_var.get()
        state = tk.NORMAL if enabled else tk.DISABLED
        for w in self._bal_ratio_widgets:
            w.config(state=state)
        for w in self._bal_mode_widgets:
            w.config(state=state)
        self._bal_suggest_btn.config(state=state)
        if enabled:
            self._refresh_counts()

    def _refresh_counts(self):
        """更新均衡面板中的各类张数显示"""
        input_dir = self.input_var.get().strip()
        counts = _count_classes(input_dir)
        if counts:
            self.bal_count_var.set(
                f"FW={counts['FW']}, TL={counts['TL']}, TR={counts['TR']}")
        else:
            self.bal_count_var.set("(目录无效)")

    def _suggest_ratio(self):
        """根据实际数据分布，自动建议均衡比例"""
        input_dir = self.input_var.get().strip()
        counts = _count_classes(input_dir)
        if not counts:
            messagebox.showwarning("警告", "无法扫描目录，请先选择有效的数据集目录。")
            return

        total = sum(counts.values())
        if total == 0:
            return

        min_cmd = min(counts, key=counts.get)
        min_count = counts[min_cmd]

        if min_count == 0:
            messagebox.showwarning("警告", f"类别 {min_cmd} 数量为0，无法计算比例。")
            return

        MAX_RATIO = 3
        ratios = {}
        for cmd in ("FW", "TL", "TR"):
            if counts[cmd] == 0:
                ratios[cmd] = 1
            else:
                raw = counts[cmd] / min_count
                ratios[cmd] = max(1, min(int(raw + 0.5), MAX_RATIO))

        self.balance_fw_var.set(ratios["FW"])
        self.balance_tl_var.set(ratios["TL"])
        self.balance_tr_var.set(ratios["TR"])

        self._bal_suggest_label.config(
            text=(f"(最少: {min_cmd}={min_count}, "
                  f"上限={MAX_RATIO}×)" if ratios[max(ratios, key=ratios.get)] == MAX_RATIO
                  else f"(基准: {min_cmd}={min_count})"))

    # ---- 标准化处理 ----
    def _on_process(self):
        input_dir = self.input_var.get().strip()
        output_dir = self.output_var.get().strip()

        if not input_dir or not os.path.isdir(input_dir):
            messagebox.showerror("错误", f"数据集目录不存在:\n{input_dir or '(空)'}")
            return

        if not output_dir:
            messagebox.showerror("错误", "无法确定 Tub 输出目录。")
            return

        # 输出目录覆盖确认
        if os.path.exists(output_dir):
            ok = messagebox.askyesno(
                "确认覆盖",
                f"输出目录已存在:\n{output_dir}\n\n是否删除并重新生成？"
            )
            if not ok:
                self.log("[*] 操作已取消。")
                return
            shutil.rmtree(output_dir)

        aug_config = {
            'brightness_contrast': {
                'enabled': self.bc_var.get(),
                'probability': self.bc_prob_var.get() / 100.0,
            },
            'gaussian_blur': {
                'enabled': self.blur_var.get(),
                'probability': self.blur_prob_var.get() / 100.0,
            },
        }
        replace_original = self.replace_var.get()

        # 构建均衡参数
        balance_ratio = None
        balance_mode = 'downsample'
        if self.balance_enabled_var.get():
            balance_ratio = {
                'FW': self.balance_fw_var.get(),
                'TL': self.balance_tl_var.get(),
                'TR': self.balance_tr_var.get(),
            }
            balance_mode = self.balance_mode_var.get()

        bc_cfg = aug_config['brightness_contrast']
        blur_cfg = aug_config['gaussian_blur']
        log_parts = [
            f"增强: 高斯模糊={'ON' if blur_cfg['enabled'] else 'OFF'}"
            f"({blur_cfg['probability']:.0%})",
            f"亮度对比度={'ON' if bc_cfg['enabled'] else 'OFF'}"
            f"({bc_cfg['probability']:.0%})",
            f"覆盖={'ON' if replace_original else 'OFF'}",
        ]
        if balance_ratio:
            log_parts.append(
                f"均衡: {balance_mode} FW:{balance_ratio['FW']}"
                f":TL:{balance_ratio['TL']}:TR:{balance_ratio['TR']}"
            )
        self.log(f"[处理] 启动 → " + ", ".join(log_parts))

        self.btn_process.config(state=tk.DISABLED)

        def worker():
            old_stdout = sys.stdout
            sys.stdout = LogRedirector(self, self.log)
            try:
                create_tub(input_dir, output_dir, aug_config,
                           replace_original=replace_original,
                           balance_ratio=balance_ratio,
                           balance_mode=balance_mode)
            except Exception as e:
                self.after(0, self.log, f"[-] 错误: {e}")
            finally:
                sys.stdout = old_stdout
                self.after(0, self._processing_done)

        threading.Thread(target=worker, daemon=True).start()

    def _processing_done(self):
        try:
            self.btn_process.config(state=tk.NORMAL)
            self.log("—" * 40)
        except tk.TclError:
            pass


# ==========================================
# 二级页面：数据合并
# ==========================================

class MergePage(tk.Toplevel, _LogMixin):
    """数据合并页面 — 多数据源按比例采样合并"""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("数据合并")
        self.geometry("620x540")
        self.minsize(520, 400)
        self.transient(parent)

        # ---- 数据源区 ----
        merge_frame = ttk.LabelFrame(self, text="数据源", padding=10)
        merge_frame.pack(fill=tk.X, padx=12, pady=(10, 8))

        # 数据源行容器
        self._sources_container = ttk.Frame(merge_frame)
        self._sources_container.pack(fill=tk.X)

        # 数据源行列表: 每项 (path_var, ratio_var, row_frame)
        self._sources = []
        self._add_source_row()
        self._add_source_row()

        # 添加数据源按钮
        add_src_btn = ttk.Button(
            merge_frame, text="+ 添加数据源",
            command=self._add_source_row
        )
        add_src_btn.pack(anchor=tk.W, pady=(4, 2))

        # ---- 目标目录 ----
        dest_frame = ttk.Frame(self)
        dest_frame.pack(fill=tk.X, padx=12, pady=(0, 4))

        dest_row = ttk.Frame(dest_frame)
        dest_row.pack(fill=tk.X, pady=2)
        ttk.Label(dest_row, text="目标目录:", width=14).pack(side=tk.LEFT)
        self._dest_var = tk.StringVar()
        ttk.Entry(dest_row, textvariable=self._dest_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(dest_row, text="浏览...", width=7,
                   command=self._browse_dest).pack(side=tk.RIGHT)

        # ---- 操作按钮 ----
        self.btn_merge = ttk.Button(
            self, text="合并数据集", width=16,
            command=self._on_merge
        )
        self.btn_merge.pack(pady=(6, 4))

        # ---- 日志 ----
        _, self._log_text = self._build_log_frame(self)
        self.log("就绪。设置数据源和目标目录后点击「合并数据集」。")

    # ---- 数据源行管理 ----
    def _add_source_row(self):
        """动态添加一行数据源输入控件"""
        path_var = tk.StringVar()
        ratio_var = tk.IntVar(value=100)

        row = ttk.Frame(self._sources_container)
        row.pack(fill=tk.X, pady=2)

        idx = len(self._sources) + 1
        ttk.Label(row, text=f"源{idx:02d}:", width=6).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=path_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        def browse(idx_local=idx - 1):
            path = filedialog.askdirectory(title=f"选择源{idx_local + 1:02d}目录")
            if path:
                self._sources[idx_local][0].set(os.path.normpath(path))

        ttk.Button(row, text="浏览", width=5, command=browse).pack(side=tk.LEFT)
        ttk.Label(row, text=" 比例").pack(side=tk.LEFT)
        ttk.Spinbox(row, from_=1, to=100, width=3,
                    textvariable=ratio_var).pack(side=tk.LEFT)
        ttk.Label(row, text="%").pack(side=tk.LEFT, padx=(0, 4))

        self._sources.append((path_var, ratio_var, row))

    def _browse_dest(self):
        """浏览选择合并目标目录"""
        path = filedialog.askdirectory(title="选择合并目标目录（不存在将自动创建）")
        if path:
            self._dest_var.set(os.path.normpath(path))

    # ---- 合并流程 ----
    def _on_merge(self):
        """执行数据集合并（后台线程）"""
        # 收集有效数据源
        src_map = {}
        seen = {}
        for i, (path_var, ratio_var, _) in enumerate(self._sources, 1):
            p = path_var.get().strip()
            if not p:
                continue
            p = os.path.normpath(p)
            try:
                ratio = ratio_var.get() / 100.0
            except tk.TclError:
                messagebox.showerror("错误", f"源{i:02d} 的比例不是有效数字。")
                return
            if p in seen:
                messagebox.showwarning(
                    "警告",
                    f"数据源被多次指定，将使用最后一次的比例:\n{p}"
                )
            seen[p] = True
            src_map[p] = ratio

        if not src_map:
            messagebox.showerror("错误", "请至少填写一个数据源路径。")
            return

        dest = self._dest_var.get().strip()
        if not dest:
            messagebox.showerror("错误", "请指定目标目录。")
            return

        # 校验源目录存在
        missing = [p for p in src_map if not os.path.isdir(p)]
        if missing:
            messagebox.showerror(
                "错误",
                "以下源目录不存在:\n" + "\n".join(f"  - {m}" for m in missing)
            )
            return

        # 目标目录非空提示
        if os.path.isdir(dest) and _glob.glob(os.path.join(dest, '*.jpg')):
            ok = messagebox.askyesno(
                "目标目录非空",
                f"目标目录已有文件:\n{dest}\n\n将继续合并（同名文件将跳过）。是否继续？"
            )
            if not ok:
                self.log("[*] 合并已取消。")
                return

        self.log(f"[合并] 启动 → {len(src_map)} 个数据源 → {dest}")

        self.btn_merge.config(state=tk.DISABLED)

        def worker():
            old_stdout = sys.stdout
            sys.stdout = LogRedirector(self, self.log)
            try:
                merge_datasets(src_map, dest)
            except Exception as e:
                self.after(0, self.log, f"[-] 错误: {e}")
            finally:
                sys.stdout = old_stdout
                self.after(0, self._merge_done)

        threading.Thread(target=worker, daemon=True).start()

    def _merge_done(self):
        """合并完成后恢复按钮"""
        try:
            self.btn_merge.config(state=tk.NORMAL)
            self.log("—" * 40)
        except tk.TclError:
            pass


# ==========================================
# 入口
# ==========================================

if __name__ == '__main__':
    app = DataLauncher()
    app.root.mainloop()
