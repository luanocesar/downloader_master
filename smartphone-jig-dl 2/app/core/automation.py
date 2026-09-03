import logging
import time

import pyautogui

from infra.window_picker import find_window

# Impede que o script quebre se o operador mover o mouse sem querer
pyautogui.FAILSAFE = False

# Tempos de acomodação após cada tipo de ação -- generosos de propósito.
# Cliques/type_text não têm nenhuma confirmação de que o app-alvo realmente
# processou a ação (trocou o foco, validou o campo, etc.) antes da próxima
# ação começar; esses sleeps são a única salvaguarda que temos contra um
# app-alvo mais lento que o esperado.
CLICK_SETTLE_SECONDS = 0.3
TYPE_SETTLE_SECONDS = 0.2
KEY_SETTLE_SECONDS = 0.15


def execute_slot_actions(slot_key, slot, label_code, janela):
    for action in slot.get("actions", []):
        if not action.get("enabled", True):
            continue

        a_type = action.get("type", "none")

        if a_type in ("click", "double_click"):
            # Relê a posição/tamanho da janela a cada clique (não mais uma
            # única vez por lote inteiro): se o app-alvo mover, redimensionar
            # ou re-layoutar enquanto um Slot anterior ainda está sendo
            # validado, um rect desatualizado mandaria os próximos cliques
            # para o lugar errado -- inclusive de volta em cima do campo de
            # um Slot anterior.
            rect = janela.rectangle()
            clique_x = rect.left + action.get("x", 0)
            clique_y = rect.top + action.get("y", 0)

            t0 = time.monotonic()
            if a_type == "click":
                logging.info(f"-> Mapeando Slot {slot_key}: Clicando no alvo (X:{clique_x}, Y:{clique_y})")
                pyautogui.click(clique_x, clique_y)
            else:
                logging.info(f"-> Mapeando Slot {slot_key}: Duplo clique no alvo (X:{clique_x}, Y:{clique_y})")
                pyautogui.doubleClick(clique_x, clique_y)
            time.sleep(CLICK_SETTLE_SECONDS)
            logging.info(f"   [Slot {slot_key}] clique + acomodação: {time.monotonic() - t0:.3f}s")

        elif a_type == "type_text":
            text = label_code if action.get("source", "barcode") == "barcode" else action.get("text", "")
            t0 = time.monotonic()
            logging.info(f"   [DIGITANDO SLOT {slot_key}] -> '{text}'")
            pyautogui.write(text, interval=0.02)
            time.sleep(TYPE_SETTLE_SECONDS)
            logging.info(f"   [Slot {slot_key}] digitação + acomodação: {time.monotonic() - t0:.3f}s")

        elif a_type == "key_press":
            key = action.get("key", "enter")
            pyautogui.press(key)
            time.sleep(KEY_SETTLE_SECONDS)

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

        for slot_key, label_code in labels_para_digitar:
            slot = slots.get(slot_key)
            if slot is None:
                # A configuração pode ter sido salva/recarregada entre o
                # recebimento do POST e a execução em background; se o Slot
                # sumiu nesse meio-tempo, pula em vez de derrubar o lote todo.
                logging.warning(f"-> Slot {slot_key} não existe mais na configuração atual. Pulando.")
                continue

            try:
                execute_slot_actions(slot_key, slot, label_code, janela)
            except Exception as e:
                # Isola a falha de UM Slot para não abortar os demais do lote.
                logging.error(f"-> ERRO ao executar ações do Slot {slot_key}: {e}. Pulando para o próximo Slot.")
                continue

    except Exception as e:
        logging.error(f"-> ERRO DURANTE DIGITAÇÃO: {e}")

    finally:
        logging.info("=" * 50)
        logging.info("-> DIGITAÇÃO CONCLUÍDA. Robô livre para o próximo Jig.\n")
