# Documentação Técnica - Smartphone Master

## Visão Geral

Este projeto centraliza a leitura de sinais Modbus no CLP e encaminha códigos de etiquetas para endpoints HTTP nas estações de teste DL, BT e FT.

Arquivos principais:
- `c:\Users\4376066\OneDrive - Jabil\Documents\projects\Samsung Smartphone App\Files\smartphone-Master 1\smartphone\main.py`
- `c:\Users\4376066\OneDrive - Jabil\Documents\projects\Samsung Smartphone App\Files\smartphone-Master 1\smartphone\modbus_mapping.json`
- `c:\Users\4376066\OneDrive - Jabil\Documents\projects\Samsung Smartphone App\Files\smartphone-Master 1\smartphone\config.env`

## Arquitetura do Sistema

- `main.py` conecta ao CLP via Modbus TCP.
- `main.py` lê coils de prontidão e registradores de código.
- `main.py` dispara requisições HTTP para endpoints definidos em `modbus_mapping.json`.

Fluxo:
1. `main.py` conecta no CLP.
2. `main.py` lê todos os coils em `read_all_coils()`.
3. `main.py` chama:
   - `handle_jig_dl()`
   - `handle_jig_bt()`
   - `handle_jig_ft()`
4. Cada handler lê registradores e envia payload para `/trigger`.

## Estrutura do Projeto

- `main.py` - software master que faz leitura Modbus e envia HTTP.
- `modbus_mapping.json` - mapeamento de coils, registradores e IPs.
- `config.env` - configuração de ambiente, como `PLC_IP` e `LOG_LEVEL`.
- `README.md` - documentação do sistema e exemplo de endpoint FastAPI.

## `main.py` - componentes principais

### Importações e inicialização

`main.py` importa:
- `pymodbus.client.sync.ModbusTcpClient`
- `dotenv.load_dotenv`

Ele carrega o arquivo `.env`:
- `load_dotenv("config.env")`

Configura logging em:
- `smartphone.log`
- `sys.stdout`

Carrega o mapeamento:
- `modbus_mapping_path = os.path.join(os.path.dirname(__file__), "modbus_mapping.json")`
- `modbus_dict = json.load(f)`

### Função `_register_to_string(registers)`

- Converte valores de registradores Modbus em string ASCII.
- Recebe cada valor de 16 bits.
- Separa bytes low/high e monta `byte_array`.
- Faz `decode('ascii', errors='ignore')`.
- Retira nulos e caracteres de controle.

### Função `send_to_endpoint_async(endpoint, payload)`

- Envia `POST` JSON para `endpoint`.
- Usa `requests.post(endpoint, json=payload, timeout=15)`.
- Registra sucesso ou erro no log.
- Executada em thread daemon.

### Classe `ModbusMaster`

Arquivo: `main.py`

#### `__init__(host, port, unit)`
- Cria `ModbusTcpClient(host=self.host, port=self.port, timeout=3)`
- Inicializa `self.is_connected = False`

#### `connect()`
- Chama `self.client.connect()`
- Atualiza `is_connected`
- Registra no log se conectou ou falhou

#### `disconnect()`
- Fecha cliente Modbus
- Define `is_connected = False`

#### `read_all_coils()`
- Lê o bloco de coils definido em `modbus_dict['coils']['meta']`
- Usa `start` e `count`
- Cria `address_to_name` invertendo `modbus_dict['coils']['data']`
- Lê coils com `self.client.read_coils(start, count, unit=self.unit)`
- Se `response.isError()`: força reconexão no próximo ciclo
- Converte bits em dicionário `named_coils[name] = state`

#### `read_label_code_from_registers(label_code_name)`
- Lê registradores definidos em `modbus_dict['registers'][label_code_name]`
- Usa `start` e `size`
- Retorna string via `_register_to_string(registers)`
- Caso de erro grava log e retorna `None`

#### `write_coil(name, value)`
- Busca `address = modbus_dict['coils']['data'][name]`
- Escreve coil com `self.client.write_coil(address=address, value=value)`

### Loop principal

Arquivo: `main.py`

#### `main()`
- Lê `PLC_IP` de `config.env`
- Se ausente, usa padrão `"192.168.100.22"`
- Cria `modbus_master = ModbusMaster(plc_ip, 10000, 1)`
- Loop infinito:
  - `run_loop(modbus_master)`
  - `time.sleep(0.10)`

#### `run_loop(modbus_master)`
- Se não conectado, chama `modbus_master.connect()`
- Se conectado, chama `modbus_master.read_all_coils()`
- Se obteve `coils`, chama:
  - `handle_jig_bt(modbus_master, coils)`
  - `handle_jig_dl(modbus_master, coils)`
  - `handle_jig_ft(modbus_master, coils)`
- Captura exceções gerais e grava no log

## Handlers em `main.py`

### `handle_jig_dl(modbus_master, coils)`

- Verifica dois sinais:
  - `DL_1_8_PRONTO`
  - `DL_9_16_PRONTO`
- Cada sinal usa IP definido em `modbus_dict['ips']['DL'][...]`
- Se ativo:
  - `time.sleep(0.5)`
  - Lê 8 códigos `CODE_DL_1`...`CODE_DL_8` ou `CODE_DL_9`...`CODE_DL_16`
  - Monta `labels_payload` com chaves `"1"` a `"8"`
  - Reseta a coil:
    - `modbus_master.write_coil(coil_name, False)`
  - Envia para endpoint:
    - `endpoint = f"{ip}/trigger"`
    - `send_to_endpoint_async(endpoint, {"mapped_labels": labels_payload})`

### `handle_jig_bt(modbus_master, coils)`

- Verifica coils:
  - `BT_1_PRONTO` ... `BT_8_PRONTO`
- Para cada coil ativa:
  - `time.sleep(2.0)`
  - Lê registrador `CODE_BT_i`
  - Reseta coil `BT_i_PRONTO`
  - Se `label` válido:
    - envia `{"label_code": label.strip()}`
    - endpoint definido em `modbus_dict['ips']['BT'][f'BT_{i}']`

### `handle_jig_ft(modbus_master, coils)`

- Verifica coils:
  - `FT_1_PRONTO` ... `FT_8_PRONTO`
- Para cada coil ativa:
  - `time.sleep(2.0)`
  - Lê registrador `CODE_FT_i`
  - Reseta coil `FT_i_PRONTO`
  - Se `label` válido:
    - envia `{"label_code": label.strip()}`
    - endpoint definido em `modbus_dict['ips']['FT'][f'FT_{i}']`

## `modbus_mapping.json`

Este arquivo define os mapeamentos usados em `main.py`.

Estrutura esperada:

- `coils.meta.start_address`
- `coils.meta.size`
- `coils.data` → nome da coil para endereço Modbus
- `registers` → cada `CODE_...` tem `start_address` e `size`
- `ips.DL`, `ips.BT`, `ips.FT` → IPs dos endpoints de cada estação

Exemplo de uso:
- `main.py` usa `modbus_dict['coils']['data'][name]` em `write_coil()`
- `main.py` usa `modbus_dict['registers'][label_code_name]` em `read_label_code_from_registers()`
- `main.py` usa `modbus_dict['ips']['BT'][...]`, `['FT'][...]`, `['DL'][...]` para construir endpoints

## `config.env`

Define variáveis de ambiente usadas por `main.py`:

- `PLC_IP=192.168.100.20`
- `LOG_LEVEL=INFO`

## Endpoints HTTP

O master (`main.py`) envia dados para endpoints HTTP no formato:

- `POST /trigger`
- `Content-Type: application/json`

Payloads:
- DL em lote:
  - `{"mapped_labels": {"1": "code1", ..., "8": "code8"}}`
- BT/FT individual:
  - `{"label_code": "2612310111M07"}`

### Exemplo de endpoint

O README antigo traz um exemplo de FastAPI que recebe `label_code` e usa PyAutoGUI para digitar no PC de teste.

Arquivo exemplo descrito:
- `smartphone/README.md` (conteúdo do endpoint FastAPI)

O endpoint exposto deve executar:
- `pyautogui.write(label_code)`
- `pyautogui.press('enter')`

## Deploy

Com base nas informações coletadas:

- Instalar dependências:
  - `pip install -r requirements.txt`
- Gerar executável do master:
  - `pyinstaller --onefile --console --name smartphone-master --uac-admin main.py`
- Gerar executável dos endpoints:
  - `pyinstaller --onefile --console --name endpoint-bt --uac-admin endpoint_bt.py`

## Logs e Troubleshooting

Logs são gravados em:
- `smartphone.log`

Se ocorrer falha:
- Verificar `PLC_IP` em `config.env`
- Confirmar conectividade ao CLP
- Validar IPs e portas dos endpoints
- Conferir firewall na porta `8000`
- Testar endpoint com:
  - `curl -X POST http://192.168.100.100:8000/trigger -H "Content-Type: application/json" -d '{"label_code":"TESTE123"}'`

## Observações

- `main.py` é o núcleo do ecossistema e coordena leitura Modbus e envio HTTP.
- `modbus_mapping.json` é a referência única para endereços e IPs.
- Os endpoints devem estar disponíveis nas máquinas de teste BT, FT e DL para receber os códigos.
