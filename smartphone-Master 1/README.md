# Documentação Técnica - Sistema de Automação Smartphone Jabil
### Visão Geral
Sistema de automação industrial que integra um CLP (Controlador Lógico Programável) 
com endpoints HTTP para processamento de códigos de etiquetas em diferentes estações de teste: 
DL (Data Logger), BT (Bluetooth) e FT (Functional Test).
 
## 🏗 Arquitetura do Sistema
  ```
    PLC[CLP Modbus TCP<br/>192.168.100.20:502] --> MAIN[Software Master<br/>main.py]
    MAIN --> DL1[DL Endpoint 1-8<br/>192.168.100.5:8000]
    MAIN --> DL2[DL Endpoint 9-16<br/>192.168.100.10:8000]
    MAIN --> BT1[BT_1 Endpoint<br/>192.168.100.100:8000]
    MAIN --> BT2[BT_2 Endpoint<br/>192.168.100.105:8000]
    MAIN --> FT1[FT_1 Endpoint<br/>192.168.100.140:8000]
    MAIN --> FT2[FT_2 Endpoint<br/>192.168.100.145:8000]
````

 
##  Estrutura do Projeto
``` 
Smartphone-jabil/
        ├── main.py                 # Software principal (Master)
        ├── modbus_mapping.json     # Configuração de endereços Modbus e IPs
        ├── config.env             # Configurações do ambiente
        ├── requirements.txt       # Dependências Python
        ├── smartphone.log         # Arquivo de logs
        └── README.md             # Documentação
```
 
##  Configuração de Hardware
### Endereçamento Modbus TCP
``` CLP: 192.168.100.20:502 (Unit ID: 1)
Range de Coils: 100-117 (18 coils)
Range de Registers: 100-410 (310 registers)
```
### Mapeamento de Coils
```
Coil           Endereço    Descrição
DL_1_8_PRONTO     100      Sinal pronto para DL 1-8
DL_9_16_PRONTO    101      Sinal pronto para DL 9-16
BT_1_PRONTO       102      Sinal pronto para BT_1
BT_2_PRONTO       103      Sinal pronto para BT_2
...               ...       ...
BT_8_PRONTO       109      Sinal pronto para BT_8
FT_1_PRONTO       110      Sinal pronto para FT_1
...               ...       ...
FT_8_PRONTO       117      Sinal pronto para FT_8
```
## Mapeamento de Registers (Códigos)
Register       Endereço     Tamanho      Descrição
CODE_DL_1       100         10 words     Código da etiqueta DL_1
CODE_DL_2       110         10 words     Código da etiqueta DL_2
...             ...         ...          ...
CODE_BT_1       260         10 words     Código da etiqueta BT_1
...             ...         ...          ...
CODE_FT_8       410         10 words     Código da etiqueta FT_8

## Mapeamento de Registers (Códigos)
```
Register      Endereço      Tamanho      Descrição
CODE_DL_1     100           10 words     Código da etiqueta DL_1
CODE_DL_2     110           10 words     Código da etiqueta DL_2
...           ...           ...          ...
CODE_BT_1     260           10 words     Código da etiqueta BT_1
...           ...           ...          ...
CODE_FT_8     410           10 words     Código da etiqueta FT_8
```
------------------------------------------

#  Fluxo de Operação
```
1. Ciclo Principal``` python
while True:
    ├── Conectar ao CLP via Modbus TCP
    ├── Ler todos os coils (100-117)
    ├── Processar DL (handle_jig_dl)
    ├── Processar BT (handle_jig_bt)  
    ├── Processar FT (handle_jig_ft)
    └── Aguardar 1 segundo
```

## 2. Processamento DL (Data Logger)
```
Tipo: Processamento em lote (múltiplos códigos)
Grupos: DL_1_8 (códigos 1-8) e DL_9_16 (códigos 9-16)
Endpoint: /trigger com payload {"label_codes": [array]}``` json
{
  "label_codes": [
    "2612310111M07",
    "2612212209M00",
    "2612212221M08"
  ]
}
```
## 3. Processamento BT/FT (Individual)

***
 * Tipo: Processamento individual (um código por vez)
 * Jigs: 8 estações independentes cada (BT_1 a BT_8, FT_1 a FT_8)
 * Endpoint: /trigger com payload {"label_code": "string"}``` json
***
```
{
  "label_code": "2612310111M07"
}
```

 
#  Endpoints HTTP
 * DL Endpoints (Múltiplos Códigos)
 * DL 1-8: http://192.168.100.5:8000/trigger``` http

```
POST /trigger

Content-Type: application/json

{
  "label_codes": ["code1", "code2", "code3", ...]
}
```

 * DL 9-16: http://192.168.100.10:8000/trigger``` http

```
POST /trigger
Content-Type: application/json

{
  "label_codes": ["code9", "code10", "code11", ...]
}
```

 * BT Endpoints (Código Individual)
 * BT_1: http://192.168.100.100:8000/trigger
 * BT_2: http://192.168.100.105:8000/trigger
...
 * BT_8: http://192.168.100.135:8000/trigger
``` 
http
POST /trigger
Content-Type: application/json

{
  "label_code": "2612310111M07"
}
```

* FT Endpoints (Código Individual)
* FT_1: http://192.168.100.140:8000/trigger
* FT_2: http://192.168.100.145:8000/trigger
...
* FT_8: http://192.168.100.175:8000/trigger
``` 
http
POST /trigger
Content-Type: application/json

{
  "label_code": "2612310111M07"
}
```

 
##  Exemplo de Endpoint (FastAPI)
```
from fastapi import FastAPI
from pydantic import BaseModel
import time
import pyautogui
import uvicorn

# Desabilitar fail-safe do PyAutoGUI
pyautogui.FAILSAFE = False

app = FastAPI()

class LabelCodeRequest(BaseModel):
    label_code: str  # Para BT/FT (individual)
    # label_codes: List[str]  # Para DL (múltiplos)

@app.post("/trigger")
async def trigger(request: LabelCodeRequest):
    label_code = request.label_code
    
    print(f" Label recebido: {label_code}")
    
    try:
        time.sleep(0.5)
        pyautogui.write(label_code)
        pyautogui.press('enter')
        
        print(" Código digitado!")
        return {"status": "success"}
        
    except Exception as e:
        print(f" Erro: {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

 
###   Configuração e Deploy
1. Dependências
``` bash
pip install -r requirements.txt
```

2. Gerar Executável
``` bash
# Software Master
pyinstaller --onefile --console --name smartphone-master --uac-admin main.py

# Endpoints
pyinstaller --onefile --console --name endpoint-bt --uac-admin endpoint_bt.py
```

3. Configuração de Firewall
``` powershell
# Liberar porta 8000 no Windows Firewall
netsh advfirewall firewall add rule name="Smartphone-Jig-Endpoint" dir=in action=allow protocol=TCP localport=8000
```

4. Variáveis de Ambiente (config.env)
``` env
PLC_IP=192.168.100.20
LOG_LEVEL=INFO
```

 
#  Monitoramento e Logs
* Arquivo de Log: smartphone.log
``` 
[2026-01-23 10:30:15] INFO - Connecting to 192.168.100.20:502 via modbus tcp...
[2026-01-23 10:30:15] INFO - Connected to 192.168.100.20:502
[2026-01-23 10:30:16] INFO - Verificando coil BT_1_PRONTO
[2026-01-23 10:30:16] INFO - Coil BT_1_PRONTO está ativo, processando...
[2026-01-23 10:30:16] INFO - Label coletado para BT_1_PRONTO: 2612310111M07
[2026-01-23 10:30:16] INFO - Enviando POST para http://192.168.100.100:8000/trigger
[2026-01-23 10:30:17] INFO - Sucesso ao enviar. Status: 200
```

 
## ⚠ Troubleshooting
Problemas Comuns
1. Conexão Modbus falha
 * Verificar IP do CLP
 * Confirmar porta 502 aberta
 * Validar Unit ID
2. Endpoint não responde
 * Verificar firewall (porta 8000)
 * Confirmar que endpoint está rodando
 * Testar com curl
3. PyAutoGUI FailSafe
 * Adicionar pyautogui.FAILSAFE = False
 * Evitar mover mouse para cantos da tela

### Comandos de Teste
``` bash
# Teste de conectividade
curl -X POST http://192.168.100.100:8000/trigger -H "Content-Type: application/json" -d '{"label_code": "TESTE123"}'

# Teste de porta
Test-NetConnection -ComputerName 192.168.100.100 -Port 8000
```
##  Manutenção
### **Atualizações de IP**
Edite para alterar endereços dos endpoints. `modbus_mapping.json`
### **Adição de Novos Jigs**
1. Adicionar coils no mapeamento
2. Adicionar registers para códigos
3. Configurar IPs dos endpoints
4. Atualizar funções handler

### **Backup de Configuração**
- `modbus_mapping.json`
- `config.env`
- Logs em `smartphone.log`

##  Resumo Técnico

| **Componente** | **Tecnologia** | **Função** |
| --- | --- | --- |
| Master | Python + PyModbus | Comunicação com CLP |
| Endpoints | FastAPI + PyAutoGUI | Automação de teclado |
| Protocolo | Modbus TCP | Comunicação industrial |
| Deploy | PyInstaller | Executáveis standalone |
| Log | Python logging | Monitoramento |
* Janeiro 2026