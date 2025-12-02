import queue

class AppContext:
    """全局上下文，用于在 Flask 线程和 Tkinter 主线程之间共享对象"""
    def __init__(self):
        self.root = None          # Tkinter 主窗口
        self.video_frame = None   # 视频播放区域
        self.idle_label = None    # 背景图片区域
        self.gui_queue = queue.Queue() # 线程通信消息队列
        self.player = None        # VLC 播放器实例
        
    def gui_invoke(self, cmd, *args):
        """向 GUI 线程发送指令"""
        self.gui_queue.put((cmd, args))

# 单例实例
ctx = AppContext()