# 📡 Meshtastic Monitor — uConsole CM4

Interface gráfica avançada para monitorização, comunicação e análise de redes
[Meshtastic](https://meshtastic.org) via TCP ao daemon `meshtasticd`.  
Desenvolvida e optimizada para o **ClockworkPi uConsole CM4**, mas funciona em
qualquer sistema Linux/macOS/Windows com Python 3 e PyQt5.

**Versão:** 1.0.beta &nbsp;·&nbsp; **Callsign:** CT7BRA

---

## 🌐 Idiomas

A interface suporta **Português** e **English**, seleccionáveis no diálogo de
ligação. A preferência é guardada entre sessões.

---

## 🚀 Funcionalidades

### 📋 Lista de Nós em Tempo Real

- Lista completa de todos os nós visíveis na rede com actualização automática
- **Colunas:** ID, Nome Longo, Nome Curto, Último Contacto, SNR, Hops, Via
  (RF/MQTT), Latitude, Longitude, Bateria (%), Modelo de Hardware, Último Tipo
  de Pacote
- **Nó local fixado no topo** com fundo âmbar e prefixo 🏠
- **Favoritos** com fundo amarelo destacado, fixados abaixo do nó local (⭐)
- Pesquisa em tempo real por ID, nome longo ou nome curto
- Duplo clique sobre qualquer nó para ver os detalhes completos do último pacote
- **Acções rápidas directamente da lista:**
  - 📧 Enviar DM (mensagem directa) — PKI (E2E) quando a chave pública é
    conhecida, PSK como fallback
  - 🗺 Centrar no mapa
  - 📡 Enviar traceroute
- Barra de dica inferior com legenda dos ícones de acção
- Contador de nós totais e nós activos nas últimas 2 horas

### 🗺 Mapa Interactivo (Leaflet)

- **4 temas de mapa:** 🌑 Escuro · ☀ Claro · 🗺 OpenStreetMap · 🛰 Satélite
- **Marcadores coloridos por estado:**
  - 🟢 Verde — nó seleccionado
  - 🔴 Vermelho — pacote recebido agora
  - 🔵 Azul — activo via RF
  - 🟠 Laranja — via MQTT
  - ⚫ Cinzento — inactivo (>2h)
- **Traceroutes** com linhas verdes sólidas (ida/volta) e tooltips de SNR por
  segmento
- **Vizinhança NeighborInfo** — linhas roxas pontilhadas entre pares de nós
  vizinhos com tooltip de SNR
- **Legenda integrada** no canto inferior direito do mapa
- Popup por nó com informações completas e botão de Traceroute inline
- Painel esquerdo com lista de traceroutes (checkboxes para mostrar/ocultar)
- Botão "Mostrar todas" para alternar visibilidade de todos os traceroutes

### 💬 Mensagens

- **Canais** múltiplos (Primary + Secondary, índices 0-7) com contador de não
  lidos
- **Mensagens Directas (DM):**
  - 🔒 **PKI** (E2E encriptado) quando a chave pública do destinatário é
    conhecida
  - 🔓 **PSK** (chave de canal) como fallback automático
  - Lista de DMs ordenada pela mensagem mais recente
- Indicador ACK/NAK por mensagem enviada
- Suporte a mensagens MQTT (☁)
- Badge 🔴 na aba de Mensagens para mensagens não lidas
- Separadores de data nas conversas ("Hoje", "Ontem", data exacta)

### 🗺 Traceroutes

- Envio de traceroute para qualquer nó da lista ou popup do mapa
- Diálogo de resultado com:
  - **Quando enviamos:** Origem = nó local, Destino = nó remoto
  - **Quando recebemos:** Origem = nó remoto (quem enviou), Destino = nó local
  - Hops de ida e volta com SNR por segmento
  - Indicadores de GPS por nó (📍 com coordenadas, ❓ sem)
  - Botão "Mostrar no Mapa" (quando o destino tem GPS)
- Cooldown de 30s entre traceroutes para proteger o canal
- Notificação quando um traceroute dirigido ao nó local é recebido

### ⚙️ Configuração Completa do Nó

- **Canais:** nome, PSK (Base64/hex/aleatório), papel, uplink/downlink MQTT,
  silenciar, precisão de posição
- **Utilizador:** nome longo, nome curto, licenciado Ham (setOwner)
- **Todas as secções de configuração do firmware:**

| Secção | Campos principais |
|--------|------------------|
| 💻 Dispositivo | Papel do nó, rebroadcast, GPIO, intervalo NodeInfo, TZ, serial |
| 📍 Posição / GPS | Modo GPS, intervalos, smart broadcast, posição fixa, HDOP |
| 🔋 Energia | Power saving, timers de desligamento, ADC, wait Bluetooth, SDS/LS |
| 🌐 Rede / WiFi | SSID/PSK WiFi, NTP, Ethernet, IP estático, gateway, DNS |
| 🖥 Display | Timeout, formato GPS, tipo OLED, flip, acordar por toque, brilho TFT |
| 📡 LoRa | Preset, região, BW/SF/CR, TX power, hop limit, override de frequência |
| 🔵 Bluetooth | Activar, modo de emparelhamento, PIN fixo |
| ☁ MQTT | Servidor, TLS, JSON, map reporting, proxy para cliente |
| 🔌 Serial | Baud rate, modo, GPIO, echo |
| 🔔 Notif. Externa | GPIO, alertas para mensagem/bell, PWM buzzer |
| 📦 Store & Forward | Activar, registos, janela histórico, servidor |
| 📏 Range Test | Activar, intervalo, CSV |
| 📊 Telemetria | Intervalos: dispositivo/ambiente/energia/saúde |
| 💬 Msgs Pre-definidas | Área de texto (uma por linha, máx 200 chars) + encoder rotativo |
| 🎙 Audio / Codec2 | Activar, PTT GPIO, bitrate, GPIOs I2S |
| 🔧 Hardware Remoto | Activar, acesso a pinos indefinidos |
| 🔗 Neighbor Info | Activar, intervalo, transmitir via LoRa |
| 💡 Ilum. Ambiente | Estado LED, corrente, RGB |
| 🔍 Sensor Detecção | GPIO, intervalos, pull-up, trigger high |
| 🧮 Paxcounter | Activar, intervalo |
| 🔐 Segurança | Canal admin, managed mode, serial debug |

- Transacção atómica — firmware reinicia apenas uma vez
- Guardar robusto com conversão de enums via descritor protobuf
- Reconstrução automática da UI ao mudar idioma (todos os labels actualizados)

### 📊 Métricas em Tempo Real (10 Secções)

Actualização automática a cada 5 segundos via JavaScript sem recarregar o HTML.

| Secção | Tipo | O que mede |
|--------|------|-----------|
| 📊 Visão Geral | Misto | Resumo: pacotes, nós activos, SNR, taxa entrega, airtime |
| 📡 Canal & Airtime | 🌐 Rede | Ch. utilization por nó, airtime TX, duty cycle EU (ETSI EN300.220) |
| 📶 Qualidade RF | 🌐 Rede | Histograma SNR, distribuição de hops, avaliação automática da qualidade |
| 📦 Tráfego | 🌐 Rede | Pacotes por tipo, pacotes/min (30 min), RF vs MQTT, padrão de routing |
| 🔋 Nós & Bateria | 🌐 Rede | Bateria (⚡ Powered), tensão, uptime, modelo hardware, GPS |
| ✅ Fiabilidade | 🏠 Local | ACK/NAK/pendente, taxa entrega, duplicados de rede, prob. colisão |
| ⏱ Latência (RTT) | 🏠 Local | RTT médio/mín/máx/P90 entre envio e ACK do destinatário |
| 🔗 Vizinhança | 🌐 Rede | Pares de vizinhos directos com SNR (NeighborInfo) |
| 📏 Alcance & Links | 🌐 Rede | Distância km entre vizinhos com GPS (fórmula Haversine) |
| ⏰ Intervalos | 🌐 Rede | Intervalo médio entre pacotes por nó (detecta nós agressivos) |

> **🏠 Métrica do Nó Local** — dados exclusivos ao nó local ligado  
> **🌐 Métrica da Rede** — observação passiva de todos os pacotes recebidos

**Ecrãs de espera inteligentes:** Cada métrica detecta automaticamente quando
dados suficientes chegam e faz a transição do ecrã de espera para a vista de
dados sem necessidade de intervenção manual.

### 🔌 Conectividade e Robustez

- Ligação TCP ao daemon **meshtasticd** (por defeito `localhost:4403`)
- **Reconexão automática** com backoff exponencial: 15s → 30s → 60s → 120s
- Watchdog de 12s por tentativa de conexão (detecta handshakes pendurados)
- Polling de segurança a cada 30s para manter o NodeDB sincronizado
- Fallback de `rxTime` para `datetime.now()` (compatível com daemon TCP)
- Nó local sempre visível e fixado no topo da lista

### 🔔 Notificações Sonoras

- Som de notificação ao receber mensagens (activável/desactivável)
- Cadeia de fallback multiplataforma:
  - **Linux:** `aplay` (ALSA, tom 880 Hz gerado) → `paplay` (PulseAudio)
  - **macOS:** `afplay` (som do sistema)
  - **Windows:** `winsound.MessageBeep`
  - **Fallback:** `QApplication.beep()`

### 📤 Acções do Nó Local

- **Enviar Info do Nó** — broadcast do NODEINFO_APP (Ctrl+I)
- **Enviar Posição Manual** — via `localNode.setPosition()` ou fallback manual
  (Ctrl+P)
- **Resetar NodeDB** — limpa a base de dados de nós do firmware
- **Console de Log** — log em tempo real da comunicação TCP

---

## 📁 Estrutura do Projecto

```
meshtastic_monitor/
├── main.py              ← Ponto de entrada · MainWindow · ligação de sinais
├── constants.py         ← Cores, estilos Qt, APP_STYLESHEET, temas do mapa
├── models.py            ← FavoritesStore, NodeTableModel, NodeFilterProxyModel
├── worker.py            ← MeshtasticWorker — TCP/pubsub/processamento de pacotes
├── dialogs.py           ← ConnectionDialog, ConsoleWindow, RebootWaitDialog
├── i18n.py              ← Sistema de internacionalização (PT/EN), função tr()
├── tabs/
│   ├── tab_nodes.py     ← MapWidget (Leaflet, traceroutes, vizinhança)
│   ├── tab_messages.py  ← MessagesTab (canais, DMs PKI/PSK)
│   ├── tab_config.py    ← ConfigTab, ChannelsTab, MESHTASTIC_CONFIG_DEFS
│   ├── tab_metrics.py   ← MetricsTab (orquestração das 10 secções)
│   ├── metrics_data.py  ← MetricsDataMixin (ingestão e cálculo de dados)
│   └── metrics_render.py← MetricsRenderMixin (geração de HTML/JS/Chart.js)
└── requirements.txt
```

---

## ⚙️ Instalação

```bash
pip install -r requirements.txt
# ou directamente:
pip install meshtastic PyQt5 PyQtWebEngine pypubsub
```

### No uConsole CM4 (Debian/Ubuntu/Raspbian)

```bash
sudo apt install python3-pyqt5 python3-pyqt5.qtwebengine python3-pip
pip3 install meshtastic pypubsub --break-system-packages
```

**Requisitos:**
- Python 3.9 ou superior
- `meshtasticd` em execução e acessível na porta 4403
- Display (X11 ou Wayland) para a interface gráfica Qt

---

## 🚀 Execução

```bash
cd meshtastic_monitor/
python3 main.py
```

No primeiro arranque (ou sem preferência guardada), o diálogo de ligação abre
em inglês. Seleccione o idioma no selector antes de ligar. A preferência é
guardada automaticamente em `QSettings`.

---

## 🗂 Ficheiro de Favoritos

Os favoritos são guardados em `~/.meshtastic_monitor_favorites.json` com dados
completos do nó (nome, GPS, chave pública), permitindo que apareçam mesmo
quando não estão no NodeDB do firmware.

---

## 📡 Requisitos do Firmware Meshtastic

| Funcionalidade | Versão mínima |
|---------------|--------------|
| DM PKI (E2E) | ≥ 2.3.0 |
| NeighborInfo via LoRa | ≥ 2.5.13 |
| Traceroute com SNR | ≥ 2.3.2 |
| Canal NeighborInfo privado | ≥ 2.5.13 |

> **Nota:** NeighborInfo via LoRa requer canal primário **privado** — o canal
> público (LongFast/ShortFast com chave padrão) bloqueia este tráfego desde o
> firmware 2.5.13.

---

## 🧑‍💻 Desenvolvido por

**CT7BRA — Tiago Veiga**  
Python 3 · PyQt5 · Meshtastic · Leaflet · Chart.js  
Optimizado para ClockworkPi uConsole CM4

---

## 🤖 Nota sobre Inteligência Artificial

Este projecto foi desenvolvido com o apoio do **Claude** (Anthropic), um
assistente de inteligência artificial. A IA colaborou activamente em múltiplas
sessões de desenvolvimento, contribuindo para:

- Arquitectura e refactoring do código (separação em módulos/mixins)
- Sistema de internacionalização (i18n) completo PT/EN
- Implementação das 10 secções de métricas em tempo real
- Sistema de traceroutes com lógica de origem/destino correcta
- Detecção e correcção de bugs (duplicados no NodeDB, condições de corrida no mapa, fugas de sinais Qt)
- Análise de performance e optimizações para o CM4

O código foi revisto, testado e validado pelo autor em hardware real
(ClockworkPi uConsole CM4) com uma rede Meshtastic activa.
