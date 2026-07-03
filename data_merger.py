#!/usr/bin/env python
# ==============================================================================
# 环境声明: Python 3.12
# 核心依赖: 无外部依赖（仅 Python 标准库）
# 脚本身份: 自动驾驶数据集合并工具 (Data Merger)
# 核心逻辑: 多源 datas 目录 → 按比例随机采样 → 复制合并到一个目标 datas
# ==============================================================================

import os
import glob
import shutil
import random
import argparse


# ==========================================
# 核心函数
# ==========================================

def merge_datasets(src_map, output_dir):
    """将多个数据源按比例合并到目标目录

    Args:
        src_map:    dict，{源目录路径: 采样比例}
                    比例范围 0.0 ~ 1.0，如 {"user/none/datas": 0.6, "user/barrier/datas": 1.0}
        output_dir: 目标目录路径，不存在则自动创建

    Returns:
        bool: True 表示成功，False 表示失败
    """

    # ---- 1. 参数校验 ----
    if not src_map:
        print("[-] 错误: 至少需要指定一个数据源")
        return False

    for src_dir, ratio in src_map.items():
        if not os.path.isdir(src_dir):
            print(f"[-] 错误: 源目录不存在 → '{src_dir}'")
            return False
        if not (0.0 <= ratio <= 1.0):
            print(f"[-] 错误: 比例须在 0.0~1.0 之间 → '{src_dir}' 的比例为 {ratio}")
            return False

    output_dir = os.path.normpath(output_dir)

    # ---- 2. 创建输出目录 ----
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"[*] 已创建输出目录: '{output_dir}'")
    else:
        existing_files = glob.glob(os.path.join(output_dir, '*.jpg'))
        if existing_files:
            print(f"[!] 警告: 输出目录已有 {len(existing_files)} 张图片，将跳过同名文件")

    # ---- 3. 扫描 & 采样 & 复制 ----
    total_selected = 0
    total_available = 0
    total_skipped = 0
    summary_lines = []

    # 记录已存在的文件名，用于去重
    existing_names = set()
    for f in glob.glob(os.path.join(output_dir, '*.jpg')):
        existing_names.add(os.path.basename(f))

    for src_dir, ratio in src_map.items():
        all_files = sorted(glob.glob(os.path.join(src_dir, '*.jpg')))
        n_total = len(all_files)

        if n_total == 0:
            print(f"[!] 警告: '{src_dir}' 中没有 .jpg 文件，跳过")
            continue

        # 采样
        if ratio <= 0.0:
            selected = []
        elif ratio >= 1.0:
            selected = all_files
        else:
            n_select = max(1, int(n_total * ratio))
            selected = random.sample(all_files, n_select)

        # 复制
        copied = 0
        skipped = 0
        for src_path in selected:
            filename = os.path.basename(src_path)
            if filename in existing_names:
                print(f"  [~] 跳过重复: {filename} (来自 {os.path.basename(src_dir)})")
                skipped += 1
                continue
            try:
                shutil.copy2(src_path, os.path.join(output_dir, filename))
                existing_names.add(filename)
                copied += 1
            except OSError as e:
                print(f"  [-] 复制失败: {filename}: {e}")
                skipped += 1

        # 源目录简称
        src_label = os.path.basename(src_dir)

        summary_lines.append(
            f"  {src_label} → 取 {copied}/{n_total} ({ratio:.0%})"
            + (f", 跳过 {skipped}" if skipped > 0 else "")
        )
        total_selected += len(selected)
        total_available += n_total
        total_skipped += skipped

        print(f"[*] '{src_label}': {len(selected)}/{n_total} 选中"
              + (f" ({skipped} 跳过重复)" if skipped > 0 else ""))

    # ---- 4. 打印摘要 ----
    final_count = len(glob.glob(os.path.join(output_dir, '*.jpg')))
    print()
    print("=" * 50)
    print(" 数据集合并完成")
    print("=" * 50)
    for line in summary_lines:
        print(line)
    if total_skipped > 0:
        print(f"  跳过重复: {total_skipped}")
    print(f"  合并总数: {final_count}")
    print(f"  输出目录: {output_dir}")
    print("=" * 50)

    return True


# ==========================================
# CLI 入口
# ==========================================

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='自动驾驶数据集合并工具 (Data Merger)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python data_merger.py --src user/clockwise_none/datas:0.6 --src user/clockwise_barrier/datas:1.0 -o user/combined/datas
  python data_merger.py --src E:/data/datas_ot1:0.5 -o E:/data/datas_sampled
        """
    )

    parser.add_argument(
        '--src', action='append', required=True,
        metavar='PATH:RATIO',
        help='源目录:采样比例（可重复多次）。比例范围 0.0~1.0'
    )
    parser.add_argument(
        '-o', '--output', required=True,
        metavar='PATH',
        help='目标目录（必填，不存在则自动创建）'
    )

    args = parser.parse_args()

    # 解析 --src 参数为 src_map
    src_map = {}
    parse_errors = []
    for item in args.src:
        if ':' not in item:
            parse_errors.append(f"格式错误（缺少冒号）: '{item}'")
            continue
        path, ratio_str = item.rsplit(':', 1)
        path = path.strip()
        if not path:
            parse_errors.append(f"路径为空: '{item}'")
            continue
        try:
            ratio = float(ratio_str.strip())
        except ValueError:
            parse_errors.append(f"比例不是数字: '{item}'")
            continue
        if path in src_map:
            print(f"[!] 警告: 重复指定源目录，后面的覆盖前面的: '{path}'")
        src_map[path] = ratio

    if parse_errors:
        print("[-] 参数解析错误:")
        for e in parse_errors:
            print(f"    {e}")
        exit(1)

    success = merge_datasets(src_map, args.output)
    exit(0 if success else 1)
