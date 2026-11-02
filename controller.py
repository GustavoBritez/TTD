import time
import pydirectinput
import pyautogui

# Desactivar pausas artificiales excesivas
pydirectinput.PAUSE = 0.05
pyautogui.PAUSE = 0.05

class GameController:
    def __init__(self):
        pass

    def walk(self, key: str, duration: float = 0.15):
        """Presiona una tecla de movimiento (W, A, S, D) durante una duración específica"""
        pydirectinput.keyDown(key.lower())
        time.sleep(duration)
        pydirectinput.keyUp(key.lower())
        time.sleep(0.05)

    def click_at(self, x: int, y: int, delay: float = 0.2):
        """Mueve el mouse y hace clic usando directinput para que Roblox lo registre"""
        pydirectinput.moveTo(x, y)
        time.sleep(0.05)
        pydirectinput.mouseDown()
        time.sleep(0.05)
        pydirectinput.mouseUp()
        time.sleep(delay)

    def select_slot(self, slot_number: int):
        """Presiona la tecla del slot (1, 2, 3, 4, 5)"""
        key = str(slot_number)
        pydirectinput.press(key)
        time.sleep(0.15)

    def place_unit(self, slot_number: int, x: int, y: int):
        """Selecciona una tropa y hace clic en el mapa para colocarla"""
        self.select_slot(slot_number)
        time.sleep(0.1)
        self.click_at(x, y)
        time.sleep(0.2)

    def upgrade_via_manager(self, book_x: int, book_y: int, upgrade_x: int, upgrade_y: int, close_x: int, close_y: int):
        """
        Flujo de mejora oficial mediante el Gerente de Unidad:
        1. Clic en el libro azul 'Unidades'
        2. Clic en el botón verde 'Mejora'
        3. Clic en el botón rojo 'Salir' para volver al modo normal
        """
        self.click_at(book_x, book_y, delay=0.3)
        self.click_at(upgrade_x, upgrade_y, delay=0.2)
        self.click_at(close_x, close_y, delay=0.2)

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
