"""Generate high-resolution gold icon (.ico) for XAUUSD Time Machine."""
import os
import math
from PIL import Image, ImageDraw

def create_gold_icon(output_path="assets/gold_icon.ico"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background rounded container / circular shield
    center = size // 2
    radius = size // 2 - 8
    
    # Outer dark gold glow / border
    draw.ellipse([center - radius, center - radius, center + radius, center + radius], fill=(24, 28, 38, 255), outline=(218, 165, 32, 255), width=8)

    # Inner subtle circle
    inner_r = radius - 12
    draw.ellipse([center - inner_r, center - inner_r, center + inner_r, center + inner_r], fill=(16, 20, 28, 255), outline=(139, 101, 8, 180), width=3)

    # Gold Hourglass / Clock Hybrid
    # Top triangle / hourglass chamber
    top_points = [
        (center - 55, center - 65),
        (center + 55, center - 65),
        (center, center - 5)
    ]
    draw.polygon(top_points, fill=(255, 215, 0, 240), outline=(255, 240, 150, 255))

    # Bottom triangle / hourglass chamber
    bottom_points = [
        (center - 55, center + 65),
        (center + 55, center + 65),
        (center, center + 5)
    ]
    draw.polygon(bottom_points, fill=(218, 165, 32, 240), outline=(255, 240, 150, 255))

    # Hourglass top and bottom plates (Gold bars)
    draw.rounded_rectangle([center - 68, center - 76, center + 68, center - 62], radius=4, fill=(255, 223, 70, 255), outline=(218, 165, 32, 255), width=2)
    draw.rounded_rectangle([center - 68, center + 62, center + 68, center + 76], radius=4, fill=(255, 223, 70, 255), outline=(218, 165, 32, 255), width=2)

    # Center nexus / sand stream
    draw.line([center, center - 10, center, center + 10], fill=(255, 255, 220, 255), width=4)

    # Glowing clock tick marks on circumference
    for i in range(12):
        angle = i * (math.pi / 6)
        r1 = inner_r - 6
        r2 = inner_r - 16 if i % 3 == 0 else inner_r - 11
        w = 4 if i % 3 == 0 else 2
        col = (255, 215, 0, 255) if i % 3 == 0 else (180, 150, 50, 200)
        x1 = center + r1 * math.sin(angle)
        y1 = center - r1 * math.cos(angle)
        x2 = center + r2 * math.sin(angle)
        y2 = center - r2 * math.cos(angle)
        draw.line([x1, y1, x2, y2], fill=col, width=w)

    # Text "Au" or symbol "XAU" at bottom center
    # Small gold sparkle at top right
    draw.ellipse([center + 50, center - 50, center + 60, center - 40], fill=(255, 255, 255, 230))
    
    # Save as .ico with multiple standard sizes
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    img.save(output_path, format="ICO", sizes=sizes)
    print(f"Icon successfully generated at: {output_path}")

if __name__ == "__main__":
    create_gold_icon("d:/Time Machine/assets/gold_icon.ico")
