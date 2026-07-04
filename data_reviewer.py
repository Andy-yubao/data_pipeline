# ==============================================================================
# 环境声明: Python 3.12
# 核心依赖: pip install opencv-python
# 脚本身份: 自动驾驶数据快速人工审查与清洗工具 (Data Reviewer)
# 核心逻辑: 幻灯片式播放，一键标记垃圾数据，支持回退，最终批量软删除至垃圾箱
# ==============================================================================

import os
import cv2
import numpy
import glob
import shutil
import argparse

# ==========================================
# 默认路径（可通过 CLI 参数覆盖）
# ==========================================
DEFAULT_DATA_DIR = 'E:/autonomous_driving/datas_ot1'


def setup_trash(trash_dir):
    """确保垃圾箱目录存在"""
    if not os.path.exists(trash_dir):
        os.makedirs(trash_dir)


def draw_overlay(img, filename, current_idx, total, is_marked, goto_buffer=""):
    """在放大后的图片上绘制UI信息，并在下方添加独立信息栏

    原始图像为 180×320，直接显示过小。本函数先放大到适合屏幕的尺寸，
    再绘制指令标签和信息栏，确保所有文字清晰可读。
    """
    # ---- 0. 放大图像到适合显示的尺寸 ----
    DISPLAY_W = 640  # 显示宽度
    h_orig, w_orig = img.shape[:2]
    scale = DISPLAY_W / w_orig
    DISPLAY_H = int(h_orig * scale)
    img = cv2.resize(img, (DISPLAY_W, DISPLAY_H), interpolation=cv2.INTER_NEAREST)
    h, w = DISPLAY_H, DISPLAY_W

    # ---- 1. 提取标签 ----
    try:
        command = filename.split('_')[-1].split('.')[0]
    except Exception:
        command = "UNKNOWN"

    if command == 'FW':
        cmd_color = (0, 255, 0)
    elif command == 'TR':
        cmd_color = (255, 255, 0)
    elif command == 'TL':
        cmd_color = (0, 255, 255)
    else:
        cmd_color = (255, 255, 255)

    # ---- 2. 绘制图像区域叠层（垃圾标记 / 指令标签） ----
    if is_marked:
        overlay = img.copy()
        cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 255), -1)
        img = cv2.addWeighted(overlay, 0.3, img, 0.7, 0)
        cv2.putText(img, "MARKED FOR TRASH", (w // 2 - 220, h // 2 - 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 255), 3)
    else:
        cv2.putText(img, f"Cmd: {command}", (w // 2 - 130, h // 2 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 2.0, cmd_color, 4)

    # ---- 3. 构建独立信息栏（三行布局，防止文字溢出） ----
    BAR_H = 82
    bar = numpy.full((BAR_H, w, 3), 32, dtype=numpy.uint8)

    # 顶部分隔亮线
    cv2.line(bar, (0, 0), (w, 0), (100, 100, 100), 2)

    # 第一行：进度 + 跳转缓冲
    progress_text = f"[{current_idx + 1} / {total}]"
    if goto_buffer:
        progress_text += f"  Goto: {goto_buffer}_"
    cv2.putText(bar, progress_text, (16, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)

    # 第二行：常用审核操作
    cv2.putText(bar, "Space / D: Next    A: Prev    X: Trash",
                (16, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (230, 230, 230), 1, cv2.LINE_AA)

    # 第三行：跳转和退出
    cv2.putText(bar, "0-9 + Enter: Jump    Q / Esc: Quit",
                (16, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (230, 230, 230), 1, cv2.LINE_AA)

    # ---- 4. 垂直拼接 ----
    return numpy.vstack((img, bar))


def run_reviewer(raw_data_dir, trash_dir, confirm_callback=None):
    """主流程：逐帧审查图片，标记垃圾并软删除

    Args:
        raw_data_dir:    原始图片所在目录
        trash_dir:       垃圾箱目录（标记删除的图片会移到这里）
        confirm_callback: 可选，确认回调函数，签名: (trash_count, trash_dir) -> bool
                          返回 True 表示确认移动。为 None 时使用终端 input()。
    """
    setup_trash(trash_dir)

    # 获取所有图片，并按文件名（包含时间戳）强制排序，确保画面播放是连贯的视频流
    image_paths = sorted(glob.glob(os.path.join(raw_data_dir, '*.jpg')))
    total_images = len(image_paths)

    if total_images == 0:
        print(f"[-] 在 {raw_data_dir} 中没有找到图片，请检查路径。")
        return

    print(f"[*] 成功加载 {total_images} 张图片。")
    print(f"[*] 垃圾箱: {trash_dir}")
    print("[*] 请在弹出的图像窗口中进行操作。")

    # 使用一个 Set 集合来存储被用户标记为垃圾的图片路径
    marked_for_deletion = set()

    idx = 0
    goto_buffer = ""  # 跳转数字输入缓冲区
    # 创建一个命名窗口，允许自由缩放大小
    cv2.namedWindow('Data Reviewer', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Data Reviewer', 700, 500)  # 默认弹窗大小

    while idx < total_images:
        img_path = image_paths[idx]
        filename = os.path.basename(img_path)

        # 读取图片
        img = cv2.imread(img_path)
        if img is None:
            idx += 1
            continue

        # 检查当前图片是否已经被标记为垃圾
        is_marked = img_path in marked_for_deletion

        # 绘制 UI 界面
        display_img = draw_overlay(img, filename, idx, total_images, is_marked, goto_buffer)
        cv2.imshow('Data Reviewer', display_img)

        # 等待键盘输入（100ms 超时轮询，以便检测窗口 X 按钮关闭）
        key = cv2.waitKey(100) & 0xFF

        # 检测窗口是否被用户点击 X 关闭 → 等同于按 Q 退出
        if cv2.getWindowProperty('Data Reviewer', cv2.WND_PROP_VISIBLE) < 1:
            break

        # 无按键，继续等待
        if key == 255:
            continue

        # ---- 数字键入：累积到跳转缓冲区 ----
        if ord('0') <= key <= ord('9'):
            goto_buffer += chr(key)

        # ---- 回车：执行跳转 ----
        elif key == 13:  # Enter
            if goto_buffer:
                target = int(goto_buffer)
                idx = max(0, min(target - 1, total_images - 1))
            goto_buffer = ""

        # ---- 退格：删除最后一位 ----
        elif key == 8:  # Backspace
            goto_buffer = goto_buffer[:-1]

        # ---- 按下 D 或 空格键：认为图片没问题，播放下一张 ----
        elif key == ord(' ') or key == ord('d'):
            goto_buffer = ""
            idx += 1

        # ---- 按下 A 键：手滑了，返回上一张图片重新看 ----
        elif key == ord('a'):
            goto_buffer = ""
            idx = max(0, idx - 1)

        # ---- 按下 X 键：标记或取消标记垃圾 ----
        elif key == ord('x'):
            goto_buffer = ""
            if is_marked:
                # 如果已经标记了，再次按 X 则是"撤销标记"，并停留在当前页让你确认
                marked_for_deletion.remove(img_path)
            else:
                # 如果没标记，按 X 标记为垃圾，并【自动跳到下一张】，保证极速盲筛体验
                marked_for_deletion.add(img_path)
                idx += 1

        # ---- 按下 Q 或 ESC 键：退出审查并执行清理 ----
        elif key == ord('q') or key == 27:
            break

    cv2.destroyAllWindows()

    # ==========================================
    # 结算与执行清理
    # ==========================================
    trash_count = len(marked_for_deletion)
    print("\n" + "=" * 50)
    print(" 审查结束结算")
    print("=" * 50)
    if trash_count == 0:
        print("[*] 你没有标记任何垃圾图片，直接退出。")
        return

    print(f"[!] 你一共标记了 {trash_count} 张垃圾图片。")

    if confirm_callback is not None:
        confirmed = confirm_callback(trash_count, trash_dir)
    else:
        answer = input(f"是否将它们移动到 {trash_dir} 文件夹？(y/n): ")
        confirmed = answer.lower() == 'y'

    if confirmed:
        print("[*] 正在转移废弃数据...")
        for file_path in marked_for_deletion:
            try:
                filename = os.path.basename(file_path)
                dest_path = os.path.join(trash_dir, filename)
                shutil.move(file_path, dest_path)
            except Exception as e:
                print(f"[-] 转移失败 {file_path}: {e}")
        print("✅ 清理完成！你的 raw_images 文件夹现在非常干净了。")
    else:
        print("[*] 操作已取消，图片未被移动。")


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
