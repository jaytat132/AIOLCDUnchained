import time
import driver
import time
import pystray
from PIL import Image, ImageFont, ImageDraw, ImageSequence
from io import BytesIO
from mss import mss
import queue
from threading import Thread, Event, Lock
from utils import debug, timing
import json
import psutil
import sys
import os
from workers import FrameWriter
from http.server import BaseHTTPRequestHandler, HTTPServer
import base64
from socketserver import ThreadingMixIn
import shutil
from hwmonitor import hw_monitor

PORT = 30003
BASE_PATH = "."
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BASE_PATH = sys._MEIPASS

FONT_FILE = os.path.join(BASE_PATH, "fonts/Rubik-Bold.ttf")
APP_ICON = os.path.join(BASE_PATH, "images/plugin.png")

MIN_SPEED = 2
BASE_SPEED = 18

import ctypes.wintypes


stats = {
    "cpu": 0,
    "pump": 0,
    "liquid": 0,
    "cpu_temp": None,
    "gpu_temp": None,
}

SENSOR_MAP = {
    "Liquid": ("liquid", "Liquid"),
    "CPU Temp": ("cpu_temp", "CPU"),
    "GPU Temp": ("gpu_temp", "GPU"),
}

MIN_COLORS = 64
colors = MIN_COLORS * 2


lcd = driver.KrakenLCD()
lcd.setupStream()
lcd_lock = Lock()  # Serialises all USB access across threads

hw_monitor.start()
driver._usb_lock_container[0] = lcd_lock  # Replace lock in container so @debounce(setBrightness) timer uses same lock

pluginInstalled = False
try:
    CSIDL_PERSONAL = 5
    SHGFP_TYPE_CURRENT = 0
    buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
    ctypes.windll.shell32.SHGetFolderPathW(
        None, CSIDL_PERSONAL, None, SHGFP_TYPE_CURRENT, buf
    )
    shutil.copytree(
        os.path.join(BASE_PATH, "SignalRGBPlugin"),
        os.path.join(buf.value, "WhirlwindFX/Plugins/KrakenLCDBridge/"),
        dirs_exist_ok=True,
    )
    print("Successfully installed SignalRGB plugin")
    pluginInstalled = True

except Exception:
    print("Could not automatically install SignalRGB plugin")


ThreadingMixIn.daemon_threads = True


# ---------------------------------------------------------------------------
# GIF Player Thread
# ---------------------------------------------------------------------------

class GifPlayer(Thread):
    """
    Upload an animated GIF to the Kraken's internal memory and let the
    device firmware play it.  This is the same approach NZXT CAM uses:

      1. Convert the GIF to a properly-sized, palette-optimised GIF blob
         that fits within the device's 20 MB bucket.
      2. Upload the blob once via bulk USB (delete old bucket -> create ->
         writeGIF -> setLcdMode BUCKET).
      3. The device plays the animation entirely on its own -- zero USB
         traffic during playback, so no interference with wireless mice
         or other USB devices.

    The thread stays alive only to detect a stop request; it does NOT
    stream frames.
    """

    def __init__(self, lcd_dev: driver.KrakenLCD, gif_path: str,
                 rotation: int = 0, fps_str: str = "",
                 fit_mode: str = "Fill", zoom: int = 100,
                 offset_x: int = 0, offset_y: int = 0):
        Thread.__init__(self, name="GifPlayer", daemon=True)
        self.lcd = lcd_dev
        self.gif_path = gif_path
        self.rotation = rotation
        self.fps_str = fps_str
        self.fit_mode = fit_mode
        self.zoom = max(100, min(400, zoom))
        self.offset_x = max(-50, min(50, offset_x))
        self.offset_y = max(-50, min(50, offset_y))
        self._stop_event = Event()
        self._load_error = None
        self.effective_fps = 0.0

    def _get_frame_duration_ms(self):
        """Return per-frame duration in ms, or None to keep the GIF's native timing."""
        try:
            val = float(self.fps_str)
            if val > 0:
                return max(20, int(1000 / val))
        except (ValueError, TypeError):
            pass
        return None

    def _fit_frame(self, frame: Image.Image, target_w: int, target_h: int) -> Image.Image:
        """Resize a frame according to fit_mode, zoom, and offset settings."""
        src_w, src_h = frame.size

        if self.fit_mode == "Stretch":
            frame = frame.resize((target_w, target_h), Image.Resampling.LANCZOS)
        elif self.fit_mode == "Fit":
            scale = min(target_w / src_w, target_h / src_h)
            scale *= self.zoom / 100.0
            new_w = max(1, round(src_w * scale))
            new_h = max(1, round(src_h * scale))
            frame = frame.resize((new_w, new_h), Image.Resampling.LANCZOS)
            bg = Image.new("RGB", (target_w, target_h), (0, 0, 0))
            paste_x = (target_w - new_w) // 2 + round(self.offset_x / 50 * target_w / 2)
            paste_y = (target_h - new_h) // 2 + round(self.offset_y / 50 * target_h / 2)
            bg.paste(frame, (paste_x, paste_y))
            frame = bg
        else:  # Fill (default)
            scale = max(target_w / src_w, target_h / src_h)
            scale *= self.zoom / 100.0
            new_w = max(1, round(src_w * scale))
            new_h = max(1, round(src_h * scale))
            frame = frame.resize((new_w, new_h), Image.Resampling.LANCZOS)
            crop_x = (new_w - target_w) // 2 - round(self.offset_x / 50 * target_w / 2)
            crop_y = (new_h - target_h) // 2 - round(self.offset_y / 50 * target_h / 2)
            crop_x = max(0, min(crop_x, new_w - target_w))
            crop_y = max(0, min(crop_y, new_h - target_h))
            frame = frame.crop((crop_x, crop_y, crop_x + target_w, crop_y + target_h))

        return frame

    def _prepare_gif(self) -> bytes:
        """Convert and optimise the GIF to fit the device bucket (<=20 MB)."""
        img = Image.open(self.gif_path)
        resolution = self.lcd.resolution
        max_size = self.lcd.maxBucketSize

        MIN_COLORS = 16
        color_boundary = [MIN_COLORS, 256]
        gif_data = None
        previous_run = (0, 0)

        for iteration in range(20):
            colors = color_boundary[0] + (color_boundary[1] - color_boundary[0]) // 2
            byteio = BytesIO()

            frames = ImageSequence.Iterator(img)
            new_frames = []
            for frame in frames:
                frame = frame.convert("RGB").rotate(self.rotation)
                frame = self._fit_frame(frame, resolution.width, resolution.height)
                pal = frame.quantize(colors)
                new_frame = frame.quantize(
                    colors, palette=pal, dither=Image.FLOYDSTEINBERG
                )
                new_frames.append(new_frame)

            if not new_frames:
                raise Exception("GIF contained no frames")

            om = new_frames[0]
            om.info = img.info
            save_kwargs = dict(
                interlace=False,
                optimize=True,
                save_all=True,
                append_images=new_frames[1:],
            )
            frame_dur = self._get_frame_duration_ms()
            if frame_dur is not None:
                save_kwargs["duration"] = frame_dur
            om.save(byteio, "GIF", **save_kwargs)
            gif_data = byteio.getvalue()
            gif_size = len(gif_data)
            print(f"[GifPlayer] Optimisation pass {iteration+1}: {colors} colors, {gif_size/1024:.1f} KB")

            if gif_size > max_size:
                color_boundary[1] = colors
            else:
                color_boundary[0] = colors
                if (previous_run[0] <= colors and previous_run[1] == gif_size) or \
                   (color_boundary[1] - color_boundary[0] < 10):
                    break
            previous_run = (colors, gif_size)

        frame_dur = self._get_frame_duration_ms()
        if frame_dur is not None:
            self.effective_fps = 1000.0 / frame_dur
        else:
            native_dur = img.info.get('duration', 100)
            self.effective_fps = 1000.0 / max(native_dur, 1)
        timing = f"{frame_dur}ms/frame ({self.effective_fps:.1f}fps)" if frame_dur else f"native timing ({self.effective_fps:.1f}fps)"
        print(f"[GifPlayer] Final GIF: {len(gif_data)/1024:.1f} KB ({len(new_frames)} frames, {timing})")
        return gif_data

    def _upload_to_device(self, gif_data: bytes):
        """Upload the GIF blob to the device's internal memory bucket."""
        with lcd_lock:
            # Drain ALL stale HID messages that accumulated during the
            # (potentially multi-second) _prepare_gif image processing.
            # Without this, readUntil() would wade through dozens of
            # periodic status reports and never find the command response.
            self.lcd.clear()

            print("[GifPlayer] Switching to liquid mode...")
            self.lcd.setLcdMode(driver.DISPLAY_MODE.LIQUID, 0x0)
            time.sleep(0.3)
            self.lcd.clear()

            print("[GifPlayer] Preparing bucket 0...")
            try:
                self.lcd.deleteBucket(0, retries=3)
            except Exception:
                print("[GifPlayer]   delete failed (bucket may not exist), continuing")
                self.lcd.clear()

            if not self.lcd.createBucket(0, size=len(gif_data)):
                raise Exception("Failed to create bucket 0")

            print(f"[GifPlayer] Uploading {len(gif_data)/1024:.1f} KB to device...")
            if not self.lcd.writeGIF(gif_data, 0):
                raise Exception("writeGIF returned failure status")

            print("[GifPlayer] Activating bucket playback...")
            self.lcd.setLcdMode(driver.DISPLAY_MODE.BUCKET, 0x0)

        print("[GifPlayer] GIF uploaded — firmware is now playing it")

    def _recover(self):
        """Try to restore SignalRGB streaming after a failure."""
        global _current_mode
        try:
            with lcd_lock:
                self.lcd.clear()
                self.lcd.setLcdMode(driver.DISPLAY_MODE.LIQUID, 0x0)
                time.sleep(0.2)
                self.lcd.clear()
                self.lcd.setupStream()
            _current_mode = "signalrgb"
            print("[GifPlayer] Recovered — restored SignalRGB streaming")
        except Exception as e:
            print(f"[GifPlayer] Recovery also failed: {e}")

    def run(self):
        global _gif_fps
        try:
            gif_data = self._prepare_gif()
        except Exception as e:
            self._load_error = str(e)
            print(f"[GifPlayer] Failed to prepare GIF: {e}")
            self._recover()
            return

        try:
            self._upload_to_device(gif_data)
        except Exception as e:
            self._load_error = str(e)
            print(f"[GifPlayer] Failed to upload GIF: {e}")
            self._recover()
            return

        _gif_fps = self.effective_fps

        while not self._stop_event.is_set():
            time.sleep(0.5)

    def stop(self):
        self._stop_event.set()


# ---------------------------------------------------------------------------
# Global GIF state
# ---------------------------------------------------------------------------

_gif_player: GifPlayer = None
_gif_path_active: str = None
_current_mode: str = "signalrgb"   # "signalrgb" | "gif"
_gif_fps: float = 0.0
_last_gif_path: str = ""
_last_gif_rotation: int = 0
_last_gif_fps_str: str = ""
_last_gif_fit_mode: str = "Fill"
_last_gif_zoom: int = 100
_last_gif_offset_x: int = 0
_last_gif_offset_y: int = 0


def _start_gif(path: str, rotation: int = 0, fps_str: str = "",
               fit_mode: str = "Fill", zoom: int = 100,
               offset_x: int = 0, offset_y: int = 0):
    global _gif_player, _gif_path_active, _current_mode
    global _last_gif_path, _last_gif_rotation, _last_gif_fps_str
    global _last_gif_fit_mode, _last_gif_zoom, _last_gif_offset_x, _last_gif_offset_y

    if _gif_player and _gif_player.is_alive():
        _gif_player.stop()
        _gif_player.join(timeout=2)
    _gif_player = None
    _gif_path_active = None

    _current_mode = "gif"
    with lcd_lock:
        lcd.streamReady = False
    time.sleep(0.5)

    _last_gif_path = path
    _last_gif_rotation = rotation
    _last_gif_fps_str = fps_str
    _last_gif_fit_mode = fit_mode
    _last_gif_zoom = zoom
    _last_gif_offset_x = offset_x
    _last_gif_offset_y = offset_y

    _gif_player = GifPlayer(lcd, path, rotation, fps_str,
                            fit_mode, zoom, offset_x, offset_y)
    _gif_player.start()
    _gif_path_active = path
    print(f"[GifPlayer] Started: {path} (fps={fps_str or 'native'}, fit={fit_mode})")


def _stop_gif():
    global _gif_player, _gif_path_active, _current_mode
    if _gif_player and _gif_player.is_alive():
        _gif_player.stop()
        _gif_player.join(timeout=2)
    _gif_player = None
    _gif_path_active = None

    # Restore device from BUCKET/LIQUID mode back to Q565 streaming
    try:
        with lcd_lock:
            lcd.clear()
            lcd.setLcdMode(driver.DISPLAY_MODE.LIQUID, 0x0)
            time.sleep(0.2)
            lcd.clear()
            lcd.setupStream()
    except Exception as e:
        print(f"[GifPlayer] Warning: could not restore streaming mode: {e}")

    _current_mode = "signalrgb"


# ---------------------------------------------------------------------------
# HTTP Server / Raw Producer
# ---------------------------------------------------------------------------

class RawProducer(Thread):
    def __init__(self, rawBuffer: queue.Queue):
        Thread.__init__(self, name="RawProducer")
        self.daemon = True
        self.rawBuffer = rawBuffer

    def run(self):
        debug("Server worker started")
        rawBuffer = self.rawBuffer
        lastFrame = time.time()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def _set_headers(self, contentType="application/json"):
                self.send_response(200)
                self.send_header("Content-type", contentType)
                self.end_headers()

            def do_HEAD(self):
                self._set_headers()

            def do_GET(self):
                if (
                    self.path == "/images/2023elite.png"
                    or self.path == "/images/2023.png"
                    or self.path == "/images/z3.png"
                    or self.path == "/images/plugin.png"
                ):
                    file = open(BASE_PATH + self.path, "rb")
                    data = file.read()
                    file.close()
                    self._set_headers("image/png")
                    self.wfile.write(data)
                else:
                    self._set_headers()
                    info = lcd.getInfo()
                    info["gifMode"] = _current_mode == "gif"
                    info["gifPath"] = _gif_path_active or ""
                    info["gifRunning"] = _gif_player is not None and _gif_player.is_alive()
                    self.wfile.write(bytes(json.dumps(info), "utf-8"))

            def do_POST(self):
                global _current_mode
                nonlocal lastFrame
                postData = self.rfile.read(
                    int(self.headers["Content-Length"] or "0")
                )

                if self.path == "/brightness":
                    data = json.loads(postData.decode("utf-8"))
                    with lcd_lock:
                        lcd.setBrightness(data["brightness"])

                elif self.path == "/gif":
                    data = json.loads(postData.decode("utf-8"))
                    gif_path = data.get("path", "").strip()
                    rotation = int(data.get("rotation", 0))
                    fps_str = data.get("fps", "")
                    fit_mode = data.get("fitMode", "Fill")
                    zoom = int(data.get("zoom", 100))
                    offset_x = int(data.get("offsetX", 0))
                    offset_y = int(data.get("offsetY", 0))
                    if gif_path and os.path.isfile(gif_path):
                        _start_gif(gif_path, rotation, fps_str,
                                   fit_mode, zoom, offset_x, offset_y)
                    else:
                        print(f"[GifPlayer] Invalid path: {gif_path!r}")

                elif self.path == "/gif/config":
                    data = json.loads(postData.decode("utf-8"))
                    gif_path = data.get("path", "").strip()
                    if gif_path:
                        global _last_gif_path, _last_gif_rotation, _last_gif_fps_str
                        global _last_gif_fit_mode, _last_gif_zoom
                        global _last_gif_offset_x, _last_gif_offset_y
                        _last_gif_path = gif_path
                        _last_gif_rotation = int(data.get("rotation", 0))
                        _last_gif_fps_str = data.get("fps", "")
                        _last_gif_fit_mode = data.get("fitMode", "Fill")
                        _last_gif_zoom = int(data.get("zoom", 100))
                        _last_gif_offset_x = int(data.get("offsetX", 0))
                        _last_gif_offset_y = int(data.get("offsetY", 0))

                elif self.path == "/gif/stop":
                    _stop_gif()
                    print("[GifPlayer] Stopped, returning to SignalRGB canvas")

                elif self.path == "/frame":
                    if _current_mode != "gif":
                        rawTime = time.time() - lastFrame
                        rawBuffer.put((postData, rawTime))
                        lastFrame = time.time()

                self._set_headers()

        class ThreadingSimpleServer(ThreadingMixIn, HTTPServer):
            pass

        server_address = ("", PORT)
        server = ThreadingSimpleServer(server_address, Handler)
        server.serve_forever()


# ---------------------------------------------------------------------------
# Overlay Producer (unchanged from original)
# ---------------------------------------------------------------------------

class OverlayProducer(Thread):
    def __init__(self, rawBuffer: queue.Queue, frameBuffer: queue.Queue):
        Thread.__init__(self, name="OverlayProducer")
        self.daemon = True
        self.rawBuffer = rawBuffer
        self.frameBuffer = frameBuffer
        self.lastAngle = 0
        self.circleImg = Image.new("RGBA", lcd.resolution, (0, 0, 0, 0))
        self.fonts = {
            "titleFontSize": 10,
            "sensorFontSize": 100,
            "sensorLabelFontSize": 10,
            "fontTitle": ImageFont.truetype(FONT_FILE, 10),
            "fontSensor": ImageFont.truetype(FONT_FILE, 100),
            "fontSensorLabel": ImageFont.truetype(FONT_FILE, 10),
            "fontDegree": ImageFont.truetype(FONT_FILE, 10 // 3),
        }

    def updateFonts(self, data):
        if data["titleFontSize"] != self.fonts["titleFontSize"]:
            data["titleFontSize"] = data["titleFontSize"]
            self.fonts["fontTitle"] = ImageFont.truetype(
                FONT_FILE, data["titleFontSize"]
            )
        if data["sensorFontSize"] != self.fonts["sensorFontSize"]:
            data["sensorFontSize"] = data["sensorFontSize"]
            self.fonts["fontSensor"] = ImageFont.truetype(
                FONT_FILE, data["sensorFontSize"]
            )
            self.fonts["fontDegree"] = ImageFont.truetype(
                FONT_FILE, data["sensorFontSize"] // 3
            )
        if data["sensorLabelFontSize"] != self.fonts["sensorLabelFontSize"]:
            data["sensorLabelFontSize"] = data["sensorLabelFontSize"]
            self.fonts["fontSensorLabel"] = ImageFont.truetype(
                FONT_FILE, data["sensorLabelFontSize"]
            )

    def run(self):
        debug("Overlay converter worker started")
        while True:
            if self.frameBuffer.full():
                time.sleep(0.001)
                continue

            self.addOverlay(*self.rawBuffer.get())

    @timing
    def parseImage(self, data):
        raw = base64.b64decode(data["raw"])
        return (
            Image.open(BytesIO(raw))
            .convert("RGBA")
            .resize(lcd.resolution, Image.Resampling.LANCZOS)
        )

    @timing
    def renderOverlay(self, data):
        alpha = 255
        if data["composition"] == "OVERLAY":
            alpha = round((100 - data["overlayTransparency"]) * 255 / 100)
        overlay = Image.new("RGBA", data["size"], (0, 0, 0, 0))
        overlayCanvas = ImageDraw.Draw(overlay)

        if data["spinner"] == "CPU" or data["spinner"] == "PUMP":
            bands = list(self.circleImg.split())
            bands[3] = bands[3].point(lambda x: round(x / 1.1) if x > 10 else 0)
            self.circleImg = Image.merge(self.circleImg.mode, bands)
            circleCanvas = ImageDraw.Draw(self.circleImg)

            angle = MIN_SPEED + BASE_SPEED * stats[data["spinner"].lower()] / 100
            newAngle = self.lastAngle + angle
            circleCanvas.arc(
                [(0, 0), lcd.resolution],
                fill=(255, 255, 255, round(alpha / 1.05)),
                width=lcd.resolution.width // 20,
                start=self.lastAngle,
                end=self.lastAngle + angle / 2,
            )
            circleCanvas.arc(
                [(0, 0), lcd.resolution],
                fill=(255, 255, 255, alpha),
                width=lcd.resolution.width // 20,
                start=self.lastAngle + angle / 2,
                end=newAngle,
            )
            self.lastAngle = newAngle
            overlay.paste(self.circleImg)

        if data["spinner"] == "STATIC":
            overlayCanvas.ellipse(
                [(0, 0), lcd.resolution],
                outline=(255, 255, 255, alpha),
                width=lcd.resolution.width // 20,
            )
        if data["textOverlay"]:
            self.updateFonts(data)

            source = data.get("sensorSource", "Liquid")
            sensor_key, sensor_label = SENSOR_MAP.get(source, ("liquid", "Liquid"))
            sensor_val = stats.get(sensor_key)
            if sensor_val is not None:
                value_text = "{:.0f}".format(sensor_val)
            else:
                value_text = "--"

            overlayCanvas.text(
                (lcd.resolution.width // 2, lcd.resolution.height // 5),
                text=data["titleText"],
                anchor="mm",
                align="center",
                font=self.fonts["fontTitle"],
                fill=(255, 255, 255, alpha),
            )
            overlayCanvas.text(
                (lcd.resolution.width // 2, lcd.resolution.height // 2),
                text=value_text,
                anchor="mm",
                align="center",
                font=self.fonts["fontSensor"],
                fill=(255, 255, 255, alpha),
            )
            textBbox = overlayCanvas.textbbox(
                (lcd.resolution.width // 2, lcd.resolution.height // 2),
                text=value_text,
                anchor="mm",
                align="center",
                font=self.fonts["fontSensor"],
            )
            overlayCanvas.text(
                ((textBbox[2], textBbox[1])),
                text="°",
                anchor="lt",
                align="center",
                font=self.fonts["fontDegree"],
                fill=(255, 255, 255, alpha),
            )
            overlayCanvas.text(
                (lcd.resolution.width // 2, 4 * lcd.resolution.height // 5),
                text=sensor_label,
                anchor="mm",
                align="center",
                font=self.fonts["fontSensorLabel"],
                fill=(255, 255, 255, alpha),
            )

        return overlay.rotate(data["rotation"])

    @timing
    def compose(self, data, img, overlay):
        if data["composition"] == "MIX":
            return Image.composite(
                img, Image.new("RGBA", img.size, (0, 0, 0, 0)), overlay
            )
        if data["composition"] == "OVERLAY":
            return Image.alpha_composite(img, overlay)

    @timing
    def addOverlay(self, postData, rawTime):
        startTime = time.time()
        data = json.loads(postData.decode("utf-8"))
        data["size"] = lcd.resolution
        img = self.parseImage(data)

        if data["composition"] != "OFF":
            overlay = self.renderOverlay(data)
            img = self.compose(data, img, overlay)

        overlayTime = time.time() - startTime
        self.frameBuffer.put(
            (
                lcd.imageToFrame(img, adaptive=data["colorPalette"] == "ADAPTIVE"),
                rawTime,
                overlayTime,
            )
        )


class StatsProducer(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True

    def run(self):
        debug("CPU stats producer started")
        while True:
            stats["cpu"] = psutil.cpu_percent(1)
            if hw_monitor.available:
                stats.update(hw_monitor.get_temps())


class Systray(Thread):
    def __init__(self):
        Thread.__init__(self)
        from pystray._util import win32
        win32.WM_LBUTTONUP = 0x0205
        win32.WM_RBUTTONUP = 0x0202

        self.menu = pystray.Menu(
            pystray.MenuItem("Device: " + lcd.name, self.noop, enabled=False),
            pystray.MenuItem(
                "Bridge: http://127.0.0.1:{}".format(PORT), self.noop, enabled=False
            ),
            pystray.MenuItem(
                "SignalRGBPlugin: "
                + ("installed" if pluginInstalled else "not installed"),
                self.noop,
                enabled=False,
            ),
            pystray.MenuItem(self.getFPS, self.noop, enabled=False),
            pystray.MenuItem(self.getGifToggleText, self.toggleGif),
            pystray.MenuItem("Browse GIF...", self.browseGif),
            pystray.MenuItem("Exit", self.stop),
        )
        self.icon = pystray.Icon(
            name="KrakenLCDBridge",
            title="KrakenLCDBridge",
            icon=Image.open(APP_ICON).resize((64, 64)),
            menu=self.menu,
        )

    def run(self):
        debug("Systray icon started")
        self.icon.run()

    def getFPS(self, _):
        if _current_mode == "gif":
            return "FPS: {:.2f} [GIF]".format(_gif_fps)
        return "FPS: {:.2f} [Canvas]".format(frameWriterWithStats.fps.value)

    def getGifToggleText(self, _):
        return "Stop GIF" if _current_mode == "gif" else "Start GIF"

    def toggleGif(self):
        if _current_mode == "gif":
            _stop_gif()
        elif _last_gif_path:
            _start_gif(
                _last_gif_path, _last_gif_rotation, _last_gif_fps_str,
                _last_gif_fit_mode, _last_gif_zoom,
                _last_gif_offset_x, _last_gif_offset_y,
            )

    def browseGif(self):
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            parent=root,
            title="Select GIF",
            filetypes=[("GIF files", "*.gif"), ("All files", "*.*")],
        )
        root.destroy()
        if path:
            _start_gif(
                path, _last_gif_rotation, _last_gif_fps_str,
                _last_gif_fit_mode, _last_gif_zoom,
                _last_gif_offset_x, _last_gif_offset_y,
            )

    def noop(self):
        pass

    def stop(self):
        self.icon.stop()


class FrameWriterWithStats(FrameWriter):
    def __init__(self, frameBuffer: queue.Queue, lcd: driver.KrakenLCD):
        super().__init__(frameBuffer, lcd)
        self.updateAIOStats()

    def updateAIOStats(self):
        if _current_mode == "gif":
            return  # Don't touch the device while GifPlayer owns it
        if time.time() - self.lastDataTime > 1:
            self.lastDataTime = time.time()
            try:
                with lcd_lock:
                    self.lcd.clear()
                    stats.update(self.lcd.getStats())
            except Exception as e:
                print(f"[Stats] AIO read failed (will retry): {e}")

    def onFrame(self):
        (frame, rawTime, gifTime) = self.frameBuffer.get()
        startTime = time.time()
        try:
            with lcd_lock:
                self.lcd.writeFrame(frame)
        except Exception as e:
            print(f"[FrameWriter] Write failed (will retry): {e}")
            return
        writeTime = time.time() - startTime
        freeTime = rawTime - writeTime
        from utils import debug
        debug(
            "FPS: {:4.1f} - Frame {:5} (size: {:7}) - raw {:6.2f}ms, gif {:6.2f}ms, write {:6.2f}ms, free time {: 7.2f}ms ".format(
                self.fps(),
                self.frameCount,
                len(frame),
                rawTime * 1000,
                gifTime * 1000,
                writeTime * 1000,
                freeTime * 1000,
            )
        )
        self.frameCount += 1
        self.updateAIOStats()


dataBuffer = queue.Queue(maxsize=2)
frameBuffer = queue.Queue(maxsize=2)

rawProducer = RawProducer(dataBuffer)
overlayProducer = OverlayProducer(dataBuffer, frameBuffer)
frameWriterWithStats = FrameWriterWithStats(frameBuffer, lcd)
statsProducer = StatsProducer()
systray = Systray()

rawProducer.start()
overlayProducer.start()
frameWriterWithStats.start()
statsProducer.start()
systray.start()

print("SignalRGB Kraken bridge started")
print(f"GIF endpoint: POST http://127.0.0.1:{PORT}/gif  body: {{\"path\": \"C:/path/to/file.gif\", \"rotation\": 0}}")
print(f"Stop GIF:     POST http://127.0.0.1:{PORT}/gif/stop")

try:
    while True:
        time.sleep(1)
        systray.icon.update_menu()
        if not (
            statsProducer.is_alive()
            and rawProducer.is_alive()
            and overlayProducer.is_alive()
            and frameWriterWithStats.is_alive()
            and systray.is_alive()
        ):
            raise KeyboardInterrupt("Some thread is dead")
except KeyboardInterrupt:
    _stop_gif()
    frameWriterWithStats.shouldStop = True
    frameWriterWithStats.join()
    systray.stop()
