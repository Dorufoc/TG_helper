#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import tkinter as tk
from tkinter import messagebox, ttk
import subprocess
import importlib
import threading
import socket
import webbrowser
import queue

# MD3 Color Tokens (与web端style.css保持一致)
MD3 = {
    'primary': '#6750A4',
    'on_primary': '#FFFFFF',
    'primary_container': '#EADDFF',
    'on_primary_container': '#21005D',
    'secondary': '#625B71',
    'on_secondary': '#FFFFFF',
    'secondary_container': '#E8DEF8',
    'tertiary': '#7D5260',
    'on_tertiary': '#FFFFFF',
    'tertiary_container': '#FFD8E4',
    'error': '#B3261E',
    'on_error': '#FFFFFF',
    'success': '#386A20',
    'on_success': '#FFFFFF',
    'background': '#FFFBFE',
    'on_background': '#1C1B1F',
    'surface': '#FFFBFE',
    'on_surface': '#1C1B1F',
    'surface_container': '#F3EDF7',
    'surface_container_high': '#ECE6F0',
    'surface_container_highest': '#E6E0E9',
    'surface_variant': '#E7E0EC',
    'on_surface_variant': '#49454F',
    'outline': '#79747E',
    'outline_variant': '#CAC4D0',
    'inverse_surface': '#313033',
    'inverse_on_surface': '#F4EFF4',
    'inverse_primary': '#D0BCFF',
    'neutral95': '#F4EFF4',
    'neutral90': '#E6E1E5',
    'neutral80': '#C9C5CA',
    'neutral70': '#AEAAAE',
    'neutral50': '#787579',
    'neutral40': '#605D62',
    'neutral30': '#484649',
    'neutral20': '#313033',
    'neutral10': '#1C1B1F',
    'neutral_variant50': '#79747E',
    'neutral_variant30': '#49454F',
}


PYQT5_AVAILABLE = False
FLASK_AVAILABLE = False
SERVER_PROCESS = None
SERVER_LOG_QUEUE = queue.Queue()
SERVER_LOG_THREAD = None

# 检测PyQt5是否可用
try:
    import PyQt5
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    PYQT5_AVAILABLE = True
except ImportError:
    pass

# 检测Flask是否可用
try:
    import flask
    FLASK_AVAILABLE = True
except ImportError:
    pass

SERVER_PORT = 5000


# 需要安装的包列表
INSTALL_PACKAGES = [
    ("PyQt5", "PyQt5==5.15.9"),
    ("PyQt5-Qt5", "PyQt5-Qt5==5.15.2"),
    ("PyQt5-sip", "PyQt5-sip==12.17.1"),
    ("PyQtWebEngine", "PyQtWebEngine==5.15.7"),
    ("PyQtWebEngine-Qt5", "PyQtWebEngine-Qt5==5.15.2"),
]


def install_pyqt5_with_log(log_callback, progress_callback):
    """使用pip逐个安装PyQt5相关包，实时返回日志和进度"""
    total = len(INSTALL_PACKAGES)
    for i, (module_name, package_spec) in enumerate(INSTALL_PACKAGES):
        try:
            if module_name == "PyQtWebEngine":
                importlib.import_module("PyQt5.QtWebEngineWidgets")
            else:
                importlib.import_module(module_name.replace("-", "_"))
            log_callback(f"[{i+1}/{total}] {package_spec} 已安装，跳过")
            progress_callback(i + 1)
            continue
        except ImportError:
            pass

        log_callback(f"[{i+1}/{total}] 正在安装 {package_spec} ...")
        cmd = [sys.executable, "-m", "pip", "install", package_spec, "-i", "https://pypi.tuna.tsinghua.edu.cn/simple", "--quiet"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                log_callback(f"[{i+1}/{total}] {package_spec} 安装成功")
            else:
                error_msg = result.stderr.strip().split("\n")[-1] if result.stderr else "未知错误"
                log_callback(f"[{i+1}/{total}] {package_spec} 安装失败: {error_msg}")
                return False
        except subprocess.TimeoutExpired:
            log_callback(f"[{i+1}/{total}] {package_spec} 安装超时")
            return False
        except Exception as e:
            log_callback(f"[{i+1}/{total}] {package_spec} 安装异常: {str(e)}")
            return False
        
        progress_callback(i + 1)
    
    return True


def verify_pyqt5():
    """验证PyQt5是否正确安装"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--format=columns"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return False
        installed = result.stdout
        required = {"PyQt5", "PyQt5-Qt5", "PyQt5-sip", "PyQtWebEngine", "PyQtWebEngine-Qt5"}
        for pkg in required:
            if pkg not in installed:
                return False
        return True
    except Exception:
        return False


def launch_browser_saver_in_subprocess():
    """在新的进程中启动浏览器源代码保存器"""
    script = """
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont
from browser_source_saver import BrowserWindow

app = QApplication(sys.argv)
app.setFont(QFont("Microsoft YaHei UI"))
window = BrowserWindow()
window.show()
sys.exit(app.exec_())
"""
    subprocess.Popen([sys.executable, "-c", script], cwd=os.getcwd())


def is_port_in_use(port):
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def read_server_output(process, log_queue):
    """后台线程读取服务器输出"""
    try:
        while True:
            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    break
                continue
            log_queue.put(line.rstrip())
    except Exception:
        pass


UNINSTALL_PACKAGES = [
    "PyQtWebEngine",
    "PyQtWebEngine-Qt5",
    "PyQt5-sip",
    "PyQt5-Qt5",
    "PyQt5",
]

def uninstall_pyqt5_with_log(log_callback, progress_callback):
    """使用pip逐个卸载PyQt5相关包，实时返回日志和进度"""
    total = len(UNINSTALL_PACKAGES)
    for i, package_name in enumerate(UNINSTALL_PACKAGES):
        log_callback(f"[{i+1}/{total}] 正在卸载 {package_name} ...")
        cmd = [sys.executable, "-m", "pip", "uninstall", package_name, "-y"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                log_callback(f"[{i+1}/{total}] {package_name} 卸载成功")
            else:
                log_callback(f"[{i+1}/{total}] {package_name} 卸载完成")
        except subprocess.TimeoutExpired:
            log_callback(f"[{i+1}/{total}] {package_name} 卸载超时")
            return False
        except Exception as e:
            log_callback(f"[{i+1}/{total}] {package_name} 卸载异常: {str(e)}")
            return False
        
        progress_callback(i + 1)
    
    return True


def launch_server(log_callback):
    """启动web_server"""
    global SERVER_PROCESS, SERVER_LOG_QUEUE, SERVER_LOG_THREAD
    SERVER_LOG_QUEUE = queue.Queue()
    
    if SERVER_PROCESS is not None and SERVER_PROCESS.poll() is None:
        log_callback("服务器已在运行中")
        return True
    
    cmd = [sys.executable, "web_server.py"]
    try:
        SERVER_PROCESS = subprocess.Popen(
            cmd,
            cwd=os.getcwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        
        SERVER_LOG_THREAD = threading.Thread(target=read_server_output, args=(SERVER_PROCESS, SERVER_LOG_QUEUE), daemon=True)
        SERVER_LOG_THREAD.start()
        
        log_callback("服务器进程已启动")
        return True
    except Exception as e:
        log_callback(f"启动服务器失败: {str(e)}")
        return False


class RoundedProgress(tk.Frame):
    """MD3风格圆角线性进度条，与web端一致"""
    
    def __init__(self, parent, maximum=100, bar_height=6, track_color=None, fill_color=None, **kwargs):
        super().__init__(parent, bg=parent.cget("bg"), **kwargs)
        
        self._maximum = maximum
        self._value = 0
        self._bar_height = bar_height
        self._track_color = track_color if track_color else MD3['outline_variant']
        self._fill_color = fill_color if fill_color else MD3['primary']
        self._corner_radius = bar_height // 2
        
        self._canvas = tk.Canvas(
            self,
            height=bar_height,
            bg=parent.cget("bg"),
            highlightthickness=0,
            bd=0
        )
        self._canvas.pack(fill="x", expand=True)
        
        self._draw()
    
    def _draw(self):
        self._canvas.delete("all")
        w = self._canvas.winfo_width()
        if w <= 1:
            return
        
        h = self._bar_height
        r = self._corner_radius
        
        # 背景轨道 - 圆角矩形
        track_pts = [
            r, 0,
            w - r, 0,
            w, 0,
            w, r,
            w, h - r,
            w, h,
            w - r, h,
            r, h,
            0, h,
            0, h - r,
            0, r,
            0, 0,
        ]
        self._canvas.create_polygon(
            track_pts, smooth=True, splinesteps=36,
            fill=self._track_color, outline=""
        )
        
        # 填充部分 - 圆角矩形
        progress_ratio = self._value / self._maximum if self._maximum > 0 else 0
        fill_w = max(r, w * progress_ratio)
        
        if fill_w >= r * 2:
            fill_pts = [
                r, 0,
                fill_w - r, 0,
                fill_w, 0,
                fill_w, r,
                fill_w, h - r,
                fill_w, h,
                fill_w - r, h,
                r, h,
                0, h,
                0, h - r,
                0, r,
                0, 0,
            ]
            self._canvas.create_polygon(
                fill_pts, smooth=True, splinesteps=36,
                fill=self._fill_color, outline=""
            )
    
    def set(self, value):
        self._value = value
        self._draw()
    
    def set_maximum(self, maximum):
        self._maximum = maximum
        self._draw()
    
    def pack(self, *args, **kwargs):
        kwargs.setdefault('fill', 'x')
        super().pack(*args, **kwargs)
    
    def config(self, **kwargs):
        if 'value' in kwargs:
            self.set(kwargs['value'])
        if 'variable' in kwargs and kwargs['variable'] is not None:
            var = kwargs['variable']
            val = var.get()
            if isinstance(val, (int, float)):
                self.set(val)
    
    def configure(self, **kwargs):
        self.config(**kwargs)


class RoundedButton(tk.Frame):
    """MD3圆角填充按钮，使用Canvas绘制，与web端风格一致"""
    
    def __init__(self, parent, text, bg_color, fg_color, command, hover_color=None, disabled=False, **kwargs):
        super().__init__(parent, bg=parent.cget("bg"), **kwargs)
        
        self._text = text
        self._bg_color = bg_color
        self._fg_color = fg_color
        self._hover_color = hover_color if hover_color else bg_color
        self._command = command
        self._disabled = disabled
        self._current_bg = bg_color if not disabled else MD3['neutral70']
        self._corner_radius = 20
        self._btn_height = 48
        
        self._canvas = tk.Canvas(
            self,
            height=self._btn_height,
            bg=parent.cget("bg"),
            highlightthickness=0,
            cursor="arrow" if disabled else "hand2",
            bd=0
        )
        self._canvas.pack(fill="x", expand=True)
        
        self._shape_id = None
        self._text_id = None
        
        self._canvas.bind("<Enter>", self._on_enter)
        self._canvas.bind("<Leave>", self._on_leave)
        self._canvas.bind("<Button-1>", self._on_click)
        self._canvas.bind("<Configure>", lambda e: self.after(10, self._draw))
        
        self._draw()
    
    def _draw(self):
        self._canvas.delete("all")
        w = self._canvas.winfo_width()
        if w <= 1:
            return
        
        r = self._corner_radius
        h = self._btn_height
        
        # 使用polygon模拟圆角矩形
        points = [
            r, 0,
            w - r, 0,
            w, 0,
            w, r,
            w, h - r,
            w, h,
            w - r, h,
            r, h,
            0, h,
            0, h - r,
            0, r,
            0, 0,
        ]
        
        self._shape_id = self._canvas.create_polygon(
            points, smooth=True, splinesteps=36,
            fill=self._current_bg, outline=""
        )
        
        self._text_id = self._canvas.create_text(
            w // 2, h // 2,
            text=self._text,
            font=("Microsoft YaHei UI", 11),
            fill=self._fg_color
        )
    
    def _on_enter(self, e):
        if self._disabled:
            return
        self._current_bg = self._hover_color
        self._draw()
    
    def _on_leave(self, e):
        if self._disabled:
            return
        self._current_bg = self._bg_color
        self._draw()
    
    def _on_click(self, e):
        if self._disabled:
            return
        if self._command:
            self._command()
    
    def config(self, **kwargs):
        if 'text' in kwargs:
            self._text = kwargs['text']
            self._draw()
        if 'bg' in kwargs or 'background' in kwargs:
            c = kwargs.get('bg', kwargs.get('background'))
            self._bg_color = c
            if not self._disabled:
                self._current_bg = c
            self._draw()
        if 'fg' in kwargs or 'foreground' in kwargs:
            c = kwargs.get('fg', kwargs.get('foreground'))
            self._fg_color = c
            self._draw()
        if 'command' in kwargs:
            self._command = kwargs['command']
        if 'state' in kwargs:
            if kwargs['state'] == 'disabled':
                self._disabled = True
                self._current_bg = MD3['neutral70']
                self._canvas.config(cursor="arrow")
            else:
                self._disabled = False
                self._current_bg = self._bg_color
                self._canvas.config(cursor="hand2")
            self._draw()
    
    def configure(self, **kwargs):
        self.config(**kwargs)
    
    def pack(self, *args, **kwargs):
        kwargs.setdefault('fill', 'x')
        super().pack(*args, **kwargs)


class MainWindow:
    """主窗口：题库管理工具（使用tkinter实现，MD3风格）"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("题库管理工具")
        self.root.resizable(False, False)
        self.install_in_progress = False
        self.log_lines = []
        self.server_running = False
        self.uninstall_in_progress = False
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        for widget in self.root.winfo_children():
            widget.destroy()
        
        self.root.configure(bg=MD3['background'])
        
        # 标题区域
        title_container = tk.Frame(self.root, bg=MD3['background'])
        title_container.pack(pady=(40, 16))
        
        title_label = tk.Label(
            title_container,
            text="题库管理工具",
            font=("Microsoft YaHei UI", 22, "bold"),
            fg=MD3['on_background'],
            bg=MD3['background']
        )
        title_label.pack()
        
        # 按钮容器
        button_frame = tk.Frame(self.root, bg=MD3['surface_container'])
        button_frame.pack(pady=10, padx=24, fill="x")
        
        if PYQT5_AVAILABLE:
            self.root.geometry("480x380")
            
            # Primary按钮 - 浏览器捕捉
            self.import_button = RoundedButton(
                button_frame,
                text="手动导入题库（浏览器捕捉）",
                bg_color=MD3['primary'],
                fg_color=MD3['on_primary'],
                hover_color="#7F67BE",
                command=self.on_browser_saver_click,
                pady=8
            )
            self.import_button.pack(pady=(12, 8), padx=16)
            
            # Filled Tonal按钮 - 服务器
            self.server_button = RoundedButton(
                button_frame,
                text="启动题库服务器",
                bg_color=MD3['primary_container'],
                fg_color=MD3['on_primary_container'],
                hover_color="#D0BCFF",
                command=self.on_server_click,
                pady=8
            )
            self.server_button.pack(pady=(4, 8), padx=16)
            
            # Error按钮 - 卸载
            self.uninstall_button = RoundedButton(
                button_frame,
                text="卸载浏览器捕捉组件",
                bg_color=MD3['error'],
                fg_color=MD3['on_error'],
                hover_color="#DC362E",
                command=self.on_uninstall_click,
                pady=8
            )
            self.uninstall_button.pack(pady=(4, 12), padx=16)
            
            # 服务器状态标签
            self.server_status_label = tk.Label(
                self.root,
                text="",
                font=("Microsoft YaHei UI", 9),
                fg=MD3['neutral50'],
                bg=MD3['background']
            )
            self.server_status_label.pack(pady=2)
            
            # 服务器日志区域
            self.server_log_frame = tk.Frame(self.root, bg=MD3['background'], padx=24)
            
            server_log_label = tk.Label(
                self.server_log_frame,
                text="服务器日志",
                font=("Microsoft YaHei UI", 11, "bold"),
                fg=MD3['on_surface_variant'],
                bg=MD3['background']
            )
            server_log_label.pack(fill="x")
            
            log_container = tk.Frame(self.server_log_frame, bg=MD3['surface_container_high'])
            log_container.pack(fill="both", expand=True, pady=(6, 0))
            
            self.server_log_text = tk.Text(
                log_container,
                height=6,
                font=("Consolas", 9),
                bg=MD3['surface_container_high'],
                fg=MD3['on_surface'],
                state="disabled",
                wrap="word",
                padx=8,
                pady=4,
                bd=0
            )
            
            server_log_scroll = ttk.Scrollbar(log_container, orient="vertical", command=self.server_log_text.yview)
            self.server_log_text.configure(yscrollcommand=server_log_scroll.set)
            
            server_log_scroll.pack(side="right", fill="y")
            self.server_log_text.pack(side="left", fill="both", expand=True)
            
            self.check_server_status()
            self._poll_server_log()
        else:
            self.root.geometry("480x480")
            
            info_label = tk.Label(
                self.root,
                text="当前环境未安装PyQt5组件\n点击下方按钮自动安装",
                font=("Microsoft YaHei UI", 10),
                fg=MD3['neutral50'],
                justify="center",
                bg=MD3['background']
            )
            info_label.pack(pady=(8, 8))
            
            self.install_button = RoundedButton(
                button_frame,
                text="安装浏览器捕捉组件",
                bg_color=MD3['tertiary'],
                fg_color=MD3['on_tertiary'],
                hover_color="#986977",
                command=self.on_install_click,
                pady=8
            )
            self.install_button.pack(pady=(4, 8), padx=16)
            
            progress_frame = tk.Frame(self.root, bg=MD3['background'])
            progress_frame.pack(pady=(8, 4), padx=32, fill="x")
            
            self.progress_bar = RoundedProgress(
                progress_frame,
                maximum=len(INSTALL_PACKAGES),
                bar_height=6,
                fill_color=MD3['primary'],
                track_color=MD3['outline_variant']
            )
            self.progress_bar.pack(fill="x")
            
            self.progress_percent_label = tk.Label(
                self.root,
                text="0%",
                font=("Microsoft YaHei UI", 9),
                fg=MD3['neutral50'],
                bg=MD3['background']
            )
            self.progress_percent_label.pack()
            
            log_frame = tk.Frame(self.root, bg=MD3['background'], padx=24)
            log_frame.pack(pady=(8, 10), fill="both", expand=True)
            
            log_label = tk.Label(
                log_frame,
                text="安装日志",
                font=("Microsoft YaHei UI", 11, "bold"),
                fg=MD3['on_surface_variant'],
                bg=MD3['background'],
                anchor="w"
            )
            log_label.pack(fill="x")
            
            log_container = tk.Frame(log_frame, bg=MD3['surface_container'])
            log_container.pack(fill="both", expand=True, pady=(6, 0))
            
            self.log_text = tk.Text(
                log_container,
                height=10,
                font=("Consolas", 9),
                bg=MD3['surface_container'],
                fg=MD3['on_surface'],
                state="disabled",
                wrap="word",
                padx=8,
                pady=4,
                bd=0
            )
            
            log_scroll = ttk.Scrollbar(log_container, orient="vertical", command=self.log_text.yview)
            self.log_text.configure(yscrollcommand=log_scroll.set)
            
            log_scroll.pack(side="right", fill="y")
            self.log_text.pack(side="left", fill="both", expand=True)
    
    def on_browser_saver_click(self):
        """点击浏览器捕捉按钮"""
        try:
            launch_browser_saver_in_subprocess()
        except Exception as e:
            messagebox.showerror("启动失败", f"无法启动浏览器模块：{str(e)}")
    
    def _append_server_log(self, message):
        """向服务器日志区域追加消息"""
        if not hasattr(self, 'server_log_text'):
            return
        self.server_log_text.config(state="normal")
        self.server_log_text.insert("end", message + "\n")
        self.server_log_text.see("end")
        self.server_log_text.config(state="disabled")
    
    def _poll_server_log(self):
        """轮询服务器日志队列并显示"""
        if not hasattr(self, 'server_log_text'):
            self.root.after(500, self._poll_server_log)
            return
        
        try:
            while True:
                line = SERVER_LOG_QUEUE.get_nowait()
                self._append_server_log(line)
        except queue.Empty:
            pass
        
        global SERVER_PROCESS
        if SERVER_PROCESS is not None and SERVER_PROCESS.poll() is not None and self.server_running:
            self._append_server_log("服务器已停止")
            self.server_running = False
            self.check_server_status()
        
        self.root.after(200, self._poll_server_log)
    
    def check_server_status(self):
        """检查服务器运行状态并更新UI"""
        if not hasattr(self, 'server_status_label'):
            return
        global SERVER_PROCESS
        if SERVER_PROCESS is not None and SERVER_PROCESS.poll() is None:
            self.server_status_label.config(text=f"服务器运行中 - http://localhost:{SERVER_PORT}", fg=MD3['success'])
            self.server_button.config(text="停止题库服务器", bg=MD3['error'], fg=MD3['on_error'], command=self.on_stop_server_click)
            if not self.server_running:
                self.server_running = True
                self.server_log_frame.pack(pady=(8, 0), padx=24, fill="both", expand=True)
                self.root.geometry("480x520")
        else:
            self.server_status_label.config(text="服务器未启动", fg=MD3['neutral50'])
            self.server_button.config(text="启动题库服务器", bg=MD3['primary_container'], fg=MD3['on_primary_container'], command=self.on_server_click)
            if self.server_running:
                self.server_running = False
                self.server_log_frame.pack_forget()
                self.root.geometry("480x380")
    
    def on_server_click(self):
        """点击服务器按钮 - 启动并打开浏览器"""
        global SERVER_PROCESS
        if SERVER_PROCESS is not None and SERVER_PROCESS.poll() is None:
            webbrowser.open(f"http://localhost:{SERVER_PORT}")
            return
        
        def do_launch():
            def log_callback(msg):
                self.root.after(0, self._append_server_log, msg)
            
            success = launch_server(log_callback)
            if success:
                self.root.after(0, self._on_server_launched)
            else:
                self.root.after(0, lambda: messagebox.showerror("启动失败", "无法启动服务器"))
        
        thread = threading.Thread(target=do_launch, daemon=True)
        thread.start()
    
    def _on_server_launched(self):
        """服务器启动成功后的处理"""
        self.check_server_status()
        self._append_server_log("等待服务器就绪...")
        self.root.after(3000, lambda: webbrowser.open(f"http://localhost:{SERVER_PORT}"))
    
    def on_stop_server_click(self):
        """点击停止服务器按钮"""
        global SERVER_PROCESS
        if SERVER_PROCESS is not None and SERVER_PROCESS.poll() is None:
            SERVER_PROCESS.terminate()
            try:
                SERVER_PROCESS.wait(timeout=5)
            except subprocess.TimeoutExpired:
                SERVER_PROCESS.kill()
            SERVER_PROCESS = None
            self._append_server_log("服务器已停止")
            self.server_running = False
        self.check_server_status()
    
    def on_uninstall_click(self):
        """点击卸载按钮"""
        if not messagebox.askyesno("确认卸载", "确定要卸载浏览器捕捉组件吗？\n卸载后需要重新安装才能使用。"):
            return
        
        if hasattr(self, 'import_button'):
            self.import_button.pack_forget()
        if hasattr(self, 'server_button'):
            self.server_button.pack_forget()
        if hasattr(self, 'uninstall_button'):
            self.uninstall_button.pack_forget()
        if hasattr(self, 'server_status_label'):
            self.server_status_label.pack_forget()
        if hasattr(self, 'server_log_frame') and self.server_running:
            self.server_log_frame.pack_forget()
        
        if not hasattr(self, 'progress_bar'):
            self._create_progress_ui()
        
        self.progress_bar.set_maximum(len(UNINSTALL_PACKAGES))
        self.progress_bar.pack(fill="x", expand=True)
        self.percent_label.pack(pady=(4, 0))
        self.log_frame.pack(pady=(8, 10), padx=24, fill="both", expand=True)
        
        self.root.geometry("480x480")
        
        self.uninstall_in_progress = True
        self.progress_bar.set(0)
        self.percent_label.config(text="0%")
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")
        self._append_log("开始卸载PyQt5组件...")
        self.root.update()
        
        def log_callback(message):
            self.root.after(0, self._append_log, message)
        
        def progress_callback(current):
            self.root.after(0, self._update_uninstall_progress, current)
        
        def do_uninstall():
            success = uninstall_pyqt5_with_log(log_callback, progress_callback)
            self.root.after(0, self._on_uninstall_done, success)
        
        thread = threading.Thread(target=do_uninstall, daemon=True)
        thread.start()
    
    def _create_progress_ui(self):
        """创建共享的进度UI（安装和卸载复用）"""
        self._progress_container = tk.Frame(self.root, bg=MD3['background'])
        self._progress_container.pack(pady=(8, 4), padx=32, fill="x")
        
        self.progress_bar = RoundedProgress(
            self._progress_container,
            maximum=len(INSTALL_PACKAGES),
            bar_height=6,
            fill_color=MD3['primary'],
            track_color=MD3['outline_variant']
        )
        self.progress_bar.pack(fill="x")
        
        self.percent_label = tk.Label(
            self.root,
            text="0%",
            font=("Microsoft YaHei UI", 9),
            fg=MD3['neutral50'],
            bg=MD3['background']
        )
        self.percent_label.pack(pady=(4, 0))
        
        self.log_frame = tk.Frame(self.root, bg=MD3['background'], padx=24)
        self.log_frame.pack(pady=(8, 10), fill="both", expand=True)
        
        self._log_label = tk.Label(
            self.log_frame,
            text="日志",
            font=("Microsoft YaHei UI", 11, "bold"),
            fg=MD3['on_surface_variant'],
            bg=MD3['background'],
            anchor="w"
        )
        self._log_label.pack(fill="x")
        
        log_container = tk.Frame(self.log_frame, bg=MD3['surface_container'])
        log_container.pack(fill="both", expand=True, pady=(6, 0))
        
        self.log_text = tk.Text(
            log_container,
            height=10,
            font=("Consolas", 9),
            bg=MD3['surface_container'],
            fg=MD3['on_surface'],
            state="disabled",
            wrap="word",
            padx=8,
            pady=4,
            bd=0
        )
        
        log_scroll = ttk.Scrollbar(log_container, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        
        log_scroll.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)
    
    def _append_log(self, message):
        """向日志区域追加消息（安装界面用）"""
        self.log_text.config(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")
    
    def _update_progress(self, current):
        """更新进度条"""
        self.progress_bar.set(current)
        percent = int((current / len(INSTALL_PACKAGES)) * 100)
        self.progress_percent_label.config(text=f"{percent}%")
    
    def _update_uninstall_progress(self, current):
        """更新卸载进度条"""
        self.progress_bar.set(current)
        percent = int((current / len(UNINSTALL_PACKAGES)) * 100)
        self.percent_label.config(text=f"{percent}%")
    
    def _on_uninstall_done(self, success):
        """卸载完成后的回调"""
        if success:
            self._append_log("所有组件卸载成功，正在重启程序...")
            self.root.after(500, self._restart_app)
        else:
            self.uninstall_in_progress = False
            self._append_log("卸载过程中出现错误")
            messagebox.showerror("卸载失败", "PyQt5组件卸载失败，请重试。")
    
    def on_install_click(self):
        """点击安装按钮"""
        if self.install_in_progress:
            return
        
        self.install_in_progress = True
        self.install_button.config(state="disabled")
        self.log_lines = []
        self._update_progress(0)
        self._append_log("开始安装PyQt5组件...")
        self.root.update()
        
        def log_callback(message):
            self.root.after(0, self._append_log, message)
        
        def progress_callback(current):
            self.root.after(0, self._update_progress, current)
        
        def do_install():
            success = install_pyqt5_with_log(log_callback, progress_callback)
            self.root.after(0, self._on_install_done, success)
        
        thread = threading.Thread(target=do_install, daemon=True)
        thread.start()
    
    def _on_install_done(self, success):
        """安装完成后的回调"""
        if success and verify_pyqt5():
            self._append_log("所有组件安装成功，正在重启程序...")
            self.root.after(500, self._restart_app)
        else:
            self.install_in_progress = False
            self.install_button.config(state="normal")
            if success:
                self._append_log("安装完成但验证失败，请检查后重试")
                messagebox.showerror("安装失败", "组件已下载但验证失败，请检查网络连接后重试。")
            else:
                self._append_log("安装过程中出现错误")
                messagebox.showerror("安装失败", "PyQt5组件安装失败，请检查网络连接后重试。")
    
    def _restart_app(self):
        """重启应用程序"""
        self.root.destroy()
        os.execv(sys.executable, [sys.executable] + sys.argv)
    
    def run(self):
        """运行主循环"""
        self.root.mainloop()


if __name__ == "__main__":
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    
    main_window = MainWindow()
    main_window.run()
