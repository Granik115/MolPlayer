"""Generate a blue-cyan tech icon matching the MolPlayer app theme (deep navy + glowing cyan/blue)."""
from PIL import Image, ImageDraw
import math

def create_icon(size=256):
    # Colors from current app theme (blue/cyan)
    bg_dark = (10, 18, 34)          # very dark navy ~ BG_DARK
    panel = (15, 30, 54)            # dark panel
    border = (62, 128, 163)         # #3e80a3 frame blue
    glow = (0, 191, 255)            # #00bfff bright cyan glow
    glow_teal = (0, 188, 212)       # #00bcd4
    depth = (33, 81, 117)           # #215175 depth blue
    center_dark = (10, 18, 34)

    img = Image.new("RGBA", (size, size), bg_dark + (255,))
    draw = ImageDraw.Draw(img)

    # Outer rounded rect (machine panel look)
    margin = size // 12
    draw.rounded_rectangle(
        [margin, margin, size - margin - 1, size - margin - 1],
        radius=size // 8,
        fill=panel + (255,),
        outline=border + (255,),
        width=max(3, size // 40)
    )

    # Inner glowing circle (molecular core) - brighter cyan
    cx, cy = size // 2, size // 2
    r = size // 3
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=glow + (255,))

    # Energy "molecular" lines / arcs in frame blue + glow
    for i in range(4):
        a = i * (math.pi / 2) + 0.3
        x1 = cx + int(r * 0.55 * math.cos(a))
        y1 = cy + int(r * 0.55 * math.sin(a))
        x2 = cx + int(r * 0.92 * math.cos(a))
        y2 = cy + int(r * 0.92 * math.sin(a))
        draw.line([(x1, y1), (x2, y2)], fill=border + (255,), width=max(3, size // 28))

    # Small tech squares around (using depth + border tones)
    sq = size // 10
    for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
        sx = cx + dx * (r + sq)
        sy = cy + dy * (r + sq)
        draw.rectangle(
            [sx - sq // 2, sy - sq // 2, sx + sq // 2, sy + sq // 2],
            fill=depth + (220,)
        )

    # Center dot
    cd = max(6, size // 18)
    draw.ellipse([cx - cd, cy - cd, cx + cd, cy + cd], fill=center_dark + (255,))

    return img

if __name__ == "__main__":
    import os
    os.makedirs("assets", exist_ok=True)
    ico_sizes = [16, 32, 48, 64, 128, 256]
    images = []
    for s in ico_sizes:
        im = create_icon(s)
        images.append(im)
        if s == 256:
            im.save("assets/icon.png")
            print("Saved assets/icon.png")
    # Save multi-size .ico
    images[0].save("assets/icon.ico", sizes=[(s, s) for s in ico_sizes])
    print("Saved assets/icon.ico")
    print("Done.")
