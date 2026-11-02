import os
import json
import time
import pyautogui
import keyboard
from rich.console import Console
from rich.table import Table

console = Console()
CONFIG_FILE = "config.json"

def main():
    width, height = pyautogui.size()
    
    positions = {
        "farm_1": None,
        "farm_2": None,
        "farm_3": None,
        "farm_4": None,
        "titan_1": None,
        "autoskip_button": None,
        "book_units_button": None,
        "upgrade_button": None,
        "close_manager_button": None,
        "play_again_button": None
    }

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                saved = json.load(f)
                positions.update(saved.get("positions", {}))
        except Exception:
            pass

    def show_status():
        os.system("cls" if os.name == "nt" else "clear")
        console.print("[bold cyan]=== TTD CALIBRADOR DE POSICIONES (Pon el cursor y presiona la tecla) ===[/bold cyan]\n")
        t = Table()
        t.add_column("Tecla", style="bold yellow")
        t.add_column("Elemento a Guardar", style="bold white")
        t.add_column("Coordenadas Guardadas", style="bold green")
        
        t.add_row("F1", "Granja 1 (Suelo)", str(positions["farm_1"]))
        t.add_row("F2", "Granja 2 (Suelo)", str(positions["farm_2"]))
        t.add_row("F3", "Granja 3 (Suelo)", str(positions["farm_3"]))
        t.add_row("F4", "Granja 4 (Suelo)", str(positions["farm_4"]))
        t.add_row("F5", "Titán 1 (Chokepoint)", str(positions["titan_1"]))
        t.add_row("F6", "Botón 'Auto-Skip' / Acelerar", str(positions["autoskip_button"]))
        t.add_row("F7", "Libro azul 'Unidades' (Abajo a la derecha)", str(positions["book_units_button"]))
        t.add_row("F8", "Botón Verde 'Mejora' (Dentro del Gerente)", str(positions["upgrade_button"]))
        t.add_row("F9", "Botón Rojo 'Salir' (Cerrar Gerente)", str(positions["close_manager_button"]))
        t.add_row("F10", "Botón 'Play Again' / Reintentar", str(positions["play_again_button"]))
        t.add_row("ESC", "[bold red]FINALIZAR Y GUARDAR[/bold red]", "")
        console.print(t)
        console.print("\n[dim]Apunta con el mouse sobre cada botón en Roblox y presiona la tecla indicada...[/dim]")

    show_status()

    key_mappings = {
        "f1": "farm_1",
        "f2": "farm_2",
        "f3": "farm_3",
        "f4": "farm_4",
        "f5": "titan_1",
        "f6": "autoskip_button",
        "f7": "book_units_button",
        "f8": "upgrade_button",
        "f9": "close_manager_button",
        "f10": "play_again_button",
    }

    while True:
        time.sleep(0.05)
        for key, name in key_mappings.items():
            if keyboard.is_pressed(key):
                pos = pyautogui.position()
                positions[name] = {"x": pos.x, "y": pos.y}
                time.sleep(0.3)
                show_status()
                break
        
        if keyboard.is_pressed("esc"):
            console.print("[bold green]\n¡Guardando en config.json!...[/bold green]")
            data = {
                "resolution": {"width": width, "height": height},
                "positions": positions
            }
            with open(CONFIG_FILE, "w") as f:
                json.dump(data, f, indent=4)
            console.print(f"[bold cyan]✔ Guardado con éxito en {CONFIG_FILE}[/bold cyan]")
            break

if __name__ == "__main__":
    main()
