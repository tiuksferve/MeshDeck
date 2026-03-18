"""
i18n.py — Internacionalização do Meshtastic Monitor.
Suporte a Inglês (padrão) e Português.

Uso:
    from i18n import tr, set_language, get_language

    label = tr("Node List")           # devolve string na língua activa
    set_language("pt")                # muda para português
    set_language("en")                # muda para inglês
"""

_LANG = "en"   # língua activa: "en" | "pt"
_CALLBACKS: list = []   # funções chamadas quando a língua muda

# ── Dicionário de traduções ─────────────────────────────────────────
# Formato: { "English string": "Portuguese string" }
# Strings sem tradução devolvem o original.
_PT: dict = {

    # ── Menus & títulos gerais ────────────────────────────────────
    "Connection": "Ligação",
    "Connect...": "Ligar...",
    "Disconnect": "Desligar",
    "Reset NodeDB": "Apagar NodeDB",
    "Node": "Nó",
    "Send Node Info": "Enviar Info do Nó",
    "Send Position": "Enviar Posição",
    "About": "Sobre",
    "About Meshtastic Monitor": "Sobre o Meshtastic Monitor",
    "Language": "Língua",
    "Change Language": "Alterar Língua",
    "Console": "Consola",
    "Show Console": "Mostrar Consola",

    # ── Abas principais ───────────────────────────────────────────
    "Nodes": "Nós",
    "Messages": "Mensagens",
    "Map": "Mapa",
    "Metrics": "Métricas",
    "Configuration": "Configuração",
    "💬  Messages": "💬  Mensagens",
    "💬  Messages  🔴": "💬  Mensagens  🔴",

    # ── ConnectionDialog ──────────────────────────────────────────
    "Configure Connection": "Configurar Conexão",
    "📡  Meshtastic Server Connection": "📡  Conexão ao Servidor Meshtastic",
    "Address:": "Endereço:",
    "Port:": "Porta:",
    "ex: localhost  or  192.168.1.1": "ex: localhost  ou  192.168.1.1",
    "💡 Default address for local daemon is <b>localhost</b> port <b>4403</b>.":
        "💡 O endereço padrão para o daemon local é <b>localhost</b> porta <b>4403</b>.",
    "Cancel": "Cancelar",
    "🔌  Connect": "🔌  Conectar",
    "Interface Language:": "Língua da Interface:",
    "English": "Inglês",
    "Portuguese": "Português",

    # ── LanguageDialog ────────────────────────────────────────────
    "Select Language": "Seleccionar Língua",
    "Choose the interface language:": "Escolha a língua da interface:",
    "Apply": "Aplicar",
    "Language changed. Some elements may require reconnection to fully update.":
        "Língua alterada. Alguns elementos podem requerer religação para actualização completa.",

    # ── Node list ─────────────────────────────────────────────────
    "⭐": "⭐",
    "📩": "📩",
    "🗺": "🗺",
    "📡": "📡",
    "ID String": "ID String",
    "ID Num": "ID Num",
    "Long Name": "Nome Longo",
    "Short Name": "Nome Curto",
    "Last Contact": "Último Contacto",
    "SNR (dB)": "SNR (dB)",
    "Hops": "Hops",
    "Via": "Via",
    "Latitude": "Latitude",
    "Longitude": "Longitude",
    "Altitude (m)": "Altitude (m)",
    "Battery (%)": "Bateria (%)",
    "Model": "Modelo",
    "Last Type": "Último Tipo",
    "Search nodes...": "Pesquisar nós...",
    "Nodes:": "Nós:",
    "⬤ {} online": "⬤ {} online",
    "⏳ Waiting for Info": "⏳ Aguardando Info",
    "Never": "Nunca",
    "☁ MQTT": "☁ MQTT",
    "Click to remove from favourites": "Clique para remover dos favoritos",
    "Click to add to favourites": "Clique para adicionar aos favoritos",
    "View on map": "Ver no mapa",
    "No position data": "Sem dados de posição",
    "DM unavailable — node never contacted": "DM indisponível — nó nunca contactado",
    "Send DM 🔒 PKI (public key known)": "Enviar DM 🔒 PKI (chave pública conhecida)",
    "Send DM 🔓 PSK (channel key)": "Enviar DM 🔓 PSK (chave de canal)",
    "🏠 This is your local node": "🏠 Este é o seu nó local",
    "LOCAL": "LOCAL",
    "Details of Last Packet": "Detalhes do Último Pacote",
    "📦  Packet — ": "📦  Pacote — ",
    "Close": "Fechar",

    # ── Map ───────────────────────────────────────────────────────
    "📡  Traceroutes": "📡  Traceroutes",
    "◉  Show all": "◉  Mostrar todas",
    "○  Show all": "○  Mostrar todas",
    "🗑  Clear list": "🗑  Limpar lista",
    "🎨  Theme:": "🎨  Tema:",
    "🌑 Dark": "🌑 Escuro",
    "☀ Light": "☀ Claro",
    "🗺 OpenStreetMap": "🗺 OpenStreetMap",
    "🛰 Satellite": "🛰 Satélite",
    "Selected": "Seleccionado",
    "Last packet": "Último pacote",
    "Inactive (>2h)": "Inactivo (>2h)",
    "Neighbourhood (NeighborInfo)": "Vizinhança (NeighborInfo)",
    "Traceroute forward": "Traceroute ida",
    "Traceroute return": "Traceroute volta",
    "Clear traceroutes?": "Limpar traceroutes?",
    "Are you sure you want to remove all {} traceroute(s)?":
        "Tem a certeza que deseja remover todos os {} traceroute(s)?",
    "The route lines on the map will also be removed.":
        "As linhas de rota no mapa também serão removidas.",
    "Neighbours: {}  ↔  {}  |  SNR: {}": "Vizinhos: {}  ↔  {}  |  SNR: {}",
    "Forward: {}  →  {}  |  SNR: {}": "Ida: {}  →  {}  |  SNR: {}",
    "Return: {}  ←  {}  |  SNR: {}": "Volta: {}  ←  {}  |  SNR: {}",
    "Via (no GPS): ": "Via (sem GPS): ",
    "SNR unknown": "SNR desconhecido",

    # ── Messages tab ──────────────────────────────────────────────
    "Channels": "Canais",
    "Direct Messages": "Mensagens Directas",
    "Select a channel or node to send a message…":
        "Seleccione um canal ou nó para enviar mensagem…",
    "📤  Send": "📤  Enviar",
    "Message to #{} · {}…": "Mensagem para #{} · {}…",
    "Send DM to {}…": "Enviar DM para {}…",
    "📩  Send DM": "📩  Enviar DM",
    "📻  # {}  ·  {}": "📻  # {}  ·  {}",
    "No messages yet": "Sem mensagens ainda",
    "Public key known — PKI DM available (E2E)": "Chave pública conhecida — DM PKI disponível (E2E)",
    "Unknown public key — DM via channel PSK": "Chave pública desconhecida — DM via PSK de canal",
    "🔒 Encrypted": "🔒 Encriptado",
    "Channel {}": "Canal {}",
    "Primary": "Primary",
    "me": "eu",
    "via MQTT": "via MQTT",
    "ACK": "ACK",
    "NAK": "NAK",
    "Pending...": "A aguardar...",

    # ── Config tab ────────────────────────────────────────────────
    "⚙ Local Node Configuration": "⚙ Config. do Nó Local",
    "Not connected": "Não conectado",
    "🔄  Reload": "🔄  Recarregar",
    "💾  Save Changes": "💾  Guardar Alterações",
    "Sections": "Secções",
    "📻 Channels": "📻 Canais",
    "👤 User": "👤 Usuário",
    "Connect to a node to see settings.": "Conecte-se a um nó para ver as configurações.",
    "Loading configuration…": "A carregar configuração…",
    "✅ Configuration loaded": "✅ Configuração carregada",
    "❌ Error loading": "❌ Erro ao carregar",
    "Error: local node unavailable": "Erro: nó local indisponível",
    "Could not load configuration.": "Não foi possível carregar a configuração.",
    "Save Configuration": "Guardar Configuração",
    "Save all configuration changes to the node?\n\n"
    "⚠  The node will restart to apply the settings.\n"
    "    The TCP connection will be temporarily lost and re-established.":
        "Deseja guardar todas as alterações de configuração no nó?\n\n"
        "⚠  O nó irá reiniciar após guardar para aplicar as configurações.\n"
        "    A ligação TCP será temporariamente perdida e restabelecida.",
    "Configuration saved!\n{} section(s) sent to node.":
        "Configuração guardada!\n{} secção(ões) enviadas ao nó.",
    "⚠ {} warning(s):\n": "⚠ {} aviso(s):\n",
    "Nothing saved": "Nada guardado",
    "No changes detected.": "Não foram detectadas alterações para guardar.",
    "Node ID": "ID do Nó",
    "HW Model": "Modelo HW",
    "Firmware": "Firmware",
    "Long Name": "Nome Longo",
    "Short Name": "Nome Curto",
    "Licensed (Ham)": "Licenciado (Ham)",
    "✏  Editable fields — save uses setOwner()":
        "✏  Campos editáveis — guardar usa setOwner()",
    "🔄  Reload": "🔄  Recarregar",
    "➕  Add Channel": "➕  Adicionar Canal",
    "💾  Save Changes": "💾  Guardar Alterações",
    "No connection": "Sem conexão",
    "⚠  No connection": "⚠  Sem conexão",
    "✅  {} channel(s) loaded": "✅  {} canal(ais) carregados",
    "➕  Channel {} added — edit and save": "➕  Canal {} adicionado — edite e guarde",
    "🗑  Channel {} marked for removal — save to apply":
        "🗑  Canal {} marcado para remoção — guarde para aplicar",
    "Max channels reached": "Limite atingido",
    "Maximum of 8 channels (0-7) already reached.":
        "O máximo de 8 canais (0-7) já foi atingido.",
    "Remove Channel": "Remover Canal",
    "Remove channel with index {}?": "Remover o canal com índice {}?",
    "Save Channels": "Guardar Canais",
    "Save all channel changes to the node?\n\n"
    "⚠  The node will restart to apply the changes.\n"
    "    The TCP connection will be temporarily lost and re-established.":
        "Guardar todas as alterações de canais no nó?\n\n"
        "⚠  O nó irá reiniciar para aplicar as alterações.\n"
        "    A ligação TCP será temporariamente perdida e restabelecida.",
    "✅  {} channel(s) saved": "✅  {} canal(ais) guardados",
    "📻  Channel {}": "📻  Canal {}",
    "Name": "Nome",
    "Channel name": "Nome do canal",
    "Role": "Papel",
    "PSK": "PSK",
    "Base64 (e.g.: AQ==)  or  default / none / random":
        "Base64 (ex: AQ==)  ou  default / none / random",
    "256-bit (32 bytes)": "256-bit (32 bytes)",
    "128-bit (16 bytes)": "128-bit (16 bytes)",
    "Default (AQ==)": "Default (AQ==)",
    "🔑 Generate": "🔑 Gerar",
    "Generates a random PSK key of the selected type":
        "Gera uma chave PSK aleatória do tipo seleccionado",
    "MQTT Uplink enabled": "Uplink MQTT habilitado",
    "MQTT Uplink": "Uplink MQTT",
    "MQTT Downlink enabled": "Downlink MQTT habilitado",
    "MQTT Downlink": "Downlink MQTT",
    "Mute notifications (is_muted)": "Silenciar notificações (is_muted)",
    "Mute": "Silenciar",
    "Position precision": "Precisão posição",
    "💡  One message per line · Separated by | in firmware · Max 200 chars total":
        "💡  Uma mensagem por linha · Separadas por | no firmware · Máx. 200 caracteres total",
    "Write one message per line.\nExample:\nHello!\nOn my way\nArriving in 10 min\nNO SIGNAL":
        "Escreva uma mensagem por linha.\nExemplo:\nOlá!\nA caminho\nChegarei em 10 min\nSEM SINAL",
    "{} / 200 characters": "{} / 200 caracteres",
    "No field available for this section.": "Nenhum campo disponível para esta secção.",

    # ── Section labels ────────────────────────────────────────────
    "💻 Device": "💻 Dispositivo",
    "📍 Position / GPS": "📍 Posição / GPS",
    "🔋 Power": "🔋 Energia",
    "🌐 Network / WiFi": "🌐 Rede / WiFi",
    "🖥 Display": "🖥 Display",
    "📡 LoRa": "📡 LoRa",
    "🔵 Bluetooth": "🔵 Bluetooth",
    "☁ MQTT": "☁ MQTT",
    "🔌 Serial": "🔌 Serial",
    "🔔 Ext. Notification": "🔔 Notif. Externa",
    "📦 Store & Forward": "📦 Store & Forward",
    "📏 Range Test": "📏 Range Test",
    "📊 Telemetry": "📊 Telemetria",
    "💬 Canned Messages": "💬 Msgs Pre-definidas",
    "🎙 Audio / Codec2": "🎙 Audio / Codec2",
    "🔧 Remote Hardware": "🔧 Hardware Remoto",
    "🔗 Neighbor Info": "🔗 Neighbor Info",
    "💡 Ambient Lighting": "💡 Ilum. Ambiente",
    "🔍 Detection Sensor": "🔍 Sensor Detecção",
    "🧮 Paxcounter": "🧮 Paxcounter",
    "🔐 Security": "🔐 Segurança",

    # ── Config field labels ───────────────────────────────────────
    "Node role": "Papel do nó",
    "Rebroadcast messages": "Retransmitir mensagens",
    "Serial enabled": "Serial habilitado",
    "Debug via serial": "Debug via serial",
    "Button GPIO": "Botão GPIO",
    "Buzzer GPIO": "Buzzer GPIO",
    "Double tap power": "Duplo clique alimentação",
    "LED heartbeat disabled": "LED em heartbeat",
    "NodeInfo broadcast interval (s)": "Intervalo broadcast NodeInfo (s)",
    "Timezone (TZ string)": "Fuso horário (TZ string)",
    "Disable triple-click": "Disable triple-click",
    "Quick chat button": "Quick chat button",
    "GPS mode": "Modo GPS",
    "GPS update interval (s)": "Intervalo update GPS (s)",
    "GPS attempt time (s)": "Tentativa GPS (s)",
    "Position broadcast interval (s)": "Intervalo broadcast pos (s)",
    "Smart position broadcast": "Smart broadcast pos.",
    "Smart min distance (m)": "Distância mínima smart (m)",
    "Smart min interval (s)": "Intervalo mínimo smart (s)",
    "Fixed latitude (degrees)": "Latitude fixa (graus)",
    "Fixed longitude (degrees)": "Longitude fixa (graus)",
    "Fixed altitude (m)": "Altitude fixa (m)",
    "Position precision flags": "Precision de posição",
    "Receiver GPIO": "Receiver GPIO",
    "Transmitter GPIO": "Transmitter GPIO",
    "Accept SBAS": "Broadcast SBAS",
    "Max HDOP to accept": "Max HDOP para aceitar",
    "Power saving mode": "Modo de economia",
    "Shutdown on battery (s)": "Desligar na bateria (s)",
    "ADC multiplier override": "Override ADC multiplicador",
    "Wait Bluetooth (s)": "Wait Bluetooth (s)",
    "SDS shutdown (s)": "Modo SDS desligar (s)",
    "LS shutdown (s)": "Modo LS desligar (s)",
    "Min wake time (s)": "Tempo mínimo acordado (s)",
    "Battery INA I2C address": "INA endereço I2C bateria",
    "Powersave GPIO": "Powersave GPIO",
    "WiFi enabled": "WiFi habilitado",
    "WiFi SSID": "SSID WiFi",
    "WiFi password": "Senha WiFi",
    "NTP server": "Servidor NTP",
    "Ethernet enabled": "Ethernet habilitada",
    "Address mode": "Modo endereçamento",
    "Static IP": "IP estático",
    "Gateway": "Gateway",
    "Subnet": "Subnet",
    "DNS": "DNS",
    "RSync server": "RSync Server",
    "Screen on (s)": "Ecrã ligado (s)",
    "GPS format": "Formato GPS",
    "Auto carousel (s)": "Múltiplo do auto dim.",
    "Units": "Unidades",
    "OLED type": "OLED tipo",
    "Display mode": "Modo do display",
    "Flip screen": "Flip ecrã",
    "Wake on tap/motion": "Acord. por toque/mov.",
    "Bold heading": "Cabeçalho negrito",
    "Compass north top": "Override largura fone",
    "Backlight secs": "Brilho do backlight",
    "TFT brightness (0-255)": "Brilho TFT (0-255)",
    "Use preset": "Usar preset",
    "Modem preset": "Modem preset",
    "Region": "Região",
    "Bandwidth": "Largura de banda",
    "Spreading factor": "Spreading factor",
    "Coding rate": "Coding rate",
    "Frequency offset (MHz)": "Offset frequência (MHz)",
    "TX enabled": "TX habilitado",
    "TX power (dBm)": "TX Power (dBm)",
    "Hop limit": "Hop limit",
    "Ignore MQTT": "Ignorar MQTT",
    "Override duty cycle": "Override duty cycle",
    "Override frequency (MHz)": "Override frequency (MHz)",
    "RX boosted gain (SX126x)": "RX boosted gain (SX126x)",
    "PA fan disabled": "PA fan GPIO",
    "OK to MQTT": "OK para MQTT",
    "Channel number (0-7)": "Número do canal (0-7)",
    "Enabled": "Habilitado",
    "Pairing mode": "Modo de emparelhamento",
    "Fixed PIN": "PIN fixo",
    "Server": "Servidor",
    "Username": "Utilizador",
    "Password": "Senha",
    "Encryption enabled": "Encriptação habilitada",
    "JSON enabled": "JSON habilitado",
    "TLS enabled": "TLS habilitado",
    "Root topic": "Root topic",
    "Proxy to client": "Proxy para cliente",
    "Map reporting": "Map reporting",
    "Map precision": "Precisão do mapa",
    "Map report interval (s)": "Intervalo map report (s)",
    "Ok to MQTT (channel)": "Ok para MQTT (canal)",
    "Echo": "Echo",
    "Baud rate": "Baud rate",
    "Timeout (ms)": "Timeout (ms)",
    "Mode": "Modo",
    "RX GPIO": "RX GPIO",
    "TX GPIO": "TX GPIO",
    "Serial only RX": "Somente RX",
    "Output active (ms)": "Saída activa (ms)",
    "Output GPIO": "Saída GPIO",
    "Vibra output GPIO": "Saída vibra GPIO",
    "Buzzer output GPIO": "Saída buzzer GPIO",
    "Alert for message": "Alerta para mensagem",
    "Alert msg buzzer": "Alerta msg pulso",
    "Alert msg vibra": "Alerta msg vibra",
    "Alert for bell": "Alerta para bell",
    "Alert bell buzzer": "Alerta bell buzzer",
    "Alert bell vibra": "Alerta bell vibra",
    "Use PWM buzzer": "Usar PWM buzzer",
    "Active GPIO level": "Nível activo GPIO",
    "Heartbeat": "Heartbeat",
    "Num records": "Num records",
    "History window (s)": "Histórico (s)",
    "Max history msgs": "Max msgs histórico",
    "Is S&F server": "É servidor S&F",
    "Sender interval (s)": "Intervalo sender (s)",
    "Save to CSV": "Guardar em CSV",
    "Device update interval (s)": "Intervalo dispositivo (s)",
    "Environment update interval (s)": "Intervalo ambiente (s)",
    "Environment measurement active": "Medição ambiente activa",
    "Environment on screen": "Ambiente no ecrã",
    "Temperature in Fahrenheit": "Temperatura em Fahrenheit",
    "Air quality interval (s)": "Intervalo air quality (s)",
    "Air quality active": "Air quality activo",
    "Power update interval (s)": "Intervalo potência (s)",
    "Power measurement active": "Medição potência activa",
    "Health update interval (s)": "Intervalo saúde (s)",
    "Health telemetry active": "Saúde activo",
    "Canned messages": "Mensagens pré-definidas",
    "Allow input source": "Fonte de entrada aceite",
    "Rotary encoder #1": "Rotary encoder #1",
    "Up/Down encoder": "Up/Down encoder",
    "Encoder GPIO A": "GPIO encoder A",
    "Encoder GPIO B": "GPIO encoder B",
    "Encoder press GPIO": "GPIO encoder Press",
    "CW event (up)": "Evento CW (cima)",
    "CCW event (down)": "Evento CCW (baixo)",
    "Press event": "Evento Press",
    "Send bell": "Enviar sinal Bell",
    "Codec2 enabled": "Codec2 habilitado",
    "PTT GPIO": "GPIO PTT",
    "Codec2 mode": "Modo codec2",
    "I2S WS GPIO": "I2S WS GPIO",
    "I2S SD GPIO": "I2S SD GPIO",
    "I2S DIN GPIO": "I2S DIN GPIO",
    "I2S SCK GPIO": "I2S SCK GPIO",
    "Allow unsafe input": "Permitir input não seg.",
    "Update interval (s)": "Intervalo update (s)",
    "Transmit over LoRa": "Transmitir sobre LoRa",
    "LED enabled": "Habilitado LED",
    "Current (mA)": "Corrente (mA)",
    "Red": "Red",
    "Green": "Green",
    "Blue": "Blue",
    "Min broadcast interval (s)": "Intervalo mínimo send (s)",
    "State broadcast interval (s)": "Intervalo estado (s)",
    "Use pull-up": "Usar pull-up",
    "Monitor GPIO": "Monitor GPIO",
    "Detection type high": "Tipo de detecção",
    "Paxcount update interval (s)": "Intervalo Paxcount (s)",
    "Public key (readonly)": "Chave pública (readonly)",
    "Admin via legacy channel": "Admin via canal legacy",
    "Managed mode": "Managed mode",
    "Serial debug mode": "Modo serial (debug)",
    "Debug log API enabled": "Log debug via serial",
    "Managed admin channel": "Admin channel enabled",
    "Bluetooth logging": "Bluetooth admin",

    # ── Metrics tab ───────────────────────────────────────────────
    "Metrics": "Métricas",
    "🗑  Clear data": "🗑  Limpar dados",
    "📊 Overview": "📊 Visão Geral",
    "📡 Channel & Airtime": "📡 Canal & Airtime",
    "📶 RF Quality": "📶 Qualidade RF",
    "📦 Traffic": "📦 Tráfego",
    "🔋 Nodes & Battery": "🔋 Nós & Bateria",
    "✅ Reliability": "✅ Fiabilidade",
    "⏱ Latency": "⏱ Latência",
    "🔗 Neighbourhood": "🔗 Vizinhança",
    "📏 Range & Links": "📏 Alcance & Links",
    "⏰ Intervals": "⏰ Intervalos",
    "Clear Metrics": "Limpar Métricas",
    "Clear all metrics data collected this session?":
        "Limpar todos os dados de métricas recolhidos nesta sessão?",

    # ── Dialogs ───────────────────────────────────────────────────
    "Error": "Erro",
    "Meshtastic Error": "Erro no Meshtastic",
    "No Connection": "Sem Conexão",
    "Connect first.": "Conecte-se primeiro.",
    "Not connected.": "Não está conectado.",
    "Yes": "Sim",
    "No": "Não",
    "Reset NodeDB": "Reset NodeDB",
    "Delete the local node NodeDB?\n\nAll known nodes will be removed from firmware.":
        "Apagar o NodeDB do nó local?\n\nTodos os nós conhecidos serão removidos do firmware.",
    "Disconnected": "Desconectado",
    "Connect first to send traceroute.": "Conecte-se primeiro para enviar traceroute.",
    "Traceroute in progress": "Traceroute em curso",
    "Wait {}s for the previous traceroute to finish.":
        "Aguarde {}s até o traceroute anterior terminar.",
    "Traceroute already exists": "Traceroute já existente",
    "Already have a traceroute for {}.\n\nSend a new traceroute anyway?":
        "Já existe um traceroute para {}.\n\nDeseja enviar um novo traceroute mesmo assim?",
    "📡 Traceroute sent to {} — waiting for response…":
        "📡 Traceroute enviado para {} — aguardando resposta…",
    "📡 Node Info sent to network.": "📡 Info do Nó enviada para a rede.",
    "Send Position": "Envio de Posição",

    # ── RebootWaitDialog ──────────────────────────────────────────
    "Rebooting node…": "A reiniciar o nó…",
    "The node is restarting to apply settings.": "O nó está a reiniciar para aplicar as configurações.",
    "Reconnecting automatically in {}s…": "A reconectar automaticamente em {}s…",
    "🔌  Reconnect now": "🔌  Reconectar agora",
    "⏳ Waiting for reboot…": "⏳ A aguardar reinício…",

    # ── ConsoleWindow ─────────────────────────────────────────────
    "Log Console": "Consola de Logs",
    "📋  Logs": "📋  Logs",
    "🗑  Clear": "🗑  Limpar",

    # ── Status bar messages ───────────────────────────────────────
    "Connecting to {}:{}…": "Conectando a {}:{}…",
    "✅ Connected — {} nodes": "✅ Ligado — {} nós",
    "❌ Disconnected": "❌ Desligado",
    "Reconnecting #{} in {}s…": "Reconexão #{} em {}s…",    # ── Additional keys ──────────────────────────────────────────────
    "Disconnect": "Desligar",
    "Log Console": "Consola de Logs",
    "Tools": "Ferramentas",
    "Favourite": "Favorito",
    "Not favourite": "Não favorito",
    "💡 ⭐=Fav · 📩/🔒=DM · 🗺=Map · 📡=TR · DblClick=Details":
        "💡 ⭐=Fav · 📩/🔒=DM · 🗺=Mapa · 📡=TR · DblClique=Detalhes",
    "Wait {}s for the previous traceroute to finish.":
        "Aguarde {}s para o traceroute anterior terminar.",
    "A traceroute to": "Já existe um traceroute para",
    "already exists.": "na lista.",
    "Traceroute sent to": "Traceroute enviado para",
    "waiting for response…": "aguardando resposta…",
    "Local node": "Nó local",
    "Nodes:": "Nós:",
    "characters": "caracteres",
    "Details of Last Packet": "Detalhes do Último Pacote",
    "📤 Sent": "📤 Enviado",
    "Sending…": "A enviar…",
    "🔑 Generate": "🔑 Gerar",
    "Mute": "Silenciar",
    "Mute notifications (is_muted)": "Silenciar notificações",
    "💡  One message per line · Separated by | in firmware · Max 200 chars total":
        "💡  Uma mensagem por linha · Separadas por | no firmware · Máx. 200 caracteres",
    "Channel": "Canal",
    "channel(s) loaded": "canal(ais) carregados",
    "channel(s) saved": "canal(ais) guardados",
    "channel(s) saved to node.": "canal(ais) guardados no nó.",
    "error(s)": "erro(s)",
    "added — edit and save": "adicionado — edite e guarde",
    "marked for removal — save to apply": "marcado para remoção — guarde para aplicar",
    "Save all channel changes to the node?\n\n⚠  The node will restart to apply changes.\n    The TCP connection will be temporarily lost.":
        "Guardar todas as alterações de canais no nó?\n\n⚠  O nó irá reiniciar para aplicar as alterações.\n    A ligação TCP será temporariamente perdida.",
    "Save all configuration changes to the node?\n\n⚠  The node will restart to apply the settings.\n    The TCP connection will be temporarily lost.":
        "Guardar todas as alterações de configuração no nó?\n\n⚠  O nó irá reiniciar para aplicar as configurações.\n    A ligação TCP será temporariamente perdida.",
    "Add Channel": "Adicionar Canal",
    "Save Channels": "Guardar Canais",
    "Remove Channel": "Remover Canal",
    "Configuration saved!": "Configuração guardada!",
    "section(s) sent to node.": "secção(ões) enviadas ao nó.",
    "Configuration Saved": "Configuração Guardada",
    "No Changes": "Sem Alterações",
    "Nothing saved": "Nada guardado",
    "No changes detected.": "Sem alterações detectadas.",
    "No connection": "Sem Conexão",
    "Max channels reached": "Limite de canais atingido",
    "Maximum of 8 channels (0-7) already reached.":
        "O máximo de 8 canais (0-7) já foi atingido.",
    "Remove channel with index": "Remover canal com índice",
    "Enabled": "Habilitado",
    "Dark": "Escuro",
    "Light": "Claro",
    "Satellite": "Satélite",
    "🌑 Dark": "🌑 Escuro",
    "☀ Light": "☀ Claro",
    "🛰 Satellite": "🛰 Satélite",
    "Show all": "Mostrar todas",
    "Clear list": "Limpar lista",
    "Theme:": "Tema:",
    "Traceroutes": "Traceroutes",
    "Clear traceroutes?": "Limpar traceroutes?",
    "traceroute(s)?\nThe route lines on the map will also be removed.":
        "traceroute(s)?\nAs linhas de rota no mapa também serão removidas.",
    "Are you sure you want to remove all": "Tem a certeza que deseja remover todos os",
    "SNR unknown": "SNR desconhecido",
    "Via (no GPS):": "Via (sem GPS):",
    "Forward": "Ida",
    "Return": "Volta",
    "Neighbourhood (NeighborInfo)": "Vizinhança (NeighborInfo)",
    "RF active": "RF activo",
    "Last packet": "Último pacote",
    "Inactive (>2h)": "Inactivo (>2h)",
    "Selected": "Seleccionado",
    "Traceroute forward": "Traceroute ida",
    "Traceroute return": "Traceroute volta",
    "No messages yet": "Sem mensagens ainda",
    "Select a channel or node to send a message…":
        "Seleccione um canal ou nó para enviar mensagem…",
    "Direct Messages": "Mensagens Directas",
    "Long Name": "Nome Longo",
    "Clear Metrics": "Limpar Métricas",
    "Clear all metrics data collected this session?":
        "Limpar todos os dados de métricas recolhidos nesta sessão?",
    "Clear data": "Limpar dados",
    "Overview": "Visão Geral",
    "Channel & Airtime": "Canal & Airtime",
    "RF Quality": "Qualidade RF",
    "Traffic": "Tráfego",
    "Nodes & Battery": "Nós & Bateria",
    "Reliability": "Fiabilidade",
    "Latency": "Latência",
    "Neighbourhood": "Vizinhança",
    "Range & Links": "Alcance & Links",
    "Intervals": "Intervalos",
    "Node ID": "ID do Nó",
    "Short Name": "Nome Curto",
    "Licensed (Ham)": "Licenciado (Ham)",
    "Last Contact": "Último Contacto",
    "Altitude (m)": "Altitude (m)",
    "Battery (%)": "Bateria (%)",
    "Model": "Modelo",
    "Last Type": "Último Tipo",
    "Search nodes...": "Pesquisar nós...",
    "Local node": "Nó local",
    "Nodes": "Nós",
    "Messages": "Mensagens",
    "Map": "Mapa",
    "Metrics": "Métricas",
    "Configuration": "Configuração",
    "Connect...": "Ligar...",
    "Send Node Info": "Enviar Info do Nó",
    "Send Position": "Enviar Posição",
    "About Meshtastic Monitor": "Sobre o Meshtastic Monitor",
    "About": "Sobre",
    "Language": "Língua",
    "Change Language": "Alterar Língua",
    "Node": "Nó",
    "Connection": "Ligação",
    "Reset NodeDB": "Reset NodeDB",
    "Disconnected": "Desligado",
    "Not connected.": "Não conectado.",
    "Close": "Fechar",
    "Cancel": "Cancelar",
    "Apply": "Aplicar",
    "Interface Language:": "Língua da Interface:",
    "Configure Connection": "Configurar Conexão",
    "Meshtastic Server Connection": "Ligação ao Servidor Meshtastic",
    "Address:": "Endereço:",
    "Port:": "Porta:",
    "🔌  Connect": "🔌  Ligar",
    "Rebooting node…": "A reiniciar o nó…",
    "The node is restarting to apply settings.":
        "O nó está a reiniciar para aplicar as configurações.",
    "🔌  Reconnect now": "🔌  Reconectar agora",
    "Log Console": "Consola de Logs",
    "📋  Logs": "📋  Registos",
    "🗑  Clear": "🗑  Limpar",
    "Select Language": "Seleccionar Língua",
    "Choose the interface language:": "Escolha a língua da interface:",
    "English": "Inglês",
    "Portuguese": "Português",
    "Meshtastic Error": "Erro Meshtastic",
    "Connect first to send traceroute.": "Conecte-se primeiro para enviar traceroute.",
    "Traceroute in progress": "Traceroute em curso",
    "Traceroute already exists": "Traceroute já existente",
    "📡 Node Info sent to network.": "📡 Info do Nó enviada para a rede.",
    "View on map": "Ver no mapa",
    "No position data": "Sem dados de posição",
    "Delete the local node NodeDB?\n\nAll known nodes will be removed from firmware.":
        "Apagar o NodeDB do nó local?\n\nTodos os nós conhecidos serão removidos do firmware.",
    "Details of Last Packet": "Detalhes do Último Pacote",
    "No packet stored": "Sem pacote armazenado",
    "No connection": "Sem Conexão",
    "Channels": "Canais",
    "User": "Utilizador",
    "Sections": "Secções",
    "Connect to a node to see settings.": "Conecte-se a um nó para ver as configurações.",
    "Loading configuration…": "A carregar configuração…",
    "✅ Configuration loaded": "✅ Configuração carregada",
    "❌ Error loading": "❌ Erro ao carregar",
    "Save Configuration": "Guardar Configuração",
    "Editable fields — save uses setOwner()": "Campos editáveis — guardar usa setOwner()",
    "No field available for this section.": "Nenhum campo disponível para esta secção.",
    "One message per line · Separated by | in firmware · Max 200 chars total":
        "Uma mensagem por linha · Separadas por | no firmware · Máx. 200 caracteres total",
    "📤 Send": "📤 Enviar",
    "📩  Send DM": "📩  Enviar DM",
    "Public key known — PKI DM available (E2E)":
        "Chave pública conhecida — DM PKI disponível (E2E)",
    "Unknown public key — DM via channel PSK":
        "Chave pública desconhecida — DM via PSK de canal",
    "Generates a random PSK key of the selected type":
        "Gera uma chave PSK aleatória do tipo seleccionado",
    "MQTT Uplink enabled": "Uplink MQTT habilitado",
    "MQTT Downlink enabled": "Downlink MQTT habilitado",
    "Mute notifications (is_muted)": "Silenciar notificações (is_muted)",
    "Position precision": "Precisão de posição",
    "Channel name": "Nome do canal",
    "Role": "Papel",
    "Name": "Nome",
    "🗑  Clear data": "🗑  Limpar dados",
    "Local Node Metric": "Métrica do Nó Local",
    "data below refers exclusively to the local node":
        "dados abaixo referem-se exclusivamente ao nó local",
    "Other network nodes do not contribute to these values":
        "Os outros nós da rede não contribuem para estes valores",
    "Network Metric": "Métrica da Rede",
    "data below is passively observed from all packets":
        "dados abaixo são observados passivamente a partir de todos os pacotes",
    "Reflects the state of the entire visible network, not just the local node.":
        "Reflecte o estado de toda a rede visível, não apenas o nó local.",

    # ── Traceroute dialog ─────────────────────────────────────────────
    "Third-party traceroute received": "Traceroute de terceiro recebido",
    "A traceroute was received between": "Foi recebido um traceroute entre",
    "Origin": "Origem",
    "Destination": "Destino",
    "Hops forward": "Hops ida",
    "Hops return": "Hops volta",
    "Traceroute Result": "Resultado do Traceroute",
    "View result on map?": "Visualizar resultado no mapa?",
    # ── New metrics keys ──────────────────────────────────────────────
    "Total Packets": "Total Pacotes",
    "Packets/min": "Pacotes/min",
    "Delivery rate": "Taxa Entrega",
    "Status": "Estado",
    "Topology": "Topologia",
    "excellent": "excelente",
    "good": "bom",
    "weak": "fraco",
    "Median SNR": "SNR Mediano",
    "Hardware by Model": "Hardware por Modelo",
    "Flood rate": "Taxa de flood",
    "Low risk": "Risco baixo",
    "Reduced flood": "Flood reduzido",
    "Congested": "Congestionado",
    "Poisson model": "Modelo Poisson",
    "LIMIT EXCEEDED": "LIMITE EXCEDIDO",
    "Waiting for telemetry data...": "Aguardando dados de telemetria...",
    "Waiting for RF packets...": "Aguardando pacotes RF...",
    "Waiting for packets...": "Aguardando pacotes...",
    "Healthy flood": "Flood saudável",
    "Possible congestion": "Possível congestionamento",
    "Routing pattern": "Padrão de roteamento",
    "Session summary": "Resumo da sessão",
    "Session started": "Sessão iniciada",
    "Includes NO_ROUTE and MAX_RETRANSMIT": "Inclui NO_ROUTE e MAX_RETRANSMIT",
    "Congested network or long route": "Rede congestionada ou rota longa",

    # ── Messages tab ─────────────────────────────────────────────────
    "Message to": "Mensagem para",
    "Send DM to": "Enviar DM para",
    "No messages in": "Nenhuma mensagem em",
    # ── Metrics reliability ───────────────────────────────────────────
    "Real ACK ✓": "ACK real ✓",
    "Real delivery rate": "Taxa de entrega real",
    "Real Delivery Rate": "Taxa de Entrega Real",
    "Local NAK Rate": "Taxa NAK Local",
    "Messages Sent": "Mensagens Enviadas",
    "Local relay": "Relay local",
    "Pending": "Pendente",
    "Local delivery": "Entrega local",
    "Network NAK": "NAK da rede",
    "sender nodes": "nodes emissores",
    "Direct": "Directo",
    "Unknown": "Desconhecido",
    "Hop Distribution": "Distribuição de Hops",
    "Battery Distribution": "Distribuição de Bateria",
    "Direct Neighbour Pairs": "Pares de Vizinhos Directos",
    "samples": "amostras",
    "Channel Utilization Over Time": "Utilização do Canal ao Longo do Tempo",

    "Wait": "Aguarde",

    "The settings have been sent to the node.": "As configurações foram enviadas ao nó.",

    "The node is restarting to apply them.": "O nó está a reiniciar para aplicar.",

    "Wait before reconnecting to ensure": "Aguarde antes de reconectar para garantir",

    "the TCP service will be available again.": "que o serviço TCP estará disponível novamente.",

    "Today": "Hoje",
    "Yesterday": "Ontem",
    "Normal for 1–2 hops in LoRa.": "Normal para 1–2 hops em LoRa.",
}

# ── Public API ──────────────────────────────────────────────────────

def get_language() -> str:
    """Returns the current language code: 'en' or 'pt'."""
    return _LANG


def set_language(lang: str):
    """Sets the active language and notifies all registered callbacks."""
    global _LANG
    if lang not in ("en", "pt"):
        return
    _LANG = lang
    for cb in list(_CALLBACKS):
        try:
            cb()
        except Exception:
            pass


def tr(text: str, *args) -> str:
    """
    Translates text to the active language.
    If active language is 'en', returns the text unchanged (English is the source).
    If active language is 'pt', looks up Portuguese translation.
    Supports positional formatting: tr("Hello {}", name)
    """
    if _LANG == "en":
        result = text
    else:
        result = _PT.get(text, text)

    if args:
        try:
            result = result.format(*args)
        except (IndexError, KeyError):
            pass
    return result


def register_retranslate(callback):
    """Register a function to be called when the language changes."""
    if callback not in _CALLBACKS:
        _CALLBACKS.append(callback)


def unregister_retranslate(callback):
    """Unregister a retranslate callback."""
    try:
        _CALLBACKS.remove(callback)
    except ValueError:
        pass
