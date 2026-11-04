import os
import json
import time
import threading
import tkinter as tk
from tkinter import messagebox, filedialog
from PIL import Image, ImageTk
import customtkinter as ctk
import pyautogui
import keyboard

from controller import GameController, enable_dpi_awareness
from vision import VisionSystem

enable_dpi_awareness()



CONFIG_FILE = "config.json"

BLUEPRINT_FILE = "blueprint.json"

STRATEGIES_DIR = os.path.join(os.path.dirname(__file__), "strategies")

_POINTS_MAP_PATH = os.path.join(
    os.path.dirname(__file__),
    "templates",
    "Mapa_Endless",
    "Puntos_De_Colocacion",
    "Puntos_de_unidades_Colocacion.png",
)
MAP_ASSET_PATH = (
    _POINTS_MAP_PATH
    if os.path.exists(_POINTS_MAP_PATH)
    else os.path.join(os.path.dirname(__file__), "assets", "map_endless.jpg")
)



os.makedirs(STRATEGIES_DIR, exist_ok=True)



# Configuración visual de CustomTkinter

ctk.set_appearance_mode("Dark")

ctk.set_default_color_theme("blue")



UNIT_PRESETS = {

    1: {"name": "Granja", "cost": 200, "color": "#2ed573", "text_color": "#ffffff"},

    2: {"name": "Mejor Guerrero", "cost": 1200, "color": "#ffa502", "text_color": "#000000"},

    3: {"name": "Titanes", "cost": 1050, "color": "#1e90ff", "text_color": "#ffffff"},

    4: {"name": "Soporte", "cost": 1000, "color": "#9b59b6", "text_color": "#ffffff"}

}



class TTDGuiApp(ctk.CTk):

    def __init__(self):

        super().__init__()



        self.title("TTD Visual Blueprint & Agent Dashboard | Modo Abisal")

        self.geometry("1080x750")

        self.minsize(980, 680)



        # Estado del Agente

        self.is_running = False

        self.bot_thread = None

        self.controller = GameController()

        self.vision = VisionSystem()



        # Variables de Memoria en Vivo

        self.match_count = 0

        self.current_objective = "DETENIDO"

        self.current_money = 0

        self.match_start_time = 0.0



        # Planificador Visual

        self.selected_slot = tk.IntVar(value=1)

        self.blueprint_items = self._ensure_point_ids(self.load_blueprint())
        self.placement_anchor = None  # Posición en vivo del pozo central tras llegar a la Zona Segura

        self.canvas_width = 750

        self.canvas_height = 478

        self.map_img_tk = None



        # Cargar configuración existente

        self.config = self.load_config()



        # Construir Interfaz

        self.setup_ui()



        # Parada de emergencia global (F12)
        self.setup_hotkeys()
        self.last_placement_time = time.time()

        # Actualizador de UI en segundo plano

        self.update_ui_loop()



    def load_config(self):

        if os.path.exists(CONFIG_FILE):

            try:

                with open(CONFIG_FILE, "r") as f:

                    return json.load(f)

            except Exception:

                pass

        return {

            "resolution": {"width": 1366, "height": 768},

            "positions": {

                "farm_1": {"x": 301, "y": 683},

                "farm_2": {"x": 352, "y": 680},

                "farm_3": {"x": 404, "y": 679},

                "farm_4": {"x": 472, "y": 680},

                "titan_1": {"x": 683, "y": 380},

                "titan_2": {"x": 600, "y": 380},

                "autoskip_button": {"x": 461, "y": 166},

                "close_manager_button": {"x": 683, "y": 520},

                "play_again_button": {"x": 683, "y": 500}

            }

        }



    def load_blueprint(self):

        if os.path.exists(BLUEPRINT_FILE):

            try:

                with open(BLUEPRINT_FILE, "r") as f:

                    return json.load(f)

            except Exception:

                pass

        return []



    def _ensure_point_ids(self, items):
        """
        Garantiza que cada unidad del plano use un Punto oficial del usuario (point_id).
        Planos antiguos/sin point_id se ajustan al punto oficial libre más cercano.
        """
        try:
            from placement_points import nearest_point_id
            cfg = self.vision.get_placement_config()
            valid_ids = {int(p["id"]) for p in cfg["points"]}
            by_id = {int(p["id"]): p for p in cfg["points"]}
            used = set()
            for it in items:
                pid = it.get("point_id")
                if pid is not None and int(pid) in valid_ids and int(pid) not in used:
                    it["point_id"] = int(pid)
                else:
                    pid = nearest_point_id(it.get("game_x", 683), it.get("game_y", 384), cfg, exclude=used)
                    it["point_id"] = pid
                if it["point_id"] is not None:
                    used.add(it["point_id"])
                    p = by_id[it["point_id"]]
                    if p.get("map"):
                        it["game_x"], it["game_y"] = int(p["map"][0]), int(p["map"][1])
                        it["canvas_x"] = int(round(p["map"][0] * 750 / 1366.0))
                        it["canvas_y"] = int(round(p["map"][1] * 478 / 768.0))
        except Exception:
            pass
        return items

    def save_blueprint(self):

        with open(BLUEPRINT_FILE, "w") as f:

            json.dump(self.blueprint_items, f, indent=4)

        if hasattr(self, "lbl_blueprint_status"):

            self.lbl_blueprint_status.configure(text=f"Tropas en Plano: {len(self.blueprint_items)}")



    def setup_ui(self):

        self.grid_columnconfigure(0, weight=1)

        self.grid_rowconfigure(0, weight=0)

        self.grid_rowconfigure(1, weight=1)



        # --- HEADER ---

        header_frame = ctk.CTkFrame(self, corner_radius=10, fg_color="#1a1c23")

        header_frame.grid(row=0, column=0, padx=15, pady=8, sticky="ew")



        title_label = ctk.CTkLabel(

            header_frame, 

            text="🛡️ TTD AGENT PANEL & VISUAL BLUEPRINT", 

            font=ctk.CTkFont(size=20, weight="bold"),

            text_color="#00d2ff"

        )

        title_label.pack(side="left", padx=15, pady=10)



        self.status_badge = ctk.CTkLabel(

            header_frame,

            text="● DETENIDO",

            font=ctk.CTkFont(size=14, weight="bold"),

            text_color="#ff4757",

            fg_color="#2f3542",

            corner_radius=8,

            padx=12,

            pady=4

        )

        self.status_badge.pack(side="right", padx=15, pady=10)



        # --- PESTAÑAS (TABVIEW) ---

        self.tabview = ctk.CTkTabview(self, corner_radius=10)

        self.tabview.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="nsew")



        self.tab_dashboard = self.tabview.add("🎮 Panel de Control")

        self.tab_blueprint = self.tabview.add("🗺️ Planificador Visual de Mapa")



        self.setup_dashboard_tab()

        self.setup_blueprint_tab()



    # =====================================================================

    # PESTAÑA 1: DASHBOARD

    # =====================================================================

    def setup_dashboard_tab(self):

        tab = self.tab_dashboard

        tab.grid_columnconfigure(0, weight=1)

        tab.grid_columnconfigure(1, weight=1)

        tab.grid_rowconfigure(0, weight=1)



        # COLUMNA IZQUIERDA

        left_frame = ctk.CTkFrame(tab, corner_radius=10)

        left_frame.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")



        self.btn_toggle = ctk.CTkButton(

            left_frame,

            text="▶ INICIAR AGENTE (BUCLE INFINITO)",

            font=ctk.CTkFont(size=15, weight="bold"),

            fg_color="#2ed573",

            hover_color="#26af5f",

            height=45,

            command=self.toggle_agent

        )

        self.btn_toggle.pack(fill="x", padx=15, pady=(15, 6))

        self.btn_open_gym = ctk.CTkButton(
            left_frame,
            text="🧬 ABRIR GYM & ENTRENADOR IA (DEAP + OPTUNA)",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#8e44ad",
            hover_color="#732d91",
            height=38,
            command=self.open_gym_window
        )
        self.btn_open_gym.pack(fill="x", padx=15, pady=(0, 8))



        # Tarjeta: Bloc de Notas en Memoria (Scratchpad)

        mem_card = ctk.CTkFrame(left_frame, fg_color="#1e222d", corner_radius=8)

        mem_card.pack(fill="x", padx=15, pady=10)



        ctk.CTkLabel(mem_card, text="🧠 BLOC DE NOTAS EN MEMORIA", font=ctk.CTkFont(size=13, weight="bold"), text_color="#70a1ff").pack(anchor="w", padx=12, pady=(10, 4))

        

        self.lbl_match = ctk.CTkLabel(mem_card, text="Partida actual: #0", font=ctk.CTkFont(size=12))

        self.lbl_match.pack(anchor="w", padx=15, pady=2)



        self.lbl_objective = ctk.CTkLabel(mem_card, text="Objetivo: Ninguno", font=ctk.CTkFont(size=12, weight="bold"), text_color="#ffa502")

        self.lbl_objective.pack(anchor="w", padx=15, pady=2)



        self.lbl_money = ctk.CTkLabel(mem_card, text="Dinero detectado: Leyendo...", font=ctk.CTkFont(size=12, weight="bold"), text_color="#2ed573")

        self.lbl_money.pack(anchor="w", padx=15, pady=2)



        self.lbl_time = ctk.CTkLabel(mem_card, text="Tiempo en partida: 0s", font=ctk.CTkFont(size=12))

        self.lbl_time.pack(anchor="w", padx=15, pady=2)



        self.lbl_blueprint_status = ctk.CTkLabel(mem_card, text=f"Tropas en Plano: {len(self.blueprint_items)}", font=ctk.CTkFont(size=12))

        self.lbl_blueprint_status.pack(anchor="w", padx=15, pady=(2, 10))



        # Herramientas de Prueba

        tools_card = ctk.CTkFrame(left_frame, fg_color="#1e222d", corner_radius=8)

        tools_card.pack(fill="x", padx=15, pady=10)



        ctk.CTkLabel(tools_card, text="🛠️ ACCIONES RÁPIDAS", font=ctk.CTkFont(size=12, weight="bold"), text_color="#a4b0be").pack(anchor="w", padx=12, pady=(8, 4))

        tool_btn_box = ctk.CTkFrame(tools_card, fg_color="transparent")

        tool_btn_box.pack(fill="x", padx=10, pady=(0, 10))



        ctk.CTkButton(tool_btn_box, text="Cámara Cenital", width=102, height=28, command=self.test_camera).pack(side="left", padx=3, pady=4)

        ctk.CTkButton(tool_btn_box, text="Offset ORB", width=92, height=28, command=self.test_orb_offset).pack(side="left", padx=3, pady=4)

        ctk.CTkButton(tool_btn_box, text="Centrar WASD", width=98, height=28, command=self.test_autocenter).pack(side="left", padx=3, pady=4)
        ctk.CTkButton(tool_btn_box, text="Probar Mejora", width=102, height=28, fg_color="#2ed573", hover_color="#26af5f", text_color="#000000", command=self.test_unit_manager).pack(side="left", padx=3, pady=4)
        ctk.CTkButton(tool_btn_box, text="Anti-AFK", width=72, height=28, command=self.controller.anti_afk_jiggle).pack(side="left", padx=3, pady=4)



        # COLUMNA DERECHA: REGISTRO DE ACCIONES

        right_frame = ctk.CTkFrame(tab, corner_radius=10)

        right_frame.grid(row=0, column=1, padx=(5, 10), pady=10, sticky="nsew")

        right_frame.grid_rowconfigure(1, weight=1)

        right_frame.grid_columnconfigure(0, weight=1)



        ctk.CTkLabel(right_frame, text="📜 REGISTRO DE ACCIONES EN TIEMPO REAL", font=ctk.CTkFont(size=12, weight="bold"), text_color="#dfe4ea").grid(row=0, column=0, sticky="w", padx=15, pady=(15, 6))



        self.log_textbox = ctk.CTkTextbox(right_frame, font=ctk.CTkFont(family="Consolas", size=11), fg_color="#111318")

        self.log_textbox.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="nsew")



    # =====================================================================

    # PESTAÑA 2: PLANIFICADOR VISUAL DE MAPA (BLUEPRINT)

    # =====================================================================

    def setup_blueprint_tab(self):

        tab = self.tab_blueprint

        tab.grid_columnconfigure(0, weight=3)

        tab.grid_columnconfigure(1, weight=1)

        tab.grid_rowconfigure(0, weight=1)



        # ÁREA DEL MAPA (CANVAS)

        map_frame = ctk.CTkFrame(tab, corner_radius=10, fg_color="#111318")

        map_frame.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")



        if os.path.exists(MAP_ASSET_PATH):

            pil_img = Image.open(MAP_ASSET_PATH)

            pil_img = pil_img.resize((self.canvas_width, self.canvas_height), Image.Resampling.LANCZOS)

            self.map_img_tk = ImageTk.PhotoImage(pil_img)

        else:

            self.map_img_tk = None



        self.canvas = tk.Canvas(

            map_frame, 

            width=self.canvas_width, 

            height=self.canvas_height, 

            bg="#111318", 

            highlightthickness=0

        )

        self.canvas.pack(padx=10, pady=10)



        if self.map_img_tk:

            self.canvas.create_image(0, 0, anchor="nw", image=self.map_img_tk)



        # Eventos del Canvas: Clic Izquierdo (Poner pin) y Clic Derecho (Borrar pin)

        self.canvas.bind("<Button-1>", self.on_map_click)

        self.canvas.bind("<Button-3>", self.on_map_right_click)



        # PANEL LATERAL DEL PLANIFICADOR

        side_frame = ctk.CTkFrame(tab, corner_radius=10)

        side_frame.grid(row=0, column=1, padx=(5, 10), pady=10, sticky="nsew")



        ctk.CTkLabel(side_frame, text="🎨 SELECCIÓN DE TROPA", font=ctk.CTkFont(size=14, weight="bold"), text_color="#00d2ff").pack(anchor="w", padx=15, pady=(15, 6))



        for slot_num, info in UNIT_PRESETS.items():

            rb = ctk.CTkRadioButton(

                side_frame,

                text=f"Slot {slot_num}: {info['name']} (${info['cost']})",

                variable=self.selected_slot,

                value=slot_num,

                font=ctk.CTkFont(size=12),

                fg_color=info['color'],

                border_color=info['color']

            )

            rb.pack(anchor="w", padx=15, pady=5)



        info_box = ctk.CTkFrame(side_frame, fg_color="#1e222d", corner_radius=6)

        info_box.pack(fill="x", padx=15, pady=(8, 12))

        ctk.CTkLabel(

            info_box, 

            text="🖱️ Clic Izquierdo: Poner pin\n❌ Clic Derecho sobre pin: Borrarlo", 

            font=ctk.CTkFont(size=11), 

            text_color="#ced6e0",

            justify="left"

        ).pack(padx=8, pady=6)



        # Botones de Guardar / Cargar Estrategias

        btn_save_as = ctk.CTkButton(

            side_frame, 

            text="💾 Guardar Estrategia Como...", 

            height=34, 

            fg_color="#2ed573", 

            hover_color="#26af5f", 

            font=ctk.CTkFont(weight="bold"), 

            command=self.save_strategy_as

        )

        btn_save_as.pack(fill="x", padx=15, pady=4)



        btn_load = ctk.CTkButton(

            side_frame, 

            text="📂 Cargar Estrategia...", 

            height=34, 

            fg_color="#3742fa", 

            hover_color="#2f3542", 

            font=ctk.CTkFont(weight="bold"), 

            command=self.load_strategy_dialog

        )

        btn_load.pack(fill="x", padx=15, pady=4)



        btn_undo = ctk.CTkButton(side_frame, text="↩️ Deshacer Último", height=30, fg_color="#57606f", command=self.undo_last_pin)

        btn_undo.pack(fill="x", padx=15, pady=4)



        btn_clear = ctk.CTkButton(side_frame, text="🗑️ Limpiar Todo", height=30, fg_color="#ff4757", hover_color="#c0392b", command=self.clear_blueprint)

        btn_clear.pack(fill="x", padx=15, pady=4)



        self.redraw_blueprint_pins()



    def _official_points(self):
        """Puntos oficiales del usuario (Puntos_de_unidades_Colocacion.png) en el marco del mapa del plano."""
        cfg = self.vision.get_placement_config()
        return [p for p in cfg["points"] if p.get("map")]

    def _point_to_canvas(self, p):
        return (int(round(p["map"][0] * self.canvas_width / 1366.0)),
                int(round(p["map"][1] * self.canvas_height / 768.0)))

    def on_map_click(self, event):
        """Solo se permite colocar sobre los puntos oficiales: el clic se ajusta al punto libre más cercano."""
        cx, cy = event.x, event.y
        slot = self.selected_slot.get()
        info = UNIT_PRESETS[slot]

        used = {it.get("point_id") for it in self.blueprint_items}
        best, best_d = None, None
        for p in self._official_points():
            if p["id"] in used:
                continue
            pcx, pcy = self._point_to_canvas(p)
            d = (pcx - cx) ** 2 + (pcy - cy) ** 2
            if best_d is None or d < best_d:
                best, best_d = p, d
        if best is None:
            self.log("⚠️ Todos los puntos oficiales ya están ocupados en el plano.")
            return

        pcx, pcy = self._point_to_canvas(best)
        item = {
            "id": len(self.blueprint_items) + 1,
            "slot": slot,
            "name": info["name"],
            "cost": info["cost"],
            "canvas_x": pcx,
            "canvas_y": pcy,
            "game_x": int(best["map"][0]),
            "game_y": int(best["map"][1]),
            "point_id": int(best["id"]),
        }

        self.blueprint_items.append(item)
        self.redraw_blueprint_pins()
        self.save_blueprint()
        self.log(f"Pin añadido: {info['name']} (Slot {slot}) en Punto oficial P{best['id']}")



    def on_map_right_click(self, event):

        """Elimina el pin que se encuentre bajo el cursor al hacer clic derecho"""

        cx, cy = event.x, event.y

        hit_idx = None

        for idx, item in enumerate(self.blueprint_items):

            dist = ((item["canvas_x"] - cx)**2 + (item["canvas_y"] - cy)**2)**0.5

            if dist <= 16:

                hit_idx = idx

                break



        if hit_idx is not None:

            removed = self.blueprint_items.pop(hit_idx)

            self.redraw_blueprint_pins()

            self.save_blueprint()

            self.log(f"✔ Pin eliminado con clic derecho: {removed['name']} (Slot {removed['slot']})")



    def undo_last_pin(self):

        if self.blueprint_items:

            removed = self.blueprint_items.pop()

            self.redraw_blueprint_pins()

            self.save_blueprint()

            self.log(f"Eliminado último pin: {removed['name']}")



    def clear_blueprint(self):

        self.blueprint_items = []

        self.redraw_blueprint_pins()

        self.save_blueprint()

        self.log("Plano de tropas vaciado.")



    def save_strategy_as(self):

        filename = filedialog.asksaveasfilename(

            initialdir=STRATEGIES_DIR,

            title="Guardar Estrategia Como...",

            defaultextension=".json",

            filetypes=[("Estrategia TTD (*.json)", "*.json")]

        )

        if filename:

            with open(filename, "w") as f:

                json.dump(self.blueprint_items, f, indent=4)

            with open(BLUEPRINT_FILE, "w") as f:

                json.dump(self.blueprint_items, f, indent=4)

            name = os.path.basename(filename)

            self.log(f"Estrategia guardada como '{name}' en carpeta strategies.")

            messagebox.showinfo("Estrategia Guardada", f"La estrategia se guardó con éxito en:\n{filename}")



    def load_strategy_dialog(self):

        filename = filedialog.askopenfilename(

            initialdir=STRATEGIES_DIR,

            title="Cargar Estrategia...",

            filetypes=[("Estrategia TTD (*.json)", "*.json")]

        )

        if filename and os.path.exists(filename):

            try:

                with open(filename, "r") as f:

                    self.blueprint_items = self._ensure_point_ids(json.load(f))

                self.redraw_blueprint_pins()

                with open(BLUEPRINT_FILE, "w") as f:

                    json.dump(self.blueprint_items, f, indent=4)

                name = os.path.basename(filename)

                self.log(f"Estrategia '{name}' cargada con {len(self.blueprint_items)} tropas.")

                messagebox.showinfo("Estrategia Cargada", f"Se cargó '{name}' con éxito.")

            except Exception as e:

                messagebox.showerror("Error", f"No se pudo cargar el archivo:\n{e}")



    def redraw_blueprint_pins(self):

        self.canvas.delete("pin")

        # Puntos oficiales del usuario (únicos lugares permitidos)
        try:
            for p in self._official_points():
                pcx, pcy = self._point_to_canvas(p)
                self.canvas.create_oval(pcx - 7, pcy - 7, pcx + 7, pcy + 7,
                                        outline="#7bed9f", width=2, dash=(2, 2), tags="pin")
                self.canvas.create_text(pcx + 13, pcy - 10, text=f"P{p['id']}",
                                        fill="#7bed9f", font=("Arial", 8, "bold"), tags="pin")
        except Exception:
            pass

        for idx, item in enumerate(self.blueprint_items):

            cx, cy = item["canvas_x"], item["canvas_y"]

            slot = item["slot"]

            info = UNIT_PRESETS.get(slot, UNIT_PRESETS[1])



            r = 13

            self.canvas.create_oval(

                cx - r, cy - r, cx + r, cy + r,

                fill=info["color"], outline="#ffffff", width=2, tags="pin"

            )

            self.canvas.create_text(

                cx, cy, text=str(slot),

                fill=info["text_color"], font=("Arial", 10, "bold"), tags="pin"

            )



        if hasattr(self, "lbl_blueprint_status"):

            self.lbl_blueprint_status.configure(text=f"Tropas en Plano: {len(self.blueprint_items)}")



    def log(self, text: str):
        timestamp = time.strftime("%H:%M:%S")
        self.after(0, lambda: self._append_log(timestamp, text))

    def _append_log(self, timestamp: str, text: str):
        if hasattr(self, "log_textbox") and self.log_textbox.winfo_exists():
            self.log_textbox.insert("end", f"[{timestamp}] {text}\n")
            self.log_textbox.see("end")

    def setup_hotkeys(self):
        try:
            keyboard.add_hotkey("f12", self.emergency_stop)
        except Exception:
            pass

    def emergency_stop(self):
        if self.is_running:
            self.is_running = False
            self.status_badge.configure(text="● DETENIDO (F12)", text_color="#ff4757")
            self.btn_toggle.configure(text="▶ INICIAR AGENTE (BUCLE INFINITO)", fg_color="#2ed573", hover_color="#26af5f")
            self.current_objective = "DETENIDO"
            self.log("🛑 ¡PARADA DE EMERGENCIA (F12) ACTIVADA! Agente detenido inmediatamente.")

    def open_gym_window(self):
        try:
            from gym_ui import TTDGymWindow
            if hasattr(self, "_gym_win") and self._gym_win is not None and self._gym_win.winfo_exists():
                self._gym_win.focus()
                self._gym_win.lift()
                return
            self._gym_win = TTDGymWindow(master=self, on_blueprint_exported=self._on_gym_blueprint_exported)
            self.log("🧬 Ventana GYM (Endless Mode | DEAP + Optuna) abierta.")
        except Exception as e:
            messagebox.showerror("Error al abrir GYM", f"No se pudo abrir la interfaz del GYM:\n{e}")

    def _on_gym_blueprint_exported(self, new_blueprint):
        self.blueprint_items = self._ensure_point_ids(self.load_blueprint())
        self.redraw_blueprint_pins()
        self.log(f"🏆 ¡Estrategia Campeona del GYM cargada en el Bot ({len(self.blueprint_items)} unidades)!")

    def test_camera(self):

        self.log("Probando ajuste de cámara en 3 segundos... ¡Cambia a Roblox!")

        threading.Thread(target=self._run_test_camera, daemon=True).start()



    def _run_test_camera(self):

        time.sleep(3)

        self.controller.calibrate_camera()

        self.log("Ajuste de cámara cenital ejecutado.")





    def test_orb_offset(self):

        self.log("Calculando desplazamiento del mapa (ORB) en 2 segundos... ¡Cambia a Roblox!")

        threading.Thread(target=self._run_test_orb, daemon=True).start()



    def _run_test_orb(self):

        time.sleep(2)

        dx, dy = self.vision.get_map_offset()

        self.log(f"🎯 Offset ORB detectado en vivo: dx={dx}px, dy={dy}px")

        if dx == 0 and dy == 0:

            self.log("ℹ️ Desfase 0 o no se detectó cambio respecto al mapa base.")

        else:

            self.log(f"✅ ¡Mapa registrado con éxito! Desfase calculado: dx={dx}px, dy={dy}px")



    def test_autocenter(self):

        self.log("Probando centrado automático WASD en 3 segundos... ¡Cambia a Roblox!")

        threading.Thread(target=self._run_test_autocenter, daemon=True).start()



    def _run_test_autocenter(self):
        time.sleep(3)
        self.auto_center_character(max_steps=12, require_running=False)
        self.log("Prueba de centrado WASD completada.")

    def test_unit_manager(self):
        self.log("Probando Gerente de Unidad + botón 'Mejora' en 3 segundos... ¡Cambia a Roblox!")
        threading.Thread(target=self._run_test_unit_manager, daemon=True).start()

    def _run_test_unit_manager(self):
        time.sleep(3)
        money = self.vision.read_money()
        self.run_unit_manager_upgrades(money=money, max_clicks=None, require_running=False)

    def run_unit_manager_upgrades(self, money: int = -1, max_clicks=None, require_running: bool = True) -> int:
        """
        Flujo verificado del Gerente de Unidad:
        1. Cancela cualquier fantasma de colocación ('X') y localiza el libro azul 'Unidades'.
        2. Abre el Gerente de Unidad y verifica con visión que realmente se abrió (reintenta si no abrió).
        3. Detecta todos los botones verdes 'Mejora' (validando el botón rojo 'Vender' a su derecha) y hace clic.
        4. Cierra el Gerente de Unidad alternando el libro azul y verifica que haya quedado cerrado.
        """
        if require_running and not self.is_running:
            return 0

        self.controller.cancel_placement()
        book_pt = self.vision.find_book_icon()
        if not book_pt:
            self.log("⚠️ No se detectó el icono azul 'Unidades' en pantalla para abrir el Gerente.")
            return 0

        # 1. Abrir el Gerente de Unidad si aún no está abierto
        if not self.vision.is_unit_manager_open():
            self.controller.click_at(book_pt[0], book_pt[1], delay=0.35)
            time.sleep(0.25)
            if not self.vision.is_unit_manager_open():
                # Reintento por si Roblox ignoró el primer clic
                self.controller.click_at(book_pt[0], book_pt[1], delay=0.35)
                time.sleep(0.25)

        total_clicked = 0
        passes = 2 if (max_clicks is None and (money < 0 or money >= 800)) else 1

        for p_idx in range(passes):
            if require_running and not self.is_running:
                break
            upgrades = self.vision.find_all_upgrade_buttons()
            if not upgrades:
                if p_idx == 0:
                    self.log(f"ℹ️ Gerente de Unidad abierto en ({book_pt[0]}, {book_pt[1]}), sin botones verdes 'Mejora' visibles.")
                break

            target_list = upgrades[:max_clicks] if max_clicks is not None else upgrades
            for u in target_list:
                if require_running and not self.is_running:
                    break
                self.controller.click_at(u["x"], u["y"], delay=0.18)
                total_clicked += 1

            if max_clicks is not None or len(upgrades) == 0:
                break
            time.sleep(0.15)

        if total_clicked > 0:
            self.log(f"⬆️ Gerente de Unidad: {total_clicked} clic(s) en botones verdes 'Mejora' (Dinero: ${money}).")
            time.sleep(0.15)

        # 2. Cerrar el Gerente de Unidad haciendo clic nuevamente en el libro azul
        self.controller.click_at(book_pt[0], book_pt[1], delay=0.25)
        time.sleep(0.20)
        if self.vision.is_unit_manager_open():
            self.controller.click_at(book_pt[0], book_pt[1], delay=0.25)

        return total_clicked

    def auto_center_character(self, max_steps: int = 16, require_running: bool = True):
        """
        Camina con WASD hasta la Zona Segura (mancha violeta de 'Zona Segura.png').
        La meta es que el pozo central de lava se vea en pantalla exactamente donde estaba
        en 'Puntos_de_unidades_Colocacion.png' (captura tomada con el personaje en la Zona Segura).
        Al terminar guarda self.placement_anchor (pozo en vivo) para proyectar los puntos oficiales.
        """
        self.log("🧭 Caminando hacia la Zona Segura (violeta) junto al pozo central de lava...")
        self.placement_anchor = None
        target_x, target_y = self.vision.get_base_map_lava_target()
        tolerance = 14  # Píxeles de margen aceptable
        last_pt = None

        for step in range(max_steps):
            if require_running and not self.is_running:
                break

            pt = self.vision.find_reference_landmark(save_debug=(step == 0))
            if not pt:
                self.log("⚠️ No se detectó el pozo central de lava en este ángulo.")
                break
            last_pt = pt

            px, py = pt
            dx = px - target_x
            dy = py - target_y

            self.log(f"Paso {step+1}: Pozo central en ({px}, {py}) vs Meta ({target_x}, {target_y}) | Error: dx={dx}px, dy={dy}px")

            if abs(dx) <= tolerance and abs(dy) <= tolerance:
                break

            # Duración de caminata proporcional a la distancia en píxeles (entre 0.05s y 0.40s)
            if abs(dx) > tolerance:
                dur_x = max(0.05, min(0.40, abs(dx) / 450.0))
                # Pozo a la derecha de la meta -> caminar a la derecha ('d'); si no, a la izquierda ('a')
                self.controller.walk('d' if dx > 0 else 'a', duration=dur_x)

            if abs(dy) > tolerance:
                dur_y = max(0.05, min(0.40, abs(dy) / 450.0))
                # Pozo debajo de la meta -> caminar hacia abajo ('s'); si no, hacia arriba ('w')
                self.controller.walk('s' if dy > 0 else 'w', duration=dur_y)

            time.sleep(0.15)

        # Lectura final estable del ancla (pozo central) al inicio de la partida (sin unidades ni auras brillantes)
        time.sleep(0.2)
        final_pt = self.vision.find_reference_landmark(save_debug=True) or last_pt
        if final_pt and abs(final_pt[0] - target_x) <= 60 and abs(final_pt[1] - target_y) <= 60:
            self.placement_anchor = final_pt
            inside, dist = self.vision.get_safe_zone_status(final_pt)
            if inside:
                self.log(f"✅ ¡Personaje en la ZONA SEGURA! (ancla pozo fijada en {final_pt}, dist={dist:.0f}px)")
            else:
                self.log(f"⚠️ Personaje cerca de Zona Segura ({dist:.0f}px). Ancla pozo fijada en {final_pt}.")
        else:
            self.placement_anchor = (target_x, target_y)
            self.log(f"🔒 Ancla de colocación fijada en la meta de Zona Segura {(target_x, target_y)}.")
        return self.placement_anchor

    def wait_for_loading_screen(self, timeout=60):

        """Espera de forma inteligente hasta que la pantalla de carga termine y el mapa esté listo"""

        self.log("Esperando fin de pantalla de carga (detectando llegada a la partida)...")

        time.sleep(4)  # Espera mínima de la cuenta regresiva 3.. 2.. 1..

        start_wait = time.time()

        while time.time() - start_wait < timeout and self.is_running:

            if self.vision.is_in_game():

                self.log("✔ ¡Pantalla de carga superada! El mapa y la interfaz están listos.")

                time.sleep(1.5)

                return True

            time.sleep(0.6)

        return False



    def toggle_agent(self):

        if not self.is_running:

            pos = self.config.get("positions", {})

            self.is_running = True

            self.status_badge.configure(text="● EN EJECUCIÓN", text_color="#2ed573")

            self.btn_toggle.configure(text="⏹ DETENER AGENTE", fg_color="#ff4757", hover_color="#d63031")

            self.log("Iniciando Agente Replicador... Cambia a Roblox.")

            self.bot_thread = threading.Thread(target=self._agent_loop, daemon=True)

            self.bot_thread.start()

        else:

            self.is_running = False

            self.status_badge.configure(text="● DETENIDO", text_color="#ff4757")

            self.btn_toggle.configure(text="▶ INICIAR AGENTE (BUCLE INFINITO)", fg_color="#2ed573", hover_color="#26af5f")

            self.current_objective = "DETENIDO"

            self.log("Agente detenido por el usuario.")



    def _agent_loop(self):

        for i in range(5, 0, -1):

            if not self.is_running:

                return

            self.log(f"Arrancando en {i}s...")

            time.sleep(1)



        pos = self.config["positions"]

        while self.is_running:

            self.match_count += 1

            self.match_start_time = time.time()

            self.log(f"=== INICIANDO PARTIDA #{self.match_count} ===")



# 1. Calibrar Cámara Cenital
            self.current_objective = "CALIBRAR CÁMARA"
            self.controller.calibrate_camera()
            time.sleep(0.8)

            # 1.5 Caminar con WASD hacia la Zona Segura (mancha violeta en Zona Segura.png)
            self.current_objective = "CAMINANDO A ZONA SEGURA (WASD)"
            self.auto_center_character(max_steps=16)
            time.sleep(0.5)



            # 3. Auto-Skip Inteligente: Garantizar que 'Saltar automáticamente' esté en VERDE
            self.current_objective = "VERIFICAR AUTO-SKIP"
            red_skip_pt = self.vision.find_autoskip_red_button()
            if red_skip_pt:
                self.controller.click_at(red_skip_pt[0], red_skip_pt[1], delay=0.25)
                self.log(f"Auto-Skip detectado en ROJO -> Clic en ({red_skip_pt[0]}, {red_skip_pt[1]}) para ponerlo en VERDE.")
            elif pos.get("autoskip_button") and self.vision.is_autoskip_red(pos["autoskip_button"]["x"], pos["autoskip_button"]["y"]):
                ax, ay = pos["autoskip_button"]["x"], pos["autoskip_button"]["y"]
                self.controller.click_at(ax, ay, delay=0.25)
                self.log(f"Auto-Skip (config) en ROJO -> Clic en ({ax}, {ay}) para ponerlo en VERDE.")
            else:
                self.log("Auto-Skip ya está en VERDE (oleadas rápidas activas).")
            time.sleep(0.5)

            # 4. Réplica del Plano Visual (recargar los 19 puntos oficiales y el plano actualizado)
            self.vision.reload_placement_config()
            self.blueprint_items = self._ensure_point_ids(self.load_blueprint())
            pending_units = [dict(item) for item in self.blueprint_items]
            total_blueprint_units = len(pending_units)
            last_mid_upgrade_time = time.time()

            self.current_objective = "EJECUTANDO PLANO DE TROPAS"
            match_loop_start = time.time()

            while self.is_running:
                if not self.controller.is_roblox_active():
                    self.log("⚠️ Roblox no está en primer plano. Esperando foco para interactuar...")
                    time.sleep(2.0)
                    continue

                elapsed = time.time() - match_loop_start

                # A0. Vigilancia continua: si el botón 'Saltar automáticamente' está en ROJO, pasarlo a VERDE inmediatamente
                red_skip_pt = self.vision.find_autoskip_red_button()
                if red_skip_pt:
                    self.controller.click_at(red_skip_pt[0], red_skip_pt[1], delay=0.2)
                    self.log(f"⚡ Auto-Skip estaba en ROJO -> Activado a VERDE en ({red_skip_pt[0]}, {red_skip_pt[1]}).")

                # A. Leer Dinero actual con OCR
                money = self.vision.read_money()
                if money >= 0:
                    self.current_money = money

                # B. Colocar tropas pendientes SOLO cuando el dinero leído alcanza realmente
                if pending_units:
                    next_unit = pending_units[0]
                    placed_so_far = total_blueprint_units - len(pending_units)

                    # Solo permitir colocación sin OCR para la PRIMERA granja al inicio de la partida (cuando empiezas con $200)
                    is_first_starter_farm = (len(pending_units) == total_blueprint_units and next_unit["cost"] <= 200 and elapsed < 12)
                    time_since_last_place = time.time() - getattr(self, "last_placement_time", match_loop_start)
                    # Fallback si OCR no detecta dinero o si Tesseract no está presente: colocar tras espera económica
                    can_place = (money >= next_unit["cost"]) or (money == -1 and (is_first_starter_farm or time_since_last_place > 22.0))

                    if can_place:
                        # Usar EXCLUSIVAMENTE los 19 puntos oficiales del usuario con el ancla fijada en el inicio
                        # (NO recalcular el pozo en medio del combate porque el aura dorada del Warlord altera el color de la lava)
                        pid = next_unit.get("point_id")
                        if pid is None:
                            from placement_points import nearest_point_id
                            pid = nearest_point_id(next_unit.get("game_x", 640), next_unit.get("game_y", 360))
                        pt_screen = self.vision.get_placement_point_screen(pid, anchor_pool=self.placement_anchor)
                        if pt_screen:
                            safe_x, safe_y = pt_screen
                        else:
                            safe_x, safe_y = int(next_unit.get("game_x", 640)), int(next_unit.get("game_y", 360))

                        self.log(f"Intentando colocar {next_unit['name']} (Slot {next_unit['slot']}) en Punto Oficial P{pid} -> ({safe_x}, {safe_y}) con R+CLICK | Dinero: ${money} / Costo: ${next_unit['cost']}")
                        placed_ok, new_money, attempts = self.controller.place_unit(
                            next_unit["slot"],
                            safe_x,
                            safe_y,
                            auto_scale=True,
                            read_money_fn=self.vision.read_money,
                            initial_money=money,
                            max_r_clicks=6,
                            is_running_fn=lambda: self.is_running,
                        )

                        if placed_ok:
                            self.log(f"✅ {next_unit['name']} (Slot {next_unit['slot']}) colocada en P{pid} ({safe_x}, {safe_y}) en {attempts}x R+CLICK | Dinero: ${money} -> ${new_money}")
                            self.last_placement_time = time.time()
                            self.current_money = new_money if new_money >= 0 else max(0, self.current_money - next_unit["cost"])
                            pending_units.pop(0)
                            time.sleep(0.8)
                        else:
                            next_unit["_fails"] = next_unit.get("_fails", 0) + 1
                            if next_unit["_fails"] >= 3:
                                self.log(f"⚠️ {next_unit['name']} en P{pid} falló 3 ciclos seguidos (posible límite o punto ocupado). Avanzando a la siguiente unidad...")
                                pending_units.pop(0)
                            else:
                                self.log(f"⏳ {next_unit['name']} en P{pid} ({safe_x}, {safe_y}): el dinero no disminuyó tras {attempts}x R+CLICK (Intento {next_unit['_fails']}/3). Reintentando...")
                            time.sleep(0.5)
                    else:
                        # Mientras ahorramos para una unidad cara (>= $1000) y ya tenemos al menos 2 granjas en pista,
                        # abrir periódicamente el Gerente de Unidad para mejorar las granjas ($200) y acelerar los ingresos.
                        if (
                            placed_so_far >= 2
                            and next_unit["cost"] >= 1000
                            and 200 <= money < (next_unit["cost"] - 150)
                            and (time.time() - last_mid_upgrade_time) >= 18.0
                        ):
                            self.current_objective = f"MEJORANDO GRANJAS (AHORRANDO ${next_unit['cost']})"
                            self.run_unit_manager_upgrades(money=money, max_clicks=2, require_running=True)
                            last_mid_upgrade_time = time.time()
                            self.current_objective = "EJECUTANDO PLANO DE TROPAS"

                # C. Si ya colocó todas las tropas -> MEJORAS CONTINUAS EN GERENTE DE UNIDAD
                else:
                    self.current_objective = "MEJORAS & COMBATE"
                    if money >= 200 or money <= 0:
                        self.run_unit_manager_upgrades(money=money, max_clicks=None, require_running=True)



                # D. Anti-AFK periódico (cada 2 minutos, no cada 2.5s)

                if int(elapsed) > 0 and int(elapsed) % 120 == 0:

                    self.controller.anti_afk_jiggle()



                # E. Detección Inteligente de Fin de Partida (Jugar de nuevo)

                if elapsed > 15:

                    replay_pt = self.vision.find_replay_button()

                    if replay_pt:

                        self.log("¡Fin de partida detectado (Derrota/Victoria)! Clic en 'Jugar de nuevo'.")

                        self.controller.click_at(replay_pt[0], replay_pt[1], delay=0.5)

                        

                        # Esperar a que la cuenta regresiva y pantalla de carga terminen

                        self.wait_for_loading_screen()

                        break



                if elapsed > 1320:

                    self.log("Partida finalizada por tiempo máximo.")

                    break



                time.sleep(2.5)



    def update_ui_loop(self):

        self.lbl_match.configure(text=f"Partida actual: #{self.match_count}")

        self.lbl_objective.configure(text=f"Objetivo: {self.current_objective}")

        money_str = f"${self.current_money}" if self.current_money >= 0 else "Leyendo..."

        self.lbl_money.configure(text=f"Dinero detectado: {money_str}")



        if self.is_running and self.match_start_time > 0:

            elapsed = int(time.time() - self.match_start_time)

            self.lbl_time.configure(text=f"Tiempo en partida: {elapsed}s")

        else:

            self.lbl_time.configure(text="Tiempo en partida: 0s")



        self.after(500, self.update_ui_loop)



if __name__ == "__main__":

    app = TTDGuiApp()

    app.mainloop()

