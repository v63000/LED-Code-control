import os
import sys
import vlc
import threading
import time
import random
from config import IDLE_DIR
from state import state
from context import ctx

# VLC 启动参数优化
# --file-caching=300: 将本地缓存降为 300ms，极大减少操作延迟
# --network-caching=1000: 网络流保持 1s 缓存
vlc_args = (
    "--no-xlib --no-osd --quiet "
    "--avcodec-hw=any "
    "--file-caching=300 "     
    "--network-caching=1000 " 
    "--clock-jitter=0 --clock-synchro=0 "
    "--mmdevice-passthrough=disabled "
)

try:
    vlc_instance = vlc.Instance(vlc_args)
    if vlc_instance is None: raise Exception("VLC Init Failed")
    player = vlc_instance.media_player_new()
    ctx.player = player 
except Exception as e:
    print(f"VLC Init Error: {e}, using fallback mode.")
    vlc_instance = vlc.Instance("--no-xlib --quiet")
    player = vlc_instance.media_player_new()
    ctx.player = player

def play_by_index(idx):
    if 0 <= idx < len(state.playlist):
        state.current_idx = idx
        p = state.playlist[idx]['path']
        
        # 停止操作可能需要一点时间，但不应阻塞
        if player.is_playing(): 
            player.stop()
        
        media = vlc_instance.media_new(os.path.abspath(p))
        player.set_media(media)
        
        if ctx.video_frame:
            # update_idletasks 比 update 更轻量
            ctx.root.update_idletasks()
            if sys.platform.startswith('win'): player.set_hwnd(ctx.video_frame.winfo_id())
            elif sys.platform.startswith('linux'): player.set_xwindow(ctx.video_frame.winfo_id())
        
        ctx.gui_invoke('lift_video')
        player.play()
        
        # 重新应用音量设置
        player.audio_set_mute(state.is_muted)
        player.audio_set_volume(state.volume)
        
        if sys.platform == 'darwin': player.set_fullscreen(True)

def auto_next():
    time.sleep(0.5)
    if not state.playlist: 
        state.current_idx = -1; ctx.gui_invoke('show_bg_layer'); return
    
    if state.loop_mode == "random":
        if len(state.playlist) > 1:
            ni = random.randint(0, len(state.playlist) - 1)
            while ni == state.current_idx: ni = random.randint(0, len(state.playlist) - 1)
            play_by_index(ni)
        else: play_by_index(0)
    elif state.loop_mode == "single": 
        play_by_index(state.current_idx)
    else: 
        play_by_index((state.current_idx + 1) % len(state.playlist))

player.event_manager().event_attach(vlc.EventType.MediaPlayerEndReached, lambda e: threading.Thread(target=auto_next).start())