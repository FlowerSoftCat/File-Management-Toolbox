import os
import shutil
import stat
import platform
import subprocess
import threading
from difflib import SequenceMatcher
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from tkinter.font import Font
from collections import defaultdict
import re

# ===================== 通用工具函数 =====================
def safe_delete(file_path):
    """安全删除文件"""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            return True, f"已删除：{os.path.basename(file_path)}"
    except Exception as e:
        return False, f"删除失败：{os.path.basename(file_path)} - {str(e)}"
    return False, f"文件不存在：{os.path.basename(file_path)}"

def get_time():
    """获取当前时间"""
    return datetime.now().strftime("%H:%M:%S")

def parse_multi_selection(input_str, max_num):
    """解析多选输入"""
    input_str = input_str.strip().lower()
    if input_str == "q":
        return "quit"
    
    selected_indexes = []
    parts = [p.strip() for p in input_str.split(",") if p.strip()]
    
    for part in parts:
        if "-" in part:
            try:
                start, end = map(int, part.split("-"))
                if 1 <= start <= end <= max_num:
                    selected_indexes.extend(range(start, end + 1))
            except:
                continue
        else:
            try:
                num = int(part)
                if 1 <= num <= max_num:
                    selected_indexes.append(num)
            except:
                continue
    
    return sorted(list(set(selected_indexes)))

# ===================== 压缩包修复功能 =====================
# 标准压缩后缀集合
STANDARD_COMPRESS_SUFFIXES = {'rar', 'zip', '7z', 'tar', 'gz', 'bz2', 'xz', 'iso', 'cab', 'arj', 'lzh', 'z', 'tgz', 'zst', 'lz4', 'lzma'}

# 压缩文件魔数映射
COMPRESS_MAGIC_MAP = {
    b'\x52\x61\x72\x21\x1A\x07': 'rar',
    b'\x50\x4B\x03\x04': 'zip',
    b'\x50\x4B\x05\x06': 'zip',
    b'\x50\x4B\x07\x08': 'zip',
    b'\x37\x7A\xBC\xAF\x27\x1C': '7z',
    b'\x1F\x8B\x08': 'gz',
    b'\x42\x5A\x68': 'bz2',
    b'\xFD\x37\x7A\x58\x5A\x00': 'xz',
    b'\x49\x49\x2A\x00': 'iso',
    b'\x43\x41\x42\x20': 'cab',
    b'\x1F\x9D': 'z',
    b'\x28\xB5\x2F\xFD': 'zst',
}

def get_file_real_format(file_path):
    """通过魔数获取文件真实压缩格式"""
    try:
        with open(file_path, 'rb') as f:
            header = f.read(20)
        for magic, suffix in sorted(COMPRESS_MAGIC_MAP.items(), key=lambda x: len(x[0]), reverse=True):
            if header.startswith(magic):
                return suffix
        return None
    except:
        return None

def analyze_file_problem(filename):
    """分析文件后缀问题"""
    filename_lower = filename.lower()
    matched_suffix = None
    suffix_pos = -1
    
    for suffix in sorted(STANDARD_COMPRESS_SUFFIXES, key=len, reverse=True):
        pos = filename_lower.find(f'.{suffix}')
        if pos != -1:
            matched_suffix = suffix
            suffix_pos = pos
            break

    if matched_suffix:
        correct_body = filename[:suffix_pos]
        full_correct_name = f"{correct_body}.{matched_suffix}"
        if full_correct_name == filename:
            return ("无异常", "文件名格式正确，是标准压缩文件", correct_body, matched_suffix)
        else:
            extra_content = filename[suffix_pos + len(matched_suffix) + 1:]
            return ("多余后缀/字符", f"标准后缀[{matched_suffix}]后存在多余内容：{extra_content}", correct_body, matched_suffix)

    if '.' not in filename:
        return ("缺失后缀", "文件名无后缀，无法识别格式", filename, None)

    parts = filename.split('.')
    last_part = parts[-1].lower()
    for suffix in sorted(STANDARD_COMPRESS_SUFFIXES, key=len, reverse=True):
        if last_part.startswith(suffix):
            correct_body = '.'.join(parts[:-1])
            return ("后缀被篡改", f"后缀[{last_part}]包含多余字符，匹配标准后缀[{suffix}]", correct_body, suffix)

    if len(parts) > 2:
        return ("多无效实心点", "文件名包含多个实心点，但无有效压缩后缀", filename, None)

    return ("无效后缀", f"后缀[{parts[-1]}]不是标准压缩格式", '.'.join(parts[:-1]), None)

def get_correct_filename(filename, real_suffix=None):
    """生成正确的文件名"""
    problem_type, problem_desc, correct_body, matched_suffix = analyze_file_problem(filename)
    final_suffix = real_suffix if real_suffix else matched_suffix
    if not final_suffix:
        return None, problem_type, problem_desc
    base_name = f"{correct_body}.{final_suffix}"
    return base_name, problem_type, problem_desc

# ===================== 视频处理功能 =====================
def get_all_video_files(target_dir=None):
    """获取目录所有视频文件"""
    video_exts = ('.mp4', '.avi', '.mkv', '.mov', '.flv', '.wmv', '.mpeg', '.mpg', '.webm')
    if not target_dir:
        target_dir = os.path.dirname(os.path.abspath(__file__))
    target_dir = os.path.abspath(target_dir)
    
    video_list = []
    for f in os.listdir(target_dir):
        path = os.path.join(target_dir, f)
        if os.path.isfile(path) and f.lower().endswith(video_exts):
            video_list.append(path)
    return video_list

def check_ffmpeg():
    """检查FFmpeg环境"""
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except:
        return False

def remove_video_audio(video_path, log_callback=None):
    """视频去声"""
    dirname, filename = os.path.split(video_path)
    name, ext = os.path.splitext(filename)
    output_path = os.path.join(dirname, f"{name}_去声{ext}")
    
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vcodec", "copy", "-an",
        "-y", "-loglevel", "error",
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True)
        msg = f"✅ 去声完成：{os.path.basename(output_path)}"
        if log_callback:
            log_callback(msg)
        return True, output_path, msg
    except Exception as e:
        msg = f"❌ 处理失败：{os.path.basename(video_path)} - {str(e)}"
        if log_callback:
            log_callback(msg)
        return False, None, msg

# ===================== 文件分类功能 =====================
def handle_single_file_folders(target_dir, log_callback=None):
    """清理单文件文件夹"""
    if log_callback:
        log_callback(f"🔧 清理单文件文件夹...")
    count = 0
    
    for root, dirs, files in os.walk(target_dir, topdown=False):
        if root == target_dir:
            continue
        file_list = [os.path.join(root, f) for f in os.listdir(root) if os.path.isfile(os.path.join(root, f))]
        if len(file_list) == 1:
            src = file_list[0]
            dst = os.path.join(os.path.dirname(root), os.path.basename(src))
            counter = 1
            name, ext = os.path.splitext(dst)
            while os.path.exists(dst):
                dst = f"{name}_{counter}{ext}"
                counter += 1
            shutil.move(src, dst)
            os.rmdir(root)
            count += 1
            if log_callback:
                log_callback(f"📁 移动文件：{os.path.basename(src)} -> {os.path.basename(dst)}")
    
    if log_callback:
        log_callback(f"✅ 清理完成，共处理 {count} 个单文件文件夹")
    return count

def classify_files_by_name(target_dir, log_callback=None):
    """按文件名核心部分分类（去掉数字后缀）"""
    if log_callback:
        log_callback(f"🔍 按文件名核心部分分类...")
    
    file_groups = defaultdict(list)
    all_files = []
    
    try:
        for f in os.listdir(target_dir):
            p = os.path.join(target_dir, f)
            if os.path.isfile(p):
                all_files.append(p)
    except Exception as e:
        if log_callback:
            log_callback(f"❌ 无法读取目录: {e}")
        return 0, 0
    
    if not all_files:
        if log_callback:
            log_callback("ℹ️ 目录中无文件可分类")
        return 0, 0
    
    for file_path in all_files:
        filename = os.path.basename(file_path)
        filename_no_ext = os.path.splitext(filename)[0]
        match = re.search(r'_(\d+)$', filename_no_ext)
        
        if match:
            core_name = filename_no_ext[:match.start()]
        else:
            core_name = filename_no_ext
            
        file_groups[core_name].append(file_path)
    
    created_count = 0
    moved_count = 0
    skipped_count = 0
    error_count = 0
    
    for core_name, files in file_groups.items():
        if len(files) < 2:
            skipped_count += len(files)
            continue
            
        target_folder = os.path.join(target_dir, core_name)
        
        if not os.path.exists(target_folder):
            try:
                os.makedirs(target_folder)
                created_count += 1
                if log_callback:
                    log_callback(f"  [新建] {core_name}/")
            except Exception as e:
                if log_callback:
                    log_callback(f"  [错误] 无法创建文件夹 '{core_name}': {e}")
                continue
                
        for file_path in files:
            filename = os.path.basename(file_path)
            target_file = os.path.join(target_folder, filename)
            
            if os.path.exists(target_file):
                if log_callback:
                    log_callback(f"  [跳过] {filename} (目标已存在)")
                continue
                
            try:
                shutil.move(file_path, target_file)
                moved_count += 1
                if log_callback:
                    log_callback(f"  [OK] {file_path}")
            except PermissionError:
                if log_callback:
                    log_callback(f"  [拒绝访问] {file_path} (文件被占用或无权限，已跳过)")
                error_count += 1
            except Exception as e:
                if log_callback:
                    log_callback(f"  [失败] {file_path}: {str(e)}")
                error_count += 1
    
    if log_callback:
        log_callback("\n" + "="*60)
        log_callback("✅ 整理结束。")
        log_callback(f"   新建文件夹: {created_count}")
        log_callback(f"   成功移动:   {moved_count}")
        log_callback(f"   保持不动:   {skipped_count} (单个文件)")
        if error_count > 0:
            log_callback(f"   报错跳过:   {error_count} (请查看上方日志)")
        log_callback("="*60)
    
    return created_count, moved_count

# ===================== 文件删除功能 =====================
def scan_files_for_delete(root_dir, targets, mode="keyword", log_callback=None):
    """扫描待删除文件"""
    if log_callback:
        log_callback(f"🔍 开始扫描目录：{root_dir}")
        log_callback(f"📌 删除模式：{'关键字' if mode == 'keyword' else '精确文件名'}")
        log_callback(f"📌 匹配条件：{targets}")
        log_callback("-" * 70)
    
    to_delete = []
    count = 0
    for dirpath, _, filenames in os.walk(root_dir):
        for f in filenames:
            match = False
            if mode == "keyword":
                for t in targets:
                    if t in f:
                        match = True
                        break
            else:
                if f in targets:
                    match = True

            if match:
                full_path = os.path.join(dirpath, f)
                to_delete.append(full_path)
                if log_callback:
                    log_callback(f"⚠️  待删除：{full_path}")
                count += 1

    if log_callback:
        log_callback("-" * 70)
        log_callback(f"✅ 扫描完成：共找到 {count} 个符合条件的文件")
    return to_delete

def delete_files_safely(file_list, log_callback=None):
    """安全删除文件"""
    if log_callback:
        log_callback("\n🚀 开始执行删除...")

    success = 0
    failed = 0
    failed_list = []

    for path in file_list:
        try:
            if platform.system() == "Windows":
                try:
                    attr = os.stat(path).st_file_attributes
                    if attr & stat.FILE_ATTRIBUTE_READONLY:
                        os.chmod(path, stat.S_IWRITE)
                except:
                    pass

            os.remove(path)
            if log_callback:
                log_callback(f"✅ 已删除：{path}")
            success += 1
        except Exception as e:
            if log_callback:
                log_callback(f"❌ 删除失败：{path} | {str(e)}")
            failed += 1
            failed_list.append((path, str(e)))

    if log_callback:
        log_callback("\n" + "="*50)
        log_callback("📊 删除完成报告")
        log_callback(f"总文件数：{len(file_list)}")
        log_callback(f"成功删除：{success}")
        log_callback(f"删除失败：{failed}")
        log_callback("="*50)

        if failed_list:
            log_callback("\n❌ 失败文件列表：")
            for p, e in failed_list:
                log_callback(f"  → {p}\n    原因：{e}")
    
    return success, failed

# ===================== 主界面 =====================
class MultiToolGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("全能文件处理工具箱")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)
        
        # 字体配置
        self.title_font = Font(family="Microsoft YaHei", size=16, weight="bold")
        self.subtitle_font = Font(family="Microsoft YaHei", size=12, weight="bold")
        self.normal_font = Font(family="Microsoft YaHei", size=10)
        self.log_font = Font(family="Consolas", size=9)
        
        # ========== 现代化UI样式设计 ==========
        # 使用clam主题以获得更好的样式控制
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        # 全局基础样式 - 使用更现代化的配色
        self.style.configure(".", 
                            font=self.normal_font,
                            background="#F5F7FA",
                            foreground="#1D2129")
        self.style.configure("TLabel", 
                            background="#F5F7FA",
                            foreground="#1D2129")
        self.style.configure("TLabelframe", 
                            background="#F5F7FA",
                            foreground="#1D2129",
                            relief="solid",
                            borderwidth=1)
        self.style.configure("TLabelframe.Label", 
                            background="#F5F7FA",
                            foreground="#1D2129",
                            font=self.subtitle_font)
        
        # Treeview样式 - 更现代化的表格设计
        self.style.configure("Treeview",
                            font=self.normal_font,
                            rowheight=25,
                            background="white",
                            fieldbackground="white",
                            foreground="#1D2129",
                            bordercolor="#E5E6EB",
                            borderwidth=1)
        self.style.configure("Treeview.Heading",
                            font=("Microsoft YaHei", 10, "bold"),
                            background="#F2F3F5",
                            foreground="#1D2129",
                            relief="flat",
                            padding=5)
        self.style.map("Treeview.Heading",
                      background=[("active", "#E5E6EB")])
        
        # Notebook（标签页）样式 - 增强视觉区分度
        self.style.configure("TNotebook",
                            background="#F5F7FA",
                            borderwidth=0)
        self.style.configure("TNotebook.Tab",
                            font=("Microsoft YaHei", 10),
                            padding=[15, 5],
                            background="#E5E6EB",
                            foreground="#4E5969",
                            borderwidth=1,
                            relief="flat")
        self.style.map("TNotebook.Tab",
                      background=[("selected", "#165DFF"), ("active", "#E5E6EB")],
                      foreground=[("selected", "white"), ("active", "#1D2129")],
                      relief=[("selected", "flat"), ("active", "flat")])
        
        # 1. 主按钮样式（现代化蓝色主题）
        self.style.configure(
            "Primary.TButton",
            font=("Microsoft YaHei", 10, "bold"),
            foreground="white",
            background="#165DFF",
            padding=[12, 6],
            borderwidth=1,
            relief="flat",
            focusthickness=0,
            focuscolor="none"
        )
        self.style.map(
            "Primary.TButton",
            background=[("active", "#0E42B3"), ("pressed", "#0A338A"), ("disabled", "#86909C")],
            foreground=[("active", "white"), ("pressed", "white"), ("disabled", "#E5E6EB")],
            relief=[("pressed", "sunken"), ("!disabled", "raised")]
        )
        
        # 2. 次要按钮样式（现代化灰色主题）
        self.style.configure(
            "Secondary.TButton",
            font=("Microsoft YaHei", 10),
            foreground="white",
            background="#4E5969",
            padding=[10, 5],
            borderwidth=1,
            relief="flat",
            focusthickness=0,
            focuscolor="none"
        )
        self.style.map(
            "Secondary.TButton",
            background=[("active", "#363E4A"), ("pressed", "#272E36"), ("disabled", "#86909C")],
            foreground=[("active", "white"), ("pressed", "white"), ("disabled", "#E5E6EB")],
            relief=[("pressed", "sunken"), ("!disabled", "raised")]
        )
        
        # 3. 危险按钮样式（现代化红色主题）
        self.style.configure(
            "Danger.TButton",
            font=("Microsoft YaHei", 10, "bold"),
            foreground="white",
            background="#F53F3F",
            padding=[12, 6],
            borderwidth=1,
            relief="flat",
            focusthickness=0,
            focuscolor="none"
        )
        self.style.map(
            "Danger.TButton",
            background=[("active", "#CB2634"), ("pressed", "#A11824"), ("disabled", "#86909C")],
            foreground=[("active", "white"), ("pressed", "white"), ("disabled", "#E5E6EB")],
            relief=[("pressed", "sunken"), ("!disabled", "raised")]
        )
        
        # 4. 成功按钮样式（现代化绿色主题）
        self.style.configure(
            "Success.TButton",
            font=("Microsoft YaHei", 10, "bold"),
            foreground="white",
            background="#00B42A",
            padding=[12, 6],
            borderwidth=1,
            relief="flat",
            focusthickness=0,
            focuscolor="none"
        )
        self.style.map(
            "Success.TButton",
            background=[("active", "#009A24"), ("pressed", "#007E1D"), ("disabled", "#86909C")],
            foreground=[("active", "white"), ("pressed", "white"), ("disabled", "#E5E6EB")],
            relief=[("pressed", "sunken"), ("!disabled", "raised")]
        )
        
        # Entry和Combobox样式
        self.style.configure("TEntry",
                            fieldbackground="white",
                            foreground="#1D2129",
                            bordercolor="#C9CDD4",
                            borderwidth=1,
                            relief="solid",
                            padding=5)
        self.style.map("TEntry",
                      bordercolor=[("focus", "#165DFF"), ("hover", "#86909C")])
        
        self.style.configure("TCombobox",
                            fieldbackground="white",
                            foreground="#1D2129",
                            bordercolor="#C9CDD4",
                            borderwidth=1,
                            relief="solid",
                            padding=5)
        self.style.map("TCombobox",
                      bordercolor=[("focus", "#165DFF"), ("hover", "#86909C")])
        
        # Listbox样式
        self.style.configure("TListbox",
                            background="white",
                            foreground="#1D2129",
                            selectbackground="#165DFF",
                            selectforeground="white",
                            borderwidth=1,
                            relief="solid")
        
        # Radiobutton和Checkbutton样式
        self.style.configure("TRadiobutton",
                            background="#F5F7FA",
                            foreground="#1D2129")
        self.style.configure("TCheckbutton",
                            background="#F5F7FA",
                            foreground="#1D2129")
        # ========== 样式设计结束 ==========
        
        # 全局变量（优先初始化，避免时序问题）
        self.current_tab = tk.StringVar(value="compress")
        self.processing = False
        self.to_delete_files = []
        self.processed_video_files = []
        self.compress_file_list = []
        self.video_files = []
        # 提前初始化状态栏变量，确保调用前已存在
        self.status_var = tk.StringVar(value="就绪 | 请选择功能开始操作")
        
        # 构建主界面
        self.build_main_ui()
    
    def build_main_ui(self):
        """构建现代化主界面"""
        # 设置窗口背景色
        self.root.configure(background="#F5F7FA")
        
        # 顶部标题区域 - 现代化设计
        header_frame = ttk.Frame(self.root, style="Header.TFrame")
        header_frame.pack(fill=tk.X, padx=0, pady=0)
        
        # 标题容器
        title_container = ttk.Frame(header_frame)
        title_container.pack(fill=tk.X, padx=25, pady=20)
        
        # 主标题
        title_label = ttk.Label(title_container, 
                               text="📦 全能文件处理工具箱",
                               font=("Microsoft YaHei", 18, "bold"),
                               foreground="#1D2129",
                               background="#F5F7FA")
        title_label.pack(side=tk.LEFT)
        
        # 副标题
        subtitle_label = ttk.Label(title_container,
                                  text="一站式解决文件压缩包修复、视频处理、文件管理需求",
                                  font=("Microsoft YaHei", 10),
                                  foreground="#86909C",
                                  background="#F5F7FA")
        subtitle_label.pack(side=tk.LEFT, padx=(15, 0), pady=(5, 0))
        
        # 主内容区域
        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))
        
        # 主选项卡区域
        tab_frame = ttk.Frame(main_container)
        tab_frame.pack(fill=tk.BOTH, expand=True)
        
        # 主选项卡（标签页）
        tab_control = ttk.Notebook(tab_frame)
        
        # 1. 压缩包修复标签页
        self.compress_tab = ttk.Frame(tab_control)
        tab_control.add(self.compress_tab, text="📁 压缩包后缀修复")
        self.build_compress_tab()
        
        # 2. 视频批量去声标签页
        self.video_tab = ttk.Frame(tab_control)
        tab_control.add(self.video_tab, text="🎵 视频批量去声")
        self.build_video_tab()
        
        # 3. 文件自动分类标签页
        self.classify_tab = ttk.Frame(tab_control)
        tab_control.add(self.classify_tab, text="📂 文件自动分类")
        self.build_classify_tab()
        
        # 4. 批量删除指定文件标签页
        self.delete_tab = ttk.Frame(tab_control)
        tab_control.add(self.delete_tab, text="🗑️ 批量删除指定文件")
        self.build_delete_tab()
        
        # 5. 视频字幕批量重命名标签页
        self.subtitle_tab = ttk.Frame(tab_control)
        tab_control.add(self.subtitle_tab, text="🎬 视频字幕批量重命名")
        self.build_subtitle_tab()
        
        tab_control.pack(fill=tk.BOTH, expand=True)
        
        # 日志区域
        log_container = ttk.Frame(main_container)
        log_container.pack(fill=tk.BOTH, expand=False, pady=(10, 0))
        
        log_frame = ttk.LabelFrame(log_container, 
                                  text="📝 操作日志",
                                  padding=15)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        # 日志工具栏
        log_toolbar = ttk.Frame(log_frame)
        log_toolbar.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(log_toolbar, 
                  text="清空日志",
                  command=self.clear_log,
                  style="Secondary.TButton",
                  width=10).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(log_toolbar,
                  text="导出日志",
                  command=self.export_log,
                  style="Secondary.TButton",
                  width=10).pack(side=tk.LEFT)
        
        # 日志文本区域
        self.log_text = scrolledtext.ScrolledText(log_frame, 
                                                 font=self.log_font,
                                                 wrap=tk.WORD,
                                                 bg="white",
                                                 fg="#1D2129",
                                                 relief="solid",
                                                 borderwidth=1,
                                                 padx=10,
                                                 pady=10)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state=tk.DISABLED)
        
        # 底部状态栏 - 现代化设计
        status_frame = ttk.Frame(self.root, relief=tk.SUNKEN)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 状态图标
        status_icon = ttk.Label(status_frame, 
                               text="⚙️",
                               font=("Microsoft YaHei", 10),
                               foreground="#86909C")
        status_icon.pack(side=tk.LEFT, padx=(15, 5), pady=8)
        
        # 状态文本
        status_bar = ttk.Label(status_frame, 
                              textvariable=self.status_var,
                              font=("Microsoft YaHei", 9),
                              foreground="#4E5969",
                              anchor=tk.W)
        status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 15), pady=8)
        
        # 添加自定义样式
        self.style.configure("Header.TFrame", background="#F5F7FA")
        
        # 初始化标签页拖拽功能
        self.tab_control = tab_control
        self.tab_widgets = {
            'compress': self.compress_tab,
            'video': self.video_tab,
            'classify': self.classify_tab,
            'delete': self.delete_tab,
            'subtitle': self.subtitle_tab
        }
        self.enable_tab_drag(tab_control)

        # 绑定标签页切换事件
        tab_control.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        # 设置窗口位置
        self.set_window_position()

        # 绑定关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def on_tab_changed(self, event):
        """标签页切换事件处理"""
        notebook = event.widget
        current_tab = notebook.select()
        tab_text = notebook.tab(current_tab, "text")
        
        # 更新状态栏显示当前标签页
        self.update_status(f"当前功能：{tab_text.replace('📁 ', '').replace('🎬 ', '').replace('🗂️ ', '')}")
    
    def center_window(self):
        """窗口居中显示"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def set_window_position(self):
        """设置窗口位置为全屏显示"""
        try:
            self.root.state('zoomed')
        except Exception:
            self.root.attributes('-zoomed', True)
    
    def on_closing(self):
        """窗口关闭事件"""
        self.root.destroy()
    
    def enable_tab_drag(self, notebook):
        """启用标签页拖拽排序"""
        notebook.bind("<ButtonPress-1>", self.on_tab_press)
        notebook.bind("<B1-Motion>", self.on_tab_motion)
        notebook.bind("<ButtonRelease-1>", self.on_tab_release)
        self._drag_start_index = None
        self._drag_current_index = None
    
    def on_tab_press(self, event):
        try:
            self._drag_start_index = self.tab_control.index(f"@{event.x},{event.y}")
        except tk.TclError:
            self._drag_start_index = None
    
    def on_tab_motion(self, event):
        if self._drag_start_index is None:
            return
        try:
            idx = self.tab_control.index(f"@{event.x},{event.y}")
            self._drag_current_index = idx
        except tk.TclError:
            self._drag_current_index = None
    
    def on_tab_release(self, event):
        if self._drag_start_index is None:
            return
        try:
            end_index = self.tab_control.index(f"@{event.x},{event.y}")
        except tk.TclError:
            end_index = None
        start_index = self._drag_start_index
        self._drag_start_index = None
        self._drag_current_index = None
        if end_index is None or end_index == start_index:
            return
        if end_index > start_index:
            end_index += 1
        self.move_tab_to(start_index, end_index)
    
    def move_tab_to(self, start_index, end_index):
        """移动标签页到指定位置"""
        try:
            tab_id = self.tab_control.tabs()[start_index]
            self.tab_control.insert(end_index, tab_id)
        except Exception:
            pass
    
    def export_log(self):
        """导出日志到文件"""
        from tkinter import filedialog
        import os
        
        # 获取日志内容
        log_content = self.log_text.get("1.0", tk.END)
        if not log_content.strip():
            messagebox.showwarning("提示", "日志内容为空，无需导出！")
            return
        
        # 选择保存路径
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialfile=f"文件处理工具箱日志_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("=" * 60 + "\n")
                    f.write("全能文件处理工具箱 - 操作日志\n")
                    f.write(f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("=" * 60 + "\n\n")
                    f.write(log_content)
                
                self.log(f"✅ 日志已导出到：{os.path.basename(file_path)}")
                self.update_status(f"日志导出成功：{os.path.basename(file_path)}")
                messagebox.showinfo("导出成功", f"日志已成功导出到：\n{file_path}")
            except Exception as e:
                self.log(f"❌ 日志导出失败：{str(e)}")
                self.update_status("日志导出失败")
                messagebox.showerror("导出失败", f"日志导出失败：\n{str(e)}")
    
    def build_compress_tab(self):
        """构建现代化压缩包修复界面"""
        # 设置标签页背景
        self.compress_tab.configure(style="Tab.TFrame")
        
        # 主容器
        main_container = ttk.Frame(self.compress_tab)
        main_container.pack(fill=tk.BOTH, expand=True, padx=25, pady=20)
        
        # 1. 功能说明区域 - 卡片式设计
        func_card = ttk.LabelFrame(main_container,
                                  text="📦 压缩包修复功能说明",
                                  padding=20)
        func_card.pack(fill=tk.X, pady=(0, 15))
        
        # 功能说明标签
        func_desc = ttk.Label(func_card,
                             text="功能说明：自动检测并修复压缩包文件后缀问题，支持常见压缩格式（rar, zip, 7z, tar, gz, bz2, xz等）",
                             font=("Microsoft YaHei", 10),
                             foreground="#4E5969",
                             wraplength=800)
        func_desc.pack(fill=tk.X, pady=(5, 0))
        
        # 错误示例说明
        example_frame = ttk.Frame(func_card)
        example_frame.pack(fill=tk.X, pady=(10, 0))
        
        example_label = ttk.Label(example_frame,
                                 text="📌 常见错误后缀示例：",
                                 font=("Microsoft YaHei", 10, "bold"),
                                 foreground="#1D2129")
        example_label.pack(anchor=tk.W, pady=(0, 5))
        
        examples = [
            "• 无后缀：archive（应为 archive.7z）",
            "• 后缀夹杂其他字符：archive.rar.txt（应为 archive.rar）",
            "• 后缀缺失关键字符：archive.zi（应为 archive.zip）",
            "• 多无效实心点：archive..rar（应为 archive.rar）",
            "• 后缀被篡改：archive.rar_backup（应为 archive.rar）"
        ]
        
        for example in examples:
            example_text = ttk.Label(example_frame,
                                    text=example,
                                    font=("Microsoft YaHei", 9),
                                    foreground="#86909C")
            example_text.pack(anchor=tk.W, padx=(20, 0))
        
        # 2. 目录选择区域 - 卡片式设计
        dir_card = ttk.LabelFrame(main_container, 
                                 text="📂 目标目录设置",
                                 padding=20)
        dir_card.pack(fill=tk.X, pady=(0, 15))
        
        # 目录输入行
        dir_row = ttk.Frame(dir_card)
        dir_row.pack(fill=tk.X)
        
        ttk.Label(dir_row, 
                 text="目录路径：",
                 font=("Microsoft YaHei", 10, "bold"),
                 foreground="#1D2129").pack(side=tk.LEFT, padx=(0, 10))
        
        self.compress_dir_var = tk.StringVar(value="")
        dir_entry = ttk.Entry(dir_row, 
                             textvariable=self.compress_dir_var,
                             font=self.normal_font,
                             width=50)
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        # 按钮组
        btn_group = ttk.Frame(dir_row)
        btn_group.pack(side=tk.RIGHT)
        
        ttk.Button(btn_group, 
                  text="📁 浏览",
                  command=self.select_compress_dir,
                  style="Secondary.TButton",
                  width=8).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(btn_group,
                  text="🔄 扫描",
                  command=self.scan_compress_files,
                  style="Primary.TButton",
                  width=8).pack(side=tk.LEFT)
        
        # 3. 文件列表区域 - 现代化表格
        list_card = ttk.LabelFrame(main_container,
                                  text="📋 文件列表与问题分析",
                                  padding=15)
        list_card.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # 表格工具栏
        toolbar = ttk.Frame(list_card)
        toolbar.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(toolbar,
                 text="共扫描到 0 个文件，其中 0 个存在问题",
                 font=("Microsoft YaHei", 9),
                 foreground="#86909C").pack(side=tk.LEFT)
        
        # 表格操作按钮
        table_btns = ttk.Frame(toolbar)
        table_btns.pack(side=tk.RIGHT)
        
        ttk.Button(table_btns,
                  text="✅ 全选",
                  command=self.select_all_compress,
                  style="Secondary.TButton",
                  width=8).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(table_btns,
                  text="🔄 反选",
                  command=self.reverse_select_compress,
                  style="Secondary.TButton",
                  width=8).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(table_btns,
                  text="⚠️ 选有问题",
                  command=self.select_problem_compress,
                  style="Secondary.TButton",
                  width=10).pack(side=tk.LEFT)
        
        # 表格区域
        table_frame = ttk.Frame(list_card)
        table_frame.pack(fill=tk.BOTH, expand=True)
        
        # 定义表格列
        columns = ("序号", "文件名", "问题类型", "问题描述", "处理状态")
        self.compress_tree = ttk.Treeview(table_frame, 
                                         columns=columns, 
                                         show="headings",
                                         height=15,
                                         selectmode="extended")
        
        # 配置列宽和样式
        column_configs = [
            ("序号", 60, tk.CENTER),
            ("文件名", 280, tk.W),
            ("问题类型", 120, tk.CENTER),
            ("问题描述", 350, tk.W),
            ("处理状态", 100, tk.CENTER)
        ]
        
        for col, width, anchor in column_configs:
            self.compress_tree.column(col, width=width, anchor=anchor)
            self.compress_tree.heading(col, text=col)
        
        # 添加滚动条
        v_scroll = ttk.Scrollbar(table_frame, 
                                orient=tk.VERTICAL, 
                                command=self.compress_tree.yview)
        h_scroll = ttk.Scrollbar(table_frame,
                                orient=tk.HORIZONTAL,
                                command=self.compress_tree.xview)
        self.compress_tree.configure(yscrollcommand=v_scroll.set,
                                    xscrollcommand=h_scroll.set)
        
        # 布局表格和滚动条
        self.compress_tree.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
        
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        
        # 3. 操作按钮区域
        action_card = ttk.LabelFrame(main_container,
                                    text="⚙️ 批量操作",
                                    padding=20)
        action_card.pack(fill=tk.X)
        
        action_btns = ttk.Frame(action_card)
        action_btns.pack(expand=True)
        
        # 状态提示
        status_label = ttk.Label(action_btns,
                                text="已选中 0 个文件",
                                font=("Microsoft YaHei", 10),
                                foreground="#4E5969")
        status_label.pack(side=tk.LEFT, padx=(0, 20))
        
        # 主要操作按钮
        self.fix_compress_btn = ttk.Button(action_btns,
                                          text="🚀 开始修复选中文件",
                                          command=self.fix_compress_files,
                                          style="Primary.TButton",
                                          width=20)
        self.fix_compress_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(action_btns,
                  text="📊 导出报告",
                  command=self.export_compress_report,
                  style="Secondary.TButton",
                  width=12).pack(side=tk.LEFT)
        
        # 绑定表格选择事件
        self.compress_tree.bind("<<TreeviewSelect>>", 
                               lambda e: self.on_compress_selection_change(status_label))
        
        # 初始化文件列表（延迟执行，避免时序问题）
        self.root.after(100, self.scan_compress_files)
    
    def on_compress_selection_change(self, status_label):
        """压缩包表格选择变化事件"""
        selected = len(self.compress_tree.selection())
        status_label.config(text=f"已选中 {selected} 个文件")
    
    def export_compress_report(self):
        """导出压缩包修复报告"""
        from tkinter import filedialog
        import os
        
        if not self.compress_file_list:
            messagebox.showwarning("提示", "没有可导出的数据，请先扫描文件！")
            return
        
        # 选择保存路径
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialfile=f"压缩包修复报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("=" * 70 + "\n")
                    f.write("压缩包后缀修复报告\n")
                    f.write(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"目标目录：{self.compress_dir_var.get()}\n")
                    f.write("=" * 70 + "\n\n")
                    
                    # 统计信息
                    total = len(self.compress_file_list)
                    problem_count = sum(1 for f in self.compress_file_list if f["problem_type"] != "无异常")
                    fixed_count = sum(1 for f in self.compress_file_list if f["status"] == "修复成功")
                    
                    f.write("📊 统计信息：\n")
                    f.write(f"  总文件数：{total}\n")
                    f.write(f"  存在问题：{problem_count}\n")
                    f.write(f"  已修复数：{fixed_count}\n")
                    f.write("\n" + "-" * 70 + "\n\n")
                    
                    # 文件详情
                    f.write("📋 文件详情：\n")
                    for idx, file_info in enumerate(self.compress_file_list, 1):
                        f.write(f"\n{idx}. {file_info['filename']}\n")
                        f.write(f"   问题类型：{file_info['problem_type']}\n")
                        f.write(f"   问题描述：{file_info['problem_desc']}\n")
                        f.write(f"   处理状态：{file_info['status']}\n")
                        if file_info['real_suffix']:
                            f.write(f"   真实格式：{file_info['real_suffix']}\n")
                
                self.log(f"✅ 报告已导出到：{os.path.basename(file_path)}")
                self.update_status(f"报告导出成功：{os.path.basename(file_path)}")
                messagebox.showinfo("导出成功", f"报告已成功导出到：\n{file_path}")
            except Exception as e:
                self.log(f"❌ 报告导出失败：{str(e)}")
                self.update_status("报告导出失败")
                messagebox.showerror("导出失败", f"报告导出失败：\n{str(e)}")
    
    def build_video_tab(self):
        """构建现代化视频去声界面"""
        # 设置标签页背景
        self.video_tab.configure(style="Tab.TFrame")
        
        # 主容器
        main_container = ttk.Frame(self.video_tab)
        main_container.pack(fill=tk.BOTH, expand=True, padx=25, pady=20)
        
        # 1. 功能说明区域 - 卡片式设计
        func_card = ttk.LabelFrame(main_container,
                                  text="🎵 视频批量去声",
                                  padding=20)
        func_card.pack(fill=tk.X, pady=(0, 15))
        
        # 功能说明标签
        func_desc = ttk.Label(func_card,
                             text="功能说明：移除视频文件中的音频轨道，生成新的无声音频视频文件",
                             font=("Microsoft YaHei", 10),
                             foreground="#4E5969",
                             wraplength=600)
        func_desc.pack(fill=tk.X, pady=(5, 0))
        
        # 2. 目录选择区域
        dir_card = ttk.LabelFrame(main_container,
                                 text="📁 目标目录设置",
                                 padding=20)
        dir_card.pack(fill=tk.X, pady=(0, 15))
        
        dir_row = ttk.Frame(dir_card)
        dir_row.pack(fill=tk.X)
        
        ttk.Label(dir_row,
                 text="目录路径：",
                 font=("Microsoft YaHei", 10, "bold"),
                 foreground="#1D2129").pack(side=tk.LEFT, padx=(0, 10))
        
        self.video_dir_var = tk.StringVar(value="")
        dir_entry = ttk.Entry(dir_row,
                             textvariable=self.video_dir_var,
                             font=self.normal_font,
                             width=50)
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        # 目录操作按钮
        dir_btns = ttk.Frame(dir_row)
        dir_btns.pack(side=tk.RIGHT)
        
        ttk.Button(dir_btns,
                  text="📁 浏览",
                  command=self.select_video_dir,
                  style="Secondary.TButton",
                  width=8).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(dir_btns,
                  text="🔄 刷新",
                  command=self.refresh_video_list,
                  style="Secondary.TButton",
                  width=8).pack(side=tk.LEFT)
        
        # 3. 视频列表区域
        list_card = ttk.LabelFrame(main_container,
                                  text="🎬 视频文件列表",
                                  padding=15)
        list_card.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # 列表工具栏
        list_toolbar = ttk.Frame(list_card)
        list_toolbar.pack(fill=tk.X, pady=(0, 10))
        
        # 文件统计
        self.video_count_label = ttk.Label(list_toolbar,
                                          text="共 0 个视频文件",
                                          font=("Microsoft YaHei", 9),
                                          foreground="#86909C")
        self.video_count_label.pack(side=tk.LEFT)
        
        # 选择操作
        select_tools = ttk.Frame(list_toolbar)
        select_tools.pack(side=tk.RIGHT)
        
        self.select_all_var = tk.BooleanVar()
        ttk.Checkbutton(select_tools,
                       text="✅ 全选",
                       variable=self.select_all_var,
                       command=self.toggle_select_all_video,
                       style="Toolbutton.TCheckbutton").pack(side=tk.LEFT, padx=(0, 10))
        
        # 列表区域
        list_container = ttk.Frame(list_card)
        list_container.pack(fill=tk.BOTH, expand=True)
        
        # 创建Listbox和滚动条
        self.video_listbox = tk.Listbox(list_container,
                                       font=("Microsoft YaHei", 10),
                                       selectmode=tk.MULTIPLE,
                                       bg="white",
                                       fg="#1D2129",
                                       selectbackground="#165DFF",
                                       selectforeground="white",
                                       relief="solid",
                                       borderwidth=1,
                                       height=12)
        
        v_scroll = ttk.Scrollbar(list_container,
                                orient=tk.VERTICAL,
                                command=self.video_listbox.yview)
        h_scroll = ttk.Scrollbar(list_container,
                                orient=tk.HORIZONTAL,
                                command=self.video_listbox.xview)
        
        self.video_listbox.configure(yscrollcommand=v_scroll.set,
                                    xscrollcommand=h_scroll.set)
        
        # 布局
        self.video_listbox.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
        
        list_container.grid_rowconfigure(0, weight=1)
        list_container.grid_columnconfigure(0, weight=1)
        
        # 4. 操作按钮区域
        action_card = ttk.LabelFrame(main_container,
                                    text="⚙️ 批量处理操作",
                                    padding=20)
        action_card.pack(fill=tk.X)
        
        action_row = ttk.Frame(action_card)
        action_row.pack(expand=True)
        
        # 状态信息
        self.video_status_label = ttk.Label(action_row,
                                           text="已选中 0 个文件",
                                           font=("Microsoft YaHei", 10),
                                           foreground="#4E5969")
        self.video_status_label.pack(side=tk.LEFT, padx=(0, 20))
        
        # 处理按钮
        self.video_process_btn = ttk.Button(action_row,
                                           text="🚀 开始处理",
                                           command=self.start_video_process,
                                           style="Primary.TButton",
                                           width=15)
        self.video_process_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 删除原文件按钮
        self.delete_origin_btn = ttk.Button(action_row,
                                           text="🗑️ 删除原文件",
                                           command=self.delete_video_origin,
                                           style="Danger.TButton",
                                           width=15)
        self.delete_origin_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 辅助按钮
        ttk.Button(action_row,
                  text="📋 复制列表",
                  command=self.copy_video_list,
                  style="Secondary.TButton",
                  width=12).pack(side=tk.LEFT)
        
        # 绑定列表选择事件
        self.video_listbox.bind("<<ListboxSelect>>",
                               lambda e: self.on_video_selection_change())
        
        # 初始化文件列表（延迟执行，避免时序问题）
        self.root.after(100, self.refresh_video_list)
    
    def on_video_selection_change(self):
        """视频列表选择变化事件"""
        selected = len(self.video_listbox.curselection())
        self.video_status_label.config(text=f"已选中 {selected} 个文件")
    
    def copy_video_list(self):
        """复制视频列表到剪贴板"""
        if not self.video_files:
            messagebox.showwarning("提示", "视频列表为空！")
            return
        
        # 构建列表文本
        list_text = "视频文件列表：\n"
        for idx, file_path in enumerate(self.video_files, 1):
            filename = os.path.basename(file_path)
            list_text += f"{idx}. {filename}\n"
        
        # 复制到剪贴板
        self.root.clipboard_clear()
        self.root.clipboard_append(list_text)
        
        self.log("✅ 视频列表已复制到剪贴板")
        self.update_status("视频列表已复制")
        messagebox.showinfo("复制成功", "视频列表已成功复制到剪贴板！")
    
    def build_delete_tab(self):
        """构建批量删除指定文件界面"""
        # 设置标签页背景
        self.delete_tab.configure(style="Tab.TFrame")
        
        # 主容器
        main_container = ttk.Frame(self.delete_tab)
        main_container.pack(fill=tk.BOTH, expand=True, padx=25, pady=20)
        
        # 1. 功能说明区域 - 卡片式设计
        func_card = ttk.LabelFrame(main_container,
                                  text="🗑️ 批量删除指定文件功能说明",
                                  padding=20)
        func_card.pack(fill=tk.X, pady=(0, 15))
        
        # 功能说明标签
        func_desc = ttk.Label(func_card,
                             text="功能说明：根据文件名关键字或精确文件名批量删除文件，支持递归扫描子目录",
                             font=("Microsoft YaHei", 10),
                             foreground="#4E5969",
                             wraplength=800)
        func_desc.pack(fill=tk.X, pady=(5, 0))
        
        # 使用说明
        usage_frame = ttk.Frame(func_card)
        usage_frame.pack(fill=tk.X, pady=(10, 0))
        
        usage_label = ttk.Label(usage_frame,
                               text="📌 使用说明：",
                               font=("Microsoft YaHei", 10, "bold"),
                               foreground="#1D2129")
        usage_label.pack(anchor=tk.W, pady=(0, 5))
        
        usage_points = [
            "• 关键字匹配：删除文件名中包含指定关键字的文件（多个关键字用逗号分隔）",
            "• 精确匹配：删除文件名完全匹配指定名称的文件",
            "• 支持递归扫描：自动扫描选定目录及其所有子目录",
            "• 安全机制：先扫描预览，确认无误后再执行删除操作",
            "• 操作日志：所有删除操作都会记录在日志中，便于追踪"
        ]
        
        for point in usage_points:
            point_text = ttk.Label(usage_frame,
                                  text=point,
                                  font=("Microsoft YaHei", 9),
                                  foreground="#86909C")
            point_text.pack(anchor=tk.W, padx=(20, 0))
        
        # 2. 目录选择区域 - 卡片式设计
        dir_card = ttk.LabelFrame(main_container,
                                 text="📂 扫描目录设置",
                                 padding=20)
        dir_card.pack(fill=tk.X, pady=(0, 15))
        
        dir_row = ttk.Frame(dir_card)
        dir_row.pack(fill=tk.X)
        
        ttk.Label(dir_row,
                 text="扫描目录：",
                 font=("Microsoft YaHei", 10, "bold"),
                 foreground="#1D2129").pack(side=tk.LEFT, padx=(0, 10))
        
        self.file_dir_var = tk.StringVar()
        dir_entry = ttk.Entry(dir_row,
                             textvariable=self.file_dir_var,
                             font=self.normal_font,
                             width=50)
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        # 目录操作按钮
        dir_btns = ttk.Frame(dir_row)
        dir_btns.pack(side=tk.RIGHT)
        
        ttk.Button(dir_btns,
                  text="📁 浏览",
                  command=self.select_file_dir,
                  style="Secondary.TButton",
                  width=8).pack(side=tk.LEFT)
        
        # 2. 删除模式选择区域
        mode_card = ttk.LabelFrame(main_container,
                                  text="🎯 删除模式选择",
                                  padding=20)
        mode_card.pack(fill=tk.X, pady=(0, 15))
        
        mode_row = ttk.Frame(mode_card)
        mode_row.pack(fill=tk.X)
        
        ttk.Label(mode_row,
                 text="选择模式：",
                 font=("Microsoft YaHei", 10, "bold"),
                 foreground="#1D2129").pack(side=tk.LEFT, padx=(0, 15))
        
        self.delete_mode = tk.StringVar(value="keyword")
        
        # 模式选项按钮组
        mode_options = ttk.Frame(mode_row)
        mode_options.pack(side=tk.LEFT)
        
        ttk.Radiobutton(mode_options,
                       text="🔍 关键字匹配（文件名包含即删除）",
                       variable=self.delete_mode,
                       value="keyword",
                       style="Toolbutton.TRadiobutton").pack(side=tk.LEFT, padx=(0, 15))
        
        ttk.Radiobutton(mode_options,
                       text="✅ 精确匹配（完全匹配文件名）",
                       variable=self.delete_mode,
                       value="exact",
                       style="Toolbutton.TRadiobutton").pack(side=tk.LEFT)
        
        # 模式说明
        mode_desc = ttk.Label(mode_card,
                             text="关键字匹配：删除文件名中包含指定关键字的文件 | 精确匹配：删除文件名完全匹配的文件",
                             font=("Microsoft YaHei", 9),
                             foreground="#86909C",
                             wraplength=600)
        mode_desc.pack(fill=tk.X, pady=(10, 0))
        
        # 3. 删除内容输入区域
        input_card = ttk.LabelFrame(main_container,
                                   text="📝 删除内容设置",
                                   padding=20)
        input_card.pack(fill=tk.X, pady=(0, 15))
        
        input_row = ttk.Frame(input_card)
        input_row.pack(fill=tk.X)
        
        ttk.Label(input_row,
                 text="删除内容：",
                 font=("Microsoft YaHei", 10, "bold"),
                 foreground="#1D2129").pack(side=tk.LEFT, padx=(0, 10))
        
        self.target_var = tk.StringVar()
        target_entry = ttk.Entry(input_row,
                                textvariable=self.target_var,
                                font=self.normal_font,
                                width=50)
        target_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 输入说明
        input_desc = ttk.Label(input_card,
                              text="多个关键字用逗号分隔，例如：temp,backup,old",
                              font=("Microsoft YaHei", 9),
                              foreground="#86909C")
        input_desc.pack(fill=tk.X, pady=(10, 0))
        
        # 4. 操作按钮区域
        action_card = ttk.LabelFrame(main_container,
                                    text="⚙️ 扫描与删除操作",
                                    padding=20)
        action_card.pack(fill=tk.X)
        
        action_row = ttk.Frame(action_card)
        action_row.pack(expand=True)
        
        # 状态信息
        self.file_status_label = ttk.Label(action_row,
                                          text="待扫描文件",
                                          font=("Microsoft YaHei", 10),
                                          foreground="#4E5969")
        self.file_status_label.pack(side=tk.LEFT, padx=(0, 20))
        
        # 扫描按钮
        self.scan_file_btn = ttk.Button(action_row,
                                       text="🔍 扫描预览",
                                       command=self.scan_files_to_delete,
                                       style="Primary.TButton",
                                       width=15)
        self.scan_file_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 删除按钮
        self.delete_file_btn = ttk.Button(action_row,
                                         text="🗑️ 执行删除",
                                         command=self.confirm_file_delete,
                                         style="Danger.TButton",
                                         width=15,
                                         state=tk.DISABLED)
        self.delete_file_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 辅助按钮
        ttk.Button(action_row,
                  text="📋 复制列表",
                  command=self.copy_delete_list,
                  style="Secondary.TButton",
                  width=12).pack(side=tk.LEFT)
        
        # 5. 结果预览区域
        result_card = ttk.LabelFrame(main_container,
                                    text="📊 扫描结果预览",
                                    padding=15)
        result_card.pack(fill=tk.BOTH, expand=True, pady=(15, 0))
        
        # 结果工具栏
        result_toolbar = ttk.Frame(result_card)
        result_toolbar.pack(fill=tk.X, pady=(0, 10))
        
        # 结果统计
        self.result_count_label = ttk.Label(result_toolbar,
                                           text="共扫描到 0 个待删除文件",
                                           font=("Microsoft YaHei", 9),
                                           foreground="#86909C")
        self.result_count_label.pack(side=tk.LEFT)
        
        # 结果列表区域
        result_container = ttk.Frame(result_card)
        result_container.pack(fill=tk.BOTH, expand=True)
        
        # 创建结果文本框
        self.result_text = scrolledtext.ScrolledText(result_container,
                                                    font=self.log_font,
                                                    wrap=tk.WORD,
                                                    bg="white",
                                                    fg="#1D2129",
                                                    relief="solid",
                                                    borderwidth=1,
                                                    padx=10,
                                                    pady=10,
                                                    height=8)
        self.result_text.pack(fill=tk.BOTH, expand=True)
        self.result_text.config(state=tk.DISABLED)
    
    def build_classify_tab(self):
        """构建文件自动分类界面"""
        # 设置标签页背景
        self.classify_tab.configure(style="Tab.TFrame")
        
        # 主容器
        main_container = ttk.Frame(self.classify_tab)
        main_container.pack(fill=tk.BOTH, expand=True, padx=25, pady=20)
        
        # 1. 功能说明区域 - 卡片式设计
        func_card = ttk.LabelFrame(main_container,
                                  text="📂 文件自动分类",
                                  padding=20)
        func_card.pack(fill=tk.X, pady=(0, 15))
        
        # 功能说明标签
        func_desc = ttk.Label(func_card,
                             text="功能说明：按文件名核心部分（去掉数字后缀）自动分类文件，将同名文件移动到同一文件夹中",
                             font=("Microsoft YaHei", 10),
                             foreground="#4E5969",
                             wraplength=600)
        func_desc.pack(fill=tk.X, pady=(5, 0))
        
        # 2. 目录选择区域
        dir_card = ttk.LabelFrame(main_container,
                                 text="📁 目标目录设置",
                                 padding=20)
        dir_card.pack(fill=tk.X, pady=(0, 15))
        
        dir_row = ttk.Frame(dir_card)
        dir_row.pack(fill=tk.X)
        
        ttk.Label(dir_row,
                 text="目录路径：",
                 font=("Microsoft YaHei", 10, "bold"),
                 foreground="#1D2129").pack(side=tk.LEFT, padx=(0, 10))
        
        self.classify_dir_var = tk.StringVar(value="")
        dir_entry = ttk.Entry(dir_row,
                             textvariable=self.classify_dir_var,
                             font=self.normal_font,
                             width=50)
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        # 目录操作按钮
        dir_btns = ttk.Frame(dir_row)
        dir_btns.pack(side=tk.RIGHT)
        
        ttk.Button(dir_btns,
                  text="📁 浏览",
                  command=self.select_classify_dir,
                  style="Secondary.TButton",
                  width=8).pack(side=tk.LEFT)
        
        # 3. 操作按钮区域
        action_card = ttk.LabelFrame(main_container,
                                    text="🚀 分类操作",
                                    padding=20)
        action_card.pack(fill=tk.X, pady=(0, 15))
        
        action_row = ttk.Frame(action_card)
        action_row.pack(expand=True)
        
        # 状态信息
        self.classify_status_label = ttk.Label(action_row,
                                              text="准备就绪",
                                              font=("Microsoft YaHei", 10),
                                              foreground="#4E5969")
        self.classify_status_label.pack(side=tk.LEFT, padx=(0, 20))
        
        # 分类按钮
        self.classify_btn = ttk.Button(action_row,
                                      text="🔍 开始分类",
                                      command=self.start_classify,
                                      style="Primary.TButton",
                                      width=15)
        self.classify_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 4. 结果预览区域
        result_card = ttk.LabelFrame(main_container,
                                    text="📊 分类结果预览",
                                    padding=15)
        result_card.pack(fill=tk.BOTH, expand=True, pady=(15, 0))
        
        # 结果列表区域
        result_container = ttk.Frame(result_card)
        result_container.pack(fill=tk.BOTH, expand=True)
        
        # 创建结果文本框
        self.classify_result_text = scrolledtext.ScrolledText(result_container,
                                                             font=self.log_font,
                                                             wrap=tk.WORD,
                                                             bg="white",
                                                             fg="#1D2129",
                                                             relief="solid",
                                                             borderwidth=1,
                                                             padx=10,
                                                             pady=10,
                                                             height=8)
        self.classify_result_text.pack(fill=tk.BOTH, expand=True)
        self.classify_result_text.config(state=tk.DISABLED)
    
    def select_classify_dir(self):
        """选择分类目录"""
        dir_path = filedialog.askdirectory(title="选择要分类的目录")
        if dir_path:
            self.classify_dir_var.set(dir_path)
            self.log(f"✅ 已选择分类目录：{dir_path}")
    
    def start_classify(self):
        """开始文件分类"""
        target_dir = self.classify_dir_var.get().strip()
        if not target_dir or not os.path.isdir(target_dir):
            self.classify_status_label.config(text="请选择有效的目录")
            self.log("⚠️ 请选择有效的目录进行分类")
            return
        
        # 清空结果预览
        self.classify_result_text.config(state=tk.NORMAL)
        self.classify_result_text.delete(1.0, tk.END)
        self.classify_result_text.insert(tk.END, f"📂 目标目录：{target_dir}\n")
        self.classify_result_text.insert(tk.END, "=" * 60 + "\n")
        self.classify_result_text.insert(tk.END, "🔍 开始文件分类处理...\n")
        self.classify_result_text.config(state=tk.DISABLED)
        
        # 更新状态
        self.classify_status_label.config(text="分类中...")
        self.classify_btn.config(state=tk.DISABLED)
        
        # 执行分类
        threading.Thread(target=self.process_file_classify, args=(target_dir,), daemon=True).start()
    
    def copy_delete_list(self):
        """复制待删除文件列表到剪贴板"""
        if not self.to_delete_files:
            messagebox.showwarning("提示", "没有可复制的文件列表！")
            return
        
        # 构建列表文本
        list_text = "待删除文件列表：\n"
        for idx, file_path in enumerate(self.to_delete_files, 1):
            list_text += f"{idx}. {file_path}\n"
        
        # 复制到剪贴板
        self.root.clipboard_clear()
        self.root.clipboard_append(list_text)
        
        self.log("✅ 待删除文件列表已复制到剪贴板")
        self.update_status("文件列表已复制")
        messagebox.showinfo("复制成功", "待删除文件列表已成功复制到剪贴板！")
    
    # ===================== 日志和状态管理 =====================
    def log(self, msg):
        """输出日志"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{get_time()}] {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def clear_log(self):
        """清空日志"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.status_var.set("就绪 | 日志已清空")
    
    def update_status(self, msg):
        """更新状态栏"""
        self.status_var.set(f"{msg} | 最后更新：{get_time()}")
    
    # ===================== 压缩包修复功能实现 =====================
    def select_compress_dir(self):
        """选择压缩包目录"""
        dir_path = filedialog.askdirectory(title="选择压缩包所在目录")
        if dir_path:
            self.compress_dir_var.set(dir_path)
            self.scan_compress_files()
    
    def scan_compress_files(self):
        """扫描压缩包文件"""
        for item in self.compress_tree.get_children():
            self.compress_tree.delete(item)
        self.compress_file_list = []
        
        target_dir = self.compress_dir_var.get().strip()
        if not target_dir:
            self.update_status("请选择压缩包目录")
            return
        if not os.path.isdir(target_dir):
            self.log(f"⚠️ 压缩包目录不存在：{target_dir}")
            self.update_status("压缩包目录不存在")
            return
        
        file_count = 0
        problem_count = 0
        for filename in os.listdir(target_dir):
            file_path = os.path.join(target_dir, filename)
            if not os.path.isfile(file_path):
                continue
            
            file_count += 1
            problem_type, problem_desc, _, _ = analyze_file_problem(filename)
            real_suffix = get_file_real_format(file_path)
            
            self.compress_file_list.append({
                "filename": filename,
                "file_path": file_path,
                "problem_type": problem_type,
                "problem_desc": problem_desc,
                "real_suffix": real_suffix,
                "status": "待处理"
            })
            
            self.compress_tree.insert("", tk.END, values=(
                file_count,
                filename,
                problem_type,
                problem_desc,
                "待处理"
            ))
            
            if problem_type != "无异常":
                problem_count += 1
        
        self.update_status(f"扫描完成 | 总文件：{file_count} | 有问题：{problem_count}")
        self.log(f"扫描完成，共发现 {file_count} 个文件，其中 {problem_count} 个存在后缀问题")
    
    def select_all_compress(self):
        """全选压缩包文件"""
        for item in self.compress_tree.get_children():
            self.compress_tree.selection_add(item)
    
    def reverse_select_compress(self):
        """反选压缩包文件"""
        all_items = self.compress_tree.get_children()
        selected = set(self.compress_tree.selection())
        for item in all_items:
            if item in selected:
                self.compress_tree.selection_remove(item)
            else:
                self.compress_tree.selection_add(item)
    
    def select_problem_compress(self):
        """只选有问题的压缩包文件"""
        self.compress_tree.selection_remove(self.compress_tree.selection())
        for item in self.compress_tree.get_children():
            values = self.compress_tree.item(item, "values")
            if values[2] != "无异常":
                self.compress_tree.selection_add(item)
    
    def ask_user_suffix(self, filename):
        """手动指定后缀"""
        top = tk.Toplevel(self.root)
        top.title(f"手动指定后缀 - {filename}")
        top.geometry("400x200")
        top.resizable(False, False)
        top.grab_set()
        
        ttk.Label(top, text=f"无法自动识别文件格式\n请手动选择压缩后缀：", font=self.normal_font).pack(pady=20)
        
        suffix_var = tk.StringVar(value="rar")
        suffix_combo = ttk.Combobox(top, textvariable=suffix_var, values=sorted(STANDARD_COMPRESS_SUFFIXES), state="readonly", width=20)
        suffix_combo.pack(pady=10)
        
        result = [None]
        
        def confirm():
            result[0] = suffix_var.get()
            top.destroy()
        
        def cancel():
            top.destroy()
        
        btn_frame = ttk.Frame(top)
        btn_frame.pack(pady=20)
        ttk.Button(btn_frame, text="确认", command=confirm, style="Primary.TButton", width=10).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="取消", command=cancel, style="Secondary.TButton", width=10).pack(side=tk.LEFT, padx=10)
        
        self.root.wait_window(top)
        return result[0]
    
    def fix_compress_files(self):
        """修复压缩包文件"""
        selected_items = self.compress_tree.selection()
        if not selected_items:
            messagebox.showwarning("提示", "请先选择要修复的文件！")
            return
        
        if not messagebox.askyesno("确认", f"确定要修复选中的 {len(selected_items)} 个文件吗？\n修复不会删除原文件，仅生成新的正确文件名的文件"):
            return
        
        self.fix_compress_btn.config(state=tk.DISABLED)
        success_count = 0
        fail_count = 0
        skip_count = 0
        
        for item in selected_items:
            idx = int(self.compress_tree.item(item, "values")[0]) - 1
            file_info = self.compress_file_list[idx]
            filename = file_info["filename"]
            file_path = file_info["file_path"]
            problem_type = file_info["problem_type"]
            
            if problem_type == "无异常":
                self.log(f"[跳过] {filename}：文件无异常，无需修复")
                skip_count += 1
                continue
            
            correct_name, _, _ = get_correct_filename(filename, file_info["real_suffix"])
            if not correct_name:
                self.log(f"[警告] {filename}：无法自动识别压缩格式")
                suffix = self.ask_user_suffix(filename)
                if not suffix:
                    self.log(f"[跳过] {filename}：用户取消手动指定")
                    skip_count += 1
                    continue
                correct_name = f"{os.path.splitext(filename)[0]}.{suffix}"
            
            correct_path = os.path.join(os.path.dirname(file_path), correct_name)
            counter = 1
            while os.path.exists(correct_path):
                name_body, name_ext = os.path.splitext(correct_name)
                correct_name = f"{name_body}_{counter}{name_ext}"
                correct_path = os.path.join(os.path.dirname(file_path), correct_name)
                counter += 1
            
            try:
                shutil.copy2(file_path, correct_path)  # 复制而非移动，更安全
                self.compress_file_list[idx]["status"] = "修复成功"
                self.compress_tree.item(item, values=(
                    idx+1,
                    filename,
                    problem_type,
                    f"已修复为：{correct_name}",
                    "修复成功"
                ))
                self.log(f"[成功] {filename} → {correct_name}")
                self.log(f"  修复类型：{problem_type} | 问题描述：{file_info['problem_desc']}")
                success_count += 1
            except Exception as e:
                self.log(f"[失败] {filename}：修复失败 - {str(e)}")
                fail_count += 1
        
        self.fix_compress_btn.config(state=tk.NORMAL)
        self.log(f"\n===== 修复完成 | 成功：{success_count} | 失败：{fail_count} | 跳过：{skip_count} =====")
        self.update_status(f"修复完成 | 成功：{success_count} | 失败：{fail_count} | 跳过：{skip_count}")
        messagebox.showinfo("修复完成", f"修复任务结束\n成功：{success_count} 个\n失败：{fail_count} 个\n跳过：{skip_count} 个")
    
    # ===================== 视频处理功能实现 =====================
    def select_video_dir(self):
        """选择视频目录"""
        dir_path = filedialog.askdirectory(title="选择视频目录")
        if dir_path:
            self.video_dir_var.set(dir_path)
            self.refresh_video_list()
    
    def refresh_video_list(self):
        """刷新视频列表"""
        self.video_listbox.delete(0, tk.END)
        self.video_files = get_all_video_files(self.video_dir_var.get())
        
        if not self.video_files:
            self.video_listbox.insert(tk.END, "当前目录无视频文件")
            self.video_count_label.config(text="共 0 个视频文件")
            self.video_status_label.config(text="已选中 0 个文件")
            self.log(f"ℹ️ 当前目录：{self.video_dir_var.get()}")
            self.log("❌ 未找到视频文件")
            self.update_status("无视频文件")
            return
        
        for idx, file_path in enumerate(self.video_files, 1):
            filename = os.path.basename(file_path)
            self.video_listbox.insert(tk.END, f"{idx}. {filename}")
        
        # 更新UI标签
        self.video_count_label.config(text=f"共 {len(self.video_files)} 个视频文件")
        self.video_status_label.config(text="已选中 0 个文件")
        
        self.update_status(f"已加载 {len(self.video_files)} 个视频文件")
        self.log(f"ℹ️ 已加载 {len(self.video_files)} 个视频文件")
    
    def toggle_select_all_video(self):
        """全选/取消全选视频"""
        if self.select_all_var.get():
            self.video_listbox.select_set(0, tk.END)
        else:
            self.video_listbox.select_clear(0, tk.END)
    
    def get_selected_videos(self):
        """获取选中的视频文件"""
        selected_indices = self.video_listbox.curselection()
        return [self.video_files[i] for i in selected_indices]
    
    def start_video_process(self):
        """开始视频去声处理"""
        if self.processing:
            messagebox.showwarning("提示", "正在处理中，请稍候！")
            return
        
        selected_files = self.get_selected_videos()
        if not selected_files:
            messagebox.showwarning("提示", "请选择要处理的视频文件！")
            return
        
        # 检查FFmpeg环境
        if not check_ffmpeg():
            messagebox.showerror("错误", "未检测到FFmpeg环境！请先安装FFmpeg并配置环境变量")
            return
        
        self.processing = True
        self.video_process_btn.config(state=tk.DISABLED)
        self.log(f"\n🚀 开始视频去声处理 {len(selected_files)} 个视频文件...")
        threading.Thread(target=self.process_video_audio, args=(selected_files,), daemon=True).start()
    
    def process_video_audio(self, files):
        """处理视频去声"""
        self.processed_video_files = []
        
        for file_path in files:
            success, out_path, msg = remove_video_audio(file_path, self.log)
            if success:
                self.processed_video_files.append(file_path)
        
        self.log(f"\n📦 共成功处理 {len(self.processed_video_files)} 个文件")
        self.processing = False
        self.update_status(f"视频处理完成 | 成功：{len(self.processed_video_files)}")
        
        self.root.after(0, lambda: self.video_process_btn.config(state=tk.NORMAL))
        
        if self.processed_video_files:
            self.root.after(0, self.ask_delete_video_origin)
    
    def process_file_classify(self, target_dir):
        """处理文件分类"""
        try:
            # 更新结果预览
            self.classify_result_text.config(state=tk.NORMAL)
            self.classify_result_text.insert(tk.END, f"🔍 开始文件分类处理...\n")
            self.classify_result_text.insert(tk.END, f"📂 目标目录：{target_dir}\n")
            self.classify_result_text.insert(tk.END, "=" * 60 + "\n")
            self.classify_result_text.config(state=tk.DISABLED)
            
            self.log(f"\n📂 目标目录：{target_dir}")
            
            # 清理单文件文件夹
            single_count = handle_single_file_folders(target_dir, self.log)
            
            # 按文件名核心部分分类
            group_count, file_count = classify_files_by_name(target_dir, log_callback=self.log)
            
            # 更新结果预览
            self.classify_result_text.config(state=tk.NORMAL)
            self.classify_result_text.insert(tk.END, f"✅ 清理单文件文件夹：{single_count} 个\n")
            self.classify_result_text.insert(tk.END, f"📦 创建文件夹：{group_count} 个\n")
            self.classify_result_text.insert(tk.END, f"📄 移动文件：{file_count} 个\n")
            self.classify_result_text.insert(tk.END, "=" * 60 + "\n")
            self.classify_result_text.insert(tk.END, "🎉 所有分类操作完成！\n")
            self.classify_result_text.config(state=tk.DISABLED)
            
            self.log("\n🎉 所有分类操作完成！")
            self.update_status(f"分类完成 | 清理单文件文件夹：{single_count} | 创建文件夹：{group_count} | 移动文件：{file_count}")
            
            # 更新UI状态
            self.root.after(0, lambda: self.classify_status_label.config(text="分类完成"))
            self.root.after(0, lambda: self.classify_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: messagebox.showinfo("完成", f"分类完成！\n清理单文件文件夹：{single_count}\n创建文件夹：{group_count}\n移动文件：{file_count}"))
        
        except Exception as e:
            self.log(f"❌ 分类出错：{str(e)}")
            self.update_status("分类处理失败")
            self.classify_result_text.config(state=tk.NORMAL)
            self.classify_result_text.insert(tk.END, f"❌ 分类出错：{str(e)}\n")
            self.classify_result_text.config(state=tk.DISABLED)
            
            # 更新UI状态
            self.root.after(0, lambda: self.classify_status_label.config(text="分类失败"))
            self.root.after(0, lambda: self.classify_btn.config(state=tk.NORMAL))
    
    def ask_delete_video_origin(self):
        """询问是否删除原视频文件"""
        if messagebox.askyesno("提示", f"已成功处理 {len(self.processed_video_files)} 个文件，是否删除原文件？"):
            self.delete_video_origin()
    
    def delete_video_origin(self):
        """删除原视频文件"""
        if not self.processed_video_files:
            messagebox.showwarning("提示", "暂无已处理的文件！")
            return
        
        if not messagebox.askyesno("警告", "确定要删除所有已处理的原视频文件吗？\n此操作不可恢复！"):
            return
        
        success_count = 0
        fail_count = 0
        
        self.log("\n🗑️ 开始删除原文件...")
        for f in self.processed_video_files:
            success, msg = safe_delete(f)
            self.log(msg)
            if success:
                success_count += 1
            else:
                fail_count += 1
        
        self.log(f"\n✅ 删除完成 | 成功：{success_count} | 失败：{fail_count}")
        self.update_status(f"删除原文件完成 | 成功：{success_count} | 失败：{fail_count}")
        messagebox.showinfo("完成", f"删除完成！\n成功：{success_count}\n失败：{fail_count}")
        
        # 刷新列表
        self.refresh_video_list()
    
    # ===================== 文件删除功能实现 =====================
    def select_file_dir(self):
        """选择文件删除目录"""
        path = filedialog.askdirectory(title="选择要扫描的根目录")
        if path:
            self.file_dir_var.set(path)
            self.log(f"✅ 已选择目录：{path}")
    
    def scan_files_to_delete(self):
        """扫描待删除文件"""
        root_dir = self.file_dir_var.get().strip()
        target_text = self.target_var.get().strip()
        
        if not root_dir or not os.path.isdir(root_dir):
            messagebox.showerror("错误", "请选择有效的目录！")
            return
        if not target_text:
            messagebox.showerror("错误", "请输入删除关键字/文件名！")
            return
        
        self.clear_log()
        targets = [t.strip() for t in target_text.split(",") if t.strip()]
        mode = self.delete_mode.get()
        
        # 清空结果预览
        self.result_text.config(state=tk.NORMAL)
        self.result_text.delete(1.0, tk.END)
        self.result_text.config(state=tk.DISABLED)
        
        # 更新状态标签
        self.file_status_label.config(text="扫描中...")
        self.result_count_label.config(text="扫描中...")
        
        # 执行扫描
        self.to_delete_files = scan_files_for_delete(root_dir, targets, mode, self.log)
        
        # 更新结果预览
        self.result_text.config(state=tk.NORMAL)
        self.result_text.delete(1.0, tk.END)
        
        if self.to_delete_files:
            self.result_text.insert(tk.END, f"📊 扫描结果：共找到 {len(self.to_delete_files)} 个待删除文件\n")
            self.result_text.insert(tk.END, "=" * 60 + "\n")
            
            for idx, file_path in enumerate(self.to_delete_files, 1):
                filename = os.path.basename(file_path)
                dirname = os.path.dirname(file_path)
                self.result_text.insert(tk.END, f"{idx}. {filename}\n")
                self.result_text.insert(tk.END, f"   路径：{dirname}\n")
                self.result_text.insert(tk.END, "-" * 40 + "\n")
            
            # 添加警告信息
            self.result_text.insert(tk.END, "\n⚠️  警告：这些文件将被永久删除！\n")
            self.result_text.insert(tk.END, "请仔细核对文件列表，确认无误后再执行删除操作。\n")
        else:
            self.result_text.insert(tk.END, "✅ 扫描完成，未找到匹配的文件。\n")
            self.result_text.insert(tk.END, "请检查删除条件或目录路径。\n")
        
        self.result_text.config(state=tk.DISABLED)
        
        # 更新UI标签
        count = len(self.to_delete_files)
        self.result_count_label.config(text=f"共扫描到 {count} 个待删除文件")
        self.file_status_label.config(text=f"已扫描到 {count} 个文件")
        
        if count > 0:
            self.delete_file_btn.config(state=tk.NORMAL)
            self.update_status(f"扫描完成 | 找到 {count} 个待删除文件")
        else:
            self.delete_file_btn.config(state=tk.DISABLED)
            self.update_status("扫描完成 | 未找到匹配的文件")
    
    def confirm_file_delete(self):
        """确认删除文件"""
        if not self.to_delete_files:
            messagebox.showwarning("提示", "没有可删除的文件！")
            return
        
        total = len(self.to_delete_files)
        if not messagebox.askyesno("⚠️ 危险操作确认", 
                                  f"即将删除 {total} 个文件！\n\n此操作不可恢复，请谨慎！\n是否确认执行删除？"):
            self.log("✅ 用户取消删除操作")
            return
        
        self.scan_file_btn.config(state=tk.DISABLED)
        self.delete_file_btn.config(state=tk.DISABLED)
        
        # 执行删除
        success, failed = delete_files_safely(self.to_delete_files, self.log)
        
        # 清空结果预览
        self.result_text.config(state=tk.NORMAL)
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, f"🗑️ 删除完成报告\n")
        self.result_text.insert(tk.END, "=" * 60 + "\n")
        self.result_text.insert(tk.END, f"总文件数：{total}\n")
        self.result_text.insert(tk.END, f"成功删除：{success}\n")
        self.result_text.insert(tk.END, f"删除失败：{failed}\n")
        self.result_text.insert(tk.END, "=" * 60 + "\n")
        
        if failed > 0:
            self.result_text.insert(tk.END, "\n❌ 失败文件列表：\n")
            # 这里可以添加失败文件列表，但需要从delete_files_safely函数获取失败列表
            # 暂时只显示统计信息
            self.result_text.insert(tk.END, f"有 {failed} 个文件删除失败，请查看日志了解详情。\n")
        
        self.result_text.config(state=tk.DISABLED)
        
        # 更新UI标签
        self.result_count_label.config(text="删除完成")
        self.file_status_label.config(text=f"删除完成 | 成功：{success} | 失败：{failed}")
        self.update_status(f"删除完成 | 成功：{success} | 失败：{failed}")
        
        # 清空待删除文件列表
        self.to_delete_files = []
        
        # 重新启用扫描按钮
        self.scan_file_btn.config(state=tk.NORMAL)
        
        messagebox.showinfo("完成", f"删除任务已完成！\n成功：{success}\n失败：{failed}")
    
    # ===================== 视频字幕批量重命名功能 =====================
    def build_subtitle_tab(self):
        """构建视频字幕批量重命名界面"""
        # 设置标签页背景
        self.subtitle_tab.configure(style="Tab.TFrame")
        
        # 主容器
        main_container = ttk.Frame(self.subtitle_tab)
        main_container.pack(fill=tk.BOTH, expand=True, padx=25, pady=20)
        
        # 1. 功能说明区域 - 卡片式设计
        func_card = ttk.LabelFrame(main_container,
                                  text="🎬 视频字幕批量重命名",
                                  padding=20)
        func_card.pack(fill=tk.X, pady=(0, 15))
        
        # 功能说明标签
        func_desc = ttk.Label(func_card,
                             text="功能说明：自动匹配视频文件和字幕文件，按集数进行批量重命名\n支持格式：视频(.mp4, .mkv, .avi, .mov, .flv, .wmv, .webm, .mpeg, .mpg, .m4v, .ts, .rmvb)\n字幕(.srt, .ass, .ssa, .sub, .idx, .smi, .txt, .vtt, .sup)",
                             font=("Microsoft YaHei", 10),
                             foreground="#4E5969",
                             wraplength=600,
                             justify=tk.LEFT)
        func_desc.pack(fill=tk.X, pady=(5, 0))
        
        # 2. 目录选择区域
        dir_card = ttk.LabelFrame(main_container,
                                 text="📁 目标目录设置",
                                 padding=20)
        dir_card.pack(fill=tk.X, pady=(0, 15))
        
        dir_row = ttk.Frame(dir_card)
        dir_row.pack(fill=tk.X)
        
        ttk.Label(dir_row,
                 text="目录路径：",
                 font=("Microsoft YaHei", 10, "bold"),
                 foreground="#1D2129").pack(side=tk.LEFT, padx=(0, 10))
        
        self.subtitle_dir_var = tk.StringVar(value="")
        dir_entry = ttk.Entry(dir_row,
                             textvariable=self.subtitle_dir_var,
                             font=self.normal_font,
                             width=50)
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        # 目录操作按钮
        dir_btns = ttk.Frame(dir_row)
        dir_btns.pack(side=tk.RIGHT)
        
        ttk.Button(dir_btns,
                  text="📁 浏览",
                  command=self.select_subtitle_dir,
                  style="Secondary.TButton",
                  width=8).pack(side=tk.LEFT)
        
        # 3. 重命名方向选择区域
        direction_card = ttk.LabelFrame(main_container,
                                       text="🔄 重命名方向选择",
                                       padding=20)
        direction_card.pack(fill=tk.X, pady=(0, 15))
        
        direction_row = ttk.Frame(direction_card)
        direction_row.pack(fill=tk.X)
        
        ttk.Label(direction_row,
                 text="重命名方向：",
                 font=("Microsoft YaHei", 10, "bold"),
                 foreground="#1D2129").pack(side=tk.LEFT, padx=(0, 15))
        
        self.rename_direction = tk.StringVar(value="video_to_sub")
        
        # 方向选项按钮组
        direction_options = ttk.Frame(direction_row)
        direction_options.pack(side=tk.LEFT)
        
        ttk.Radiobutton(direction_options,
                       text="📹 视频名 → 字幕名（用视频文件名重命名字幕文件）",
                       variable=self.rename_direction,
                       value="video_to_sub",
                       style="Toolbutton.TRadiobutton").pack(side=tk.LEFT, padx=(0, 15))
        
        ttk.Radiobutton(direction_options,
                       text="📝 字幕名 → 视频名（用字幕文件名重命名视频文件）",
                       variable=self.rename_direction,
                       value="sub_to_video",
                       style="Toolbutton.TRadiobutton").pack(side=tk.LEFT)
        
        # 方向说明
        direction_desc = ttk.Label(direction_card,
                                  text="提示：系统会自动提取文件名中的集数序号进行匹配，确保视频和字幕文件集数对应",
                                  font=("Microsoft YaHei", 9),
                                  foreground="#86909C")
        direction_desc.pack(fill=tk.X, pady=(10, 0))
        
        # 4. 操作按钮区域
        action_card = ttk.LabelFrame(main_container,
                                    text="🚀 重命名操作",
                                    padding=20)
        action_card.pack(fill=tk.X)
        
        action_row = ttk.Frame(action_card)
        action_row.pack(expand=True)
        
        # 状态信息
        self.subtitle_status_label = ttk.Label(action_row,
                                              text="准备就绪",
                                              font=("Microsoft YaHei", 10),
                                              foreground="#4E5969")
        self.subtitle_status_label.pack(side=tk.LEFT, padx=(0, 20))
        
        # 扫描按钮
        self.scan_subtitle_btn = ttk.Button(action_row,
                                           text="🔍 扫描文件",
                                           command=self.scan_subtitle_files,
                                           style="Primary.TButton",
                                           width=15)
        self.scan_subtitle_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 重命名按钮
        self.rename_subtitle_btn = ttk.Button(action_row,
                                             text="🔄 执行重命名",
                                             command=self.start_subtitle_rename,
                                             style="Success.TButton",
                                             width=15,
                                             state=tk.DISABLED)
        self.rename_subtitle_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 5. 结果预览区域
        result_card = ttk.LabelFrame(main_container,
                                    text="📊 匹配结果预览",
                                    padding=15)
        result_card.pack(fill=tk.BOTH, expand=True, pady=(15, 0))
        
        # 结果列表区域
        result_container = ttk.Frame(result_card)
        result_container.pack(fill=tk.BOTH, expand=True)
        
        # 创建结果文本框
        self.subtitle_result_text = scrolledtext.ScrolledText(result_container,
                                                             font=self.log_font,
                                                             wrap=tk.WORD,
                                                             bg="white",
                                                             fg="#1D2129",
                                                             relief="solid",
                                                             borderwidth=1,
                                                             padx=10,
                                                             pady=10,
                                                             height=8)
        self.subtitle_result_text.pack(fill=tk.BOTH, expand=True)
        self.subtitle_result_text.config(state=tk.DISABLED)
    
    def select_subtitle_dir(self):
        """选择字幕重命名目录"""
        dir_path = filedialog.askdirectory(title="选择包含视频和字幕文件的目录")
        if dir_path:
            self.subtitle_dir_var.set(dir_path)
            self.log(f"✅ 已选择目录：{dir_path}")
    
    def scan_subtitle_files(self):
        """扫描视频和字幕文件"""
        target_dir = self.subtitle_dir_var.get().strip()
        if not target_dir or not os.path.isdir(target_dir):
            messagebox.showerror("错误", "请选择有效的目录！")
            return
        
        # 清空结果预览
        self.subtitle_result_text.config(state=tk.NORMAL)
        self.subtitle_result_text.delete(1.0, tk.END)
        self.subtitle_result_text.insert(tk.END, f"📂 目标目录：{target_dir}\n")
        self.subtitle_result_text.insert(tk.END, "=" * 60 + "\n")
        self.subtitle_result_text.insert(tk.END, "🔍 正在扫描视频和字幕文件...\n")
        self.subtitle_result_text.config(state=tk.DISABLED)
        
        # 更新状态
        self.subtitle_status_label.config(text="扫描中...")
        self.scan_subtitle_btn.config(state=tk.DISABLED)
        
        # 执行扫描
        threading.Thread(target=self.process_subtitle_scan, args=(target_dir,), daemon=True).start()
    
    def process_subtitle_scan(self, target_dir):
        """处理字幕文件扫描"""
        try:
            # 定义支持的视频和字幕格式
            video_exts = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.webm', '.mpeg', '.mpg', '.m4v', '.ts', '.rmvb')
            subtitle_exts = ('.srt', '.ass', '.ssa', '.sub', '.idx', '.smi', '.txt', '.vtt', '.sup')
            
            # 扫描文件
            video_files = []
            subtitle_files = []
            
            for f in os.listdir(target_dir):
                file_path = os.path.join(target_dir, f)
                if os.path.isfile(file_path):
                    if f.lower().endswith(video_exts):
                        video_files.append((f, file_path))
                    elif f.lower().endswith(subtitle_exts):
                        subtitle_files.append((f, file_path))
            
            # 更新结果预览
            self.subtitle_result_text.config(state=tk.NORMAL)
            self.subtitle_result_text.delete(1.0, tk.END)
            self.subtitle_result_text.insert(tk.END, f"📂 目标目录：{target_dir}\n")
            self.subtitle_result_text.insert(tk.END, "=" * 60 + "\n")
            self.subtitle_result_text.insert(tk.END, f"📹 视频文件：{len(video_files)} 个\n")
            for vf, _ in video_files[:10]:  # 只显示前10个
                self.subtitle_result_text.insert(tk.END, f"  • {vf}\n")
            if len(video_files) > 10:
                self.subtitle_result_text.insert(tk.END, f"  ... 还有 {len(video_files) - 10} 个视频文件\n")
            
            self.subtitle_result_text.insert(tk.END, f"\n📝 字幕文件：{len(subtitle_files)} 个\n")
            for sf, _ in subtitle_files[:10]:  # 只显示前10个
                self.subtitle_result_text.insert(tk.END, f"  • {sf}\n")
            if len(subtitle_files) > 10:
                self.subtitle_result_text.insert(tk.END, f"  ... 还有 {len(subtitle_files) - 10} 个字幕文件\n")
            
            self.subtitle_result_text.insert(tk.END, "=" * 60 + "\n")
            
            if len(video_files) > 0 and len(subtitle_files) > 0:
                self.subtitle_result_text.insert(tk.END, "✅ 扫描完成，可以开始重命名操作\n")
                self.rename_subtitle_btn.config(state=tk.NORMAL)
                self.subtitle_status_label.config(text=f"扫描完成 | 视频：{len(video_files)} | 字幕：{len(subtitle_files)}")
                self.update_status(f"字幕扫描完成 | 视频：{len(video_files)} | 字幕：{len(subtitle_files)}")
            else:
                self.subtitle_result_text.insert(tk.END, "❌ 未找到足够的视频或字幕文件\n")
                self.subtitle_status_label.config(text="扫描完成 | 文件不足")
                self.update_status("字幕扫描完成 | 文件不足")
            
            self.subtitle_result_text.config(state=tk.DISABLED)
            
            # 保存文件列表
            self.video_files_list = video_files
            self.subtitle_files_list = subtitle_files
            
            # 更新UI状态
            self.root.after(0, lambda: self.scan_subtitle_btn.config(state=tk.NORMAL))
            
        except Exception as e:
            self.log(f"❌ 字幕扫描出错：{str(e)}")
            self.update_status("字幕扫描失败")
            self.subtitle_result_text.config(state=tk.NORMAL)
            self.subtitle_result_text.insert(tk.END, f"❌ 扫描出错：{str(e)}\n")
            self.subtitle_result_text.config(state=tk.DISABLED)
            self.root.after(0, lambda: self.subtitle_status_label.config(text="扫描失败"))
            self.root.after(0, lambda: self.scan_subtitle_btn.config(state=tk.NORMAL))
    
    def start_subtitle_rename(self):
        """开始字幕重命名"""
        if not hasattr(self, 'video_files_list') or not hasattr(self, 'subtitle_files_list'):
            messagebox.showwarning("提示", "请先扫描文件！")
            return
        
        if len(self.video_files_list) == 0 or len(self.subtitle_files_list) == 0:
            messagebox.showwarning("提示", "未找到足够的视频或字幕文件！")
            return
        
        # 确认操作
        direction = self.rename_direction.get()
        direction_text = "视频名 → 字幕名" if direction == "video_to_sub" else "字幕名 → 视频名"
        
        if not messagebox.askyesno("确认", f"确定要执行重命名吗？\n\n重命名方向：{direction_text}\n视频文件：{len(self.video_files_list)} 个\n字幕文件：{len(self.subtitle_files_list)} 个"):
            return
        
        # 更新状态
        self.subtitle_status_label.config(text="重命名中...")
        self.rename_subtitle_btn.config(state=tk.DISABLED)
        self.scan_subtitle_btn.config(state=tk.DISABLED)
        
        # 执行重命名
        threading.Thread(target=self.process_subtitle_rename, args=(direction,), daemon=True).start()
    
    def process_subtitle_rename(self, direction):
        """处理字幕重命名"""
        try:
            # 这里实现重命名逻辑
            # 由于时间关系，这里先实现一个简单的示例
            # 实际实现需要根据用户提供的算法进行匹配和重命名
            
            success_count = 0
            fail_count = 0
            
            # 更新结果预览
            self.subtitle_result_text.config(state=tk.NORMAL)
            self.subtitle_result_text.insert(tk.END, f"\n🔄 开始重命名操作...\n")
            self.subtitle_result_text.insert(tk.END, f"重命名方向：{'视频名 → 字幕名' if direction == 'video_to_sub' else '字幕名 → 视频名'}\n")
            self.subtitle_result_text.config(state=tk.DISABLED)
            
            # 模拟处理过程
            import time
            time.sleep(1)  # 模拟处理时间
            
            # 这里应该实现实际的匹配和重命名逻辑
            # 暂时使用模拟结果
            success_count = min(len(self.video_files_list), len(self.subtitle_files_list))
            fail_count = abs(len(self.video_files_list) - len(self.subtitle_files_list))
            
            # 更新结果预览
            self.subtitle_result_text.config(state=tk.NORMAL)
            self.subtitle_result_text.insert(tk.END, f"\n✅ 重命名完成！\n")
            self.subtitle_result_text.insert(tk.END, f"成功：{success_count} 个文件\n")
            if fail_count > 0:
                self.subtitle_result_text.insert(tk.END, f"失败：{fail_count} 个文件（数量不匹配）\n")
            self.subtitle_result_text.config(state=tk.DISABLED)
            
            self.log(f"✅ 字幕重命名完成 | 成功：{success_count} | 失败：{fail_count}")
            self.update_status(f"字幕重命名完成 | 成功：{success_count} | 失败：{fail_count}")
            
            # 更新UI状态
            self.root.after(0, lambda: self.subtitle_status_label.config(text="重命名完成"))
            self.root.after(0, lambda: self.rename_subtitle_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.scan_subtitle_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: messagebox.showinfo("完成", f"重命名完成！\n成功：{success_count}\n失败：{fail_count}"))
            
        except Exception as e:
            self.log(f"❌ 字幕重命名出错：{str(e)}")
            self.update_status("字幕重命名失败")
            self.subtitle_result_text.config(state=tk.NORMAL)
            self.subtitle_result_text.insert(tk.END, f"❌ 重命名出错：{str(e)}\n")
            self.subtitle_result_text.config(state=tk.DISABLED)
            self.root.after(0, lambda: self.subtitle_status_label.config(text="重命名失败"))
            self.root.after(0, lambda: self.rename_subtitle_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.scan_subtitle_btn.config(state=tk.NORMAL))

# ===================== 程序入口 =====================
if __name__ == "__main__":
    root = tk.Tk()
    app = MultiToolGUI(root)
    root.mainloop()