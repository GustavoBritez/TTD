import cv2
import numpy as np
import mss
import os
import re
import pytesseract

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

# Asegurar ruta de Tesseract en Windows si no est en PATH
TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe")
]
for t_path in TESSERACT_PATHS:
    if os.path.exists(t_path):
        pytesseract.pytesseract.tesseract_cmd = t_path
        break

class VisionSystem:
    def __init__(self):
        self.sct = mss.mss()

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
        template = cv2.imread(path, cv2.IMREAD_COLOR)
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

    def read_money_from_crop(self, crop) -> int:
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

            debug_path = os.path.join(os.path.dirname(__file__), "debug_money_ocr.png")
            cv2.imwrite(debug_path, padded)

            custom_config = r'--psm 7 -c tessedit_char_whitelist=0123456789'
            text = pytesseract.image_to_string(padded, config=custom_config)
            nums = re.findall(r'\d+', text)
            if nums:
                return int("".join(nums))
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

    def find_book_icon(self):
        """Busca el icono azul del libro 'Unidades' para abrir el Gerente de Unidad."""
        res = self.find_template("book_unidades_clean.png", threshold=0.70)
        if res is None:
            res = self.find_template("book_unidades.png", threshold=0.65)
        return res

    def find_all_upgrade_buttons(self, screen=None) -> list:
        """
        Detecta TODOS los botones verdes 'Mejora' visibles dentro del Gerente de Unidad,
        lee el costo aproximado debajo de cada botón ($200, $1300, $3000, etc.) y devuelve
        una lista de diccionarios [{'x': cx, 'y': cy, 'cost': cost}, ...] ordenada de menor
        a mayor costo para mejorar todas las unidades disponibles de forma distribuida.
        Ignora por completo los botones rojos ('Vender') y las unidades en nivel máximo (Nivel 8).
        """
        upgrades = []
        try:
            if screen is None:
                screen = self.grab_screen()
            sh, sw = screen.shape[:2]
            if sw > 600 and sh > 500:
                rx1, rx2 = int(sw * 0.15), int(sw * 0.85)
                ry1, ry2 = int(sh * 0.14), int(sh * 0.85)
            else:
                rx1, rx2, ry1, ry2 = 0, sw, 0, sh

            roi = screen[ry1:ry2, rx1:rx2]
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            green_mask = cv2.inRange(hsv, np.array([38, 110, 110]), np.array([85, 255, 255]))
            cnts, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for c in cnts:
                area = cv2.contourArea(c)
                if 350 <= area <= 5000:
                    x, y, w, h = cv2.boundingRect(c)
                    btn_h = min(h, 27)
                    aspect = w / float(btn_h) if btn_h > 0 else 0
                    if 1.6 <= aspect <= 3.5:
                        btn_hsv = hsv[y:y + btn_h, x:x + w]
                        white_in_btn = np.count_nonzero((btn_hsv[:, :, 1] < 70) & (btn_hsv[:, :, 2] > 190))
                        white_ratio = white_in_btn / float(w * btn_h)
                        if 0.12 <= white_ratio <= 0.65:
                            cy1 = max(0, y + btn_h - 3)
                            cy2 = min(roi.shape[0], y + btn_h + 14)
                            cx1 = max(0, x + 3)
                            cx2 = min(roi.shape[1], x + w - 14)
                            cost_val = 200
                            if cy2 > cy1 and cx2 > cx1:
                                cost_roi = roi[cy1:cy2, cx1:cx2]
                                cost_large = cv2.resize(cost_roi, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
                                chsv = cv2.cvtColor(cost_large, cv2.COLOR_BGR2HSV)
                                cwhite = ((chsv[:, :, 1] < 80) & (chsv[:, :, 2] > 165)).astype(np.uint8) * 255
                                nl, lbls, stats, _ = cv2.connectedComponentsWithStats(cwhite)
                                comps = [(stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_WIDTH], i) for i in range(1, nl) if stats[i, cv2.CC_STAT_AREA] >= 10]
                                comps.sort()
                                if comps:
                                    fx, fw, flbl = comps[0]
                                    if fw <= 22 and len(comps) >= 2:
                                        cwhite[lbls == flbl] = 0
                                    else:
                                        cwhite[:, :fx + 16] = 0
                                cbw = cv2.bitwise_not(cwhite)
                                cpad = cv2.copyMakeBorder(cbw, 15, 15, 15, 15, cv2.BORDER_CONSTANT, value=255)
                                txt = pytesseract.image_to_string(cpad, config=r'--psm 7 -c tessedit_char_whitelist=0123456789')
                                nums = re.findall(r'\d+', txt)
                                if nums:
                                    parsed = int("".join(nums))
                                    if 50 <= parsed <= 100000:
                                        cost_val = parsed
                            real_cx = rx1 + x + w // 2
                            real_cy = ry1 + y + btn_h // 2
                            upgrades.append({"x": real_cx, "y": real_cy, "cost": cost_val})

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
        Detecta EXCLUSIVAMENTE el pozo central de lava con rocas dentro de la isla de piedra,
        ignorando por completo el mar de lava gigante que rodea el mapa exterior.
        """
        h, w = bgr_img.shape[:2]
        hsv = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)

        # 1. Aislar la plataforma central de piedra oscura + camino negro
        # La piedra y pista tienen brillo bajo/medio y saturación baja (a diferencia de la lava brillante)
        stone_mask = ((hsv[:, :, 1] < 110) & (gray > 10) & (gray < 135)).astype(np.uint8) * 255
        stone_mask[:int(h * 0.10), :] = 0
        stone_mask[int(h * 0.84):, :] = 0

        # Cerrar huecos pequeños para obtener el polígono envolvente (Convex Hull) de toda la isla de piedra
        kernel_close = np.ones((21, 21), np.uint8)
        stone_closed = cv2.morphologyEx(stone_mask, cv2.MORPH_CLOSE, kernel_close)
        contours_stone, _ = cv2.findContours(stone_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        island_interior_mask = np.zeros((h, w), dtype=np.uint8)
        if contours_stone:
            # Tomar el contorno más grande (la isla principal del mapa) y su Convex Hull
            largest_stone = max(contours_stone, key=cv2.contourArea)
            hull = cv2.convexHull(largest_stone)
            cv2.drawContours(island_interior_mask, [hull], -1, 255, thickness=cv2.FILLED)
            # Erodir 35px hacia adentro para cortar cualquier contacto con el mar de lava exterior
            island_interior_mask = cv2.erode(island_interior_mask, np.ones((35, 35), np.uint8), iterations=1)

        # 2. Detectar píxeles de lava amarilla/naranja brillante
        lower_lava = np.array([12, 130, 150])
        upper_lava = np.array([38, 255, 255])
        lava_mask = cv2.inRange(hsv, lower_lava, upper_lava)

        # Quédate SOLO con la lava que está ADENTRO de la isla de piedra
        inner_lava = cv2.bitwise_and(lava_mask, island_interior_mask)
        inner_lava = cv2.morphologyEx(inner_lava, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))

        # 3. Buscar los parches internos de lava (el pozo central con rocas y la ranura izquierda)
        contours_lava, _ = cv2.findContours(inner_lava, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        valid_patches = []
        img_cx, img_cy = w // 2, h // 2

        for c in contours_lava:
            area = cv2.contourArea(c)
            # El pozo central de lava con rocas mide entre 1500 y 35000 px en 1366x768
            if 1200 < area < 40000:
                M = cv2.moments(c)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    # Priorizar el pozo que es más ancho/cuadrado (el central con rocas) sobre la ranura fina
                    x, y, cw, ch = cv2.boundingRect(c)
                    aspect_ratio = float(min(cw, ch)) / max(cw, ch) if max(cw, ch) > 0 else 0
                    dist_to_center = np.hypot(cx - img_cx, cy - img_cy)
                    score = (aspect_ratio * 2.0) - (dist_to_center / 500.0)
                    valid_patches.append((score, cx, cy, c))

        if valid_patches:
            valid_patches.sort(key=lambda item: item[0], reverse=True)
            _, best_cx, best_cy, best_c = valid_patches[0]

            if save_debug:
                dbg = bgr_img.copy()
                cv2.drawContours(dbg, [best_c], -1, (0, 255, 0), 3)
                cv2.circle(dbg, (best_cx, best_cy), 8, (0, 0, 255), -1)
                cv2.circle(dbg, (img_cx, img_cy), 8, (255, 0, 255), 2)
                cv2.line(dbg, (img_cx, img_cy), (best_cx, best_cy), (0, 255, 255), 2)
                cv2.imwrite(os.path.join(os.path.dirname(__file__), "debug_lava_center.png"), dbg)

            return (best_cx, best_cy)
        return None

    def find_reference_landmark(self):
        """Detecta en vivo el pozo central de lava con rocas y guarda debug_lava_center.png"""
        try:
            screen = self.grab_screen()
            if screen.shape[:2] != (768, 1366):
                screen = cv2.resize(screen, (1366, 768))
            return self.get_lava_center_from_image(screen, save_debug=True)
        except Exception:
            return None

    def get_base_map_lava_target(self):
        """
        Punto exacto de la pantalla (x, y) donde debe quedar ubicado el pozo central de lava
        para que el jugador quede parado justo al lado del centro de lava con rocas (como en la Foto 1).
        """
        default_map = os.path.join(os.path.dirname(__file__), "assets", "map_endless.jpg")
        if os.path.exists(default_map):
            base_img = cv2.imread(default_map, cv2.IMREAD_COLOR)
            if base_img is not None:
                base_resized = cv2.resize(base_img, (1366, 768))
                pt = self.get_lava_center_from_image(base_resized, save_debug=False)
                if pt:
                    return pt
        # En 1366x768, cuando el jugador está parado junto al pozo central con rocas (Foto 1),
        # el centroide del pozo de lava queda justo encima del personaje en (650, 350):
        return (650, 350)

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
        Calcula el desplazamiento (dx, dy) del mapa actual en pantalla respecto al mapa base de referencia
        debido al spawn aleatorio del personaje, utilizando OpenCV ORB Feature Matching.
        Soporta galera multi-ngulo de Mapa_Endless para mxima robustez ante diferentes rotaciones de cmara.
        Retorna (dx, dy) en pixeles.
        """
        try:
            screen = self.grab_screen()
            screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
            if screen_gray.shape[:2] != (768, 1366):
                screen_gray = cv2.resize(screen_gray, (1366, 768))

            orb = cv2.ORB_create(2000)
            kp_s, desc_s = orb.detectAndCompute(screen_gray, None)
            if desc_s is None:
                return (0, 0)

            matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

            candidates = []
            if base_map_path and os.path.exists(base_map_path):
                candidates.append(base_map_path)
            
            endless_dir = os.path.join(TEMPLATES_DIR, "Mapa_Endless")
            if os.path.exists(endless_dir):
                import glob
                angle_files = sorted(glob.glob(os.path.join(endless_dir, "*.png")))
                candidates.extend(angle_files[:5])
            
            default_map = os.path.join(os.path.dirname(__file__), "assets", "map_endless.jpg")
            if os.path.exists(default_map) and default_map not in candidates:
                candidates.append(default_map)

            best_overall_inliers = 0
            best_final_dx = 0
            best_final_dy = 0

            for cand_path in candidates:
                base_img = cv2.imread(cand_path, cv2.IMREAD_GRAYSCALE)
                if base_img is None:
                    continue
                base_resized = cv2.resize(base_img, (1366, 768))
                kp_b, desc_b = orb.detectAndCompute(base_resized, None)
                if desc_b is None:
                    continue

                matches = matcher.match(desc_s, desc_b)
                if len(matches) < 15:
                    continue

                matches = sorted(matches, key=lambda x: x.distance)
                top_matches = matches[:min(80, len(matches))]

                pts_s = np.float32([kp_s[m.queryIdx].pt for m in top_matches])
                pts_b = np.float32([kp_b[m.trainIdx].pt for m in top_matches])

                diffs = pts_s - pts_b
                median_dx = np.median(diffs[:, 0])
                median_dy = np.median(diffs[:, 1])

                inliers = np.sum((np.abs(diffs[:, 0] - median_dx) < 25) & (np.abs(diffs[:, 1] - median_dy) < 25))
                if inliers > best_overall_inliers:
                    best_overall_inliers = inliers
                    best_final_dx = int(median_dx)
                    best_final_dy = int(median_dy)

            if best_overall_inliers >= 10:
                return (best_final_dx, best_final_dy)
        except Exception:
            pass

        return (0, 0)

    def transform_blueprint_point(self, game_x: int, game_y: int) -> tuple:
        """
        Transforma una coordenada (game_x, game_y) del Blueprint (map_endless.jpg)
        a la pantalla en vivo actual corrigiendo TANTO traslación (dx, dy) COMO rotación de cámara.
        """
        try:
            default_map = os.path.join(os.path.dirname(__file__), "assets", "map_endless.jpg")
            if not os.path.exists(default_map):
                dx, dy = self.get_map_offset()
                return (game_x + dx, game_y + dy)

            screen = self.grab_screen()
            screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
            if screen_gray.shape[:2] != (768, 1366):
                screen_gray = cv2.resize(screen_gray, (1366, 768))

            base_img = cv2.imread(default_map, cv2.IMREAD_GRAYSCALE)
            base_gray = cv2.resize(base_img, (1366, 768))

            # Enmascarar la UI para que ORB solo compare las rocas y el camino del mapa
            mask = np.zeros((768, 1366), dtype=np.uint8)
            mask[95:630, 120:1240] = 255

            orb = cv2.ORB_create(3000)
            kp_b, desc_b = orb.detectAndCompute(base_gray, mask)
            kp_s, desc_s = orb.detectAndCompute(screen_gray, mask)

            if desc_b is not None and desc_s is not None and len(kp_b) > 20 and len(kp_s) > 20:
                matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
                matches = matcher.match(desc_b, desc_s)
                if len(matches) >= 12:
                    matches = sorted(matches, key=lambda x: x.distance)[:120]
                    pts_b = np.float32([kp_b[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
                    pts_s = np.float32([kp_s[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)

                    # Estimar matriz de Rotación + Traslación con RANSAC
                    M, inliers = cv2.estimateAffinePartial2D(pts_b, pts_s, method=cv2.RANSAC, ransacReprojThreshold=15.0)
                    if M is not None and np.sum(inliers) >= 8:
                        pt = np.array([[[float(game_x), float(game_y)]]], dtype=np.float32)
                        transformed = cv2.transform(pt, M)[0][0]
                        return (int( transformed[0] ), int( transformed[1] ))
        except Exception:
            pass

        dx, dy = self.get_map_offset()
        return (game_x + dx, game_y + dy)

