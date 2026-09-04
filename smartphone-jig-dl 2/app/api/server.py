import logging
import threading

from fastapi import BackgroundTasks, FastAPI
from pydantic import BaseModel

from core import automation
from core.config import ServerConfig, load_and_validate_config


class LabelCodeRequest(BaseModel):
    # Most stations POST a full batch keyed by Slot number. At least one
    # station's CLP side only ever has one barcode at a time and names the
    # field `label_code` instead -- that value maps onto Slot "1".
    mapped_labels: dict[str, str] | None = None
    label_code: str | None = None


class TriggerServer:
    """Mantém o estado do servidor entre requisições: a última configuração
    válida carregada e se o robô está ocupado digitando um lote."""

    def __init__(self, config: ServerConfig, config_path: str, script_path: str):
        self.config = config
        self.config_path = config_path
        self.script_path = script_path
        # A Lock (instead of a plain bool) makes "is it free? -> claim it"
        # a single atomic operation. FastAPI runs sync endpoints like this
        # one in a thread pool, so two /trigger requests arriving close
        # together used to both read `robot_busy == False` before either
        # one set it to True -- both would then launch PyAutoGUI automation
        # concurrently, interleaving clicks/keystrokes into the same field
        # on the target window. acquire(blocking=False) closes that gap.
        self._lock = threading.Lock()

    def _run_typing_routine(self, labels_para_digitar):
        try:
            automation.type_labels_into_window(
                self.config.target_window, self.config.slots, labels_para_digitar, self.config.step_delay_ms,
            )
        finally:
            self._lock.release()

    @staticmethod
    def _resolve_mapped_labels(request: LabelCodeRequest) -> dict[str, str]:
        if request.mapped_labels is not None:
            return request.mapped_labels
        if request.label_code:
            return {"1": request.label_code}
        return {}

    def handle_trigger(self, request: LabelCodeRequest, background_tasks: BackgroundTasks):
        logging.info("\n" + "=" * 50)
        logging.info(">>> NOVO GATILHO RECEBIDO <<<")

        if not self._lock.acquire(blocking=False):
            logging.warning("-> ALERTA: Robô já está trabalhando! Ignorando pulso duplicado do CLP.")
            return {"status": "busy", "message": "Robô ocupado, ignorando duplicata."}

        # From here on the lock must be released before returning/raising on
        # every path except "queued" -- that one hands the lock off to
        # _run_typing_routine, which releases it once the typing finishes.
        queued = False
        try:
            # Recarrega o config.json a cada gatilho, para que Slots/Actions
            # adicionados ou editados na UI depois que o servidor já estava rodando
            # sejam respeitados sem precisar reiniciar o processo. HOST/PORT não são
            # recarregados aqui pois o servidor já está vinculado a eles.
            try:
                reloaded = load_and_validate_config(self.config_path, self.script_path)
                self.config.slots = reloaded.slots
                self.config.target_window = reloaded.target_window
                self.config.step_delay_ms = reloaded.step_delay_ms
            except Exception as e:
                logging.warning(f"-> Falha ao recarregar {self.config_path}/{self.script_path} ({e}). Usando a última configuração válida em memória.")

            mapped_labels = self._resolve_mapped_labels(request)

            # Tolerante a posições em falta/fora de ordem: cada posição do POST só é
            # usada se existir em SLOTS, sempre amarrada pelo número (chave), nunca
            # pela ordem/posição no payload.
            labels_para_digitar = []
            unknown_keys = []
            for raw_key, label_code in mapped_labels.items():
                slot_key = raw_key.strip()

                if not label_code:
                    continue
                if slot_key not in self.config.slots:
                    unknown_keys.append(raw_key)
                    continue
                if not self.config.slots[slot_key].get("enabled", True):
                    continue

                labels_para_digitar.append((slot_key, label_code))

            # Ordem de execução determinística (1, 2, 3, ...), independente da ordem
            # em que as chaves chegaram no JSON do POST.
            labels_para_digitar.sort(key=lambda pair: int(pair[0]) if pair[0].isdigit() else pair[0])

            if unknown_keys:
                logging.warning(f"-> POST continha posições sem Slot correspondente na configuração atual (ignoradas): {unknown_keys}")

            if not labels_para_digitar:
                logging.info("-> Todos os campos vazios, Slots desabilitados ou sem correspondência. Abortando.")
                return {"status": "empty"}

            logging.info(f"-> Pacote aceito para Slots {[k for k, _ in labels_para_digitar]}. Liberando o Master e iniciando digitação em background...")
            background_tasks.add_task(self._run_typing_routine, labels_para_digitar)
            queued = True

            return {"status": "success", "message": "Iniciando digitação física na tela."}
        finally:
            if not queued:
                self._lock.release()


def create_app(config: ServerConfig, config_path: str, script_path: str) -> FastAPI:
    app = FastAPI()
    trigger_server = TriggerServer(config, config_path, script_path)

    @app.post("/trigger")
    def trigger(request: LabelCodeRequest, background_tasks: BackgroundTasks):
        return trigger_server.handle_trigger(request, background_tasks)

    return app
