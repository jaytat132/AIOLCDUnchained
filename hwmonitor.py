"""
Hardware temperature monitoring via LibreHardwareMonitorLib.dll (pythonnet).

Setup:
  1. pip install pythonnet
  2. Download LibreHardwareMonitor from
     https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases
  3. Copy LibreHardwareMonitorLib.dll (and HidSharp.dll if present) next to
     signalrgb.exe (or this script).
  4. Run the application **as Administrator** — LHM requires admin for full
     sensor access.

If pythonnet or the DLL is missing the module degrades gracefully:
hw_monitor.available will be False and get_temps() returns {}.
"""

import os
import sys
import time
from threading import Thread, Lock

_POLL_INTERVAL = 2  # seconds
_DLL_NAME = "LibreHardwareMonitorLib"


class HWMonitor:
    def __init__(self):
        self._lock = Lock()
        self._temps: dict = {}
        self._available = False
        self._error: str | None = None
        self._computer = None
        self._hw_type = None
        self._sensor_type = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def start(self):
        """Try to load the DLL and begin background polling."""
        try:
            dll_dir = self._find_dll_dir()
            if dll_dir is None:
                raise FileNotFoundError(
                    f"{_DLL_NAME}.dll not found. "
                    "Place it next to the executable or install LibreHardwareMonitor."
                )
            self._unblock_dlls(dll_dir)
            self._load(dll_dir)
            self._available = True
            Thread(target=self._poll_loop, daemon=True, name="HWMonitor").start()
            print(f"[HWMonitor] Started (dir={dll_dir})")
        except Exception as e:
            self._error = str(e)
            print(f"[HWMonitor] Not available: {e}")

    @property
    def available(self):
        return self._available

    @property
    def error(self):
        return self._error

    def get_temps(self) -> dict:
        """Return latest cached temperatures, e.g. {"cpu_temp": 52.0, "gpu_temp": 61.0}."""
        with self._lock:
            return dict(self._temps)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    @staticmethod
    def _find_dll_dir() -> str | None:
        """Return the directory containing the LHM DLL, or None."""
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        cwd = os.getcwd()
        candidates = [
            os.path.join(base, "lhm"),
            os.path.join(cwd, "lhm"),
            base,
            cwd,
            os.path.join(base, "dist"),
            os.path.join(cwd, "dist"),
        ]
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        for d in (pf, pf86):
            candidates.append(os.path.join(d, "LibreHardwareMonitor"))
        for d in candidates:
            if os.path.isfile(os.path.join(d, f"{_DLL_NAME}.dll")):
                return os.path.abspath(d)
        return None

    @staticmethod
    def _unblock_dlls(dll_dir: str):
        """Remove Zone.Identifier ADS from DLLs so .NET doesn't refuse to load them."""
        for name in os.listdir(dll_dir):
            if name.lower().endswith(".dll"):
                try:
                    os.remove(os.path.join(dll_dir, name + ":Zone.Identifier"))
                except OSError:
                    pass

    def _load(self, dll_dir: str):
        dll_path = os.path.join(dll_dir, f"{_DLL_NAME}.dll")

        # pythonnet 3.x must choose a .NET runtime BEFORE 'import clr'.
        # Modern LHM (.NET 8) needs coreclr; older LHM (.NET Framework) needs netfx.
        # Try coreclr first (covers newer builds), fall back to netfx (always on Windows).
        try:
            from pythonnet import load as _load_runtime
            for runtime in ("netfx", "coreclr"):
                try:
                    _load_runtime(runtime)
                    print(f"[HWMonitor] pythonnet runtime: {runtime}")
                    break
                except Exception:
                    continue
        except Exception:
            pass  # older pythonnet or already loaded — continue with default

        try:
            import clr  # pythonnet
        except ImportError:
            raise ImportError(
                "pythonnet is not installed. Run:  pip install pythonnet"
            )

        if dll_dir not in sys.path:
            sys.path.append(dll_dir)

        # Try each loading strategy and verify the namespace import works.
        strategies = [
            ("name", lambda: clr.AddReference(_DLL_NAME)),
            ("full-path", lambda: clr.AddReference(dll_path)),
        ]
        # Assembly.LoadFrom requires System.Reflection (only works once clr is up)
        try:
            from System.Reflection import Assembly
            strategies.append(
                ("Assembly.LoadFrom", lambda: Assembly.LoadFrom(dll_path))
            )
        except Exception:
            pass

        last_err = None
        for desc, load_fn in strategies:
            try:
                load_fn()
            except Exception as e:
                print(f"[HWMonitor] {desc}: load failed — {e}")
                continue
            try:
                from LibreHardwareMonitor.Hardware import (
                    Computer, HardwareType, SensorType,
                )
                print(f"[HWMonitor] Loaded via {desc}")
                break
            except ImportError as e:
                last_err = e
                print(f"[HWMonitor] {desc}: loaded but import failed — {e}")
        else:
            raise RuntimeError(
                f"Could not import LibreHardwareMonitor.Hardware from "
                f"{dll_path}. Last error: {last_err}. "
                f"Make sure the DLL version matches your .NET runtime "
                f"(try the net472 build if using .NET Framework)."
            )

        # Pre-load ALL DLLs from the LHM directory so .NET can resolve
        # dependencies (System.Memory, HidSharp, etc.) when Computer.Open() runs.
        from System.Reflection import Assembly as SysAssembly
        preloaded = 0
        for fname in os.listdir(dll_dir):
            if not fname.lower().endswith(".dll"):
                continue
            if fname.lower() == f"{_DLL_NAME.lower()}.dll":
                continue
            try:
                SysAssembly.LoadFrom(os.path.join(dll_dir, fname))
                preloaded += 1
            except Exception:
                pass
        print(f"[HWMonitor] Pre-loaded {preloaded} dependency DLLs from {dll_dir}")

        comp = Computer()
        comp.IsCpuEnabled = True
        comp.IsGpuEnabled = True
        comp.Open()

        self._computer = comp
        self._hw_type = HardwareType
        self._sensor_type = SensorType

    def _poll_loop(self):
        self._read_sensors()
        while True:
            time.sleep(_POLL_INTERVAL)
            try:
                self._read_sensors()
            except Exception as e:
                print(f"[HWMonitor] Poll error: {e}")

    def _read_sensors(self):
        data: dict = {}
        for hw in self._computer.Hardware:
            hw.Update()
            for sub in hw.SubHardware:
                sub.Update()

            ht = hw.HardwareType
            for sensor in hw.Sensors:
                if sensor.SensorType != self._sensor_type.Temperature:
                    continue
                if sensor.Value is None:
                    continue
                val = float(sensor.Value)
                name_l = sensor.Name.lower()

                if ht == self._hw_type.Cpu:
                    if "package" in name_l or "tctl" in name_l or "cpu_temp" not in data:
                        data["cpu_temp"] = val
                elif ht in (
                    self._hw_type.GpuNvidia,
                    self._hw_type.GpuAmd,
                    self._hw_type.GpuIntel,
                ):
                    if "core" in name_l or "gpu_temp" not in data:
                        data["gpu_temp"] = val

        with self._lock:
            self._temps.update(data)


# Module-level singleton — call hw_monitor.start() after LCD init.
hw_monitor = HWMonitor()
