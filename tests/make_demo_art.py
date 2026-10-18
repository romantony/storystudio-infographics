"""Stand-in art for examples/demo, so the build can be tested without paying for image generation.
Draws two flat 'vector' backgrounds and one character on a green background (which then goes through infogen cutout).
Run from the demo folder: python3 ../../tests/make_demo_art.py"""
import os, random
from PIL import Image, ImageDraw

os.makedirs("assets", exist_ok=True); random.seed(4)

def city():
    W, H = 1920, 1080; im = Image.new("RGB", (W, H)); d = ImageDraw.Draw(im)
    for y in range(H): c = int(20 + 40 * y / H); d.line([(0, y), (W, y)], fill=(c, c + 10, 70 + c))
    d.ellipse((1450, 120, 1650, 320), fill=(250, 240, 200))
    x = 0
    while x < W:
        w = random.randint(110, 220); h = random.randint(300, 760); col = random.choice([(34, 52, 92), (44, 66, 110), (28, 40, 76)])
        d.rectangle((x, H - h, x + w, H), fill=col)
        for wy in range(H - h + 30, H - 40, 46):
            for wx in range(x + 18, x + w - 30, 38):
                if random.random() < 0.7: d.rectangle((wx, wy, wx + 20, wy + 26), fill=(255, 210, 90))
        x += w + random.randint(8, 30)
    d.rectangle((0, H - 120, W, H), fill=(20, 26, 44))
    im.save("assets/city_night.png")

def servers():
    W, H = 1920, 1080; im = Image.new("RGB", (W, H), (16, 30, 58)); d = ImageDraw.Draw(im)
    d.polygon([(0, H), (W, H), (W * 0.62, H * 0.45), (W * 0.38, H * 0.45)], fill=(26, 46, 84))
    for k in range(9):
        s = 1 - k * 0.09; top = H * 0.45 - 260 * s
        for side in (-1, 1):
            x0 = W / 2 + side * (120 + 760 * s ** 1.6); w = 150 * s
            d.rectangle((x0 - w / 2, top, x0 + w / 2, H * 0.45 + 300 * s), fill=(40, 70, 120))
            for j in range(10):
                y = top + 20 * s + j * 50 * s; d.rectangle((x0 - w / 2 + 10 * s, y, x0 + w / 2 - 10 * s, y + 20 * s), fill=(60, 200, 255) if (j + k) % 3 else (90, 255, 160))
    im.save("assets/server_hall.png")

def analyst():
    W, H = 768, 1344; im = Image.new("RGB", (W, H), (0, 255, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((250, 600, 520, 1000), 60, fill=(222, 170, 40))          # sweater
    d.rectangle((270, 990, 380, 1260), fill=(40, 50, 80)); d.rectangle((390, 990, 500, 1260), fill=(40, 50, 80))
    d.ellipse((255, 1240, 385, 1290), fill=(250, 250, 250)); d.ellipse((385, 1240, 515, 1290), fill=(250, 250, 250))
    d.ellipse((240, 260, 530, 600), fill=(245, 200, 170))                          # head
    d.chord((225, 230, 545, 520), 180, 360, fill=(25, 25, 30)); d.rectangle((225, 370, 275, 560), fill=(25, 25, 30)); d.rectangle((495, 370, 545, 560), fill=(25, 25, 30))
    for cx in (335, 435):
        d.ellipse((cx - 38, 400, cx + 38, 476), outline=(30, 30, 30), width=8); d.ellipse((cx - 9, 430, cx + 9, 448), fill=(30, 30, 30))
    d.arc((340, 500, 430, 560), 200, 340, fill=(120, 40, 40), width=8)              # worried mouth
    d.rounded_rectangle((180, 300, 260, 640), 40, fill=(222, 170, 40)); d.rounded_rectangle((510, 300, 590, 640), 40, fill=(222, 170, 40))   # arms up
    d.ellipse((185, 250, 265, 330), fill=(245, 200, 170)); d.ellipse((505, 250, 585, 330), fill=(245, 200, 170))
    im.save("assets/analyst_worried.png")

city(); servers(); analyst(); print("assets/city_night.png assets/server_hall.png assets/analyst_worried.png")
