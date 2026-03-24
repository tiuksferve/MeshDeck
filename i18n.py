"""
i18n.py — Internacionalização do Meshtastic Monitor.

Suporta Português (pt) e English (en).
O idioma activo é definido em set_language() e lido via tr().
"""

_LANG = "en"   # default: English

def set_language(lang: str):
    """Define o idioma activo. lang: 'en' ou 'pt'."""
    global _LANG
    _LANG = lang if lang in ("en", "pt") else "en"

def get_language() -> str:
    return _LANG

def tr(key: str, **kwargs) -> str:
    """Devolve o texto no idioma activo.
    Os kwargs são substituídos nas chaves {nome} do texto.
    """
    text = _STRINGS.get(key, {}).get(_LANG, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text


# ── Dicionário de traduções ──────────────────────────────────────────────────
# Formato: "chave": {"pt": "texto PT", "en": "texto EN"}
# A chave é o texto em PT (para facilitar o uso no código).
# Textos sem tradução necessária usam o mesmo valor em ambos os idiomas.

_STRINGS: dict = {

    # ── Janela principal ──────────────────────────────────────────────────────
    "app_title":                    {"pt": "Meshtastic Monitor {v}",          "en": "Meshtastic Monitor {v}"},
    "Nó local: —":                  {"pt": "Nó local: —",                     "en": "Local node: —"},
    "Nó local: {name} [{short}]":   {"pt": "Nó local: {name} [{short}]",      "en": "Local node: {name} [{short}]"},
    "Nós: {total}":                 {"pt": "Nós: {total}",                    "en": "Nodes: {total}"},
    "online":                       {"pt": "online",                          "en": "online"},
    "⚫  Desconectado":             {"pt": "⚫  Desconectado",                "en": "⚫  Disconnected"},
    "🟢  {host}":                   {"pt": "🟢  {host}",                     "en": "🟢  {host}"},
    "🔴  Desconectado":             {"pt": "🔴  Desconectado",               "en": "🔴  Disconnected"},
    "SNR tooltip":                  {"pt": "SNR do último pacote recebido · Pacotes/min da rede",
                                     "en": "Last received packet SNR · Network packets/min"},
    "Total de nós na rede (excluindo o nó local)":
                                    {"pt": "Total de nós na rede (excluindo o nó local)",
                                     "en": "Total nodes in network (excluding local node)"},
    "Pesquisar por ID, nome longo ou curto…":
                                    {"pt": "Pesquisar por ID, nome longo ou curto…",
                                     "en": "Search by ID, long name or short name…"},
    "hint_bar":                     {"pt": "💡 ⭐ → Favorito  ·  📩/🔒 → DM  ·  🗺 → Mapa  ·  📡 → Traceroute  ·  ",
                                     "en": "💡 ⭐ → Favourite  ·  📩/🔒 → DM  ·  🗺 → Map  ·  📡 → Traceroute  ·  "},
    "hint_fav":                     {"pt": "⭐ Favorito (fixo no topo)  &nbsp;",
                                     "en": "⭐ Favourite (pinned at top)  &nbsp;"},
    "hint_nofav":                   {"pt": "☆ Não favorito",                 "en": "☆ Not a favourite"},
    "Duplo clique → Detalhes":      {"pt": "Duplo clique → Detalhes",         "en": "Double-click → Details"},
    "GPS activo com posição conhecida":
                                    {"pt": "GPS activo com posição conhecida",
                                     "en": "GPS active with known position"},
    "GPS activo mas posição ainda não disponível":
                                    {"pt": "GPS activo mas posição ainda não disponível",
                                     "en": "GPS active but position not yet available"},
    "nó local tooltip":             {"pt": "Nó local  ·  {long_name} [{short_name}]  ·  {node_id}\nGPS: {gps_tip}",
                                     "en": "Local node  ·  {long_name} [{short_name}]  ·  {node_id}\nGPS: {gps_tip}"},

    # ── Abas ─────────────────────────────────────────────────────────────────
    "📋  Lista de Nós":             {"pt": "📋  Lista de Nós",                "en": "📋  Node List"},
    "💬  Mensagens":                {"pt": "💬  Mensagens",                   "en": "💬  Messages"},
    "💬  Mensagens  🔴":            {"pt": "💬  Mensagens  🔴",               "en": "💬  Messages  🔴"},
    "🗺  Mapa":                     {"pt": "🗺  Mapa",                        "en": "🗺  Map"},
    "📈 Métricas":                  {"pt": "📈 Métricas",                     "en": "📈 Metrics"},
    "⚙ Configurações":              {"pt": "⚙ Configurações",                 "en": "⚙ Settings"},

    # ── Menus ─────────────────────────────────────────────────────────────────
    "🔌  Conexão":                  {"pt": "🔌  Conexão",                     "en": "🔌  Connection"},
    "🔌  Conectar…":                {"pt": "🔌  Conectar…",                   "en": "🔌  Connect…"},
    "⏹  Desconectar":               {"pt": "⏹  Desconectar",                  "en": "⏹  Disconnect"},
    "📡  Nó":                       {"pt": "📡  Nó",                          "en": "📡  Node"},
    "📡  Enviar Info do Nó":        {"pt": "📡  Enviar Info do Nó",           "en": "📡  Send Node Info"},
    "📍  Enviar Posição Manual":    {"pt": "📍  Enviar Posição Manual",        "en": "📍  Send Manual Position"},
    "🔧  Ferramentas":              {"pt": "🔧  Ferramentas",                  "en": "🔧  Tools"},
    "🗑  Reset NodeDB":             {"pt": "🗑  Reset NodeDB",                 "en": "🗑  Reset NodeDB"},
    "🖥  Consola de logs…":         {"pt": "🖥  Consola de logs…",             "en": "🖥  Log Console…"},
    "🔔  Som em nova mensagem":     {"pt": "🔔  Som em nova mensagem",         "en": "🔔  Sound on new message"},
    "Activa beep do sistema ao receber mensagem não lida":
                                    {"pt": "Activa beep do sistema ao receber mensagem não lida",
                                     "en": "Activates system beep on unread message"},
    "ℹ️  Sobre":                    {"pt": "ℹ️  Sobre",                       "en": "ℹ️  About"},
    "📋  Sobre Meshtastic Monitor": {"pt": "📋  Sobre Meshtastic Monitor",    "en": "📋  About Meshtastic Monitor"},

    # ── Lista de Nós — cabeçalhos ─────────────────────────────────────────────
    "Nome Longo":                   {"pt": "Nome Longo",                       "en": "Long Name"},
    "Nome Curto":                   {"pt": "Nome Curto",                       "en": "Short Name"},
    "Último Contato":               {"pt": "Último Contato",                   "en": "Last Contact"},
    "Bateria (%)":                  {"pt": "Bateria (%)",                      "en": "Battery (%)"},
    "Modelo":                       {"pt": "Modelo",                           "en": "Model"},
    "Último Tipo":                  {"pt": "Último Tipo",                      "en": "Last Type"},

    # ── Lista de Nós — tooltips e células ─────────────────────────────────────
    "🏠 Este é o seu nó local · {id}":
                                    {"pt": "🏠 Este é o seu nó local · {id}",
                                     "en": "🏠 This is your local node · {id}"},
    "Clique para remover dos favoritos":
                                    {"pt": "Clique para remover dos favoritos",
                                     "en": "Click to remove from favourites"},
    "Clique para adicionar aos favoritos":
                                    {"pt": "Clique para adicionar aos favoritos",
                                     "en": "Click to add to favourites"},
    "Ver no mapa":                  {"pt": "Ver no mapa",                      "en": "View on map"},
    "Sem dados de posição":         {"pt": "Sem dados de posição",             "en": "No position data"},
    "DM indisponível — nó nunca contactado":
                                    {"pt": "DM indisponível — nó nunca contactado",
                                     "en": "DM unavailable — node never contacted"},
    "Enviar DM 🔒 PKI (chave pública conhecida)":
                                    {"pt": "Enviar DM 🔒 PKI (chave pública conhecida)",
                                     "en": "Send DM 🔒 PKI (public key known)"},
    "Enviar DM 🔓 PSK (chave de canal)":
                                    {"pt": "Enviar DM 🔓 PSK (chave de canal)",
                                     "en": "Send DM 🔓 PSK (channel key)"},
    "⏳ Aguardando Info":            {"pt": "⏳ Aguardando Info",               "en": "⏳ Awaiting Info"},
    "Nunca":                        {"pt": "Nunca",                            "en": "Never"},

    # ── Mapa ─────────────────────────────────────────────────────────────────
    "🎨  Tema:":                    {"pt": "🎨  Tema:",                        "en": "🎨  Theme:"},
    "🌑 Escuro":                    {"pt": "🌑 Escuro",                        "en": "🌑 Dark"},
    "☀ Claro":                     {"pt": "☀ Claro",                          "en": "☀ Light"},
    "🗺 OpenStreetMap":            {"pt": "🗺 OpenStreetMap",                  "en": "🗺 OpenStreetMap"},
    "🛰 Satélite":                 {"pt": "🛰 Satélite",                       "en": "🛰 Satellite"},
    "📡  Traceroutes":              {"pt": "📡  Traceroutes",                  "en": "📡  Traceroutes"},
    "◉  Mostrar todas":             {"pt": "◉  Mostrar todas",                 "en": "◉  Show all"},
    "○  Mostrar todas":             {"pt": "○  Mostrar todas",                 "en": "○  Show all"},
    "🗑  Limpar lista":             {"pt": "🗑  Limpar lista",                  "en": "🗑  Clear list"},
    "Limpar lista de traceroutes":  {"pt": "Limpar lista de traceroutes",       "en": "Clear traceroute list"},
    "confirm_clear_traceroute":     {"pt": "Tem a certeza que deseja remover todos os {n} traceroute(s) da lista?\n\nAs linhas de rota no mapa também serão removidas.",
                                     "en": "Are you sure you want to remove all {n} traceroute(s) from the list?\n\nRoute lines on the map will also be removed."},
    "📡 Aguardando dados de posição...":
                                    {"pt": "📡 Aguardando dados de posição...",
                                     "en": "📡 Awaiting position data..."},
    "Ida":                          {"pt": "Ida",                              "en": "Forward"},
    "Volta":                        {"pt": "Volta",                            "en": "Return"},
    "Via (sem GPS)":               {"pt": "Via (sem GPS)",                     "en": "Via (no GPS)"},
    "Hop":                          {"pt": "Hop",                            "en": "Hop"},
    "SNR desconhecido":             {"pt": "SNR desconhecido",                 "en": "Unknown SNR"},
    "RF activo":                    {"pt": "RF activo",                        "en": "RF active"},
    "Seleccionado":                 {"pt": "Seleccionado",                     "en": "Selected"},
    "Pacote recebido":              {"pt": "Pacote recebido",                  "en": "Packet received"},
    "Inactivo (>2h)":               {"pt": "Inactivo (>2h)",                   "en": "Inactive (>2h)"},
    "Traceroute ida":               {"pt": "Traceroute ida",                   "en": "Traceroute forward"},
    "Traceroute volta":             {"pt": "Traceroute volta",                  "en": "Traceroute return"},
    "Vizinhança (NeighborInfo)":    {"pt": "Vizinhança (NeighborInfo)",         "en": "Neighbourhood (NeighborInfo)"},
    "🔗 Vizinhos: {a}  ↔  {b}":    {"pt": "🔗 Vizinhos: {a}  ↔  {b}",        "en": "🔗 Neighbours: {a}  ↔  {b}"},

    # ── Diálogo Traceroute ────────────────────────────────────────────────────
    "Origem:":                      {"pt": "Origem:",                          "en": "Origin:"},
    "Destino:":                     {"pt": "Destino:",                         "en": "Destination:"},
    "origem":                       {"pt": "origem",                           "en": "origin"},
    "destino":                      {"pt": "destino",                          "en": "destination"},
    "Rota de ida":                  {"pt": "Rota de ida",                      "en": "Forward route"},
    "Rota de volta":                {"pt": "Rota de volta",                    "en": "Return route"},
    "Resultado do Traceroute":      {"pt": "Resultado do Traceroute",           "en": "Traceroute Result"},
    "📍 com localização  ❓ sem localização":
                                    {"pt": "📍 com localização  ❓ sem localização",
                                     "en": "📍 with location  ❓ without location"},
    "🗺  Mostrar no Mapa":          {"pt": "🗺  Mostrar no Mapa",               "en": "🗺  Show on Map"},
    "⚠ Nenhum nó da rota tem localização — mapa indisponível.":
                                    {"pt": "⚠ Nenhum nó da rota tem localização — mapa indisponível.",
                                     "en": "⚠ No node on the route has location — map unavailable."},
    "Fechar":                       {"pt": "Fechar",                            "en": "Close"},
    "Traceroute de terceiro recebido":
                                    {"pt": "Traceroute de terceiro recebido",   "en": "Third-party traceroute received"},
    "Foi recebido um traceroute entre:\n\n":
                                    {"pt": "Foi recebido um traceroute entre:\n\n",
                                     "en": "A traceroute was received between:\n\n"},
    "Deseja visualizar o resultado?":
                                    {"pt": "Deseja visualizar o resultado?",    "en": "Do you want to view the result?"},
    "Resposta recebida mas sem rota.":
                                    {"pt": "Resposta recebida mas sem rota.",   "en": "Response received but no route."},
    "Traceroute em curso":          {"pt": "Traceroute em curso",               "en": "Traceroute in progress"},
    "Aguarde {n}s até o traceroute anterior terminar.":
                                    {"pt": "Aguarde {n}s até o traceroute anterior terminar.",
                                     "en": "Wait {n}s for the previous traceroute to finish."},
    "Traceroute já existente":      {"pt": "Traceroute já existente",           "en": "Traceroute already exists"},
    "Já existe um traceroute para {name} na lista.\n\n":
                                    {"pt": "Já existe um traceroute para {name} na lista.\n\n",
                                     "en": "A traceroute for {name} already exists in the list.\n\n"},
    "Deseja enviar um novo traceroute mesmo assim?":
                                    {"pt": "Deseja enviar um novo traceroute mesmo assim?",
                                     "en": "Do you want to send a new traceroute anyway?"},
    "Desconectado":                 {"pt": "Desconectado",                      "en": "Disconnected"},
    "Conecte-se primeiro para enviar traceroute.":
                                    {"pt": "Conecte-se primeiro para enviar traceroute.",
                                     "en": "Connect first to send a traceroute."},
    "Sem Posição":                  {"pt": "Sem Posição",                       "en": "No Position"},
    "O nó {name} não tem dados de geolocalização.":
                                    {"pt": "O nó {name} não tem dados de geolocalização.",
                                     "en": "Node {name} has no geolocation data."},
    "Hops ida:   {n}":             {"pt": "Hops ida:   {n}",                 "en": "Forward hops:   {n}"},
    "Hops volta: {n}":             {"pt": "Hops volta: {n}",                 "en": "Return hops: {n}"},

    # ── Aba Mensagens ─────────────────────────────────────────────────────────
    "📻  Canais":                   {"pt": "📻  Canais",                        "en": "📻  Channels"},
    "📩  Mensagens Directas":       {"pt": "📩  Mensagens Directas",            "en": "📩  Direct Messages"},
    "Seleccione um canal ou nó":    {"pt": "Seleccione um canal ou nó",         "en": "Select a channel or node"},
    "Seleccione um canal ou nó para enviar mensagem…":
                                    {"pt": "Seleccione um canal ou nó para enviar mensagem…",
                                     "en": "Select a channel or node to send a message…"},
    "📤  Enviar":                   {"pt": "📤  Enviar",                        "en": "📤  Send"},
    "📩  Enviar DM":                {"pt": "📩  Enviar DM",                     "en": "📩  Send DM"},
    "Mensagem para #{n} · {name}…": {"pt": "Mensagem para #{n} · {name}…",     "en": "Message to #{n} · {name}…"},
    "Mensagem directa para {name}…":{"pt": "Mensagem directa para {name}…",    "en": "Direct message to {name}…"},
    "Canal {n}":                    {"pt": "Canal {n}",                         "en": "Channel {n}"},
    "Chave pública conhecida — DM PKI disponível (E2E)":
                                    {"pt": "Chave pública conhecida — DM PKI disponível (E2E)",
                                     "en": "Public key known — PKI DM available (E2E)"},
    "Chave pública desconhecida — DM via PSK de canal":
                                    {"pt": "Chave pública desconhecida — DM via PSK de canal",
                                     "en": "Public key unknown — DM via channel PSK"},
    "Nenhuma mensagem em":          {"pt": "Nenhuma mensagem em",           "en": "No messages in"},
    "ainda.":                       {"pt": "ainda.",                         "en": "yet."},
    "A enviar...":                  {"pt": "A enviar...",                       "en": "Sending..."},
    "Recebido por relay":           {"pt": "Recebido por relay",                "en": "Received via relay"},

    # ── Configurações — Canais ────────────────────────────────────────────────
    "⚠  Sem conexão":              {"pt": "⚠  Sem conexão",                    "en": "⚠  Not connected"},
    "🔄  Recarregar":              {"pt": "🔄  Recarregar",                     "en": "🔄  Reload"},
    "➕  Adicionar Canal":          {"pt": "➕  Adicionar Canal",                "en": "➕  Add Channel"},
    "💾  Guardar Alterações":       {"pt": "💾  Guardar Alterações",             "en": "💾  Save Changes"},
    "✅  {n} canal(ais) carregados":{"pt": "✅  {n} canal(ais) carregados",     "en": "✅  {n} channel(s) loaded"},
    "❌  Erro: {e}":               {"pt": "❌  Erro: {e}",                      "en": "❌  Error: {e}"},
    "Sem Conexão":                  {"pt": "Sem Conexão",                       "en": "Not Connected"},
    "Conecte-se primeiro.":         {"pt": "Conecte-se primeiro.",              "en": "Connect first."},
    "Limite atingido":              {"pt": "Limite atingido",                   "en": "Limit reached"},
    "O máximo de 8 canais (0-7) já foi atingido.":
                                    {"pt": "O máximo de 8 canais (0-7) já foi atingido.",
                                     "en": "The maximum of 8 channels (0-7) has been reached."},
    "➕  Canal {n} adicionado — edite e guarde":
                                    {"pt": "➕  Canal {n} adicionado — edite e guarde",
                                     "en": "➕  Channel {n} added — edit and save"},
    "Erro":                         {"pt": "Erro",                              "en": "Error"},
    "Não foi possível criar canal:\\n{e}":
                                    {"pt": "Não foi possível criar canal:\\n{e}",
                                     "en": "Could not create channel:\\n{e}"},
    "Remover Canal":                {"pt": "Remover Canal",                     "en": "Remove Channel"},
    "Remover o canal com índice {n}?":
                                    {"pt": "Remover o canal com índice {n}?",   "en": "Remove channel with index {n}?"},
    "🗑  Canal {n} marcado para remoção — guarde para aplicar":
                                    {"pt": "🗑  Canal {n} marcado para remoção — guarde para aplicar",
                                     "en": "🗑  Channel {n} marked for removal — save to apply"},
    "Não está conectado.":          {"pt": "Não está conectado.",               "en": "Not connected."},
    "Guardar Canais":               {"pt": "Guardar Canais",                    "en": "Save Channels"},
    "Guardar todas as alterações de canais no nó?\n\n":
                                    {"pt": "Guardar todas as alterações de canais no nó?\n\n",
                                     "en": "Save all channel changes to the node?\n\n"},
    "⚠  O nó irá reiniciar para aplicar as alterações.\n":
                                    {"pt": "⚠  O nó irá reiniciar para aplicar as alterações.\n",
                                     "en": "⚠  The node will restart to apply the changes.\n"},
    "A ligação TCP será temporariamente perdida e restabelecida.":
                                    {"pt": "A ligação TCP será temporariamente perdida e restabelecida.",
                                     "en": "The TCP connection will be temporarily lost and re-established."},
    "A guardar…":                   {"pt": "A guardar…",                        "en": "Saving…"},
    "✅  {n} canal(ais) guardados": {"pt": "✅  {n} canal(ais) guardados",      "en": "✅  {n} channel(s) saved"},
    "| ⚠ {n} erro(s)":             {"pt": "| ⚠ {n} erro(s)",                   "en": "| ⚠ {n} error(s)"},
    "Canais Guardados":             {"pt": "Canais Guardados",                   "en": "Channels Saved"},
    "{n} canal(ais) guardados no nó.":
                                    {"pt": "{n} canal(ais) guardados no nó.",   "en": "{n} channel(s) saved to the node."},
    "Erro ao guardar canais:\\n{e}":{"pt": "Erro ao guardar canais:\\n{e}",     "en": "Error saving channels:\\n{e}"},
    "Erro ao aplicar canal {n}: {e}":
                                    {"pt": "Erro ao aplicar canal {n}: {e}",    "en": "Error applying channel {n}: {e}"},
    "Nome do canal":                {"pt": "Nome do canal",                     "en": "Channel name"},
    "Base64 (ex: AQ==)  ou  default / none / random":
                                    {"pt": "Base64 (ex: AQ==)  ou  default / none / random",
                                     "en": "Base64 (e.g.: AQ==)  or  default / none / random"},
    "🔑 Gerar":                    {"pt": "🔑 Gerar",                          "en": "🔑 Generate"},
    "Gera uma chave PSK aleatória do tipo seleccionado":
                                    {"pt": "Gera uma chave PSK aleatória do tipo seleccionado",
                                     "en": "Generates a random PSK key of the selected type"},
    "Uplink MQTT habilitado":       {"pt": "Uplink MQTT habilitado",            "en": "MQTT Uplink enabled"},
    "Downlink MQTT habilitado":     {"pt": "Downlink MQTT habilitado",          "en": "MQTT Downlink enabled"},
    "Silenciar notificações (is_muted)":
                                    {"pt": "Silenciar notificações (is_muted)", "en": "Mute notifications (is_muted)"},
    "Precisão posição":             {"pt": "Precisão posição",                  "en": "Position precision"},
    "📻  Canal {n}":               {"pt": "📻  Canal {n}",                     "en": "📻  Channel {n}"},

    # ── Configurações — Nó Local ──────────────────────────────────────────────
    "⚙ Config. do No Local":       {"pt": "⚙ Config. do No Local",             "en": "⚙ Local Node Config"},
    "Secções":                      {"pt": "Secções",                           "en": "Sections"},
    "Não conectado":                {"pt": "Não conectado",                     "en": "Not connected"},
    "Conecte-se a um nó para ver as configurações.":
                                    {"pt": "Conecte-se a um nó para ver as configurações.",
                                     "en": "Connect to a node to view settings."},
    "A carregar configuração…":     {"pt": "A carregar configuração…",           "en": "Loading configuration…"},
    "Não foi possível obter o nó local.":
                                    {"pt": "Não foi possível obter o nó local.",
                                     "en": "Could not get local node."},
    "Erro: nó local indisponível":  {"pt": "Erro: nó local indisponível",       "en": "Error: local node unavailable"},
    "✅ Configuração carregada":    {"pt": "✅ Configuração carregada",          "en": "✅ Configuration loaded"},
    "❌ Erro ao carregar":          {"pt": "❌ Erro ao carregar",               "en": "❌ Error loading"},
    "📻 Canais":                   {"pt": "📻 Canais",                         "en": "📻 Channels"},
    "👤 Usuário":                  {"pt": "👤 Usuário",                        "en": "👤 User"},
    "ID do Nó":                    {"pt": "ID do Nó",                          "en": "Node ID"},
    "✏  Campos editáveis — guardar usa setOwner()":
                                    {"pt": "✏  Campos editáveis — guardar usa setOwner()",
                                     "en": "✏  Editable fields — saving uses setOwner()"},
    "Nenhum campo disponível para esta secção.":
                                    {"pt": "Nenhum campo disponível para esta secção.",
                                     "en": "No fields available for this section."},
    "📍 Posição / GPS":             {"pt": "📍 Posição / GPS",                  "en": "📍 Position / GPS"},
    "🌐 Rede / WiFi":               {"pt": "🌐 Rede / WiFi",                    "en": "🌐 Network / WiFi"},
    "🔧 Hardware Remoto":           {"pt": "🔧 Hardware Remoto",                "en": "🔧 Remote Hardware"},
    "Guardar Configuração":         {"pt": "Guardar Configuração",              "en": "Save Configuration"},
    "Deseja guardar todas as alterações de configuração no nó?\n\n":
                                    {"pt": "Deseja guardar todas as alterações de configuração no nó?\n\n",
                                     "en": "Do you want to save all configuration changes to the node?\n\n"},
    "⚠  O nó irá reiniciar após guardar para aplicar as configurações.\n":
                                    {"pt": "⚠  O nó irá reiniciar após guardar para aplicar as configurações.\n",
                                     "en": "⚠  The node will restart after saving to apply the settings.\n"},
    "⚠ Nada guardado":             {"pt": "⚠ Nada guardado",                   "en": "⚠ Nothing saved"},
    "Sem Alterações":               {"pt": "Sem Alterações",                    "en": "No Changes"},
    "Não foram detectadas alterações para guardar.":
                                    {"pt": "Não foram detectadas alterações para guardar.",
                                     "en": "No changes detected to save."},
    "Configuração Guardada":        {"pt": "Configuração Guardada",             "en": "Configuration Saved"},
    "✅ {n} secção(ões) guardadas": {"pt": "✅ {n} secção(ões) guardadas",     "en": "✅ {n} section(s) saved"},
    "Configuração guardada!\n{n} secção(ões) enviadas ao nó.":
                                    {"pt": "Configuração guardada!\n{n} secção(ões) enviadas ao nó.",
                                     "en": "Configuration saved!\n{n} section(s) sent to the node."},
    "❌ Erro ao guardar":           {"pt": "❌ Erro ao guardar",               "en": "❌ Error saving"},
    "Erro ao guardar configuração:\\n{e}":
                                    {"pt": "Erro ao guardar configuração:\\n{e}",
                                     "en": "Error saving configuration:\\n{e}"},
    "Não está conectado a nenhum nó.":
                                    {"pt": "Não está conectado a nenhum nó.",   "en": "Not connected to any node."},

    # ── Configurações — campos ────────────────────────────────────────────────
    "Papel do nó":                  {"pt": "Papel do nó",                       "en": "Node role"},
    "Retransmitir mensagens":       {"pt": "Retransmitir mensagens",            "en": "Retransmit messages"},
    "Botão GPIO":                   {"pt": "Botão GPIO",                        "en": "GPIO button"},
    "Duplo clique alimentação":     {"pt": "Duplo clique alimentação",          "en": "Power double-click"},
    "Intervalo broadcast NodeInfo (s)":
                                    {"pt": "Intervalo broadcast NodeInfo (s)",  "en": "NodeInfo broadcast interval (s)"},
    "Fuso horário (TZ string)":     {"pt": "Fuso horário (TZ string)",          "en": "Timezone (TZ string)"},
    "Intervalo update GPS (s)":     {"pt": "Intervalo update GPS (s)",          "en": "GPS update interval (s)"},
    "Intervalo broadcast pos (s)":  {"pt": "Intervalo broadcast pos (s)",       "en": "Position broadcast interval (s)"},
    "Distância mínima smart (m)":   {"pt": "Distância mínima smart (m)",        "en": "Smart min. distance (m)"},
    "Intervalo mínimo smart (s)":   {"pt": "Intervalo mínimo smart (s)",        "en": "Smart min. interval (s)"},
    "Latitude fixa (graus)":        {"pt": "Latitude fixa (graus)",             "en": "Fixed latitude (degrees)"},
    "Longitude fixa (graus)":       {"pt": "Longitude fixa (graus)",            "en": "Fixed longitude (degrees)"},
    "Altitude fixa (m)":            {"pt": "Altitude fixa (m)",                 "en": "Fixed altitude (m)"},
    "Precision de posição":         {"pt": "Precision de posição",              "en": "Position precision"},
    "Desligar na bateria (s)":      {"pt": "Desligar na bateria (s)",           "en": "Shutdown on battery (s)"},
    "Tempo mínimo acordado (s)":    {"pt": "Tempo mínimo acordado (s)",         "en": "Min. awake time (s)"},
    "INA endereço I2C bateria":     {"pt": "INA endereço I2C bateria",          "en": "Battery INA I2C address"},
    "IP estático":                  {"pt": "IP estático",                       "en": "Static IP"},
    "Ecrã ligado (s)":              {"pt": "Ecrã ligado (s)",                   "en": "Screen on (s)"},
    "Região":                       {"pt": "Região",                            "en": "Region"},
    "Offset frequência (MHz)":      {"pt": "Offset frequência (MHz)",           "en": "Frequency offset (MHz)"},
    "Número do canal (0-7)":        {"pt": "Número do canal (0-7)",             "en": "Channel number (0-7)"},
    "Encriptação habilitada":       {"pt": "Encriptação habilitada",            "en": "Encryption enabled"},
    "Precisão do mapa":             {"pt": "Precisão do mapa",                  "en": "Map precision"},
    "Intervalo map report (s)":     {"pt": "Intervalo map report (s)",          "en": "Map report interval (s)"},
    "Ok para MQTT (canal)":         {"pt": "Ok para MQTT (canal)",              "en": "OK for MQTT (channel)"},
    "Alerta para mensagem":         {"pt": "Alerta para mensagem",              "en": "Alert for message"},
    "Nível activo GPIO":            {"pt": "Nível activo GPIO",                 "en": "GPIO active level"},
    "Histórico (s)":                {"pt": "Histórico (s)",                     "en": "History (s)"},
    "Max msgs histórico":           {"pt": "Max msgs histórico",                "en": "Max history msgs"},
    "Intervalo sender (s)":         {"pt": "Intervalo sender (s)",              "en": "Sender interval (s)"},
    "Guardar em CSV":               {"pt": "Guardar em CSV",                    "en": "Save to CSV"},
    "Intervalo dispositivo (s)":    {"pt": "Intervalo dispositivo (s)",         "en": "Device interval (s)"},
    "Intervalo ambiente (s)":       {"pt": "Intervalo ambiente (s)",            "en": "Environment interval (s)"},
    "Medição ambiente activa":      {"pt": "Medição ambiente activa",           "en": "Env. measurement active"},
    "Intervalo air quality (s)":    {"pt": "Intervalo air quality (s)",         "en": "Air quality interval (s)"},
    "Air quality activo":           {"pt": "Air quality activo",                "en": "Air quality active"},
    "Intervalo potência (s)":       {"pt": "Intervalo potência (s)",            "en": "Power interval (s)"},
    "Medição potência activa":      {"pt": "Medição potência activa",           "en": "Power measurement active"},
    "Intervalo saúde (s)":          {"pt": "Intervalo saúde (s)",               "en": "Health interval (s)"},
    "Saúde activo":                 {"pt": "Saúde activo",                      "en": "Health active"},
    "Mensagens pré-definidas":      {"pt": "Mensagens pré-definidas",           "en": "Canned messages"},
    "Enviar sinal Bell":            {"pt": "Enviar sinal Bell",                 "en": "Send Bell signal"},
    "Permitir input não seg.":      {"pt": "Permitir input não seg.",            "en": "Allow unsafe input"},
    "Transmitir sobre LoRa":        {"pt": "Transmitir sobre LoRa",             "en": "Transmit over LoRa"},
    "Intervalo update (s)":         {"pt": "Intervalo update (s)",              "en": "Update interval (s)"},
    "Intervalo mínimo send (s)":    {"pt": "Intervalo mínimo send (s)",         "en": "Min. send interval (s)"},
    "Intervalo estado (s)":         {"pt": "Intervalo estado (s)",              "en": "Status interval (s)"},
    "Tipo de detecção":             {"pt": "Tipo de detecção",                  "en": "Detection type"},
    "Intervalo Paxcount (s)":       {"pt": "Intervalo Paxcount (s)",            "en": "Paxcount interval (s)"},
    "Admin via canal legacy":       {"pt": "Admin via canal legacy",            "en": "Admin via legacy channel"},
    "canned_hint":                  {"pt": "💡  Uma mensagem por linha · Separadas por | no firmware · Máx. 200 chars total",
                                     "en": "💡  One message per line · Separated by | in firmware · Max. 200 chars total"},
    "canned_placeholder":           {"pt": "Escreva uma mensagem por linha.\nExemplo:\nOlá!\nA caminho\nChegarei em 10 min\nSEM SINAL",
                                     "en": "Write one message per line.\nExample:\nHello!\nOn my way\nArriving in 10 min\nNO SIGNAL"},
    "0 / 200 caracteres":           {"pt": "0 / 200 caracteres",               "en": "0 / 200 characters"},
    "{n} / 200 caracteres":         {"pt": "{n} / 200 caracteres",             "en": "{n} / 200 characters"},

    # ── Diálogos ─────────────────────────────────────────────────────────────
    "Configurar Conexão":           {"pt": "Configurar Conexão",                "en": "Connection Settings"},
    "📡  Conexão ao Servidor Meshtastic":
                                    {"pt": "📡  Conexão ao Servidor Meshtastic",
                                     "en": "📡  Connect to Meshtastic Server"},
    "ex: localhost  ou  192.168.1.1":
                                    {"pt": "ex: localhost  ou  192.168.1.1",   "en": "e.g.: localhost  or  192.168.1.1"},
    "Endereço:":                    {"pt": "Endereço:",                         "en": "Address:"},
    "Porta:":                       {"pt": "Porta:",                            "en": "Port:"},
    "💡 Endereço padrão: localhost · porta 4403":
                                    {"pt": "💡 Endereço padrão: localhost · porta 4403",
                                     "en": "💡 Default address: localhost · port 4403"},
    "Idioma:":                      {"pt": "Idioma:",                           "en": "Language:"},
    "Cancelar":                     {"pt": "Cancelar",                          "en": "Cancel"},
    "🔌  Conectar":                 {"pt": "🔌  Conectar",                      "en": "🔌  Connect"},
    "Pacote":                        {"pt": "Pacote",                             "en": "Packet"},
    "Detalhes do Último Pacote":    {"pt": "Detalhes do Último Pacote",         "en": "Last Packet Details"},
    "Nenhum pacote armazenado":     {"pt": "Nenhum pacote armazenado",          "en": "No packet stored"},
    "🖥  Consola de Logs":          {"pt": "🖥  Consola de Logs",               "en": "🖥  Log Console"},
    "0 linhas":                     {"pt": "0 linhas",                          "en": "0 lines"},
    "{n} linhas":                   {"pt": "{n} linhas",                        "en": "{n} lines"},
    "Filtro:":                      {"pt": "Filtro:",                           "en": "Filter:"},
    "palavra-chave…":               {"pt": "palavra-chave…",                    "en": "keyword…"},
    "🗑 Limpar":                    {"pt": "🗑 Limpar",                         "en": "🗑 Clear"},
    "A reiniciar nó…":              {"pt": "A reiniciar nó…",                   "en": "Restarting node…"},
    "🔄  Nó a reiniciar":           {"pt": "🔄  Nó a reiniciar",               "en": "🔄  Node restarting"},
    "reboot_msg":                   {"pt": "As configurações foram enviadas ao nó.\nO nó está a reiniciar para as aplicar.\n\nAguarde antes de reconectar para garantir\nque o serviço TCP está novamente disponível.",
                                     "en": "Settings have been sent to the node.\nThe node is restarting to apply them.\n\nWait before reconnecting to ensure\nthe TCP service is available again."},
    "🔌  Aguarde {n}s…":           {"pt": "🔌  Aguarde {n}s…",                "en": "🔌  Please wait {n}s…"},
    "🔌  Reconectar agora":        {"pt": "🔌  Reconectar agora",              "en": "🔌  Reconnect now"},
    "Sobre o Meshtastic Monitor":   {"pt": "Sobre o Meshtastic Monitor",        "en": "About Meshtastic Monitor"},
    "Versão {v}  ·  2025":         {"pt": "Versão {v}  ·  2025",              "en": "Version {v}  ·  2025"},
    "uconsole_line":                 {"pt": "Desenvolvido e optimizado para o ClockworkPi uConsole CM4.",
                                     "en": "Developed and optimised for the ClockworkPi uConsole CM4."},
    "about_desc":                   {"pt": "Interface gráfica avançada para monitorização e comunicação\nem redes mesh Meshtastic via TCP ao daemon meshtasticd.\n\n",
                                     "en": "Advanced graphical interface for monitoring and communication\nover Meshtastic mesh networks via TCP to the meshtasticd daemon.\n\n"},
    "about_feat1":                  {"pt": "✅  Lista de nós em tempo real com pesquisa e favoritos\n",
                                     "en": "✅  Real-time node list with search and favourites\n"},
    "about_feat2":                  {"pt": "🗺  Mapa Leaflet com traceroutes e métricas de rede\n",
                                     "en": "🗺  Leaflet map with traceroutes and network metrics\n"},
    "about_feat3":                  {"pt": "💬  Mensagens por canal e DM com suporte PKI/PSK\n",
                                     "en": "💬  Channel and DM messages with PKI/PSK support\n"},
    "about_feat4":                  {"pt": "⚙  Configuração completa do nó com transacção atómica\n",
                                     "en": "⚙  Full node configuration with atomic transaction\n"},
    "about_feat5":                  {"pt": "📈  Métricas: Canal, RF, Tráfego, Duty Cycle, Fiabilidade",
                                     "en": "📈  Metrics: Channel, RF, Traffic, Duty Cycle, Reliability"},
    "Criado por":                   {"pt": "Criado por",                        "en": "Developed by"},

    # ── Status bar ────────────────────────────────────────────────────────────
    "📡 Info do Nó enviada para a rede.":
                                    {"pt": "📡 Info do Nó enviada para a rede.",
                                     "en": "📡 Node Info sent to the network."},
    "📡 Traceroute enviado para {name} — aguardando resposta…":
                                    {"pt": "📡 Traceroute enviado para {name} — aguardando resposta…",
                                     "en": "📡 Traceroute sent to {name} — awaiting response…"},
    "📡 Traceroute: {origin} → {dest}  ({n} links)":
                                    {"pt": "📡 Traceroute: {origin} → {dest}  ({n} links)",
                                     "en": "📡 Traceroute: {origin} → {dest}  ({n} links)"},
    "🔌 Ligação perdida — a reconectar em {n}s (tentativa {k})…":
                                    {"pt": "🔌 Ligação perdida — a reconectar em {n}s (tentativa {k})…",
                                     "en": "🔌 Connection lost — reconnecting in {n}s (attempt {k})…"},
    "🔄 A tentar reconectar… (tentativa {n})":
                                    {"pt": "🔄 A tentar reconectar… (tentativa {n})",
                                     "en": "🔄 Attempting reconnect… (attempt {n})"},
    "🔔 Som de notificação activado":
                                    {"pt": "🔔 Som de notificação activado",    "en": "🔔 Notification sound enabled"},
    "🔔 Som de notificação silenciado":
                                    {"pt": "🔔 Som de notificação silenciado",  "en": "🔔 Notification sound muted"},
    "Reset NodeDB":                 {"pt": "Reset NodeDB",                      "en": "Reset NodeDB"},
    "Apagar o NodeDB do nó local?\n\nTodos os nós conhecidos serão removidos do firmware.":
                                    {"pt": "Apagar o NodeDB do nó local?\n\nTodos os nós conhecidos serão removidos do firmware.",
                                     "en": "Clear the local node's NodeDB?\n\nAll known nodes will be removed from the firmware."},
    "Envio de Posição":             {"pt": "Envio de Posição",                  "en": "Position Send"},
    "Erro no Meshtastic":           {"pt": "Erro no Meshtastic",               "en": "Meshtastic Error"},

    # ── Métricas — geral ─────────────────────────────────────────────────────
    "Métricas":                     {"pt": "Métricas",                          "en": "Metrics"},
    "🔄  Actualizar":               {"pt": "🔄  Actualizar",                    "en": "🔄  Refresh"},
    "🗑  Limpar dados":             {"pt": "🗑  Limpar dados",                  "en": "🗑  Clear data"},
    "Limpar Métricas":              {"pt": "Limpar Métricas",                   "en": "Clear Metrics"},
    "Limpar todos os dados de métricas recolhidos nesta sessão?":
                                    {"pt": "Limpar todos os dados de métricas recolhidos nesta sessão?",
                                     "en": "Clear all metrics data collected in this session?"},
    "📊 Visão Geral":               {"pt": "📊 Visão Geral",                    "en": "📊 Overview"},
    "📡 Canal & Airtime":           {"pt": "📡 Canal & Airtime",                "en": "📡 Channel & Airtime"},
    "📶 Qualidade RF":              {"pt": "📶 Qualidade RF",                   "en": "📶 RF Quality"},
    "📦 Tráfego":                   {"pt": "📦 Tráfego",                        "en": "📦 Traffic"},
    "🔋 Nós & Bateria":             {"pt": "🔋 Nós & Bateria",                  "en": "🔋 Nodes & Battery"},
    "✅ Fiabilidade":               {"pt": "✅ Fiabilidade",                    "en": "✅ Reliability"},
    "⏱ Latência":                  {"pt": "⏱ Latência",                       "en": "⏱ Latency"},
    "🔗 Vizinhança":                {"pt": "🔗 Vizinhança",                     "en": "🔗 Neighbourhood"},
    "📏 Alcance & Links":           {"pt": "📏 Alcance & Links",                "en": "📏 Range & Links"},
    "⏰ Intervalos":                {"pt": "⏰ Intervalos",                     "en": "⏰ Intervals"},
    "🌐 Métrica da Rede":           {"pt": "🌐 Métrica da Rede",               "en": "🌐 Network Metric"},
    "network_metric_desc":          {"pt": "— os dados abaixo são observados passivamente a partir de todos os pacotes recebidos pelo nó local. Refletem o estado de toda a rede visível, não apenas o nó local.",
                                     "en": "— the data below is passively observed from all packets received by the local node. Reflects the state of the entire visible network, not just the local node."},
    "🏠 Métrica do Nó Local":       {"pt": "🏠 Métrica do Nó Local",           "en": "🏠 Local Node Metric"},
    "local_metric_desc":            {"pt": "— os dados abaixo referem-se exclusivamente ao nó local (mensagens enviadas e respectivos ACK/NAK). Os outros nós da rede não contribuem para estes valores.",
                                     "en": "— the data below refers exclusively to the local node (sent messages and their ACK/NAK). Other network nodes do not contribute to these values."},

    # ── Métricas — KPIs e textos HTML ────────────────────────────────────────
    "Resumo da sessão · Actualizado: {hora}":
                                    {"pt": "Resumo da sessão · Actualizado: {hora}",
                                     "en": "Session summary · Updated: {hora}"},
    "Total Pacotes":                {"pt": "Total Pacotes",                     "en": "Total Packets"},
    "Nós Activos (2h)":             {"pt": "Nós Activos (2h)",                  "en": "Active Nodes (2h)"},
    "Pacotes/min":                  {"pt": "Pacotes/min",                       "en": "Packets/min"},
    "SNR Médio":                    {"pt": "SNR Médio",                         "en": "Avg SNR"},
    "Hops Médio":                   {"pt": "Hops Médio",                        "en": "Avg Hops"},
    "Taxa Entrega":                 {"pt": "Taxa Entrega",                      "en": "Delivery Rate"},
    "Só mensagens enviadas pelo nó local":
                                    {"pt": "Só mensagens enviadas pelo nó local",
                                     "en": "Local node sent messages only"},
    "Airtime TX (avg)":             {"pt": "Airtime TX (avg)",                  "en": "TX Airtime (avg)"},
    "Utiliz. Canal (avg)":          {"pt": "Utiliz. Canal (avg)",               "en": "Channel Util. (avg)"},
    "<25% óptimo · <50% aceitável · >50% crítico":
                                    {"pt": "&lt;25% óptimo · &lt;50% aceitável · &gt;50% crítico",
                                     "en": "&lt;25% optimal · &lt;50% acceptable · &gt;50% critical"},
    "Top Nós por Pacotes":          {"pt": "Top Nós por Pacotes",               "en": "Top Nodes by Packets"},
    "Sem dados ainda":              {"pt": "Sem dados ainda",                   "en": "No data yet"},
    "Actualizado:":                 {"pt": "Actualizado:",                      "en": "Updated:"},
    "Nome":                         {"pt": "Nome",                              "en": "Name"},
    "Pacotes":                      {"pt": "Pacotes",                           "en": "Packets"},
    "Bateria":                      {"pt": "Bateria",                           "en": "Battery"},
    "Canal LoRa · Airtime TX · Hourly Duty Cycle · {hora}":
                                    {"pt": "Canal LoRa · Airtime TX · Hourly Duty Cycle · {hora}",
                                     "en": "LoRa Channel · TX Airtime · Hourly Duty Cycle · {hora}"},
    "Channel Utilization da Rede":  {"pt": "Channel Utilization da Rede",       "en": "Network Channel Utilization"},
    "Duty Cycle/h — Pior Nó ({nome})":
                                    {"pt": "Duty Cycle/h — Pior Nó ({nome})",  "en": "Duty Cycle/h — Worst Node ({nome})"},
    "Duty Cycle/h por Nó":         {"pt": "Duty Cycle/h por Nó",               "en": "Duty Cycle/h per Node"},
    "Airtime TX (10 min, avg)":     {"pt": "Airtime TX (10 min, avg)",          "en": "TX Airtime (10 min, avg)"},
    "Métrica da rede — airtime observado por cada nó (RX+TX de todos) · {ch_label}":
                                    {"pt": "Métrica da rede — airtime observado por cada nó (RX+TX de todos) · {ch_label}",
                                     "en": "Network metric — airtime observed by each node (RX+TX from all) · {ch_label}"},
    "Firmware atrasa envios acima de 25% · Para GPS: limite 40%":
                                    {"pt": "Firmware atrasa envios acima de 25% · Para GPS: limite 40%",
                                     "en": "Firmware delays sends above 25% · For GPS: limit 40%"},
    "Aguardando dados de telemetria...":
                                    {"pt": "Aguardando dados de telemetria...", "en": "Awaiting telemetry data..."},
    "Métrica por nó (TX daquele nó) · airUtilTx×6 · Limite EU: 10%/hora · {dc_label_w}":
                                    {"pt": "Métrica por nó (TX daquele nó) · airUtilTx×6 · Limite EU: 10%/hora · {dc_label_w}",
                                     "en": "Per-node metric (that node's TX) · airUtilTx×6 · EU limit: 10%/hour · {dc_label_w}"},
    "Aguardando dados de airUtilTx...":
                                    {"pt": "Aguardando dados de airUtilTx...", "en": "Awaiting airUtilTx data..."},
    "Média de TX de todos os nós nos últimos 10 min":
                                    {"pt": "Média de TX de todos os nós nos últimos 10 min",
                                     "en": "Average TX from all nodes in the last 10 min"},
    "Channel Utilization ao Longo do Tempo":
                                    {"pt": "Channel Utilization ao Longo do Tempo",
                                     "en": "Channel Utilization Over Time"},
    "Limite óptimo (25%)":          {"pt": "Limite óptimo (25%)",               "en": "Optimal limit (25%)"},
    "Limite crítico (50%)":         {"pt": "Limite crítico (50%)",              "en": "Critical limit (50%)"},
    "Por Nó — Ch. Util · Airtime TX · Duty Cycle/h":
                                    {"pt": "Por Nó — Ch. Util · Airtime TX · Duty Cycle/h",
                                     "en": "Per Node — Ch. Util · TX Airtime · Duty Cycle/h"},
    "Estado":                       {"pt": "Estado",                            "en": "Status"},
    "✅ Óptimo (<25%)":             {"pt": "✅ Óptimo (<25%)",                  "en": "✅ Optimal (<25%)"},
    "⚠ Próximo do limite":         {"pt": "⚠ Próximo do limite",               "en": "⚠ Near limit"},
    "🚨 LIMITE EXCEDIDO":           {"pt": "🚨 LIMITE EXCEDIDO",               "en": "🚨 LIMIT EXCEEDED"},
    "⚠ Atenção":                   {"pt": "⚠ Atenção",                        "en": "⚠ Warning"},
    "🚨 Excede limite":             {"pt": "🚨 Excede limite",                  "en": "🚨 Exceeds limit"},
    "Sem dados":                    {"pt": "Sem dados",                         "en": "No data"},
    "⏳ Aguardando dados de telemetria (TELEMETRY_APP)...":
                                    {"pt": "⏳ Aguardando dados de telemetria (TELEMETRY_APP)...",
                                     "en": "⏳ Awaiting telemetry data (TELEMETRY_APP)..."},
    "Os nós devem ter o módulo de telemetria activado.":
                                    {"pt": "Os nós devem ter o módulo de telemetria activado.",
                                     "en": "Nodes must have the telemetry module active."},
    "Distribuição de SNR e hops · {n} amostras":
                                    {"pt": "Distribuição de SNR e hops · {n} amostras",
                                     "en": "SNR and hops distribution · {n} samples"},
    "SNR Mediano":                  {"pt": "SNR Mediano",                       "en": "Median SNR"},
    "SNR P10 (pior 10%)":           {"pt": "SNR P10 (pior 10%)",               "en": "SNR P10 (worst 10%)"},
    "Distribuição SNR (dB)":        {"pt": "Distribuição SNR (dB)",             "en": "SNR Distribution (dB)"},
    "Distribuição de Hops":         {"pt": "Distribuição de Hops",              "en": "Hop Distribution"},
    "Avaliação da Qualidade RF":    {"pt": "Avaliação da Qualidade RF",         "en": "RF Quality Assessment"},
    "⏳ Aguardando dados suficientes para avaliação...":
                                    {"pt": "⏳ Aguardando dados suficientes para avaliação...",
                                     "en": "⏳ Awaiting sufficient data for assessment..."},
    "Distribuição de qualidade em {n} pacotes:":
                                    {"pt": "Distribuição de qualidade em {n} pacotes:",
                                     "en": "Quality distribution over {n} pacotes:"},
    "✅ Rede em excelentes condições RF. A grande maioria dos pacotes chega com sinal forte.":
                                    {"pt": "✅ <b>Rede em excelentes condições RF.</b> A grande maioria dos pacotes chega com sinal forte.",
                                     "en": "✅ <b>Network in excellent RF conditions.</b> The vast majority of packets arrive with strong signal."},
    "✅ Qualidade RF boa. A maioria das ligações é estável, com algumas margens.":
                                    {"pt": "✅ <b>Qualidade RF boa.</b> A maioria das ligações é estável, com algumas margens.",
                                     "en": "✅ <b>Good RF quality.</b> Most links are stable, with some margin."},
    "⚠️ Qualidade RF moderada.":    {"pt": "⚠️ <b>Qualidade RF moderada.</b> Uma parte significativa dos pacotes está em zona marginal — risco de perda em condições adversas.",
                                     "en": "⚠️ <b>Moderate RF quality.</b> A significant portion of packets are in the marginal zone — risk of loss in adverse conditions."},
    "🚨 Qualidade RF fraca.":       {"pt": "🚨 <b>Qualidade RF fraca.</b> Mais de 60% dos pacotes chegam com sinal deficiente. Reveja antenas e posicionamento.",
                                     "en": "🚨 <b>Poor RF quality.</b> Over 60% of packets arrive with poor signal. Review antennas and placement."},
    "⚠️ Pior decil SNR fraco":      {"pt": "⚠️ <b>Pior decil:</b> SNR ≤ {snr_p10} dB — algumas ligações estão severamente degradadas, possivelmente com perda de pacotes frequente.",
                                     "en": "⚠️ <b>Worst decile:</b> SNR ≤ {snr_p10} dB — some links are severely degraded, possibly with frequent packet loss."},
    "ℹ️ Pior decil SNR marginal":   {"pt": "ℹ️ <b>Pior decil:</b> SNR ≤ {snr_p10} dB — ligações marginais no extremo da cobertura.",
                                     "en": "ℹ️ <b>Worst decile:</b> SNR ≤ {snr_p10} dB — marginal links at the edge of coverage."},
    "✅ Pior decil SNR ok":          {"pt": "✅ <b>Pior decil:</b> SNR ≥ {snr_p10} dB — mesmo os piores percursos têm sinal razoável.",
                                     "en": "✅ <b>Worst decile:</b> SNR ≥ {snr_p10} dB — even the worst paths have reasonable signal."},
    "topologia":                    {"pt": "<b>Topologia:</b> {pct_direct}% directos · {pct_1hop}% a 1 hop · média {avg_hops:.1f} hops · máximo {max_hops} hops.",
                                     "en": "<b>Topology:</b> {pct_direct}% direct · {pct_1hop}% at 1 hop · avg {avg_hops:.1f} hops · max {max_hops} hops."},
    "⚠️ Média de hops elevada":     {"pt": "⚠️ Média de hops elevada — a rede depende muito de repetidores. Pode aumentar latência e congestionamento.",
                                     "en": "⚠️ High average hop count — the network relies heavily on repeaters. May increase latency and congestion."},
    "⚠️ Máximo de hops":            {"pt": "⚠️ Máximo de {max_hops} hops detectado — próximo do limite do firmware (7). Considere rever o hop limit configurado.",
                                     "en": "⚠️ Maximum of {max_hops} hops detected — close to firmware limit (7). Consider reviewing the configured hop limit."},
    "conclusao_verde":              {"pt": "<br><b>Conclusão:</b> Rede RF saudável e bem dimensionada. 🟢",
                                     "en": "<br><b>Summary:</b> Healthy and well-dimensioned RF network. 🟢"},
    "conclusao_amarela":            {"pt": "<br><b>Conclusão:</b> Rede funcional com oportunidades de melhoria. Monitorize em períodos de maior tráfego. 🟡",
                                     "en": "<br><b>Summary:</b> Functional network with room for improvement. Monitor during peak traffic periods. 🟡"},
    "conclusao_vermelha":           {"pt": "<br><b>Conclusão:</b> Qualidade RF abaixo do esperado. Reveja infraestrutura de antenas, posicionamento e modo de radio configurado. 🔴",
                                     "en": "<br><b>Summary:</b> RF quality below expectations. Review antenna infrastructure, placement and configured radio mode. 🔴"},
    "⏳ Aguardando pacotes RF...":  {"pt": "⏳ Aguardando pacotes RF...",        "en": "⏳ Awaiting RF packets..."},
    "Distribuição de tráfego da sessão":
                                    {"pt": "Distribuição de tráfego da sessão", "en": "Session traffic distribution"},
    "Padrão de Routing":            {"pt": "Padrão de Routing",                 "en": "Routing Pattern"},
    "Pacotes por Tipo — Sessão":    {"pt": "Pacotes por Tipo — Sessão",         "en": "Packets by Type — Session"},
    "Pacotes por Minuto (últimos 30 min)":
                                    {"pt": "Pacotes por Minuto (últimos 30 min)",
                                     "en": "Packets per Minute (last 30 min)"},
    "🟢 Directo":                   {"pt": "🟢 Directo",                        "en": "🟢 Direct"},
    "⚫ Desconhecido":               {"pt": "⚫ Desconhecido",                   "en": "⚫ Unknown"},
    "💬 Mensagem":                  {"pt": "💬 Mensagem",                       "en": "💬 Message"},
    "📍 Posição":                   {"pt": "📍 Posição",                        "en": "📍 Position"},
    "⏳ Aguardando pacotes...":     {"pt": "⏳ Aguardando pacotes...",           "en": "⏳ Awaiting packets..."},
    "Saúde dos nós, baterias e hardware · {hora}":
                                    {"pt": "Saúde dos nós, baterias e hardware · {hora}",
                                     "en": "Node health, batteries and hardware · {hora}"},
    "Bateria / Powered":            {"pt": "Bateria / Powered",                 "en": "Battery / Powered"},
    "Bateria Média":                {"pt": "Bateria Média",                     "en": "Avg Battery"},
    "{n} com alimentação externa · 📍 {m} com GPS":
                                    {"pt": "{n} com alimentação externa · 📍 {m} com GPS",
                                     "en": "{n} with external power · 📍 {m} with GPS"},
    "Nós Activos ao Longo do Tempo":{"pt": "Nós Activos ao Longo do Tempo",    "en": "Active Nodes Over Time"},
    "Nós activos":                  {"pt": "Nós activos",                       "en": "Active nodes"},
    "Distribuição de Bateria":      {"pt": "Distribuição de Bateria",           "en": "Battery Distribution"},
    "Hardware por Modelo ({n} nós)":{"pt": "Hardware por Modelo ({n} nós)",    "en": "Hardware by Model ({n} nodes)"},
    "Bateria por Nó":               {"pt": "Bateria por Nó",                    "en": "Battery per Node"},
    "Tensão":                       {"pt": "Tensão",                            "en": "Voltage"},
    "Sem dados de bateria ainda":   {"pt": "Sem dados de bateria ainda",        "en": "No battery data yet"},
    "Fiabilidade da rede Meshtastic — observação passiva + nó local":
                                    {"pt": "Fiabilidade da rede Meshtastic — observação passiva + nó local",
                                     "en": "Meshtastic network reliability — passive observation + local node"},
    "🌐 Fiabilidade da Rede (todos os nós)":
                                    {"pt": "🌐 Fiabilidade da Rede (todos os nós)",
                                     "en": "🌐 Network Reliability (all nodes)"},
    "Taxa de Flood (5 min)":        {"pt": "Taxa de Flood (5 min)",             "en": "Flood Rate (5 min)"},
    "Colisões Estimadas (CAD)":     {"pt": "Colisões Estimadas (CAD)",          "en": "Estimated Collisions (CAD)"},
    "NAK da Rede (ROUTING_APP)":    {"pt": "NAK da Rede (ROUTING_APP)",        "en": "Network NAK (ROUTING_APP)"},
    "Pacotes únicos (5 min)":       {"pt": "Pacotes únicos (5 min)",            "en": "Unique Packets (5 min)"},
    "% de pacotes únicos reencaminhados por ≥2 nós":
                                    {"pt": "% de pacotes únicos reencaminhados por ≥2 nós",
                                     "en": "% of unique packets forwarded by ≥2 nodes"},
    "Inclui NO_ROUTE e MAX_RETRANSMIT":
                                    {"pt": "Inclui NO_ROUTE e MAX_RETRANSMIT", "en": "Includes NO_ROUTE and MAX_RETRANSMIT"},
    "{n} nós emissores · {m} duplicados vistos":
                                    {"pt": "{n} nós emissores · {m} duplicados vistos",
                                     "en": "{n} sending nodes · {m} duplicates seen"},
    "ACK vs NAK — Rede":            {"pt": "ACK vs NAK — Rede",                "en": "ACK vs NAK — Network"},
    "Referências":                  {"pt": "Referências",                       "en": "References"},
    "Métrica":                      {"pt": "Métrica",                           "en": "Metric"},
    "Referência":                   {"pt": "Referência",                        "en": "Reference"},
    "Taxa de flood":                {"pt": "Taxa de flood",                     "en": "Flood rate"},
    "NAK da rede":                  {"pt": "NAK da rede",                       "en": "Network NAK"},
    "Entrega local":                {"pt": "Entrega local",                     "en": "Local delivery"},
    ">60% Congestionado":           {"pt": ">60% Congestionado",               "en": ">60% Congested"},
    "<10% Fraco":                   {"pt": "<10% Fraco",                       "en": "<10% Low"},
    "5-20% Atenção":               {"pt": "5-20% Atenção",                    "en": "5-20% Warning"},
    ">20% Crítico":                 {"pt": ">20% Crítico",                     "en": ">20% Critical"},
    "📍 Nó Local (mensagens enviadas)":
                                    {"pt": "📍 Nó Local (mensagens enviadas)", "en": "📍 Local Node (sent messages)"},
    "Taxa de Entrega Real":         {"pt": "Taxa de Entrega Real",              "en": "Actual Delivery Rate"},
    "Taxa NAK Local":               {"pt": "Taxa NAK Local",                   "en": "Local NAK Rate"},
    "Mensagens Enviadas":           {"pt": "Mensagens Enviadas",                "en": "Messages Sent"},
    "ACK do destinatário ÷ (ACK+NAK)":
                                    {"pt": "ACK do destinatário ÷ (ACK+NAK)", "en": "Recipient ACK ÷ (ACK+NAK)"},
    "Não inclui retransmissões locais":
                                    {"pt": "Não inclui retransmissões locais", "en": "Does not include local retransmissions"},
    "Falhas definitivas com errorReason":
                                    {"pt": "Falhas definitivas com errorReason","en": "Definitive failures with errorReason"},
    "Distribuição — Nó Local":      {"pt": "Distribuição — Nó Local",          "en": "Distribution — Local Node"},
    "Relay local":                  {"pt": "Relay local",                      "en": "Local relay"},
    "Pendente":                     {"pt": "Pendente",                         "en": "Pending"},
    "✅ Flood saudável":            {"pt": "✅ Flood saudável",                "en": "✅ Healthy flood"},
    "⏳ Envie mensagens para ver métricas do nó local.":
                                    {"pt": "⏳ Envie mensagens para ver métricas do nó local.",
                                     "en": "⏳ Send messages to see local node metrics."},
    "[!] Possível congestionamento": {"pt": "[!] Possível congestionamento",   "en": "[!] Possible congestion"},
    "[!] Risco elevado":            {"pt": "[!] Risco elevado",                "en": "[!] High risk"},
    "Sem dados de Ch.Util.":        {"pt": "Sem dados de Ch.Util.",            "en": "No Ch.Util. data"},
    "⏳ Aguardando pacotes ROUTING_APP na rede…":
                                    {"pt": "⏳ Aguardando pacotes ROUTING_APP na rede…",
                                     "en": "⏳ Awaiting ROUTING_APP packets on the network…"},
    "RTT (Round-Trip Time) — tempo entre envio e ACK · {n} amostras · {hora}":
                                    {"pt": "RTT (Round-Trip Time) — tempo entre envio e ACK · {n} amostras · {hora}",
                                     "en": "RTT (Round-Trip Time) — time between send and ACK · {n} samples · {hora}"},
    "RTT Mediana":                  {"pt": "RTT Mediana",                      "en": "Median RTT"},
    "RTT P90 (pior 10%)":           {"pt": "RTT P90 (pior 10%)",              "en": "RTT P90 (worst 10%)"},
    "RTT Mínimo":                   {"pt": "RTT Mínimo",                       "en": "Min RTT"},
    "RTT Máximo":                   {"pt": "RTT Máximo",                       "en": "Max RTT"},
    "Distribuição de RTT":          {"pt": "Distribuição de RTT",              "en": "RTT Distribution"},
    "Nº de mensagens":              {"pt": "Nº de mensagens",                  "en": "No. of messages"},
    "Interpretação":                {"pt": "Interpretação",                    "en": "Interpretation"},
    "RTT < 5s: Ligação directa excelente (0 hops).":
                                    {"pt": "RTT &lt; 5s:</b> Ligação directa excelente (0 hops).",
                                     "en": "RTT &lt; 5s:</b> Excellent direct link (0 hops)."},
    "RTT 5–15s: Normal para 1–2 hops em LoRa.":
                                    {"pt": "RTT 5–15s:</b> Normal para 1–2 hops em LoRa.",
                                     "en": "RTT 5–15s:</b> Normal for 1–2 hops over LoRa."},
    "RTT 15–30s: Possível congestão ou 3+ hops.":
                                    {"pt": "RTT 15–30s:</b> Possível congestão ou 3+ hops.",
                                     "en": "RTT 15–30s:</b> Possible congestion or 3+ hops."},
    "RTT > 30s: Rede congestionada ou rota longa.":
                                    {"pt": "RTT &gt; 30s:</b> Rede congestionada ou rota longa.",
                                     "en": "RTT &gt; 30s:</b> Congested network or long route."},
    "⏳ Sem dados de latência ainda.":
                                    {"pt": "⏳ Sem dados de latência ainda.",  "en": "⏳ No latency data yet."},
    "Envie mensagens com wantAck=True para medir o RTT":
                                    {"pt": "Envie mensagens com wantAck=True para medir o RTT",
                                     "en": "Send messages with wantAck=True to measure RTT"},
    "(tempo entre envio e ACK do destinatário).":
                                    {"pt": "(tempo entre envio e ACK do destinatário).",
                                     "en": "(time between send and recipient ACK)."},
    "Nós que se vêem mutuamente via LoRa · {n} nós reportaram · {m} pares únicos · {hora}":
                                    {"pt": "Nós que se vêem mutuamente via LoRa · {n} nós reportaram · {m} pares únicos · {hora}",
                                     "en": "Nodes that can see each other via LoRa · {n} nodes reported · {m} unique pairs · {hora}"},
    "Pares de Vizinhos Directos":   {"pt": "Pares de Vizinhos Directos",       "en": "Direct Neighbour Pairs"},
    "Nome A":                       {"pt": "Nome A",                           "en": "Name A"},
    "Nome B":                       {"pt": "Nome B",                           "en": "Name B"},
    "Sem pares":                    {"pt": "Sem pares",                        "en": "No pairs"},
    "neighborinfo_card":            {"pt": "Os nós da rede enviam automaticamente pacotes <b>NEIGHBORINFO_APP</b> com a lista de vizinhos directos e respectivo SNR.",
                                     "en": "Network nodes automatically send <b>NEIGHBORINFO_APP</b> packets with the list of direct neighbours and their SNR."},
    "neighborinfo_appear":          {"pt": "Estes dados aparecem normalmente após 1–2 minutos de operação se o módulo estiver activo.",
                                     "en": "This data normally appears after 1–2 minutes of operation if the module is active."},
    "⏳ Sem dados de NeighborInfo ainda.":
                                    {"pt": "⏳ Sem dados de NeighborInfo ainda.",
                                     "en": "⏳ No NeighborInfo data yet."},
    "⚙ Como activar o NeighborInfo":{"pt": "⚙ Como activar o NeighborInfo",   "en": "⚙ How to enable NeighborInfo"},
    "neighborinfo_intro":           {"pt": "Os pacotes de vizinhança <b>não são enviados por defeito</b> via LoRa. Para activar em cada nó:",
                                     "en": "Neighbourhood packets are <b>not sent by default</b> via LoRa. To enable on each node:"},
    "neighborinfo_li1":             {"pt": "Módulo <b>Neighbor Info</b> → <b>Enabled: ON</b>",
                                     "en": "Module <b>Neighbor Info</b> → <b>Enabled: ON</b>"},
    "neighborinfo_li2":             {"pt": "Activar <b>Transmit Over LoRa</b> (firmware ≥ 2.5.13)",
                                     "en": "Enable <b>Transmit Over LoRa</b> (firmware ≥ 2.5.13)"},
    "neighborinfo_li3":             {"pt": "Canal primário deve ser <b>privado</b> — canal público (LongFast/ShortFast com chave padrão) bloqueia este tráfego desde o firmware 2.5.13",
                                     "en": "Primary channel must be <b>private</b> — the public channel (LongFast/ShortFast with default key) blocks this traffic since firmware 2.5.13"},
    "neighborinfo_li4_viz":         {"pt": "Intervalo mínimo: <b>4 horas</b> (14 400 s) — os primeiros dados podem demorar",
                                     "en": "Minimum interval: <b>4 hours</b> (14,400 s) — first data may take a while"},
    "neighborinfo_li4_range":       {"pt": "Intervalo mínimo de envio: <b>4 horas</b> (14 400 s) — os primeiros dados podem demorar",
                                     "en": "Minimum send interval: <b>4 hours</b> (14,400 s) — first data may take a while"},
    "neighborinfo_note1":           {"pt": "ℹ O módulo deteta vizinhos mesmo que o nó vizinho não o tenha activo (firmware ≥ 2.3.2).",
                                     "en": "ℹ The module detects neighbours even if the neighbouring node does not have it active (firmware ≥ 2.3.2)."},
    "neighborinfo_note2":           {"pt": "⚠ A partir do firmware 2.5.13, o envio via LoRa no canal público foi bloqueado para reduzir tráfego. Por defeito, os dados chegam apenas via MQTT.",
                                     "en": "⚠ From firmware 2.5.13, sending via LoRa on the public channel was blocked to reduce traffic. By default, data only arrives via MQTT."},
    "Alcance dos links LoRa directos (requer GPS + NeighborInfo) · {hora}":
                                    {"pt": "Alcance dos links LoRa directos (requer GPS + NeighborInfo) · {hora}",
                                     "en": "Range of direct LoRa links (requires GPS + NeighborInfo) · {hora}"},
    "Maior Alcance":                {"pt": "Maior Alcance",                    "en": "Longest Range"},
    "Par de maior alcance":         {"pt": "Par de maior alcance",             "en": "Longest range pair"},
    "Nós com GPS":                  {"pt": "Nós com GPS",                     "en": "Nodes with GPS"},
    "Links por Alcance":            {"pt": "Links por Alcance",                "en": "Links by Range"},
    "Nó A":                         {"pt": "Nó A",                            "en": "Node A"},
    "Nó B":                         {"pt": "Nó B",                            "en": "Node B"},
    "Distância":                    {"pt": "Distância",                        "en": "Distance"},
    "⏳ Sem dados de alcance ainda.":
                                    {"pt": "⏳ Sem dados de alcance ainda.",   "en": "⏳ No range data yet."},
    "Requer que os nós reportem posição GPS (POSITION_APP)":
                                    {"pt": "Requer que os nós reportem posição GPS (<b>POSITION_APP</b>)",
                                     "en": "Requires nodes to report GPS position (<b>POSITION_APP</b>)"},
    "e que os dados de vizinhança (NEIGHBORINFO_APP) estejam disponíveis.":
                                    {"pt": "e que os dados de vizinhança (<b>NEIGHBORINFO_APP</b>) estejam disponíveis.",
                                     "en": "and neighbourhood data (<b>NEIGHBORINFO_APP</b>) to be available."},
    "Nós com GPS conhecidos até agora: {n}":
                                    {"pt": "Nós com GPS conhecidos até agora: <b>{n}</b>",
                                     "en": "Nodes with known GPS so far: <b>{n}</b>"},
    "range_haversine":              {"pt": "ℹ O cálculo de alcance usa a fórmula de Haversine sobre as coordenadas GPS de cada par de vizinhos reportados.",
                                     "en": "ℹ The range calculation uses the Haversine formula on the GPS coordinates of each reported neighbour pair."},
    "range_metric_info":            {"pt": "ℹ️ Métrica da rede — calcula a distância real entre nós vizinhos reportados via\n    <b>NEIGHBORINFO_APP</b>, usando as coordenadas GPS de cada nó (fórmula de Haversine).\n    Não envolve o nó local a não ser que ele também esteja nos pares.",
                                     "en": "ℹ️ Network metric — calculates the actual distance between neighbour nodes reported via\n    <b>NEIGHBORINFO_APP</b>, using each node's GPS coordinates (Haversine formula).\n    Does not involve the local node unless it is also in the pairs."},
    "viz_metric_info":              {"pt": "ℹ️ Estes dados provêm de pacotes <b>NEIGHBORINFO_APP</b> enviados pelos nós da rede —\n    representam ligações directas observadas por cada nó (não pelo nó local).\n    As linhas roxas pontilhadas no mapa mostram os mesmos pares.",
                                     "en": "ℹ️ This data comes from <b>NEIGHBORINFO_APP</b> packets sent by network nodes —\n    they represent direct links observed by each node (not the local node).\n    The purple dashed lines on the map show the same pairs."},
    "Intervalo real entre pacotes recebidos de cada nó · {hora}":
                                    {"pt": "Intervalo real entre pacotes recebidos de cada nó · {hora}",
                                     "en": "Actual interval between packets received from each node · {hora}"},
    "Intervalo Médio entre Pacotes por Nó":
                                    {"pt": "Intervalo Médio entre Pacotes por Nó",
                                     "en": "Average Packet Interval per Node"},
    "Média":                        {"pt": "Média",                            "en": "Average"},
    "Amostras":                     {"pt": "Amostras",                         "en": "Samples"},
    "Frequência":                   {"pt": "Frequência",                       "en": "Frequency"},
    "Alta frequência":              {"pt": "Alta frequência",                  "en": "High frequency"},
    "Baixa frequência":             {"pt": "Baixa frequência",                 "en": "Low frequency"},
    "⏳ Sem dados de intervalos ainda.":
                                    {"pt": "⏳ Sem dados de intervalos ainda.", "en": "⏳ No interval data yet."},
    "Requer pelo menos 2 pacotes por nó para calcular o intervalo médio.":
                                    {"pt": "Requer pelo menos 2 pacotes por nó para calcular o intervalo médio.",
                                     "en": "Requires at least 2 packets per node to calculate the average interval."},
    "intervals_metric_info":        {"pt": "ℹ️ Métrica da rede — mede o tempo real entre pacotes consecutivos de cada nó observado.\n    Um intervalo muito baixo pode indicar um nó mal configurado a congestionar o canal.\n    Um intervalo muito alto pode indicar um nó com problemas de cobertura ou bateria fraca.\n    Não envolve o nó local a não ser que ele também envie pacotes observáveis.",
                                     "en": "ℹ️ Network metric — measures the actual time between consecutive packets from each observed node.\n    A very low interval may indicate a misconfigured node congesting the channel.\n    A very high interval may indicate a node with coverage problems or weak battery.\n    Does not involve the local node unless it also sends observable packets."},
    "ℹ️ Intervalos <30s = alta frequência · 30–180s = normal · >180s = baixa frequência":
                                    {"pt": "ℹ️ Intervalos &lt;30s = alta frequência · 30–180s = normal · &gt;180s = baixa frequência",
                                     "en": "ℹ️ Intervals &lt;30s = high frequency · 30–180s = normal · &gt;180s = low frequency"},
    "duty_cycle_note":              {"pt": "ℹ️ Duty cycle horário estimado = airUtilTx × 6. Limite EU_433/EU_868: 10%/hora (ETSI EN300.220).",
                                     "en": "ℹ️ Estimated hourly duty cycle = airUtilTx × 6. EU_433/EU_868 limit: 10%/hour (ETSI EN300.220)."},
}
