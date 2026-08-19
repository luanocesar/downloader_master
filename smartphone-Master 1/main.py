import threading
from pymodbus.client.sync import ModbusTcpClient
import time
from dotenv import load_dotenv

import sys
import logging
import json
import requests
import os

if getattr(sys, 'frozen', False):
    base_path = os.path.dirname(sys.executable)
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

load_dotenv("config.env")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("smartphone.log", mode="a"),
        logging.StreamHandler(sys.stdout)
    ]
)

modbus_mapping_path = os.path.join(os.path.dirname(__file__), "modbus_mapping.json")

with open(modbus_mapping_path, "r") as f:
    modbus_dict = json.load(f)

def _register_to_string(registers):
    bytes_list = []
    for value in registers:
        bytes_list.append(value & 0xFF)
        bytes_list.append((value >> 8) & 0xFF)
    byte_array = bytes(bytes_list)
    result = byte_array.decode('ascii', errors='ignore').strip('\0 \r\n\t')
    null_index = result.find('\0')
    result_string = result[:null_index] if null_index >= 0 else result
    return result_string

def send_to_endpoint_async(endpoint, payload):
    try:
        response = requests.post(endpoint, json=payload, timeout=15)
        if response.status_code == 200:
            logging.info(f"Sucesso ao enviar para {endpoint}. Resposta: {response.text}")
        else:
            logging.error(f"Falha ao enviar para {endpoint}. Status: {response.status_code}")
    except Exception as e:
        logging.error(f"Erro de rede ao enviar para {endpoint}: {e}")

class ModbusMaster:
    def __init__(self, host: str, port: int, unit: int):
        self.host = host if host else "192.168.100.22"
        self.port = port
        self.unit = unit
        self.client = ModbusTcpClient(host=self.host, port=self.port, timeout=3)
        self.is_connected = False

    def connect(self):
        logging.info(f"Connecting to {self.host}:{self.port} via modbus tcp...")
        self.is_connected = self.client.connect()
        if self.is_connected:
            logging.info(f"Connected to {self.host}:{self.port}")
        else:
            logging.error(f"Failed to connect to {self.host}:{self.port}")

    def disconnect(self):
        self.client.close()
        self.is_connected = False
        logging.info("[SUCCESS] Disconnected from modbus tcp")

    def read_all_coils(self):
        start = modbus_dict['coils']['meta']['start_address']
        count = modbus_dict['coils']['meta']['size']
        data = modbus_dict['coils']['data']

        address_to_name = {v: k for k, v in data.items()}

        try:
            response = self.client.read_coils(start, count, unit=self.unit)

            if response.isError():
                logging.error("Falha silenciosa no Modbus. Forçando reconexão no próximo ciclo...")
                self.is_connected = False
                self.client.close()
                return None

            bits = response.bits

            named_coils = {}
            for i, state in enumerate(bits):
                coil_address = start + i
                name = address_to_name.get(coil_address)

                if name is not None:
                    named_coils[name] = state
            return named_coils

        except Exception as e:
            logging.error(f"Exceção na leitura Modbus: {e}")
            self.is_connected = False
            self.client.close()
            return None

    def read_label_code_from_registers(self, label_code_name):
        start = modbus_dict['registers'][label_code_name]['start_address']
        size = modbus_dict['registers'][label_code_name]['size']

        response = self.client.read_holding_registers(start, size, unit=self.unit)

        if not response.isError():
            registers = response.registers
            return _register_to_string(registers)
        else:
            logging.error(f"Failed to read label code {label_code_name}")
            return None

    def write_coil(self, name, value):
        address = modbus_dict['coils']['data'][name]

        if address is None:
            logging.error(f"Coil {name} not found.")
            return

        self.client.write_coil(address=address, value=value)

def run_loop(modbus_master: ModbusMaster):
    try:
        if not modbus_master.is_connected:
            modbus_master.connect()

        if modbus_master.is_connected:
            coils = modbus_master.read_all_coils()

            if coils:
                handle_jig_bt(modbus_master, coils)
                handle_jig_dl(modbus_master, coils)
                handle_jig_ft(modbus_master, coils)
    except Exception as ex:
        logging.error(f'Error running loop: {ex}')


def handle_jig_dl(modbus_master, coils):
    jig_names = ['DL_1_8', 'DL_9_16']

    for i in range(1, 3):  # start=1; end=2
        coil_name = jig_names[i - 1] + '_PRONTO'
        ip = modbus_dict['ips']['DL'][jig_names[i - 1]]

        if coils and coil_name in coils and coils[coil_name]:
            logging.info(f"Coil {coil_name} está ativo, processando...")
            time.sleep(0.5)

            start = 1 if i == 1 else 9

            labels_payload = {}

            logging.info(f"Lendo códigos DL de {start} a {start + 7}")
            for j in range(start, start + 8):
                label = modbus_master.read_label_code_from_registers(f'CODE_DL_{j}')

                field_position = str((j - start) + 1)

                if label is not None and label.strip() != '':
                    labels_payload[field_position] = label.strip()
                    logging.info(f"Lido CODE_DL_{j} (Campo {field_position}): {label}")
                else:
                    labels_payload[field_position] = ""
                    logging.info(f"CODE_DL_{j} (Campo {field_position}) está vazio/desabilitado.")

            logging.info(f'writing {coil_name} = False')
            modbus_master.write_coil(coil_name, False)
            logging.info(f"Payload mapeado para {coil_name}: {labels_payload}")

            endpoint = f"{ip}/trigger"

            threading.Thread(target=send_to_endpoint_async,
                             args=(endpoint, {"mapped_labels": labels_payload}),
                             daemon=True).start()


def handle_jig_bt(modbus_master, coils):
    for i in range(1, 9):
        coil_name = f'BT_{i}_PRONTO'
        register_name = f'CODE_BT_{i}'
        ip = modbus_dict['ips']['BT'][f'BT_{i}']

        if coils and coil_name in coils and coils[coil_name]:
            logging.info(f"Coil {coil_name} está ativo, processando...")

            time.sleep(2.0)

            label = modbus_master.read_label_code_from_registers(register_name)

            logging.info(f'writing {coil_name} = False')
            modbus_master.write_coil(coil_name, False)

            if label is not None and label.strip() != '':
                logging.info(f"Lido {register_name}: {label.strip()}")
                logging.info(f"Label coletado para {coil_name}: {label.strip()}")

                endpoint = f"{ip}/trigger"
                logging.info(f"Preparando para enviar para endpoint: {endpoint}")

                # ENVIO EM THREAD
                threading.Thread(target=send_to_endpoint_async,
                                 args=(endpoint, {"label_code": label.strip()}),
                                 daemon=True).start()
            else:
                logging.warning(f"Label vazio ou nulo para {register_name}")


def handle_jig_ft(modbus_master, coils):
    for i in range(1, 9):
        coil_name = f'FT_{i}_PRONTO'
        register_name = f'CODE_FT_{i}'
        ip = modbus_dict['ips']['FT'][f'FT_{i}']

        if coils and coil_name in coils and coils[coil_name]:
            logging.info(f"Coil {coil_name} está ativo, processando...")

            time.sleep(2.0)

            label = modbus_master.read_label_code_from_registers(register_name)
            logging.info(f"Label Code Read: {label}")

            logging.info(f'writing {coil_name} = False')
            modbus_master.write_coil(coil_name, False)

            if label is None or label.strip() == '':
                logging.error(f'Label Code Not Found para {coil_name}')
                continue

            endpoint = f"{ip}/trigger"
            logging.info(f"Preparando para enviar para endpoint: {endpoint}")

            # ENVIO EM THREAD
            threading.Thread(target=send_to_endpoint_async,
                             args=(endpoint, {"label_code": label.strip()}),
                             daemon=True).start()


def main():
    plc_ip = os.getenv('PLC_IP')
    if not plc_ip:
        plc_ip = "192.168.100.22"
        logging.warning(f"PLC_IP não encontrado em config.env, usando IP padrão: {plc_ip}")

    modbus_master = ModbusMaster(plc_ip, 10000, 1)

    try:
        while True:
            run_loop(modbus_master)
            time.sleep(0.10)

    except Exception as e:
        logging.error('Global exception', e)
        pass


if __name__ == "__main__":
    main()