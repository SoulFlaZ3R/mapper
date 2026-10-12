"""
Genera l'icona occhio per Mapper.
Generates the eye icon for Mapper.
"""
from PIL import Image, ImageDraw
import math


def draw_eye(draw, cx, cy, s, color=(255, 216, 162, 255), pupil_color=(25, 15, 60, 255)):
    """Disegna un occhio stilizzato. / Draws a stylized eye."""
    eye_w = s * 0.72
    eye_h = s * 0.36

    # Forma esterna occhio (due archi) / Outer eye shape (two arcs)
    points_top = []
    points_bot = []
    steps = 40
    for i in range(steps + 1):
        t = i / steps
        x = cx - eye_w / 2 + eye_w * t
        yt = cy - eye_h / 2 * math.sin(t * math.pi)
        points_top.append((x, yt))
        yb = cy + eye_h / 2 * math.sin(t * math.pi)
        points_bot.append((x, yb))

    eye_shape = points_top + list(reversed(points_bot))
    draw.polygon([(int(x), int(y)) for x, y in eye_shape], fill=color)

    # Iride / Iris
    iris_r = s * 0.145
    draw.ellipse(
        [int(cx - iris_r), int(cy - iris_r), int(cx + iris_r), int(cy + iris_r)],
        fill=pupil_color,
    )

    # Pupilla / Pupil
    pupil_r = s * 0.075
    draw.ellipse(
        [int(cx - pupil_r), int(cy - pupil_r), int(cx + pupil_r), int(cy + pupil_r)],
        fill=(10, 8, 20, 255),
    )

    # Riflesso luce / Light reflection
    ref_r = s * 0.035
    ref_x = cx + iris_r * 0.35
    ref_y = cy - iris_r * 0.35
    draw.ellipse(
        [int(ref_x - ref_r), int(ref_y - ref_r), int(ref_x + ref_r), int(ref_y + ref_r)],
        fill=(255, 255, 255, 220),
    )


def create_icon():
    sizes = [256, 48, 32, 16]
    images = []

    for size in sizes:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Sfondo viola scuro arrotondato / Dark purple rounded background
        margin = max(1, size // 16)
        draw.rounded_rectangle(
            [margin, margin, size - margin - 1, size - margin - 1],
            radius=size // 5,
            fill=(25, 15, 60, 255),
        )

        # Occhio giallo / Yellow eye
        cx = size / 2
        cy = size / 2
        draw_eye(draw, cx, cy, size, color=(255, 216, 162, 255), pupil_color=(25, 15, 60, 255))

        images.append(img)

    images[0].save(
        "icon.ico", format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[1:],
    )
    print("icon.ico generated successfully.")


if __name__ == "__main__":
    create_icon()
