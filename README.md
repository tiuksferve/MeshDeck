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
- Indicador de leitura por canal e por DM
- ACK/NAK por mensagem enviada

### ⚙️ Configuração Completa do Nó
- Todas as secções de localConfig e moduleConfig do firmware Meshtastic
- Canais: PSK, nome, papel, uplink/downlink MQTT
- Mensagens pré-definidas com área de texto (separadas por |)
- Transacção atómica — firmware reinicia só uma vez

### 📊 Métricas em Tempo Real (10 secções)

| Secção | Tipo | O que mede |
|--------|------|-----------|
| 📊 Visão Geral | Misto | Resumo: pacotes, nós, SNR, taxa entrega |
| 📡 Canal & Airtime | 🌐 Rede | Channel utilization, airtime TX, duty cycle EU |
| 📶 Qualidade RF | 🌐 Rede | Histograma SNR, hops, avaliação automática |
| 📦 Tráfego | 🌐 Rede | Pacotes por tipo, pacotes/min, RF vs MQTT |
| 🔋 Nós & Bateria | 🌐 Rede | Bateria, tensão, uptime, hardware model, GPS |
| ✅ Fiabilidade | 🏠 Local | ACK/NAK, taxa entrega, duplicados, colisões |
| ⏱ Latência (RTT) | 🏠 Local | RTT médio/mín/máx/P90 (envio→ACK) |
| 🔗 Vizinhança | 🌐 Rede | Pares vizinhos directos com SNR |
| 📏 Alcance & Links | 🌐 Rede | Distância km entre vizinhos com GPS |
| ⏰ Intervalos | 🌐 Rede | Intervalo entre pacotes por nó |

> **🏠 Métrica do Nó Local** — exclusivo ao nó ligado  
> **🌐 Métrica da Rede** — todos os pacotes observados

---

## 📁 Estrutura do Projecto

```
meshtastic_monitor/
├── main.py              ← Ponto de entrada
├── constants.py         ← Cores e estilos Qt
├── models.py            ← Modelos de dados e favoritos
├── worker.py            ← Comunicação TCP com o daemon
├── dialogs.py           ← Diálogos auxiliares
├── tabs/
│   ├── tab_nodes.py     ← Mapa Leaflet e lista de traceroutes
│   ├── tab_messages.py  ← Canais e DMs
│   ├── tab_config.py    ← Configuração completa do nó
│   └── tab_metrics.py   ← 10 secções de métricas
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
completos do nó (nome, GPS, chave pública).

---

## 🧑‍💻 Desenvolvido por

**CT7BRA — Tiago Veiga**  
Python 3 · PyQt5 · Meshtastic · Leaflet · Chart.js  
Optimizado para ClockworkPi uConsole CM4
