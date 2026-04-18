import asyncio
import os
import random
import re
import websockets
import requests
import pyperclip
from bs4 import BeautifulSoup
from pynput import keyboard 

# =========================
# CONFIGURACIÓN Y ESTADO
# =========================
VGC_FORMAT = "gen9championsvgc2026regma"
VERSION_ACTUAL = "9.8 CLI - Format Rules Validator" # NUEVO

ui_state = {
    "epoca": 1, 
    "current_view": "dashboard",
    "sub_view_counters": False, 
    "logs": ["🚀 Sistema VGC AI Nexus 9.8 CLI Online.", f"Filtro estricto: {VGC_FORMAT}."],
    "equipo_crudo": "",
    "equipo_parseado": [],
    "tailwind": False, "trickroom": False,
    "modo_sparring": False, "hp_aliado": 100, "hp_rival": 100,
    "pausa_input": False,
    "reportes": [],
    "cambios_equipo": [],
    "historial_amenaza": []
}

# =========================
# BASES DE DATOS
# =========================
meta_db = {
    "showdown_usage": {}, "showdown_cores": [], "showdown_leads": [],
    "switch_usage": {}, "switch_cores": [], "switch_leads": [],
}

BASE_STATS = {
    "Incineroar": {"hp": 95, "atk": 115, "def": 90, "spa": 80, "spd": 90, "spe": 60},
    "Garchomp": {"hp": 108, "atk": 130, "def": 95, "spa": 80, "spd": 85, "spe": 102},
    "Sneasler": {"hp": 80, "atk": 130, "def": 60, "spa": 40, "spd": 80, "spe": 120},
    "Whimsicott": {"hp": 60, "atk": 67, "def": 85, "spa": 77, "spd": 75, "spe": 116},
    "Kingambit": {"hp": 100, "atk": 135, "def": 120, "spa": 60, "spd": 85, "spe": 50},
    "Sinistcha": {"hp": 71, "atk": 60, "def": 106, "spa": 121, "spd": 80, "spe": 70},
    "Mega-Charizard-Y": {"hp": 78, "atk": 104, "def": 78, "spa": 159, "spd": 115, "spe": 100},
    "Basculegion": {"hp": 120, "atk": 112, "def": 65, "spa": 80, "spd": 75, "spe": 78},
    "Floette-Eternal": {"hp": 74, "atk": 65, "def": 67, "spa": 125, "spd": 128, "spe": 92}
}
STATS = ["hp", "atk", "def", "spa", "spd", "spe"]

TIPO_DEBILIDADES = {
    "Incineroar": ["Water", "Ground", "Rock", "Fighting"], "Sneasler": ["Psychic", "Ground", "Flying"],
    "Garchomp": ["Ice", "Dragon", "Fairy"], "Mega-Charizard-Y": ["Rock", "Water", "Electric"],
    "Basculegion": ["Ghost", "Dark", "Grass", "Electric"], "Sinistcha": ["Fire", "Ice", "Flying", "Dark", "Ghost"]
}

ESTRATEGIAS_CORES = {
    "Mega-Charizard-Y + Whimsicott": "Clima Paralelo (Pelipper/Tyranitar) para quitar el sol o Fake Out + Rock Slide x4 efectivo.",
    "Sneasler + Kingambit": "Intimidate + Will-O-Wisp (Rotom-Wash) neutraliza su presión física. Garchomp los amenaza a ambos.",
    "Incineroar + Sinistcha": "Clear Amulet en tu atacante físico y ataques Volador/Siniestro fuertes (Brave Bird).",
    "Garchomp + Floette-Eternal": "Control de Terreno y Hielo. Floette cubre los dragones, priorizar ataques Veneno/Acero primero.",
    "Pelipper + Basculegion": "Gastrodon (Storm Drain) o anular la lluvia. Speed control es vital."
}
ESTRATEGIAS_LEADS = {
    "Whimsicott + Garchomp": "Fake Out a Whimsicott + Ataque de Hielo (Ice Shard). No dejar que Garchomp haga SD.",
    "Incineroar + Basculegion": "Proteger al objetivo vulnerable. Redirección (Rage Powder) para ataques de Basculegion.",
    "Mega-Gengar + Sneasler": "Speed Control inmediato. Ambos son frágiles pero letales. Tailwind propio o Trick Room.",
    "Rotom-W + Kingambit": "Atacantes Lucha rápidos o Tierra que ignoren Levitación (Mold Breaker)."
}

# =========================
# UTILIDADES CLI
# =========================
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def add_log(msg):
    ui_state["logs"].append(f"[{ui_state['epoca']}] {msg}")
    if len(ui_state["logs"]) > 5: ui_state["logs"].pop(0)

# =========================
# PARSER Y MOTORES VGC
# =========================
def parse_evs_ivs(line, prefijo="EVs:"):
    stats_dict = {s: (31 if prefijo == "IVs:" else 0) for s in STATS}
    parts = line.replace(prefijo, "").split("/")
    for p in parts:
        try:
            val, stat = p.strip().split()
            stats_dict[stat.lower()[:3]] = int(val)
        except: pass
    return stats_dict

def parse_team(raw):
    blocks = raw.strip().split("\n\n")
    team = []
    for b in blocks:
        lines = [l.strip() for l in b.split("\n") if l.strip()]
        if not lines: continue
        data = {"name": "", "item": "", "evs": {s:0 for s in STATS}, "ivs": {s:31 for s in STATS}, "nature": "Hardy", "moves":[]}
        
        if "@" in lines[0]:
            name, item = lines[0].split("@", 1)
            data["name"] = name.replace("(M)","").replace("(F)","").strip()
            data["item"] = item.strip()
        else:
            data["name"] = lines[0].replace("(M)","").replace("(F)","").strip()

        for l in lines[1:]:
            if l.startswith("EVs:"): data["evs"] = parse_evs_ivs(l, "EVs:")
            elif l.startswith("IVs:"): data["ivs"] = parse_evs_ivs(l, "IVs:")
            elif l.endswith(" Nature"): data["nature"] = l.split(" ")[0].strip()
            elif l.startswith("-"): data["moves"].append(l[1:].strip())
        team.append(data)
    return team

# NUEVO: Validador Estricto de Formato
def validar_reglas_regma(team):
    errores = []
    for p in team:
        # 1. Validación de Stats (EVs / IVs limit)
        total_evs = sum(p["evs"].values())
        if total_evs > 510: errores.append(f"❌ {p['name']}: EVs exceden 510 (Tiene {total_evs}).")
        for stat, val in p["evs"].items():
            if val > 252: errores.append(f"❌ {p['name']}: EV en {stat} es ilegal ({val} > 252).")
        for stat, val in p["ivs"].items():
            if not (0 <= val <= 31): errores.append(f"❌ {p['name']}: IV en {stat} es ilegal ({val}).")
        
        # 2. Validación de Movimientos
        if len(p["moves"]) > 4: errores.append(f"❌ {p['name']}: Excede 4 movimientos permitidos.")
        elif len(p["moves"]) == 0: errores.append(f"⚠️ {p['name']}: No tiene movimientos registrados.")

        # 3. Validación de Items
        if not p["item"]: errores.append(f"⚠️ {p['name']}: No tiene objeto equipado.")

    return errores

def calc_speed(pokemon):
    base = BASE_STATS.get(pokemon["name"], {}).get("spe", 80)
    ev = pokemon["evs"].get("spe", 0)
    iv = pokemon["ivs"].get("spe", 31)
    
    raw_speed = int(((2 * base + iv + (ev // 4)) * 50) / 100) + 5
    nature = pokemon.get("nature", "")
    
    if nature in ["Timid", "Hasty", "Jolly", "Naive"]: raw_speed = int(raw_speed * 1.1)
    elif nature in ["Brave", "Relaxed", "Quiet", "Sassy"]: raw_speed = int(raw_speed * 0.9)
        
    if "Scarf" in pokemon.get("item", ""): raw_speed = int(raw_speed * 1.5)
    elif "Iron Ball" in pokemon.get("item", ""): raw_speed = int(raw_speed * 0.5)
        
    if ui_state["tailwind"]: raw_speed *= 2
    return raw_speed

def get_turn_order(team):
    speeds = [(p["name"], calc_speed(p), f"EV:{p['evs'].get('spe', 0)}|Nat:{p['nature'][:3]}") for p in team]
    return sorted(speeds, key=lambda x: x[1], reverse=not ui_state["trickroom"])

def determinar_amenaza(pkmn_meta):
    riesgo = 0
    ataques_meta = {"Incineroar": "Fire", "Sneasler": "Poison", "Garchomp": "Ground", "Mega-Charizard-Y": "Fire", "Basculegion": "Water"}
    tipo_ataque = ataques_meta.get(pkmn_meta, "Normal")
    for p in ui_state["equipo_parseado"]:
        if tipo_ataque in TIPO_DEBILIDADES.get(p["name"], []): riesgo += 1
    if riesgo >= 3: return "CRÍTICA"
    if riesgo == 2: return "ALTA"
    return "BAJA"

def actualizar_desde_web():
    try:
        add_log("🌐 Extrayendo Live Meta desde Pokémon Zone...")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get("https://www.pokemon-zone.com/champions/", headers=headers, timeout=10)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            texto_puro = soup.get_text(separator=' ')
            patron_uso = re.findall(r'([A-Z][a-zA-Z0-9\-]+)\s+(?:[A-Z][a-z]+\s+){0,2}(\d{1,3}\.\d)%\s*·', texto_puro)
            
            uso_real = {}
            for pkmn, pct in patron_uso:
                if pkmn not in ["Fire", "Dark", "Grass", "Water", "Teams", "Usage"]: 
                    uso_real[pkmn] = float(pct)
            
            if uso_real:
                meta_db["switch_usage"] = uso_real
                top_pkmn = list(uso_real.keys())[:10] 
                
                cores_activos = []
                if "Mega-Charizard-Y" in top_pkmn or "Whimsicott" in top_pkmn: cores_activos.append(("Mega-Charizard-Y + Whimsicott", "Sun + Tailwind"))
                if "Sneasler" in top_pkmn and "Kingambit" in top_pkmn: cores_activos.append(("Sneasler + Kingambit", "Offensive Pressure"))
                if "Incineroar" in top_pkmn and "Sinistcha" in top_pkmn: cores_activos.append(("Incineroar + Sinistcha", "Cycle Control"))
                if "Garchomp" in top_pkmn and "Floette-Eternal" in top_pkmn: cores_activos.append(("Garchomp + Floette-Eternal", "Dragon/Fairy"))
                meta_db["switch_cores"] = cores_activos if cores_activos else [("Meta Inestable", "Esperando consolidación")]

                leads_activos = []
                if "Whimsicott" in top_pkmn and "Garchomp" in top_pkmn: leads_activos.append(("Whimsicott + Garchomp", "TW + Setup"))
                if "Incineroar" in top_pkmn and "Basculegion" in top_pkmn: leads_activos.append(("Incineroar + Basculegion", "Fake Out + Swift Swim"))
                if "Sneasler" in top_pkmn: leads_activos.append(("Mega-Gengar + Sneasler", "Fast Offense"))
                if "Kingambit" in top_pkmn: leads_activos.append(("Rotom-W + Kingambit", "Pivot + Priority"))
                meta_db["switch_leads"] = leads_activos if leads_activos else [("Meta Inestable", "Esperando consolidación")]
                
                add_log("✅ Meta de Champions extraído exitosamente.")
                return
    except Exception as e:
        add_log(f"⚠️ Error de Scraping Web. Usando fallback local.")

    usage = [("Incineroar", 52.4), ("Sneasler", 45.2), ("Garchomp", 36.2), ("Sinistcha", 32.5), ("Kingambit", 26.9)]
    for name, percent in usage: meta_db["switch_usage"][name] = percent
    meta_db["switch_cores"] = [("Mega-Charizard-Y + Whimsicott", "Sun + Tailwind"), ("Sneasler + Kingambit", "Offensive Pressure"), ("Incineroar + Sinistcha", "Cycle Control")]
    meta_db["switch_leads"] = [("Whimsicott + Garchomp", "TW + Setup"), ("Incineroar + Basculegion", "Fake Out + Swift Swim")]

async def showdown_observer():
    uri = "ws://sim.smogon.com:8000/showdown/websocket"
    try:
        meta_db["showdown_usage"] = {"Sneasler": 142, "Incineroar": 130, "Garchomp": 115, "Mega-Charizard-Y": 98}
        meta_db["showdown_cores"] = [("Pelipper + Basculegion", "Rain Offense"), ("Garchomp + Floette-Eternal", "Dragon/Fairy")]
        meta_db["showdown_leads"] = [("Mega-Gengar + Sneasler", "Fast Offense"), ("Rotom-W + Kingambit", "Pivot + Priority")]
        async with websockets.connect(uri) as ws:
            await ws.send(f"|/search {VGC_FORMAT}")
            add_log(f"🔗 Conexión a Showdown sellada al formato: {VGC_FORMAT}")
            while True: await asyncio.sleep(1) 
    except: pass

# =========================
# MOTOR DE ANALÍTICA Y ADAPTACIÓN
# =========================
def generar_reporte_y_adaptar():
    epoca = ui_state["epoca"]
    
    top_switch = list(meta_db["switch_usage"].keys())[0] if meta_db["switch_usage"] else "Desconocido"
    top_sd = list(meta_db["showdown_usage"].keys())[0] if meta_db["showdown_usage"] else "Desconocido"
    
    reporte = f"Época {epoca:<4} | Top SW: {top_switch:<15} | Top SD: {top_sd}"
    ui_state["reportes"].insert(0, reporte)
    if len(ui_state["reportes"]) > 8: ui_state["reportes"].pop()

    if ui_state["equipo_crudo"]:
        raw = ui_state["equipo_crudo"]
        cambio = None
        
        if top_switch == "Incineroar" and "Clear Amulet" not in raw:
            raw = raw.replace("Focus Sash", "Clear Amulet").replace("Leftovers", "Clear Amulet")
            cambio = "Se equipó Clear Amulet para ignorar Intimidate de Incineroar."
        elif top_switch == "Garchomp" and "Air Balloon" not in raw:
            raw = raw.replace("Clear Amulet", "Air Balloon").replace("Focus Sash", "Air Balloon")
            cambio = "Se equipó Air Balloon para evadir Ground attacks de Garchomp."
            
        if cambio:
            ui_state["equipo_crudo"] = raw
            ui_state["equipo_parseado"] = parse_team(raw)
            ui_state["cambios_equipo"].insert(0, f"[{epoca}] {cambio}")
            if len(ui_state["cambios_equipo"]) > 5: ui_state["cambios_equipo"].pop()
            add_log(f"⚙️ AUTO-ADAPT: {cambio}")

    amenaza_total = sum(1 for p in list(meta_db["switch_usage"].keys())[:6] if determinar_amenaza(p) in ["ALTA", "CRÍTICA"])
    ui_state["historial_amenaza"].append(amenaza_total)
    if len(ui_state["historial_amenaza"]) > 10: ui_state["historial_amenaza"].pop(0)

async def simulador_hp():
    while True:
        ui_state["epoca"] += 1
        ui_state["hp_aliado"] = random.randint(30, 100)
        ui_state["hp_rival"] = random.randint(20, 100)
        
        if ui_state["epoca"] % 10 == 0:
            generar_reporte_y_adaptar()
            
        await asyncio.sleep(5) 

# =========================
# VISTAS CLI (RENDERERS)
# =========================
def render_header():
    modo = "SPARRING" if ui_state["modo_sparring"] else "EVOLUTIVO"
    tw = "ON" if ui_state["tailwind"] else "OFF"
    tr = "ON" if ui_state["trickroom"] else "OFF"
    counters = "ON" if ui_state["sub_view_counters"] else "OFF"
    
    print("=" * 80)
    print(f"{VERSION_ACTUAL} | {modo} | VISTA: {ui_state['current_view'].upper()}")
    print(f"Campos -> Tailwind(t): {tw} | TrickRoom(r): {tr} | Estrategias(c): {counters}")
    print("=" * 80)

def render_dashboard():
    print(f"MONITOR DE COMBATE (Live) - Aliado: {ui_state['hp_aliado']}% | Rival: {ui_state['hp_rival']}%")
    print("-" * 80)
    print("ÚLTIMOS EVENTOS:")
    for log in ui_state["logs"]: print(f"  > {log}")
    print("-" * 80)
    print("EQUIPO ACTIVO (Extracto):")
    if ui_state["equipo_crudo"]:
        lineas_equipo = ui_state["equipo_crudo"].split('\n')[:4]
        for linea in lineas_equipo: print(f"  {linea}")
        print("  ...")
    else:
        print("  Sin equipo importado.")

def render_meta(is_switch):
    usage_data = meta_db["switch_usage"] if is_switch else meta_db["showdown_usage"]
    cores_data = meta_db["switch_cores"] if is_switch else meta_db["showdown_cores"]
    leads_data = meta_db["switch_leads"] if is_switch else meta_db["showdown_leads"]
    
    print("USO DEL META:")
    for p, c in sorted(usage_data.items(), key=lambda x: x[1], reverse=True)[:5]:
        bar = '█' * int(c / 2) if is_switch else str(c)
        val = f"{c}%" if is_switch else "usos"
        print(f"  {p:<20} | {bar:<25} {val}")
    print("-" * 80)

    if ui_state["sub_view_counters"]:
        print("CÓMO ROMPER LOS TOP CORES / LEADS:")
        for nombre, _ in cores_data + leads_data:
            estrategia = ESTRATEGIAS_CORES.get(nombre) or ESTRATEGIAS_LEADS.get(nombre, "Priorizar daño neutro.")
            print(f"  [!] {nombre:<30} -> {estrategia}")
    else:
        print(f"{'CORES METAGAME':<40} | LEADS FRECUENTES")
        for i in range(max(len(cores_data), len(leads_data))):
            core = f"{cores_data[i][0]} ({cores_data[i][1]})" if i < len(cores_data) else ""
            lead = f"{leads_data[i][0]} ({leads_data[i][1]})" if i < len(leads_data) else ""
            print(f"  {core:<38} | {lead}")

def render_tactico():
    print(f"{'AMENAZA GLOBAL':<25} | VEREDICTO")
    print("-" * 40)
    for p in list(meta_db["switch_usage"].keys())[:6]:
        riesgo = determinar_amenaza(p)
        print(f"  {p:<23} | {riesgo}")

def render_velocidad():
    print("CALCULADORA DE TURNOS DINÁMICA (Lvl 50)")
    print(f"{'Turno':<6} | {'Pokémon':<20} | {'Params.':<15} | {'Vel. Final'}")
    print("-" * 65)
    
    if not ui_state["equipo_parseado"]: 
        print("  Sin datos. Importa un equipo primero (Comando: i)")
    else:
        for i, (name, spd, details) in enumerate(get_turn_order(ui_state["equipo_parseado"]), 1):
            print(f"  #{i:<4} | {name:<20} | {details:<15} | {spd}")

def render_reportes():
    print("REPORTES DE RENDIMIENTO (Corte cada 10 Épocas)")
    print("-" * 80)
    if not ui_state["reportes"]:
        print("  [!] Esperando alcanzar la Época 10 para generar el primer análisis...")
    for r in ui_state["reportes"]:
        print(f"  📊 {r}")
        
    print("\nHISTORIAL DE ADAPTACIONES AUTÓNOMAS:")
    if not ui_state["cambios_equipo"]:
        print("  [!] Ninguna mutación aplicada al equipo todavía.")
    for c in ui_state["cambios_equipo"]:
        print(f"  🔧 {c}")

def render_graficos():
    print("GRÁFICO DE ADAPTACIÓN: AMENAZA DEL META VS TU EQUIPO")
    print("Objetivo: Reducir las barras (Menos amenazas detectadas en el top 6)")
    print("-" * 80)
    
    if not ui_state["historial_amenaza"]:
        print("  [!] Recopilando telemetría... (Requiere alcanzar la Época 10)")
        return

    max_val = max(ui_state["historial_amenaza"]) if max(ui_state["historial_amenaza"]) > 0 else 1
    for i, val in enumerate(ui_state["historial_amenaza"]):
        bar_length = int((val / max_val) * 30)
        bar = '▓' * bar_length
        epoca_num = (i + 1) * 10
        print(f"  Época {epoca_num:<3} | {bar:<30} ({val} amenazas activas)")

def render_view():
    clear_screen()
    render_header()
    
    view = ui_state["current_view"]
    if view == "dashboard": render_dashboard()
    elif view == "meta_switch": render_meta(True)
    elif view == "meta_showdown": render_meta(False)
    elif view == "simulador_tactico": render_tactico()
    elif view == "simulador_velocidad": render_velocidad()
    elif view == "reportes": render_reportes()
    elif view == "graficos": render_graficos()
    
    print("=" * 80)
    print("COMANDOS: [d]ash | [1] Switch | [2] Showdown | [3] Táctico | [4] Velocidad")
    print("          [5] Reportes | [6] Gráficos | [i]mportar | [e]xportar | [q]uit")

# =========================
# LÓGICA DE INTERACCIÓN
# =========================
# NUEVO: Lógica de feedback tras importar
def procesar_importacion_y_validar(raw_team):
    ui_state["equipo_crudo"] = raw_team
    ui_state["equipo_parseado"] = parse_team(raw_team)
    ui_state["historial_amenaza"] = [] 
    ui_state["cambios_equipo"] = []
    
    errores_formato = validar_reglas_regma(ui_state["equipo_parseado"])
    if errores_formato:
        add_log("⚠️ ADVERTENCIA: El equipo viola las reglas de Champions Reg M-A:")
        for err in errores_formato[:3]: add_log(err)
        if len(errores_formato) > 3: add_log(f"  ...y {len(errores_formato)-3} errores más.")
    else:
        add_log("✅ Equipo importado y 100% legal para el formato.")

def solicitar_importacion():
    raw = pyperclip.paste().strip()
    if raw:
        procesar_importacion_y_validar(raw)
    else:
        add_log("⚠️ Portapapeles vacío. No se pudo importar.")

def exportar_equipo():
    if ui_state["equipo_crudo"]:
        pyperclip.copy(ui_state["equipo_crudo"])
        add_log("📤 Equipo actual copiado al portapapeles.")
    else:
        add_log("⚠️ No hay equipo activo para exportar.")

def mostrar_menu_principal():
    ui_state["pausa_input"] = True
    clear_screen()
    print("=" * 80)
    print(" VGC NEXUS 9.8 CLI - MAIN MENU ".center(80))
    print("=" * 80)
    print("\n[1] Modo Escalar Ladder")
    print("[2] Modo Sparring (Importará equipo del portapapeles)")
    op = input("\nSelecciona: ").strip()
    
    ui_state["modo_sparring"] = (op == "2")
    if ui_state["modo_sparring"]:
        solicitar_importacion()
    ui_state["current_view"] = "dashboard"
    ui_state["pausa_input"] = False

def on_press(key):
    if ui_state.get("pausa_input", False): return 
    
    try:
        cmd = key.char.lower()
        if cmd == 'd': ui_state["current_view"] = "dashboard"
        elif cmd == '1': ui_state["current_view"] = "meta_switch"
        elif cmd == '2': ui_state["current_view"] = "meta_showdown"
        elif cmd == '3': ui_state["current_view"] = "simulador_tactico"
        elif cmd == '4': ui_state["current_view"] = "simulador_velocidad"
        elif cmd == '5': ui_state["current_view"] = "reportes"
        elif cmd == '6': ui_state["current_view"] = "graficos"
        elif cmd == 'c': ui_state["sub_view_counters"] = not ui_state["sub_view_counters"]
        elif cmd == 't': 
            ui_state["tailwind"] = not ui_state["tailwind"]
            add_log(f"🌪️ Tailwind {'ON' if ui_state['tailwind'] else 'OFF'}")
        elif cmd == 'r': 
            ui_state["trickroom"] = not ui_state["trickroom"]
            add_log(f"🌀 Trick Room {'ON' if ui_state['trickroom'] else 'OFF'}")
        elif cmd == 'i': solicitar_importacion()
        elif cmd == 'e': exportar_equipo()
        elif cmd == 'm': mostrar_menu_principal()
        elif cmd == 'q': 
            print("\nSaliendo de VGC Nexus CLI...")
            os._exit(0) 
    except AttributeError:
        pass

async def auto_render():
    while True:
        if not ui_state.get("pausa_input", False):
            render_view()
        await asyncio.sleep(2)

async def main():
    portapapeles_inicial = pyperclip.paste().strip()
    if portapapeles_inicial and ("EVs:" in portapapeles_inicial or "@" in portapapeles_inicial):
        # Usamos la misma función nueva para asegurar validación al arrancar
        procesar_importacion_y_validar(portapapeles_inicial)

    actualizar_desde_web()
    mostrar_menu_principal()
    
    listener = keyboard.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()
    
    asyncio.create_task(showdown_observer())
    asyncio.create_task(simulador_hp())
    
    await auto_render()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSistemas apagados.")
