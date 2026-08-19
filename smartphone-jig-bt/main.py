from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import time
import pyautogui
import uvicorn
import sys
import logging

pyautogui.FAILSAFE = False

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

app = FastAPI()


class LabelCodeRequest(BaseModel):
    label_code: str


ROBO_OCUPADO = False


def rotina_digitacao_bt_ft(label_code):
    global ROBO_OCUPADO
    ROBO_OCUPADO = True

    try:
        time.sleep(0.1)
        pyautogui.write(label_code)
        pyautogui.press('enter')
        logging.info(f"   [SUCESSO] Código '{label_code}' digitado!")
    except Exception as e:
        logging.error(f"Erro durante a digitação: {e}")
    finally:
        ROBO_OCUPADO = False  # Destranca a porta
        logging.info("=" * 40 + "\n")


@app.post("/trigger")
def trigger(request: LabelCodeRequest, background_tasks: BackgroundTasks):
    global ROBO_OCUPADO

    logging.info("\n" + "=" * 40)
    logging.info(f">>> GATILHO RECEBIDO: {request.label_code} <<<")

    if ROBO_OCUPADO:
        logging.warning("-> ALERTA: Robô ocupado, ignorando pulso duplicado.")
        return {"status": "busy"}

    background_tasks.add_task(rotina_digitacao_bt_ft, request.label_code)

    return {"status": "success"}


@app.get("/")
def health():
    return {"status": "online"}


if __name__ == "__main__":
    logging.info("\n" + "=" * 40)
    MEU_IP = "192.168.100.140"
    logging.info(f" Servidor BT/FT Iniciado no IP {MEU_IP}")
    uvicorn.run(app, host=MEU_IP, port=8000, log_config=None)