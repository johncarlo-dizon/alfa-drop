from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
PURPLE = "#6d4aff"
WHITE = "#ffffff"

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

d.rounded_rectangle((40, 40, SIZE - 40, SIZE - 40), radius=220, fill=PURPLE)

cx = SIZE // 2
d.rectangle((cx - 70, 200, cx + 70, 540), fill=WHITE)                       # arrow shaft
d.polygon([(cx - 220, 500), (cx + 220, 500), (cx, 750)], fill=WHITE)        # arrow head
d.rounded_rectangle((250, 790, SIZE - 250, 865), radius=38, fill=WHITE)     # tray

out = Path("assets")
out.mkdir(exist_ok=True)
icon = img.resize((256, 256), Image.LANCZOS)
icon.save(out / "alfadrop.ico", format="ICO",
          sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("Saved", out / "alfadrop.ico")