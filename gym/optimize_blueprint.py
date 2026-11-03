# -*- coding: utf-8 -*-
"""
Motor de Entrenamiento y Optimización de Estrategias para Toilet Tower Defense (Modo Endless).
Integra:
  1. DEAP (Algoritmos Evolutivos Genéticos: Selección por Torneo, Cruce con Reparación de Restricciones y Mutación Topológica).
  2. Optuna (Optimización Bayesiana TPE: Tree-structured Parzen Estimator).
  3. Modo Híbrido (DEAP + Optuna) generación tras generación.

Respeta estrictamente las restricciones de inventario del jugador:
  - Máximo 4 Granjas (Slot 1 - Casa de jengibre) en los nodos de piedra exteriores (0..3).
  - Máximo 4 Señor de la Guerra (Slot 2 - Reloj de señor de guerra titán resplandeciente) en nodos de combate (4..23).
  - Máximo 5 Z1MP (Slot 3 - Camarógrafo Z1MP resplandeciente) en nodos de combate (4..23).
  - Máximo 4 Camarógrafo Jefe Mafia (Slot 4 - Camarógrafo del jefe de la mafia) en nodos de combate (4..23).
  Total = 17 unidades colocadas (dentro del límite máximo de 20 del juego).
"""
import copy
import json
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Dict, Generator, List, Optional, Tuple

import deap.base as deap_base
import deap.creator as deap_creator
import deap.tools as deap_tools
import optuna

# Silenciar logs verbosos de Optuna por consola
optuna.logging.set_verbosity(optuna.logging.WARNING)

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ttd_env import (
    COMBAT_SPOTS,
    DATA_DIR,
    FARM_SPOTS,
    MAX_BY_SLOT,
    PROJECT_ROOT,
    TTDEndlessGymEnv,
)


# Inicializar clases DEAP una sola vez
if not hasattr(deap_creator, "FitnessTTD"):
    deap_creator.create("FitnessTTD", deap_base.Fitness, weights=(1000.0, 1.0, 0.01))
if not hasattr(deap_creator, "IndividualTTD"):
    deap_creator.create("IndividualTTD", list, fitness=deap_creator.FitnessTTD)


def validate_and_repair_genome(genome: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """
    Garantiza que cualquier genoma cumpla al 100% las reglas de negocio:
      - Exactamente hasta 4 de Slot 1 (en spots 0..3)
      - Exactamente hasta 4 de Slot 2 (en spots 4..23)
      - Exactamente hasta 5 de Slot 3 (en spots 4..23)
      - Exactamente hasta 4 de Slot 4 (en spots 4..23)
      - Sin repetir ningún spot_idx.
    """
    counts = {1: 0, 2: 0, 3: 0, 4: 0}
    used_spots = set()
    repaired: List[Tuple[int, int]] = []

    free_farm_spots = list(range(len(FARM_SPOTS)))
    random.shuffle(free_farm_spots)
    free_combat_spots = list(range(len(FARM_SPOTS), len(FARM_SPOTS) + len(COMBAT_SPOTS)))
    random.shuffle(free_combat_spots)

    for slot, spot_idx in genome:
        if slot not in MAX_BY_SLOT:
            continue
        if counts[slot] >= MAX_BY_SLOT[slot]:
            continue
        if slot == 1:
            if spot_idx not in range(len(FARM_SPOTS)) or spot_idx in used_spots:
                spot_idx = next((s for s in free_farm_spots if s not in used_spots), -1)
        else:
            if spot_idx not in range(len(FARM_SPOTS), len(FARM_SPOTS) + len(COMBAT_SPOTS)) or spot_idx in used_spots:
                spot_idx = next((s for s in free_combat_spots if s not in used_spots), -1)
        if spot_idx == -1:
            continue
        used_spots.add(spot_idx)
        counts[slot] += 1
        repaired.append((slot, spot_idx))

    # Completar unidades faltantes hasta llegar a las 17 unidades (4, 4, 5, 4)
    for slot, max_cnt in MAX_BY_SLOT.items():
        while counts[slot] < max_cnt:
            if slot == 1:
                spot_idx = next((s for s in free_farm_spots if s not in used_spots), -1)
            else:
                spot_idx = next((s for s in free_combat_spots if s not in used_spots), -1)
            if spot_idx == -1:
                break
            used_spots.add(spot_idx)
            counts[slot] += 1
            repaired.append((slot, spot_idx))

    # Asegurar que el inicio tenga al menos 1 granja o 1 defensa costeable para no bloquear la oleada 1-3
    if repaired and repaired[0][0] != 1:
        first_farm_idx = next((i for i, (sl, _) in enumerate(repaired) if sl == 1), None)
        if first_farm_idx is not None:
            repaired[0], repaired[first_farm_idx] = repaired[first_farm_idx], repaired[0]

    return repaired


def create_random_genome() -> List[Tuple[int, int]]:
    """
    Crea un genoma aleatorio válido de 17 unidades:
      - 4 Granjas (Slot 1)
      - 4 Señor de la Guerra (Slot 2)
      - 5 Z1MP (Slot 3)
      - 4 Camarógrafo Jefe Mafia (Slot 4)
    """
    farm_spots = list(range(len(FARM_SPOTS)))
    random.shuffle(farm_spots)
    farms = [(1, sp) for sp in farm_spots[: MAX_BY_SLOT[1]]]

    total_combat = MAX_BY_SLOT[2] + MAX_BY_SLOT[3] + MAX_BY_SLOT[4]
    combat_pool_spots = random.sample(
        range(len(FARM_SPOTS), len(FARM_SPOTS) + len(COMBAT_SPOTS)),
        total_combat,
    )
    combat_slots = (
        [2] * MAX_BY_SLOT[2]
        + [3] * MAX_BY_SLOT[3]
        + [4] * MAX_BY_SLOT[4]
    )
    random.shuffle(combat_slots)
    combat_genes = list(zip(combat_slots, combat_pool_spots))

    # Apertura inteligente: intercalar granjas con las primeras defensas
    opening = [
        farms[0],
        farms[1],
        combat_genes[0],
        farms[2],
        farms[3],
    ]
    rest = combat_genes[1:]
    random.shuffle(rest)
    return validate_and_repair_genome(opening + rest)


def evaluate_genome(
    env: TTDEndlessGymEnv,
    genome: List[Tuple[int, int]],
    prefer_farms_until_wave: int = 16,
) -> Tuple[int, float, int, List[Dict], List[Dict]]:
    """
    Simula una partida completa ejecutando el genoma en el entorno TTDEndlessGymEnv.
    Retorna:
      (oleada_alcanzada, dps_final_equipo, dinero_final, blueprint_history, final_placed_units)
    """
    env.reset()
    q = list(genome)

    last_info = {}
    while not env.terminated:
        # 1. Colocar todas las unidades de la cola en orden si el dinero alcanza
        placed_any = True
        while q and placed_any:
            slot, spot_idx = q[0]
            if env.can_place_unit(slot, spot_idx):
                env.place_unit_action(slot, spot_idx)
                q.pop(0)
            else:
                placed_any = False

        # 2. Si hay granjas ya colocadas y estamos ahorrando para una unidad cara (> $1000),
        #    o si ya terminamos de colocar las 17 unidades, mejorar unidades disponibles
        if not q:
            env.upgrade_cheapest_available(prefer_farms_until_wave=prefer_farms_until_wave)
        else:
            next_slot, _ = q[0]
            next_cost = env.units_catalog[next_slot]["levels"][0]["cost"]
            # Si ya hay al menos 2 granjas y una defensa en pista, mejorar granjas baratas acelera la economía
            if env.slot_counts[1] >= 2 and (env.slot_counts[2] + env.slot_counts[3] + env.slot_counts[4]) >= 1:
                for u in env.placed_units:
                    if u["slot"] == 1 and u["level"] < 4:
                        up_cost = env.units_catalog[1]["levels"][u["level"]]["cost"]
                        if env.money >= up_cost and (env.money - up_cost >= min(200, next_cost // 3)):
                            env.money -= up_cost
                            u["level"] += 1

        _, _, done, _, info = env.step_wave()
        last_info = info
        if done:
            break

    team_dps = env.compute_current_team_dps()
    frac = 0.0
    if last_info and "damage" in last_info and "wave_hp" in last_info:
        frac = min(0.999, max(0.0, float(last_info["damage"]) / max(1.0, float(last_info["wave_hp"]))))
    continuous_wave = float(env.wave) + frac
    return (
        continuous_wave,
        team_dps,
        env.money,
        copy.deepcopy(env.placement_history),
        copy.deepcopy(env.placed_units),
    )


# Instancia local por proceso para evaluaciones multihilo/multinúcleo
_worker_env: Optional[TTDEndlessGymEnv] = None


def _eval_worker(genome: List[Tuple[int, int]]) -> Tuple[float, float, int, List[Dict], List[Dict]]:
    global _worker_env
    if _worker_env is None:
        _worker_env = TTDEndlessGymEnv(max_waves=160)
    return evaluate_genome(_worker_env, genome)


def cx_ttd_genomes(ind1, ind2):
    """Operador de cruce genético DEAP con preservación de restricciones (4, 4, 5, 4)."""
    cut = random.randint(3, len(ind1) - 3)
    child1_raw = list(ind1[:cut]) + [g for g in ind2 if g not in ind1[:cut]]
    child2_raw = list(ind2[:cut]) + [g for g in ind1 if g not in ind2[:cut]]
    c1 = validate_and_repair_genome(child1_raw)
    c2 = validate_and_repair_genome(child2_raw)
    ind1[:] = c1
    ind2[:] = c2
    return ind1, ind2


def mut_ttd_genome(individual, indpb: float = 0.35):
    """
    Operador de mutación DEAP:
      - Intercambia el orden de colocación en la cola.
      - Cambia las coordenadas (spot_idx) de unidades de combate hacia otros nodos libres de piedra.
      - Intercambia las coordenadas de dos unidades de combate (ej. permutar Warlord y Mafia Boss).
    """
    g = list(individual)
    r = random.random()
    if r < 0.40 and len(g) > 4:
        # Permutar el orden de dos unidades (manteniendo la primera granja al inicio)
        i, j = random.sample(range(1, len(g)), 2)
        g[i], g[j] = g[j], g[i]
    elif r < 0.75:
        # Mover una unidad de combate a un nodo de piedra libre (4..23)
        used = {sp for _, sp in g}
        free_combat = [sp for sp in range(len(FARM_SPOTS), len(FARM_SPOTS) + len(COMBAT_SPOTS)) if sp not in used]
        combat_indices = [idx for idx, (sl, _) in enumerate(g) if sl != 1]
        if free_combat and combat_indices:
            idx = random.choice(combat_indices)
            sl, _ = g[idx]
            g[idx] = (sl, random.choice(free_combat))
    else:
        # Intercambiar los nodos (spots) entre dos unidades de combate de distinto tipo
        combat_indices = [idx for idx, (sl, _) in enumerate(g) if sl != 1]
        if len(combat_indices) >= 2:
            i, j = random.sample(combat_indices, 2)
            sl_i, sp_i = g[i]
            sl_j, sp_j = g[j]
            g[i] = (sl_i, sp_j)
            g[j] = (sl_j, sp_i)

    individual[:] = validate_and_repair_genome(g)
    return (individual,)


class TTDOptimizerTrainer:
    """
    Entrenador Generación tras Generación que combina DEAP (Algoritmo Genético)
    y Optuna (Optimización Bayesiana TPE) sobre TTDEndlessGymEnv.
    """

    def __init__(self, max_waves: int = 200, pop_size: int = 36, num_workers: int = 6):
        self.env = TTDEndlessGymEnv(max_waves=max_waves)
        self.pop_size = pop_size
        self.generation = 0
        self.stagnation_counter = 0
        self.num_workers = min(num_workers, max(1, (os.cpu_count() or 4) - 1))
        self.executor = ProcessPoolExecutor(max_workers=self.num_workers)

        # Estado del Campeón Histórico
        self.best_wave = 0.0
        self.best_dps = 0.0
        self.best_money = 0
        self.best_genome: List[Tuple[int, int]] = []
        self.best_blueprint: List[Dict] = []
        self.best_placed_units: List[Dict] = []
        self.history: List[Dict] = []

        # Configurar Toolbox de DEAP
        self.toolbox = deap_base.Toolbox()
        self.toolbox.register("individual", lambda: deap_creator.IndividualTTD(create_random_genome()))
        self.toolbox.register("population", deap_tools.initRepeat, list, self.toolbox.individual)
        self.toolbox.register("mate", cx_ttd_genomes)
        self.toolbox.register("mutate", mut_ttd_genome, indpb=0.35)
        self.toolbox.register("select", deap_tools.selTournament, tournsize=3)

        self.population = self.toolbox.population(n=self.pop_size)
        self.hof = deap_tools.HallOfFame(5)

        # Configurar Estudio Bayesiano de Optuna
        self.study = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=42, n_startup_trials=10),
        )

    def _update_champion(
        self,
        wave: float,
        dps: float,
        money: int,
        genome: List[Tuple[int, int]],
        bp: List[Dict],
        placed_units: List[Dict],
        source: str,
    ) -> bool:
        score_new = (round(wave, 3), round(dps, 1), money)
        score_cur = (round(self.best_wave, 3), round(self.best_dps, 1), self.best_money)
        if score_new > score_cur:
            self.best_wave = wave
            self.best_dps = dps
            self.best_money = money
            self.best_genome = copy.deepcopy(genome)
            self.best_blueprint = copy.deepcopy(bp)
            self.best_placed_units = copy.deepcopy(placed_units)
            return True
        return False

    def _optuna_trial_to_genome(self, trial: optuna.Trial) -> List[Tuple[int, int]]:
        """Construye un genoma guiado por el modelo probabilístico TPE de Optuna."""
        farms = [(1, i) for i in range(MAX_BY_SLOT[1])]
        total_combat = MAX_BY_SLOT[2] + MAX_BY_SLOT[3] + MAX_BY_SLOT[4]

        # Seleccionar prioridades para cada uno de los nodos de combate
        spot_priorities = []
        for sp in range(len(FARM_SPOTS), len(FARM_SPOTS) + len(COMBAT_SPOTS)):
            prio = trial.suggest_float(f"spot_prio_{sp}", 0.0, 1.0)
            spot_priorities.append((prio, sp))
        spot_priorities.sort(reverse=True)
        chosen_combat_spots = [sp for _, sp in spot_priorities[:total_combat]]

        # Asignar qué rol va en cada nodo elegido
        role_weights = []
        for idx in range(total_combat):
            w2 = trial.suggest_float(f"w_slot2_pos{idx}", 0.0, 1.0)
            w3 = trial.suggest_float(f"w_slot3_pos{idx}", 0.0, 1.0)
            w4 = trial.suggest_float(f"w_slot4_pos{idx}", 0.0, 1.0)
            role_weights.append((idx, w2, w3, w4))

        rem = {2: MAX_BY_SLOT[2], 3: MAX_BY_SLOT[3], 4: MAX_BY_SLOT[4]}
        combat_genes = []
        for idx, w2, w3, w4 in role_weights:
            options = [(w2, 2), (w3, 3), (w4, 4)]
            options.sort(reverse=True)
            picked_slot = next((sl for _, sl in options if rem[sl] > 0), 3)
            rem[picked_slot] -= 1
            combat_genes.append((picked_slot, chosen_combat_spots[idx]))

        genome = [
            farms[0],
            farms[1],
            combat_genes[0],
            farms[2],
            farms[3],
        ] + combat_genes[1:]
        return validate_and_repair_genome(genome)

    def step_generation(self, mode: str = "hybrid") -> Dict:
        """
        Ejecuta 1 generación completa de entrenamiento ('deap', 'optuna' o 'hybrid')
        y devuelve las métricas y el estado del campeón para actualizar la UI en vivo.
        """
        t0 = time.time()
        self.generation += 1
        gen_best_wave = 0
        gen_best_dps = 0.0
        improved = False
        eval_count = 0

        if mode in ("deap", "hybrid"):
            # Evaluar población DEAP en paralelo usando 6 núcleos
            results = list(self.executor.map(_eval_worker, self.population))
            for ind, (w, dps, money, bp, placed) in zip(self.population, results):
                ind.fitness.values = (float(w), float(dps), float(money))
                eval_count += 1
                if w > gen_best_wave or (w == gen_best_wave and dps > gen_best_dps):
                    gen_best_wave = w
                    gen_best_dps = dps
                if self._update_champion(w, dps, money, list(ind), bp, placed, "DEAP"):
                    improved = True

            self.hof.update(self.population)

            # Selección por Torneo + Elitismo + Cruce + Mutación (DEAP)
            offspring = self.toolbox.select(self.population, len(self.population) - len(self.hof))
            offspring = [self.toolbox.clone(ind) for ind in offspring]

            for child1, child2 in zip(offspring[::2], offspring[1::2]):
                if random.random() < 0.65:
                    self.toolbox.mate(child1, child2)
                    del child1.fitness.values
                    del child2.fitness.values

            for mutant in offspring:
                if random.random() < 0.45:
                    self.toolbox.mutate(mutant)
                    del mutant.fitness.values

            elites = [self.toolbox.clone(e) for e in self.hof]
            self.population[:] = elites + offspring

        if mode in ("optuna", "hybrid"):
            n_trials = 12 if mode == "hybrid" else self.pop_size
            trials = [self.study.ask() for _ in range(n_trials)]
            genomes = [self._optuna_trial_to_genome(t) for t in trials]
            opt_results = list(self.executor.map(_eval_worker, genomes))

            for trial, genome, (w, dps, money, bp, placed) in zip(trials, genomes, opt_results):
                score = float(w) * 1000.0 + (dps / 100_000.0)
                self.study.tell(trial, score)
                eval_count += 1

                if w > gen_best_wave or (w == gen_best_wave and dps > gen_best_dps):
                    gen_best_wave = w
                    gen_best_dps = dps
                if self._update_champion(w, dps, money, genome, bp, placed, "Optuna"):
                    improved = True
                    if self.population:
                        self.population[-1] = deap_creator.IndividualTTD(copy.deepcopy(genome))

        # Mecanismo Anti-Estancamiento: Si pasan 6 generaciones sin mejorar, inyectar diversidad
        if improved:
            self.stagnation_counter = 0
        else:
            self.stagnation_counter += 1
            if self.stagnation_counter >= 6:
                n_inject = max(6, len(self.population) // 3)
                for i in range(len(self.population) - n_inject, len(self.population)):
                    self.population[i] = deap_creator.IndividualTTD(create_random_genome())
                self.stagnation_counter = 0

        elapsed = time.time() - t0
        slot_summary = {1: 0, 2: 0, 3: 0, 4: 0}
        for item in self.best_blueprint:
            slot_summary[item["slot"]] = slot_summary.get(item["slot"], 0) + 1

        record = {
            "generation": self.generation,
            "mode": mode.upper(),
            "evals": eval_count,
            "elapsed_s": round(elapsed, 3),
            "gen_best_wave": int(gen_best_wave),
            "gen_best_dps": gen_best_dps,
            "champion_wave": int(self.best_wave),
            "champion_wave_fraction": round(self.best_wave, 2),
            "champion_dps": self.best_dps,
            "champion_money": self.best_money,
            "improved": improved,
            "slot_summary": slot_summary,
            "champion_blueprint": copy.deepcopy(self.best_blueprint),
            "champion_placed_units": copy.deepcopy(self.best_placed_units),
            "champion_genome": copy.deepcopy(self.best_genome),
        }
        self.history.append(record)
        return record

    def close(self):
        try:
            self.executor.shutdown(wait=False)
        except Exception:
            pass

    def save_champion_blueprint(self, target_paths: Optional[List[str]] = None) -> List[str]:
        """Guarda el mejor blueprint descubierto en 'gym/data/best_gym_blueprint.json' y opcionalmente en 'blueprint.json'."""
        if target_paths is None:
            target_paths = [
                os.path.join(DATA_DIR, "best_gym_blueprint.json"),
                os.path.join(PROJECT_ROOT, "blueprint.json"),
                os.path.join(PROJECT_ROOT, "strategies", "estrategia_gym_top1.json"),
            ]
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
            for item in self.best_blueprint
        ]
        saved = []
        for path in target_paths:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(clean_bp, f, indent=4, ensure_ascii=False)
            saved.append(path)
        return saved


def main(generations: int = 15, mode: str = "hybrid"):
    trainer = TTDOptimizerTrainer(max_waves=160, pop_size=32)
    print(f"Iniciando entrenamiento ({mode.upper()}) por {generations} generaciones...")
    print("Límites de inventario aplicados: 4 Granjas (S1), 4 Señor de la Guerra (S2), 5 Z1MP (S3), 4 Jefe Mafia (S4) = 17 máx.")
    t_start = time.time()
    for _ in range(generations):
        rec = trainer.step_generation(mode=mode)
        flag = "[* NUEVO RECORD]" if rec["improved"] else ""
        print(
            f"[Gen {rec['generation']:02d}] Oleada Campeón: W{rec['champion_wave']} | "
            f"DPS Equipo: {rec['champion_dps']:,.0f} | Dinero: ${rec['champion_money']:,} | "
            f"Tropas: S1={rec['slot_summary'][1]}, S2={rec['slot_summary'][2]}, "
            f"S3={rec['slot_summary'][3]}, S4={rec['slot_summary'][4]} ({rec['elapsed_s']:.2f}s) {flag}"
        )
    paths = trainer.save_champion_blueprint()
    print(f"\nEntrenamiento finalizado en {time.time() - t_start:.2f}s.")
    print(f"Campeón guardado en: {paths[0]}")


if __name__ == "__main__":
    main(generations=12, mode="hybrid")
