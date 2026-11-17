"""아이콘(이력곡선 모양)을 src/datalab/data/icon.ico로 만든다. 한 번만 돌리고 결과를 커밋한다."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([8, 8, S - 8, S - 8], 40, fill=(31, 78, 140, 255))
h = np.linspace(-1, 1, 200)
for shift, col in ((0.25, (255, 200, 60, 255)), (-0.25, (120, 220, 255, 255))):
    m = np.tanh((h + shift) * 4)
    pts = [(S / 2 + x * 90, S / 2 - y * 80) for x, y in zip(h, m)]
    d.line(pts, fill=col, width=14, joint="curve")
out = Path(__file__).resolve().parents[1] / "src" / "datalab" / "data" / "icon.ico"
img.save(out, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(out)
