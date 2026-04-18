import asyncio
import os
import pyperclip
import random
import re
import json
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
# CONFIGURACIÓN Y ESTADO
# =========================
console = Console()
VGC_FORMAT = "gen9championsvgc2026regma" 

ui_state = {
    "epoca": 1, "wr": 0.0, "status": "Iniciando...", 
    "current_view": "dashboard", 
    "logs": ["Sistema VGC AI Iniciado."],
    "equipo_crudo": "Sinistcha @ Leftovers\nAbility: Hospitality\nEVs: 22 HP / 22 Def / 22 SpD\nBold Nature\n- Matcha Gotcha\n- Strength Sap\n- Rage Powder\n- Protect",
    "rival_crudo": "",
    "pausa_import": False, 
    "pausa_menu": False, # Nuevo estado para el Menú Principal
    "modo_sparring": False,
    "hp_aliado": 100, "hp_rival": 100
}

meta_db = {
    "pokemon_usage": {},
    "common_moves": {}
}

def add_log(msg):
    ui_state["logs"].append(msg)
    if len(ui_state["logs"]) > 15:
        ui_state["logs"].pop(0)

# =========================
# GESTOR DE EVENTOS (HOTKEYS)
# =========================
def on_press(key):
    try:
        k = key.char.lower()
        if k == 'd': ui_state["current_view"] = "dashboard"
        elif k == 'r': ui_state["current_view"] = "radar"
        elif k == 'l': ui_state["current_view"] = "logs"
        elif k == 'm': ui_state["pausa_menu"] = True  # Nuevo atajo
        elif k == 'e':
            pyperclip.copy(ui_state["equipo_crudo"])
            add_log("📋 Equipo copiado al Portapapeles.")
        elif k == 'i':
            ui_state["pausa_import"] = True 
    except AttributeError:
        pass

listener = keyboard.Listener(on_press=on_press)
listener.daemon = True
listener.start()

# =========================
# MOTOR DE SCRAPING WS (OBSERVADOR)
# =========================
async def showdown_observer():
    uri = "ws://sim.smogon.com:8000/showdown/websocket"
    try:
        async with websockets.connect(uri) as websocket:
            ui_state["status"] = "Conectado WS"
            add_log("🟢 Conexión WebSocket establecida con Showdown.")
            
            while True:
                message = await websocket.recv()
                
                if "|challstr|" in message:
                    await websocket.send(f"|/cmd roomlist {VGC_FORMAT}")
                
                if VGC_FORMAT in message and "roomlist" in message:
                    match = re.search(rf'(battle-{VGC_FORMAT}-\d+)', message)
                    if match:
                        room_id = match.group(1)
                        await websocket.send(f"|/join {room_id}")
                        add_log(f"👁️ Scrapeando sala: {room_id}")
                
                lines = message.split('\n')
                for line in lines:
                    parts = line.split('|')
                    if len(parts) > 2:
                        if parts[1] == 'poke':
                            pkmn = parts[3].split(',')[0].strip()
                            meta_db["pokemon_usage"][pkmn] = meta_db["pokemon_usage"].get(pkmn, 0) + 1
                        elif parts[1] == 'move':
                            pkmn = parts[2].split(':')[1].strip() if ':' in parts[2] else parts[2]
                            move = parts[3]
                            if pkmn not in meta_db["common_moves"]:
                                meta_db["common_moves"][pkmn] = {}
                            meta_db["common_moves"][pkmn][move] = meta_db["common_moves"][pkmn].get(move, 0) + 1
                            
                with open("meta_2026.json", "w") as f:
                    json.dump(meta_db, f, indent=4)
                    
    except Exception as e:
        ui_state["status"] = "Error WS"
        add_log(f"🔴 Error WebSocket: {str(e)[:40]}")

# =========================
# DISEÑO DE INTERFAZ (RICH REDESIGN)
# =========================
def render_header():
    modo = "🥊 SPARRING" if ui_state["modo_sparring"] else "🧬 EVOLUTIVO"
    text = f"[bold cyan]VGC 2026 CENTRAL HUB[/bold cyan] | Modo: {modo} | Época: {ui_state['epoca']} | Win Rate: {ui_state['wr']*100:.1f}% | Status: {ui_state['status']}"
    return Panel(Align.center(text), border_style="cyan")

def render_footer():
    text = "[M] Menú Principal  |  [D] Dashboard  |  [R] Radar Anti-Meta  |  [L] Logs  |  [I] Importar  |  [E] Exportar"
    return Panel(Align.center(text), border_style="dim white")

def render_view():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3)
    )
    
    layout["header"].update(render_header())
    layout["footer"].update(render_footer())

    # --- VISTA 1: DASHBOARD ---
    if ui_state["current_view"] == "dashboard":
        layout["body"].split_row(Layout(name="left", ratio=2), Layout(name="right", ratio=1))
        
        hp_grid = Table.grid(expand=True)
        
        progreso_aliado = Progress(TextColumn("[bold green]TÚ    "), BarColumn(bar_width=30, complete_style="green"), TextColumn("{task.fields[hp]}%"))
        progreso_aliado.add_task("hp", total=100, completed=ui_state["hp_aliado"], hp=ui_state["hp_aliado"])
        
        progreso_rival = Progress(TextColumn("[bold red]RIVAL "), BarColumn(bar_width=30, complete_style="red"), TextColumn("{task.fields[hp]}%"))
        progreso_rival.add_task("hp", total=100, completed=ui_state["hp_rival"], hp=ui_state["hp_rival"])
        
        hp_grid.add_row(progreso_aliado)
        hp_grid.add_row(progreso_rival)
        
        monitor_panel = Panel(Align.center(hp_grid), title="Monitor de Combate", border_style="green", height=6)
        
        mini_logs = "\n".join(ui_state["logs"][-6:])
        logs_panel = Panel(f"[dim]{mini_logs}[/dim]", title="Eventos Recientes", border_style="dim white")
        
        layout["left"].split_column(Layout(monitor_panel, size=6), Layout(logs_panel))
        layout["right"].update(Panel(f"[cyan]{ui_state['equipo_crudo'][:500]}...[/cyan]", title="Equipo Activo", border_style="blue"))
    
    # --- VISTA 2: RADAR ANTI-META ---
    elif ui_state["current_view"] == "radar":
        table = Table(title="Radar Showdown (Tier List Dinámica)", expand=True)
        table.add_column("Amenaza", style="bold white")
        table.add_column("Uso Real", style="cyan", justify="center")
        table.add_column("Ataque Frecuente", style="magenta")
        table.add_column("Veredicto Ofensivo", justify="center")
        
        top_meta = sorted(meta_db["pokemon_usage"].items(), key=lambda x: x[1], reverse=True)[:6]
        
        if not top_meta:
            table.add_row("Esperando batallas...", "-", "-", "[dim]Calibrando...[/dim]")
        else:
            total = sum(meta_db["pokemon_usage"].values())
            for pkmn, count in top_meta:
                uso_pct = (count / total) * 100
                top_move = "-"
                if pkmn in meta_db["common_moves"] and meta_db["common_moves"][pkmn]:
                    top_move = max(meta_db["common_moves"][pkmn], key=meta_db["common_moves"][pkmn].get)
                
                if "Ogerpon" in pkmn or "Urshifu" in pkmn:
                    veredicto = "[bold red]Se requiere RK / Check[/bold red]" 
                else:
                    veredicto = "[bold green]Cobertura OK[/bold green]"
                    
                table.add_row(pkmn, f"{uso_pct:.1f}%", top_move, veredicto)
                
        layout["body"].update(Panel(Align.center(table), border_style="yellow"))
        
    # --- VISTA 3: LOGS DE SISTEMA ---
    elif ui_state["current_view"] == "logs":
        logs_text = "\n".join(ui_state["logs"])
        layout["body"].update(Panel(logs_text, title="Consola de Depuración", border_style="magenta"))
        
    return layout

# =========================
# FUNCIONES DE MENÚ E IMPORTACIÓN
# =========================
def solicitar_importacion(label="EQUIPO"):
    console.clear()
    console.print(Panel(Align.center(f"[bold cyan]📥 IMPORTACIÓN DE {label}[/bold cyan]"), border_style="cyan"))
    console.print("Pega el código Showdown y presiona [bold]ENTER dos veces[/bold]:\n")
    
    lines = []
    while True:
        try:
            line = input().strip()
            if line.upper() == "FIN" or (line == "" and len(lines) > 0 and lines[-1] == ""): break
            lines.append(line)
        except EOFError:
            break
            
    raw = "\n".join(lines).strip()
    return re.sub(r'\n{3,}', '\n\n', raw)

def mostrar_menu_principal():
    """Función separada para poder llamarla al inicio y cuando el usuario presione 'M'"""
    console.clear()
    console.print(Panel(Align.center("[bold cyan]🚀 VGC 2026 AI - MENÚ PRINCIPAL[/bold cyan]"), border_style="cyan"))
    opcion = input("\n[1] Modo Evolutivo (Escalar Meta)\n[2] Modo Sparring (Rival Fijo)\n\nSelecciona: ")
    
    if opcion == "2":
        ui_state["modo_sparring"] = True
        ui_state["equipo_crudo"] = solicitar_importacion("TU EQUIPO")
        ui_state["rival_crudo"] = solicitar_importacion("RIVAL FIJO")
    else:
        ui_state["modo_sparring"] = False
        # Equipo por defecto para el modo evolutivo si no se tiene uno
        if not ui_state["equipo_crudo"] or ui_state["equipo_crudo"] == "":
            ui_state["equipo_crudo"] = "Sinistcha @ Leftovers\nAbility: Hospitality\nEVs: 22 HP / 22 Def / 22 SpD\nBold Nature\n- Matcha Gotcha\n- Strength Sap\n- Rage Powder\n- Protect"

# =========================
# BUCLE PRINCIPAL
# =========================
async def main():
    # Lanzar el menú principal la primera vez
    mostrar_menu_principal()

    # Iniciar la recolección de datos en segundo plano
    asyncio.create_task(showdown_observer())

    # Iniciar la interfaz gráfica
    with Live(render_view(), refresh_per_second=10, screen=True) as live:
        while True:
            # Lógica para regresar al menú principal
            if ui_state["pausa_menu"]:
                live.stop()
                mostrar_menu_principal()
                ui_state["pausa_menu"] = False
                ui_state["current_view"] = "dashboard" # Devolver la vista al dashboard
                add_log("🔄 Reinicio de sesión desde el Menú Principal.")
                live.start()

            # Lógica de importación rápida
            if ui_state["pausa_import"]:
                live.stop()
                ui_state["equipo_crudo"] = solicitar_importacion("NUEVO EQUIPO")
                ui_state["pausa_import"] = False
                add_log("📥 Equipo actualizado por el usuario.")
                live.start()
            
            ui_state["hp_aliado"] = random.randint(30, 100)
            ui_state["hp_rival"] = random.randint(20, 100)
            
            await asyncio.sleep(2.5) 
            
            ui_state["epoca"] += 1
            ui_state["wr"] = random.uniform(0.4, 0.85)
            live.update(render_view())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.clear()
        console.print("[bold red]Sesión terminada. Base de datos del meta guardada en meta_2026.json[/bold red]")
