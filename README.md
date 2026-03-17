# 📡 Meshtastic Monitor

Interface gráfica avançada para monitorização e comunicação em redes mesh Meshtastic, optimizada para execução no dispositivo **ClockworkPi uConsole com módulo CM4**.

---

## Funcionalidades

### Lista de Nós
- Tabela em tempo real com todos os nós da rede: ID, nome, último contacto, SNR, hops, via (RF/MQTT), bateria, posição GPS e modelo de hardware
- Nome curto em **verde** para nós activos (vistos nas últimas 2 horas), cinzento para inativos
- Contador de nós totais e online no topo da lista
- Pesquisa em tempo real por ID, nome longo ou nome curto — sem afectar o mapa
- Ordenação por qualquer coluna; favoritos fixos no topo
- Marcação de favoritos (⭐) com persistência entre sessões
- Envio de mensagem directa (DM) com suporte a PKI e PSK
- Botão de traceroute por nó
- Botão de localização no mapa por nó

### Mapa Interactivo
- Mapa Leaflet com 4 temas: Escuro, Claro, OpenStreetMap, Satélite
- Marcadores coloridos por estado:
  - 🔴 **Vermelho** — nó que enviou o último pacote recebido (persiste até outro tomar o lugar)
  - 🔵 **Azul** — nó RF activo
  - 🟠 **Laranja** — nó via MQTT
  - ⚫ **Cinzento** — nó inactivo (sem pacotes há mais de 2 horas)
  - 🟢 **Verde** — nó seleccionado
- Popup por nó com: ID, via, SNR, bateria, encriptação, último contacto, botão de traceroute
- Tooltip rápido com nome curto, via, SNR e bateria
- Redesenho automático ao receber pacotes em tempo real

### Traceroute
- Sidebar com lista de traceroutes realizados (checkboxes para mostrar/ocultar)
- Linhas de rota no mapa:
  - **Verde claro** → rota de ida
  - **Verde escuro** → rota de volta
  - Linhas paralelas com offset de 3px quando ida e volta partilham o mesmo caminho
  - Linhas centradas quando só existe uma direcção
  - Redesenho automático ao fazer zoom (offset em píxeis, independente do nível de zoom)
- Tooltip com nós de cada hop, SNR por segmento, e aviso de nós sem GPS
- Verificação de traceroute duplicado antes de enviar
- Bloqueio de novo envio durante contagem regressiva de 30s
- Detecção de traceroutes de terceiros com pedido de confirmação para visualizar
- Nomes curtos dos nós na lista de traceroutes

### Mensagens
- Chat por canal (0–7) e mensagens directas (DM)
- Suporte a encriptação PKI (curva 25519) e PSK por canal
- Indicadores de estado de entrega: enviando, ACK implícito, ACK confirmado, NAK com motivo
- Número de hops em cada mensagem recebida
- Histórico por sessão com separadores de data

### Configurações
- Edição completa das configurações do nó local através de todas as secções:
  - Utilizador (nome longo, nome curto, licença)
  - Canais (PSK em Base64, papel, uplink/downlink MQTT, precisão de posição, silenciar)
  - Dispositivo, Posição/GPS, Energia, Rede/WiFi, Display, LoRa, Bluetooth
  - MQTT, Serial, Notif. Externa, Store & Forward, Range Test, Telemetria
  - Msgs Pre-definidas, Audio/Codec2, Hardware Remoto, Neighbor Info
  - Iluminação Ambiente, Sensor de Detecção, Paxcounter, Segurança
- Transacção atómica: `beginSettingsTransaction` / `commitSettingsTransaction` — o nó reinicia apenas uma vez
- Gerador de chave PSK integrado (256-bit, 128-bit ou Default)
- Após guardar: desliga automaticamente e apresenta diálogo de espera com contador de 15s antes de reconectar

### Ferramentas
- Reset do NodeDB do nó local
- Consola de logs em tempo real (janela não-bloqueante, `Ctrl+L`) com filtro por palavra-chave

### Conectividade
- Ligação TCP ao daemon `meshtasticd` local (padrão: `localhost:4403`)
- Reconexão automática com backoff exponencial (5s → 10s → 30s → 60s) ao perder a ligação
- Favoritos persistidos localmente — nós favoritos aparecem na lista mesmo sem estarem no NodeDB activo

---

## Requisitos do Sistema

| Componente | Versão mínima |
|---|---|
| Python | 3.9+ |
| PyQt5 | 5.15+ |
| PyQtWebEngine | 5.15+ |
| meshtastic (lib) | 2.3+ |
| meshtasticd | Qualquer versão recente |
| Sistema operativo | Linux (testado em Debian/Raspbian no uConsole CM4) |

---

## Instalação

### 1. Clonar o repositório

```bash
git clone https://github.com/utilizador/meshtastic-monitor.git
cd meshtastic-monitor
```

### 2. Instalar dependências Python

```bash
pip install -r requirements.txt --break-system-packages
```

> Em sistemas Debian/Raspberry Pi OS com Python gerido pelo sistema, use sempre a flag `--break-system-packages`.

### 3. Dependências do sistema (se necessário)

```bash
sudo apt update
sudo apt install python3-pyqt5 python3-pyqt5.qtwebengine python3-pyqt5.qtsvg
```

### 4. Garantir que o meshtasticd está em execução

```bash
sudo systemctl status meshtasticd
# Se não estiver activo:
sudo systemctl start meshtasticd
```

### 5. Executar

```bash
python3 meshtastic_monitor.py
```

---

## Configuração da Ligação

Na janela de ligação (`Ctrl+K` ou menu **Conexão → Conectar…**):

| Campo | Padrão | Descrição |
|---|---|---|
| Host | `localhost` | Endereço IP ou hostname do daemon |
| Porta | `4403` | Porta TCP do meshtasticd |

---

## Estrutura de Ficheiros

```
meshtastic_monitor.py       Script principal
requirements.txt            Dependências Python
~/.meshtastic_monitor_favorites.json   Favoritos persistidos (criado automaticamente)
```

---

## Notas para o uConsole CM4

- O débounce do mapa está configurado para 800ms para não sobrecarregar o GPU VideoCore IV
- O poll de sincronização do NodeDB corre a cada 15 segundos
- O timer de traceroute está a 1 segundo (suficiente para detectar cliques sem pressão no CPU)
- Toda a saída de logs está desactivada no terminal — usar a consola integrada (`Ctrl+L`)
- As bibliotecas `meshtastic` e `pubsub` estão silenciadas para nível WARNING

---

## Licença

MIT — livre para uso, modificação e distribuição.
