"""`hf-studio start`: arranca la API y la UI con un solo comando en Windows, macOS y Linux."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading

from . import setup

API_PORT = 8787
UI_PORT = 3000


# En macOS, `brew install ffmpeg` no trae rubberband; `ffmpeg-full` sí, pero es keg-only (no entra al PATH).
BREW_FFMPEG_FULL = ("/opt/homebrew/opt/ffmpeg-full/bin", "/usr/local/opt/ffmpeg-full/bin")


def check_ffmpeg() -> None:
    """Prefiere el ffmpeg-full de Homebrew si está y avisa si falta ffmpeg o su filtro rubberband.

    Cambia el PATH de este proceso, que heredan la API y sus subprocesos de ffmpeg."""
    if sys.platform == "darwin":
        entries = os.environ.get("PATH", "").split(os.pathsep)
        for folder in BREW_FFMPEG_FULL:
            if os.path.isfile(os.path.join(folder, "ffmpeg")):
                # Al principio aunque ya esté en el PATH: detrás de otro ffmpeg no se usaría.
                os.environ["PATH"] = os.pathsep.join([folder, *(e for e in entries if e != folder)])
                break
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not shutil.which("ffprobe"):
        print(
            "Note: ffmpeg is not installed; voice change, audio isolation and keeping the source audio need it."
        )
        return
    try:
        filters = subprocess.run(
            [ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True, check=False
        )
    except OSError:
        return
    if " rubberband " not in filters.stdout:
        hint = (
            "brew install ffmpeg-full" if sys.platform == "darwin" else "an ffmpeg build with librubberband"
        )
        print(
            f"Note: this ffmpeg has no rubberband filter; the deep, monster and ghost voice effects need it ({hint})."
        )


class _WindowsJob:
    """Job Object de Windows: todos los procesos que lance pnpm (next dev…) caen en él y se cierran juntos,
    aunque pnpm ya haya salido, e incluso si HF Studio muere sin limpiar (KILL_ON_JOB_CLOSE)."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimits),
                ("IoInfo", ctypes.c_uint64 * 6),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        self._ctypes = ctypes
        k32 = self._k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        k32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.handle = k32.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = ExtendedLimits()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        # 9 = JobObjectExtendedLimitInformation
        if not k32.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())

    def add(self, proc: subprocess.Popen) -> None:
        if not self._k32.AssignProcessToJobObject(self.handle, int(proc._handle)):
            raise self._ctypes.WinError(self._ctypes.get_last_error())

    def terminate(self) -> None:
        self._k32.TerminateJobObject(self.handle, 1)

    def resume(self, pid: int) -> None:
        """Reanuda los hilos de un proceso creado con CREATE_SUSPENDED (Toolhelp32 + ResumeThread)."""
        ctypes = self._ctypes
        from ctypes import wintypes

        class ThreadEntry(ctypes.Structure):
            _fields_ = (
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ThreadID", wintypes.DWORD),
                ("th32OwnerProcessID", wintypes.DWORD),
                ("tpBasePri", wintypes.LONG),
                ("tpDeltaPri", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
            )

        k32 = self._k32
        k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k32.OpenThread.restype = wintypes.HANDLE
        k32.Thread32First.argtypes = k32.Thread32Next.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ThreadEntry),
        ]
        k32.ResumeThread.argtypes = k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.ResumeThread.restype = wintypes.DWORD
        snapshot = k32.CreateToolhelp32Snapshot(0x4, 0)  # TH32CS_SNAPTHREAD
        if snapshot in (None, wintypes.HANDLE(-1).value):
            raise ctypes.WinError(ctypes.get_last_error())
        resumed = 0
        try:
            entry = ThreadEntry(dwSize=ctypes.sizeof(ThreadEntry))
            more = k32.Thread32First(snapshot, ctypes.byref(entry))
            while more:
                if entry.th32OwnerProcessID == pid:
                    thread = k32.OpenThread(0x2, False, entry.th32ThreadID)  # THREAD_SUSPEND_RESUME
                    if thread:
                        if k32.ResumeThread(thread) != 0xFFFFFFFF:
                            resumed += 1
                        k32.CloseHandle(thread)
                more = k32.Thread32Next(snapshot, ctypes.byref(entry))
        finally:
            k32.CloseHandle(snapshot)
        if not resumed:
            raise OSError(f"could not resume the web UI process {pid}")


class UI:
    """`pnpm dev` de la UI, en su propio grupo (POSIX) o Job Object (Windows) para cerrarlo entero."""

    def __init__(self, pnpm: str) -> None:
        self.stopping = threading.Event()  # activo cuando el cierre lo pedimos nosotros
        self.job = None
        if os.name == "nt":
            try:
                self.job = _WindowsJob()
            except OSError:
                self.job = None  # sin job queda taskkill /T, que cubre a los hijos mientras pnpm viva
            # Suspendido hasta entrar al job: así ningún hijo (next dev) puede nacer fuera de él.
            suspended = 0x4 if self.job else 0  # CREATE_SUSPENDED
            flags = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | suspended}
        else:
            flags = {"start_new_session": True}
        # El script dev de web/package.json ya liga a 127.0.0.1.
        self.proc = subprocess.Popen([pnpm, "dev", "--port", str(UI_PORT)], cwd=setup.ROOT / "web", **flags)
        if job := self.job:
            try:
                job.add(self.proc)
            except OSError:
                self.job = None  # queda taskkill /T
            try:
                job.resume(self.proc.pid)  # siempre: un pnpm suspendido nunca arrancaría
            except OSError:
                self.stop()  # no dejar un proceso suspendido colgando
                raise

    def stop(self) -> None:
        """Cierra la UI y todo lo que lanzó, aunque pnpm ya haya salido (next podría seguir vivo)."""
        self.stopping.set()
        if self.job:
            self.job.terminate()
        elif os.name == "nt":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True, check=False
            )
        else:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass  # sin procesos vivos en el grupo (macOS da EPERM si solo quedan zombis)
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def watch(self, crashed: threading.Event) -> None:
        """Si la UI termina sin que la paremos (puerto ocupado, error de Next…), lo avisa y detiene la API."""
        code = self.proc.wait()
        if not self.stopping.is_set():
            crashed.set()
            print(f"\nThe web UI stopped (exit code {code}). Stopping HF Studio.", file=sys.stderr)
            signal.raise_signal(signal.SIGINT)  # uvicorn (o el try de start) lo atiende como un Ctrl+C


def start(api_only: bool, setup_ok) -> int:
    """`setup_ok()` prepara `.env` y la clave de la UI; devuelve 0 si todo está listo."""
    pnpm = shutil.which("pnpm")
    if not api_only and not pnpm:
        print(
            "The web UI needs Node.js 20+ and pnpm (https://pnpm.io/installation)."
            " To use HF Studio only from agents, run: uv run hf-studio start --api-only",
            file=sys.stderr,
        )
        return 1
    check_ffmpeg()
    if setup_ok() != 0:
        return 1
    web = setup.ROOT / "web"
    # Se mira Next y no solo la carpeta: un node_modules a medias (instalación cortada) no sirve.
    needs_install = not api_only and not (web / "node_modules" / "next" / "package.json").is_file()
    if needs_install and subprocess.run([pnpm, "install"], cwd=web, check=False).returncode:
        return 1
    import uvicorn

    ui = None
    crashed = threading.Event()
    # Todo dentro del try: si la UI cae antes de que uvicorn instale su manejador, el SIGINT del vigilante
    # llega como KeyboardInterrupt y el finally igual cierra la UI.
    try:
        if not api_only:
            try:
                ui = UI(pnpm)
            except OSError as exc:
                print(f"Could not start the web UI: {exc}", file=sys.stderr)
                return 1
            threading.Thread(target=ui.watch, args=(crashed,), daemon=True).start()
            print(f"\nHF Studio: http://localhost:{UI_PORT}  ·  API docs: http://127.0.0.1:{API_PORT}/docs")
        else:
            print(f"\nHF Studio API: http://127.0.0.1:{API_PORT}  ·  docs: http://127.0.0.1:{API_PORT}/docs")
        print("Connect an agent: uv run hf-studio connect claude-code   (or codex, claude-desktop, json)")
        print("Press Ctrl+C to stop.\n", flush=True)
        if not crashed.is_set():
            uvicorn.run("hf_studio.main:app", host="127.0.0.1", port=API_PORT)
    except KeyboardInterrupt:
        pass
    finally:
        if ui:
            ui.stop()
    return 1 if crashed.is_set() else 0


# `hf-studio cloud` (la imagen Docker): la UI ya compilada con `output: "standalone"` de Next.
STANDALONE_SERVER = setup.ROOT / "web" / ".next" / "standalone" / "server.js"
MIN_PASSWORD = 12


def cloud(prepare) -> int:
    """API en 127.0.0.1 y la UI en 0.0.0.0:$PORT, detrás de la contraseña de STUDIO_PASSWORD.

    `prepare()` valida la clave de Higgsfield y devuelve una clave nueva de la UI (o None si falla). La clave
    de la UI se rota en cada arranque y solo vive en el entorno del proceso de Node: no se escribe en disco."""
    password = os.environ.get("STUDIO_PASSWORD", "")
    if len(password) < MIN_PASSWORD:
        # Sin contraseña, cualquiera con la URL gastaría los créditos del dueño: no se arranca.
        print(
            f"STUDIO_PASSWORD is required (at least {MIN_PASSWORD} characters): the UI is reachable from the"
            " internet and every visitor would spend your credits.",
            file=sys.stderr,
        )
        return 1
    node = shutil.which("node")
    if not node or not STANDALONE_SERVER.is_file():
        print(
            f"Missing node or the built UI at {STANDALONE_SERVER} (build the Docker image).", file=sys.stderr
        )
        return 1
    check_ffmpeg()
    token = prepare()
    if not token:
        return 1
    import uvicorn

    port = os.environ.get("PORT", str(UI_PORT))
    env = {
        **os.environ,
        "HOSTNAME": "0.0.0.0",
        "PORT": port,
        "HF_STUDIO_URL": f"http://127.0.0.1:{API_PORT}",
        "HF_STUDIO_TOKEN": token,
        "NODE_ENV": "production",
    }
    # Las claves de los proveedores no le hacen falta a la UI: solo las ve la API.
    for name in list(env):
        if name.endswith("_API_KEY") or name in ("HF_API_KEY_ID", "HF_API_KEY_SECRET"):
            del env[name]
    ui = subprocess.Popen([node, str(STANDALONE_SERVER)], cwd=STANDALONE_SERVER.parent, env=env)
    crashed, stopping = threading.Event(), threading.Event()

    def watch() -> None:
        ui.wait()
        if not stopping.is_set():  # la cerramos nosotros: no es una caída
            crashed.set()
            signal.raise_signal(signal.SIGINT)

    threading.Thread(target=watch, daemon=True).start()
    print(f"HF Studio UI on port {port}; API on 127.0.0.1:{API_PORT}.", flush=True)

    def stop(signum, frame) -> None:
        raise KeyboardInterrupt

    # SIGTERM (docker stop, redeploy): uvicorn lo atiende y, al salir, lo vuelve a emitir con el manejador que
    # hubiera antes. Con el de por defecto Python moriría sin pasar por el finally y Node no se cerraría en orden.
    previous = signal.signal(signal.SIGTERM, stop)
    try:
        if not crashed.is_set():
            uvicorn.run("hf_studio.main:app", host="127.0.0.1", port=API_PORT)
    except KeyboardInterrupt:
        pass
    finally:
        stopping.set()
        # Un segundo SIGTERM durante el cierre no debe cortar la espera ni dejar a Node sin matar.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if ui.poll() is None:
            ui.terminate()
            try:
                ui.wait(timeout=10)
            except subprocess.TimeoutExpired:
                ui.kill()
        signal.signal(signal.SIGTERM, previous)
    return 1 if crashed.is_set() else 0
