import os
import cv2
import socket
import qrcode
import psutil
import time
import sys
import re
import platform
import threading
from PIL import Image, ImageDraw, ImageOps, ImageFont
from config import VIDEO_DIR, THUMB_DIR, IDLE_DIR, PORT, ALLOWED_VIDEO_EXT, ALLOWED_IMG_EXT

# 硬件依赖
try: import GPUtil
except ImportError: GPUtil = None

try: 
    import wmi
    import pythoncom
except ImportError: 
    wmi = None
    pythoncom = None

# --- 独立的硬件监控线程类 ---
class HardwareMonitor:
    def __init__(self):
        self.stats = {
            "cpu_v": 0, "cpu_n": "Loading...",
            "mem_v": 0,
            "gpu_v": 0, "gpu_n": "Detecting...",
            "net_up": "0 B/s", "net_down": "0 B/s"
        }
        self._stop_event = False
        self._last_net_io = None
        self._last_net_time = 0
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self.thread.start()

    def get_current_stats(self):
        return self.stats

    def _simplify_name(self, name):
        if not name: return "Unknown"
        name = str(name)
        for r in [r'\(R\)', r'\(TM\)', 'Corporation', 'CPU', 'Processor', 'Graphics', 'Video Controller']:
            name = re.sub(r, '', name, flags=re.I)
        name = re.sub(r'@.*', '', name)
        name = re.sub(r'NVIDIA\s*GeForce\s*', '', name, flags=re.I)
        name = re.sub(r'AMD\s*Radeon\s*', '', name, flags=re.I)
        name = re.sub(r'Intel\s*', '', name, flags=re.I)
        return " ".join(name.split())

    def _get_cpu_name(self):
        raw = platform.processor()
        # Windows WMI 优化
        if sys.platform.startswith('win') and wmi and pythoncom:
            try:
                pythoncom.CoInitialize()
                c = wmi.WMI()
                for p in c.Win32_Processor():
                    raw = p.Name; break
                pythoncom.CoUninitialize()
            except: pass
        elif sys.platform.startswith('linux'):
            try:
                with open('/proc/cpuinfo', 'r') as f:
                    for line in f:
                        if 'model name' in line: raw = line.split(':')[1].strip(); break
            except: pass
        return self._simplify_name(raw)

    def _get_gpu_info_win(self):
        usage, name = 0, None
        if not (wmi and pythoncom): return 0, None
        try:
            pythoncom.CoInitialize() # 关键：线程内初始化
            local_wmi = wmi.WMI()
            # Name
            for gpu in local_wmi.Win32_VideoController():
                n = gpu.Name
                if n and not any(x in n.lower() for x in ['rdp', 'citrix', 'vnc']):
                    name = n
                    if any(x in n.lower() for x in ['nvidia', 'amd', 'rtx', 'gtx']): break
            # Usage
            try:
                engines = local_wmi.Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine()
                if engines:
                    vals = [float(e.UtilizationPercentage) for e in engines if str(e.UtilizationPercentage).isdigit()]
                    if vals: usage = max(vals)
            except: pass
            pythoncom.CoUninitialize()
        except: pass
        return usage, self._simplify_name(name)

    def _loop(self):
        # 1. 初始化静态信息 (仅一次)
        cpu_name = self._get_cpu_name()
        gpu_name_cache = "Integrated"
        
        while not self._stop_event:
            try:
                # CPU & MEM
                cpu_v = psutil.cpu_percent(interval=None)
                mem_v = psutil.virtual_memory().percent
                
                # GPU (优先 GPUtil, 其次 WMI)
                gpu_v = 0
                nvidia_ok = False
                if GPUtil:
                    try:
                        gpus = GPUtil.getGPUs()
                        if gpus:
                            gpu_v = gpus[0].load * 100
                            gpu_name_cache = self._simplify_name(gpus[0].name)
                            nvidia_ok = True
                    except: pass
                
                if not nvidia_ok and sys.platform.startswith('win'):
                    w_v, w_n = self._get_gpu_info_win()
                    gpu_v = w_v
                    if w_n: gpu_name_cache = w_n

                # NET
                net_u = "0 B/s"; net_d = "0 B/s"
                curr_io = psutil.net_io_counters()
                curr_time = time.time()
                if self._last_net_io and self._last_net_time:
                    dur = curr_time - self._last_net_time
                    if dur > 0.1: # 避免除零或过短
                        sent = (curr_io.bytes_sent - self._last_net_io.bytes_sent) / dur
                        recv = (curr_io.bytes_recv - self._last_net_io.bytes_recv) / dur
                        def fmt(b):
                            if b<1024: return f"{int(b)} B/s"
                            elif b<1024**2: return f"{b/1024:.1f} KB/s"
                            else: return f"{b/1024**2:.1f} MB/s"
                        net_u = fmt(sent)
                        net_d = fmt(recv)
                
                self._last_net_io = curr_io
                self._last_net_time = curr_time

                # 更新状态
                self.stats = {
                    "cpu_v": round(cpu_v, 1), "cpu_n": cpu_name,
                    "mem_v": round(mem_v, 1),
                    "gpu_v": round(gpu_v, 1), "gpu_n": gpu_name_cache,
                    "net_up": net_u, "net_down": net_d
                }
            except Exception as e:
                print(f"Monitor Error: {e}")
            
            time.sleep(1.5) # 1.5秒刷新一次，足够快且不卡

# 全局单例
sys_monitor = HardwareMonitor()

def exec_sys_command(cmd):
    if cmd == 'shutdown':
        if sys.platform.startswith('win'): os.system("shutdown /s /t 1")
        else: os.system("shutdown -h now")
    elif cmd == 'exit':
        os._exit(0)

# --- 基础工具 ---
def is_video(f): return '.' in f and f.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO_EXT
def is_image(f): return '.' in f and f.rsplit('.', 1)[1].lower() in ALLOWED_IMG_EXT
def safe_filename(f): return os.path.basename(f).strip().replace('/', '').replace('\\', '')
def resolve_path(subpath):
    if subpath is None: subpath = ""
    subpath = subpath.replace('\\', '/').strip('/')
    abs_v = os.path.abspath(os.path.join(VIDEO_DIR, subpath))
    abs_t = os.path.abspath(os.path.join(THUMB_DIR, subpath))
    if not abs_v.startswith(os.path.abspath(VIDEO_DIR)): return None, None
    return abs_v, abs_t
def get_video_duration(p):
    try:
        c = cv2.VideoCapture(p)
        if c.isOpened():
            f = c.get(cv2.CAP_PROP_FRAME_COUNT); fps = c.get(cv2.CAP_PROP_FPS); c.release()
            if fps > 0: return int(f/fps)
    except: pass
    return 0
def generate_thumbnail(vp, td, fn, force=False):
    if not os.path.exists(td): os.makedirs(td, exist_ok=True)
    tn = fn + ".jpg"; tp = os.path.join(td, tn)
    if os.path.exists(tp) and not force: return tn
    try:
        c = cv2.VideoCapture(vp)
        if c.isOpened():
            c.set(cv2.CAP_PROP_POS_FRAMES, 30); ret, f = c.read()
            if not ret: c.set(cv2.CAP_PROP_POS_FRAMES, 0); ret, f = c.read()
            if ret:
                r = cv2.resize(f, (320, 180)); cv2.imencode(".jpg", r)[1].tofile(tp)
        c.release()
    except: pass
    if not os.path.exists(tp):
        try: i = Image.new('RGB', (320, 180), (44,44,46)); ImageDraw.Draw(i).ellipse((130,60,190,120), outline=(0,122,255), width=3); i.save(tp)
        except: pass
    return tn
def get_thumb_url_by_path(fp):
    try: return f"/thumbs/{os.path.relpath(fp, VIDEO_DIR).replace('\\', '/')}.jpg"
    except: return ""
def get_local_ip():
    try: s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close(); return ip
    except: return "127.0.0.1"
def create_system_background():
    try:
        ip = get_local_ip(); url = f"http://{ip}:{PORT}"; w, h = 1920, 1080
        img = Image.new('RGB', (w, h), (20, 20, 22)); draw = ImageDraw.Draw(img)
        qr = qrcode.QRCode(box_size=10, border=2); qr.add_data(url); qr.make(fit=True)
        qri = qr.make_image(fill_color="black", back_color="white").resize((300, 300), Image.Resampling.LANCZOS)
        qx = (w - 300) // 2; qy = (h - 300) // 2 - 50
        draw.rectangle((qx-10, qy-10, qx+310, qy+310), fill="white"); img.paste(qri, (qx, qy))
        try: font = ImageFont.truetype("arial.ttf", 60); sfont = ImageFont.truetype("arial.ttf", 40)
        except: font = None; sfont = None
        def dt(text, y, c, f):
            tw = draw.textlength(text, f) if f else len(text)*15
            draw.text(((w-tw)/2, y), text, fill=c, font=f)
        dt("LED Pro Media Player", qy-100, (255,255,255), font)
        dt(f"Control: {url}", qy+330, (0,160,255), sfont)
        dt("Scan QR to connect", qy+390, (180,180,180), sfont)
        fn = "_system_default_bg.jpg"; img.save(os.path.join(IDLE_DIR, fn), quality=95); return fn
    except: return None