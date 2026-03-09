# utils.py
import io
from PIL import Image
import numpy as np

def tight_crop_by_nonwhite(img_bytes, white_thresh=250, pad=2):
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    arr = np.array(img)
    mask = np.any(arr < white_thresh, axis=2)
    if not mask.any():
        return img_bytes
    ys, xs = np.where(mask)
    y0, y1 = ys.min(), ys.max() + 1
    x0, x1 = xs.min(), xs.max() + 1
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(arr.shape[1], x1 + pad)
    y1 = min(arr.shape[0], y1 + pad)
    cropped = img.crop((x0, y0, x1, y1))
    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    return buf.getvalue()

def remove_white_bg_make_transparent(png_bytes, white_thresh=245, soft=15):
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            m = min(r, g, b)
            if m >= white_thresh:
                px[x, y] = (r, g, b, 0)
            elif m >= white_thresh - soft:
                alpha = int(255 * (white_thresh - m) / soft)
                alpha = max(0, min(255, alpha))
                px[x, y] = (r, g, b, alpha)
    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    if bbox:
        img = img.crop(bbox)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()