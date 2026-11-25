"""Genera icon.ico: un puntero de ratón con una sombra de otro puntero detrás
(la copia), sobre el fondo oscuro de la app. Requiere: pip install pillow"""
from PIL import Image, ImageDraw

BG, INK, ACCENT, GHOST = "#121513", "#edebe4", "#ff5b38", "#4a504b"
S = 1024  # se dibuja grande y se reduce para suavizar bordes

# puntero clásico en una cuadrícula de 0-100
ARROW = [(0, 0), (0, 74), (19, 56), (31, 84), (45, 78), (33, 51), (58, 51)]


def pointer(draw, dx, dy, scale, fill, outline=None):
    pts = [(x * scale + dx, y * scale + dy) for x, y in ARROW]
    draw.polygon(pts, fill=fill)
    if outline:
        draw.line(pts + [pts[0]], fill=outline, width=int(S * 0.025), joint="curve")


img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.22), fill=BG)
k = S * 0.0085
pointer(d, S * 0.40, S * 0.30, k, GHOST)           # la copia, detrás y apagada
pointer(d, S * 0.24, S * 0.16, k, INK, BG)         # el puntero delante
# punto de acento: marca de "grabando"
r = S * 0.07
d.ellipse((S * 0.74 - r, S * 0.24 - r, S * 0.74 + r, S * 0.24 + r), fill=ACCENT)

sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
img.resize((256, 256), Image.LANCZOS).save("icon.ico", sizes=sizes)
img.resize((256, 256), Image.LANCZOS).save("icon.png")
print("ok")
