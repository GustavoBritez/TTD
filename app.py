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



from controller import GameController

from vision import VisionSystem



CONFIG_FILE = "config.json"

BLUEPRINT_FILE = "blueprint.json"

STRATEGIES_DIR = os.path.join(os.path.dirname(__file__), "strategies")

MAP_ASSET_PATH = os.path.join(os.path.dirname(__file__), "assets", "map_endless.jpg")



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

        self.blueprint_items = self.load_blueprint()

        self.canvas_width = 750

        self.canvas_height = 478

        self.map_img_tk = None



        # Cargar configuración existente

        self.config = self.load_config()



        # Construir Interfaz

        self.setup_ui()



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

        self.btn_toggle.pack(fill="x", padx=15, pady=(15, 10))



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



        ctk.CTkButton(tool_btn_box, text="Cámara Cenital", width=110, height=28, command=self.test_camera).pack(side="left", padx=3, pady=4)

        ctk.CTkButton(tool_btn_box, text="Probar Offset ORB", width=120, height=28, command=self.test_orb_offset).pack(side="left", padx=3, pady=4)

        ctk.CTkButton(tool_btn_box, text="Centrar WASD", width=100, height=28, command=self.test_autocenter).pack(side="left", padx=3, pady=4)
        ctk.CTkButton(tool_btn_box, text="Anti-AFK", width=80, height=28, command=self.controller.anti_afk_jiggle).pack(side="left", padx=3, pady=4)



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



    def on_map_click(self, event):

        cx, cy = event.x, event.y

        slot = self.selected_slot.get()

        info = UNIT_PRESETS[slot]



        game_x = int(cx * (1366 / self.canvas_width))

        game_y = int(cy * (768 / self.canvas_height))



        item = {

            "id": len(self.blueprint_items) + 1,

            "slot": slot,

            "name": info["name"],

            "cost": info["cost"],

            "canvas_x": cx,

            "canvas_y": cy,

            "game_x": game_x,

            "game_y": game_y

        }

        self.blueprint_items.append(item)

        self.redraw_blueprint_pins()

        self.save_blueprint()

        self.log(f"Pin añadido: {info['name']} (Slot {slot}) en ({cx}, {cy})")



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

                    self.blueprint_items = json.load(f)

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

        if hasattr(self, "log_textbox"):

            self.log_textbox.insert("end", f"[{timestamp}] {text}\n")

            self.log_textbox.see("end")



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

        self.auto_center_character()

        self.log("Prueba de centrado WASD completada.")



    def auto_center_character(self, max_steps: int = 12):
        self.log("🧭 Centrando personaje hacia la zona central de lava con WASD...")
        target_x, target_y = self.vision.get_base_map_lava_target()
        tolerance = 18  # Píxeles de margen aceptable

        for step in range(max_steps):
            if not self.is_running and not threading.current_thread().name.startswith("Thread"):
                break

            pt = self.vision.find_reference_landmark()
            if not pt:
                self.log("⚠️ No se detectó la lava central en este ángulo.")
                break

            px, py = pt
            dx = px - target_x
            dy = py - target_y

            self.log(f"Paso {step+1}: Lava en ({px}, {py}) vs Meta ({target_x}, {target_y}) | Error: dx={dx}px, dy={dy}px")

            if abs(dx) <= tolerance and abs(dy) <= tolerance:
                self.log("✅ ¡Personaje alineado en el centro del mapa!")
                break

            # Duración de caminata proporcional a la distancia en píxeles (entre 0.06s y 0.28s)
            if abs(dx) > tolerance:
                dur_x = max(0.06, min(0.28, abs(dx) / 450.0))
                if dx > tolerance:
                    # La lava está a la derecha -> caminar a la derecha ('d')
                    self.controller.walk('d', duration=dur_x)
                else:
                    # La lava está a la izquierda -> caminar a la izquierda ('a')
                    self.controller.walk('a', duration=dur_x)

            if abs(dy) > tolerance:
                dur_y = max(0.06, min(0.28, abs(dy) / 450.0))
                if dy > tolerance:
                    # La lava está abajo -> caminar hacia abajo ('s')
                    self.controller.walk('s', duration=dur_y)
                else:
                    # La lava está arriba -> caminar hacia arriba ('w')
                    self.controller.walk('w', duration=dur_y)

            time.sleep(0.15)

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

            # 1.5 ¡NUEVO! Caminar con WASD hacia el centro del mapa (Lava)
            self.current_objective = "CENTRANDO PERSONAJE (WASD)"
            self.auto_center_character(max_steps=10)
            time.sleep(0.5)

            # 2. Calcular Desfase residual con ORB (ya con el personaje en el centro)
            self.current_objective = "CALIBRANDO OFFSET FINO (ORB)"
            dx, dy = self.vision.get_map_offset()
            self.log(f"🎯 Offset fino post-WASD: dx={dx}px, dy={dy}px")
            time.sleep(0.5)



            # 3. Auto-Skip Inteligente: Detección automática por plantilla o configuración

            self.current_objective = "VERIFICAR AUTO-SKIP"

            skip_pt = self.vision.find_skip_button()

            if skip_pt:

                askip_x, askip_y = skip_pt

            elif pos.get("autoskip_button"):

                askip_x = pos["autoskip_button"]["x"]

                askip_y = pos["autoskip_button"]["y"]

            else:

                askip_x, askip_y = 785, 32



            if self.vision.is_autoskip_red(askip_x, askip_y):

                self.controller.click_at(askip_x, askip_y)

                self.log(f"Auto-Skip desactivado (rojo) -> Clic para activarlo en ({askip_x}, {askip_y}).")

            else:

                self.log("Auto-Skip ya estaba activado (verde). No se toca.")

            time.sleep(0.5)



            # 4. Réplica del Plano Visual (Blueprint)

            pending_units = [dict(item) for item in self.blueprint_items]



            self.current_objective = "EJECUTANDO PLANO DE TROPAS"

            match_loop_start = time.time()



            while self.is_running:

                elapsed = time.time() - match_loop_start



                # A. Leer Dinero actual con OCR

                money = self.vision.read_money()

                if money >= 0:

                    self.current_money = money



                # B. Colocar tropas pendientes SOLO cuando el dinero leído alcanza realmente

                if pending_units:

                    next_unit = pending_units[0]



                    # Solo permitir colocación sin OCR para la PRIMERA granja al inicio de la partida (cuando empiezas con $200)

                    is_first_starter_farm = (len(pending_units) == len(self.blueprint_items) and next_unit["cost"] <= 200 and elapsed < 12)

                    can_place = (money >= next_unit["cost"]) or (money == -1 and is_first_starter_farm)



                    if can_place:

                        target_x = max(30, min(1336, next_unit["game_x"] + dx))

                        target_y = max(30, min(738, next_unit["game_y"] + dy))

                        

                        # Solo ajustar a la orilla de la pista si es unidad de pelea (Slot 2, 3, 4)
                        # Las granjas (Slot 1) respetan su posición lejana en el Blueprint
                        if next_unit["slot"] != 1:
                            safe_x, safe_y = self.vision.snap_to_safe_strip(target_x, target_y)
                        else:
                            safe_x, safe_y = target_x, target_y

                        self.log(f"Colocando {next_unit['name']} (Slot {next_unit['slot']}) en ({safe_x}, {safe_y}) | Dinero: ${money} / Costo: ${next_unit['cost']}")
                        self.controller.place_unit(next_unit["slot"], safe_x, safe_y)
                        
                        # Si por algún motivo un obstáculo impidió el primer clic, intentar 2 micro-posiciones vecinas y limpiar selección
                        time.sleep(0.15)
                        self.controller.click_at(safe_x + 18, safe_y, delay=0.1)
                        self.controller.click_at(safe_x - 18, safe_y, delay=0.1)
                        self.controller.cancel_placement()

                        self.current_money = max(0, self.current_money - next_unit["cost"])
                        pending_units.pop(0)
                        time.sleep(1.2)



                # C. Si ya colocó todas las tropas o tiene dinero sobrante -> MEJORAS

                else:

                    self.current_objective = "MEJORAS & COMBATE"

                    if money >= 200 or money == 0:

                        book_pt = self.vision.find_book_icon()

                        if book_pt:

                            self.controller.click_at(book_pt[0], book_pt[1], delay=0.3)

                            time.sleep(0.2)



                            upgrade_pt = self.vision.find_upgrade_button()

                            if upgrade_pt:

                                self.controller.click_at(upgrade_pt[0], upgrade_pt[1], delay=0.2)

                                self.log(f"Mejora aplicada en Gerente de Unidad (Dinero: ${money})")

                                time.sleep(0.2)



                            close_pt = self.vision.find_close_button()

                            if close_pt:

                                self.controller.click_at(close_pt[0], close_pt[1], delay=0.2)

                            else:

                                self.controller.click_at(book_pt[0], book_pt[1], delay=0.2)



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

