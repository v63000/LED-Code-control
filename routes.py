import os
import shutil
import cv2
import traceback
from flask import Blueprint, request, jsonify, send_from_directory, render_template
from screeninfo import get_monitors
from PIL import Image, ImageOps

from config import VIDEO_DIR, THUMB_DIR, IDLE_DIR
from state import state
from utils import resolve_path, is_video, is_image, generate_thumbnail, safe_filename, get_thumb_url_by_path, get_video_duration, sys_monitor, exec_sys_command
from context import ctx
import player_logic

api_bp = Blueprint('api', __name__)
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index(): return render_template('index.html')
@main_bp.route('/thumbs/<path:f>')
def serve_thumb(f): return send_from_directory(THUMB_DIR, f)
@main_bp.route('/idle_imgs/<path:f>')
def serve_idle(f): return send_from_directory(IDLE_DIR, f)
@main_bp.route('/video_stream/<path:f>')
def video_stream(f):
    av = os.path.join(VIDEO_DIR, f)
    if not os.path.exists(av): return "404", 404
    return send_from_directory(os.path.dirname(av), os.path.basename(av))

@api_bp.route('/sys/<action>')
def sys_ctrl(action):
    exec_sys_command(action)
    return jsonify({"ok": True})

@api_bp.route('/status')
def get_status():
    ms = [{"id": i, "width": m.width, "height": m.height} for i, m in enumerate(get_monitors())]
    cv = {}; ct = 0; tl = 0
    # 直接读取缓存，毫秒级响应
    sys_info = sys_monitor.get_current_stats()
    
    if 0 <= state.current_idx < len(state.playlist):
        item = state.playlist[state.current_idx]
        cv = { "name": item['name'], "thumb": get_thumb_url_by_path(item['path']), "path": os.path.relpath(item['path'], VIDEO_DIR).replace('\\', '/') }
        if ctx.player.is_playing() or ctx.player.get_state() in [1, 2, 3, 4]:
            ct = ctx.player.get_time() / 1000.0; tl = ctx.player.get_length() / 1000.0
            if tl <= 0: tl = item.get('duration', 0)
    
    rp = [{ "name": i['name'], "path": i['path'], "thumb": get_thumb_url_by_path(i['path']), "duration": i.get('duration', 0) } for i in state.playlist]
    bfs = [f for f in sorted(os.listdir(IDLE_DIR)) if is_image(f)] if os.path.exists(IDLE_DIR) else []
    
    return jsonify({
        "playlist": rp, "current_idx": state.current_idx, "current_video": cv, "current_time": ct, "total_time": tl, 
        "monitors": ms, "target_monitor": state.target_monitor, "loop_mode": state.loop_mode, "volume": state.volume, 
        "is_muted": state.is_muted, "idle_image": state.idle_image, "bg_files": bfs, "is_playing": ctx.player.is_playing(),
        "sys": sys_info
    })

# ... (保留原有的 upload, library, control, mkdir, delete 等所有路由，此处省略以节省篇幅，请直接使用上个版本 routes.py 的其余部分) ...
# ⚠️ 重要：请务必保留 upload, library 等接口，或者直接复制之前 routes.py 的内容，只需修改 get_status 一处即可。
# 为方便起见，以下是完整的 routes.py 剩余部分：

@api_bp.route('/upload', methods=['POST'])
def upload_video():
    try:
        rp = request.form.get('path', ''); av, at = resolve_path(rp)
        if not av: return jsonify({"msg": "Path Error"}), 400
        if 'files' not in request.files: return jsonify({"msg": "No Files"}), 400
        c = 0
        for f in request.files.getlist('files'):
            if f and is_video(f.filename):
                fn = safe_filename(f.filename); sp = os.path.join(av, fn)
                f.save(sp); generate_thumbnail(sp, at, fn); c += 1
        return jsonify({"msg": "ok", "count": c})
    except Exception as e: return jsonify({"msg": str(e)}), 500

@api_bp.route('/bg/upload', methods=['POST'])
def upload_bg():
    try:
        c = 0
        for f in request.files.getlist('files'): 
            if f and is_image(f.filename): fn = safe_filename(f.filename); f.save(os.path.join(IDLE_DIR, fn)); c += 1
        return jsonify({"msg":"ok", "count": c})
    except Exception as e: return jsonify({"msg": str(e)}), 500

@api_bp.route('/bg/set', methods=['POST'])
def set_bg(): 
    try:
        n = request.json.get('name'); state.idle_image = n; state.save_state(); ctx.gui_invoke('update_bg'); return jsonify({"ok":True})
    except: return jsonify({"ok":False})

@api_bp.route('/bg/delete', methods=['POST'])
def del_bg(): 
    try:
        n = request.json.get('name'); p = os.path.join(IDLE_DIR, n)
        if os.path.exists(p): os.remove(p)
        if state.idle_image == n: state.idle_image = ""; state.save_state(); ctx.gui_invoke('update_bg')
        return jsonify({"ok":True})
    except: return jsonify({"ok":False})

@api_bp.route('/library')
def get_library():
    rp = request.args.get('path', ''); av, at = resolve_path(rp)
    if not av: return jsonify({"error": "path"}), 400
    dirs, files = [], []
    for i in sorted(os.listdir(av)):
        fp = os.path.join(av, i)
        if os.path.isdir(fp):
            cp = os.path.join(fp, "_folder_cover.jpg"); t = None
            if os.path.exists(cp): ts = int(os.path.getmtime(cp)); t = f"/video_stream/{os.path.join(rp, i, '_folder_cover.jpg').replace('\\', '/')}?t={ts}"
            dirs.append({"name": i, "thumb": t})
        elif is_video(i):
            if not os.path.exists(os.path.join(at, i+".jpg")): generate_thumbnail(fp, at, i)
            tf = os.path.join(at, i+".jpg"); ts = int(os.path.getmtime(tf)) if os.path.exists(tf) else 0
            files.append({"name": i, "thumb": os.path.join(rp, i+".jpg").replace('\\', '/'), "ts": ts})
    return jsonify({"current_path": rp, "folders": dirs, "files": files})

@api_bp.route('/library/mkdir', methods=['POST'])
def mkdir():
    rel = request.json.get('path',''); n = request.json.get('name',''); av, _ = resolve_path(os.path.join(rel, n))
    if av: os.makedirs(av, exist_ok=True); return jsonify({"ok":True})
    return jsonify({"ok": False})

@api_bp.route('/library/delete', methods=['POST'])
def del_item():
    try:
        p=request.json.get('path',''); n=request.json.get('name'); is_f=request.json.get('is_folder')
        bv, bt = resolve_path(p); tv=os.path.join(bv, n); tt=os.path.join(bt, n)
        if is_f: (shutil.rmtree(tv) if os.path.exists(tv) else None, shutil.rmtree(tt) if os.path.exists(tt) else None)
        else: (os.remove(tv) if os.path.exists(tv) else None, os.remove(tt+".jpg") if os.path.exists(tt+".jpg") else None)
        return jsonify({"ok":True})
    except: return jsonify({"ok":False})

@api_bp.route('/library/rename', methods=['POST'])
def ren_item():
    try:
        p=request.json.get('path',''); o=request.json.get('old_name'); n=request.json.get('new_name')
        bv, bt = resolve_path(p); ov=os.path.join(bv, o); nv=os.path.join(bv, n)
        os.rename(ov, nv); ot = os.path.join(bt, o+".jpg"); nt = os.path.join(bt, n+".jpg")
        if os.path.exists(ot): os.rename(ot, nt)
        otd = os.path.join(bt, o); ntd = os.path.join(bt, n)
        if os.path.exists(otd): os.rename(otd, ntd)
        return jsonify({"ok":True})
    except: return jsonify({"ok":False})

@api_bp.route('/library/set_frame_cover', methods=['POST'])
def set_frame_cover():
    try:
        rp=request.json.get('path', ''); fn=request.json.get('file', ''); ts=float(request.json.get('time', 0))
        av, at = resolve_path(rp); vp=os.path.join(av, fn); tp=os.path.join(at, fn+".jpg")
        cap = cv2.VideoCapture(vp); cap.set(cv2.CAP_PROP_POS_MSEC, ts * 1000); ret, f = cap.read()
        if ret:
            f = cv2.resize(f, (320, 180)); s, b = cv2.imencode(".jpg", f)
            if s: b.tofile(tp); cap.release(); return jsonify({"ok": True})
        cap.release(); return jsonify({"ok": False})
    except: return jsonify({"ok": False})

@api_bp.route('/library/set_folder_cover', methods=['POST'])
def set_folder_cover():
    try:
        rp=request.form.get('path', ''); fd=request.form.get('folder', ''); f=request.files.get('file')
        if f and is_image(f.filename):
            av, _ = resolve_path(rp); td=os.path.join(av, fd)
            if not os.path.exists(td): return jsonify({"ok": False})
            img = Image.open(f); img = ImageOps.fit(img, (320, 180), Image.Resampling.LANCZOS); img.save(os.path.join(td, "_folder_cover.jpg"))
            return jsonify({"ok": True})
        return jsonify({"ok": False})
    except: return jsonify({"ok": False})

@api_bp.route('/library/batch_delete', methods=['POST'])
def batch_delete():
    items = request.json.get('items', []); c = 0
    for i in items:
        rel=i.get('path',''); n=i.get('name',''); is_f=i.get('is_folder',False)
        bv, bt = resolve_path(rel); 
        if not bv: continue
        tv=os.path.join(bv, n); tt=os.path.join(bt, n)
        try:
            if is_f: (shutil.rmtree(tv) if os.path.exists(tv) else None, shutil.rmtree(tt) if os.path.exists(tt) else None)
            else: (os.remove(tv) if os.path.exists(tv) else None, os.remove(tt+".jpg") if os.path.exists(tt+".jpg") else None)
            c+=1
        except: pass
    return jsonify({"ok":True, "count":c})

@api_bp.route('/playlist/add')
def add_pl():
    rel=request.args.get('path',''); fname=request.args.get('file',''); av, _ = resolve_path(rel); full=os.path.join(av, fname)
    if os.path.exists(full):
        state.playlist.append({"name": fname, "path": full, "duration": get_video_duration(full)}); state.save_state()
        if len(state.playlist) == 1: player_logic.play_by_index(0)
    return jsonify({"ok": True})

@api_bp.route('/playlist/add_folder')
def add_folder_pl():
    rel=request.args.get('path',''); n=request.args.get('name',''); av, _ = resolve_path(os.path.join(rel,n)); a = 0
    if os.path.exists(av):
        for f in sorted(os.listdir(av)):
            full=os.path.join(av, f)
            if os.path.isfile(full) and is_video(f):
                state.playlist.append({"name": f, "path": full, "duration": get_video_duration(full)}); a+=1
    if a>0: state.save_state(); (player_logic.play_by_index(0) if len(state.playlist)==a else None)
    return jsonify({"ok":True, "count":a})

@api_bp.route('/playlist/remove/<int:i>')
def rem_pl(i):
    if 0<=i<len(state.playlist):
        state.playlist.pop(i); state.save_state()
        if i==state.current_idx: ctx.player.stop(); state.current_idx=-1; ctx.gui_invoke('show_bg_layer')
        elif i<state.current_idx: state.current_idx-=1
    return jsonify({"ok":True})

@api_bp.route('/playlist/clear')
def clr_pl(): ctx.player.stop(); state.playlist=[]; state.current_idx=-1; state.save_state(); ctx.gui_invoke('show_bg_layer'); return jsonify({"ok":True})

@api_bp.route('/playlist/reorder', methods=['POST'])
def reorder_playlist():
    try:
        nis = request.json.get('indices', [])
        if len(nis) != len(state.playlist): return jsonify({"ok": False})
        np = [state.playlist[i] for i in nis]
        if state.current_idx != -1:
            curr = state.playlist[state.current_idx]
            state.current_idx = np.index(curr) if curr in np else -1
        state.playlist = np; state.save_state(); return jsonify({"ok":True})
    except: return jsonify({"ok":False})

@api_bp.route('/control/<action>')
def ctrl(action):
    if action == 'pause':
        if ctx.player.is_playing(): ctx.player.pause()
        else:
            if state.current_idx == -1 and len(state.playlist) > 0: player_logic.play_by_index(0)
            else: ctx.player.play(); ctx.gui_invoke('hide_bg_layer')
    elif action == 'next': player_logic.auto_next()
    elif action == 'prev': player_logic.play_by_index((state.current_idx-1) if state.current_idx>0 else 0)
    elif action == 'stop': ctx.player.stop(); state.current_idx = -1; ctx.gui_invoke('show_bg_layer')
    return jsonify({"ok": True})

@api_bp.route('/control/seek/<float:t>')
def api_seek(t): ctx.player.set_time(int(t*1000)); return jsonify({"ok":True})
@api_bp.route('/control/toggle_loop')
def toggle_loop():
    m = ["list", "single", "random"]
    state.loop_mode = m[(m.index(state.loop_mode) + 1) % len(m)]; state.save_state(); return jsonify({"ok":True, "mode":state.loop_mode})
@api_bp.route('/play/<int:i>')
def play_idx(i): player_logic.play_by_index(i); return jsonify({"ok":True})
@api_bp.route('/set_screen/<int:i>')
def set_scr(i):
    if state.target_monitor == i: state.target_monitor = -1; ctx.gui_invoke('hide_window')
    else: state.target_monitor = i; ctx.gui_invoke('move_window', i)
    state.save_state(); return jsonify({"ok":True})
@api_bp.route('/screen/test')
def screen_test(): ctx.gui_invoke('screen_test'); return jsonify({"ok":True})
@api_bp.route('/set_volume/<int:vol>')
def set_vol(vol): state.volume=vol; state.is_muted=False; ctx.player.audio_set_mute(False); ctx.player.audio_set_volume(vol); state.save_state(); return jsonify({"ok":True})
@api_bp.route('/toggle_mute')
def mute(): state.is_muted=not state.is_muted; ctx.player.audio_set_mute(state.is_muted); state.save_state(); return jsonify({"ok":True})