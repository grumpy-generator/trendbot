"""
==============================================================
  TREND BOT v3 — IMAGE FINDER
  Strategy:
    1. Pollinations.ai (free AI generation — always relevant)
    2. DuckDuckGo image search (duckduckgo-search library)
    3. Bing image search (scraping fallback)
    4. Placeholder with ticker text
==============================================================
"""

import os
import re
import logging
import hashlib
import requests
from io import BytesIO
from urllib.parse import quote_plus

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from duckduckgo_search import DDGS
    HAS_DDGS = True
except ImportError:
    HAS_DDGS = False

IMAGE_DIR = "images"
TARGET_SIZE = (512, 512)


def find_token_image(story_title, ticker, name, visual_hint="", keywords=None):
    """
    Find or create an image for a token.

    Strategy (ordered by reliability):
    1. Pollinations.ai — AI generates a meme-coin image from the visual description
    2. DuckDuckGo image search — finds real viral photos/memes
    3. Bing image search — scraping fallback
    4. Placeholder — colored square with ticker text
    """
    os.makedirs(IMAGE_DIR, exist_ok=True)

    queries = _build_search_queries(visual_hint, name, keywords)

    # 1. DuckDuckGo image search (real viral photo/meme)
    if HAS_DDGS:
        for query in queries:
            filepath = _search_ddg(query, ticker)
            if filepath:
                logging.info(f"Image: DDG OK for '{ticker}' via '{query}'")
                return filepath

    # 2. Bing image search (scraping fallback)
    for query in queries[:2]:
        filepath = _search_bing(query, ticker)
        if filepath:
            logging.info(f"Image: Bing OK for '{ticker}' via '{query}'")
            return filepath

    # 3. Pollinations.ai — AI generation when no real image found
    prompt = _build_pollinations_prompt(name, visual_hint, story_title, keywords)
    filepath = _generate_with_pollinations(prompt, ticker)
    if filepath:
        logging.info(f"Image: Pollinations.ai OK for '{ticker}'")
        return filepath

    # 4. Placeholder
    logging.warning(f"Image: placeholder for '{ticker}'")
    return _create_placeholder(ticker, name)


# ---------------------------------------------------------------
# Pollinations.ai — AI generation
# ---------------------------------------------------------------

def _build_pollinations_prompt(name, visual_hint, story_title, keywords):
    parts = []
    if visual_hint and len(visual_hint) > 5:
        parts.append(visual_hint)
    elif name:
        parts.append(f"{name} mascot")
    parts += [
        "crypto meme coin token",
        "cute cartoon style",
        "flat design",
        "centered composition",
        "white or simple background",
        "vibrant colors",
        "no text",
    ]
    return ", ".join(parts)[:400]


def _generate_with_pollinations(prompt, ticker):
    try:
        encoded = quote_plus(prompt)
        seed = abs(hash(ticker)) % 9999
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width=512&height=512&nologo=true&seed={seed}"
        )
        resp = requests.get(url, timeout=45, headers={"User-Agent": "TrendBot/3.0"})
        if resp.status_code != 200:
            return None

        content = resp.content
        if len(content) < 3000:
            return None

        filename = f"{ticker.lower()}_{hashlib.md5(content[:500]).hexdigest()[:8]}_ai.png"
        filepath = os.path.join(IMAGE_DIR, filename)
        return _save_image(content, filepath)

    except Exception as e:
        logging.debug(f"Pollinations failed: {e}")
        return None


# ---------------------------------------------------------------
# DuckDuckGo — library-based (reliable)
# ---------------------------------------------------------------

def _search_ddg(query, ticker):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=8, type_image="photo"))
        for r in results:
            url = r.get("image", "")
            if url:
                fp = _download_and_save(url, ticker)
                if fp:
                    return fp
    except Exception as e:
        logging.debug(f"DDG search failed: {e}")
    return None


# ---------------------------------------------------------------
# Bing — scraping fallback
# ---------------------------------------------------------------

def _search_bing(query, ticker):
    try:
        url = f"https://www.bing.com/images/search?q={quote_plus(query)}&form=HDRSC2&first=1"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None

        # Bing embeds image URLs in JSON-like blocks
        img_urls = re.findall(r'"murl"\s*:\s*"(https?://[^"]+)"', resp.text)
        for img_url in img_urls[:8]:
            if any(x in img_url.lower() for x in [".svg", "icon", "logo", "pixel"]):
                continue
            fp = _download_and_save(img_url, ticker)
            if fp:
                return fp

    except Exception as e:
        logging.debug(f"Bing search failed: {e}")
    return None


def _build_search_queries(visual_hint, name, keywords):
    queries = []
    if visual_hint and len(visual_hint) > 5:
        queries.append(visual_hint)
    if name:
        queries.append(f"{name} meme")
    if keywords:
        for kw in keywords[:2]:
            queries.append(f"{kw} meme funny")
    return queries


# ---------------------------------------------------------------
# Download + save
# ---------------------------------------------------------------

def _download_and_save(image_url, ticker):
    try:
        resp = requests.get(image_url, timeout=8, stream=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        if resp.status_code != 200:
            return None

        content = resp.content
        if len(content) < 5000 or len(content) > 10_000_000:
            return None

        img_hash = hashlib.md5(content[:1000]).hexdigest()[:8]
        filepath = os.path.join(IMAGE_DIR, f"{ticker.lower()}_{img_hash}.png")
        return _save_image(content, filepath)

    except Exception as e:
        logging.debug(f"Image download failed ({image_url[:60]}): {e}")
        return None


def _save_image(content, filepath):
    """Save image bytes to filepath. Normalizes to 512x512 PNG if PIL available."""
    try:
        if HAS_PIL:
            img = Image.open(BytesIO(content))
            img = _normalize_image(img)
            img.save(filepath, "PNG")
        else:
            with open(filepath, "wb") as f:
                f.write(content)
        return filepath
    except Exception as e:
        logging.debug(f"Save image failed: {e}")
        return None


def _normalize_image(img):
    """Convert to RGB, center-crop to square, resize to 512x512."""
    if img.mode in ("RGBA", "P", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    w, h = img.size
    m = min(w, h)
    img = img.crop(((w - m) // 2, (h - m) // 2, (w + m) // 2, (h + m) // 2))
    return img.resize(TARGET_SIZE, Image.LANCZOS)


# ---------------------------------------------------------------
# Placeholder
# ---------------------------------------------------------------

def _create_placeholder(ticker, name):
    if not HAS_PIL:
        return None
    try:
        seed = sum(ord(c) for c in ticker)
        colors = [
            (76, 175, 80), (33, 150, 243), (255, 152, 0),
            (156, 39, 176), (244, 67, 54), (0, 188, 212), (255, 193, 7),
        ]
        img = Image.new("RGB", TARGET_SIZE, colors[seed % len(colors)])
        draw = ImageDraw.Draw(img)

        text = f"${ticker}"
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
        except (IOError, OSError):
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x, y = (TARGET_SIZE[0] - tw) // 2, (TARGET_SIZE[1] - th) // 2
        draw.text((x + 2, y + 2), text, fill=(0, 0, 0, 128), font=font)
        draw.text((x, y), text, fill="white", font=font)

        if name:
            try:
                sfont = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
            except (IOError, OSError):
                sfont = font
            b2 = draw.textbbox((0, 0), name, font=sfont)
            nw = b2[2] - b2[0]
            draw.text(((TARGET_SIZE[0] - nw) // 2, y + th + 20), name, fill="white", font=sfont)

        filepath = os.path.join(IMAGE_DIR, f"{ticker.lower()}_placeholder.png")
        img.save(filepath, "PNG")
        return filepath

    except Exception as e:
        logging.error(f"Placeholder failed: {e}")
        return None
