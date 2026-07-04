# 数据集合并工具 (data_merger) 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 开发 `data_merger.py`，支持多源数据集按比例随机采样合并到目标目录，并在 GUI 面板中集成。

**Architecture:** 新增 `data_merger.py` 独立模块，提供 `merge_datasets()` 核心函数；修改 `data_launcher.py` 新增「数据集合并」GUI 区域。CLI 和 GUI 共用 `merge_datasets()` 入口。

**Tech Stack:** Python 3.12, `shutil`, `glob`, `random`, `argparse`, `tkinter`（内置）

---

## 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| 创建 | `data_merger.py` | 核心合并逻辑 + CLI 入口 |
| 修改 | `data_launcher.py` | GUI 中新增数据集合并区域 |
| 修改 | `README.md` | 文档更新 |

---

### Task 1: 创建 data_merger.py — 核心模块

**Files:**
- Create: `E:\study\AutoCar\data_pipeline\data_merger.py`

- [ ] **Step 1: 创建 data_merger.py 完整文件**

```python
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
        src_dir = os.path.normpath(src_dir)
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
        src_dir = os.path.normpath(src_dir)
        all_files = sorted(glob.glob(os.path.join(src_dir, '*.jpg')))
        n_total = len(all_files)

        if n_total == 0:
            print(f"[!] 警告: '{src_dir}' 中没有 .jpg 文件，跳过")
            continue

        # 采样
        if ratio >= 1.0:
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
                print(f"  [~] 跳过重复: {filename} (来自 {os.path.basename(os.path.dirname(src_dir))}/{os.path.basename(src_dir)})")
                skipped += 1
                continue
            shutil.copy2(src_path, os.path.join(output_dir, filename))
            existing_names.add(filename)
            copied += 1

        # 源目录简称
        src_label = os.path.basename(os.path.dirname(src_dir))
        if not src_label or src_label == '.':
            src_label = os.path.basename(src_dir)

        summary_lines.append(
            f"  {src_label} → 取 {len(selected)}/{n_total} ({ratio:.0%})"
            + (f", 跳过重复 {skipped}" if skipped > 0 else "")
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
```

- [ ] **Step 2: 验证 CLI 基本用法**

```bash
cd E:/study/AutoCar/data_pipeline
python data_merger.py --help
```

Expected: 显示帮助信息，包含 `--src` 和 `-o` 参数说明。

- [ ] **Step 3: 测试单源合并**

```bash
cd E:/study/AutoCar/data_pipeline
python data_merger.py --src ../user/clockwise_none/datas:0.1 -o ../user/test_merger_single
```

Expected: 从 4958 张中随机抽约 496 张复制到 test_merger_single，打印统计摘要。

- [ ] **Step 4: 测试多源合并**

```bash
cd E:/study/AutoCar/data_pipeline
python data_merger.py --src ../user/clockwise_none/datas:0.05 --src ../user/clockwise_barrier/datas:0.05 -o ../user/test_merger_multi
```

Expected: 两个源各 5% 合并，打印两个源各自的统计。

- [ ] **Step 5: 清理测试目录**

```bash
rm -rf E:/study/AutoCar/user/test_merger_single E:/study/AutoCar/user/test_merger_multi
```

- [ ] **Step 6: Commit**

```bash
cd E:/study/AutoCar/data_pipeline
git add data_merger.py
git commit -m "feat: 新增 data_merger.py 数据集合并模块"
```

---

### Task 2: 修改 data_launcher.py — 添加 GUI 合并面板

**Files:**
- Modify: `E:\study\AutoCar\data_pipeline\data_launcher.py`

- [ ] **Step 1: 添加 import**

在 `from data_processor import create_tub` 之后添加一行：

```python
from data_merger import merge_datasets
```

修改位置: `data_launcher.py:19`

Edit: 在 `from data_processor import create_tub` 之后插入新 import 行。

- [ ] **Step 2: 在 action_frame 之前添加合并面板**

在 `# ---- 增强选项 + 操作按钮 ----` 这一行（当前第 95 行）**之前**，插入以下代码：

```python
        # ---- 数据集合并区 ----
        merge_frame = ttk.LabelFrame(self.root, text="数据集合并", padding=10)
        merge_frame.pack(fill=tk.X, padx=12, pady=(4, 8))

        # 数据源行容器
        self.merge_sources_container = ttk.Frame(merge_frame)
        self.merge_sources_container.pack(fill=tk.X)

        # 数据源行列表: 每项 (path_var, ratio_var, row_frame)
        self.merge_sources = []
        self._add_merge_source_row()
        self._add_merge_source_row()

        # 添加数据源按钮
        add_src_btn = ttk.Button(
            merge_frame, text="+ 添加数据源",
            command=self._add_merge_source_row
        )
        add_src_btn.pack(anchor=tk.W, pady=(4, 6))

        # 目标目录行
        dest_row = ttk.Frame(merge_frame)
        dest_row.pack(fill=tk.X, pady=2)
        ttk.Label(dest_row, text="目标目录:", width=14).pack(side=tk.LEFT)
        self.merge_dest_var = tk.StringVar()
        ttk.Entry(dest_row, textvariable=self.merge_dest_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(dest_row, text="浏览...", width=7,
                   command=self._browse_merge_dest).pack(side=tk.RIGHT)

        # 合并按钮
        self.btn_merge = ttk.Button(
            merge_frame, text="合并数据集", width=14,
            command=self.on_merge
        )
        self.btn_merge.pack(pady=(6, 0))
```

- [ ] **Step 3: 在 DataLauncher 类中添加数据集合并相关方法**

在 `_processing_done` 方法之后（`class DataLauncher` 内部末尾），添加以下方法：

```python
    # ---- 数据集合并 ----
    def _add_merge_source_row(self):
        """动态添加一行数据源输入控件"""
        path_var = tk.StringVar()
        ratio_var = tk.IntVar(value=100)

        row = ttk.Frame(self.merge_sources_container)
        row.pack(fill=tk.X, pady=2)

        idx = len(self.merge_sources) + 1
        ttk.Label(row, text=f"源{idx:02d}:", width=6).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=path_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        def browse(idx_local=idx - 1):
            path = filedialog.askdirectory(title=f"选择源{idx_local + 1:02d}目录")
            if path:
                self.merge_sources[idx_local][0].set(os.path.normpath(path))

        ttk.Button(row, text="浏览", width=5, command=browse).pack(side=tk.LEFT)
        ttk.Label(row, text=" 比例").pack(side=tk.LEFT)
        ttk.Spinbox(row, from_=1, to=100, width=3,
                    textvariable=ratio_var).pack(side=tk.LEFT)
        ttk.Label(row, text="%").pack(side=tk.LEFT, padx=(0, 4))

        self.merge_sources.append((path_var, ratio_var, row))

    def _browse_merge_dest(self):
        """浏览选择合并目标目录"""
        path = filedialog.askdirectory(title="选择合并目标目录（不存在将自动创建）")
        if path:
            self.merge_dest_var.set(os.path.normpath(path))

    def on_merge(self):
        """执行数据集合并（后台线程）"""
        # 收集有效数据源
        src_map = {}
        for path_var, ratio_var, _ in self.merge_sources:
            p = path_var.get().strip()
            if not p:
                continue
            p = os.path.normpath(p)
            ratio = ratio_var.get() / 100.0
            src_map[p] = ratio

        if not src_map:
            messagebox.showerror("错误", "请至少填写一个数据源路径。")
            return

        dest = self.merge_dest_var.get().strip()
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

        self.log(f"[合并] 启动 → {len(src_map)} 个数据源 → {dest}")

        self.btn_review.config(state=tk.DISABLED)
        self.btn_process.config(state=tk.DISABLED)
        self.btn_merge.config(state=tk.DISABLED)

        def worker():
            old_stdout = sys.stdout
            sys.stdout = LogRedirector(self.root, self.log)
            try:
                merge_datasets(src_map, dest)
            except Exception as e:
                self.root.after(0, self.log, f"[-] 错误: {e}")
            finally:
                sys.stdout = old_stdout
                self.root.after(0, self._merge_done)

        threading.Thread(target=worker, daemon=True).start()

    def _merge_done(self):
        """合并完成后恢复按钮"""
        self.btn_review.config(state=tk.NORMAL)
        self.btn_process.config(state=tk.NORMAL)
        self.btn_merge.config(state=tk.NORMAL)
        self.log("—" * 40)
```

- [ ] **Step 4: 调整窗口大小**

找到 `self.root.geometry("700x550")` 行（约第 51 行），改为更大的窗口以适应新增内容：

```python
self.root.geometry("700x750")
```

Edit: 将 `"700x550"` 替换为 `"700x750"`。

- [ ] **Step 5: 验证 GUI 启动**

```bash
cd E:/study/AutoCar/data_pipeline
python data_launcher.py
```

Expected: 窗口正常显示，能看到新增的「数据集合并」区域（默认两行数据源），滚动条可看到日志区。

手动测试：检查所有按钮（审核清洗、标准化处理、合并数据集）可点击，添加数据源按钮可动态追加行。

- [ ] **Step 6: Commit**

```bash
cd E:/study/AutoCar/data_pipeline
git add data_launcher.py
git commit -m "feat: GUI面板新增数据集合并功能区"
```

---

### Task 3: 更新 README.md

**Files:**
- Modify: `E:\study\AutoCar\data_pipeline\README.md`

- [ ] **Step 1: 概述表格中新增 data_merger 行**

在 README.md 约第 40-44 行的表格中，添加一行：

```
| 合并 | `data_merger` | 多个 datas 目录 | 按比例随机采样合并 | 第三个环节 |
```

Edit: 在 `| 标准化增强 |` 和 `| GUI 面板 |` 之间插入。

- [ ] **Step 2: 架构图新增合并节点**

在 README.md 约第 50-56 行的 ASCII 架构图中，扩展为包含合并流程：

```
采集原始数据              审核清洗                合并                标准化 & 增强            模型训练
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ datas_ot1/   │───▶│ data_reviewer│───▶│ data_merger  │───▶│data_processor│───▶│   tub/       │
│ *.jpg 散装    │    │ X 标记垃圾    │    │ 多源按比例合并 │    │ 标准化 + 增强  │    │ 可直接训练    │
│              │    │ 移至 trash/  │    │              │    │              │    │              │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
```

Edit: 替换现有架构图。

- [ ] **Step 3: 模块关系新增**

在模块关系图中添加 `data_merger` 行：

```
data_launcher.py  ── GUI 启动器 ──┐
                                  ├──▶ data_reviewer.run_reviewer()
                                  ├──▶ data_merger.merge_datasets()
                                  ├──▶ data_processor.create_tub()
                                  └──▶ 日志面板 (LogRedirector)

data_reviewer.py  ── 独立可运行（CLI），也可被 GUI 调用
data_merger.py    ── 独立可运行（CLI），也可被 GUI 调用
data_processor.py ── 独立可运行（CLI），也可被 GUI 调用
```

Edit: 替换现有模块关系图。

- [ ] **Step 4: 新增 data_merger 模块详解章节**

在 `data_processor` 章节之后、`data_launcher` 章节之前（即现有「数据传输规范」前面的 model 详解区域末尾），插入以下内容：

```markdown

### data_merger — 数据集合并

**功能：** 将多个清洗后的 `datas/` 目录按指定比例随机采样，合并到一个目标目录。

**核心流程：**

1. 接收多个 `--src PATH:RATIO` 参数和一个 `-o` 目标目录
2. 对每个源目录：扫描所有 `.jpg`，按比例随机抽取
3. 逐个复制到目标目录（同名文件跳过，先到先得）
4. 输出统计摘要

**运行方式：**

```bash
# 基本用法：两个源各取不同比例
python data_merger.py --src user/clockwise_none/datas:0.6 --src user/clockwise_barrier/datas:1.0 -o user/merged/datas

# 单源抽样
python data_merger.py --src user/clockwise-v1/datas:0.5 -o user/clockwise-v1/datas_50pct
```

**注意事项：**

- 比例 1.0 表示全取不随机，0.0 表示跳过该源
- 目标目录不存在时自动创建
- 同名文件冲突：保留先复制的那份，跳过后续同名文件并打印警告
- 合并操作不修改原始数据源
```

- [ ] **Step 5: CLI 参数参考新增**

在 README.md CLI 参数参考章节，`data_processor.py` 之后添加：

```markdown

### data_merger.py

```
python data_merger.py --src PATH:RATIO [...] -o PATH

必需参数:
  --src PATH:RATIO    源目录:采样比例（可重复多次），比例范围 0.0~1.0
  -o, --output PATH   目标目录（不存在则自动创建）
```
```

- [ ] **Step 6: Commit**

```bash
cd E:/study/AutoCar/data_pipeline
git add README.md
git commit -m "docs: 新增 data_merger 数据集合并模块文档"
```
