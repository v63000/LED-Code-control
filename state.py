import os
import json
from config import CONFIG_FILE

class PlayerState:
    """播放器状态管理与持久化"""
    def __init__(self):
        self.playlist = [] 
        self.current_idx = -1
        self.loop_mode = "list" # list, single, random
        self.target_monitor = -1 
        self.volume = 100
        self.is_muted = False
        self.idle_image = ""
        self.load_state()

    def save_state(self):
        data = {
            "playlist": self.playlist,
            "target_monitor": self.target_monitor,
            "loop_mode": self.loop_mode,
            "volume": self.volume,
            "is_muted": self.is_muted,
            "idle_image": self.idle_image
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except: pass

    def load_state(self):
        if not os.path.exists(CONFIG_FILE): return
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if "playlist" in data:
                self.playlist = []
                for x in data["playlist"]:
                    # 校验文件是否存在
                    if os.path.exists(x.get('path', '')):
                        if 'duration' not in x: x['duration'] = 0
                        self.playlist.append(x)
            if "target_monitor" in data: self.target_monitor = int(data["target_monitor"])
            if "loop_mode" in data: self.loop_mode = data["loop_mode"]
            if "volume" in data: self.volume = int(data["volume"])
            if "is_muted" in data: self.is_muted = bool(data.get("is_muted", False))
            if "idle_image" in data: self.idle_image = data["idle_image"]
        except: pass

state = PlayerState()