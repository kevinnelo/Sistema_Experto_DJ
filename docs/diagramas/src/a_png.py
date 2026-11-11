"""Convierte los .svg de docs/diagramas a .png (requiere playwright)."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
carpeta = Path(__file__).resolve().parent.parent
with sync_playwright() as p:
    b = p.chromium.launch()
    for svg in sorted(carpeta.glob("*.svg")):
        if len(sys.argv) > 1 and sys.argv[1] not in svg.name:
            continue
        pg = b.new_page(device_scale_factor=2)
        pg.goto(svg.as_uri())
        caja = pg.locator("svg").bounding_box()
        pg.set_viewport_size({"width": int(caja["width"]), "height": int(caja["height"])})
        pg.screenshot(path=str(svg.with_suffix(".png")))
        pg.close()
    b.close()
