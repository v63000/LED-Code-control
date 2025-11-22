import os
import sys
import time
import socket
import threading
import platform
import tkinter as tk
from flask import Flask, render_template_string, request, jsonify
import vlc
import qrcode
from PIL import ImageTk # 需要 pip install pillow

# ================= 配置 =================
VIDEO_DIR = "videos"   # 视频文件夹
PORT = 8888            # 服务端口
# =======================================

# 初始化环境
if not os.path.exists(VIDEO_DIR):
    os.makedirs(VIDEO_DIR)

# 全局状态
player_instance = None
vlc_player = None
root = None
video_panel = None
is_looping = False
playlist = []
current_index = 0

app = Flask(__name__)

# --- 获取本机局域网IP ---
def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

# --- 手机端 Web 界面 (响应式设计) ---
WEB_UI = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>LED大屏中控台</title>
    <style>
        body { background-color: #121212; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 0; }
        .header { background: #1f1f1f; padding: 20px; text-align: center; border-bottom: 1px solid #333; }
        .header h1 { margin: 0; font-size: 20px; color: #00d2ff; }
        .container { padding: 15px; padding-bottom: 80px; }
        
        .card { background: #1f1f1f; border-radius: 12px; padding: 15px; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        .card-title { font-size: 14px; color: #888; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 1px; }
        
        .btn-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        .btn { border: none; padding: 15px; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer; color: white; transition: opacity 0.2s; }
        .btn:active { opacity: 0.7; }
        
        .btn-stop { background: #cf304a; grid-column: span 2; }
        .btn-refresh { background: #333; color: #aaa; grid-column: span 2; margin-top: 10px;}
        
        .file-list { list-style: none; padding: 0; margin: 0; }
        .file-item { background: #2c2c2c; border-radius: 8px; padding: 15px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }
        .file-name { font-size: 15px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 70%; }
        .btn-play { background: #00d2ff; color: #000; padding: 8px 16px; border-radius: 20px; font-size: 14px; }
        
        .status-bar { position: fixed; bottom: 0; left: 0; right: 0; background: #252525; padding: 15px; text-align: center; border-top: 1px solid #333; font-size: 14px; color: #00d2ff; }
    </style>
</head>
<body>
    <div class="header">
        <h1>📺 大屏控制中心</h1>
    </div>

    <div class="container">
        <div class="card">
            <div class="card-title">全局控制</div>
            <div class="btn-grid">
                <button class="btn btn-stop" onclick="control('stop')">⏹ 停止 / 黑屏</button>
            </div>
            <button class="btn btn-refresh" onclick="location.reload()">🔄 刷新文件列表</button>
        </div>

        <div class="card">
            <div class="card-title">视频列表 (点击播放)</div>
            <ul class="file-list">
                {% for video in videos %}
                <li class="file-item" onclick="play('{{ video }}')">
                    <span class="file-name">🎬 {{ video }}</span>
                    <button class="btn btn-play">播放</button>
                </li>
                {% endfor %}
            </ul>
        </div>
    </div>

    <div class="status-bar" id="status">设备已连接</div>

    <script>
        function control(action) {
            fetch('/api/' + action).then(res => res.json()).then(updateStatus);
        }
        function play(file) {
            fetch('/api/play?file=' + encodeURIComponent(file)).then(res => res.json()).then(updateStatus);
        }
        function updateStatus(data) {
            if(data.message) {
                document.getElementById('status').innerText = data.message;
            }
        }
    </script>
</body>
</html>
"""

# --- 后端逻辑 ---
@app.route('/')
def index():
    files = sorted([f for f in os.listdir(VIDEO_DIR) if f.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.wmv'))])
    return render_template_string(WEB_UI, videos=files)

@app.route('/api/play')
def api_play():
    filename = request.args.get('file')
    filepath = os.path.join(VIDEO_DIR, filename)
    if os.path.exists(filepath):
        play_video(filepath)
        return jsonify({"message": f"正在播放: {filename}"})
    return jsonify({"message": "文件未找到"})

@app.route('/api/stop')
def api_stop():
    stop_video()
    return jsonify({"message": "播放已停止 (黑屏)"})

# --- VLC 播放核心 ---
def play_video(path):
    global vlc_player, player_instance
    
    if vlc_player:
        vlc_player.stop()
    
    # 设置 VLC 参数
    if not player_instance:
        # --input-repeat=65535 实现单曲无限循环
        player_instance = vlc.Instance("--no-xlib", "--input-repeat=65535")
    
    vlc_player = player_instance.media_player_new()
    media = player_instance.media_new(path)
    vlc_player.set_media(media)
    
    # 跨平台嵌入窗口
    # Windows 使用 hwnd, Linux 使用 xid, Mac 使用 nsview
    plat = platform.system()
    window_id = video_panel.winfo_id()
    
    if plat == "Windows":
        vlc_player.set_hwnd(window_id)
    elif plat == "Linux":
        vlc_player.set_xwindow(window_id)
    elif plat == "Darwin": # macOS
        # macOS 嵌入比较复杂，通常需要 pyobjc，这里做个简单处理
        # 如果嵌入失败，VLC会弹出一个新窗口，这也是可接受的
        try:
            import objc
            vlc_player.set_nsobject(window_id)
        except:
            print("Mac OS 嵌入提示: 建议安装 pyobjc 库以获得最佳体验")
            pass

    vlc_player.play()

def stop_video():
    global vlc_player
    if vlc_player:
        vlc_player.stop()

# --- GUI 界面 (PC端) ---
def start_ui():
    global root, video_panel
    root = tk.Tk()
    root.title("LED播放端 - 双击全屏")
    root.configure(bg="black")
    root.geometry("800x600")
    
    # 1. 视频显示区域 (frame)
    video_panel = tk.Frame(root, bg="black")
    video_panel.pack(fill=tk.BOTH, expand=True)
    
    # 2. 覆盖在视频之上的控制层 (显示二维码)
    # 使用 place 布局悬浮在视频上方，播放时可以被隐藏或者保留
    overlay = tk.Frame(root, bg="black")
    overlay.place(relx=0.5, rely=0.5, anchor="center")
    
    ip_url = f"http://{get_ip()}:{PORT}"
    
    # 生成二维码
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(ip_url)
    qr.make(fit=True)
    img = ImageTk.PhotoImage(qr.make_image(fill_color="white", back_color="black"))
    
    lbl_qr = tk.Label(overlay, image=img, bg="black")
    lbl_qr.pack()
    
    lbl_text = tk.Label(overlay, text=f"手机扫码控制\n{ip_url}\n\n(双击窗口切换全屏)", 
                       font=("Arial", 14), fg="white", bg="black")
    lbl_text.pack(pady=10)

    # 双击全屏切换逻辑
    def toggle_fullscreen(event):
        is_full = root.attributes('-fullscreen')
        root.attributes('-fullscreen', not is_full)
        # 全屏时隐藏鼠标
        if not is_full:
            root.config(cursor="none") 
            overlay.place_forget() # 播放时隐藏二维码
        else:
            root.config(cursor="")
            overlay.place(relx=0.5, rely=0.5, anchor="center") # 退出全屏显示二维码

    root.bind("<Double-1>", toggle_fullscreen)
    root.bind("<Escape>", lambda e: root.attributes('-fullscreen', False))

    root.mainloop()

# --- 启动 ---
if __name__ == "__main__":
    # 启动 Web 服务器线程
    t = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False))
    t.daemon = True
    t.start()
    
    print(f"系统已启动，控制地址: http://{get_ip()}:{PORT}")
    print(f"请将视频文件放入 {VIDEO_DIR} 文件夹")
    
    # 启动 GUI
    start_ui()