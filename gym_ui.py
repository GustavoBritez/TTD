# -*- coding: utf-8 -*-
"""
Interfaz Gráfica Interactiva del GYM para Toilet Tower Defense (Modo Endless).
Permite:
  1. Entrenar Generación tras Generación usando DEAP (Algoritmo Genético) y Optuna (Bayesiano TPE)
     respetando los límites de inventario (4 Granjas, 4 Señor de la Guerra, 5 Z1MP, 4 Jefe Mafia = 17 máx).
  2. Darle al botón ▶ PLAY para ver en vivo sobre el mapa 'assets/map_endless.jpg' cómo el agente
     coloca y mejora las unidades mientras los inodoros y jefes avanzan por la pista extraída.
  3. Exportar la estrategia campeona con un clic a 'blueprint.json' para que el bot de mouse la ejecute en Roblox.
"""
import copy
import json
import math
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox
from typing import Dict, List, Optional

import customtkinter as ctk
from PIL import Image, ImageTk

ROOT = os.path.dirname(os.path.abspath(__file__))
GYM_DIR = os.path.join(ROOT, "gym")
if GYM_DIR not in sys.path:
    sys.path.insert(0, GYM_DIR)

from gym.optimize_blueprint import TTDOptimizerTrainer, create_random_genome, evaluate_genome
from gym.ttd_env import (
    ALL_CANDIDATE_SPOTS,
    COMBAT_SPOTS,
    DATA_DIR,
    FARM_SPOTS,
    MAX_BY_SLOT,
    MAP_PATH,
    STUDS_TO_PX,
    TRACK_WAYPOINTS,
    TTDEndlessGymEnv,
)

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

SLOT_STYLE = {
    1: {"name": "Casa de Jengibre (Granja)", "short": "Granja", "color": "#2ed573", "fg": "#ffffff", "max": 4},
    2: {"name": "Señor de la Guerra Titán (Shiny)", "short": "Warlord", "color": "#ffa502", "fg": "#000000", "max": 1},
    3: {"name": "Camarógrafo Z1MP (Shiny)", "short": "Z1MP", "color": "#1e90ff", "fg": "#ffffff", "max": 5},
    4: {"name": "Camarógrafo Jefe Mafia", "short": "Mafia", "color": "#9b59b6", "fg": "#ffffff", "max": 4},
}


class TTDGymWindow(ctk.CTkToplevel):
    """
    Ventana del Simulador Gymnasium & Entrenamiento Evolutivo (DEAP + Optuna).
    Puede abrirse como ventana independiente (`python gym_ui.py`) o desde un botón en `app.py`.
    """

    def __init__(self, master=None, on_blueprint_exported=None):
        super().__init__(master=master)
        self.title("🧬 TTD Endless Mode GYM | Entrenamiento DEAP + Optuna & Reproductor en Vivo")
        self.geometry("1260x820")
        self.minsize(1140, 740)
        self.on_blueprint_exported = on_blueprint_exported

        # Dimensiones del Canvas del Mapa (escalado proporcional de 1366x768)
        self.canvas_w = 820
        self.canvas_h = 461
        self.scale_x = self.canvas_w / 1366.0
        self.scale_y = self.canvas_h / 768.0

        # Entorno y Entrenador
        self.trainer = TTDOptimizerTrainer(max_waves=200, pop_size=28)
        self.play_env = TTDEndlessGymEnv(max_waves=200)

        # Estado de Entrenamiento y Reproducción (Play)
        self.is_training = False
        self.is_playing = False
        self.play_speed = tk.DoubleVar(value=2.0)
        self.show_ranges = tk.BooleanVar(value=True)
        self.show_track_nodes = tk.BooleanVar(value=True)
        self.engine_mode = tk.StringVar(value="hybrid")

        # Inicializar un primer genoma base para que el mapa tenga una estrategia lista desde el segundo 0
        init_genome = create_random_genome()
        w, dps, money, bp, placed = evaluate_genome(self.trainer.env, init_genome)
        self.trainer._update_champion(w, dps, money, init_genome, bp, placed, "Init")

        self.play_queue = []
        self.displayed_units: List[Dict] = copy.deepcopy(self.trainer.best_placed_units)

        self._build_ui()
        self._draw_static_map()
        self.redraw_dynamic_layer()

    def _game_to_canvas(self, gx: float, gy: float):
        return gx * self.scale_x, gy * self.scale_y

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)

        # --- BARRA SUPERIOR ---
        header = ctk.CTkFrame(self, corner_radius=10, fg_color="#161922")
        header.grid(row=0, column=0, columnspan=2, padx=12, pady=(10, 6), sticky="ew")

        ctk.CTkLabel(
            header,
            text="🧬 TTD ENDLESS MODE GYM — SIMULADOR DEAP + OPTUNA (ROBLOX DIGITAL TWIN)",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#00d2ff",
        ).pack(side="left", padx=15, pady=10)

        self.lbl_status = ctk.CTkLabel(
            header,
            text="● LISTO PARA ENTRENAR / PLAY",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#2ed573",
            fg_color="#252a38",
            corner_radius=8,
            padx=12,
            pady=4,
        )
        self.lbl_status.pack(side="right", padx=15, pady=10)

        # --- COLUMNA IZQUIERDA: MAPA INTERACTIVO + MÉTRICAS EN VIVO ---
        left_col = ctk.CTkFrame(self, corner_radius=10, fg_color="#12151e")
        left_col.grid(row=1, column=0, padx=(12, 6), pady=(0, 12), sticky="nsew")
        left_col.grid_rowconfigure(1, weight=0)
        left_col.grid_rowconfigure(2, weight=1)
        left_col.grid_columnconfigure(0, weight=1)

        # Barra de indicadores sobre el mapa
        hud_bar = ctk.CTkFrame(left_col, corner_radius=8, fg_color="#1c202e")
        hud_bar.grid(row=0, column=0, padx=10, pady=(10, 6), sticky="ew")

        self.lbl_gen = ctk.CTkLabel(hud_bar, text="Generación: #0", font=ctk.CTkFont(size=13, weight="bold"), text_color="#70a1ff")
        self.lbl_gen.pack(side="left", padx=12, pady=6)

        self.lbl_champ_wave = ctk.CTkLabel(
            hud_bar,
            text=f"🏆 Récord Campeón: Oleada {self.trainer.best_wave}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#ffa502",
        )
        self.lbl_champ_wave.pack(side="left", padx=12, pady=6)

        self.lbl_live_wave = ctk.CTkLabel(
            hud_bar,
            text="▶ Play: En espera",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#2ed573",
        )
        self.lbl_live_wave.pack(side="left", padx=12, pady=6)

        self.lbl_live_money = ctk.CTkLabel(
            hud_bar,
            text=f"💵 Dinero: ${self.trainer.best_money:,}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#2ed573",
        )
        self.lbl_live_money.pack(side="right", padx=12, pady=6)

        # Canvas del Mapa Endless Mode
        canvas_container = ctk.CTkFrame(left_col, corner_radius=8, fg_color="#0d0f15")
        canvas_container.grid(row=1, column=0, padx=10, pady=4)

        self.canvas = tk.Canvas(
            canvas_container,
            width=self.canvas_w,
            height=self.canvas_h,
            bg="#0d0f15",
            highlightthickness=1,
            highlightbackground="#2f3542",
        )
        self.canvas.pack(padx=4, pady=4)
        self.canvas.bind("<Button-3>", self.on_canvas_right_click)

        # Panel inferior izquierdo: Bitácora de Generaciones y Eventos de Simulación
        log_frame = ctk.CTkFrame(left_col, corner_radius=8, fg_color="#181c26")
        log_frame.grid(row=2, column=0, padx=10, pady=(4, 10), sticky="nsew")
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            log_frame,
            text="📈 HISTORIAL DE EVOLUCIÓN (DEAP + OPTUNA) & EVENTOS DE PARTIDA",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#a4b0be",
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(6, 2))

        self.txt_log = ctk.CTkTextbox(log_frame, font=ctk.CTkFont(family="Consolas", size=11), fg_color="#0f1118", height=140)
        self.txt_log.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="nsew")

        # --- COLUMNA DERECHA: CONTROLES DE ENTRENAMIENTO, PLAY Y LÍMITES DE UNIDADES ---
        right_col = ctk.CTkFrame(self, corner_radius=10, fg_color="#161922")
        right_col.grid(row=1, column=1, padx=(6, 12), pady=(0, 12), sticky="nsew")

        # 1. Tarjeta de Entrenamiento Evolutivo
        train_card = ctk.CTkFrame(right_col, corner_radius=8, fg_color="#1e222f")
        train_card.pack(fill="x", padx=12, pady=(12, 8))

        ctk.CTkLabel(
            train_card,
            text="🧬 1. ENTRENAR MODELO (GENERACIONES)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#00d2ff",
        ).pack(anchor="w", padx=12, pady=(10, 4))

        mode_row = ctk.CTkFrame(train_card, fg_color="transparent")
        mode_row.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(mode_row, text="Motor IA:", font=ctk.CTkFont(size=12)).pack(side="left")
        self.opt_engine = ctk.CTkOptionMenu(
            mode_row,
            values=["hybrid", "deap", "optuna"],
            variable=self.engine_mode,
            width=160,
            height=26,
        )
        self.opt_engine.pack(side="right")

        self.btn_train_loop = ctk.CTkButton(
            train_card,
            text="🧬 ENTRENAR GENERACIÓN TRAS GENERACIÓN",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#8e44ad",
            hover_color="#732d91",
            height=40,
            command=self.toggle_training,
        )
        self.btn_train_loop.pack(fill="x", padx=12, pady=(8, 5))

        self.btn_step_gen = ctk.CTkButton(
            train_card,
            text="⏭ AVANZAR +1 GENERACIÓN",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#3742fa",
            hover_color="#2f3542",
            height=32,
            command=self.run_single_generation,
        )
        self.btn_step_gen.pack(fill="x", padx=12, pady=(0, 10))

        # 2. Tarjeta de Reproducción Visual (Botón PLAY)
        play_card = ctk.CTkFrame(right_col, corner_radius=8, fg_color="#1e222f")
        play_card.pack(fill="x", padx=12, pady=8)

        ctk.CTkLabel(
            play_card,
            text="▶ 2. REPRODUCIR PARTIDA EN EL MAPA",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#2ed573",
        ).pack(anchor="w", padx=12, pady=(10, 4))

        self.btn_play = ctk.CTkButton(
            play_card,
            text="▶ PLAY (VER CAMPEÓN JUGAR EN VIVO)",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#2ed573",
            hover_color="#26af5f",
            text_color="#000000",
            height=44,
            command=self.toggle_play,
        )
        self.btn_play.pack(fill="x", padx=12, pady=(4, 8))

        spd_row = ctk.CTkFrame(play_card, fg_color="transparent")
        spd_row.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkLabel(spd_row, text="Velocidad Play:", font=ctk.CTkFont(size=12)).pack(side="left")
        for mult in (1.0, 2.0, 4.0, 8.0):
            ctk.CTkRadioButton(
                spd_row,
                text=f"{int(mult)}x",
                variable=self.play_speed,
                value=mult,
                width=42,
                font=ctk.CTkFont(size=11),
            ).pack(side="left", padx=4)

        chk_row = ctk.CTkFrame(play_card, fg_color="transparent")
        chk_row.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkCheckBox(
            chk_row,
            text="Mostrar Rangos",
            variable=self.show_ranges,
            font=ctk.CTkFont(size=11),
            command=self.redraw_dynamic_layer,
        ).pack(side="left", padx=(0, 10))
        ctk.CTkCheckBox(
            chk_row,
            text="Mostrar Pista y Nodos",
            variable=self.show_track_nodes,
            font=ctk.CTkFont(size=11),
            command=self.redraw_dynamic_layer,
        ).pack(side="left")

        # 3. Tarjeta de Límites de Inventario (14 Unidades Máximas)
        inv_card = ctk.CTkFrame(right_col, corner_radius=8, fg_color="#1e222f")
        inv_card.pack(fill="x", padx=12, pady=8)

        ctk.CTkLabel(
            inv_card,
            text="📦 LÍMITES DE UNIDADES EN MAPA (14 / 20 MÁX)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#ffa502",
        ).pack(anchor="w", padx=12, pady=(10, 6))

        self.slot_labels: Dict[int, ctk.CTkLabel] = {}
        for slot_id, st in SLOT_STYLE.items():
            row = ctk.CTkFrame(inv_card, fg_color="#141720", corner_radius=6)
            row.pack(fill="x", padx=12, pady=3)
            dot = ctk.CTkLabel(row, text="●", text_color=st["color"], font=ctk.CTkFont(size=16, weight="bold"))
            dot.pack(side="left", padx=(8, 4), pady=4)
            ctk.CTkLabel(row, text=f"S{slot_id}: {st['name']}", font=ctk.CTkFont(size=11)).pack(side="left", pady=4)
            lbl_cnt = ctk.CTkLabel(
                row,
                text=f"0 / {st['max']}",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=st["color"],
            )
            lbl_cnt.pack(side="right", padx=8, pady=4)
            self.slot_labels[slot_id] = lbl_cnt

        self.lbl_dps_summary = ctk.CTkLabel(
            inv_card,
            text=f"⚡ DPS Efectivo Campeón: {self.trainer.best_dps:,.0f}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#70a1ff",
        )
        self.lbl_dps_summary.pack(anchor="w", padx=12, pady=(6, 10))

        # 4. Exportación Sim-to-Real hacia el Bot de Mouse (blueprint.json)
        export_card = ctk.CTkFrame(right_col, corner_radius=8, fg_color="#1e222f")
        export_card.pack(fill="x", padx=12, pady=(8, 12))

        ctk.CTkLabel(
            export_card,
            text="🎯 3. PASAR ESTRATEGIA AL BOT DE ROBLOX",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#00d2ff",
        ).pack(anchor="w", padx=12, pady=(10, 4))

        self.btn_export = ctk.CTkButton(
            export_card,
            text="💾 APLICAR CAMPEÓN A BLUEPRINT.JSON",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#ffa502",
            hover_color="#e67e22",
            text_color="#000000",
            height=40,
            command=self.export_champion_to_bot,
        )
        self.btn_export.pack(fill="x", padx=12, pady=(4, 10))

        self.log(
            f"GYM Endless Mode inicializado. Campeón base: Oleada {self.trainer.best_wave} "
            f"(DPS: {self.trainer.best_dps:,.0f}) con 17 unidades (4 Granjas, 4 Warlord, 5 Z1MP, 4 Mafia)."
        )

    def log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.txt_log.insert("end", f"[{ts}] {msg}\n")
        self.txt_log.see("end")

    def _draw_static_map(self):
        self.canvas.delete("all")
        if os.path.exists(MAP_PATH):
            pil_img = Image.open(MAP_PATH).resize((self.canvas_w, self.canvas_h), Image.Resampling.LANCZOS)
            self.map_tk = ImageTk.PhotoImage(pil_img)
            self.canvas.create_image(0, 0, anchor="nw", image=self.map_tk, tags="bg")

    def redraw_dynamic_layer(self):
        self.canvas.delete("dyn")

        # 1. Dibujar polilínea de la pista (16 waypoints) y los 24 nodos de piedra si está activo
        if self.show_track_nodes.get():
            pts = []
            for gx, gy in TRACK_WAYPOINTS:
                cx, cy = self._game_to_canvas(gx, gy)
                pts.extend([cx, cy])
            if len(pts) >= 4:
                self.canvas.create_line(
                    *pts,
                    fill="#ff4757",
                    width=3,
                    dash=(6, 4),
                    tags="dyn",
                )
            # Portal de entrada (Spawn) y Base Final
            sx, sy = self._game_to_canvas(*TRACK_WAYPOINTS[0])
            ex, ey = self._game_to_canvas(*TRACK_WAYPOINTS[-1])
            self.canvas.create_oval(sx - 9, sy - 9, sx + 9, sy + 9, fill="#a55eea", outline="#ffffff", width=2, tags="dyn")
            self.canvas.create_text(sx, sy - 15, text="SPAWN", fill="#ffffff", font=("Arial", 8, "bold"), tags="dyn")
            self.canvas.create_oval(ex - 9, ey - 9, ex + 9, ey + 9, fill="#ff4757", outline="#ffffff", width=2, tags="dyn")
            self.canvas.create_text(ex, ey + 15, text="BASE", fill="#ff6b81", font=("Arial", 8, "bold"), tags="dyn")

            # Nodos libres de piedra
            for idx, (gx, gy) in enumerate(ALL_CANDIDATE_SPOTS):
                cx, cy = self._game_to_canvas(gx, gy)
                is_farm = idx < len(FARM_SPOTS)
                col = "#2ed573" if is_farm else "#747d8c"
                self.canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill=col, outline="#1e272e", tags="dyn")

        # 2. Dibujar círculos de rango de las unidades colocadas
        units_to_draw = self.play_env.placed_units if self.is_playing else self.displayed_units
        if self.show_ranges.get():
            for u in units_to_draw:
                slot = u["slot"]
                lvl = u["level"]
                lv_data = self.trainer.env.units_catalog[slot]["levels"][lvl - 1]
                rng_px = float(lv_data.get("range", 25)) * STUDS_TO_PX * self.scale_x
                cx, cy = self._game_to_canvas(u["x"], u["y"])
                col = SLOT_STYLE[slot]["color"]
                self.canvas.create_oval(
                    cx - rng_px,
                    cy - rng_px,
                    cx + rng_px,
                    cy + rng_px,
                    outline=col,
                    width=1,
                    dash=(3, 3),
                    tags="dyn",
                )

        # 3. Si está en modo PLAY, dibujar rayos láser de ataque e inodoros avanzando por la pista
        if self.is_playing:
            for laser in self.play_env.visual_lasers:
                x1, y1 = self._game_to_canvas(laser["x1"], laser["y1"])
                x2, y2 = self._game_to_canvas(laser["x2"], laser["y2"])
                col = SLOT_STYLE.get(laser["slot"], SLOT_STYLE[3])["color"]
                self.canvas.create_line(x1, y1, x2, y2, fill=col, width=2, tags="dyn")
                if laser.get("aoe"):
                    self.canvas.create_oval(x2 - 12, y2 - 12, x2 + 12, y2 + 12, outline="#ffa502", width=2, tags="dyn")

            for en in self.play_env.visual_enemies:
                ex, ey = self._game_to_canvas(en["x"], en["y"])
                r = 11 if en["is_boss"] else 7
                fill_col = "#ff4757" if en["is_boss"] else ("#00d2ff" if en.get("slowed") else "#f1f2f6")
                outline_col = "#ffa502" if en["is_boss"] else "#2f3542"
                self.canvas.create_oval(
                    ex - r, ey - r, ex + r, ey + r,
                    fill=fill_col, outline=outline_col, width=2, tags="dyn"
                )
                # Barra de vida del inodoro
                hp_ratio = max(0.0, min(1.0, en["hp"] / max(1.0, en["max_hp"])))
                bw = 22 if en["is_boss"] else 16
                self.canvas.create_rectangle(ex - bw / 2, ey - r - 7, ex + bw / 2, ey - r - 3, fill="#2f3542", outline="", tags="dyn")
                self.canvas.create_rectangle(
                    ex - bw / 2,
                    ey - r - 7,
                    ex - bw / 2 + bw * hp_ratio,
                    ey - r - 3,
                    fill="#2ed573" if hp_ratio > 0.35 else "#ff4757",
                    outline="",
                    tags="dyn",
                )

        # 4. Dibujar los iconos de las Unidades Colocadas (con su Slot y Nivel actual)
        counts = {1: 0, 2: 0, 3: 0, 4: 0}
        for u in units_to_draw:
            slot = u["slot"]
            lvl = u["level"]
            counts[slot] = counts.get(slot, 0) + 1
            cx, cy = self._game_to_canvas(u["x"], u["y"])
            st = SLOT_STYLE[slot]
            r = 12
            self.canvas.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                fill=st["color"], outline="#ffffff", width=2, tags="dyn"
            )
            self.canvas.create_text(
                cx, cy,
                text=f"S{slot}",
                fill=st["fg"],
                font=("Arial", 8, "bold"),
                tags="dyn",
            )
            self.canvas.create_text(
                cx, cy + 16,
                text=f"Nv.{lvl}",
                fill="#ffffff",
                font=("Arial", 8, "bold"),
                tags="dyn",
            )

        # Actualizar contadores de límites de unidades en el panel derecho
        for slot_id, lbl in self.slot_labels.items():
            mx = SLOT_STYLE[slot_id]["max"]
            lbl.configure(text=f"{counts.get(slot_id, 0)} / {mx}")

    # =========================================================================
    # LÓGICA DE ENTRENAMIENTO (DEAP + OPTUNA) GENERACIÓN TRAS GENERACIÓN
    # =========================================================================
    def run_single_generation(self):
        if self.is_training:
            return
        threading.Thread(target=self._step_one_gen_worker, daemon=True).start()

    def _step_one_gen_worker(self):
        rec = self.trainer.step_generation(mode=self.engine_mode.get())
        self.after(0, lambda: self._on_generation_completed(rec))

    def toggle_training(self):
        if not self.is_training:
            if self.is_playing:
                self.toggle_play()
            self.is_training = True
            self.btn_train_loop.configure(text="⏹ DETENER ENTRENAMIENTO", fg_color="#ff4757", hover_color="#d63031")
            self.lbl_status.configure(text="● ENTRENANDO (DEAP + OPTUNA)", text_color="#ffa502")
            threading.Thread(target=self._training_loop_worker, daemon=True).start()
        else:
            self.is_training = False
            self.btn_train_loop.configure(
                text="🧬 ENTRENAR GENERACIÓN TRAS GENERACIÓN",
                fg_color="#8e44ad",
                hover_color="#732d91",
            )
            self.lbl_status.configure(text="● ENTRENAMIENTO EN PAUSA", text_color="#2ed573")

    def _training_loop_worker(self):
        while self.is_training:
            rec = self.trainer.step_generation(mode=self.engine_mode.get())
            self.after(0, lambda r=rec: self._on_generation_completed(r))
            time.sleep(0.05)

    def _on_generation_completed(self, rec: Dict):
        self.lbl_gen.configure(text=f"Generación: #{rec['generation']} ({rec['mode']})")
        self.lbl_champ_wave.configure(text=f"🏆 Récord Campeón: Oleada {rec['champion_wave']}")
        self.lbl_live_money.configure(text=f"💵 Dinero: ${rec['champion_money']:,}")
        self.lbl_dps_summary.configure(text=f"⚡ DPS Efectivo Campeón: {rec['champion_dps']:,.0f}")

        if not self.is_playing:
            self.displayed_units = copy.deepcopy(rec["champion_placed_units"])
            self.redraw_dynamic_layer()

        tag = "★ ¡NUEVO CAMPEÓN!" if rec["improved"] else ""
        self.log(
            f"[Gen #{rec['generation']:02d} | {rec['mode']}] Mejor Gen: W{rec['gen_best_wave']} | "
            f"Campeón: Oleada {rec['champion_wave']} (DPS: {rec['champion_dps']:,.0f}) | "
            f"{rec['evals']} partidas en {rec['elapsed_s']:.2f}s {tag}"
        )

    # =========================================================================
    # LÓGICA DEL BOTÓN "PLAY" (SIMULACIÓN VISUAL EN VIVO EN EL MAPA ENDLESS)
    # =========================================================================
    def toggle_play(self):
        if not self.is_playing:
            if self.is_training:
                self.toggle_training()
            if not self.trainer.best_genome:
                messagebox.showwarning("Sin Estrategia", "Primero entrena al menos 1 generación.")
                return
            self.is_playing = True
            self.btn_play.configure(text="⏹ DETENER REPRODUCCIÓN (PLAY)", fg_color="#ff4757", hover_color="#d63031", text_color="#ffffff")
            self.lbl_status.configure(text="● REPRODUCIENDO PARTIDA EN VIVO", text_color="#2ed573")
            self._start_visual_match()
        else:
            self.is_playing = False
            self.btn_play.configure(
                text="▶ PLAY (VER CAMPEÓN JUGAR EN VIVO)",
                fg_color="#2ed573",
                hover_color="#26af5f",
                text_color="#000000",
            )
            self.lbl_status.configure(text="● LISTO", text_color="#2ed573")
            self.lbl_live_wave.configure(text="▶ Play: Detenido")
            self.displayed_units = copy.deepcopy(self.trainer.best_placed_units)
            self.redraw_dynamic_layer()

    def _start_visual_match(self):
        self.play_env.reset()
        self.play_queue = copy.deepcopy(self.trainer.best_genome)
        self._prepare_next_visual_wave()
        self.log(f"▶ Iniciando reproducción en vivo del Campeón en el mapa Endless Mode (17 unidades máx)...")
        self._play_tick_loop()

    def _prepare_next_visual_wave(self):
        # 1. El agente coloca todas las unidades de su cola genética que el dinero actual permita
        placed_any = True
        while self.play_queue and placed_any:
            slot, spot_idx = self.play_queue[0]
            if self.play_env.can_place_unit(slot, spot_idx):
                self.play_env.place_unit_action(slot, spot_idx)
                self.play_queue.pop(0)
                st = SLOT_STYLE[slot]
                gx, gy = self.play_env.candidate_spots[spot_idx]
                self.log(f"  [Oleada {self.play_env.wave}] Colocado {st['name']} en ({gx}, {gy})")
            else:
                placed_any = False

        # 2. Si la cola terminó o hay excedente temprano para granjas, mejorar unidades
        if not self.play_queue:
            up_cnt = self.play_env.upgrade_cheapest_available(prefer_farms_until_wave=16)
            if up_cnt > 0:
                self.log(f"  [Oleada {self.play_env.wave}] Gerente de Unidad aplicó {up_cnt} mejoras.")
        else:
            next_slot, _ = self.play_queue[0]
            next_cost = self.play_env.units_catalog[next_slot]["levels"][0]["cost"]
            if self.play_env.slot_counts[1] >= 2 and (self.play_env.slot_counts[2] + self.play_env.slot_counts[3] + self.play_env.slot_counts[4]) >= 1:
                for u in self.play_env.placed_units:
                    if u["slot"] == 1 and u["level"] < 4:
                        up_cost = self.play_env.units_catalog[1]["levels"][u["level"]]["cost"]
                        if self.play_env.money >= up_cost and (self.play_env.money - up_cost >= min(200, next_cost // 3)):
                            self.play_env.money -= up_cost
                            u["level"] += 1

        self.play_env.spawn_visual_wave()
        self.lbl_live_wave.configure(text=f"▶ Jugando Oleada: {self.play_env.wave}")
        self.lbl_live_money.configure(text=f"💵 Dinero: ${self.play_env.money:,}")
        self.lbl_dps_summary.configure(text=f"⚡ DPS Actual en Mapa: {self.play_env.compute_current_team_dps():,.0f}")

    def _play_tick_loop(self):
        if not self.is_playing:
            return

        spd = float(self.play_speed.get())
        steps = max(1, int(spd // 2))
        dt = 0.11 * (spd / steps)

        status = "running"
        for _ in range(steps):
            status = self.play_env.step_visual_tick(dt=dt)
            if status != "running":
                break

        self.redraw_dynamic_layer()

        if status == "wave_cleared":
            if self.play_env.terminated:
                self.log(f"🏆 ¡Partida completada! El Campeón superó el límite de {self.play_env.max_waves} oleadas.")
                self.toggle_play()
                return
            self._prepare_next_visual_wave()
        elif status == "defeat":
            self.log(f"💀 Fin de la partida en la Oleada {self.play_env.wave}: los inodoros superaron la defensa.")
            self.toggle_play()
            return

        self.after(35, self._play_tick_loop)

    def export_champion_to_bot(self):
        if not self.trainer.best_blueprint:
            messagebox.showwarning("Sin Campeón", "Aún no hay una estrategia para exportar.")
            return
        saved_paths = self.trainer.save_champion_blueprint()
        self.log(f"💾 Estrategia Campeona (Oleada {self.trainer.best_wave}, 14 unidades) exportada a: {saved_paths[1]}")
        if callable(self.on_blueprint_exported):
            try:
                self.on_blueprint_exported(self.trainer.best_blueprint)
            except Exception:
                pass
        messagebox.showinfo(
            "Campeón Aplicado a Blueprint.json",
            f"¡Estrategia Campeona (Oleada {self.trainer.best_wave}) exportada con éxito!\n\n"
            f"• 4 Casas de Jengibre (Slot 1)\n"
            f"• 1 Señor de la Guerra (Slot 2)\n"
            f"• 5 Camarógrafos Z1MP (Slot 3)\n"
            f"• 4 Camarógrafos Jefe Mafia (Slot 4)\n\n"
            f"Total: 14 unidades colocadas.\n\n"
            f"Guardado en:\n- blueprint.json\n- strategies/estrategia_gym_top1.json\n\n"
            f"Ya puedes iniciar el Agente en el Panel Principal para que la replique con el mouse en Roblox.",
        )

    def on_canvas_right_click(self, event):
        """Permite borrar cualquier punto candidato o tropa haciendo clic derecho sobre él."""
        cx, cy = event.x, event.y
        # Convertir a coordenadas de juego
        gx = int(round(cx / self.scale_x))
        gy = int(round(cy / self.scale_y))

        # Buscar el punto más cercano dentro de un radio de tolerancia
        best_dist = 9999.0
        best_idx = None
        best_spot = None

        for idx, (sx, sy) in enumerate(self.trainer.env.candidate_spots):
            d = math.hypot(gx - sx, gy - sy)
            if d < best_dist:
                best_dist = d
                best_idx = idx
                best_spot = (sx, sy)

        if best_idx is not None and best_dist <= 30.0:
            removed_gx, removed_gy = best_spot
            # No permitir borrar si quedan menos de 14 puntos
            if len(self.trainer.env.candidate_spots) <= 14:
                messagebox.showwarning("Límite mínimo", "No puedes borrar más puntos: se necesitan al menos 14 para las tropas.")
                return

            # Eliminar el punto de ambos entornos
            self.trainer.env.candidate_spots.pop(best_idx)
            self.play_env.candidate_spots = list(self.trainer.env.candidate_spots)
            self.trainer.env.num_spots = len(self.trainer.env.candidate_spots)
            self.play_env.num_spots = len(self.play_env.candidate_spots)

            # Re-generar un genoma válido sin ese punto
            new_g = create_random_genome()
            w, dps, money, bp, placed = evaluate_genome(self.trainer.env, new_g)
            self.trainer.best_wave = w
            self.trainer.best_dps = dps
            self.trainer.best_money = money
            self.trainer.best_genome = new_g
            self.trainer.best_blueprint = bp
            self.trainer.best_placed_units = placed
            self.displayed_units = copy.deepcopy(placed)

            self.log(f"❌ Nodo ({removed_gx}, {removed_gy}) ELIMINADO del mapa con clic derecho. Quedan {len(self.trainer.env.candidate_spots)} puntos.")
            self.redraw_dynamic_layer()


def main():
    root = ctk.CTk()
    root.withdraw()
    win = TTDGymWindow(master=root)
    def on_close():
        try:
            win.trainer.close()
        except Exception:
            pass
        root.destroy()
    win.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()

