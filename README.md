# Meshtastic Monitor — uConsole CM4

Interface gráfica avançada para monitorização e comunicação em redes Meshtastic,
optimizada para o ClockworkPi uConsole CM4. Conecta via TCP ao daemon `meshtasticd`.

## Estrutura do projecto

```
meshtastic_monitor/
│
├── main.py              ← Ponto de entrada — executa aqui
├── constants.py         ← Cores, estilos Qt, APP_STYLESHEET, MAP_THEMES
├── models.py            ← FavoritesStore, NodeTableModel, NodeFilterProxyModel, _safe_update
├── worker.py            ← MeshtasticWorker (TCP + pubsub + processamento de pacotes)
├── dialogs.py           ← ConnectionDialog, ConsoleWindow, RebootWaitDialog, _LogHandler
│
├── tabs/
│   ├── __init__.py
│   ├── tab_nodes.py     ← MapWidget com traceroutes e NeighborInfo (Leaflet)
│   ├── tab_messages.py  ← MessagesTab — canais, DMs PKI/PSK
│   ├── tab_config.py    ← ConfigTab, ChannelsTab, todas as definições de config Meshtastic
│   └── tab_metrics.py   ← MetricsTab — Canal, RF, Tráfego, Bateria, Fiabilidade, Latência
│
└── requirements.txt
```

## Dependências de importação

```
constants  ←── (sem dependências locais)
models     ←── constants
worker     ←── constants, dialogs (_LogHandler)
dialogs    ←── constants
tabs/*     ←── constants  [tab_nodes também importa models (_FAVORITES)]
main       ←── constants, models, worker, dialogs, tabs/*
```

## Como executar

```bash
cd meshtastic_monitor/
python3 main.py
```

Ou a partir do directório pai:

```bash
python3 meshtastic_monitor/main.py
```

## Instalação de dependências

```bash
pip install meshtastic PyQt5 PyQtWebEngine pypubsub
```

## Módulos e responsabilidades

| Ficheiro | Linhas | Conteúdo |
|---|---|---|
| `constants.py` | ~297 | Todas as cores, estilos CSS/Qt, constantes globais |
| `models.py` | ~411 | Modelos de dados — tabela de nós, favoritos, filtro |
| `worker.py` | ~1111 | Toda a lógica TCP/pubsub, processamento de pacotes |
| `dialogs.py` | ~330 | Diálogos independentes, log handler |
| `tabs/tab_nodes.py` | ~932 | Mapa Leaflet + traceroutes |
| `tabs/tab_messages.py` | ~620 | Mensagens canal + DM |
| `tabs/tab_config.py` | ~1420 | Configuração completa do nó |
| `tabs/tab_metrics.py` | ~1803 | Métricas em tempo real |
| `main.py` | ~1202 | MainWindow + wiring de sinais |

## Desenvolvido por

**CT7BRA — Tiago Veiga**  
Python 3 · PyQt5 · Meshtastic · Leaflet · Chart.js
