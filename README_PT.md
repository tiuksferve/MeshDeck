# 📡 MeshDeck — uConsole CM4

Interface gráfica avançada para monitorização, comunicação e configuração de redes
[Meshtastic](https://meshtastic.org) via TCP ou USB Serial directo.  
Desenvolvida e optimizada para o **ClockworkPi uConsole CM4**, mas funciona em
qualquer sistema Linux/macOS/Windows com Python 3 e PyQt5.

**Versão:** 1.0.3-beta &nbsp;·&nbsp; **Callsign:** CT7BRA &nbsp;·&nbsp; **Ano:** 2026

---

## 🌐 Idiomas

A interface suporta **Português** e **English**, seleccionáveis no diálogo de
ligação. A preferência é guardada entre sessões via `QSettings`.

---

## 🚀 Funcionalidades

### 📋 Lista de Nós em Tempo Real

- Lista completa de todos os nós visíveis na rede com actualização automática
- **Colunas:** ID String, ID Num, Nome Longo, Nome Curto, Último Contacto, SNR,
  Hops, Via (RF/MQTT), Latitude, Longitude, Altitude (m), Bateria (%), Modelo HW,
  Último Tipo de Pacote
- **Nó local fixado no topo** com fundo âmbar e prefixo 🏠
- **Favoritos** geridos directamente no firmware (⭐), fixados abaixo do nó local
- Pesquisa em tempo real por ID, nome longo ou nome curto
- Duplo clique para ver detalhes completos do último pacote recebido
- **Acções rápidas directamente da lista:**
  - 📧 Enviar DM — PKI (E2E) quando a chave pública é conhecida, PSK como fallback
  - 🗺 Centrar no mapa
  - 📡 Enviar traceroute
- Barra de dica inferior com legenda dos ícones
- Contadores de nós: total e activos (últimas 2 horas)
- **Feedback de estado imediato** enquanto conecta e carrega os nós

### 🗺 Mapa Interactivo (Leaflet)

- **4 temas de mapa:** 🌑 Escuro · ☀ Claro · 🗺 OpenStreetMap · 🛰 Satélite
- **Marcadores coloridos por estado:**
  - 🟢 Verde — nó seleccionado
  - 🔴 Vermelho — pacote recebido agora
  - 🔵 Azul — activo via RF
  - 🟠 Laranja — via MQTT
  - ⚫ Cinzento — inactivo (>2h)
- **Traceroutes** com linhas verdes sólidas (ida/volta) e tooltips de SNR por segmento
- **Vizinhança NeighborInfo** — linhas roxas pontilhadas entre pares de nós vizinhos
- **Legenda integrada** no canto inferior direito do mapa
- Popup por nó com informações completas e botão de Traceroute inline
- Painel esquerdo com lista de traceroutes (checkboxes)

### 💬 Mensagens

- **Canais** múltiplos (Primary + Secondary, índices 0-7) com contador de não lidos
- **Mensagens Directas (DM):**
  - 🔒 **PKI** (E2E encriptado) quando a chave pública do destinatário é conhecida
  - 🔓 **PSK** (chave de canal) como fallback automático
  - Lista de DMs ordenada pela mensagem mais recente
- Indicador ACK/NAK por mensagem enviada
- Suporte a mensagens MQTT (☁)
- Badge 🔴 na aba de Mensagens para mensagens não lidas
- Separadores de data nas conversas ("Hoje", "Ontem", data exacta)

### 🧭 Navegação

- **Bússola** — rumo e distância em tempo real do nó local para qualquer nó remoto seleccionado
- **Caixa Nó Local** — nome, ID, coordenadas GPS, altitude, estado GPS, e botão
  **🔄 Posição** para reler as coordenadas GPS do nó em qualquer momento:
  - Lê da cache do daemon (`nodesByNum`) — actualizada com cada pacote GPS recebido
  - Fallback para `localConfig.position.fixed_lat/lon` em nós com posição fixa
  - Mostra `⏳ A ler posição…` enquanto activo; aviso de 3 segundos se sem posição
- **Caixa Alvo** — nome, distância, SNR (verde/laranja/vermelho), altitude, direcção cardinal
- **Tabela de nós GPS** — todos os nós com GPS conhecido, ordenados por distância
- Avisos de estado GPS: activo com fix, activo sem fix, desactivado

### 🗺 Traceroutes

- Envio de traceroute para qualquer nó da lista ou popup do mapa
- Diálogo de resultado com hops de ida e volta, SNR por segmento, indicadores GPS
- Botão "Mostrar no Mapa" (quando o destino tem GPS)
- Cooldown de 30s entre traceroutes
- Notificação quando um traceroute dirigido ao nó local é recebido

### ⚙️ Configuração Completa do Nó

- **Canais:** nome, PSK (Base64/hex/aleatório), papel, uplink/downlink MQTT, silenciar, precisão posição
- **Utilizador:** nome longo, nome curto, licenciado Ham (via `setOwner`) — só guardado quando os valores mudam
- **Todas as 21 secções de configuração do firmware** (Dispositivo, Posição/GPS, Energia,
  Rede/WiFi, Display, LoRa, Bluetooth, MQTT, Serial, Notif. Externa, Store & Forward,
  Range Test, Telemetria, Msgs Pré-definidas, Audio/Codec2, Hardware Remoto,
  Neighbor Info, Ilum. Ambiente, Sensor Detecção, Paxcounter, Segurança)
- **Transacção atómica** — firmware reinicia apenas uma vez após guardar tudo
  (`beginSettingsTransaction` / `commitSettingsTransaction`)
- **Save correcto para proto3:** campos bool `False` são serializados via double-set
  para garantir que chegam ao firmware (mesmo sendo o valor por defeito do protobuf)
- **Lista de campos validada:** todos os campos confirmados contra `config.proto`
  e `module_config.proto` oficiais; campos inexistentes removidos
- **Confirmação detalhada do save:** mostra exactamente que `writeConfig()`, `setOwner`
  e `setCannedMessages` foram enviados ao nó
- Reconstrução automática da UI ao mudar idioma
- `proxy_to_client_enabled` mostrado como read-only com nota explicativa
  (requer protocolo `mqttClientProxyMessage` — previsto para versão futura)

### 📊 Métricas em Tempo Real (11 Secções)

Actualização automática a cada 5 segundos. A secção Nó Local recarrega quando os dados mudam (hash MD5); as restantes actualizam via JavaScript sem recarregar o HTML.

| Secção | Tipo | O que mede |
|--------|------|-----------|
| 📊 Visão Geral | Misto | Pacotes, nós activos, SNR, taxa entrega, airtime |
| 🏠 Nó Local | 🏠 Local | Bateria, Ch. Util., Air TX, duty cycle/h (limite EU), SNR RX, msgs enviadas/ACK/NAK, RTT, uptime (contador live), GPS |
| 📡 Canal & Airtime | 🌐 Rede | Ch. utilization, airtime TX, duty cycle EU (ETSI EN300.220) |
| 📶 Qualidade RF | 🌐 Rede | Histograma SNR, distribuição hops, avaliação automática |
| 📦 Tráfego | 🌐 Rede | Pacotes por tipo, pacotes/min, RF vs MQTT, padrão routing |
| 🔋 Nós & Bateria | 🌐 Rede | Bateria, tensão, uptime, modelo hardware, GPS |
| ✅ Fiabilidade | Misto | ACK/NAK/erros FW separados, taxa entrega, flood windowed, prob. colisão |
| ⏱ Latência (RTT) | 🏠 Local | RTT médio/mín/máx/P90 entre envio e ACK |
| 🔗 Vizinhança | 🌐 Rede | Pares de vizinhos directos com SNR (NeighborInfo) |
| 📏 Alcance & Links | 🌐 Rede | Distância km entre vizinhos com GPS (Haversine) |
| ⏰ Intervalos | 🌐 Rede | Intervalo médio entre pacotes por nó |

**Melhorias de precisão na v1.0.3-beta:**
- P10 de SNR corrigido para `int(0.1*(n-1))` — `n//10` dava valor errado para amostras pequenas
- Taxa de flood windowed (janela 5 min), deixou de ser cumulativa
- Erros `ROUTING_APP` separados: ACK / NAK-entrega / Erros FW (NO_ROUTE, MAX_RETRANSMIT)
- `_ch_util` / `_air_tx` expiram após 30 min sem actualização (TTL)
- Contagem de GPS usa `_node_pos` com coordenadas validadas
### 🔌 Conectividade e Robustez

- Ligação TCP ao daemon **meshtasticd** (por defeito `localhost:4403`)
- **Ligação USB Serial** via bridge integrado — sem necessidade de placa AIO
- **Reconexão automática** com backoff exponencial: 15s → 30s → 60s → 120s
- Watchdog de 12s por tentativa de conexão
- Polling de segurança a cada 30s para manter o NodeDB sincronizado
- **Ligação não bloqueante** — `TCPInterface` adiado via `QTimer.singleShot(50)`

### ⭐ Favoritos

Geridos **directamente no firmware** via `setFavorite()` / `removeFavorite()`.
Sem ficheiro local — a fonte de verdade é sempre o NodeDB do firmware.

### 🔔 Notificações Sonoras

- Som de notificação ao receber mensagens (activável/desactivável)
- Cadeia multiplataforma: `aplay` (Linux) → `afplay` (macOS) → `winsound` (Windows) → `QApplication.beep()`

---

## 🔌 Ligação USB Serial

O MeshDeck pode conectar directamente a um dispositivo Meshtastic via USB sem
necessitar da placa AIO nem de um daemon `meshtasticd` a correr.

### Como funciona

Um bridge integrado (`meshtastic_bridge.py`) lê o stream serial do dispositivo,
filtra ruído de debug/boot, e re-expõe os frames limpos como servidor TCP local
em `127.0.0.1:4403`.

### Hardware suportado

| Chipset | Placas |
|---------|--------|
| Espressif ESP32/S2/S3/C3 | Maioria das placas Meshtastic |
| Silicon Labs CP210x | HELTEC, LILYGO T-Beam, RAK |
| FTDI FT232 | Placas DIY e de desenvolvimento |
| CH340 / CH341 | Placas chinesas de baixo custo |
| Prolific PL2303 | Clones mais antigos |
| Adafruit nRF52840 | Feather, ItsyBitsy |
| RAK Wireless nRF52840 | RAK4631 |

### Como usar

1. Ligar o dispositivo Meshtastic via USB
2. Abrir **🔌 Conexão…** → aba **🔌 USB Serial**
3. Seleccionar a porta no dropdown
4. Clicar **▶ Iniciar Bridge Serial** e aguardar **✅ Bridge activa**
5. Clicar **🔌 Conectar**

### Requisito adicional

```bash
pip install pyserial>=3.5
```

Já incluído em `requirements.txt`.

### Bridge em linha de comandos

```bash
python3 meshtastic_bridge.py --list
python3 meshtastic_bridge.py --port /dev/ttyACM0 --verbose
```

> **Créditos:** Conceito e código original por **[@KMX415](https://github.com/KMX415)**.

---

## 📁 Estrutura do Projecto

```
meshdeck/
├── main.py                  ← Ponto de entrada · MainWindow · ligação de sinais
├── constants.py             ← Cores, estilos Qt, APP_STYLESHEET
├── models.py                ← FirmwareFavorites, NodeTableModel, NodeFilterProxyModel
├── worker.py                ← MeshtasticWorker — TCP/Serial/pubsub/pacotes
├── dialogs.py               ← ConnectionDialog, ConsoleWindow, RebootWaitDialog
├── i18n.py                  ← Sistema de internacionalização (PT/EN), tr()
├── meshtastic_bridge.py     ← Bridge serial USB-para-TCP
├── tabs/
│   ├── tab_nodes.py         ← MapWidget (Leaflet, traceroutes, vizinhança)
│   ├── tab_messages.py      ← MessagesTab (canais, DMs PKI/PSK)
│   ├── tab_navigation.py    ← NavigationTab (bússola, tabela GPS, refresh posição)
│   ├── tab_config.py        ← ConfigTab, ChannelsTab, MESHTASTIC_CONFIG_DEFS
│   ├── tab_metrics.py       ← MetricsTab (orquestração das 11 secções)
│   ├── metrics_data.py      ← MetricsDataMixin (ingestão e cálculo de dados)
│   └── metrics_render.py    ← MetricsRenderMixin (geração HTML/JS/Chart.js)
└── requirements.txt
```

---

## ⚙️ Instalação

```bash
pip install -r requirements.txt
```

### No uConsole CM4 (Debian/Ubuntu/Raspbian)

```bash
sudo apt install python3-pyqt5 python3-pyqt5.qtwebengine python3-pip
pip3 install meshtastic pypubsub pyserial --break-system-packages
```

**Requisitos:** Python 3.9+, display X11 ou Wayland.  
**Modo TCP:** `meshtasticd` a correr na porta 4403.  
**Modo Serial:** dispositivo Meshtastic via USB + `pyserial`.

---

## 🚀 Execução

```bash
cd meshdeck/
python3 main.py
```

---

## 📡 Requisitos do Firmware Meshtastic

| Funcionalidade | Versão mínima |
|---------------|--------------|
| DM PKI (E2E) | ≥ 2.3.0 |
| NeighborInfo via LoRa | ≥ 2.5.13 |
| Traceroute com SNR | ≥ 2.3.2 |
| Favoritos no firmware | ≥ 2.3.0 |

---

## 🧑‍💻 Desenvolvido por

**CT7BRA — Tiago Veiga**  
Python 3 · PyQt5 · Meshtastic · Leaflet · Chart.js  
Optimizado para ClockworkPi uConsole CM4 · 2026

---

## 🤝 Créditos

| Contribuidor | Contribuição |
|--------------|-------------|
| [@KMX415](https://github.com/KMX415) | Conceito e código original do bridge serial |

---

## 🤖 Nota sobre Inteligência Artificial

Este projecto foi desenvolvido com o apoio do **Claude** (Anthropic). A IA
colaborou em múltiplas sessões contribuindo para a arquitectura, i18n, as 10
secções de métricas, a aba de navegação (incluindo o refresh de posição GPS),
a aba de configuração (reescrita completa do pipeline de save, correcção proto3,
auditoria de campos), lógica de traceroutes, detecção e correcção de bugs,
optimizações de performance para o CM4, integração do bridge serial USB,
e tradução completa PT/EN.

O código foi revisto, testado e validado pelo autor em hardware real
(ClockworkPi uConsole CM4) com uma rede Meshtastic activa.
