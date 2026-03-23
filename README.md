# 📡 Meshtastic Monitor — uConsole CM4

Interface gráfica avançada para monitorização, comunicação e análise de redes
[Meshtastic](https://meshtastic.org) via TCP ao daemon `meshtasticd`.  
Desenvolvida e optimizada para o **ClockworkPi uConsole CM4**, mas funciona em
qualquer sistema Linux/macOS/Windows com Python 3 e PyQt5.

---

## 🚀 Capacidades

### 📋 Lista de Nós
- Lista em tempo real de todos os nós visíveis na rede com actualização automática
- Colunas: ID, Nome, Último Contacto, SNR, Hops, Via (RF/MQTT), GPS, Bateria, Hardware, Último Tipo de Pacote
- **Nó local fixado no topo** com fundo âmbar e prefixo 🏠
- **Favoritos** com fundo amarelo destacado e fixados abaixo do nó local (⭐)
- Pesquisa em tempo real por ID, nome longo ou nome curto
- Duplo clique para ver detalhes completos do último pacote recebido
- Ação rápida de DM (📩) e traceroute (📡) directamente da lista
- Indicador visual de encriptação PKI (🔒) vs PSK (📩)
- Contador de nós totais e nós online (últimas 2 horas)

### 🗺 Mapa Interactivo (Leaflet)
- 4 temas: 🌑 Escuro · ☀ Claro · 🗺 OpenStreetMap · 🛰 Satélite
- **Marcadores coloridos** por estado (seleccionado, activo, RF, MQTT, inactivo)
- **Traceroutes** com linhas verdes (ida/volta) e tooltips de SNR por segmento
- **Vizinhança NeighborInfo** — linhas roxas pontilhadas entre pares de nós vizinhos
- **Legenda integrada** no canto inferior direito do mapa
- Popup por nó com informações completas e botão de Traceroute
- Painel esquerdo com lista de traceroutes com checkboxes

### 💬 Mensagens
- Múltiplos canais (Primary + Secondary, índices 0-7)
- DMs com suporte a PKI (E2E) e PSK (fallback automático)
- Indicador de leitura por canal e por DM (🔴)
- ACK/NAK por mensagem enviada

### ⚙️ Configuração Completa do Nó
- Todas as secções de localConfig e moduleConfig do firmware Meshtastic
- Canais: PSK, nome, papel, uplink/downlink MQTT
- Mensagens pré-definidas com área de texto (separadas por |)
- Transacção atómica — firmware reinicia só uma vez

### 🔌 Ligação & Robustez
- Ligação TCP ao daemon `meshtasticd` (por defeito `localhost:4403`)
- **Reconexão automática** com backoff exponencial (15s → 30s → 60s → 120s)
- Watchdog de 12s por tentativa — detecta ligações TCP pendentes sem resposta
- Contagem regressiva visível na status bar durante o processo de reconexão
- Polling de segurança a cada 30s para manter o NodeDB sincronizado

### 📊 Métricas em Tempo Real (10 secções)

Actualizadas automaticamente a cada **5 segundos** via JavaScript incremental (sem redesenho).

| Secção | Tipo | O que mede |
|--------|------|------------|
| 📊 Visão Geral | Misto | Resumo: pacotes, nós, SNR, taxa de entrega |
| 📡 Canal & Airtime | 🌐 Rede | Channel utilization, airtime TX, duty cycle EU (10%/h) |
| 📶 Qualidade RF | 🌐 Rede | SNR médio/mediano/P10, histograma SNR, hops, avaliação automática |
| 📦 Tráfego | 🌐 Rede | Pacotes por tipo, pacotes/min, RF vs MQTT |
| 🔋 Nós & Bateria | 🌐 Rede | Bateria (⚡ Powered), tensão, uptime, hardware, GPS |
| ✅ Fiabilidade | 🏠 Local + 🌐 Rede | ACK/NAK, taxa entrega, duplicados, probabilidade de colisão |
| ⏱ Latência (RTT) | 🏠 Local | RTT médio/mín/máx/P90 (envio→ACK) |
| 🔗 Vizinhança | 🌐 Rede | Pares vizinhos directos com SNR (requer NEIGHBORINFO_APP) |
| 📏 Alcance & Links | 🌐 Rede | Distância km entre vizinhos com GPS (Haversine) |
| ⏰ Intervalos | 🌐 Rede | Intervalo médio entre pacotes por nó |

> **🏠 Métrica do Nó Local** — exclusivo ao nó ligado  
> **🌐 Métrica da Rede** — todos os pacotes observados

#### ⚠ Vizinhança e Alcance & Links
Estas métricas requerem o módulo **Neighbor Info** activo com **Transmit Over LoRa** habilitado (firmware ≥ 2.5.13) e um **canal privado** — o canal público (LongFast/ShortFast com chave padrão) bloqueia este tráfego desde o firmware 2.5.13. O intervalo mínimo é de **4 horas**, pelo que os primeiros dados podem demorar a aparecer.

---

## 📁 Estrutura do Projecto

```
meshtastic_monitor/
├── main.py                ← Ponto de entrada · MainWindow · ligação de sinais
├── constants.py           ← Cores, estilos Qt, APP_STYLESHEET
├── models.py              ← FavoritesStore, NodeTableModel, NodeFilterProxyModel
├── worker.py              ← MeshtasticWorker — TCP/pubsub/pacotes/reconexão
├── dialogs.py             ← ConnectionDialog, ConsoleWindow, RebootWaitDialog
├── tabs/
│   ├── tab_nodes.py       ← MapWidget (Leaflet, traceroutes, vizinhança)
│   ├── tab_messages.py    ← MessagesTab (canais, DMs PKI/PSK)
│   ├── tab_config.py      ← ConfigTab, configuração completa do nó
│   ├── tab_metrics.py     ← MetricsTab (orquestração UI, timer 5s)
│   ├── metrics_data.py    ← MetricsDataMixin — ingestão e cálculo de dados
│   └── metrics_render.py  ← MetricsRenderMixin — geração HTML/JS por secção
└── requirements.txt
```

---

## ⚙️ Instalação

```bash
pip install -r requirements.txt
# ou
pip install meshtastic PyQt5 PyQtWebEngine pypubsub
```

### No uConsole CM4 (Debian/Ubuntu)

```bash
sudo apt install python3-pyqt5 python3-pyqt5.qtwebengine python3-pip
pip3 install meshtastic pypubsub --break-system-packages
```

**Requisitos:** Python 3.9+ · `meshtasticd` em execução na porta 4403

---

## 🚀 Execução

```bash
cd meshtastic_monitor/
python3 main.py
```

O diálogo de ligação pede o endereço/porta do daemon (`localhost:4403` por defeito).

---

## 🗂 Ficheiro de Favoritos

Os favoritos são guardados em `~/.meshtastic_monitor_favorites.json` com dados
completos do nó (nome, GPS, chave pública), permanecendo visíveis mesmo quando
o nó não está no NodeDB do firmware.

---

## 🧑‍💻 Desenvolvido por

**CT7BRA — Tiago Veiga**  
Python 3 · PyQt5 · Meshtastic · Leaflet · Chart.js  
Optimizado para ClockworkPi uConsole CM4
