import asyncio
import os
import pyperclip
import random
import re
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
    "current_view": "entrenamiento", "last_event": "Sistema Listo",
    "equipo_crudo": "", "rival_crudo": "",
    "pausa_import": False, "modo_sparring": False,
    "hp_aliado": 100, "hp_rival": 100
}

PKMN_STATS = {
    "Sinistcha": "HP: 168 / Def: 162 / SpA: 141",
    "Milotic": "HP: 100 / Def: 117 / SpA: 136",
    "Tyranitar": "Atk: 135 / Def: 127 / Spe: 80",
    "Incineroar": "Atk: 135 / Def: 127 / SpD: 139",
    "Rotom-Wash": "Def: 174 / SpA: 127 / Spe: 106",
    "Farigiraf": "SpA: 165 / Def: 104 / SpD: 90"
}

# =========================
# GESTOR DE EVENTOS (HOTKEYS)
# =========================
def on_press(key):
    try:
        k = key.char.lower()
        if k == 'm': ui_state["current_view"] = "entrenamiento"
        elif k == 's': ui_state["current_view"] = "estrategia"
        elif k == 'p': ui_state["current_view"] = "pokemon"
        elif k == 'e':
            pyperclip.copy(ui_state["equipo_crudo"])
            ui_state["last_event"] = "📋 ¡Copiado al Portapapeles!"
        elif k == 'i':
            ui_state["pausa_import"] = True 
    except AttributeError:
        pass

listener = keyboard.Listener(on_press=on_press)
listener.daemon = True
listener.start()

# =========================
# INTERFAZ GRÁFICA (RICH)
# =========================
def crear_monitor_batalla():
    grid = Table.grid(expand=True)
    aliado = Progress(TextColumn("[bold green]IA ALIADA "), BarColumn(bar_width=20, complete_style="green"), TextColumn("{task.fields[hp]}%"))
    aliado.add_task("hp", total=100, completed=ui_state["hp_aliado"], hp=ui_state["hp_aliado"])
    
    rival = Progress(TextColumn("[bold red]RIVAL      "), BarColumn(bar_width=20, complete_style="red"), TextColumn("{task.fields[hp]}%"))
    rival.add_task("hp", total=100, completed=ui_state["hp_rival"], hp=ui_state["hp_rival"])
    
    grid.add_row(aliado)
    grid.add_row(rival)
    return grid

def render_view():
    layout = Layout()
    layout.split_column(Layout(name="nav", size=3), Layout(name="content"))
    modo = "🥊 SPARRING" if ui_state["modo_sparring"] else "🧬 EVOLUTIVO"
    nav_text = f"{modo} | [M] Monitor | [S] Estrategia | [P] Pokémon | [E] Exportar | [I] Importar"
    layout["nav"].update(Panel(Align.center(nav_text), border_style="cyan"))

    if ui_state["current_view"] == "entrenamiento":
        layout["content"].split_row(Layout(name="left"), Layout(name="right"))
        telemetria = f"\n[bold yellow]Época:[/bold yellow] {ui_state['epoca']}\n[bold green]Win Rate:[/bold green] {ui_state['wr']*100:.1f}%\n[bold blue]Status:[/bold blue] {ui_state['status']}\n\n[bold magenta]Log:[/bold magenta]\n{ui_state['last_event']}"
        
        contenido_izquierdo = Group(Align.center(telemetria + "\n\n[white]MONITOR DE CAMPO[/white]\n"), crear_monitor_batalla())
        layout["left"].update(Panel(contenido_izquierdo, title="Telemetría", border_style="green"))
        layout["right"].update(Panel(f"[dim]{ui_state['equipo_crudo']}[/dim]", title="Equipo Activo", border_style="blue"))
    
    elif ui_state["current_view"] == "estrategia":
        table = Table(title="Análisis Táctico")
        table.add_column("Sinergia", style="cyan"); table.add_column("Fortaleza", style="green"); table.add_column("Debilidad", style="red")
        table.add_row("Core Regenerativo", "Hospitality + Matcha", "Fuego/Volador")
        table.add_row("Control de Campo", "Rage Powder Redirect", "Taunt/Prankster")
        layout["content"].update(Panel(table, border_style="magenta"))
        
    elif ui_state["current_view"] == "pokemon":
        table = Table(title="Base de Datos del Equipo")
        table.add_column("Pokémon", style="green"); table.add_column("Stats (Lvl 50)", style="white")
        for name, stats in PKMN_STATS.items(): table.add_row(name, stats)
        layout["content"].update(Align.center(table))
        
    return layout

# =========================
# LÓGICA DE IMPORTACIÓN
# =========================
def solicitar_importacion(label="EQUIPO"):
    console.clear()
    console.print(Panel(Align.center(f"[bold cyan]📥 MODO IMPORTACIÓN: {label}[/bold cyan]"), border_style="cyan"))
    console.print("Pega el código Showdown y escribe 'FIN' en una nueva línea o presiona ENTER dos veces:\n")
    
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

# =========================
# BUCLE PRINCIPAL
# =========================
async def main():
    console.clear()
    console.print(Panel(Align.center("[bold cyan]🚀 VGC 2026 AI - SELECTOR[/bold cyan]"), border_style="cyan"))
    console.print("\n[1] Modo Evolutivo\n[2] Modo Sparring (Rival Fijo)")
    
    opcion = input("\nSelecciona modo: ")
    
    if opcion == "2":
        ui_state["modo_sparring"] = True
        ui_state["equipo_crudo"] = solicitar_importacion("TU EQUIPO")
        ui_state["rival_crudo"] = solicitar_importacion("RIVAL FIJO")
    else:
        ui_state["equipo_crudo"] = "Sinistcha @ Leftovers\nAbility: Hospitality\nEVs: 22 HP / 22 Def / 22 SpD\nBold Nature\n- Matcha Gotcha\n- Strength Sap\n- Rage Powder\n- Protect"

    with Live(render_view(), refresh_per_second=10, screen=True) as live:
        while True:
            if ui_state["pausa_import"]:
                live.stop()
                ui_state["equipo_crudo"] = solicitar_importacion("ACTUALIZAR EQUIPO")
                ui_state["pausa_import"] = False
                ui_state["last_event"] = "📥 Equipo Actualizado"
                live.start()
            
            ui_state["status"] = "Combatiendo..."
            ui_state["hp_aliado"] = random.randint(30, 100)
            ui_state["hp_rival"] = random.randint(20, 100)
            
            await asyncio.sleep(2) 
            
            ui_state["epoca"] += 1
            ui_state["wr"] = random.uniform(0.4, 0.85)
            live.update(render_view())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.clear()
        console.print("[bold red]Sesión de entrenamiento finalizada.[/bold red]")
