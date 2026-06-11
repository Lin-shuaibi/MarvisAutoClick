#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Marvis Auto Click — 模板匹配自动点击工具

基于 OpenCV 模板匹配，在屏幕上搜索"确认"按钮图案并自动点击。
支持冷却防重复（8秒），兼容 DirectInput 游戏。
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading, time, queue, sys, os, ctypes
from datetime import datetime

try: import win32gui, win32con, win32api, win32ui, win32process
except ImportError:
    tk.Tk().withdraw(); messagebox.showerror("缺少依赖","需要 pywin32\n\n  pip install pywin32"); sys.exit(1)

# ── 全局快捷键常量 ──────────────────────────────────────
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000

# F键虚拟键码
VK_MAP = {"F5":0x74,"F6":0x75,"F7":0x76,"F8":0x77,
          "F9":0x78,"F10":0x79,"F11":0x7A,"F12":0x7B}
MOD_MAP = {"无":0,"Ctrl":MOD_CONTROL,"Alt":MOD_ALT,"Shift":MOD_SHIFT}



# ── 可选依赖 ──────────────────────────────────────────────
_HAVE_PIL = False
try: from PIL import ImageGrab, Image; _HAVE_PIL = True
except: pass

# numpy 独立导入（OCR 和 cv2 都需要）
_HAVE_NP = False
try: import numpy as np; _HAVE_NP = True
except: pass

_HAVE_CV2 = False
try:
    import cv2
    if not _HAVE_NP: import numpy as np; _HAVE_NP = True
    _HAVE_CV2 = True
except: pass

def grab_screen(bbox=None):
    if not _HAVE_PIL: return None
    try: return ImageGrab.grab(bbox=bbox)
    except: return None

# ══════════════════════════════════════════════════════════════════
#  区域选择器
# ══════════════════════════════════════════════════════════════════
class RegionSelector:
    def __init__(self, parent):
        self.parent = parent
        self._result = None

    def select(self, title="按住左键拖拽选择区域  [ESC取消]"):
        if not _HAVE_PIL:
            messagebox.showerror("缺少依赖","需要 pillow\n\n  pip install pillow"); return None
        img = grab_screen()
        if img is None: messagebox.showerror("截图失败","无法截取屏幕"); return None
        from PIL import ImageTk
        photo = ImageTk.PhotoImage(img)
        w, h = img.size
        self._result = None; self._sx = self._sy = None; self._rid = None
        win = tk.Toplevel(self.parent)
        win.title(title)
        win.attributes('-fullscreen',True,'-topmost',True)
        win.focus_force()
        cv = tk.Canvas(win,width=w,height=h,highlightthickness=0,cursor='crosshair')
        cv.pack()
        cv.create_image(0,0,anchor='nw',image=photo); cv.image=photo
        def on_press(evt): self._sx,self._sy=evt.x_root,evt.y_root
        def on_drag(evt):
            if self._rid: cv.delete(self._rid)
            self._rid=cv.create_rectangle(self._sx,self._sy,evt.x_root,evt.y_root,
                outline='#ff4444',width=3,stipple='gray25')
        def on_release(evt):
            x1,y1=min(self._sx,evt.x_root),min(self._sy,evt.y_root)
            x2,y2=max(self._sx,evt.x_root),max(self._sy,evt.y_root)
            if (x2-x1)<10 or (y2-y1)<10: return
            self._result=(int(x1),int(y1),int(x2),int(y2)); win.destroy()
        cv.bind('<ButtonPress-1>',on_press)
        cv.bind('<B1-Motion>',on_drag)
        cv.bind('<ButtonRelease-1>',on_release)
        win.bind('<Escape>',lambda e:win.destroy())
        cv.create_text(w//2,30,text=title,fill='white',font=('Microsoft YaHei',16,'bold'))
        self.parent.wait_window(win)
        return self._result

# ══════════════════════════════════════════════════════════════════
#  图像差异
# ══════════════════════════════════════════════════════════════════
def image_diff(i1,i2):
    if i1 is None or i2 is None or i1.size!=i2.size: return 100.0
    try:
        w,h=i1.size; p1,p2=i1.load(),i2.load(); t,c=0,0; s=max(1,min(w,h)//50)
        for y in range(0,h,s):
            for x in range(0,w,s):
                a,b=p1[x,y],p2[x,y]; t+=abs(a[0]-b[0])+abs(a[1]-b[1])+abs(a[2]-b[2]); c+=1
        return (t/c)/2.55 if c else 0.0
    except: return 100.0

# ══════════════════════════════════════════════════════════════════
#  核心引擎
# ══════════════════════════════════════════════════════════════════
class ConfirmMonitor:
    MODE_TEMPLATE="template"
    TEMPLATE_THRESHOLD=0.8

    def __init__(self):
        self.mode=self.MODE_TEMPLATE
        self._running=False; self._thread=None; self.check_interval=1.0
        self.log_queue=queue.Queue()
        self.template_img=None; self._tm_clicked=False; self._tm_click_time=0; self._tm_cooldown=8.0; self.last_match_conf=0.0
        self.last_diff=0.0

    def start_monitoring(self,template=None,interval=0.5):
        if self._running: return False
        if template is None: return False
        self.template_img=template
        self.check_interval=max(0.1,min(5,interval))
        self._tm_clicked=False; self._tm_click_time=0; self._tm_cooldown=8.0; self.last_match_conf=0.0
        self.mode=self.MODE_TEMPLATE
        self._running=True
        self._thread=threading.Thread(target=self._loop,daemon=True)
        self._thread.start(); return True

    def stop_monitoring(self):
        self._running=False
        if self._thread: self._thread.join(timeout=2.0); self._thread=None
    @property
    def is_running(self): return self._running
    def test_click_at(self,cx,cy): self._do_click(cx,cy)

    def _do_click(self, cx, cy):
        """Click simulation - tries SendInput + mouse_event + SendMessage"""
        # Move mouse to the click position
        win32api.SetCursorPos((cx, cy))
        time.sleep(0.15)
        # Bring target window to foreground
        try:
            hwnd = win32gui.WindowFromPoint((cx, cy))
            if hwnd:
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                tid = win32process.GetWindowThreadProcessId(hwnd)[0]
                cur_tid = win32api.GetCurrentThreadId()
                win32process.AttachThreadInput(cur_tid, tid, True)
                win32gui.SetForegroundWindow(hwnd)
                win32process.AttachThreadInput(cur_tid, tid, False)
                time.sleep(0.1)
        except:
            pass
        # === Method 1: SendInput (for DirectInput games) ===
        import struct
        is_64 = ctypes.sizeof(ctypes.c_void_p) == 8
        expected = 40 if is_64 else 28
        for flags in [win32con.MOUSEEVENTF_LEFTDOWN, win32con.MOUSEEVENTF_LEFTUP]:
            buf = struct.pack('=I', 0)
            if is_64:
                buf += struct.pack('=I', 0)
            buf += struct.pack('=iiIII', 0, 0, 0, flags, 0)
            if is_64:
                buf += struct.pack('=Q', 0)
            else:
                buf += struct.pack('=I', 0)
            while len(buf) < expected:
                buf += b'\x00'
            ret = ctypes.windll.user32.SendInput(1, buf, len(buf))
            time.sleep(0.05)
        if ret == 0:
            pass  # SendInput failed, try backup methods
        # === Method 2: mouse_event backup ===
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.03)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.03)
        # === Method 3: WM message backup ===
        try:
            hwnd = win32gui.WindowFromPoint((cx, cy))
            if hwnd:
                wp = win32api.MAKELONG(cx & 0xFFFF, cy & 0xFFFF)
                win32gui.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, wp)
                time.sleep(0.02)
                win32gui.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, wp)
        except:
            pass
    def _loop(self):
        try:
            self._template_loop()
        finally: self.log_queue.put(("stop","■ 已停止"))

    # ── 模板匹配模式 ──────────────────────────────────────────
    def _template_loop(self):
        if not _HAVE_CV2: self.log_queue.put(("error","需要 opencv-python")); return
        if not _HAVE_PIL: self.log_queue.put(("error","需要 pillow")); return
        tmpl_np=np.array(self.template_img)
        tmpl_gray=cv2.cvtColor(tmpl_np,cv2.COLOR_RGB2GRAY) if len(tmpl_np.shape)==3 else tmpl_np
        th,tw=tmpl_gray.shape[:2]; self._tm_clicked=False
        self.log_queue.put(("info",f"模板匹配 {tw}x{th}  阈值{self.TEMPLATE_THRESHOLD:.2f}"))
        while self._running:
            try:
                screen=grab_screen()
                if screen is None: time.sleep(self.check_interval); continue
                snp=np.array(screen)
                sgray=cv2.cvtColor(snp,cv2.COLOR_RGB2GRAY) if len(snp.shape)==3 else snp
                res=cv2.matchTemplate(sgray,tmpl_gray,cv2.TM_CCOEFF_NORMED)
                _,mv,_,ml=cv2.minMaxLoc(res); self.last_match_conf=float(mv)
                if mv >= self.TEMPLATE_THRESHOLD:
                    cx, cy = ml[0]+tw//2, ml[1]+th//2
                    now = time.time()
                    if not self._tm_clicked:
                        self._do_click(cx, cy)
                        self._tm_clicked = True
                        self._tm_click_time = now
                        self.log_queue.put(("click", f"✓ 点击({cx},{cy})"))
                    elif now - self._tm_click_time > self._tm_cooldown:
                        self._do_click(cx, cy)
                        self._tm_click_time = now
                        self.log_queue.put(("click", f"✓ 再次({cx},{cy})"))
                else:
                    if self._tm_clicked:
                        self._tm_clicked = False
                        self.log_queue.put(("info", f"模板消失({mv:.2f}) 待命"))
            except Exception as e: self.log_queue.put(("error",str(e)))
            time.sleep(self.check_interval)


# ══════════════════════════════════════════════════════════════════
#  图形界面（精简版，仅模板匹配）
# ══════════════════════════════════════════════════════════════════
class AutoConfirmApp:
    def __init__(self,root):
        self.root=root
        self.root.title("Marvis Auto Confirm — 模板匹配点击工具")
        self.root.geometry("560x520"); self.root.minsize(480,420)
        self.root.configure(bg="#f0f0f0")
        try:
            base=getattr(sys,'_MEIPASS',os.path.dirname(os.path.abspath(__file__)))
            ico=os.path.join(base,"icon.ico")
            if os.path.exists(ico): self.root.iconbitmap(ico)
        except: pass
        self.mon=ConfirmMonitor(); self._timer=None
        self._hk_id = 1  # hotkey registration id
        self._hk_key = "F6"
        self._hk_mod = "无"
        self._build_ui()
        self._poll_log()
        self._register_hotkey()

    def _build_ui(self):
        if not _HAVE_CV2:
            ttk.Label(self.root, text="需要安装 opencv-python\n\n  pip install opencv-python numpy",
                foreground="#e74c3c", font=("", 10)).pack(pady=40)
            return

        main = ttk.Frame(self.root, padding=8)
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 0))

        f1 = ttk.LabelFrame(main, text="① 截取模板", padding=6)
        f1.pack(fill=tk.X)
        self.btn_cap = ttk.Button(f1, text="📷 框选模板", command=self.capture_template, width=14)
        self.btn_cap.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(f1, text="模板:").pack(side=tk.LEFT)
        self.tv = tk.StringVar(value="(未截取)")
        ttk.Label(f1, textvariable=self.tv, foreground="#2c3e50",
                   font=("", 9, "bold")).pack(side=tk.LEFT, padx=4)
        self.tp = ttk.Label(f1, text="")
        self.tp.pack(side=tk.RIGHT, padx=4)

        f2 = ttk.LabelFrame(main, text="② 设置", padding=6)
        f2.pack(fill=tk.X, pady=(6, 0))

        # 行1: 间隔 + 阈值 + 置信度
        row1 = ttk.Frame(f2)
        row1.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(row1, text="间隔(秒):").pack(side=tk.LEFT, padx=(0, 4))
        self.ti2 = ttk.Spinbox(row1, from_=0.1, to=3, increment=0.1,
                                textvariable=tk.StringVar(value="0.5"), width=8)
        self.ti2.pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(row1, text="阈值:").pack(side=tk.LEFT, padx=(0, 4))
        self.tsl = ttk.Scale(row1, from_=0.5, to=0.99, value=0.8,
                              orient=tk.HORIZONTAL, length=120)
        self.tsl.pack(side=tk.LEFT, padx=(0, 2))
        self.tv2 = tk.StringVar(value="0.80")
        ttk.Label(row1, textvariable=self.tv2, width=4).pack(side=tk.LEFT)
        self.tsl.config(command=lambda v: self.tv2.set(f"{float(v):.2f}"))
        ttk.Label(row1, text="置信度:").pack(side=tk.LEFT, padx=(12, 4))
        self.tc = tk.StringVar(value="-")
        ttk.Label(row1, textvariable=self.tc, foreground="#2980b9",
                   font=("Consolas", 9)).pack(side=tk.LEFT)

        # 行2: 快捷键设置
        row2 = ttk.Frame(f2)
        row2.pack(fill=tk.X)
        ttk.Label(row2, text="快捷键:").pack(side=tk.LEFT, padx=(0, 4))
        self.hk_mod = ttk.Combobox(row2, values=["无","Ctrl","Alt","Shift"],
                                    state="readonly", width=6)
        self.hk_mod.set("无")
        self.hk_mod.pack(side=tk.LEFT, padx=(0, 2))
        self.hk_key = ttk.Combobox(row2, values=["F5","F6","F7","F8","F9","F10"],
                                    state="readonly", width=5)
        self.hk_key.set("F6")
        self.hk_key.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(row2, text="(全局热键，游戏中也有效)", foreground="#999",
                   font=("", 8)).pack(side=tk.LEFT)
        # 监听热键修改
        def _on_hk_change(*_):
            self._register_hotkey()
        self.hk_mod.bind('<<ComboboxSelected>>', _on_hk_change)
        self.hk_key.bind('<<ComboboxSelected>>', _on_hk_change)

        f3 = ttk.Frame(main)
        f3.pack(fill=tk.X, pady=(6, 0))
        ctrl = ttk.LabelFrame(f3, text="③ 启动", padding=6)
        ctrl.pack(fill=tk.X)
        self.btms = ttk.Button(ctrl, text="▶ 开始匹配", command=self.start_template, width=14)
        self.btms.pack(side=tk.LEFT, padx=2)
        self.btmp = ttk.Button(ctrl, text="■ 停止", state=tk.DISABLED,
                                command=self.stop, width=8)
        self.btmp.pack(side=tk.LEFT, padx=2)
        ttk.Label(ctrl, text="状态:", font=("", 9)).pack(side=tk.LEFT, padx=(18, 4))
        self.ts3 = tk.StringVar(value="🟢 就绪")
        ttk.Label(ctrl, textvariable=self.ts3, font=("", 9, "bold")).pack(side=tk.LEFT)

        f4 = ttk.LabelFrame(main, text="💡 使用说明", padding=6)
        f4.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(f4, text=(
            "① 框选模板截取确认按钮 \n"
            "② 调阈值 → 按 F6 开始/停止匹配 \n"
            "③ 自动搜索并点击，冷却8秒防重复 \n"
            "快捷键为全局热键(游戏中也生效)，可自定义"
        ), foreground="#7f8c8d", font=("", 8)).pack(anchor='w')

        # ── 日志 ──
        fl = ttk.LabelFrame(self.root, text="📋 运行日志", padding=6)
        fl.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 6))
        self.log = scrolledtext.ScrolledText(fl, height=10, wrap=tk.WORD,
            font=("Consolas", 9), bg="#fafafa", relief=tk.FLAT, borderwidth=1)
        self.log.pack(fill=tk.BOTH, expand=True)
        self.log.tag_config("info", foreground="#555")
        self.log.tag_config("click", foreground="#27ae60", font=("Consolas", 9, "bold"))
        self.log.tag_config("error", foreground="#e74c3c")
        self.log.tag_config("stop", foreground="#e67e22")
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _log(self,m,tag="info"):
        self.log.insert(tk.END,m+"\n",tag); self.log.see(tk.END)

    def capture_template(self):
        sel=RegionSelector(self.root)
        r=sel.select("框住「确认」按钮的图案  [ESC取消]")
        if not r: return
        tmpl=grab_screen(bbox=r)
        if tmpl is None: messagebox.showerror("错误","截图失败"); return
        self.mon.template_img=tmpl; self.tv.set(f"{r[2]-r[0]}x{r[3]-r[1]}")
        try:
            from PIL import ImageTk
            w,h=tmpl.size; sc=min(120/w,120/h,1.0)
            if sc<1: tmpl=tmpl.resize((int(w*sc),int(h*sc)),Image.NEAREST)
            p=ImageTk.PhotoImage(tmpl); self.tp.config(image=p); self.tp.image=p
        except: pass
        self._log(f"已截取模板: {r[2]-r[0]}x{r[3]-r[1]}","info")

    def start_template(self):
        if self.mon.template_img is None: messagebox.showwarning("提示","请先截取模板"); return
        try: interval=max(0.1,min(3,float(self.ti2.get())))
        except: interval=0.5
        ConfirmMonitor.TEMPLATE_THRESHOLD=float(self.tsl.get())
        if self.mon.start_monitoring(template=self.mon.template_img,interval=interval):
            self._tmpl_ui(True); self._start_tconf(); self._log(f"▶ 开始模板匹配","info")

    def stop(self):
        self.mon.stop_monitoring(); self._tmpl_ui(False)

    def _tmpl_ui(self,on):
        if not hasattr(self,'btms'): return
        d,n=(tk.DISABLED,tk.NORMAL) if on else (tk.NORMAL,tk.DISABLED)
        self.btms.config(state=d);self.btmp.config(state=n);self.btn_cap.config(state=d)
        self.ti2.config(state=d);self.tsl.config(state=d)
        self.ts3.set("🔴 匹配中…" if on else "🟢 就绪");self.tc.set("-")

    def _start_tconf(self): self._upd_tc()
    def _stop_tconf(self): pass
    def _upd_tc(self):
        if self.mon.is_running and hasattr(self,'tc'):
            self.tc.set(f"{self.mon.last_match_conf:.3f}"); self.root.after(300,self._upd_tc)

    def _poll_log(self):
        # 处理日志
        try:
            while True:
                t,m=self.mon.log_queue.get_nowait(); self._log(m,t)
                if t=="stop": self._tmpl_ui(False)
        except queue.Empty: pass
        # 轮询全局热键
        self._poll_hotkey()
        self._timer=self.root.after(100,self._poll_log)

    def _register_hotkey(self):
        """注册全局热键（基于当前 UI 设置）"""
        try:
            # 先注销旧的
            try:
                hw = ctypes.windll.user32.GetParent(self.root.winfo_id())
                ctypes.windll.user32.UnregisterHotKey(hw, self._hk_id)
            except: pass
            # 读取设置
            mod_name = self.hk_mod.get() if hasattr(self,'hk_mod') else "无"
            key_name = self.hk_key.get() if hasattr(self,'hk_key') else "F6"
            vk = VK_MAP.get(key_name, 0x75)
            mod = MOD_MAP.get(mod_name, 0) | MOD_NOREPEAT
            # 注册
            hw = ctypes.windll.user32.GetParent(self.root.winfo_id())
            ret = ctypes.windll.user32.RegisterHotKey(hw, self._hk_id, mod, vk)
            self._hk_key = key_name
            self._hk_mod = mod_name
            if ret:
                self._log(f"⌨ 热键: {mod_name+'+' if mod_name else ''}{key_name}", "info")
        except Exception as e:
            pass

    def _poll_hotkey(self):
        """轮询检查是否收到 WM_HOTKEY"""
        try:
            hw = ctypes.windll.user32.GetParent(self.root.winfo_id())
            msg = ctypes.wintypes.MSG()
            while ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), hw,
                                                     WM_HOTKEY, WM_HOTKEY, 1):
                if msg.wParam == self._hk_id:
                    self._toggle_hotkey()
        except: pass

    def _toggle_hotkey(self):
        """热键触发：切换开始/停止"""
        if self.mon.is_running:
            self.stop()
            self._log(f"⌨ 热键停止", "stop")
        else:
            if self.mon.template_img is None:
                self._log(f"⌨ 请先截取模板", "error")
                return
            self.start_template()
            self._log(f"⌨ 热键启动", "info")

    def _on_closing(self):
        try:
            hw = ctypes.windll.user32.GetParent(self.root.winfo_id())
            ctypes.windll.user32.UnregisterHotKey(hw, self._hk_id)
        except: pass
        self.mon.stop_monitoring()
        if self._timer: self.root.after_cancel(self._timer)
        self.root.destroy()


# ══════════════════════════════════════════════════════════════════
#  入口
# ══════════════════════════════════════════════════════════════════
def main():
    try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except:
        try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except: pass
    root=tk.Tk()
    s=ttk.Style()
    try: s.theme_use("vista")
    except:
        try: s.theme_use("clam")
        except: pass
    AutoConfirmApp(root); root.mainloop()

if __name__=="__main__":
    main()
