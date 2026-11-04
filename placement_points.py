# -*- coding: utf-8 -*-
"""
Puntos de colocación OFICIALES del usuario + Zona Segura.

Fuentes (pintadas a mano por el usuario):
  - templates/Mapa_Endless/Puntos_De_Colocacion/Puntos_de_unidades_Colocacion.png
      -> 17 círculos VERDES = únicos lugares donde la IA (GYM y Bot) puede colocar y alternar unidades.
         La captura está tomada con el personaje YA parado en la Zona Segura.
  - templates/Mapa_Endless/Zona Segura/Zona Segura.png
      -> Mancha VIOLETA = Zona Segura a la que el personaje debe llegar caminando (WASD).

Marcos de coordenadas:
  - "ref" : píxeles nativos de Puntos_de_unidades_Colocacion.png (1365x687).
  - "map" : coordenadas canónicas 1366x768 sobre la vista de Puntos_de_unidades_Colocacion.png
            (usadas tanto por el GYM como por el planificador visual de app.py).
  - pantalla en vivo: proyectadas por vision.py a partir del pozo central de lava en vivo (ancla).
"""
import json
import os
from typing import Dict, List, Optional

ROOT = os.path.dirname(os.path.abspath(__file__))
POINTS_PNG = os.path.join(
    ROOT, "templates", "Mapa_Endless", "Puntos_De_Colocacion", "Puntos_de_unidades_Colocacion.png"
)
SAFE_PNG = os.path.join(ROOT, "templates", "Mapa_Endless", "Zona Segura", "Zona Segura.png")
JSON_PATH = os.path.join(ROOT, "assets", "placement_points.json")

# Respaldo exacto de los 19 puntos verdes extraídos de Puntos_de_unidades_Colocacion.png (1365x687)
_FALLBACK_REF_POINTS = [
    [608.5, 118.5],  # P1
    [653.0, 197.0],  # P2
    [725.0, 207.0],  # P3
    [588.0, 279.0],  # P4
    [718.0, 284.0],  # P5
    [387.0, 354.0],  # P6
    [516.0, 354.0],  # P7
    [599.0, 358.0],  # P8
    [718.0, 345.0],  # P9
    [694.0, 388.0],  # P10
    [766.0, 394.0],  # P11
    [394.5, 435.5],  # P12
    [597.0, 413.0],  # P13
    [550.0, 458.5],  # P14
    [633.0, 462.0],  # P15
    [715.0, 470.0],  # P16
    [380.5, 515.5],  # P17
    [513.0, 555.0],  # P18
    [587.0, 559.0],  # P19
]
_FALLBACK = {
    "ref_viewport": [1365, 687],
    "ref_pool": [641.5, 365.0],
    "points": _FALLBACK_REF_POINTS,
    "safe_zone": {"offset_from_pool": [0.0, 0.0], "radius": 42.6, "source_height": 683},
}


def _detect_green_points(img) -> List[List[float]]:
    import cv2
    import numpy as np

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, np.array([45, 120, 100]), np.array([80, 255, 255]))
    n, _, st, cen = cv2.connectedComponentsWithStats(green)
    pts = []
    for i in range(1, n):
        area = st[i, cv2.CC_STAT_AREA]
        bw, bh = st[i, cv2.CC_STAT_WIDTH], st[i, cv2.CC_STAT_HEIGHT]
        if 120 < area < 1200 and 0.7 < bw / float(bh) < 1.4 and area / float(bw * bh) > 0.6:
            pts.append([round(float(cen[i][0]), 1), round(float(cen[i][1]), 1)])
    pts.sort(key=lambda p: (round(p[1] / 25.0), p[0]))
    return pts


def _safe_zone_from_png() -> Optional[Dict]:
    import cv2
    import numpy as np

    if not os.path.exists(SAFE_PNG):
        return None
    img = cv2.imread(SAFE_PNG, cv2.IMREAD_COLOR)
    if img is None:
        return None
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    purple = cv2.inRange(hsv, np.array([135, 60, 80]), np.array([165, 255, 255]))
    n, lab, st, cen = cv2.connectedComponentsWithStats(purple)
    if n <= 1:
        return None
    big = max(range(1, n), key=lambda i: st[i, cv2.CC_STAT_AREA])
    pcx, pcy = float(cen[big][0]), float(cen[big][1])
    radius = float(np.sqrt(st[big, cv2.CC_STAT_AREA] / np.pi))

    lava = cv2.inRange(hsv, np.array([12, 130, 150]), np.array([38, 255, 255]))
    union = cv2.bitwise_or(lava, (lab == big).astype(np.uint8) * 255)
    n2, lab2, st2, cen2 = cv2.connectedComponentsWithStats(union)
    comp = lab2[int(pcy), int(pcx)]
    h = img.shape[0]
    if comp > 0 and st2[comp, cv2.CC_STAT_AREA] < 40000:
        pool_x, pool_y = float(cen2[comp][0]), float(cen2[comp][1])
    else:
        pool_x, pool_y = pcx, pcy
    return {
        "offset_from_pool": [round(pcx - pool_x, 1), round(pcy - pool_y, 1)],
        "radius": round(radius, 1),
        "source_height": int(h),
    }


def build_placement_config(vision=None, save: bool = True) -> Dict:
    """Extrae los 17 puntos verdes, el pozo central de referencia y la Zona Segura."""
    import cv2

    img = cv2.imread(POINTS_PNG, cv2.IMREAD_COLOR)
    if img is None:
        return _fallback_config()
    h, w = img.shape[:2]
    points = _detect_green_points(img)
    if len(points) < 5:
        points = list(_FALLBACK_REF_POINTS)

    ref_pool = list(_FALLBACK["ref_pool"])
    if vision is not None:
        pt = vision.get_lava_center_from_image(cv2.resize(img, (1366, 768)))
        if pt:
            ref_pool = [round(pt[0] * w / 1366.0, 1), round(pt[1] * h / 768.0, 1)]

    sx = 1366.0 / float(w)
    sy = 768.0 / float(h)
    safe = _safe_zone_from_png() or dict(_FALLBACK["safe_zone"])

    cfg = {
        "ref_viewport": [int(w), int(h)],
        "ref_center": [w / 2.0, h / 2.0],
        "ref_pool": ref_pool,
        "points": [
            {
                "id": i + 1,
                "ref": p,
                "map": [int(round(p[0] * sx)), int(round(p[1] * sy))],
            }
            for i, p in enumerate(points)
        ],
        "safe_zone": safe,
        "source_mtimes": {
            "points_png": os.path.getmtime(POINTS_PNG) if os.path.exists(POINTS_PNG) else 0,
            "safe_png": os.path.getmtime(SAFE_PNG) if os.path.exists(SAFE_PNG) else 0,
        },
    }
    if save:
        os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)
        with open(JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    return cfg


def _fallback_config() -> Dict:
    w, h = _FALLBACK["ref_viewport"]
    sx, sy = 1366.0 / float(w), 768.0 / float(h)
    return {
        "ref_viewport": [w, h],
        "ref_center": [w / 2.0, h / 2.0],
        "ref_pool": list(_FALLBACK["ref_pool"]),
        "points": [
            {
                "id": i + 1,
                "ref": p,
                "map": [int(round(p[0] * sx)), int(round(p[1] * sy))],
            }
            for i, p in enumerate(_FALLBACK["points"])
        ],
        "safe_zone": dict(_FALLBACK["safe_zone"]),
        "source_mtimes": {},
    }


def _is_stale(cfg: Dict) -> bool:
    mt = cfg.get("source_mtimes", {})
    try:
        if os.path.exists(POINTS_PNG) and os.path.getmtime(POINTS_PNG) > mt.get("points_png", 0) + 1:
            return True
        if os.path.exists(SAFE_PNG) and os.path.getmtime(SAFE_PNG) > mt.get("safe_png", 0) + 1:
            return True
    except OSError:
        pass
    return False


def load_placement_config(auto_rebuild: bool = False, vision=None) -> Dict:
    cfg = None
    if os.path.exists(JSON_PATH):
        try:
            with open(JSON_PATH, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = None
    if auto_rebuild and (cfg is None or _is_stale(cfg)):
        try:
            cfg = build_placement_config(vision=vision, save=True)
        except Exception:
            pass
    return cfg or _fallback_config()


def map_spots(cfg: Optional[Dict] = None) -> List[tuple]:
    """Lista [(map_x, map_y)] de los 17 puntos oficiales del usuario en el marco 1366x768 (índice = id - 1)."""
    cfg = cfg or load_placement_config()
    return [(int(p["map"][0]), int(p["map"][1])) for p in cfg["points"] if p.get("map")]


def nearest_point_id(map_x: float, map_y: float, cfg: Optional[Dict] = None, exclude=()) -> Optional[int]:
    """ID (1..17) del punto oficial más cercano a (map_x, map_y)."""
    cfg = cfg or load_placement_config()
    best, best_d = None, None
    for p in cfg["points"]:
        if p["id"] in exclude or not p.get("map"):
            continue
        d = (p["map"][0] - map_x) ** 2 + (p["map"][1] - map_y) ** 2
        if best_d is None or d < best_d:
            best, best_d = p["id"], d
    return best


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ROOT)
    from vision import VisionSystem

    c = build_placement_config(vision=VisionSystem(), save=True)
    print(f"{len(c['points'])} puntos oficiales | pozo ref={c['ref_pool']} | zona segura={c['safe_zone']}")
    for p in c["points"]:
        print(f"  P{p['id']:02d} ref={p['ref']} map_1366x768={p['map']}")
    print("Guardado en", JSON_PATH)
