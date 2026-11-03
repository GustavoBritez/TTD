# -*- coding: utf-8 -*-
"""
Scraper de la wiki de Toilet Tower Defense (Fandom) -> datos para el simulador (gym).

Descarga, vía la API oficial de MediaWiki (sin parsear HTML):
  1. Todos los enemigos (infobox: vida, velocidad, oleada de aparición, modos, habilidades).
  2. La vida por oleada que cada página documenta (secciones "Endless Mode", "Nightmare", etc.).
  3. La estructura de oleadas del Endless ("Endless Mode/Wave Structure").
  4. La lista de jefes del Endless con su vida ("Endless Mode").

Salida:
  gym/data/raw/*.wikitext          (caché de las páginas, para no volver a pedirlas)
  gym/data/enemies.json            (enemigos normalizados)
  gym/data/endless_waves.json      (composición de cada oleada)
  gym/data/enemy_wave_hp.json      (vida observada por oleada)
  gym/data/endless_bosses.json     (jefes cada 10 oleadas)

Uso:
  python gym/tools/scrape_wiki.py            # usa la caché si existe
  python gym/tools/scrape_wiki.py --refresh  # vuelve a descargar todo
"""
import json
import os
import re
import sys
import time

import mwparserfromhell
import requests

API = "https://toilet-tower-defense-game.fandom.com/api.php"
WIKI = "https://toilet-tower-defense-game.fandom.com/wiki/"
HEADERS = {"User-Agent": "Mozilla/5.0 (TTD-gym research scraper)"}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(DATA, "raw")

ENEMY_CATEGORIES = ["Category:Toilets", "Category:Enemies", "Category:Endless Bosses", "Category:Endless bosses"]
INFOBOX_NAMES = ("toilet_infobox", "toilet infobox", "character", "enemy infobox", "enemy_infobox")


# --------------------------------------------------------------------------------------
# Descarga
# --------------------------------------------------------------------------------------
def _get(params):
    params = dict(params, format="json")
    for attempt in range(4):
        try:
            r = requests.get(API, params=params, headers=HEADERS, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Fallo al consultar la API: {params}")


def category_members(cat):
    titles, cont = [], {}
    while True:
        d = _get({"action": "query", "list": "categorymembers", "cmtitle": cat, "cmlimit": 500, "cmnamespace": 0, **cont})
        titles += [m["title"] for m in d["query"]["categorymembers"]]
        if "continue" not in d:
            return titles
        cont = d["continue"]


def _cache_path(title):
    safe = re.sub(r'[<>:"/\\|?*]', "_", title)
    return os.path.join(RAW, safe + ".wikitext")


def fetch_pages(titles, refresh=False):
    """Devuelve {titulo_pedido: wikitext}. Sigue redirecciones. Pide 50 páginas por llamada."""
    out, pending = {}, []
    for t in titles:
        p = _cache_path(t)
        if not refresh and os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                out[t] = f.read()
        else:
            pending.append(t)

    for i in range(0, len(pending), 50):
        batch = pending[i:i + 50]
        d = _get({"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
                  "titles": "|".join(batch), "redirects": 1})
        q = d.get("query", {})
        alias = {t: t for t in batch}
        for n in q.get("normalized", []):
            alias[n["from"]] = n["to"]
        redirects = {r["from"]: r["to"] for r in q.get("redirects", [])}
        content = {}
        for page in q.get("pages", {}).values():
            if "revisions" in page:
                content[page["title"]] = page["revisions"][0]["slots"]["main"]["*"]
        for t in batch:
            final = alias.get(t, t)
            final = redirects.get(final, final)
            if final in content:
                out[t] = content[final]
                with open(_cache_path(t), "w", encoding="utf-8") as f:
                    f.write(content[final])
        time.sleep(0.3)
    return out


# --------------------------------------------------------------------------------------
# Normalización
# --------------------------------------------------------------------------------------
_SUFFIX = {"k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12}


def parse_number(text):
    """'835,000 HP [wave 50]' -> 835000 ; '1.6M' -> 1600000 ; '7.168.218 HP' -> 7168218."""
    if not text:
        return None
    m = re.search(r"(\d[\d.,]*)\s*([kKmMbBtT])?(?![a-zA-Z])", text)
    if not m:
        return None
    num, suf = m.group(1), (m.group(2) or "").lower()
    if suf and len(re.findall(r"[.,]", num)) >= 2:
        # '273.189.440M': el número ya está completo con separadores de miles; el sufijo es redundante
        return int(re.sub(r"[.,]", "", num))
    if suf:
        num = num.replace(",", ".") if num.count(",") == 1 and "." not in num else num.replace(",", "")
        try:
            return int(float(num) * _SUFFIX[suf])
        except ValueError:
            return None
    # Sin sufijo: '.' y ',' son separadores de miles (la wiki mezcla ambos formatos)
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", num):
        return int(re.sub(r"[.,]", "", num))
    try:
        return int(float(num.replace(",", "")))
    except ValueError:
        return None


SPEED_TIERS = [  # (tier, palabras clave) evaluadas en orden
    ("Maximal", ("maximal", "maximum", "max speed")),
    ("Extremely Fast", ("extremely fast", "super fast", "insanely fast", "very very fast")),
    ("Very Fast", ("very fast",)),
    ("Fast", ("fast", "quick")),
    ("Very Slow", ("very slow", "extremely slow")),
    ("Slow", ("slow",)),
    ("Average", ("average", "medium", "normal", "moderate", "decent", "mid")),
]


def speed_tier(text):
    if not text:
        return None
    first = text.strip().splitlines()[0].lower()
    for tier, keys in SPEED_TIERS:
        if any(k in first for k in keys):
            return tier
    return None


def clean(wikicode_text):
    """Quita plantillas/enlaces/HTML y deja texto legible."""
    if wikicode_text is None:
        return ""
    s = str(wikicode_text)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    code = mwparserfromhell.parse(s)
    for tpl in code.filter_templates(recursive=False):
        # {{Godly|X}} -> X ; {{Type|Stun}} -> Stun
        try:
            val = str(tpl.params[-1].value) if tpl.params else ""
            code.replace(tpl, val)
        except ValueError:
            pass
    txt = code.strip_code(normalize=True, collapse=True)
    txt = re.sub(r"<[^>]+>", "", txt)
    return re.sub(r"[ \t]+", " ", txt).strip()


# --------------------------------------------------------------------------------------
# Parsers de páginas
# --------------------------------------------------------------------------------------
def parse_enemies_index(wikitext):
    """Página 'Enemies': nombre -> {hp_index, tags}."""
    info = {}
    for line in wikitext.splitlines():
        names = re.findall(r"\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]", line)
        names = [n for n in names if not n.startswith(("(", ":")) and not n.lower().startswith(("file:", "category:"))]
        if not names:
            continue
        name = names[0].strip()
        hp = re.search(r"\[\[\(([^\]]*?)HP", line)
        tags = [t.strip() for t in re.findall(r"\{\{Type\|\s*([^}|]+)", line)]
        info[name] = {"hp_index": parse_number(hp.group(1)) if hp else None, "tags": sorted(set(tags))}
    return info


def find_infobox(code):
    for tpl in code.filter_templates():
        if str(tpl.name).strip().lower() in INFOBOX_NAMES:
            return tpl
    return None


def tparam(tpl, *names):
    for n in names:
        if tpl is not None and tpl.has(n):
            return str(tpl.get(n).value)
    return None


def parse_wave_lines(wikitext):
    """Recorre las secciones y extrae líneas 'Wave N ... X HP' junto con el modo (título de sección)."""
    rows, section = [], ""
    for raw in wikitext.splitlines():
        h = re.match(r"^\s*(=+)\s*(.*?)\s*=+\s*$", raw)
        if h:
            section = clean(h.group(2))
            continue
        line = clean(raw.lstrip("*#: "))
        m = re.match(r"^wave\s*(\d+)\b(.*)$", line, flags=re.I)
        if not m:
            continue
        wave, rest = int(m.group(1)), m.group(2)
        hp_m = re.search(r"(\d[\d.,]*\s*[kKmMbB]?)\s*HP", rest)
        cnt_m = re.search(r"(?:x\s*(\d+))|(?:(\d+)\s*x\b)|(?:^\s*:?\s*(\d+)\s+[A-Za-z])", rest)
        count = next((int(g) for g in (cnt_m.groups() if cnt_m else []) if g), None)
        rows.append({"section": section, "wave": wave, "hp": parse_number(hp_m.group(1)) if hp_m else None,
                     "count": count, "per_person": "per person" in rest.lower(), "raw": line})
    return rows


def parse_wave_structure(wikitext):
    waves = []
    for raw in wikitext.splitlines():
        m = re.match(r"^\*\s*'*\s*wave\s*(\d+)\s*:?(.*)$", raw.strip(), flags=re.I)
        if not m:
            continue
        wave, body = int(m.group(1)), m.group(2)
        boss_part = ""
        if re.search(r"Boss\s*:", body):
            body, boss_part = re.split(r"Boss\s*:", body, maxsplit=1)
        entries = []
        for cnt, name, label in re.findall(r"(?:[xх]\s*(\d+|\?)\s*)?\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", body):
            entries.append({"enemy": name.strip(), "label": (label or name).strip(),
                            "count": int(cnt) if cnt.isdigit() else None,
                            "count_known": cnt.isdigit()})
        boss = re.findall(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", boss_part)
        waves.append({
            "wave": wave,
            "is_boss_wave": bool(boss_part) or "'''" in raw,
            "boss": (boss[0][1] or boss[0][0]).strip() if boss else None,
            "boss_page": boss[0][0].strip() if boss else None,
            "no_normal_enemies": "no normal enemies" in body.lower(),
            "documented": bool(entries) or bool(boss) or "no normal enemies" in body.lower(),
            "enemies": entries,
        })
    return waves


def parse_endless_bosses(wikitext):
    out = []
    in_list = False
    for raw in wikitext.splitlines():
        if re.match(r"^==\s*Boss List\s*==", raw):
            in_list = True
            continue
        if in_list and raw.startswith("==") and "Boss List" not in raw:
            break
        if not in_list:
            continue
        m = re.search(r"Wave\s*(\d+)\s*-\s*\[\[([^\]|]+)(?:\|([^\]]+))?\]\]\s*-\s*([\d.,]+)\s*HP", raw)
        if m:
            out.append({"wave": int(m.group(1)), "boss": m.group(2).strip(), "hp": parse_number(m.group(4)),
                        "note": clean(raw[m.end():])})
    return out


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------
def main(refresh=False):
    os.makedirs(RAW, exist_ok=True)

    core = fetch_pages(["Enemies", "Endless Mode", "Endless Mode/Wave Structure"], refresh=refresh)
    index = parse_enemies_index(core["Enemies"])
    waves = parse_wave_structure(core["Endless Mode/Wave Structure"])
    bosses = parse_endless_bosses(core["Endless Mode"])

    titles = set(index)
    for cat in ENEMY_CATEGORIES:
        titles |= set(category_members(cat))
    for w in waves:
        titles |= {e["enemy"] for e in w["enemies"]}
        if w["boss_page"]:
            titles.add(w["boss_page"])
    titles |= {b["boss"] for b in bosses}
    titles = sorted(t for t in titles if not t.startswith("("))
    print(f"Páginas candidatas a enemigo: {len(titles)}")

    pages = fetch_pages(titles, refresh=refresh)
    print(f"Páginas descargadas: {len(pages)}")

    enemies, wave_hp = [], []
    for title in titles:
        wt = pages.get(title)
        if wt is None:
            continue
        code = mwparserfromhell.parse(wt)
        box = find_infobox(code)
        idx = index.get(title, {})
        if box is None and not idx.get("tags"):
            continue  # no es un enemigo (p.ej. página de categoría o de una unidad enlazada en el texto)
        health_raw = clean(tparam(box, "health", "hp"))
        speed_raw = clean(tparam(box, "speed"))
        abilities = [clean(p.value) for p in (box.params if box is not None else [])
                     if str(p.name).strip().lower().startswith("ability")]
        cats = re.findall(r"\[\[Category:([^\]|]+)", wt)
        rows = parse_wave_lines(wt)
        for r in rows:
            wave_hp.append({"enemy": title, **r})
        enemies.append({
            "name": title,
            "url": WIKI + title.replace(" ", "_"),
            "health_raw": health_raw,
            "health": parse_number(health_raw) or idx.get("hp_index"),
            "health_index_page": idx.get("hp_index"),
            "speed_raw": speed_raw,
            "speed_tier": speed_tier(speed_raw),
            "wave_debut": clean(tparam(box, "wave_debut", "debut")),
            "modes": clean(tparam(box, "modes")),
            "species": clean(tparam(box, "species")),
            "abilities": abilities,
            "tags": idx.get("tags", []),
            "is_boss": any("boss" in c.lower() for c in cats) or "Boss" in idx.get("tags", []),
            "stuns_units": any(c.strip().lower() == "stunners" for c in cats) or any("stun" in t.lower() for t in idx.get("tags", [])),
            "off_track": any("off-track" in c.lower() for c in cats),
            "categories": sorted(set(c.strip() for c in cats)),
            "endless_rows": sum(1 for r in rows if "endless" in r["section"].lower()),
        })

    def dump(name, obj):
        with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)

    dump("enemies.json", enemies)
    dump("endless_waves.json", waves)
    dump("enemy_wave_hp.json", wave_hp)
    dump("endless_bosses.json", bosses)
    print(f"Enemigos: {len(enemies)} | con vida: {sum(1 for e in enemies if e['health'])} | "
          f"con velocidad: {sum(1 for e in enemies if e['speed_tier'])}")
    print(f"Oleadas Endless: {len(waves)} (documentadas: {sum(w['documented'] for w in waves)}) | "
          f"filas vida/oleada: {len(wave_hp)} | jefes: {len(bosses)}")


if __name__ == "__main__":
    main(refresh="--refresh" in sys.argv)
