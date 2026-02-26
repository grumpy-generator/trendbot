"""
==============================================================
  TREND BOT v3 — IMAGE FINDER
  1. Search web for a relevant image (meme, mascot, viral photo)
  2. Download and resize for pump.fun (512x512 recommended)
  3. Fallback: generate with AI if nothing found online
==============================================================
"""

import os
import re
import json
import time
import logging
import hashlib
import requests
from io import BytesIO
from urllib.parse import quote_plus

# Try to import PIL for image processing
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

    Strategy:
    1. Search for the specific visual/character from the story
    2. Search for the meme/viral angle
    3. Fallback: generate with AI

    Returns: filepath to image, or None
    """
    os.makedirs(IMAGE_DIR, exist_ok=True)

    # Build search queries from most specific to general
    queries = []

    # Use AI visual hint if available (e.g. "green frog mascot")
    if visual_hint:
        queries.append(visual_hint)

    # Use the token name + meme context
    if name:
        queries.append(f"{name} meme")
        queries.append(name)

    # Extract key visual elements from title
    if keywords:
        for kw in keywords[:2]:
            queries.append(f"{kw} meme funny")

    # Try each query until we find a good image
    for query in queries:
        filepath = _search_and_download(query, ticker)
        if filepath:
            logging.info(f"Image found for '{ticker}' via query: '{query}'")
            return filepath

    # Fallback: try to generate with AI
    filepath = _generate_with_ai(name or ticker, visual_hint or story_title)
    if filepath:
        return filepath

    # Last resort: create a simple text-based placeholder
    return _create_placeholder(ticker, name)


def _search_and_download(query, ticker):
    """
    Search for an image using DuckDuckGo (no API key needed).
    Downloads the first suitable result.
    """
    try:
        # DuckDuckGo image search via their vqd token system
        search_url = "https://duckduckgo.com/"
        params = {"q": query}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        # Get vqd token
        resp = requests.get(search_url, params=params, headers=headers, timeout=5)
        vqd_match = re.search(r'vqd=(["\'])([^"\']+)\1', resp.text)
        if not vqd_match:
            # Try alternative pattern
            vqd_match = re.search(r'vqd=([\d-]+)', resp.text)
        if not vqd_match:
            return _search_via_bing(query, ticker)

        vqd = vqd_match.group(2) if vqd_match.lastindex == 2 else vqd_match.group(1)

        # Search images
        img_url = "https://duckduckgo.com/i.js"
        img_params = {
            "l": "us-en",
            "o": "json",
            "q": query,
            "vqd": vqd,
            "f": ",,,,,",
            "p": "1",
        }

        img_resp = requests.get(img_url, params=img_params, headers=headers, timeout=8)
        if img_resp.status_code != 200:
            return _search_via_bing(query, ticker)

        results = img_resp.json().get("results", [])

        # Try to download first 5 results
        for result in results[:5]:
            image_url = result.get("image", "")
            if not image_url:
                continue

            filepath = _download_and_process(image_url, ticker)
            if filepath:
                return filepath

    except Exception as e:
        logging.debug(f"DuckDuckGo search failed for '{query}': {e}")

    return _search_via_bing(query, ticker)


def _search_via_bing(query, ticker):
    """
    Fallback image search via Bing (no API key, scraping public results).
    """
    try:
        url = f"https://www.bing.com/images/search?q={quote_plus(query)}&form=HDRSC2&first=1"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code != 200:
            return None

        # Extract image URLs from the page
        # Bing stores them in murl attributes
        img_urls = re.findall(r'murl":"(https?://[^"]+)"', resp.text)

        for img_url in img_urls[:5]:
            # Skip very small images and SVGs
            if ".svg" in img_url or "icon" in img_url.lower():
                continue
            filepath = _download_and_process(img_url, ticker)
            if filepath:
                return filepath

    except Exception as e:
        logging.debug(f"Bing search failed for '{query}': {e}")

    return None


def _download_and_process(image_url, ticker):
    """
    Download an image, validate it, resize to 512x512.
    Returns filepath or None.
    """
    try:
        # Download with timeout
        resp = requests.get(image_url, timeout=8, stream=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

        if resp.status_code != 200:
            return None

        content_type = resp.headers.get("content-type", "")
        if not any(t in content_type for t in ["image/jpeg", "image/png", "image/webp", "image/gif"]):
            # Try to detect from content
            content = resp.content
            if len(content) < 5000:  # Too small, probably not a real image
                return None
        else:
            content = resp.content

        if len(content) < 5000:  # Less than 5KB = probably not useful
            return None
        if len(content) > 10_000_000:  # More than 10MB = too large
            return None

        # Generate filename from ticker
        img_hash = hashlib.md5(content[:1000]).hexdigest()[:8]
        filename = f"{ticker.lower()}_{img_hash}.png"
        filepath = os.path.join(IMAGE_DIR, filename)

        if HAS_PIL:
            # Process with PIL: resize to 512x512, convert to PNG
            img = Image.open(BytesIO(content))

            # Convert to RGB if needed (handles RGBA, P mode, etc.)
            if img.mode in ("RGBA", "P", "LA"):
                # Create white background for transparent images
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Resize to square (center crop then resize)
            w, h = img.size
            min_dim = min(w, h)
            left = (w - min_dim) // 2
            top = (h - min_dim) // 2
            img = img.crop((left, top, left + min_dim, top + min_dim))
            img = img.resize(TARGET_SIZE, Image.LANCZOS)

            img.save(filepath, "PNG", quality=95)
        else:
            # No PIL — save raw
            with open(filepath, "wb") as f:
                f.write(content)

        logging.info(f"Downloaded image: {filepath} ({len(content)} bytes)")
        return filepath

    except Exception as e:
        logging.debug(f"Image download failed ({image_url[:60]}): {e}")
        return None


def _generate_with_ai(name, description):
    """
    Generate an image using a free/cheap AI service.
    Uses Pollinations.ai (free, no API key needed).
    """
    try:
        # Pollinations.ai — free AI image generation
        prompt = f"cute cartoon meme mascot for crypto token called {name}, {description}, simple flat design, centered, square format, white background"
        encoded_prompt = quote_plus(prompt[:500])

        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true"

        resp = requests.get(url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0"
        })

        if resp.status_code == 200 and len(resp.content) > 5000:
            filename = f"{name.lower().replace(' ', '_')}_ai.png"
            filepath = os.path.join(IMAGE_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(resp.content)

            # Resize if PIL available
            if HAS_PIL:
                img = Image.open(filepath)
                img = img.resize(TARGET_SIZE, Image.LANCZOS)
                img.save(filepath, "PNG")

            logging.info(f"AI generated image: {filepath}")
            return filepath

    except Exception as e:
        logging.debug(f"AI image generation failed: {e}")

    return None


def _create_placeholder(ticker, name):
    """
    Create a simple colored placeholder image with the ticker text.
    Requires PIL.
    """
    if not HAS_PIL:
        return None

    try:
        from PIL import ImageDraw, ImageFont

        # Generate a color based on ticker
        seed = sum(ord(c) for c in ticker)
        colors = [
            (76, 175, 80),    # green
            (33, 150, 243),   # blue
            (255, 152, 0),    # orange
            (156, 39, 176),   # purple
            (244, 67, 54),    # red
            (0, 188, 212),    # cyan
            (255, 235, 59),   # yellow
        ]
        bg_color = colors[seed % len(colors)]

        img = Image.new("RGB", TARGET_SIZE, bg_color)
        draw = ImageDraw.Draw(img)

        # Draw ticker text centered
        text = f"${ticker}"
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
        except (IOError, OSError):
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (TARGET_SIZE[0] - text_w) // 2
        y = (TARGET_SIZE[1] - text_h) // 2

        # White text with slight shadow
        draw.text((x + 2, y + 2), text, fill=(0, 0, 0, 128), font=font)
        draw.text((x, y), text, fill="white", font=font)

        # Add name below
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
