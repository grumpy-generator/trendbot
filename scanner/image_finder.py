"""
==============================================================
  TREND BOT v3 — IMAGE FINDER
  Strategy:
    1. Pollinations.ai (free AI generation — always works)
    2. Web search (DuckDuckGo → Bing) for a real meme/photo
    3. Placeholder with ticker text
==============================================================
"""

import os
import re
import time
import logging
import hashlib
import requests
from io import BytesIO
from urllib.parse import quote_plus

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

IMAGE_DIR = "images"
TARGET_SIZE = (512, 512)


def find_token_image(story_title, ticker, name, visual_hint="", keywords=None):
    """
    Find or create an image for a token.

    Strategy (ordered by reliability):
    1. Pollinations.ai AI generation using the visual description
    2. Web search (DuckDuckGo → Bing) for a real meme/viral image
    3. Placeholder with ticker text

    Returns: filepath to image, or None
    """
    os.makedirs(IMAGE_DIR, exist_ok=True)

    # 1. Pollinations.ai — free, no API key, always generates something relevant
    prompt = _build_pollinations_prompt(name, visual_hint, story_title, keywords)
    filepath = _generate_with_pollinations(prompt, ticker)
    if filepath:
        logging.info(f"Image: Pollinations.ai success for '{ticker}'")
        return filepath

    # 2. Web search for real meme images
    search_queries = _build_search_queries(visual_hint, name, keywords)
    for query in search_queries:
        filepath = _search_and_download(query, ticker)
        if filepath:
            logging.info(f"Image: web search success for '{ticker}' via '{query}'")
            return filepath

    # 3. Placeholder
    logging.warning(f"Image: falling back to placeholder for '{ticker}'")
    return _create_placeholder(ticker, name)


def _build_pollinations_prompt(name, visual_hint, story_title, keywords):
    """Build a good image generation prompt for Pollinations.ai."""
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
    """
    Generate an image via Pollinations.ai (free, no API key).
    Returns filepath or None.
    """
    try:
        encoded = quote_plus(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=512&height=512&nologo=true&seed={abs(hash(ticker)) % 9999}"

        resp = requests.get(url, timeout=60, headers={"User-Agent": "TrendBot/3.0"})

        if resp.status_code != 200:
            logging.debug(f"Pollinations.ai returned {resp.status_code}")
            return None

        content = resp.content
        if len(content) < 3000:  # too small = error page
            logging.debug(f"Pollinations.ai response too small: {len(content)} bytes")
            return None

        filename = f"{ticker.lower()}_{hashlib.md5(content[:500]).hexdigest()[:8]}_ai.png"
        filepath = os.path.join(IMAGE_DIR, filename)

        if HAS_PIL:
            img = Image.open(BytesIO(content))
            img = _normalize_image(img)
            img.save(filepath, "PNG")
        else:
            with open(filepath, "wb") as f:
                f.write(content)

        return filepath

    except Exception as e:
        logging.debug(f"Pollinations.ai failed: {e}")
        return None


def _build_search_queries(visual_hint, name, keywords):
    """Build web search queries from most to least specific."""
    queries = []
    if visual_hint:
        queries.append(visual_hint)
    if name:
        queries.append(f"{name} meme")
    if keywords:
        for kw in keywords[:2]:
            queries.append(f"{kw} meme funny")
    return queries


def _search_and_download(query, ticker):
    """
    Search for an image via DuckDuckGo, fallback to Bing.
    Returns filepath or None.
    """
    filepath = _search_ddg(query, ticker)
    if filepath:
        return filepath
    return _search_bing(query, ticker)


def _search_ddg(query, ticker):
    """DuckDuckGo image search."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        # Get vqd token
        resp = requests.get("https://duckduckgo.com/", params={"q": query},
                            headers=headers, timeout=6)

        vqd = None
        for pattern in [r'vqd=(["\'])([^"\']+)\1', r'"vqd"\s*:\s*"([^"]+)"', r'vqd=([\d-]+)']:
            m = re.search(pattern, resp.text)
            if m:
                vqd = m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(1)
                break

        if not vqd:
            return None

        img_resp = requests.get(
            "https://duckduckgo.com/i.js",
            params={"l": "us-en", "o": "json", "q": query, "vqd": vqd, "f": ",,,,,", "p": "1"},
            headers=headers, timeout=8,
        )
        if img_resp.status_code != 200:
            return None

        results = img_resp.json().get("results", [])
        for result in results[:5]:
            url = result.get("image", "")
            if url:
                fp = _download_and_process(url, ticker)
                if fp:
                    return fp

    except Exception as e:
        logging.debug(f"DuckDuckGo search failed: {e}")

    return None


def _search_bing(query, ticker):
    """Bing image search fallback."""
    try:
        url = f"https://www.bing.com/images/search?q={quote_plus(query)}&form=HDRSC2&first=1"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code != 200:
            return None

        img_urls = re.findall(r'murl":"(https?://[^"]+)"', resp.text)
        for img_url in img_urls[:5]:
            if ".svg" in img_url or "icon" in img_url.lower():
                continue
            fp = _download_and_process(img_url, ticker)
            if fp:
                return fp

    except Exception as e:
        logging.debug(f"Bing search failed: {e}")

    return None


def _download_and_process(image_url, ticker):
    """Download an image, validate it, resize to 512x512."""
    try:
        resp = requests.get(image_url, timeout=8, stream=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

        if resp.status_code != 200:
            return None

        content = resp.content
        if len(content) < 5000 or len(content) > 10_000_000:
            return None

        content_type = resp.headers.get("content-type", "")
        if not any(t in content_type for t in ["image/jpeg", "image/png", "image/webp", "image/gif"]):
            # Validate by trying to open it
            if not HAS_PIL:
                return None
            try:
                Image.open(BytesIO(content)).verify()
            except Exception:
                return None

        img_hash = hashlib.md5(content[:1000]).hexdigest()[:8]
        filename = f"{ticker.lower()}_{img_hash}.png"
        filepath = os.path.join(IMAGE_DIR, filename)

        if HAS_PIL:
            img = Image.open(BytesIO(content))
            img = _normalize_image(img)
            img.save(filepath, "PNG", quality=95)
        else:
            with open(filepath, "wb") as f:
                f.write(content)

        return filepath

    except Exception as e:
        logging.debug(f"Image download failed ({image_url[:60]}): {e}")
        return None


def _normalize_image(img):
    """Convert to RGB, center-crop to square, resize to 512x512."""
    if img.mode in ("RGBA", "P", "LA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        background.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    w, h = img.size
    min_dim = min(w, h)
    left = (w - min_dim) // 2
    top = (h - min_dim) // 2
    img = img.crop((left, top, left + min_dim, top + min_dim))
    img = img.resize(TARGET_SIZE, Image.LANCZOS)
    return img


def _create_placeholder(ticker, name):
    """Create a simple colored placeholder image with ticker text."""
    if not HAS_PIL:
        return None

    try:
        from PIL import ImageDraw, ImageFont

        seed = sum(ord(c) for c in ticker)
        colors = [
            (76, 175, 80), (33, 150, 243), (255, 152, 0),
            (156, 39, 176), (244, 67, 54), (0, 188, 212), (255, 193, 7),
        ]
        bg_color = colors[seed % len(colors)]

        img = Image.new("RGB", TARGET_SIZE, bg_color)
        draw = ImageDraw.Draw(img)

        text = f"${ticker}"
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
        except (IOError, OSError):
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), text, font=font)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (TARGET_SIZE[0] - text_w) // 2
        y = (TARGET_SIZE[1] - text_h) // 2

        draw.text((x + 2, y + 2), text, fill=(0, 0, 0, 128), font=font)
        draw.text((x, y), text, fill="white", font=font)

        if name:
            try:
                small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
            except (IOError, OSError):
                small_font = font
            bbox2 = draw.textbbox((0, 0), name, font=small_font)
            name_w = bbox2[2] - bbox2[0]
            draw.text(((TARGET_SIZE[0] - name_w) // 2, y + text_h + 20), name, fill="white", font=small_font)

        filename = f"{ticker.lower()}_placeholder.png"
        filepath = os.path.join(IMAGE_DIR, filename)
        img.save(filepath, "PNG")
        return filepath

    except Exception as e:
        logging.error(f"Placeholder creation failed: {e}")
        return None
