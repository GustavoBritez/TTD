import time
import pydirectinput
import pyautogui

# Desactivar pausas artificiales excesivas
pydirectinput.PAUSE = 0.05
pyautogui.PAUSE = 0.05

class GameController:
    BASE_WIDTH = 1366
    BASE_HEIGHT = 768

    def __init__(self):
        pass

    def scale_coords(self, x: int, y: int) -> tuple:
        """Convierte coordenadas del plano canónico 1366x768 a la resolución real del monitor"""
        sw, sh = pyautogui.size()
        if sw == self.BASE_WIDTH and sh == self.BASE_HEIGHT:
            return int(x), int(y)
        sx = int(round(x * (sw / float(self.BASE_WIDTH))))
        sy = int(round(y * (sh / float(self.BASE_HEIGHT))))
        return sx, sy

    def is_roblox_active(self) -> bool:
        """Verifica si la ventana activa en primer plano es Roblox"""
        try:
            import win32gui
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd).lower()
            return "roblox" in title
        except Exception:
            return True

    def focus_roblox(self) -> bool:
        """Intenta enfocar la ventana de Roblox si está en segundo plano"""
        try:
            import win32gui
            found_hwnds = []
            def enum_cb(hwnd, extra):
                if "roblox" in win32gui.GetWindowText(hwnd).lower():
                    extra.append(hwnd)
            win32gui.EnumWindows(enum_cb, found_hwnds)
            if found_hwnds:
                win32gui.SetForegroundWindow(found_hwnds[0])
                time.sleep(0.25)
                return True
        except Exception:
            pass
        return False

    def walk(self, key: str, duration: float = 0.15):
        """Presiona una tecla de movimiento (W, A, S, D) durante una duración específica"""
        pydirectinput.keyDown(key.lower())
        time.sleep(duration)
        pydirectinput.keyUp(key.lower())
        time.sleep(0.05)

    def click_at(self, x: int, y: int, delay: float = 0.2, auto_scale: bool = False):
        """Mueve el mouse con micro-desplazamiento relativo para activar el raycast 3D de Roblox"""
        if auto_scale:
            x, y = self.scale_coords(x, y)
        pydirectinput.moveTo(x, y)
        time.sleep(0.04)
        # Micro-jiggle de 2 píxeles: obligatorio en Roblox para que actualice el hover 3D en el suelo
        pydirectinput.moveRel(2, 2, relative=True)
        time.sleep(0.04)
        pydirectinput.moveRel(-2, -2, relative=True)
        time.sleep(0.06)
        pydirectinput.mouseDown()
        time.sleep(0.06)
        pydirectinput.mouseUp()
        time.sleep(delay)

    def select_slot(self, slot_number: int):
        """Presiona la tecla del slot (1, 2, 3, 4, 5)"""
        key = str(slot_number)
        pydirectinput.press(key)
        time.sleep(0.15)

    def rotate_unit(self):
        """Presiona la tecla R para rotar la unidad seleccionada antes de hacer clic"""
        pydirectinput.press('r')
        time.sleep(0.06)

    def place_unit(
        self,
        slot_number: int,
        x: int,
        y: int,
        auto_scale: bool = False,
        read_money_fn=None,
        initial_money: int = -1,
        max_r_clicks: int = 6,
        is_running_fn=None,
    ) -> tuple:
        """
        Selecciona la unidad y ejecuta R+CLICK repetidamente hasta confirmar que el dinero
        disminuyó (lo que garantiza al 100% que la unidad se colocó en el mapa sin falsos positivos).
        Retorna (colocada_con_exito: bool, nuevo_dinero: int, intentos_usados: int).
        """
        if auto_scale:
            x, y = self.scale_coords(x, y)

        if initial_money < 0 and read_money_fn is not None:
            initial_money = read_money_fn()

        # 1. Seleccionar el slot de la unidad (1..4)
        self.select_slot(slot_number)

        # Posicionar el mouse sobre el punto oficial antes de iniciar R+CLICK
        pydirectinput.moveTo(x, y)
        time.sleep(0.05)

        current_money = initial_money
        for attempt in range(1, max_r_clicks + 1):
            if is_running_fn is not None and not is_running_fn():
                return (False, current_money, attempt - 1)

            # 2. Apretar R (rotar unidad) + CLICK en el punto
            self.rotate_unit()
            self.click_at(x, y, delay=0.18, auto_scale=False)

            # 3. Verificar inmediatamente si el dinero disminuyó
            if read_money_fn is not None:
                new_money = read_money_fn()
                if new_money >= 0:
                    if initial_money < 0:
                        # Si antes no teníamos lectura OCR válida, tomamos esta como base
                        initial_money = new_money
                        current_money = new_money
                    elif new_money < initial_money:
                        # ¡El dinero disminuyó! La unidad ya se colocó -> detener R+CLICK inmediatamente
                        return (True, new_money, attempt)
                    else:
                        current_money = new_money
            else:
                return (True, current_money, attempt)

        # Si tras los intentos R+CLICK el dinero no disminuyó, cancelar selección para no dejar fantasma activo
        self.cancel_placement()
        return (False, current_money, max_r_clicks)

    def cancel_placement(self):
        """Presiona X para cancelar la selección de colocar tropas"""
        pydirectinput.press('x')
        time.sleep(0.05)

    def upgrade_unit_at(self, unit_x: int, unit_y: int, upgrade_btn_x: int, upgrade_btn_y: int, auto_scale: bool = False):
        """Mejora una unidad haciendo clic en su posición en el mapa y luego en el botón de mejora"""
        self.click_at(unit_x, unit_y, delay=0.25, auto_scale=auto_scale)
        self.click_at(upgrade_btn_x, upgrade_btn_y, delay=0.2, auto_scale=auto_scale)
        self.cancel_placement()

    def upgrade_via_manager(self, book_x: int, book_y: int, upgrade_x: int, upgrade_y: int, close_x: int = None, close_y: int = None, auto_scale: bool = False):
        """
        Flujo de mejora oficial mediante el Gerente de Unidad:
        1. Clic en el libro azul 'Unidades' para abrir
        2. Clic en el botón verde 'Mejora'
        3. Clic nuevamente en el libro azul para cerrar (evitando el botón rojo de Vender)
        """
        self.click_at(book_x, book_y, delay=0.3, auto_scale=auto_scale)
        self.click_at(upgrade_x, upgrade_y, delay=0.2, auto_scale=auto_scale)
        # Se cierra alternando el icono del libro para evitar presionar 'Vender'
        self.click_at(book_x, book_y, delay=0.2, auto_scale=auto_scale)

    def calibrate_camera(self):
        """
        Ajusta la cámara a vista cenital (desde arriba):
        1. Zoom al máximo alejando con 'O'
        2. Arrastre con clic derecho para ángulo cenital
        """
        # Alejar cámara al tope
        for _ in range(15):
            pydirectinput.press('o')
            time.sleep(0.02)
        time.sleep(0.2)

        # Centrar el mouse y arrastrar hacia arriba con botón derecho
        sw, sh = pyautogui.size()
        cx, cy = sw // 2, sh // 2
        pydirectinput.moveTo(cx, cy)
        time.sleep(0.05)
        # Arrastrar hacia abajo con clic derecho para elevar la cámara y mirar al suelo (vista pájaro)
        pydirectinput.mouseDown(button='right')
        time.sleep(0.05)
        # Dividir el movimiento en pasos suaves para que Roblox registre el ángulo completo
        for _ in range(3):
            pydirectinput.moveRel(0, 150, relative=True)
            time.sleep(0.03)
        time.sleep(0.05)
        pydirectinput.mouseUp(button='right')
        time.sleep(0.2)

    def anti_afk_jiggle(self):
        """Micro-movimiento inocuo del cursor que evita AFK sin tocar la cámara ni hacer zoom"""
        pydirectinput.moveRel(1, 0, relative=True)
        time.sleep(0.03)
        pydirectinput.moveRel(-1, 0, relative=True)
