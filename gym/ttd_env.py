# -*- coding: utf-8 -*-
"""
Entorno Gymnasium para Toilet Tower Defense (Roblox) - Modo Endless.

Adaptado desde la arquitectura de 'ai-gym-tower-defense' específicamente para las reglas,
físicas, economías y límites de unidades de Toilet Tower Defense en Roblox:
  - Mapa real: 'assets/map_endless.jpg' (coordenadas canónicas de juego 1366x768).
  - Límites reales de colocación del usuario (máximo 17 unidades activas dentro del tope global de 20):
      * Slot 1 (Casa de jengibre / Granja): máx 4
      * Slot 2 (Reloj de señor de guerra titán resplandeciente): máx 4
      * Slot 3 (Camarógrafo Z1MP resplandeciente): máx 5
      * Slot 4 (Camarógrafo del jefe de la mafia): máx 4
  - Datos reales de 141 enemigos, 209 oleadas y 19 jefes extraídos de la Wiki Fandom ('gym/data/').
  - Incluye modo Ultra-Rápido por oleada (para entrenar con DEAP y Optuna miles de partidas)
    y modo Tick-a-Tick Visual (para reproducir en vivo con el botón PLAY en la UI sobre el mapa).
"""
import functools
import json
import math
import os
import random
from typing import Dict, List, Optional, Tuple

import gymnasium as gym
from gymnasium import spaces
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
PROJECT_ROOT = os.path.dirname(ROOT)
MAP_PATH = os.path.join(PROJECT_ROOT, "assets", "map_endless.jpg")

# Velocidades calibradas en píxeles/segundo sobre vista cenital 1366x768
SPEED_PX_PER_SEC: Dict[str, float] = {
    "Very Slow": 16.0,
    "Slow": 25.0,
    "Average": 38.0,
    "Fast": 56.0,
    "Very Fast": 80.0,
    "Extremely Fast": 115.0,
    "Maximal": 160.0,
}

# Conversión de studs de rango de TTD a píxeles en resolución 1366x768 Cenital
STUDS_TO_PX = 3.5

# Límites estrictos de colocación por Slot definidos por el inventario del usuario
MAX_BY_SLOT: Dict[int, int] = {
    1: 4,  # Casa de jengibre (Granja)
    2: 1,  # Reloj de señor de guerra titán resplandeciente (Definitivo / Ultimate: Solo 1)
    3: 5,  # Camarógrafo Z1MP resplandeciente
    4: 4,  # Camarógrafo del jefe de la mafia
}
MAX_TOTAL_UNITS = 20  # Tope global del mapa; con MAX_BY_SLOT colocamos hasta 14 unidades (4+1+5+4)

# Polilínea exacta de 16 waypoints del camino de los inodoros sobre assets/map_endless.jpg (1366x768)
TRACK_WAYPOINTS: List[Tuple[int, int]] = [
    (950, 185),  # 0: Spawn (portal morado superior derecho)
    (944, 280),  # 1: Bajada inicial
    (895, 280),  # 2: Escalón izquierdo superior
    (895, 360),  # 3: Giro hacia la derecha
    (1082, 375), # 4: Esquina derecha media
    (1076, 480), # 5: Bajada derecha media
    (1152, 485), # 6: Extensión bucle exterior derecho
    (1150, 567), # 7: Esquina inferior exterior derecha
    (990, 567),  # 8: Retorno interior derecho
    (988, 653),  # 9: Esquina inferior derecha
    (764, 643),  # 10: Esquina inferior central
    (778, 510),  # 11: Subida central
    (848, 510),  # 12: Bucle central derecho
    (848, 435),  # 13: Tope bucle central
    (585, 418),  # 14: Recta hacia la izquierda
    (547, 655),  # 15: Base / Salida final inferior izquierda
]

# 4 Nodos de piedra exteriores para Granjas (Slot 1)
FARM_SPOTS: List[Tuple[int, int]] = [
    (995, 305),   # idx 0 (F1)
    (845, 235),   # idx 1 (F2)
    (1120, 615),  # idx 2 (F3)
    (1045, 305),  # idx 3 (F4)
]

# Nodos de piedra estratégicos sobre plataformas alrededor de la pista para Combate/Soporte (Slots 2, 3, 4)
COMBAT_SPOTS: List[Tuple[int, int]] = [
    (935, 410),   # C1 - isla superior central
    (1035, 515),  # C2 - isla derecha media
    (935, 515),   # C3 - corazón del mapa
    (935, 600),   # C4 - isla inferior derecha
    (885, 585),   # C5 - curva inferior central-derecha
    (825, 585),   # C6 - curva inferior central-izquierda
    (820, 545),   # C7 - interior bucle central
    (890, 470),   # C8 - cruce central
    (805, 470),   # C9 - plataforma central-izquierda
    (735, 470),   # C10 - subida central exterior
    (730, 545),   # C11 - pared izquierda de subida central
    (730, 600),   # C12 - esquina inferior central-izquierda
    (795, 390),   # C13 - recta superior central
    (715, 385),   # C14 - recta superior media
    (645, 380),   # C15 - esquina superior izquierda
    (640, 455),   # C16 - interior curva final
    (630, 520),   # C17 - bajada final interior
    (620, 585),   # C18 - bajada final baja
    (525, 485),   # C19 - guardia exterior izquierda
]

ALL_CANDIDATE_SPOTS: List[Tuple[int, int]] = FARM_SPOTS + COMBAT_SPOTS


class TTDEndlessGymEnv(gym.Env):
    """
    Entorno Gymnasium para Toilet Tower Defense (Modo Endless).
    Soporta:
      - Simulación rápida por oleada (`step` / `step_wave`) para algoritmos evolutivos (DEAP) y bayesianos (Optuna).
      - Simulación visual tick a tick (`spawn_visual_wave` + `step_visual_tick`) para ver la partida en vivo en la UI.
    """

    metadata = {"render_modes": ["rgb_array"], "render_fps": 30}

    def __init__(self, max_waves: int = 200, render_mode: Optional[str] = None):
        super().__init__()
        self.max_waves = max_waves
        self.render_mode = render_mode

        with open(os.path.join(DATA_DIR, "units.json"), encoding="utf-8") as f:
            self.units_catalog = {u["slot"]: u for u in json.load(f)["units"]}
        with open(os.path.join(DATA_DIR, "enemies.json"), encoding="utf-8") as f:
            self.enemies_list = json.load(f)
        self.enemies_by_name = {e["name"]: e for e in self.enemies_list}
        with open(os.path.join(DATA_DIR, "endless_waves.json"), encoding="utf-8") as f:
            self.waves_data = json.load(f)
        self.waves_by_num = {w["wave"]: w for w in self.waves_data}
        with open(os.path.join(DATA_DIR, "endless_bosses.json"), encoding="utf-8") as f:
            self.bosses_by_wave = {b["wave"]: b for b in json.load(f)}
        self._wave_cache: Dict[int, Tuple[float, float, bool, List[Dict]]] = {}

        self.track_waypoints = list(TRACK_WAYPOINTS)
        self.candidate_spots = list(ALL_CANDIDATE_SPOTS)
        self.segment_lengths, self.track_length = self._compute_track_segments()

        self.max_by_slot = dict(MAX_BY_SLOT)
        self.max_total_units = min(MAX_TOTAL_UNITS, sum(self.max_by_slot.values()))  # 17

        # Espacio de acciones estilo ai-gym-tower-defense:
        # 0: Pasar / iniciar oleada
        # 1: Mejorar unidad más económica/prioritaria disponible
        # 2 .. 2 + (4 * 24) - 1: Colocar unidad de Slot (1..4) en Spot (0..23)
        self.num_spots = len(self.candidate_spots)
        self.action_space = spaces.Discrete(2 + 4 * self.num_spots)

        # Observación: [oleada_norm, dinero_norm, c_slot1, c_slot2, c_slot3, c_slot4, nivel_promedio, cobertura_dps]
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(8,), dtype=np.float32)

        # Estado de la partida
        self.wave = 1
        self.money = 200
        self.base_hp = 300.0
        self.placed_units: List[Dict] = []
        self.used_spots = set()
        self.slot_counts = {1: 0, 2: 0, 3: 0, 4: 0}
        self.placement_history: List[Dict] = []
        self.upgrade_log: List[Dict] = []
        self.last_rewind_wave = -10
        self.terminated = False

        # Estado de animación tick-a-tick para la UI
        self.visual_enemies: List[Dict] = []
        self.visual_lasers: List[Dict] = []
        self.visual_spawn_queue: List[Dict] = []
        self.visual_timer = 0.0
        self.visual_wave_income_pending = 0

        self.reset()

    def _compute_track_segments(self) -> Tuple[List[float], float]:
        seg_lengths = []
        total = 0.0
        for i in range(len(self.track_waypoints) - 1):
            x1, y1 = self.track_waypoints[i]
            x2, y2 = self.track_waypoints[i + 1]
            d = math.hypot(x2 - x1, y2 - y1)
            seg_lengths.append(d)
            total += d
        return seg_lengths, total

    def pos_along_track(self, dist_px: float) -> Tuple[float, float]:
        """Convierte una distancia recorrida en píxeles (0 .. track_length) a coordenadas (x, y) en el mapa."""
        if dist_px <= 0:
            return float(self.track_waypoints[0][0]), float(self.track_waypoints[0][1])
        rem = dist_px
        for i, seg_len in enumerate(self.segment_lengths):
            if rem <= seg_len or i == len(self.segment_lengths) - 1:
                t = max(0.0, min(1.0, rem / max(1e-6, seg_len)))
                x1, y1 = self.track_waypoints[i]
                x2, y2 = self.track_waypoints[i + 1]
                return x1 + t * (x2 - x1), y1 + t * (y2 - y1)
            rem -= seg_len
        return float(self.track_waypoints[-1][0]), float(self.track_waypoints[-1][1])

    @functools.lru_cache(maxsize=4096)
    def _point_to_track_coverage(self, px: int, py: int, radius_px: int) -> float:
        """Fracción de la pista cubierta por una unidad en (px, py) con radio 'radius_px'."""
        samples = 80
        covered = 0
        for s in range(samples):
            dist = (s / float(samples - 1)) * self.track_length
            sx, sy = self.pos_along_track(dist)
            if math.hypot(px - sx, py - sy) <= radius_px:
                covered += 1
        return covered / float(samples)

    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None):
        super().reset(seed=seed)
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
        self.wave = 1
        self.money = 200
        self.base_hp = 300.0
        self.placed_units = []
        self.used_spots = set()
        self.slot_counts = {1: 0, 2: 0, 3: 0, 4: 0}
        self.placement_history = []
        self.upgrade_log = []
        self.last_rewind_wave = -10
        self.terminated = False

        self.visual_enemies = []
        self.visual_lasers = []
        self.visual_spawn_queue = []
        self.visual_timer = 0.0
        self.visual_wave_income_pending = 0
        return self._get_obs(), {}

    def _get_obs(self) -> np.ndarray:
        avg_lvl = float(np.mean([u["level"] for u in self.placed_units])) if self.placed_units else 0.0
        total_dps_norm = min(1.0, self.compute_current_team_dps() / 5_000_000.0)
        return np.array([
            min(1.0, self.wave / float(self.max_waves)),
            min(1.0, self.money / 100000.0),
            self.slot_counts[1] / float(self.max_by_slot[1]),
            self.slot_counts[2] / float(self.max_by_slot[2]),
            self.slot_counts[3] / float(self.max_by_slot[3]),
            self.slot_counts[4] / float(self.max_by_slot[4]),
            avg_lvl / 8.0,
            total_dps_norm,
        ], dtype=np.float32)

    def can_place_unit(self, slot: int, spot_idx: int) -> bool:
        """Verifica límites por unidad (4 Granjas, 4 Warlord, 5 Z1MP, 4 Mafia Boss), dinero y nodo libre."""
        if slot not in self.units_catalog:
            return False
        if spot_idx < 0 or spot_idx >= self.num_spots or spot_idx in self.used_spots:
            return False
        if len(self.placed_units) >= self.max_total_units:
            return False
        if self.slot_counts.get(slot, 0) >= self.max_by_slot.get(slot, 4):
            return False
        # Granjas (Slot 1) en nodos de granja (0..3); Combate/Soporte (2,3,4) en nodos de combate (4..23)
        if slot == 1 and spot_idx >= len(FARM_SPOTS):
            return False
        if slot != 1 and spot_idx < len(FARM_SPOTS):
            return False
        cost = self.units_catalog[slot]["levels"][0]["cost"]
        return self.money >= cost

    def action_masks(self) -> np.ndarray:
        """Máscara booleana de acciones válidas (compatible con sb3_contrib MaskablePPO)."""
        mask = np.zeros(self.action_space.n, dtype=bool)
        mask[0] = True  # Siempre se puede avanzar la oleada
        # Acción 1: mejorar si alguna unidad colocada puede subir de nivel con el dinero actual
        for u in self.placed_units:
            levels = self.units_catalog[u["slot"]]["levels"]
            if u["level"] < len(levels) and self.money >= levels[u["level"]]["cost"]:
                mask[1] = True
                break
        # Acciones 2..N: colocar (slot, spot_idx)
        for slot in (1, 2, 3, 4):
            for spot_idx in range(self.num_spots):
                if self.can_place_unit(slot, spot_idx):
                    act_id = 2 + (slot - 1) * self.num_spots + spot_idx
                    mask[act_id] = True
        return mask

    def place_unit_action(self, slot: int, spot_idx: int) -> bool:
        if not self.can_place_unit(slot, spot_idx):
            return False
        unit_def = self.units_catalog[slot]
        cost = unit_def["levels"][0]["cost"]
        x, y = self.candidate_spots[spot_idx]
        self.money -= cost
        self.used_spots.add(spot_idx)
        self.slot_counts[slot] += 1
        unit_id = len(self.placed_units) + 1
        u_obj = {
            "id": unit_id,
            "slot": slot,
            "name": unit_def["name_es"],
            "level": 1,
            "x": int(x),
            "y": int(y),
            "spot_idx": spot_idx,
            "cooldown_timer": 0.0,
        }
        self.placed_units.append(u_obj)
        # Escala a canvas 750x478 de app.py (1366/750 = 1.8213, 768/478 = 1.6067)
        self.placement_history.append({
            "id": unit_id,
            "slot": slot,
            "name": unit_def["name_es"],
            "cost": cost,
            "canvas_x": int(round(x * 750.0 / 1366.0)),
            "canvas_y": int(round(y * 478.0 / 768.0)),
            "game_x": int(x),
            "game_y": int(y),
            "spot_idx": spot_idx,
            "wave_placed": self.wave,
        })
        return True

    def upgrade_step_once(self, prefer_farms_until_wave: int = 16) -> bool:
        """Realiza una sola mejora óptima (prioriza granjas en oleadas tempranas y menor costo)."""
        candidates = []
        for idx, u in enumerate(self.placed_units):
            levels = self.units_catalog[u["slot"]]["levels"]
            if u["level"] < len(levels):
                next_lv = levels[u["level"]]
                cost = next_lv["cost"]
                if self.money >= cost:
                    priority = 0 if (u["slot"] == 1 and self.wave <= prefer_farms_until_wave) else 1
                    candidates.append((priority, cost, idx))
        if not candidates:
            return False
        candidates.sort(key=lambda item: (item[0], item[1]))
        _, cost, best_idx = candidates[0]
        self.money -= cost
        self.placed_units[best_idx]["level"] += 1
        self.upgrade_log.append({
            "wave": self.wave,
            "unit_id": self.placed_units[best_idx]["id"],
            "slot": self.placed_units[best_idx]["slot"],
            "new_level": self.placed_units[best_idx]["level"],
            "cost": cost,
        })
        return True

    def upgrade_cheapest_available(self, prefer_farms_until_wave: int = 16) -> int:
        """Mejora todas las unidades posibles con el dinero actual (idéntico al nuevo Gerente de Unidad)."""
        upgraded = 0
        while self.upgrade_step_once(prefer_farms_until_wave=prefer_farms_until_wave):
            upgraded += 1
        return upgraded

    def _compute_unit_effective_stats(self, u: Dict, has_boss: bool = False) -> Tuple[float, float, float, float]:
        """
        Retorna (dmg, cd, rng_px, effective_dps) de una unidad considerando los Boosters cercanos
        (Slot 2: Cooldown Boost; Slot 4: Damage Boost) en rango.
        """
        u_def = self.units_catalog[u["slot"]]
        lv_data = u_def["levels"][u["level"] - 1]
        dmg = float(lv_data.get("damage", 0))
        cd = float(lv_data.get("cooldown", 1.0))
        rng_px = float(lv_data.get("range", 25)) * STUDS_TO_PX

        if u_def.get("can_be_boosted", True):
            best_cd_boost = 0.0
            best_dmg_boost = 0.0
            for other in self.placed_units:
                if other is u:
                    continue
                o_def = self.units_catalog[other["slot"]]
                o_lv = o_def["levels"][other["level"] - 1]
                o_rng_px = float(o_lv.get("range", 25)) * STUDS_TO_PX
                if math.hypot(u["x"] - other["x"], u["y"] - other["y"]) <= o_rng_px:
                    best_cd_boost = max(best_cd_boost, float(o_lv.get("cooldown_boost_pct", 0.0)) / 100.0)
                    best_dmg_boost = max(best_dmg_boost, float(o_lv.get("damage_boost_pct", 0.0)) / 100.0)
            dmg *= (1.0 + best_dmg_boost)
            cd *= max(0.35, 1.0 - best_cd_boost)

        if has_boss and u_def.get("boss_damage_bonus_pct"):
            dmg *= (1.0 + float(u_def["boss_damage_bonus_pct"]) / 100.0)

        ally_dps = float(lv_data.get("ally_dps", 0))
        dps = (dmg / cd if cd > 0 else 0.0) + ally_dps
        return dmg, cd, rng_px, dps

    def compute_current_team_dps(self) -> float:
        total = 0.0
        for u in self.placed_units:
            _, _, rng_px, dps = self._compute_unit_effective_stats(u, has_boss=False)
            u_def = self.units_catalog[u["slot"]]
            aoe_mult = 2.4 if ("aoe_360" in u_def["role"] or "splash" in u_def["role"]) else 1.0
            cov = self._point_to_track_coverage(int(u["x"]), int(u["y"]), int(rng_px))
            total += dps * aoe_mult * cov
        return total

    def _compute_wave_hp_and_speed(self, wave_num: int) -> Tuple[float, float, bool, List[Dict]]:
        """
        Retorna (total_hp, avg_speed_px, has_boss, enemy_descriptors) para la oleada 'wave_num'
        usando los datos extraídos de la Wiki Fandom (con caché en memoria).
        """
        if wave_num in self._wave_cache:
            return self._wave_cache[wave_num]
        w_entry = self.waves_by_num.get(wave_num)
        total_hp = 0.0
        speeds = []
        has_boss = False
        descriptors = []

        if w_entry and w_entry.get("documented"):
            for item in w_entry["enemies"]:
                cnt = max(1, int(item.get("count") or 3))
                en_name = item["enemy"]
                en = self.enemies_by_name.get(en_name, {})
                # Los mobs comunes escalan gradualmente; no deben superar el 5% de la vida de un jefe en oleadas altas
                default_mob_hp = min(3_200_000.0, 160.0 * (1.108 ** min(wave_num, 110)))
                hp = float(en.get("health") or default_mob_hp)
                tier = en.get("speed_tier") or "Average"
                spd = SPEED_PX_PER_SEC.get(tier, 38.0)
                total_hp += cnt * hp
                speeds.append(spd)
                descriptors.append({
                    "name": en_name,
                    "count": min(cnt, 8),
                    "hp": (cnt * hp) / min(cnt, 8),
                    "speed": spd,
                    "is_boss": bool(en.get("is_boss", False)),
                })
            if w_entry.get("boss") or wave_num in self.bosses_by_wave:
                has_boss = True
                boss_info = self.bosses_by_wave.get(wave_num, {})
                b_hp = float(boss_info.get("hp") or (14500.0 * (1.205 ** max(0, wave_num - 10))))
                b_name = boss_info.get("boss") or w_entry.get("boss") or f"Jefe Oleada {wave_num}"
                total_hp += b_hp
                speeds.append(SPEED_PX_PER_SEC["Slow"])
                descriptors.append({
                    "name": b_name,
                    "count": 1,
                    "hp": b_hp,
                    "speed": SPEED_PX_PER_SEC["Slow"],
                    "is_boss": True,
                })
        else:
            # Curva calibrada con los jefes reales de Endless Mode (Wave 10..190)
            has_boss = (wave_num % 10 == 0)
            if has_boss and wave_num in self.bosses_by_wave:
                b_info = self.bosses_by_wave[wave_num]
                b_hp = float(b_info.get("hp") or (14500.0 * (1.205 ** max(0, wave_num - 10))))
                b_name = b_info.get("boss", f"Boss W{wave_num}")
                mob_hp = b_hp * 0.18
                total_hp = mob_hp + b_hp
                descriptors.append({"name": f"Escuadrón W{wave_num}", "count": 5, "hp": mob_hp / 5.0, "speed": 42.0, "is_boss": False})
                descriptors.append({"name": b_name, "count": 1, "hp": b_hp, "speed": SPEED_PX_PER_SEC["Slow"], "is_boss": True})
            else:
                base_wave_hp = min(80_000_000.0, 360.0 * (1.115 ** min(wave_num, 120)))
                total_hp = base_wave_hp
                descriptors.append({
                    "name": f"Inodoros W{wave_num}",
                    "count": 6,
                    "hp": total_hp / 6.0,
                    "speed": 38.0 + min(35.0, wave_num * 0.22),
                    "is_boss": False,
                })
            speeds.append(38.0 + min(35.0, wave_num * 0.22))

        avg_speed = float(np.mean(speeds)) if speeds else 38.0
        res = (max(300.0, total_hp), avg_speed, has_boss, descriptors)
        self._wave_cache[wave_num] = res
        return res

    def step(self, action: int):
        """Interfaz estándar Gymnasium."""
        if action == 1:
            self.upgrade_step_once()
            return self._get_obs(), 0.05, self.terminated, False, {"wave": self.wave}
        elif action >= 2:
            rel = action - 2
            slot = (rel // self.num_spots) + 1
            spot_idx = rel % self.num_spots
            ok = self.place_unit_action(slot, spot_idx)
            return self._get_obs(), (0.1 if ok else -0.05), self.terminated, False, {"wave": self.wave}
        else:
            return self.step_wave()

    def step_wave(self):
        """Simula una oleada completa de forma analítica ultra-rápida para entrenamiento DEAP / Optuna."""
        if self.terminated:
            return self._get_obs(), 0.0, True, False, {"wave_reached": self.wave}

        wave_hp, avg_speed_px, has_boss, _ = self._compute_wave_hp_and_speed(self.wave)

        # Ralentización del 60% si hay al menos un Titan Warlord Clockman (Slot 2) cubriendo la pista
        warlord_cov = 0.0
        for u in self.placed_units:
            if u["slot"] == 2:
                _, _, rng_px, _ = self._compute_unit_effective_stats(u, has_boss)
                warlord_cov = max(warlord_cov, self._point_to_track_coverage(int(u["x"]), int(u["y"]), int(rng_px)))

        slow_factor = 1.0 - (0.60 * min(1.0, warlord_cov * 1.4))
        effective_speed = avg_speed_px * max(0.40, slow_factor)
        time_on_track = self.track_length / max(8.0, effective_speed)

        total_damage_dealt = 0.0
        wave_income = 110 + self.wave * 38

        for u in self.placed_units:
            u_def = self.units_catalog[u["slot"]]
            lv_data = u_def["levels"][u["level"] - 1]
            wave_income += int(lv_data.get("income", 0))

            _, _, rng_px, dps = self._compute_unit_effective_stats(u, has_boss=has_boss)
            aoe_mult = 2.4 if ("aoe_360" in u_def["role"] or "splash" in u_def["role"]) else 1.0
            coverage = self._point_to_track_coverage(int(u["x"]), int(u["y"]), int(rng_px))

            total_damage_dealt += dps * aoe_mult * coverage * time_on_track

        # Habilidad activa Warlord Rewind: cada 6 oleadas un Titan Warlord puede rebobinar al jefe/oleada al inicio
        has_warlord = self.slot_counts[2] > 0
        if total_damage_dealt < wave_hp and has_warlord and (self.wave - self.last_rewind_wave >= 6):
            self.last_rewind_wave = self.wave
            total_damage_dealt *= 1.75  # Rebobinar da un 75% extra de tiempo en pista

        if total_damage_dealt < wave_hp:
            leaked_hp = wave_hp - total_damage_dealt
            if leaked_hp <= self.base_hp:
                self.base_hp -= leaked_hp
            else:
                self.base_hp = 0.0
                self.terminated = True
                return self._get_obs(), -10.0, True, False, {
                    "wave_reached": self.wave,
                    "wave_hp": wave_hp,
                    "damage": total_damage_dealt,
                }

        self.money += int(wave_income)
        self.wave += 1
        done = self.wave > self.max_waves
        if done:
            self.terminated = True
        return self._get_obs(), 1.0 + (self.wave * 0.05), done, False, {
            "wave_reached": self.wave,
            "wave_hp": wave_hp,
            "damage": total_damage_dealt,
        }

    # =========================================================================
    # SIMULACIÓN TICK-A-TICK VISUAL PARA EL BOTÓN "PLAY" EN LA UI
    # =========================================================================
    def spawn_visual_wave(self):
        """Inicializa las entidades visuales de enemigos para la oleada actual sobre la pista del mapa."""
        _, _, _, descriptors = self._compute_wave_hp_and_speed(self.wave)
        self.visual_enemies = []
        self.visual_lasers = []
        self.visual_spawn_queue = []
        self.visual_timer = 0.0

        wave_income = 110 + self.wave * 38
        for u in self.placed_units:
            lv_data = self.units_catalog[u["slot"]]["levels"][u["level"] - 1]
            wave_income += int(lv_data.get("income", 0))
        self.visual_wave_income_pending = wave_income

        spawn_delay = 0.0
        for desc in descriptors:
            for i in range(desc["count"]):
                self.visual_spawn_queue.append({
                    "spawn_time": spawn_delay,
                    "name": desc["name"],
                    "max_hp": float(desc["hp"]),
                    "hp": float(desc["hp"]),
                    "speed": float(desc["speed"]),
                    "is_boss": bool(desc["is_boss"]),
                    "dist": 0.0,
                    "slowed": False,
                })
                spawn_delay += 0.45 if not desc["is_boss"] else 0.8

        for u in self.placed_units:
            u["cooldown_timer"] = 0.0

    def step_visual_tick(self, dt: float = 0.12) -> str:
        """
        Avanza un tick visual de la oleada actual.
        Retorna:
          - 'running': la oleada sigue en curso
          - 'wave_cleared': todos los enemigos de la oleada fueron eliminados
          - 'defeat': un enemigo llegó a la base y no pudo ser detenido
        """
        self.visual_timer += dt
        self.visual_lasers = []

        # 1. Spawnear enemigos pendientes de la cola
        while self.visual_spawn_queue and self.visual_spawn_queue[0]["spawn_time"] <= self.visual_timer:
            en = self.visual_spawn_queue.pop(0)
            x, y = self.pos_along_track(0.0)
            en["x"] = x
            en["y"] = y
            self.visual_enemies.append(en)

        # 2. Mover enemigos a lo largo de los 16 waypoints de la pista
        warlords = [u for u in self.placed_units if u["slot"] == 2]
        for en in self.visual_enemies:
            slowed = False
            for wl in warlords:
                _, _, wl_rng, _ = self._compute_unit_effective_stats(wl, has_boss=en["is_boss"])
                if math.hypot(en["x"] - wl["x"], en["y"] - wl["y"]) <= wl_rng:
                    slowed = True
                    break
            en["slowed"] = slowed
            eff_speed = en["speed"] * (0.40 if slowed else 1.0)
            # Factor x2.2 visual para que la oleada sea fluida y dinámica en pantalla
            en["dist"] += eff_speed * dt * 2.2
            en["x"], en["y"] = self.pos_along_track(en["dist"])

            # ¿Llegó al final de la pista?
            if en["dist"] >= self.track_length:
                if warlords and (self.wave - self.last_rewind_wave >= 6):
                    # ¡Warlord Rewind! Devuelve al inodoro al principio de la pista
                    self.last_rewind_wave = self.wave
                    en["dist"] = 0.0
                    en["x"], en["y"] = self.pos_along_track(0.0)
                elif en["hp"] <= self.base_hp:
                    self.base_hp -= en["hp"]
                    en["hp"] = 0.0
                else:
                    self.base_hp = 0.0
                    self.terminated = True
                    return "defeat"

        # 3. Las unidades atacan a los enemigos dentro de su rango
        for u in self.placed_units:
            u["cooldown_timer"] = max(0.0, u.get("cooldown_timer", 0.0) - dt * 2.2)
            if u["cooldown_timer"] > 0.0 or not self.visual_enemies:
                continue

            u_def = self.units_catalog[u["slot"]]
            dmg, cd, rng_px, dps = self._compute_unit_effective_stats(u, has_boss=any(e["is_boss"] for e in self.visual_enemies))

            # Buscar enemigos ESTRICTAMENTE dentro del rango (Objetivo: Primero -> mayor 'dist')
            in_range = [
                e for e in self.visual_enemies
                if e["hp"] > 0 and math.hypot(e["x"] - u["x"], e["y"] - u["y"]) <= rng_px
            ]

            if in_range:
                in_range.sort(key=lambda e: e["dist"], reverse=True)
                target = in_range[0]
                shot_dmg = dps * cd * 1.5

                if "aoe_360" in u_def["role"]:
                    for e in in_range:
                        e["hp"] -= shot_dmg
                    self.visual_lasers.append({
                        "x1": u["x"], "y1": u["y"],
                        "x2": target["x"], "y2": target["y"],
                        "slot": u["slot"], "aoe": True
                    })
                elif "splash" in u_def["role"]:
                    splash_px = float(u_def.get("splash_radius", 20)) * STUDS_TO_PX
                    for e in self.visual_enemies:
                        if e["hp"] > 0 and math.hypot(e["x"] - target["x"], e["y"] - target["y"]) <= splash_px:
                            e["hp"] -= shot_dmg
                    self.visual_lasers.append({
                        "x1": u["x"], "y1": u["y"],
                        "x2": target["x"], "y2": target["y"],
                        "slot": u["slot"], "aoe": False
                    })
                else:
                    target["hp"] -= shot_dmg
                    self.visual_lasers.append({
                        "x1": u["x"], "y1": u["y"],
                        "x2": target["x"], "y2": target["y"],
                        "slot": u["slot"], "aoe": False
                    })
                u["cooldown_timer"] = cd

        # Eliminar enemigos derrotados
        self.visual_enemies = [e for e in self.visual_enemies if e["hp"] > 0]

        if not self.visual_enemies and not self.visual_spawn_queue:
            self.money += int(self.visual_wave_income_pending)
            self.wave += 1
            if self.wave > self.max_waves:
                self.terminated = True
            return "wave_cleared"

        return "running"

    def export_blueprint_json(self, filepath: str):
        """Exporta el plan de colocación en el formato exacto que consume 'app.py'."""
        clean_bp = [
            {
                "id": item["id"],
                "slot": item["slot"],
                "name": item["name"],
                "cost": item["cost"],
                "canvas_x": item["canvas_x"],
                "canvas_y": item["canvas_y"],
                "game_x": item["game_x"],
                "game_y": item["game_y"],
            }
            for item in self.placement_history
        ]
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(clean_bp, f, indent=4, ensure_ascii=False)
        return clean_bp
