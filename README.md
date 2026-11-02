# 🛡️ Roblox TTD - Auto Endless AI Vision Bot

Bot autónomo de visión artificial diseñado para el modo **Endless** de **Toilet Tower Defense (TTD)** en Roblox.

Utiliza **OpenCV**, **MSS** (captura ultrarrápida a nivel de DirectX/GDI), **OCR con PyTesseract** y algoritmos de **detección de cinta de enemigos** para garantizar la colocación de unidades, mejora automática y reinicio infinito sin fallos de calibración.

---

## ✨ Características Principales

1. **Planificador Visual Interactivo (Blueprint GUI):**
   * Interfaz moderna desarrollada con `CustomTkinter`.
   * Permite fijar y diseñar la estrategia de unidades en el mapa con clic izquierdo y eliminarlas con clic derecho.
   * Guarda y exporta estrategias en formato JSON (`strategies/`).

2. **Detección Dinámica de Cinta de Enemigos (`Track-Guided Placement`):**
   * Analiza en vivo la canaleta oscura del mapa por donde marchan los enemigos.
   * Delimita la lava y las zonas prohibidas.
   * Ajuste magnético automático (`snap_to_safe_strip`): si una tropa iba a ser colocada en la lava o en la pista, se reubica instantáneamente a la piedra óptima adyacente más cercana.

3. **Auto-Mejora con Gerente de Unidad (Libro Azul):**
   * Accede al panel izquierdo de gestión mediante el icono del libro azul (`Unidades`).
   * Detecta y presiona el botón verde de **Mejora** con coincidencia de plantilla al 100%.
   * Cierra automáticamente el panel para evitar obstrucciones visuales.

4. **Auto-Skip de Oleadas:**
   * Detección visual del botón **Saltar** en la barra superior.
   * Activación automática de la casilla de auto-salto cuando está en rojo.

5. **Detección de Derrota/Victoria y Bucle Infinito:**
   * Detección por visión de la pantalla de fin de partida.
   * Clic automático en **"Jugar de nuevo"** y espera inteligente de pantalla de carga para iniciar la siguiente partida.

6. **Anti-AFK Integrado:**
   * Micro-movimientos de control para evitar la desconexión por inactividad de Roblox.

---

## 🚀 Requisitos e Instalación

### 1. Requisitos Previos
* **Python 3.10 o superior**
* **Tesseract-OCR** instalado en Windows (usualmente en `C:\Program Files\Tesseract-OCR\tesseract.exe`).

### 2. Instalación de Dependencias
```bash
pip install -r requirements.txt
```

---

## 🎮 Modo de Uso

1. Abre **Roblox** e ingresa al modo **Endless** de Toilet Tower Defense.
2. Inicia la aplicación del bot:
   ```bash
   python app.py
   ```
3. En la pestaña **Plano de Tropas**, carga o diseña tu estrategia de unidades.
4. Presiona el botón verde **"▶ INICIAR BOT"** y enfoca la ventana de Roblox.

---

## 📁 Estructura del Proyecto

```
TTD/
├── app.py                 # Interfaz gráfica principal y bucle de automatización
├── vision.py              # Motor de visión por computador (OpenCV, OCR, segmentación de cinta)
├── controller.py          # Emulación de teclado y mouse con PyDirectInput
├── recorder.py            # Módulo de grabación de partidas
├── blueprint.json         # Plano de colocación activo
├── requirements.txt       # Dependencias de Python
├── templates/             # Plantillas visuales (botones, iconos, galería multi-ángulo)
├── assets/                # Imágenes de referencia del mapa
└── strategies/            # Estrategias guardadas en formato JSON
```
