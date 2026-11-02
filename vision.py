import cv2
import numpy as np
import mss
import os
import re
import pytesseract

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

class VisionSystem:
    def __init__(self):
        self.sct = mss.mss()

    def grab_screen(self):
        """Captura toda la pantalla de forma ultrarrápida en formato OpenCV BGR"""
        monitor = self.sct.monitors[1]
        screenshot = np.array(self.sct.grab(monitor))
        return cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)

    def find_template(self, template_name_or_path: str, threshold: float = 0.75):
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
        Lee el dinero actual en pantalla mediante OCR en la zona inferior central.
        Detecta números como $300, $400, $2310 de forma robusta.
        """
        try:
            screen = self.grab_screen()
            h, w = screen.shape[:2]

            # Zona inferior central donde aparece el dinero
            crop = screen[int(h * 0.78):int(h * 0.94), int(w * 0.40):int(w * 0.58)]
            text = pytesseract.image_to_string(crop, config='--psm 6')
            nums = re.findall(r'\d+', text)
            if nums:
                for n in nums:
                    if len(n) >= 3:
                        return int(n)
                return int(nums[0])
        except Exception:
            pass
        return 0

    def find_skip_button(self):
        """Busca el botón 'Saltar' / 'Auto-Saltar' en la barra superior."""
        return self.find_template("btn_saltar_oleada.png", threshold=0.70)

    def find_book_icon(self):
        """Busca el icono azul del libro 'Unidades' automáticamente con OpenCV"""
        return self.find_template("book_unidades.png", threshold=0.75)

    def find_upgrade_button(self):
        """Busca el botón verde 'Mejora' del Gerente de Unidad automáticamente con OpenCV"""
        return self.find_template("btn_mejora.png", threshold=0.75)

    def find_close_button(self):
        """Busca el botón rojo 'Salida' del Gerente de Unidad automáticamente con OpenCV"""
        return self.find_template("btn_salida_clean.png", threshold=0.75)

    def find_reference_landmark(self):
        """
        Detecta el portal amarillo superior para calibrar la posición del personaje en el mapa.
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
        Determina si terminó la pantalla de carga y ya estamos dentro de la partida.
        Devuelve True si el icono del libro 'Unidades' está visible o si se detecta dinero.
        """
        return self.find_book_icon() is not None or self.read_money() > 0

    def find_replay_button(self):
        """
        Detecta el botón verde 'Jugar de nuevo' en la pantalla de derrota/victoria.
        Busca en el cuadrante inferior derecho el botón verde alargado.
        Retorna (center_x, center_y) o None.
        """
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
        Verifica si la casilla de 'Saltar automáticamente' está en rojo (desactivada).
        Si está roja, devuelve True para hacer clic y activarla a verde.
        Si ya está verde, devuelve False para no desactivarla.
        """
        try:
            screen = self.grab_screen()
            h, w = screen.shape[:2]
            x1 = max(0, x - radius)
            x2 = min(w, x + radius)
            y1 = max(0, y - radius)
            y2 = min(h, y + radius)
            crop = screen[y1:y2, x1:x2]

            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            lower_red1 = np.array([0, 150, 150])
            upper_red1 = np.array([10, 255, 255])
            lower_red2 = np.array([170, 150, 150])
            upper_red2 = np.array([180, 255, 255])
            mask_red = cv2.inRange(hsv, lower_red1, upper_red1) | cv2.inRange(hsv, lower_red2, upper_red2)
            
            return cv2.countNonZero(mask_red) > 20
        except Exception:
            pass
        return True

    def get_map_offset(self, base_map_path=None) -> tuple:
        """
        Calcula el desplazamiento (dx, dy) del mapa actual en pantalla respecto al mapa base de referencia
        debido al spawn aleatorio del personaje, utilizando OpenCV ORB Feature Matching.
        Soporta galería multi-ángulo de Mapa_Endless para máxima robustez ante diferentes rotaciones de cámara.
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

            # Lista de imágenes de referencia a probar (mapa base y ángulos tomados por el usuario)
            candidates = []
            if base_map_path and os.path.exists(base_map_path):
                candidates.append(base_map_path)
            
            endless_dir = os.path.join(TEMPLATES_DIR, "Mapa_Endless")
            if os.path.exists(endless_dir):
                import glob
                angle_files = sorted(glob.glob(os.path.join(endless_dir, "*.png")))
                candidates.extend(angle_files[:5]) # Primeras referencias angulares
            
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

                matches = matcher.match(desc_b, desc_s)
                if len(matches) < 15:
                    continue

                matches = sorted(matches, key=lambda x: x.distance)[:150]
                deltas = []
                for m in matches:
                    pt_b = kp_b[m.queryIdx].pt
                    pt_s = kp_s[m.trainIdx].pt
                    deltas.append((pt_s[0] - pt_b[0], pt_s[1] - pt_b[1]))
                import numpy as np
                deltas = np.array(deltas)

                best_dx, best_dy = 0, 0
                max_inliers = 0
                for d in deltas:
                    dist = np.sqrt((deltas[:,0] - d[0])**2 + (deltas[:,1] - d[1])**2)
                    inliers = np.sum(dist < 12.0)
                    if inliers > max_inliers:
                        max_inliers = inliers
                        best_dx, best_dy = d[0], d[1]

                if max_inliers > best_overall_inliers and max_inliers >= 8:
                    dist = np.sqrt((deltas[:,0] - best_dx)**2 + (deltas[:,1] - best_dy)**2)
                    inliers_mask = dist < 12.0
                    best_overall_inliers = max_inliers
                    best_final_dx = int(round(np.median(deltas[inliers_mask, 0])))
                    best_final_dy = int(round(np.median(deltas[inliers_mask, 1])))

            if best_overall_inliers >= 8:
                return (best_final_dx, best_final_dy)

        except Exception as e:
            print(f"Error al calcular offset del mapa con ORB multi-ángulo: {e}")
        return (0, 0)
