# -*- coding: utf-8 -*-
"""
Genera el archivo Excel completo 'ttd_datos_enemigos_y_unidades.xlsx' con:
  1. Enemigos_Fandom (141 enemigos con HP, categoría de velocidad, velocidad numérica estimada, habilidades, etc.)
  2. Jefes_Endless (curva oficial de HP de jefes de Oleada 10 a 190)
  3. Oleadas_Endless (estructura de las oleadas de Modo Infinito)
  4. Mis_4_Unidades (tablas nivel por nivel de tus 4 unidades equipadas en los slots 1, 2, 3 y 4)
  5. Tabla_Velocidades (conversión de categorías de velocidad de la Wiki a studs/s y px/s en el mapa)
"""
import json
import os
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
PROJECT_ROOT = os.path.dirname(ROOT)

SPEED_MAP = {
    "Very Slow":      {"studs_s": 4.0,  "px_s": 14.0, "time_track_s": 95.0, "desc": "Jefes gigantes (Boss Toilet, Giant Turkey, Mothership)"},
    "Slow":           {"studs_s": 6.5,  "px_s": 22.5, "time_track_s": 58.0, "desc": "Inodoros básicos y tanques pesados (Toilet, Large Toilet, Boss 4.0)"},
    "Average":        {"studs_s": 10.0, "px_s": 35.0, "time_track_s": 38.0, "desc": "Velocidad estándar (Spider Toilet, DJ Toilet, Mutant Toilet)"},
    "Fast":           {"studs_s": 15.0, "px_s": 52.0, "time_track_s": 25.0, "desc": "Rápidos (Small Toilet, Vacuum Toilet, Secutor Astro, Giant Smooth)"},
    "Very Fast":      {"studs_s": 22.0, "px_s": 76.0, "time_track_s": 17.0, "desc": "Muy rápidos (Assassin Toilet, Airplane Toilet, Dual Buzzsaw Car)"},
    "Extremely Fast": {"studs_s": 32.0, "px_s": 110.0,"time_track_s": 12.0, "desc": "Extremadamente rápidos (Cat Toilet, Phantom Toilet)"},
    "Maximal":        {"studs_s": 45.0, "px_s": 155.0,"time_track_s": 8.5,  "desc": "Velocidad máxima tras habilidad (Glitch Toilet post-Glitch Ram)"},
}


def style_sheet(ws, header_color="1F4E78"):
    header_fill = PatternFill(start_color=header_color, end_color=header_color, fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    thin = Side(border_style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.border = border
            if isinstance(cell.value, (int, float)):
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=False)

    ws.freeze_panes = "A2"
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = max((len(str(c.value or "")) for c in col[:60]), default=10)
        ws.column_dimensions[col_letter].width = max(12, min(42, max_len + 4))


def main():
    enemies = json.load(open(os.path.join(DATA, "enemies.json"), encoding="utf-8"))
    bosses = json.load(open(os.path.join(DATA, "endless_bosses.json"), encoding="utf-8"))
    waves = json.load(open(os.path.join(DATA, "endless_waves.json"), encoding="utf-8"))
    units_data = json.load(open(os.path.join(DATA, "units.json"), encoding="utf-8"))["units"]

    wb = openpyxl.Workbook()

    # 1. Hoja Enemigos_Fandom
    ws1 = wb.active
    ws1.title = "Enemigos_Fandom"
    ws1.append([
        "Nombre Enemigo",
        "Vida Base (HP)",
        "Texto Vida (Wiki)",
        "Categoría Velocidad",
        "Velocidad Estimada (studs/s)",
        "Velocidad Mapa (px/s)",
        "Tiempo Recorrido Pista (s)",
        "Texto Velocidad (Wiki)",
        "Oleada Debut",
        "Es Jefe",
        "Aturde Unidades",
        "Sale de Pista",
        "Modos",
        "Habilidades",
        "URL Wiki",
    ])

    for e in sorted(enemies, key=lambda x: (x["health"] is None, x["health"] or 0)):
        tier = e["speed_tier"] or "Average"
        s_info = SPEED_MAP.get(tier, SPEED_MAP["Average"])
        ws1.append([
            e["name"],
            e["health"] if e["health"] is not None else "Variable / No doc.",
            e["health_raw"] or "",
            e["speed_tier"] or "No doc. (Asumido Average)",
            s_info["studs_s"],
            s_info["px_s"],
            s_info["time_track_s"],
            e["speed_raw"] or "",
            e["wave_debut"] or "",
            "SÍ" if e["is_boss"] else "NO",
            "SÍ" if e["stuns_units"] else "NO",
            "SÍ" if e["off_track"] else "NO",
            e["modes"] or "",
            " | ".join(e["abilities"]) if e["abilities"] else "",
            e["url"],
        ])
    style_sheet(ws1, "1F4E78")

    # 2. Hoja Jefes_Endless
    ws2 = wb.create_sheet("Jefes_Endless")
    ws2.append(["Oleada", "Jefe (Boss)", "Vida Oficial en Endless (HP)", "Categoría Velocidad", "Velocidad (px/s)", "Aturde Unidades"])
    enemy_by_name = {e["name"]: e for e in enemies}
    for b in bosses:
        en = enemy_by_name.get(b["boss"], {})
        tier = en.get("speed_tier") or "Slow"
        s_info = SPEED_MAP.get(tier, SPEED_MAP["Slow"])
        ws2.append([
            b["wave"],
            b["boss"],
            b["hp"],
            tier,
            s_info["px_s"],
            "SÍ" if en.get("stuns_units") else "NO",
        ])
    style_sheet(ws2, "833C0C")

    # 3. Hoja Oleadas_Endless
    ws3 = wb.create_sheet("Oleadas_Endless")
    ws3.append(["Oleada", "Es Oleada Jefe", "Jefe de Oleada", "Composición de Enemigos", "HP Base Estimado Total", "Documentada en Wiki"])
    boss_hp_by_wave = {b["wave"]: b["hp"] for b in bosses}
    for w in waves:
        comp_parts = []
        total_hp = 0
        for item in w["enemies"]:
            cnt = item["count"] if item["count"] is not None else 1
            comp_parts.append(f"x{cnt} {item['label']}")
            en = enemy_by_name.get(item["enemy"], {})
            if en.get("health"):
                total_hp += cnt * en["health"]
        if w["boss"]:
            total_hp += boss_hp_by_wave.get(w["wave"], enemy_by_name.get(w["boss_page"], {}).get("health") or 0)
        ws3.append([
            w["wave"],
            "SÍ" if w["is_boss_wave"] else "NO",
            w["boss"] or "",
            ", ".join(comp_parts) if comp_parts else ("Solo Jefe" if w["no_normal_enemies"] else "Pendiente en Wiki"),
            total_hp if total_hp > 0 else "",
            "SÍ" if w["documented"] else "NO",
        ])
    style_sheet(ws3, "375623")

    # 4. Hoja Mis_4_Unidades
    ws4 = wb.create_sheet("Mis_4_Unidades")
    ws4.append([
        "Slot (Tecla)",
        "Unidad (Español)",
        "Nombre Wiki",
        "Shiny (+50% Daño / +10% Boost)",
        "Nivel",
        "Costo Nivel ($)",
        "Costo Acumulado ($)",
        "Daño por Golpe",
        "Cooldown (s)",
        "DPS Propio",
        "Rango (studs)",
        "Ingresos por Oleada ($)",
        "Boost Cooldown (%)",
        "Boost Daño (%)",
        "Salud Aliado Invocado",
        "DPS Aliado Invocado",
        "DPS Total Efectivo",
        "Eficiencia (DPS / $ Acumulado)",
    ])
    for u in units_data:
        cum_cost = 0
        for lv in u["levels"]:
            cum_cost += lv["cost"]
            dmg = lv.get("damage", 0)
            cd = lv.get("cooldown", 1.0)
            own_dps = round(dmg / cd, 1) if cd > 0 else 0
            ally_dps = lv.get("ally_dps", 0)
            total_dps = own_dps + ally_dps
            eff = round(total_dps / cum_cost, 3) if cum_cost > 0 else 0
            ws4.append([
                u["slot"],
                u["name_es"],
                u["name"],
                "SÍ" if u["shiny"] else "NO",
                lv["level"],
                lv["cost"],
                cum_cost,
                dmg,
                cd,
                own_dps,
                lv.get("range", 0),
                lv.get("income", 0),
                lv.get("cooldown_boost_pct", 0),
                lv.get("damage_boost_pct", 0),
                lv.get("ally_health", 0),
                ally_dps,
                total_dps,
                eff,
            ])
    style_sheet(ws4, "4A154B")

    # 5. Hoja Tabla_Velocidades
    ws5 = wb.create_sheet("Tabla_Velocidades")
    ws5.append(["Categoría en Wiki (Speed Tier)", "Velocidad (studs/s)", "Velocidad en Mapa 1366x768 (px/s)", "Tiempo en cruzar pista Endless (s)", "Ejemplos de Enemigos"])
    for tier, info in SPEED_MAP.items():
        ws5.append([tier, info["studs_s"], info["px_s"], info["time_track_s"], info["desc"]])
    style_sheet(ws5, "2F5597")

    out_root = os.path.join(PROJECT_ROOT, "ttd_datos_enemigos_y_unidades.xlsx")
    out_gym = os.path.join(DATA, "ttd_datos_enemigos_y_unidades.xlsx")
    wb.save(out_root)
    wb.save(out_gym)
    print(f"Excel generado con éxito en:\n  - {out_root}\n  - {out_gym}")


if __name__ == "__main__":
    main()

