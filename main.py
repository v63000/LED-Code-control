import threading
import tkinter as tk
import time
import os
import ctypes
import sys
from PIL import ImageTk, Image, ImageOps
from screeninfo import get_monitors
from flask import Flask

from config import PORT, IDLE_DIR
from state import state
from context import ctx
from routes import main_bp, api_bp
from utils import create_system_background, sys_monitor # 引入监控实例
import player_logic

# DPI 适配
try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
except: 
    try: ctypes.windll.user32.SetProcessDPIAware()
    except: pass

# 提升进程优先级
try:
    if sys.platform.startswith('win'):
        pid = os.getpid()
        h = ctypes.windll.kernel32.OpenProcess(0x0100, False, pid)
        ctypes.windll.kernel32.SetPriorityClass(h, 0x00000080) 
except: pass

def get_player_state_safe():
    if not ctx.player: return False
    # 1=Opening, 2=Buffering, 3=Playing, 4=Paused
    return ctx.player.get_state() in [1, 2, 3, 4]

def update_bg_display():
    if not state.idle_image: ctx.idle_label.config(image='', bg='black'); return
    p = os.path.join(IDLE_DIR, state.idle_image)
    if os.path.exists(p):
        try:
            ms = get_monitors()
            if state.target_monitor != -1 and state.target_monitor < len(ms):
                m = ms[state.target_monitor]; tw, th = m.width, m.height
            else: tw, th = ctx.root.winfo_screenwidth(), ctx.root.winfo_screenheight()
            if tw < 100: tw, th = 1920, 1080
            img = Image.open(p)
            img = ImageOps.fit(img, (tw, th), Image.Resampling.LANCZOS)
            tk_img = ImageTk.PhotoImage(img)
            ctx.idle_label.config(image=tk_img, bg='black')
            ctx.idle_label.image = tk_img 
            if not get_player_state_safe(): show_bg_layer()
        except: pass

def show_bg_layer(): ctx.idle_label.place(relx=0, rely=0, relwidth=1, relheight=1); ctx.idle_label.lift()
def hide_bg_layer(): ctx.idle_label.place_forget(); ctx.video_frame.update()

def _gui_screen_test():
    ms = get_monitors()
    def show_monitor(idx):
        if idx >= len(ms): return
        m = ms[idx]
        win = tk.Toplevel(ctx.root); win.overrideredirect(True)
        win.geometry(f"{m.width}x{m.height}+{m.x}+{m.y}"); win.configure(bg='#0A84FF'); win.attributes('-topmost', True)
        tk.Label(win, text=f"SCR {idx+1}\n{m.width}x{m.height}", font=("Arial", 80, "bold"), fg="white", bg="#0A84FF").pack(expand=True)
        ctx.root.after(1500, lambda: (win.destroy(), show_monitor(idx + 1)))
    show_monitor(0)

def gui_loop():
    try:
        while True:
            cmd, args = ctx.gui_queue.get_nowait()
            if cmd == 'move_window':
                i = args[0]; ms = get_monitors()
                if i < len(ms):
                    m = ms[i]
                    ctx.root.attributes('-fullscreen', False); ctx.root.deiconify()
                    ctx.root.geometry(f"{m.width}x{m.height}+{m.x}+{m.y}")
                    ctx.root.update(); ctx.root.attributes('-fullscreen', True)
                    update_bg_display()
                    if not get_player_state_safe(): show_bg_layer()
            elif cmd == 'hide_window': ctx.root.withdraw()
            elif cmd == 'screen_test': _gui_screen_test()
            elif cmd == 'show_bg_layer': show_bg_layer()
            elif cmd == 'hide_bg_layer': hide_bg_layer()
            elif cmd == 'update_bg': update_bg_display()
            elif cmd == 'lift_video': hide_bg_layer()
    except: pass
    ctx.root.after(100, gui_loop)

def start_flask():
    app = Flask(__name__)
    app.register_blueprint(main_bp); app.register_blueprint(api_bp, url_prefix='/api')
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

def main():
    # 启动监控线程
    sys_monitor.start()

    root = tk.Tk(); root.title("LED Pro"); root.configure(bg="black"); root.config(cursor="none")
    ctx.root = root
    ctx.video_frame = tk.Frame(root, bg="black"); ctx.video_frame.pack(fill=tk.BOTH, expand=True)
    ctx.idle_label = tk.Label(root, bg="black")

    t = threading.Thread(target=start_flask); t.daemon = True; t.start()

    def init():
        try:
            gui_loop(); ms = get_monitors()
            sys_bg = create_system_background()
            if not state.idle_image or state.idle_image == "_system_default_bg.jpg":
                if sys_bg: state.idle_image = sys_bg; state.save_state()
            if state.target_monitor != -1 and state.target_monitor < len(ms): ctx.gui_invoke('move_window', state.target_monitor)
            else: root.withdraw()
            update_bg_display()
            if not state.playlist and not get_player_state_safe(): show_bg_layer()
        except: pass
    
    root.after(1000, init); root.mainloop()

if __name__ == '__main__': main()