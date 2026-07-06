#!/usr/bin/env python
# ==============================================================================
# 环境声明: Python 3.12
# 核心依赖: pip install Pillow; tkinter（Python 内置）
# 脚本身份: 自动驾驶数据快速人工审查与清洗工具 (Data Reviewer)
# 核心逻辑: 幻灯片式播放 FV+GV 双视图，一键标记垃圾，支持回退，批量软删除至垃圾箱
# ==============================================================================

import os
import glob
import shutil
import argparse
import tkinter as tk

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageTk


# ==========================================
# 默认路径（可通过 CLI 参数覆盖）
# ==========================================
DEFAULT_DATA_DIR = 'E:/autonomous_driving/datas_ot1'

# 显示常量
FV_DISPLAY_W = 640       # FV 显示宽度（等比例放大）
GV_DISPLAY_W = 640       # GV 显示区域固定宽度（防抖动）
BAR_H = 100              # 底部信息栏高度


# ==========================================
# 字体（跨平台兼容）
# ==========================================

def _get_font(size, bold=False):
    """获取 PIL 字体，Windows/macOS/Linux 均可回退"""
    fonts = []
    if bold:
        fonts = ['arialbd.ttf', 'Arial Bold.ttf', 'LiberationSans-Bold.ttf']
    else:
        fonts = ['arial.ttf', 'Arial.ttf', 'LiberationSans-Regular.ttf']

    for name in fonts:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    # 最终回退：PIL 默认位图字体（仅小字号可用）
    try:
        return ImageFont.truetype('C:/Windows/Fonts/arial.ttf', size)
    except (OSError, IOError):
        return ImageFont.load_default()


# ==========================================
# 文件名解析
# ==========================================

def parse_filename(filename):
    """从 FV 文件名中提取时间戳和驾驶指令

    期望格式: FV_<timestamp>_<COMMAND>.jpg
    返回: (timestamp, command) 或 (None, None)
    """
    base = os.path.splitext(filename)[0]
    parts = base.split('_')
    if len(parts) < 3 or parts[0] != 'FV':
        return None, None
    return parts[1], parts[-1]


# ==========================================
# 文件配对
# ==========================================

def build_review_list(data_dir):
    """扫描 datas 目录，构建 FV+GV 配对列表

    规则:
      - 以 FV 时间戳为基准排列展示
      - 匹配的 GV 随 FV 一起展示
      - GV-only 的时间戳直接忽略

    Returns:
        [(fv_path, command, gv_path_or_None), ...]  按时间戳升序排列
    """
    all_jpgs = sorted(glob.glob(os.path.join(data_dir, '*.jpg')))

    fv_map = {}   # timestamp → (path, command)
    gv_map = {}   # timestamp → path

    for p in all_jpgs:
        name = os.path.basename(p)
        if name.startswith('FV_'):
            ts, cmd = parse_filename(name)
            if ts:
                fv_map[ts] = (p, cmd)
        elif name.startswith('GV_'):
            # GV 格式: GV_<timestamp>_<CMD>_<X>_<Y>.jpg
            ts = name.split('_')[1]
            gv_map[ts] = p

    items = []
    for ts in sorted(fv_map.keys()):
        fv_path, cmd = fv_map[ts]
        items.append((fv_path, cmd, gv_map.get(ts)))

    return items


# ==========================================
# 图像渲染
# ==========================================

def _render_frame(fv_img, gv_img, is_marked, command,
                  current_idx, total, goto_buffer,
                  last_gv_img=None, gv_is_matched=True):
    """用 PIL 合成审核界面的完整帧

    Returns:
        PIL Image — FV+GV 并排 + 底部信息栏的合成图
    """
    # ---- 1. 缩放 FV 到显示宽度 ----
    fv_w, fv_h = fv_img.size
    scale = FV_DISPLAY_W / fv_w
    fv_display_h = int(fv_h * scale)
    fv = fv_img.resize((FV_DISPLAY_W, fv_display_h), Image.LANCZOS)

    # ---- 2. GV 区域：固定宽度 box，防切换抖动 ----
    gv_box_w = GV_DISPLAY_W
    gv_box_h = fv_display_h
    gv_box = Image.new('RGB', (gv_box_w, gv_box_h), (50, 50, 50))

    # 确定实际显示的 GV 图像
    display_gv = gv_img if gv_img is not None else last_gv_img

    if display_gv is not None:
        # 等比缩放 GV 使其适配固定 box（不裁切，居中显示）
        gv_orig_w, gv_orig_h = display_gv.size
        scale = min(gv_box_w / gv_orig_w, gv_box_h / gv_orig_h)
        gv_w = int(gv_orig_w * scale)
        gv_h = int(gv_orig_h * scale)
        gv_resized = display_gv.resize((gv_w, gv_h), Image.LANCZOS)
        offset_x = (gv_box_w - gv_w) // 2
        offset_y = (gv_box_h - gv_h) // 2
        gv_box.paste(gv_resized, (offset_x, offset_y))

    else:
        # 没有任何 GV 图像：纯灰底 + 提示文字
        draw_gv = ImageDraw.Draw(gv_box)
        font_ph = _get_font(18)
        ph_text = "无顶视图"
        bbox = draw_gv.textbbox((0, 0), ph_text, font=font_ph)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw_gv.text(((gv_box_w - tw) // 2, (gv_box_h - th) // 2),
                     ph_text, fill=(150, 150, 150), font=font_ph)

    # ---- 3. 并排拼接 FV + GV ----
    canvas_w = FV_DISPLAY_W + gv_box_w
    canvas_h = fv_display_h
    composite = Image.new('RGB', (canvas_w, canvas_h))
    composite.paste(fv, (0, 0))
    composite.paste(gv_box, (FV_DISPLAY_W, 0))

    # ---- 4. 绘制 FV 上的叠层（垃圾标记 / 指令标签） ----
    draw = ImageDraw.Draw(composite)

    if is_marked:
        # 红色半透明遮罩
        overlay = Image.new('RGBA', (FV_DISPLAY_W, fv_display_h),
                            (255, 0, 0, 77))
        composite.paste(overlay, (0, 0), overlay)

        font_mark = _get_font(32, bold=True)
        mark_text = "MARKED FOR TRASH"
        bbox = draw.textbbox((0, 0), mark_text, font=font_mark)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((FV_DISPLAY_W - tw) // 2, (fv_display_h - th) // 2 - 30),
                  mark_text, fill=(255, 0, 0), font=font_mark, stroke_width=2,
                  stroke_fill=(0, 0, 0))
    else:
        # 指令标签
        cmd_colors = {
            'FW': (0, 255, 0),
            'TR': (255, 200, 0),
            'TL': (0, 255, 255),
        }
        color = cmd_colors.get(command, (255, 255, 255))
        font_cmd = _get_font(42, bold=True)
        cmd_text = f"Cmd: {command}"
        bbox = draw.textbbox((0, 0), cmd_text, font=font_cmd)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((FV_DISPLAY_W - tw) // 2, (fv_display_h - th) // 2),
                  cmd_text, fill=color, font=font_cmd, stroke_width=3,
                  stroke_fill=(0, 0, 0))

    # ---- 5. 底部信息栏 ----
    bar_img = Image.new('RGB', (canvas_w, BAR_H), (32, 32, 32))
    draw_bar = ImageDraw.Draw(bar_img)

    # 顶部分隔亮线
    draw_bar.line([(0, 0), (canvas_w, 0)], fill=(100, 100, 100), width=2)

    font_small = _get_font(15)
    font_tip = _get_font(13)

    # 第一行：进度 + 跳转缓冲（左） / GV 状态（右）
    progress_text = f"[{current_idx + 1} / {total}]"
    if goto_buffer:
        progress_text += f"  Goto: {goto_buffer}_"
    draw_bar.text((16, 10), progress_text, fill=(255, 255, 255), font=font_small)

    # GV 状态指示（右对齐）
    if gv_img is not None:
        gv_status = "● GV 匹配"
        gv_status_color = (100, 255, 100)
    elif last_gv_img is not None:
        gv_status = "○ GV 缓存"
        gv_status_color = (255, 200, 80)
    else:
        gv_status = "✕ 无 GV"
        gv_status_color = (255, 100, 100)
    bbox = draw_bar.textbbox((0, 0), gv_status, font=font_small)
    sw = bbox[2] - bbox[0]
    draw_bar.text((canvas_w - sw - 16, 10), gv_status, fill=gv_status_color,
                  font=font_small)

    # 第二行：常用操作
    draw_bar.text((16, 38), "Space / D: Next    A: Prev    X: Trash",
                  fill=(220, 220, 220), font=font_tip)

    # 第三行：跳转和退出
    draw_bar.text((16, 62), "0-9 + Enter: Jump    Q / Esc: Quit",
                  fill=(220, 220, 220), font=font_tip)

    # ---- 6. 垂直拼接 ----
    final = Image.new('RGB', (canvas_w, canvas_h + BAR_H))
    final.paste(composite, (0, 0))
    final.paste(bar_img, (0, canvas_h))

    return final


# ==========================================
# tkinter 审核窗口
# ==========================================

class ReviewerWindow:
    """tkinter 审核窗口，替代原 OpenCV imshow 交互"""

    def __init__(self, display_items, trash_dir,
                 confirm_callback=None, master=None):
        """创建审核窗口并进入主循环（阻塞调用方）

        Args:
            display_items:    [(fv_path, command, gv_path_or_None), ...]
            trash_dir:        垃圾箱目录
            confirm_callback: 确认回调，或 None 使用终端 input()
            master:           可选的父 tk 组件（嵌入 data_launcher 时用）
        """
        self.display_items = display_items
        self.total = len(display_items)
        self.trash_dir = trash_dir
        self.confirm_callback = confirm_callback

        self.idx = 0
        self.goto_buffer = ""
        self.marked = set()            # 存储 fv_path（绝对路径）
        self._cached_frame = None      # 当前帧的 PIL Image 缓存
        self._tk_image = None          # ImageTk.PhotoImage 引用
        self._last_gv_image = None     # 上一帧 GV（用于无 GV 帧的残影过渡）

        # 构建窗口：有 master 时用 Toplevel，独立运行时自己创 Tk
        if master is not None:
            self._own_root = False
            self.root = tk.Toplevel(master)
        else:
            self._own_root = True
            self.root = tk.Tk()
        self.root.resizable(False, False)  # 固定窗口大小，防抖动
        self.root.title("数据审核 — Data Reviewer")
        self.root.bind('<Key>', self._on_key)
        self.root.protocol("WM_DELETE_WINDOW", self._on_quit)

        # 图片显示 Label
        self.label = tk.Label(self.root, bg='black')
        self.label.pack()

        # 首次渲染
        self._show_current()
        self.root.mainloop()

    # ---- 显示 ----

    def _show_current(self):
        """加载当前 FV+GV 并合成显示"""
        fv_path, command, gv_path = self.display_items[self.idx]

        try:
            fv_img = Image.open(fv_path)
            fv_img.load()
            if fv_img.mode != 'RGB':
                fv_img = fv_img.convert('RGB')
        except Exception:
            # 损坏图片，跳过
            if self.idx < self.total - 1:
                self.idx += 1
                self._show_current()
            return

        gv_img = None
        if gv_path:
            try:
                gv_img = Image.open(gv_path)
                gv_img.load()
                if gv_img.mode != 'RGB':
                    gv_img = gv_img.convert('RGB')
                self._last_gv_image = gv_img.copy()  # 为后续无 GV 帧保留残影
            except Exception:
                gv_img = None

        is_marked = fv_path in self.marked

        self._cached_frame = _render_frame(
            fv_img, gv_img, is_marked, command,
            self.idx, self.total, self.goto_buffer,
            self._last_gv_image, gv_is_matched=(gv_img is not None)
        )

        self._tk_image = ImageTk.PhotoImage(self._cached_frame)
        self.label.config(image=self._tk_image)

        # 更新窗口标题
        fname = os.path.basename(fv_path)
        status = " [TRASH]" if is_marked else ""
        self.root.title(f"[{self.idx + 1}/{self.total}] {fname}{status}")

    # ---- 键盘事件 ----

    def _on_key(self, event):
        """键盘事件分发"""
        key = event.keysym
        char = event.char

        # 数字键 → 跳转缓冲区
        if char and '0' <= char <= '9':
            self.goto_buffer += char
            self._show_current()
            return

        # 回车 → 执行跳转
        if key == 'Return':
            if self.goto_buffer:
                target = int(self.goto_buffer)
                self.idx = max(0, min(target - 1, self.total - 1))
            self.goto_buffer = ""
            self._show_current()
            return

        # 退格
        if key == 'BackSpace':
            self.goto_buffer = self.goto_buffer[:-1]
            self._show_current()
            return

        # 空格 / D / Right → 下一张
        if key in ('space', 'd', 'Right'):
            self.goto_buffer = ""
            if self.idx < self.total - 1:
                self.idx += 1
            self._show_current()
            return

        # A / Left → 上一张
        if key in ('a', 'Left'):
            self.goto_buffer = ""
            self.idx = max(0, self.idx - 1)
            self._show_current()
            return

        # X → 标记/取消垃圾
        if key == 'x':
            self.goto_buffer = ""
            fv_path = self.display_items[self.idx][0]
            if fv_path in self.marked:
                self.marked.remove(fv_path)
                self._show_current()
            else:
                self.marked.add(fv_path)
                if self.idx < self.total - 1:
                    self.idx += 1
                self._show_current()
            return

        # Q / Escape → 退出
        if key in ('q', 'Escape'):
            self._on_quit()
            return

    # ---- 退出 ----

    def _on_quit(self):
        """退出审核，执行结算与清理"""
        self.root.destroy()
        self._settle()

    def _settle(self):
        """结算：移动标记的垃圾图片到 trash 目录"""
        trash_count = len(self.marked)

        print("\n" + "=" * 50)
        print(" 审查结束结算")
        print("=" * 50)

        if trash_count == 0:
            print("[*] 你没有标记任何垃圾图片，直接退出。")
            return

        print(f"[!] 你一共标记了 {trash_count} 张垃圾图片。")

        # 获取对应路径（FV + 匹配的 GV 一并删除）
        all_trash_paths = []
        for fv_path in self.marked:
            all_trash_paths.append(fv_path)
            # 同时查找匹配的 GV
            fv_name = os.path.basename(fv_path)
            ts, _ = parse_filename(fv_name)
            if ts:
                gv_pattern = f"GV_{ts}_*.jpg"
                data_dir = os.path.dirname(fv_path)
                for gp in glob.glob(os.path.join(data_dir, gv_pattern)):
                    if gp not in all_trash_paths:
                        all_trash_paths.append(gp)

        if self.confirm_callback is not None:
            confirmed = self.confirm_callback(
                len(all_trash_paths), self.trash_dir)
        else:
            answer = input(
                f"是否将它们移动到 {self.trash_dir} 文件夹？(y/n): ")
            confirmed = answer.lower() == 'y'

        if not os.path.exists(self.trash_dir):
            os.makedirs(self.trash_dir)

        if confirmed:
            print("[*] 正在转移废弃数据...")
            moved = 0
            for file_path in all_trash_paths:
                try:
                    dest = os.path.join(self.trash_dir,
                                        os.path.basename(file_path))
                    shutil.move(file_path, dest)
                    moved += 1
                except Exception as e:
                    print(f"[-] 转移失败 {file_path}: {e}")
            print(f"✅ 清理完成！共移动 {moved} 个文件到垃圾箱。")
        else:
            print("[*] 操作已取消，图片未被移动。")


# ==========================================
# 工具函数
# ==========================================

def setup_trash(trash_dir):
    """确保垃圾箱目录存在"""
    if not os.path.exists(trash_dir):
        os.makedirs(trash_dir)


# ==========================================
# 主入口（模块级 API）
# ==========================================

def run_reviewer(raw_data_dir, trash_dir, confirm_callback=None, master=None):
    """主流程：逐帧审查 FV+GV 双视图，标记垃圾并软删除

    Args:
        raw_data_dir:    原始图片所在目录
        trash_dir:       垃圾箱目录（标记删除的图片会移到这里）
        confirm_callback: 可选，确认回调函数，
                          签名: (trash_count, trash_dir) -> bool
                          返回 True 表示确认移动。为 None 时使用终端 input()。
        master:           可选的父 tk 组件（嵌入 data_launcher 时传入）
    """
    setup_trash(trash_dir)

    # 构建 FV+GV 配对列表
    display_items = build_review_list(raw_data_dir)
    total_items = len(display_items)

    if total_items == 0:
        print(f"[-] 在 {raw_data_dir} 中没有找到 FV_ 图片，请检查路径。")
        return

    # 统计 GV 匹配情况
    gv_matched = sum(1 for (_, _, gv) in display_items if gv is not None)
    print(f"[*] 成功加载 {total_items} 张 FV 图片"
          + (f"（{gv_matched} 张有匹配 GV）"
             if gv_matched > 0 else "，无 GV 匹配"))
    print(f"[*] 垃圾箱: {trash_dir}")
    print("[*] 请在弹出的审核窗口中进行操作。")

    # 启动 tkinter 审核窗口（阻塞至窗口关闭）
    ReviewerWindow(display_items, trash_dir, confirm_callback, master)


# ==========================================
# CLI 入口
# ==========================================

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='自动驾驶数据快速人工审查与清洗工具 (Data Reviewer)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python data_reviewer.py
  python data_reviewer.py E:/autonomous_driving/datas_ot1
  python data_reviewer.py E:/autonomous_driving/datas_ot1 -t E:/autonomous_driving/trash
  python data_reviewer.py user/clockwise-v1/datas
  python data_reviewer.py user/clockwise-v1/datas -t user/custom_trash
        """
    )

    parser.add_argument(
        'input_dir', nargs='?', default=DEFAULT_DATA_DIR,
        help=f'原始图片所在目录 (默认: {DEFAULT_DATA_DIR})'
    )
    parser.add_argument(
        '--trash', '-t', default=None,
        help='垃圾箱目录 (默认: 数据集同级目录下的 trash/)'
    )

    args = parser.parse_args()

    # 自动计算默认垃圾箱路径：与数据集同级的 trash/ 目录
    trash_dir = args.trash
    if trash_dir is None:
        input_abs = os.path.abspath(args.input_dir)
        trash_dir = os.path.join(os.path.dirname(input_abs), 'trash')

    run_reviewer(args.input_dir, trash_dir)
