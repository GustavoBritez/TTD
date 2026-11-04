import cv2, numpy as np, json

R = r"C:\Users\Navegador\Desktop\STICK"
P = R + r"\templates\Mapa_Endless\Puntos_De_Colocacion\Puntos_de_unidades_Colocacion.png"
pimg_raw = cv2.imread(P)
h_raw, w_raw = pimg_raw.shape[:2]
pimg_1366 = cv2.resize(pimg_raw, (1366, 768))

# Load transforms.json
data = json.load(open(R + r"\scratch\transforms.json"))
Tpm = np.array(data["Tpm"], dtype=np.float64) # Puntos(1365x687) -> map_endless(1366x768)
# Invert Tpm: map_endless(1366x768) -> Puntos(1365x687)
Tmp = cv2.invertAffineTransform(Tpm)

TRACK_MAP = [
    (950, 185), (944, 280), (895, 280), (895, 360),
    (1082, 375), (1076, 480), (1152, 485), (1150, 567),
    (990, 567), (988, 653), (764, 643), (778, 510),
    (848, 510), (848, 435), (585, 418), (547, 655),
]
track_arr = np.float32(TRACK_MAP).reshape(-1, 1, 2)
track_in_p_raw = cv2.transform(track_arr, Tmp).reshape(-1, 2)
sx = 1366.0 / w_raw
sy = 768.0 / h_raw
track_in_p_1366 = [(int(round(x * sx)), int(round(y * sy))) for x, y in track_in_p_raw]

cfg = json.load(open(R + r"\assets\placement_points.json"))
pts_1366 = [(int(round(p["ref"][0] * sx)), int(round(p["ref"][1] * sy))) for p in cfg["points"]]

dbg = pimg_1366.copy()
for i in range(len(track_in_p_1366) - 1):
    cv2.line(dbg, track_in_p_1366[i], track_in_p_1366[i+1], (0, 0, 255), 3)
for i, (x, y) in enumerate(pts_1366):
    cv2.circle(dbg, (x, y), 10, (255, 255, 0), 2)
    cv2.putText(dbg, f"P{i+1}", (x + 10, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

cv2.imwrite(R + r"\scratch\verify_puntos_1366.png", dbg)
print("TRACK_WAYPOINTS_1366 =", track_in_p_1366)
print("PTS_1366 =", pts_1366)

