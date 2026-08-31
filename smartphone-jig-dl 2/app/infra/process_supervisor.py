import os
import queue
import subprocess
import sys
import threading
import time


def kill_process_tree(proc):
    """Kills proc and every descendant it spawned.

    proc.terminate() alone only kills that one PID. A PyInstaller
    --onefile EXE on Windows runs as a launcher that unpacks itself to a
    temp dir and spawns a child process to do the real work; killing
    only the launcher orphans that child, which keeps running (and keeps
    the port bound) invisibly to us, showing up in Task Manager forever.
    `taskkill /T` walks and kills the whole tree instead.
    """
    if proc is None:
        return
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass


class ProcessSupervisor:
    """Supervisiona um processo filho: start/stop, kill-tree em stop, leitura
    de stdout em background e detecção de saída/timeout. Não depende de Tk;
    o chamador deve invocar `poll()` periodicamente (ex.: via Tk `.after()`)
    e é responsável por exibir as linhas de saída retornadas.

    `ready_marker`: texto (case-insensitive) que, ao aparecer numa linha de
    saída, marca o processo como "confirmado rodando" (não basta ter sido
    spawnado; ex.: o processo pode falhar ao bindar uma porta). Se None,
    o processo é considerado confirmado assim que é iniciado.
    """

    def __init__(self, base_dir, ready_marker=None, stop_timeout=10.0):
        self.base_dir = base_dir
        self.ready_marker = ready_marker
        self.stop_timeout = stop_timeout

        self.process = None
        self.stopping = False
        self.confirmed_running = False
        self._stopping_deadline = None
        self._output_queue = queue.Queue()
        self._reader_thread = None

    @property
    def is_running(self):
        return self.process is not None

    @property
    def pid(self):
        return self.process.pid if self.process is not None else None

    def resolve_process_path(self, filename):
        filename = (filename or "main.py").strip() or "main.py"

        if os.path.isabs(filename):
            return filename

        return os.path.join(self.base_dir, filename)

    def start(self, filename):
        """Inicia `filename` (relativo a base_dir, ou absoluto) como processo
        filho. Levanta FileNotFoundError se o alvo não existir. Retorna o
        caminho resolvido do processo iniciado."""
        if self.process is not None:
            return None

        target_path = self.resolve_process_path(filename)
        if not os.path.isfile(target_path):
            raise FileNotFoundError(target_path)

        cmd = [sys.executable, "-u", target_path] if target_path.lower().endswith(".py") else [target_path]

        self.confirmed_running = self.ready_marker is None
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            # Inherit our own CWD rather than target_path's directory: the
            # child reads config.json relative to its CWD, and that file
            # lives wherever *we* were launched from, not necessarily next
            # to the script/exe being launched.
        )
        self._start_output_reader_thread()

        return target_path

    def force_kill(self):
        """Mata o processo imediatamente, sem aguardar confirmação de saída
        (usado ao encerrar o supervisor/aplicação, quando não há mais poll()
        para confirmar o término)."""
        if self.process is not None:
            kill_process_tree(self.process)
            self.process = None
            self.stopping = False
            self._stopping_deadline = None
            self.confirmed_running = False

    def stop(self):
        if self.process is None or self.stopping:
            return

        # Don't flip to OFF right away: on Windows, terminating a process
        # doesn't guarantee its listening socket is released immediately. If
        # the caller starts a new process too fast, it can fail to bind with
        # "only one usage of each socket address is normally permitted".
        # `poll()` keeps `stopping` True (caller should show e.g.
        # "STOPPING...") until the process is confirmed to have exited.
        kill_process_tree(self.process)
        self.stopping = True
        self._stopping_deadline = time.monotonic() + self.stop_timeout
        self.confirmed_running = False

    def _start_output_reader_thread(self):
        proc = self.process

        def _reader():
            try:
                for line in iter(proc.stdout.readline, ""):
                    if not line:
                        break
                    self._output_queue.put(line.rstrip("\n"))
            except Exception:
                pass
            finally:
                if proc.stdout:
                    proc.stdout.close()

        self._reader_thread = threading.Thread(target=_reader, daemon=True)
        self._reader_thread.start()

    def poll(self):
        """Drena a saída pendente e atualiza o estado do processo (detecta
        confirmação de "rodando", saída espontânea, ou timeout de stop).
        Deve ser chamado periodicamente. Retorna a lista de novas linhas de
        saída/status a exibir, na ordem em que ocorreram."""
        new_lines = []

        try:
            while True:
                line = self._output_queue.get_nowait()
                new_lines.append(line)

                if not self.confirmed_running and self.ready_marker is not None \
                        and self.ready_marker.lower() in line.lower():
                    self.confirmed_running = True
        except queue.Empty:
            pass

        # Detect the process dying on its own (crash, closed manually, etc.)
        # so status doesn't stay stuck on ON. Also used to confirm a
        # caller-requested stop has actually finished before reporting OFF
        # (see stop()) so a fast stop->start doesn't race the OS releasing
        # the port.
        if self.process is not None:
            exited = self.process.poll() is not None
            timed_out = (
                self.stopping and self._stopping_deadline is not None
                and time.monotonic() > self._stopping_deadline
            )

            if exited:
                new_lines.append(f"--- Process exited (code {self.process.returncode}) ---")
            elif timed_out:
                new_lines.append(
                    f"--- WARNING: process did not exit within {self.stop_timeout:.0f}s; resetting status to OFF anyway ---"
                )

            if exited or timed_out:
                self.process = None
                self.stopping = False
                self._stopping_deadline = None
                self.confirmed_running = False

        return new_lines
