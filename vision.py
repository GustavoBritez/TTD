import cv2
import numpy as np
import mss
import os
import re
import pytesseract

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

import shutil

# Asegurar ruta de Tesseract en Windows si no está en PATH
TESSERACT_PATHS = [
    os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]
HAS_TESSERACT = False
for t_path in TESSERACT_PATHS:
    if os.path.exists(t_path):
        pytesseract.pytesseract.tesseract_cmd = t_path
        HAS_TESSERACT = True
        break
if not HAS_TESSERACT and shutil.which("tesseract"):
    HAS_TESSERACT = True

class VisionSystem:
    def __init__(self):
        self.sct = mss.mss()
        self.has_tesseract = HAS_TESSERACT
        self._template_cache = {}
        self._base_orb_kp = None
        self._base_orb_desc = None
        self._lava_ref_patches = self._load_lava_ref_patches()

    def _load_lava_ref_patches(self):
        """
        Pre-carga parches multiescala del pozo central triangular de lava con rocas
        para distinguir al 100% el pozo central (zona violeta) de la ranura izquierda y del mar exterior.
        """
        patches = []
        try:
            ref_candidates = [
                (os.path.join(TEMPLATES_DIR, "Mapa_Endless", "RobloxScreenShot20261101_231345796.png"), 643, 352),
                (os.path.join(os.path.dirname(__file__), "assets", "map_endless.jpg"), 937, 487),
            ]
            for path, cx, cy in ref_candidates:
                if os.path.exists(path):
                    img = cv2.imread(path, cv2.IMREAD_COLOR)
                    if img is not None:
                        img_r = cv2.resize(img, (1366, 768))
                        hw, hh = 95, 95
                        patch = img_r[max(0, cy - hh):min(768, cy + hh), max(0, cx - hw):min(1366, cx + hw)]
                        if patch.size > 0:
                            for s in (0.70, 0.80, 0.90, 1.0, 1.10):
                                tw = max(16, int(patch.shape[1] * s))
                                th = max(16, int(patch.shape[0] * s))
                                patches.append(cv2.resize(patch, (tw, th)))
                            break
        except Exception:
            pass
        return patches

    def grab_screen(self):
        """Captura toda la pantalla de forma ultrarrpida en formato OpenCV BGR"""
        monitor = self.sct.monitors[1]
        screenshot = np.array(self.sct.grab(monitor))
        return cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)

    def find_template(self, template_name_or_path: str, threshold: float = 0.70):
        """
        Busca una imagen de plantilla en la pantalla actual.
        Retorna (center_x, center_y) si se encuentra, o None.
        """
        if os.path.isabs(template_name_or_path):
            path = template_name_or_path
        else:
            path = os.path.join(TEMPLATES_DIR, template_name_or_path)

        if not os.path.exists(path):
            return None

        screen = self.grab_screen()
        if path not in self._template_cache:
            template = cv2.imread(path, cv2.IMREAD_COLOR)
            if template is not None:
                self._template_cache[path] = template
        else:
            template = self._template_cache[path]
        if template is None:
            return None

        h, w = template.shape[:2]
        res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        if max_val >= threshold:
            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2
            return (center_x, center_y)
        return None

    def read_money_from_crop(self, crop, save_debug: bool = False) -> int:
        """
        Extrae el valor numérico exacto de un recorte con el texto '$XXXX' de TTD:
        1. Usa el contorno verde para localizar la caja exacta del dinero (ignorando lava y carteles).
        2. Extrae el relleno BLANCO SÓLIDO interior de los dígitos (evitando letras huecas).
        3. Elimina automáticamente el primer componente izquierdo (el símbolo '$') para que
           Tesseract jamás confunda '$' con un '6', '5' u '8'.
        """
        try:
            crop_large = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            hsv = cv2.cvtColor(crop_large, cv2.COLOR_BGR2HSV)

            # 1. Máscara del borde verde para aislar la región exacta del texto '$XXXX'
            green_mask = cv2.inRange(hsv, np.array([35, 60, 80]), np.array([92, 255, 255]))
            cnts, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            valid_boxes = [cv2.boundingRect(c) for c in cnts if cv2.contourArea(c) > 25]
            if not valid_boxes:
                return -1

            x1 = max(0, min(bx for bx, by, bw, bh in valid_boxes) - 8)
            y1 = max(0, min(by for bx, by, bw, bh in valid_boxes) - 8)
            x2 = min(crop_large.shape[1], max(bx + bw for bx, by, bw, bh in valid_boxes) + 8)
            y2 = min(crop_large.shape[0], max(by + bh for bx, by, bw, bh in valid_boxes) + 8)

            roi_hsv = hsv[y1:y2, x1:x2]
            roi_green = green_mask[y1:y2, x1:x2]

            # 2. Extraer el relleno blanco sólido interior (baja saturación, alto brillo y sin borde verde)
            white_mask = ((roi_hsv[:, :, 1] < 55) & (roi_hsv[:, :, 2] > 205) & (roi_green == 0)).astype(np.uint8) * 255

            # Conservar únicamente componentes blancos rodeados por el borde verde
            green_dilated = cv2.dilate(roi_green, np.ones((5, 5), np.uint8), iterations=1)
            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(white_mask)
            clean_white = np.zeros_like(white_mask)
            char_boxes = []
            for lbl in range(1, num_labels):
                comp_mask = (labels == lbl).astype(np.uint8) * 255
                if stats[lbl, cv2.CC_STAT_AREA] >= 20 and np.any(cv2.bitwise_and(comp_mask, green_dilated)):
                    clean_white[labels == lbl] = 255
                    char_boxes.append((stats[lbl, cv2.CC_STAT_LEFT], stats[lbl, cv2.CC_STAT_WIDTH], lbl))

            if not char_boxes:
                return -1

            # 3. Ordenar de izquierda a derecha y eliminar el primer símbolo (siempre es '$')
            char_boxes.sort(key=lambda item: item[0])
            if len(char_boxes) >= 2:
                first_x, first_w, first_lbl = char_boxes[0]
                if first_w <= 65:
                    clean_white[labels == first_lbl] = 0

            digits_bw = cv2.bitwise_not(clean_white)
            padded = cv2.copyMakeBorder(digits_bw, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)

            if save_debug:
                debug_path = os.path.join(os.path.dirname(__file__), "debug_money_ocr.png")
                cv2.imwrite(debug_path, padded)

            custom_config = r'--psm 7 -c tessedit_char_whitelist=0123456789'
            text = pytesseract.image_to_string(padded, config=custom_config)
            nums = re.findall(r'\d+', text)
            if nums:
                return int("".join(nums))
            if len(char_boxes) == 2:
                return 0
        except Exception:
            pass
        return -1

    def read_money(self) -> int:
        """
        Lee el dinero actual en pantalla por encima de la hotbar.
        Devuelve el dinero exacto o -1 si no es visible.
        """
        try:
            screen = self.grab_screen()
            h, w = screen.shape[:2]
            crop = screen[int(h * 0.77):int(h * 0.89), int(w * 0.35):int(w * 0.65)]
            return self.read_money_from_crop(crop)
        except Exception:
            return -1

    def find_skip_button(self):
        """Busca el botón 'Saltar' en la barra superior (soporta clean y normal)."""
        res = self.find_template("btn_saltar_clean.png", threshold=0.70)
        if res is None:
            res = self.find_template("btn_saltar_oleada.png", threshold=0.65)
        return res

    def find_autoskip_red_button(self, screen=None):
        """
        Detecta específicamente el botón cuadrado ROJO de 'Saltar automáticamente'
        en la parte superior central de la pantalla.
        Si ya está en VERDE (activado), devuelve None para no desactivarlo.
        """
        try:
            if screen is None:
                screen = self.grab_screen()
            h, w = screen.shape[:2]

            # Zona superior central del HUD donde aparece 'Saltar automáticamente'
            x1, x2 = int(w * 0.38), int(w * 0.66)
            y1, y2 = int(h * 0.02), int(h * 0.15)
            roi = screen[y1:y2, x1:x2]

            # 1. Búsqueda por plantilla multi-escala del recuadro rojo + validación estricta de color rojo
            tpl_path = os.path.join(TEMPLATES_DIR, "btn_autoskip_red_box.png")
            if os.path.exists(tpl_path):
                tpl_box = cv2.imread(tpl_path, cv2.IMREAD_COLOR)
                if tpl_box is not None:
                    for scale in (1.0, 0.85, 1.15):
                        th = int(tpl_box.shape[0] * scale)
                        tw = int(tpl_box.shape[1] * scale)
                        if roi.shape[0] < th or roi.shape[1] < tw:
                            continue
                        tpl_s = cv2.resize(tpl_box, (tw, th)) if scale != 1.0 else tpl_box
                        res = cv2.matchTemplate(roi, tpl_s, cv2.TM_CCOEFF_NORMED)
                        _, max_val, _, max_loc = cv2.minMaxLoc(res)
                        if max_val >= 0.62:
                            cx = x1 + max_loc[0] + tw // 2
                            cy = y1 + max_loc[1] + th // 2
                            patch = screen[max(0, cy - 5):min(h, cy + 5), max(0, cx - 5):min(w, cx + 5)]
                            if patch.size > 0:
                                b, g, r = patch.mean(axis=(0, 1))
                                if r > 180 and g < 70 and b < 70:
                                    return (cx, cy)

            # 2. Respaldo por contorno cuadrado rojo sólido en HSV dentro del HUD superior
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            m1 = cv2.inRange(hsv, np.array([0, 160, 160]), np.array([8, 255, 255]))
            m2 = cv2.inRange(hsv, np.array([172, 160, 160]), np.array([180, 255, 255]))
            red_mask = cv2.bitwise_or(m1, m2)
            contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in sorted(contours, key=cv2.contourArea, reverse=True):
                area = cv2.contourArea(c)
                if 150 <= area <= 1200:
                    bx, by, bw, bh = cv2.boundingRect(c)
                    aspect = float(min(bw, bh)) / max(bw, bh) if max(bw, bh) > 0 else 0
                    solidity = area / float(bw * bh) if (bw * bh) > 0 else 0
                    if aspect >= 0.75 and solidity >= 0.75:
                        return (x1 + bx + bw // 2, y1 + by + bh // 2)
        except Exception:
            pass
        return None

    def find_book_icon(self, screen=None):
        """
        Busca el icono azul del libro 'Unidades' para abrir/cerrar el Gerente de Unidad.
        Combina:
        1. Plantilla multiescala del interior limpio del libro ('book_unidades_clean.png', inmune al fondo de lava o cadenas).
        2. Plantilla completa ('book_unidades.png').
        3. Respaldo por contorno azul celeste del libro en la zona inferior derecha del HUD.
        """
        try:
            if screen is None:
                screen = self.grab_screen()
            h, w = screen.shape[:2]

            # Restringir a la mitad inferior derecha donde reside el icono 'Unidades' (evita barra de tareas y chat superior)
            vx, vy, vw, vh = self.get_roblox_viewport()
            rx1 = max(0, int(vx + vw * 0.54))
            rx2 = min(w, int(vx + vw * 0.78))
            ry1 = max(0, int(vy + vh * 0.78))
            ry2 = min(h, int(vy + vh * 0.99))
            if rx2 <= rx1 + 40 or ry2 <= ry1 + 40:
                rx1, rx2 = int(w * 0.54), int(w * 0.78)
                ry1, ry2 = int(h * 0.78), int(h * 0.98)

            roi = screen[ry1:ry2, rx1:rx2]

            # 1. Búsqueda multiescala con book_unidades_clean.png (solo interior azul del libro, sin fondo exterior)
            clean_path = os.path.join(TEMPLATES_DIR, "book_unidades_clean.png")
            if os.path.exists(clean_path):
                if clean_path not in self._template_cache:
                    self._template_cache[clean_path] = cv2.imread(clean_path, cv2.IMREAD_COLOR)
                tpl_clean = self._template_cache[clean_path]
                if tpl_clean is not None:
                    best_val, best_pt = -1.0, None
                    for scale in (1.0, 1.10, 1.15, 1.20, 1.25, 0.90):
                        tw = max(12, int(round(tpl_clean.shape[1] * scale)))
                        th = max(12, int(round(tpl_clean.shape[0] * scale)))
                        if roi.shape[0] < th or roi.shape[1] < tw:
                            continue
                        tpl_s = cv2.resize(tpl_clean, (tw, th)) if scale != 1.0 else tpl_clean
                        res = cv2.matchTemplate(roi, tpl_s, cv2.TM_CCOEFF_NORMED)
                        _, max_val, _, max_loc = cv2.minMaxLoc(res)
                        if max_val > best_val:
                            best_val = float(max_val)
                            best_pt = (rx1 + max_loc[0] + tw // 2, ry1 + max_loc[1] + th // 2)
                    if best_val >= 0.64 and best_pt is not None:
                        return best_pt

            # 2. Plantilla completa book_unidades.png en la ROI
            full_path = os.path.join(TEMPLATES_DIR, "book_unidades.png")
            if os.path.exists(full_path):
                if full_path not in self._template_cache:
                    self._template_cache[full_path] = cv2.imread(full_path, cv2.IMREAD_COLOR)
                tpl_full = self._template_cache[full_path]
                if tpl_full is not None and roi.shape[0] >= tpl_full.shape[0] and roi.shape[1] >= tpl_full.shape[1]:
                    res = cv2.matchTemplate(roi, tpl_full, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(res)
                    if max_val >= 0.62:
                        return (rx1 + max_loc[0] + tpl_full.shape[1] // 2, ry1 + max_loc[1] + tpl_full.shape[0] // 2)

            # 3. Respaldo por contorno azul celeste del libro 'Unidades' dentro del HUD inferior derecho
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            blue_mask = cv2.inRange(hsv, np.array([95, 130, 160]), np.array([112, 255, 255]))
            cnts, _ = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in sorted(cnts, key=cv2.contourArea, reverse=True):
                area = cv2.contourArea(c)
                if 320 <= area <= 2500:
                    bx, by, bw, bh = cv2.boundingRect(c)
                    aspect = bw / float(bh) if bh > 0 else 0.0
                    if 0.65 <= aspect <= 1.35:
                        return (rx1 + bx + bw // 2, ry1 + by + bh // 2)
        except Exception:
            pass
        return None

    def is_unit_manager_open(self, screen=None) -> bool:
        """
        Verifica si la ventana central 'Gerente de unidad' está actualmente abierta en pantalla,
        detectando su barra horizontal blanca superior de separación o sus botones 'Mejora' activos.
        """
        try:
            if screen is None:
                screen = self.grab_screen()
            sh, sw = screen.shape[:2]
            if sw > 600 and sh > 500:
                rx1, rx2 = int(sw * 0.20), int(sw * 0.80)
                ry1, ry2 = int(sh * 0.08), int(sh * 0.35)
            else:
                rx1, rx2, ry1, ry2 = 0, sw, 0, int(sh * 0.25)

            roi = screen[ry1:ry2, rx1:rx2]
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            white_bar = ((hsv[:, :, 1] < 35) & (hsv[:, :, 2] > 215)).astype(np.uint8) * 255
            cnts, _ = cv2.findContours(white_bar, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in cnts:
                _, _, w, h = cv2.boundingRect(c)
                if w >= 200 and 2 <= h <= 14 and (w / float(h)) >= 22.0:
                    return True
        except Exception:
            pass
        return False

    def find_all_upgrade_buttons(self, screen=None) -> list:
        """
        Detecta TODOS los botones verdes 'Mejora' visibles dentro del Gerente de Unidad,
        valida que tengan a su derecha el botón rojo 'Vender' (descartando barras de vida del mapa),
        lee el costo debajo de cada botón en una sola llamada OCR por lotes y devuelve
        una lista [{'x': cx, 'y': cy, 'cost': cost}, ...] ordenada de menor a mayor costo.
        Ignora por completo los botones rojos ('Vender') y las unidades en nivel máximo (Nivel 8).
        """
        upgrades = []
        try:
            if screen is None:
                screen = self.grab_screen()
            sh, sw = screen.shape[:2]
            if sw > 600 and sh > 500:
                rx1, rx2 = int(sw * 0.15), int(sw * 0.85)
                ry1, ry2 = int(sh * 0.12), int(sh * 0.88)
            else:
                rx1, rx2, ry1, ry2 = 0, sw, 0, sh

            roi = screen[ry1:ry2, rx1:rx2]
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            green_mask = cv2.inRange(hsv, np.array([38, 100, 100]), np.array([85, 255, 255]))
            m1 = cv2.inRange(hsv, np.array([0, 110, 100]), np.array([10, 255, 255]))
            m2 = cv2.inRange(hsv, np.array([170, 110, 100]), np.array([180, 255, 255]))
            red_mask = cv2.bitwise_or(m1, m2)
            cnts, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            strips = []
            strip_h = 72

            for c in cnts:
                area = cv2.contourArea(c)
                if 250 <= area <= 14000:
                    x, y, w, h = cv2.boundingRect(c)
                    # Altura proporcional al ancho del botón (inmune a la resolución/escala de la ventana)
                    btn_h = max(12, min(h, int(round(w * 0.38))))
                    aspect = w / float(btn_h) if btn_h > 0 else 0.0
                    if 1.6 <= aspect <= 3.6:
                        btn_hsv = hsv[y:y + btn_h, x:x + w]
                        white_in_btn = np.count_nonzero((btn_hsv[:, :, 1] < 80) & (btn_hsv[:, :, 2] > 180))
                        white_ratio = white_in_btn / float(w * btn_h)

                        # Todo botón 'Mejora' dentro del Gerente de Unidad tiene su botón rojo 'Vender' a la derecha
                        rx_start = min(roi.shape[1], x + w)
                        rx_end = min(roi.shape[1], x + int(w * 2.3))
                        red_right = np.count_nonzero(red_mask[y:min(roi.shape[0], y + btn_h), rx_start:rx_end])

                        if 0.10 <= white_ratio <= 0.65 and red_right >= int(w * btn_h * 0.15):
                            cy1 = max(0, y + int(round(w * 0.34)))
                            cy2 = min(roi.shape[0], y + int(round(w * 0.56)))
                            cx1 = max(0, x + int(round(w * 0.04)))
                            cx2 = min(roi.shape[1], x + int(round(w * 0.78)))

                            if cy2 > cy1 and cx2 > cx1 and self.has_tesseract:
                                cost_roi = roi[cy1:cy2, cx1:cx2]
                                f_sc = 48.0 / float(max(1, cost_roi.shape[0]))
                                clarge = cv2.resize(cost_roi, None, fx=f_sc, fy=f_sc, interpolation=cv2.INTER_CUBIC)
                                if clarge.shape[0] != 48:
                                    clarge = cv2.resize(clarge, (clarge.shape[1], 48))
                                if clarge.shape[1] < 240:
                                    clarge = cv2.copyMakeBorder(
                                        clarge, 0, 0, 0, 240 - clarge.shape[1], cv2.BORDER_CONSTANT, value=(0, 0, 0)
                                    )
                                else:
                                    clarge = clarge[:, :240]
                                chsv = cv2.cvtColor(clarge, cv2.COLOR_BGR2HSV)
                                cwhite = ((chsv[:, :, 1] < 85) & (chsv[:, :, 2] > 160)).astype(np.uint8) * 255
                                nl, lbls, stats, _ = cv2.connectedComponentsWithStats(cwhite)
                                comps = [
                                    (stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_WIDTH], i)
                                    for i in range(1, nl)
                                    if stats[i, cv2.CC_STAT_AREA] >= 12
                                ]
                                comps.sort()
                                if comps:
                                    fx, fw, flbl = comps[0]
                                    if fw <= 26 and len(comps) >= 2:
                                        cwhite[lbls == flbl] = 0
                                    else:
                                        cwhite[:, :fx + 16] = 0
                                cbw = cv2.bitwise_not(cwhite)
                                cpad = cv2.copyMakeBorder(cbw, 12, 12, 16, 16, cv2.BORDER_CONSTANT, value=255)
                                strips.append(cpad)

                            real_cx = rx1 + x + w // 2
                            real_cy = ry1 + y + btn_h // 2
                            # Costo por defecto 1500 si OCR no distingue texto pequeño ($3000+), para que las granjas de $200 vayan primero
                            upgrades.append({"x": real_cx, "y": real_cy, "cost": 1500})

            if strips and len(strips) == len(upgrades) and self.has_tesseract:
                batch_img = np.vstack(strips)
                data = pytesseract.image_to_data(
                    batch_img,
                    config=r'--psm 6 -c tessedit_char_whitelist=0123456789',
                    output_type=pytesseract.Output.DICT,
                )
                by_idx = {}
                for txt, top in zip(data.get("text", []), data.get("top", [])):
                    nums = re.findall(r'\d+', str(txt))
                    if nums:
                        idx = min(len(upgrades) - 1, max(0, int(top) // strip_h))
                        by_idx.setdefault(idx, []).append("".join(nums))
                for idx, parts in by_idx.items():
                    parsed = int("".join(parts))
                    if 50 <= parsed <= 100000:
                        upgrades[idx]["cost"] = parsed

            upgrades.sort(key=lambda u: (u["cost"], u["y"] // 60, u["x"]))
        except Exception:
            pass
        return upgrades

    def find_upgrade_button(self):
        """Devuelve la mejora disponible más económica (compatibilidad con llamadas individuales)."""
        upgrades = self.find_all_upgrade_buttons()
        if upgrades:
            return (upgrades[0]["x"], upgrades[0]["y"])
        return None

    def find_close_button(self):
        """
        El botón rojo del Gerente de Unidad corresponde a 'VENDER', no a 'Salida'.
        Para evitar vender unidades por error, el menú se cierra alternando
        el icono del libro ('find_book_icon'). Retorna None.
        """
        return None

    def get_lava_center_from_image(self, bgr_img, save_debug: bool = False):
        """
        Detecta EXCLUSIVAMENTE el pozo central triangular de lava con rocas (zona violeta)
        dentro de la isla de piedra, descartando el mar de lava exterior y la ranura izquierda fina.
        """
        h, w = bgr_img.shape[:2]
        hsv = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)

        # 1. Máscara de lava brillante amarilla/naranja
        lava = cv2.inRange(hsv, np.array([12, 130, 150]), np.array([38, 255, 255]))

        # 2. Piso de la isla (piedra oscura + camino negro) y pista negra pura
        island_floor = ((bgr_img[:, :, 2] < 100) & (gray < 115)).astype(np.uint8)
        black_track = ((bgr_img[:, :, 2] < 25) & (gray < 28)).astype(np.uint8)

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(lava)
        candidates = []

        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if not (1500 <= area <= 15000):
                continue

            x = stats[i, cv2.CC_STAT_LEFT]
            y = stats[i, cv2.CC_STAT_TOP]
            cw = stats[i, cv2.CC_STAT_WIDTH]
            ch = stats[i, cv2.CC_STAT_HEIGHT]

            # Descartar lava que toca los bordes de la pantalla (mar de lava exterior)
            if x <= 8 or y <= 8 or (x + cw) >= w - 8 or (y + ch) >= h - 8:
                continue

            cx, cy = int(centroids[i][0]), int(centroids[i][1])
            if not (200 < cx < 1160 and 85 < cy < 660):
                continue

            # Verificar en una ventana expandida 45px alrededor del pozo que esté rodeado por piso de isla y pista
            bx1, by1 = max(0, x - 45), max(0, y - 45)
            bx2, by2 = min(w, x + cw + 45), min(h, y + ch + 45)
            non_lava_box = (lava[by1:by2, bx1:bx2] == 0)
            total_non_lava = max(1, np.count_nonzero(non_lava_box))

            floor_ratio = np.count_nonzero(island_floor[by1:by2, bx1:bx2] * non_lava_box) / float(total_non_lava)
            track_ratio = np.count_nonzero(black_track[by1:by2, bx1:bx2] * non_lava_box) / float(total_non_lava)

            if floor_ratio < 0.82 or not (0.06 <= track_ratio <= 0.42):
                continue

            # Evaluar similitud con el parche del pozo central triangular con rocas
            best_tm = 0.0
            if self._lava_ref_patches:
                roi_half = 125
                rx1, ry1 = max(0, cx - roi_half), max(0, cy - roi_half)
                rx2, ry2 = min(w, cx + roi_half), min(h, cy + roi_half)
                roi = bgr_img[ry1:ry2, rx1:rx2]
                best_tm = -1.0
                for sp in self._lava_ref_patches:
                    if roi.shape[0] >= sp.shape[0] and roi.shape[1] >= sp.shape[1]:
                        res = cv2.matchTemplate(roi, sp, cv2.TM_CCOEFF_NORMED)
                        _, max_val, _, _ = cv2.minMaxLoc(res)
                        if max_val > best_tm:
                            best_tm = float(max_val)

            wh = float(cw) / float(ch) if ch > 0 else 0.0
            # El pozo central triangular tiene wh ~ 0.72-1.05; la ranura izquierda fina tiene wh ~ 0.40-0.53
            aspect_bonus = 0.22 if (0.65 <= wh <= 1.15) else -0.22
            score = best_tm + aspect_bonus
            candidates.append((score, cx, cy, i))

        if candidates:
            # Si están visibles ambos pozos internos, dar bonus adicional al que está más a la derecha y arriba
            if len(candidates) >= 2:
                max_cx_minus_cy = max(c[1] - c[2] for c in candidates)
                candidates = [
                    (c[0] + (0.12 if (c[1] - c[2]) == max_cx_minus_cy else 0.0), c[1], c[2], c[3])
                    for c in candidates
                ]
            candidates.sort(key=lambda item: item[0], reverse=True)
            _, best_cx, best_cy, best_label = candidates[0]

            if save_debug:
                dbg = bgr_img.copy()
                comp_mask = (labels == best_label).astype(np.uint8) * 255
                cnts, _ = cv2.findContours(comp_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(dbg, cnts, -1, (0, 255, 0), 3)
                cv2.circle(dbg, (best_cx, best_cy), 8, (0, 0, 255), -1)
                tx, ty = self.get_base_map_lava_target()
                cv2.circle(dbg, (tx, ty), 8, (255, 0, 255), 2)
                cv2.line(dbg, (tx, ty), (best_cx, best_cy), (0, 255, 255), 2)
                cv2.imwrite(os.path.join(os.path.dirname(__file__), "debug_lava_center.png"), dbg)

            return (best_cx, best_cy)
        return None

    def find_reference_landmark(self, save_debug: bool = False):
        """Detecta en vivo el pozo central de lava con rocas y guarda debug_lava_center.png si se solicita"""
        try:
            screen = self.grab_screen()
            if screen.shape[:2] != (768, 1366):
                screen = cv2.resize(screen, (1366, 768))
            return self.get_lava_center_from_image(screen, save_debug=save_debug)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Zona Segura + Puntos de colocación oficiales del usuario
    # ------------------------------------------------------------------
    def get_placement_config(self):
        """Config de placement_points.py (puntos verdes + zona violeta), cacheada."""
        if getattr(self, "_placement_cfg", None) is None:
            try:
                from placement_points import load_placement_config
                self._placement_cfg = load_placement_config(auto_rebuild=True, vision=self)
            except Exception:
                from placement_points import _fallback_config
                self._placement_cfg = _fallback_config()
        return self._placement_cfg

    def reload_placement_config(self):
        self._placement_cfg = None
        return self.get_placement_config()

    def get_roblox_viewport(self):
        """
        Rectángulo (x, y, w, h) del área de juego de Roblox (client area, sin barra de título)
        en el espacio canónico 1366x768 de la captura. Si no se encuentra la ventana,
        se asume pantalla completa.
        """
        try:
            import win32gui
            mon = self.sct.monitors[1]
            sx = 1366.0 / float(mon["width"])
            sy = 768.0 / float(mon["height"])
            hwnds = []

            def _cb(hwnd, acc):
                if win32gui.IsWindowVisible(hwnd) and not win32gui.IsIconic(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title.strip().lower() == "roblox":
                        acc.append(hwnd)
            win32gui.EnumWindows(_cb, hwnds)
            if hwnds:
                fg = win32gui.GetForegroundWindow()
                hwnd = fg if fg in hwnds else hwnds[0]
                l, t, r, b = win32gui.GetClientRect(hwnd)
                x0, y0 = win32gui.ClientToScreen(hwnd, (0, 0))
                w, h = r - l, b - t
                if w > 200 and h > 200:
                    return ((x0 - mon["left"]) * sx, (y0 - mon["top"]) * sy, w * sx, h * sy)
        except Exception:
            pass
        return (0.0, 0.0, 1366.0, 768.0)

    def ref_to_screen(self, ref_x: float, ref_y: float, anchor_pool=None):
        """
        Convierte un punto del marco de referencia (captura Puntos_de_unidades_Colocacion.png)
        a la pantalla en vivo (espacio canónico 1366x768).
          - Con anchor_pool (posición en vivo del pozo central): punto = ancla + (p - pozo_ref) * k
          - Sin ancla: se usa el centro del viewport (el personaje siempre está en el centro).
        k = alto_viewport_vivo / alto_viewport_ref (el FOV vertical de Roblox es fijo).
        """
        cfg = self.get_placement_config()
        vx, vy, vw, vh = self.get_roblox_viewport()
        k = vh / float(cfg["ref_viewport"][1])
        if anchor_pool is not None:
            px, py = cfg["ref_pool"]
            return (int(round(anchor_pool[0] + (ref_x - px) * k)), int(round(anchor_pool[1] + (ref_y - py) * k)))
        cx, cy = cfg["ref_center"]
        return (int(round(vx + vw / 2.0 + (ref_x - cx) * k)), int(round(vy + vh / 2.0 + (ref_y - cy) * k)))

    def get_placement_point_screen(self, point_id: int, anchor_pool=None):
        """Coordenada de pantalla de un punto oficial (1..N)."""
        cfg = self.get_placement_config()
        for p in cfg["points"]:
            if int(p["id"]) == int(point_id):
                return self.ref_to_screen(p["ref"][0], p["ref"][1], anchor_pool)
        return None

    def get_safe_zone_status(self, pool_pt):
        """
        Indica si el personaje (centro del viewport) está dentro de la Zona Segura violeta,
        definida en 'Zona Segura.png' como offset+radio respecto al pozo central.
        Devuelve (dentro: bool, distancia_px: float).
        """
        cfg = self.get_placement_config()
        vx, vy, vw, vh = self.get_roblox_viewport()
        k = vh / float(cfg["ref_viewport"][1])
        sz = cfg.get("safe_zone", {})
        off = sz.get("offset_from_pool", [0.0, 0.0])
        radius = float(sz.get("radius", 43.0)) * k
        zx, zy = pool_pt[0] + off[0] * k, pool_pt[1] + off[1] * k
        d = float(np.hypot(vx + vw / 2.0 - zx, vy + vh / 2.0 - zy))
        # +15px: el personaje no puede pisar la lava, se para en el borde de la mancha violeta
        return d <= radius + 15.0 * k, d

    def get_base_map_lava_target(self):
        """
        Posición de pantalla (espacio 1366x768) donde debe verse el pozo central de lava
        cuando el personaje está parado en la Zona Segura, exactamente igual que en la
        captura de los Puntos de colocación del usuario.
        """
        try:
            cfg = self.get_placement_config()
            return self.ref_to_screen(cfg["ref_pool"][0], cfg["ref_pool"][1], anchor_pool=None)
        except Exception:
            return (645, 350)

    def is_in_game(self) -> bool:
        """
        Determina si termin la pantalla de carga y ya estamos dentro de la partida.
        Devuelve True si el icono del libro 'Unidades' est visible o si se detecta dinero.
        """
        return self.find_book_icon() is not None or self.read_money() > 0

    def find_replay_button(self):
        """
        Detecta el botn verde 'Jugar de nuevo' en la pantalla de derrota/victoria.
        Prioriza la plantilla exacta btn_jugar_nuevo.png con fallback a deteccin de contorno verde.
        """
        tpl_pt = self.find_template("btn_jugar_nuevo.png", threshold=0.70)
        if tpl_pt:
            return tpl_pt

        try:
            screen = self.grab_screen()
            h, w = screen.shape[:2]
            hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
            lower_green = np.array([35, 150, 150])
            upper_green = np.array([85, 255, 255])
            mask = cv2.inRange(hsv, lower_green, upper_green)

            mask_br = mask[int(h * 0.70):, int(w * 0.50):]
            contours, _ = cv2.findContours(mask_br, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in contours:
                if cv2.contourArea(c) > 600:
                    x, y, cw, ch = cv2.boundingRect(c)
                    real_x = int(w * 0.50) + x + cw // 2
                    real_y = int(h * 0.70) + y + ch // 2
                    return (real_x, real_y)
        except Exception:
            pass
        return None

    def is_autoskip_red(self, x: int, y: int, radius: int = 15) -> bool:
        """
        Verifica si la casilla de 'Saltar automticamente' est en rojo (desactivada).
        Si est roja, devuelve True para hacer clic y activarla a verde.
        """
        try:
            screen = self.grab_screen()
            h, w = screen.shape[:2]
            
            x1 = max(0, x - radius)
            y1 = max(0, y - radius)
            x2 = min(w, x + radius)
            y2 = min(h, y + radius)
            
            roi = screen[y1:y2, x1:x2]
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            
            mask1 = cv2.inRange(hsv, np.array([0, 120, 100]), np.array([10, 255, 255]))
            mask2 = cv2.inRange(hsv, np.array([170, 120, 100]), np.array([180, 255, 255]))
            red_pixels = np.count_nonzero(mask1) + np.count_nonzero(mask2)
            
            total_pixels = roi.shape[0] * roi.shape[1]
            if total_pixels > 0 and (red_pixels / total_pixels) > 0.15:
                return True
        except Exception:
            pass
        return False

    def get_track_placement_zones(self, screen=None):
        """
        Analiza el mapa en vivo identificando:
        1. La cinta/pista oscura donde caminan los enemigos.
        2. La lava circundante (prohibido colocar).
        3. La franja ptima de combate en piedra alrededor de la pista (25-50 px).
        """
        if screen is None:
            screen = self.grab_screen()
        h, w = screen.shape[:2]
        gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)

        # Lava (amarillo/naranja brillante)
        lava = cv2.inRange(hsv, (10, 100, 100), (35, 255, 255))
        lava_expanded = cv2.dilate(lava, np.ones((25, 25), np.uint8))

        # Pista oscura (canaleta por donde pasan los enemigos)
        track_raw = (gray < 25).astype(np.uint8) * 255
        track_raw[:int(h * 0.10), :] = 0
        track_raw[int(h * 0.86):, :] = 0
        track_raw[:, :int(w * 0.08)] = 0
        track_raw[:, int(w * 0.92):] = 0
        track_raw[lava_expanded > 0] = 0

        # Conectar segmentos de la pista
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        track = cv2.morphologyEx(track_raw, cv2.MORPH_CLOSE, kernel)

        # Franja construible adyacente a la pista
        track_dilated = cv2.dilate(track, np.ones((45, 45), np.uint8))
        strip = cv2.bitwise_and(track_dilated, cv2.bitwise_not(track))
        strip[lava_expanded > 0] = 0
        strip[:int(h * 0.10), :] = 0
        strip[int(h * 0.86):, :] = 0
        strip[:, :int(w * 0.08)] = 0
        strip[:, int(w * 0.92):] = 0

        return track, strip

    def snap_to_safe_strip(self, target_x: int, target_y: int, screen=None) -> tuple:
        """
        Verifica si (target_x, target_y) cae sobre lava o sobre la pista de enemigos.
        Si no es seguro, ajusta matemticamente el clic al punto de piedra seguro
        ms cercano en la franja adyacente a la cinta.
        """
        try:
            if screen is None:
                screen = self.grab_screen()
            _, strip = self.get_track_placement_zones(screen)
            h, w = strip.shape[:2]
            tx = max(0, min(w - 1, int(target_x)))
            ty = max(0, min(h - 1, int(target_y)))

            if strip[ty, tx] > 0:
                return tx, ty

            y_indices, x_indices = np.where(strip > 0)
            if len(x_indices) == 0:
                return tx, ty

            distances = (x_indices - tx)**2 + (y_indices - ty)**2
            nearest_idx = np.argmin(distances)
            return int(x_indices[nearest_idx]), int(y_indices[nearest_idx])
        except Exception:
            return int(target_x), int(target_y)

    def get_map_offset(self, base_map_path=None) -> tuple:
        """
        Calcula el desplazamiento (dx, dy) del mapa actual en pantalla respecto a assets/map_endless.jpg
        (sobre el cual están definidas las coordenadas de blueprint.json).
        Combina detección directa del pozo central triangular (937, 487 en map_endless.jpg) con ORB.
        """
        try:
            screen = self.grab_screen()
            if screen.shape[:2] != (768, 1366):
                screen = cv2.resize(screen, (1366, 768))

            # 1. Desplazamiento exacto usando el pozo central triangular de lava (en map_endless.jpg está en 937, 487)
            live_lava = self.get_lava_center_from_image(screen, save_debug=False)
            if live_lava is not None:
                return (int(live_lava[0] - 937), int(live_lava[1] - 487))

            # 2. Fallback con ORB respecto a assets/map_endless.jpg
            default_map = base_map_path or os.path.join(os.path.dirname(__file__), "assets", "map_endless.jpg")
            if os.path.exists(default_map):
                screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                base_img = cv2.imread(default_map, cv2.IMREAD_GRAYSCALE)
                if base_img is not None:
                    base_resized = cv2.resize(base_img, (1366, 768))
                    orb = cv2.ORB_create(2000)
                    kp_s, desc_s = orb.detectAndCompute(screen_gray, None)
                    kp_b, desc_b = orb.detectAndCompute(base_resized, None)
                    if desc_s is not None and desc_b is not None:
                        matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
                        matches = matcher.match(desc_s, desc_b)
                        if len(matches) >= 15:
                            matches = sorted(matches, key=lambda x: x.distance)[:80]
                            pts_s = np.float32([kp_s[m.queryIdx].pt for m in matches])
                            pts_b = np.float32([kp_b[m.trainIdx].pt for m in matches])
                            diffs = pts_s - pts_b
                            median_dx = np.median(diffs[:, 0])
                            median_dy = np.median(diffs[:, 1])
                            inliers = np.sum((np.abs(diffs[:, 0] - median_dx) < 25) & (np.abs(diffs[:, 1] - median_dy) < 25))
                            if inliers >= 10:
                                return (int(median_dx), int(median_dy))
        except Exception:
            pass

        return (0, 0)

    def transform_blueprint_point(self, game_x: int, game_y: int) -> tuple:
        """
        Transforma una coordenada (game_x, game_y) del Blueprint (map_endless.jpg)
        a la pantalla en vivo actual corrigiendo TANTO traslación (dx, dy) COMO rotación/escala de cámara.
        """
        try:
            default_map = os.path.join(os.path.dirname(__file__), "assets", "map_endless.jpg")
            if not os.path.exists(default_map):
                dx, dy = self.get_map_offset()
                return (game_x + dx, game_y + dy)

            screen = self.grab_screen()
            if screen.shape[:2] != (768, 1366):
                screen = cv2.resize(screen, (1366, 768))
            screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)

            orb = cv2.ORB_create(3000)
            mask = np.zeros((768, 1366), dtype=np.uint8)
            mask[95:630, 120:1240] = 255

            if self._base_orb_kp is None or self._base_orb_desc is None:
                base_img = cv2.imread(default_map, cv2.IMREAD_GRAYSCALE)
                if base_img is not None:
                    base_gray = cv2.resize(base_img, (1366, 768))
                    self._base_orb_kp, self._base_orb_desc = orb.detectAndCompute(base_gray, mask)

            kp_b, desc_b = self._base_orb_kp, self._base_orb_desc
            kp_s, desc_s = orb.detectAndCompute(screen_gray, mask)

            if desc_b is not None and desc_s is not None and len(kp_b) > 20 and len(kp_s) > 20:
                matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
                matches = matcher.match(desc_b, desc_s)
                if len(matches) >= 12:
                    matches = sorted(matches, key=lambda x: x.distance)[:120]
                    pts_b = np.float32([kp_b[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
                    pts_s = np.float32([kp_s[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)

                    # Estimar matriz de Rotación + Escala + Traslación con RANSAC
                    M, inliers = cv2.estimateAffinePartial2D(pts_b, pts_s, method=cv2.RANSAC, ransacReprojThreshold=15.0)
                    if M is not None and np.sum(inliers) >= 12:
                        pt = np.array([[[float(game_x), float(game_y)]]], dtype=np.float32)
                        transformed = cv2.transform(pt, M)[0][0]
                        return (int(transformed[0]), int(transformed[1]))
        except Exception:
            pass

        dx, dy = self.get_map_offset()
        return (game_x + dx, game_y + dy)

