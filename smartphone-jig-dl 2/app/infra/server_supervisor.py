import logging
import queue
import threading
import time

import uvicorn

_THREAD_DONE = object()


class _QueueLogHandler(logging.Handler):
    """Encaminha registros do logger raiz para uma fila, para que o poll()
    do Tk possa exibi-los no console da UI -- substitui a leitura de stdout
    de um processo filho que existia quando o servidor rodava separado."""

    def __init__(self, out_queue):
        super().__init__()
        self._out_queue = out_queue

    def emit(self, record):
        try:
            self._out_queue.put(self.format(record))
        except Exception:
            pass


class ServerSupervisor:
    """Roda o servidor uvicorn/FastAPI em uma thread de background dentro
    deste mesmo processo (antes rodava como main.py/main.exe, um processo
    filho supervisionado via subprocess). Mantém a mesma superfície que
    ProcessSupervisor tinha (`is_running`, `stopping`, `confirmed_running`,
    `start()`, `stop()`, `force_kill()`, `poll()`) para que a UI não precise
    saber a diferença.

    `ready_marker`: texto (case-insensitive) que, ao aparecer numa linha de
    log, marca o servidor como "confirmado rodando" (uvicorn só emite sua
    linha "Uvicorn running on ..." depois de bindar a porta com sucesso).
    """

    LOG_FORMAT = "[%(asctime)s] %(message)s"

    def __init__(self, ready_marker=None, stop_timeout=10.0):
        self.ready_marker = ready_marker
        self.stop_timeout = stop_timeout

        self._server = None
        self._thread = None
        self._log_handler = None
        self.stopping = False
        self.confirmed_running = False
        self._stopping_deadline = None
        self._output_queue = queue.Queue()

    @property
    def is_running(self):
        return self._server is not None

    def start(self, app, host, port):
        """Sobe `app` (ASGI) em host:port numa thread de background."""
        if self._server is not None:
            return

        self._log_handler = _QueueLogHandler(self._output_queue)
        self._log_handler.setFormatter(logging.Formatter(self.LOG_FORMAT))
        logging.getLogger().addHandler(self._log_handler)

        config = uvicorn.Config(app, host=host, port=port, log_config=None)
        server = uvicorn.Server(config)
        self._server = server
        self.confirmed_running = self.ready_marker is None

        def _run():
            try:
                server.run()
            except Exception as e:
                self._output_queue.put(f"--- Server error: {e} ---")
            finally:
                self._output_queue.put(_THREAD_DONE)

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def force_kill(self):
        """Sinaliza parada imediata, sem aguardar confirmação (usado ao
        encerrar a aplicação, quando não há mais poll() para confirmar)."""
        if self._server is not None:
            self._server.should_exit = True
        self._teardown()

    def stop(self):
        if self._server is None or self.stopping:
            return

        # Não reseta para OFF na hora: should_exit é honrado no próximo ciclo
        # do loop de eventos do uvicorn, não instantaneamente. poll() mantém
        # `stopping` True (UI mostra "STOPPING...") até a thread do servidor
        # de fato terminar.
        self._server.should_exit = True
        self.stopping = True
        self._stopping_deadline = time.monotonic() + self.stop_timeout
        self.confirmed_running = False

    def _teardown(self):
        if self._log_handler is not None:
            logging.getLogger().removeHandler(self._log_handler)
            self._log_handler = None
        self._server = None
        self._thread = None
        self.stopping = False
        self._stopping_deadline = None
        self.confirmed_running = False

    def poll(self):
        """Drena a saída pendente e atualiza o estado do servidor (detecta
        confirmação de "rodando", parada espontânea, ou timeout de stop).
        Deve ser chamado periodicamente. Retorna a lista de novas linhas de
        saída/status a exibir, na ordem em que ocorreram."""
        new_lines = []
        thread_done = False

        try:
            while True:
                item = self._output_queue.get_nowait()
                if item is _THREAD_DONE:
                    thread_done = True
                    continue

                new_lines.append(item)
                if not self.confirmed_running and self.ready_marker is not None \
                        and self.ready_marker.lower() in item.lower():
                    self.confirmed_running = True
        except queue.Empty:
            pass

        if self._server is not None:
            timed_out = (
                self.stopping and self._stopping_deadline is not None
                and time.monotonic() > self._stopping_deadline
            )

            if thread_done:
                new_lines.append("--- Server stopped ---")
            elif timed_out:
                new_lines.append(
                    f"--- WARNING: server did not stop within {self.stop_timeout:.0f}s; resetting status to OFF anyway ---"
                )

            if thread_done or timed_out:
                self._teardown()

        return new_lines
