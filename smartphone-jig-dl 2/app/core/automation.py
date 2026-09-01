import logging
import time

import pyautogui

from infra.window_picker import find_window

# Impede que o script quebre se o operador mover o mouse sem querer
pyautogui.FAILSAFE = False


def execute_slot_actions(slot_key, slot, label_code, janela_left, janela_top):
    for action in slot.get("actions", []):
        if not action.get("enabled", True):
            continue

        a_type = action.get("type", "none")

        if a_type == "click":
            clique_x = janela_left + action.get("x", 0)
            clique_y = janela_top + action.get("y", 0)
            logging.info(f"-> Mapeando Slot {slot_key}: Clicando no alvo (X:{clique_x}, Y:{clique_y})")
            pyautogui.click(clique_x, clique_y)
            time.sleep(0.15)

        elif a_type == "type_text":
            text = label_code if action.get("source", "barcode") == "barcode" else action.get("text", "")
            logging.info(f"   [DIGITANDO SLOT {slot_key}] -> '{text}'")
            pyautogui.write(text, interval=0.02)

        elif a_type == "key_press":
            key = action.get("key", "enter")
            pyautogui.press(key)
            time.sleep(0.15)

        # a_type == "none": nenhuma operação


def type_labels_into_window(target_window_title, slots, labels_para_digitar):
    try:
        janela = find_window(target_window_title)

        if janela.is_minimized():
            logging.info("-> Janela minimizada detectada! Restaurando...")
            janela.restore()

        # Sempre traz a janela para primeiro plano/foco antes de cada
        # automação, mesmo que não esteja minimizada: o operador pode ter
        # clicado em outra janela, ou outro programa pode ter sobreposto o
        # alvo entre um gatilho e o próximo. Sem isso, os cliques calculados
        # abaixo podem acabar acertando a janela errada.
        janela.set_focus()

        time.sleep(0.5)
        rect = janela.rectangle()
        janela_left = rect.left
        janela_top = rect.top

        for slot_key, label_code in labels_para_digitar:
            slot = slots.get(slot_key)
            if slot is None:
                # A configuração pode ter sido salva/recarregada entre o
                # recebimento do POST e a execução em background; se o Slot
                # sumiu nesse meio-tempo, pula em vez de derrubar o lote todo.
                logging.warning(f"-> Slot {slot_key} não existe mais na configuração atual. Pulando.")
                continue

            try:
                execute_slot_actions(slot_key, slot, label_code, janela_left, janela_top)
            except Exception as e:
                # Isola a falha de UM Slot para não abortar os demais do lote.
                logging.error(f"-> ERRO ao executar ações do Slot {slot_key}: {e}. Pulando para o próximo Slot.")
                continue

    except Exception as e:
        logging.error(f"-> ERRO DURANTE DIGITAÇÃO: {e}")

    finally:
        logging.info("=" * 50)
        logging.info("-> DIGITAÇÃO CONCLUÍDA. Robô livre para o próximo Jig.\n")
