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

    def read_money(self) -> int:
        """
        Lee el dinero actual aislando el color verde brillante ($XXXX) por encima de la hotbar.
        Filtra con HSV, binariza y genera 'debug_money_ocr.png'.
        Devuelve el dinero o -1 si falla.
        """
        try:
            screen = self.grab_screen()
            h, w = screen.shape[:2]

            # Recorte ajustado: solo la franja del dinero (arriba de los slots de tropas)
            crop = screen[int(h * 0.78):int(h * 0.88), int(w * 0.42):int(w * 0.58)]

            # Escalar x3 para que Tesseract lea perfecto los nmeros pequeos
            crop_large = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

            # Aislar el color verde claro/brillante del texto de dinero en TTD (HSV)
            hsv = cv2.cvtColor(crop_large, cv2.COLOR_BGR2HSV)
            lower_green = np.array([35, 60, 100])
            upper_green = np.array([95, 255, 255])
            mask = cv2.inRange(hsv, lower_green, upper_green)

            # Engrosar ligeramente las letras y poner texto negro sobre fondo blanco
            kernel = np.ones((2, 2), np.uint8)
            mask = cv2.dilate(mask, kernel, iterations=1)
            processed = cv2.bitwise_not(mask)

            # Guardar imagen de depuracin para verificar el recorte en vivo
            debug_path = os.path.join(os.path.dirname(__file__), "debug_money_ocr.png")
            cv2.imwrite(debug_path, processed)

            # PSM 7 = Tratar la imagen como una sola lnea de texto, solo dgitos
            custom_config = r'--psm 7 -c tessedit_char_whitelist=0123456789'
            text = pytesseract.image_to_string(processed, config=custom_config)

            nums = re.findall(r'\d+', text)
            if nums:
                full_num = "".join(nums)
                return int(full_num)
        except Exception as e:
            pass
        return -1

    def find_skip_button(self):
        """Busca el botn 'Saltar' en la barra superior (soporta clean y normal)."""
        res = self.find_template("btn_saltar_clean.png", threshold=0.70)
        if res is None:
            res = self.find_template("btn_saltar_oleada.png", threshold=0.65)
        return res

    def find_book_icon(self):
        """Busca el icono azul del libro 'Unidades' para abrir el Gerente de Unidad."""
        res = self.find_template("book_unidades_clean.png", threshold=0.70)
        if res is None:
            res = self.find_template("book_unidades.png", threshold=0.65)
        return res

    def find_upgrade_button(self):
        """Busca el botn verde 'Mejora' del Gerente de Unidad automticamente con OpenCV"""
        return self.find_template("btn_mejora.png", threshold=0.70)

    def find_close_button(self):
        """Busca el botn rojo 'Salida' del Gerente de Unidad automticamente con OpenCV"""
        res = self.find_template("btn_salida_clean.png", threshold=0.70)
        if res is None:
            res = self.find_template("btn_salida.png", threshold=0.65)
        return res

    def find_reference_landmark(self):
        """
        Detecta el portal amarillo superior para calibrar la posicin del personaje en el mapa.
        Retorna (center_x, center_y) del portal o None.
        """
        try:
            screen = self.grab_screen()
            hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
            lower_yellow = np.array([20, 180, 180])
            upper_yellow = np.array([35, 255, 255])
            mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
            
            h, w = screen.shape[:2]
            mask_top = mask[:int(h * 0.45), :]
            contours, _ = cv2.findContours(mask_top, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in sorted(contours, key=cv2.contourArea, reverse=True):
                if cv2.contourArea(c) > 100:
                    x, y, cw, ch = cv2.boundingRect(c)
                    return (x + cw // 2, y + ch // 2)
        except Exception:
            pass
        return None

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
