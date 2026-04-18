import asyncio
import os
import pyperclip
import random
import re
import json
import sys
import requests
import websockets
from pynput import keyboard
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.console import Console, Group
from rich.table import Table
from rich.align import Align
from rich.progress import BarColumn, Progress, TextColumn

# =========================
# CONFIGURACIÓN Y RED GLOBAL
# =========================
console = Console()
VGC_FORMAT = "gen9championsvgc2026regma" 
VERSION_ACTUAL = "1.0"

# URLs de tu repositorio tai117/VGC_IA
URL_VERSION = "https://raw.githubusercontent.com/tai117/VGC_IA/main/version.txt"
URL_META_GLOBAL = "https://raw.githubusercontent.com/tai117/VGC_IA/main/global_meta.json"

ui_state = {
    "epoca": 1, "wr": 0.0, "status": "Iniciando...", 
    "current_view": "dashboard", 
    "logs": ["Sistema VGC AI Iniciado."],
    "equipo_crudo": "Sinistcha @ Leftovers\nAbility: Hospitality\nEVs: 22 HP / 22 Def / 22 SpD\nBold Nature\n- Matcha Gotcha\n- Strength Sap\n- Rage Powder\n- Protect",
    "pausa_import": False, "pausa_menu": False,
    "modo_sparring": False, "hp_aliado": 100, "hp_rival": 100
}

meta_db = {"pokemon_usage": {}, "common_moves": {}}

def add_log(msg):
    ui_state["logs"].append(msg)
    if len(ui_state["logs"]) > 15: ui_state["logs"].pop(0)

# =========================
# GESTIÓN DE ACTUALIZACIONES Y META GLOBAL
# =========================
async def sincronizar_meta_comunidad():
    """Descarga tendencias de la comunidad desde GitHub."""
    try:
        add_log("🌐 Sincronizando con Meta Global...")
        res = requests.get(URL_META_GLOBAL, timeout=5)
        if res.status_code == 200:
            datos = res.json()
            for pkmn, count in datos.get("pokemon_usage", {}).items():
                meta_db["pokemon_usage"][pkmn] = meta_db["pokemon_usage"].get(pkmn, 0) + count
            add_log("✅ Meta Global (Switch/Comunidad) sincronizado.")
    except:
        add_log("⚠️ Falló sincronización global. Usando datos locales.")

def verificar_actualizaciones():
    """Valida la versión del software contra el repositorio."""
    try:
        res = requests.get(URL_VERSION, timeout=3)
        if res.status_code == 200 and res.text.strip() != VERSION_ACTUAL:
            console.print(f"\n[bold red]NUEVA VERSIÓN DETECTADA ({res.text.strip()})[/bold red]")
            sys.exit()
    except: pass

# =========================
# MOTOR DE OBSERVACIÓN WS
# =========================
async def showdown_observer():
    """Observador en tiempo real del formato VGC 2026."""
    uri = "ws://sim.smogon.com:8000/showdown/websocket"
    try:
        async with websockets.connect(uri) as ws:
            ui_state["status"] = "Conectado WS"
            while True:
                msg = await ws.recv()
                if "|challstr|" in msg: await ws.send(f"|/cmd roomlist {VGC_FORMAT}")
                if VGC_FORMAT in msg and "roomlist" in msg:
                    room = re.search(rf'(battle-{VGC_FORMAT}-\d+)', msg)
                    if room: await ws.send(f"|/join {room.group(1)}")
                
                for line in msg.split('\n'):
                    parts = line.split('|')
                    if len(parts) > 2:
                        if parts[1] == 'poke':
                            p = parts[3].split(',')[0].strip()
                            meta_db["pokemon_usage"][p] = meta_db["pokemon_usage"].get(p, 0) + 1
                        elif parts[1] == 'move':
                            p = parts[2].split(':')[1].strip() if ':' in parts[2] else parts[2]
                            m = parts[3]
                            if p not in meta_db["common_moves"]: meta_db["common_moves"][p] = {}
                            meta_db["common_moves"][p][m] = meta_db["common_moves"][p].get(m, 0) + 1
                with open("meta_2026.json", "w") as f: json.dump(meta_db, f, indent=4)
    except: ui_state["status"] = "Error WS"

# =========================
# INTERFAZ Y NAVEGACIÓN (HOTKEYS)
# =========================
def on_press(key):
    try:
        k = key.char.lower()
        if k == 'd': ui_state["current_view"] = "dashboard"
        elif k == 'r': ui_state["current_view"] = "radar"
        elif k == 'l': ui_state["current_view"] = "logs"
        elif k == 'm': ui_state["pausa_menu"] = True
        elif k == 'i': ui_state["pausa_import"] = True
    except: pass

keyboard.Listener(on_press=on_press).start()

def render_view():
    layout = Layout()
    layout.split_column(Layout(name="h", size=3), Layout(name="b"), Layout(name="f", size=3))
    
    modo = "🥊 SPARRING" if ui_state["modo_sparring"] else "🧬 EVOLUTIVO"
    header = f"[bold cyan]VGC 2026 GLOBAL HUB[/bold cyan] | {modo} | WR: {ui_state['wr']*100:.1f}% | Ver: {VERSION_ACTUAL}"
    layout["h"].update(Panel(Align.center(header), border_style="cyan"))
    layout["f"].update(Panel(Align.center("[M] Menú | [D] Dash | [R] Radar | [L] Logs | [I] Import"), border_style="dim"))

    if ui_state["current_view"] == "dashboard":
        layout["b"].split_row(Layout(name="l", ratio=2), Layout(name="r"))
        hp = Table.grid(expand=True)
        for n, c, h in [("[green]IA", "green", ui_state["hp_aliado"]), ("[red]RV", "red", ui_state["hp_rival"])]:
            p = Progress(TextColumn(f"{n} "), BarColumn(bar_width=30, complete_style=c), TextColumn("{task.fields[hp]}%"))
            p.add_task("hp", total=100, completed=h, hp=h)
            hp.add_row(p)
        layout["l"].split_column(Layout(Panel(Align.center(hp), title="Live Monitor"), size=6), Layout(Panel("\n".join(ui_state["logs"][-6:]), title="Logs")))
        layout["r"].update(Panel(ui_state["equipo_crudo"][:400], title="Equipo"))

    elif ui_state["current_view"] == "radar":
        t = Table(title="Radar Anti-Meta (Comunidad + Local)", expand=True)
        t.add_column("Pokémon", style="bold"); t.add_column("Uso", justify="center"); t.add_column("Veredicto")
        total_uso = max(1, sum(meta_db["pokemon_usage"].values()))
        top = sorted(meta_db["pokemon_usage"].items(), key=lambda x: x[1], reverse=True)[:6]
        for p, c in top:
            status = "[red]Crit[/red]" if "Urshifu" in p or "Ogerpon" in p else "[green]OK[/green]"
            t.add_row(p, f"{(c/total_uso*100):.1f}%", status)
        layout["b"].update(Panel(Align.center(t), border_style="yellow"))

    elif ui_state["current_view"] == "logs":
        layout["b"].update(Panel("\n".join(ui_state["logs"]), title="System Console", border_style="magenta"))

    return layout

# =========================
# FLUJO DE CONTROL
# =========================
def solicitar_importacion(label="EQUIPO"):
    console.clear()
    console.print(Panel(Align.center(f"[bold cyan]📥 IMPORTACIÓN DE {label}[/bold cyan]")))
    lines = []
    while True:
        try:
            line = input().strip()
            if line.upper() == "FIN" or (line == "" and len(lines) > 0 and lines[-1] == ""): break
            lines.append(line)
        except EOFError: break
    return "\n".join(lines).strip()

def mostrar_menu_principal():
    console.clear()
    console.print(Panel(Align.center("[bold cyan]VGC AI 2026 - MENÚ[/bold cyan]")))
    op = input("\n[1] Evolutivo\n[2] Sparring\nSelecciona: ")
    ui_state["modo_sparring"] = (op == "2")
    if ui_state["modo_sparring"]:
        ui_state["equipo_crudo"] = solicitar_importacion("TU EQUIPO")
    add_log("🔄 Sesión iniciada.")

async def main():
    console.clear()
    verificar_actualizaciones()
    mostrar_menu_principal()
    
    asyncio.create_task(showdown_observer())
    await sincronizar_meta_comunidad()

    with Live(render_view(), refresh_per_second=10, screen=True) as live:
        while True:
            if ui_state["pausa_menu"]:
                live.stop(); await main(); break
            if ui_state["pausa_import"]:
                live.stop(); ui_state["equipo_crudo"] = solicitar_importacion("NUEVO EQUIPO")
                ui_state["pausa_import"] = False; live.start()
            
            ui_state["hp_aliado"] = random.randint(30, 100)
            ui_state["hp_rival"] = random.randint(20, 100)
            await asyncio.sleep(2.5)
            ui_state["epoca"] += 1; ui_state["wr"] = random.uniform(0.4, 0.85)
            live.update(render_view())

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: console.print("[red]Sistema Cerrado.")
