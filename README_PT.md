# 📡 MeshDeck — uConsole CM4

Interface gráfica avançada para monitorização, comunicação e análise de redes
[Meshtastic](https://meshtastic.org) via TCP ao daemon `meshtasticd`.  
Desenvolvida e optimizada para o **ClockworkPi uConsole CM4**, mas funciona em
qualquer sistema Linux/macOS/Windows com Python 3 e PyQt5.

**Versão:** 1.0.1-beta.1 &nbsp;·&nbsp; **Callsign:** CT7BRA &nbsp;·&nbsp; **Ano:** 2026

---

## 🌐 Idiomas

A interface suporta **Português** e **English**, seleccionáveis no diálogo de
ligação. A preferência é guardada entre sessões via `QSettings`.

---

## 🚀 Funcionalidades

### 📋 Lista de Nós em Tempo Real

- Lista completa de todos os nós visíveis na rede com actualização automática
- **Colunas:** ID String, ID Num, Nome Longo, Nome Curto, Último Contacto, SNR,
  Hops, Via (RF/MQTT), Latitude, Longitude, Altitude (m), Bateria (%), Modelo
  de Hardware, Último Tipo de Pacote
- **Nó local fixado no topo** com fundo âmbar e prefixo 🏠
- **Favoritos** geridos directamente no firmware do nó (⭐), fixados abaixo do
  nó local com fundo amarelo destacado
- Pesquisa em tempo real por ID, nome longo ou nome curto
- Duplo clique sobre qualquer nó para ver os detalhes completos do último pacote
- **Acções rápidas directamente da lista:**
  - 📧 Enviar DM (mensagem directa) — PKI (E2E) quando a chave pública é conhecida, PSK como fallback
  - 🗺 Centrar no mapa
  - 📡 Enviar traceroute
- Barra de dica inferior com legenda dos ícones
- Contador de nós: total e activos (últimas 2 horas)
- **Feedback de estado imediato** enquanto conecta e carrega os nós:
  - `"🔌 A ligar a host:port…"` aparece imediatamente ao clicar Conectar
  - `"⏳ A carregar nós da rede… (N recebidos)"` actualiza à medida que os nós chegam
  - `"✅ Rede pronta — N nós carregados"` quando o batch inicial termina

### 🗺 Mapa Interactivo (Leaflet)

- **4 temas de mapa:** 🌑 Escuro · ☀ Claro · 🗺 OpenStreetMap · 🛰 Satélite
- **Marcadores coloridos por estado:**
  - 🟢 Verde — nó seleccionado
  - 🔴 Vermelho — pacote recebido agora
  - 🔵 Azul — activo via RF
  - 🟠 Laranja — via MQTT
  - ⚫ Cinzento — inactivo (>2h)
- **Traceroutes** com linhas verdes sólidas (ida/volta) e tooltips de SNR por segmento
- **Vizinhança NeighborInfo** — linhas roxas pontilhadas entre pares de nós vizinhos com tooltip de SNR
- **Legenda integrada** no canto inferior direito do mapa
- Popup por nó com informações completas e botão de Traceroute inline
- Painel esquerdo com lista de traceroutes (checkboxes para mostrar/ocultar)
- Botão "Mostrar todas" para alternar visibilidade de todos os traceroutes

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
- **Caixa Nó Local** — nome, ID, coordenadas GPS, altitude e estado do GPS, **centrado verticalmente** na caixa
- **Caixa Alvo** — nome do nó, distância, SNR (verde/laranja/vermelho), altitude, direcção cardinal — **centrado verticalmente** na caixa
- **Tabela de nós GPS** — todos os nós com GPS conhecido, colunas de largura igual a preencher toda a largura, ordenados por distância ao nó local
- Avisos de estado GPS: activo com fix, activo sem fix, desactivado

### 🗺 Traceroutes

- Envio de traceroute para qualquer nó da lista ou popup do mapa
- Diálogo de resultado com hops de ida e volta, SNR por segmento, indicadores GPS
- Botão "Mostrar no Mapa" (quando o destino tem GPS)
- Cooldown de 30s entre traceroutes
- Notificação quando um traceroute dirigido ao nó local é recebido

### ⚙️ Configuração Completa do Nó

- **Canais:** nome, PSK (Base64/hex/aleatório), papel, uplink/downlink MQTT, silenciar, precisão posição
- **Utilizador:** nome longo, nome curto, licenciado Ham (via setOwner)
- **Todas as 21 secções de configuração do firmware** (Dispositivo, Posição/GPS, Energia, Rede/WiFi, Display, LoRa, Bluetooth, MQTT, Serial, Notif. Externa, Store & Forward, Range Test, Telemetria, Msgs Pré-definidas, Audio/Codec2, Hardware Remoto, Neighbor Info, Ilum. Ambiente, Sensor Detecção, Paxcounter, Segurança)
- Transacção atómica — firmware reinicia apenas uma vez após guardar todas as alterações
- Reconstrução automática da UI ao mudar idioma

### 📊 Métricas em Tempo Real (10 Secções)

Actualização automática a cada 5 segundos via JavaScript sem recarregar o HTML.

| Secção | Tipo | O que mede |
|--------|------|-----------|
| 📊 Visão Geral | Misto | Pacotes, nós activos, SNR, taxa entrega, airtime |
| 📡 Canal & Airtime | 🌐 Rede | Ch. utilization, airtime TX, duty cycle EU (ETSI EN300.220) |
| 📶 Qualidade RF | 🌐 Rede | Histograma SNR, distribuição hops, avaliação automática |
| 📦 Tráfego | 🌐 Rede | Pacotes por tipo, pacotes/min, RF vs MQTT, padrão routing |
| 🔋 Nós & Bateria | 🌐 Rede | Bateria, tensão, uptime, modelo hardware, GPS |
| ✅ Fiabilidade | 🏠 Local | ACK/NAK/pendente, taxa entrega, duplicados, prob. colisão |
| ⏱ Latência (RTT) | 🏠 Local | RTT médio/mín/máx/P90 entre envio e ACK |
| 🔗 Vizinhança | 🌐 Rede | Pares de vizinhos directos com SNR (NeighborInfo) |
| 📏 Alcance & Links | 🌐 Rede | Distância km entre vizinhos com GPS (Haversine) |
| ⏰ Intervalos | 🌐 Rede | Intervalo médio entre pacotes por nó |

### 🔌 Conectividade e Robustez

- Ligação TCP ao daemon **meshtasticd** (por defeito `localhost:4403`)
- **Reconexão automática** com backoff exponencial: 15s → 30s → 60s → 120s
- Watchdog de 12s por tentativa de conexão
- Polling de segurança a cada 30s para manter o NodeDB sincronizado
- **Ligação não bloqueante** — a criação do `TCPInterface` é adiada via
  `QTimer.singleShot(50)` para que a mensagem de estado seja sempre visível
  antes do handshake TCP começar (crítico no CM4 onde o handshake pode demorar
  vários segundos)
- **Carga diferida do NodeDB** — o batch inicial corre depois de a UI pintar,
  mantendo a mensagem "A carregar…" visível durante todo o processo

### ⭐ Favoritos

Os favoritos são geridos **directamente no firmware** do nó local via
`setFavorite()` / `removeFavorite()`. Não é usado nenhum ficheiro local — a
fonte de verdade é sempre o NodeDB do firmware.

### 🔔 Notificações Sonoras

- Som de notificação ao receber mensagens (activável/desactivável)
- Cadeia multiplataforma: `aplay` (Linux) → `afplay` (macOS) → `winsound` (Windows) → `QApplication.beep()`

---

## 📁 Estrutura do Projecto

```
meshdeck/
├── main.py              ← Ponto de entrada · MainWindow · ligação de sinais
├── constants.py         ← Cores, estilos Qt, APP_STYLESHEET
├── models.py            ← FirmwareFavorites, NodeTableModel, NodeFilterProxyModel
├── worker.py            ← MeshtasticWorker — TCP/pubsub/processamento de pacotes
├── dialogs.py           ← ConnectionDialog, ConsoleWindow, RebootWaitDialog
├── i18n.py              ← Sistema de internacionalização (PT/EN), função tr()
├── tabs/
│   ├── tab_nodes.py     ← MapWidget (Leaflet, traceroutes, vizinhança)
│   ├── tab_messages.py  ← MessagesTab (canais, DMs PKI/PSK)
│   ├── tab_navigation.py← NavigationTab (bússola, tabela GPS)
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

**Requisitos:** Python 3.9+, `meshtasticd` na porta 4403, display X11 ou Wayland.

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

## 🤖 Nota sobre Inteligência Artificial

Este projecto foi desenvolvido com o apoio do **Claude** (Anthropic). A IA
colaborou em múltiplas sessões contribuindo para a arquitectura, i18n, as 10
secções de métricas, a aba de navegação, lógica de traceroutes, detecção de
bugs, optimizações de performance para o CM4 e tradução completa PT/EN.

O código foi revisto, testado e validado pelo autor em hardware real
(ClockworkPi uConsole CM4) com uma rede Meshtastic activa.
