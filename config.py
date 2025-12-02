import os

# 基础路径配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 资源目录
VIDEO_DIR = os.path.join(BASE_DIR, "videos")
THUMB_DIR = os.path.join(BASE_DIR, "thumbs")
IDLE_DIR  = os.path.join(BASE_DIR, "idle_imgs")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# 服务端口
PORT = 8080

# 允许的文件格式
ALLOWED_VIDEO_EXT = {'mp4', 'avi', 'mkv', 'mov', 'wmv', 'flv', 'ts', 'webm', 'm4v', 'mpg'}
ALLOWED_IMG_EXT = {'jpg', 'jpeg', 'png', 'bmp', 'webp', 'gif'}

# 自动创建必要目录
for d in [VIDEO_DIR, THUMB_DIR, IDLE_DIR]:
    os.makedirs(d, exist_ok=True)