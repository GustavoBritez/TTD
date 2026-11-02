import os
import json
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from controller import GameController
from vision import VisionSystem

console = Console()
CONFIG_FILE = "config.json"

# =====================================================================
# 1. BLOC DE NOTAS EN MEMORIA (WORKING MEMORY / SCRATCHPAD)
# =====================================================================
@dataclass
class WorkingMemory:
    """
    Mantiene el estado cognitivo del bot en tiempo real:
    - En qué oleada o fase está
    - Qué unidades ya colocó y sus niveles de mejora
    - Cuál es su objetivo actual y la cola de tareas pendientes
    - Registro de acciones recientes
    """
    match_number: int = 1
    current_wave: int = 1
    match_start_time: float = 0.0
    units_placed: Dict[str, bool] = field(default_factory=lambda: {
        "farm_1": False,
        "farm_2": False,
        "farm_3": False,
        "farm_4": False,
        "titan_1": False
    })
    upgrade_levels: Dict[str, int] = field(default_factory=lambda: {
        "farm_1": 0,
        "farm_2": 0,
        "farm_3": 0,
        "farm_4": 0,
        "titan_1": 0
    })
    current_objective: str = "INICIALIZAR_PARTIDA"
    action_log: List[str] = field(default_factory=list)

    def log(self, action: str):
        self.action_log.append(f"[{time.strftime('%H:%M:%S')}] {action}")
        if len(self.action_log) > 10:
            self.action_log.pop(0)

    def print_scratchpad(self):
        """Muestra en pantalla el bloc de notas mental del bot"""
        t = Table(title=f"Bloc de Notas en Memoria (Partida #{self.match_number})")
        t.add_column("Propiedad", style="cyan")
        t.add_column("Estado Actual", style="green")

        t.add_row("Objetivo Actual", f"[bold yellow]{self.current_objective}[/bold yellow]")
        t.add_row("Tiempo de Partida", f"{int(time.time() - self.match_start_time)}s")
        t.add_row("Granjas Colocadas", f"{sum(1 for k in self.units_placed if 'farm' in k and self.units_placed[k])}/4")
        t.add_row("Titán Colocado", "Sí" if self.units_placed["titan_1"] else "Pendiente (Oleada 6)")
        
        console.print(Panel(t, border_style="bold blue"))


# =====================================================================
# 2. CAJA DE HERRAMIENTAS (TOOLBOX)
# =====================================================================
class BotToolbox:
    """Herramientas de acción que el agente ejecuta en tiempo real"""
    def __init__(self, controller: GameController):
        self.controller = controller

    def tool_calibrate_camera(self):
        """Herramienta: Ajustar cámara cenital para fijar el mapa 3D a un plano 2D"""
        console.print("[cyan][Tool Use] Ejecutando: Calibrar Cámara Cenital[/cyan]")
        self.controller.calibrate_camera()

    def tool_enable_autoskip(self, x: int, y: int):
        """Herramienta: Presionar botón de acelerar/auto-skip"""
        console.print("[cyan][Tool Use] Ejecutando: Activar Auto-Skip[/cyan]")
        self.controller.click_at(x, y)

    def tool_place_unit(self, slot: int, x: int, y: int):
        """Herramienta: Seleccionar slot y colocar tropa en el mapa"""
        console.print(f"[cyan][Tool Use] Ejecutando: Colocar Unidad (Slot {slot}) en ({x}, {y})[/cyan]")
        self.controller.place_unit(slot, x, y)

    def tool_upgrade_unit(self, unit_x: int, unit_y: int, upgrade_btn_x: int, upgrade_btn_y: int):
        """Herramienta: Clic en la unidad y clic en el botón de mejora"""
        console.print(f"[cyan][Tool Use] Ejecutando: Mejorar Unidad en ({unit_x}, {unit_y})[/cyan]")
        self.controller.upgrade_unit_at(unit_x, unit_y, upgrade_btn_x, upgrade_btn_y)

    def tool_click_replay(self, x: int, y: int):
        """Herramienta: Clic en botón de Reintentar (Play Again)"""
        console.print("[cyan][Tool Use] Ejecutando: Clic en Play Again (Reintentar)[/cyan]")
        self.controller.click_at(x, y)

    def tool_anti_afk(self):
        """Herramienta: Micro-pulsación para evitar desconexión por inactividad"""
        self.controller.anti_afk_jiggle()


# =====================================================================
# 3. AGENTE CON BUCLE DE PERCEPCIÓN-DECISIÓN-ACCIÓN
# =====================================================================
class AgentTTD:
    def __init__(self):
        self.controller = GameController()
        self.tools = BotToolbox(self.controller)
        self.vision = VisionSystem()
        self.memory = WorkingMemory()
        self.config = self.load_config()

    def load_config(self) -> Optional[dict]:
        if not os.path.exists(CONFIG_FILE):
            console.print("[bold red]No se encontró config.json en la carpeta actual.[/bold red]")
            console.print("[yellow]Ejecuta 'python recorder.py' para calibrar tus posiciones primero.[/yellow]")
            return None
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)

    def evaluate_and_act(self, pos: dict):
        """
        Ciclo principal de toma de decisiones:
        1. Percibe el estado visual o temporal
        2. Consulta su bloc de notas (memory)
        3. Decide qué herramienta ejecutar
        4. Actualiza su memoria
        """
        elapsed = time.time() - self.memory.match_start_time

        # --- A. Fase de Inicialización (0 a 10s) ---
        if self.memory.current_objective == "INICIALIZAR_PARTIDA":
            self.tools.tool_calibrate_camera()
            time.sleep(1)
            if pos.get("autoskip_button"):
                self.tools.tool_enable_autoskip(pos["autoskip_button"]["x"], pos["autoskip_button"]["y"])
            self.memory.current_objective = "COLOCAR_GRANJAS"
            return

        # --- B. Fase de Granjas (Slot 1) ---
        if self.memory.current_objective == "COLOCAR_GRANJAS":
            for i in range(1, 5):
                key = f"farm_{i}"
                if not self.memory.units_placed[key] and pos.get(key):
                    p = pos[key]
                    self.tools.tool_place_unit(slot=1, x=p["x"], y=p["y"])
                    self.memory.units_placed[key] = True
                    self.memory.log(f"Granja {i} colocada")
                    time.sleep(1)
                    return
            
            # Si ya se colocaron las 4 granjas:
            self.memory.current_objective = "ESPERAR_TITAN_OLA_6"
            return

        # --- C. Esperar a Oleada 6 y colocar el Titán (Slot 2) ---
        if self.memory.current_objective == "ESPERAR_TITAN_OLA_6":
            # Con Auto-Skip activo, la oleada 6 llega aprox. a los 30 segundos
            if elapsed >= 30:
                if pos.get("titan_1"):
                    t = pos["titan_1"]
                    self.tools.tool_place_unit(slot=2, x=t["x"], y=t["y"])
                    self.memory.units_placed["titan_1"] = True
                    self.memory.log("Titán 1 colocado en chokepoint")
                    self.memory.current_objective = "MEJORAR_UNIDADES_Y_COMBATE"
            else:
                time.sleep(2)
            return

        # --- D. Modo Combate y Mejoras Activas ---
        if self.memory.current_objective == "MEJORAR_UNIDADES_Y_COMBATE":
            # Realizar mejoras en el Titán
            if pos.get("upgrade_button") and pos.get("titan_1"):
                t = pos["titan_1"]
                u = pos["upgrade_button"]
                self.tools.tool_upgrade_unit(t["x"], t["y"], u["x"], u["y"])
                self.memory.upgrade_levels["titan_1"] += 1
                self.memory.log(f"Upgrade intentado en Titán")

            # Anti-AFK preventivo
            self.tools.tool_anti_afk()

            # Vigilancia de Fin de Partida (después de 2 minutos)
            if elapsed > 120 and pos.get("play_again_button"):
                p_btn = pos["play_again_button"]
                self.tools.tool_click_replay(p_btn["x"], p_btn["y"])

    def run_match(self):
        if not self.config:
            return

        pos = self.config["positions"]
        self.memory.match_start_time = time.time()
        self.memory.current_objective = "INICIALIZAR_PARTIDA"
        self.memory.units_placed = {k: False for k in self.memory.units_placed}
        self.memory.upgrade_levels = {k: 0 for k in self.memory.upgrade_levels}

        console.print(f"[bold green]>>> COMIENZA PARTIDA #{self.memory.match_number} <<<[/bold green]")

        while True:
            elapsed = time.time() - self.memory.match_start_time
            self.memory.print_scratchpad()
            self.evaluate_and_act(pos)

            if elapsed > 1320:  # 22 minutos max
                console.print("[yellow]Fin de partida por tiempo máximo. Reiniciando...[/yellow]")
                break

            time.sleep(3)

    def start(self):
        console.print("[bold cyan]=================================================[/bold cyan]")
        console.print("[bold yellow]   AGENTE TTD: VISIÓN + MEMORIA + TOOL USE      [/bold yellow]")
        console.print("[bold cyan]=================================================[/bold cyan]")
        console.print("[white]Cambia a la ventana de Roblox. Iniciando en 5 segundos...[/white]")
        for i in range(5, 0, -1):
            console.print(f"Iniciando en {i}...")
            time.sleep(1)

        while True:
            self.run_match()
            self.memory.match_number += 1
            console.print("[bold cyan]Cargando nueva partida en 12 segundos...[/bold cyan]")
            time.sleep(12)

if __name__ == "__main__":
    agent = AgentTTD()
    agent.start()
