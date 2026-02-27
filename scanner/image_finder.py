"""
==============================================================
  TREND BOT v3 — IMAGE FINDER
  Strategy:
    1. DuckDuckGo image search (real memes, viral images)
    2. Bing image search (scraping fallback)
    3. Pollinations.ai (AI generation — when web search finds nothing)
    4. Placeholder with ticker text

  Web search comes first because it finds the actual viral image
  associated with the trend (the meme that's spreading). Pollinations
  is the fallback AI generator for when nothing is found.
  Images can be photos, drawings, memes — anything relevant.
==============================================================
"""

import os
import re
import socket
import logging
import hashlib
import ipaddress
import requests
from io import BytesIO
from urllib.parse import quote_plus, urlparse

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

# ---------------------------------------------------------------
# Security: SSRF guard + filename sanitiser
# ---------------------------------------------------------------

def _is_safe_url(url: str) -> bool:
    """
    Reject URLs that could be used for SSRF (Server-Side Request Forgery).
    Allows only http/https to public IPs — blocks loopback, RFC-1918 private
    ranges, link-local (169.254.x.x), cloud metadata endpoints, and all
    non-HTTP schemes (file://, javascript://, data://, etc.).
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        # Block obvious localhost aliases
        if hostname.lower() in ("localhost", "0.0.0.0", "::1"):
            return False
        # Resolve hostname → IP and check it's public
        try:
            ip = ipaddress.ip_address(socket.gethostbyname(hostname))
        except (socket.gaierror, ValueError):
            return False  # can't resolve → reject
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False
        return True
    except Exception:
        return False


def _safe_ticker(ticker: str) -> str:
    """
    Sanitise ticker for use in file-system paths.
    Strips everything that isn't A-Z 0-9 — prevents path-traversal attacks
    (e.g. a ticker like '../../evil' becomes 'evil').
    """
    clean = re.sub(r"[^A-Za-z0-9]", "", ticker)
    return clean[:20] if clean else "TOKEN"

# News/photojournalism domains that produce real photos — not cartoon mascots.
# Images from these domains are filtered out.
_NEWS_PHOTO_DOMAINS = {
    "reuters.com", "apimages.com", "ap.org", "apnews.com",
    "gettyimages.com", "gettyimages.es", "gettyimages.co.uk",
    "alamy.com", "shutterstock.com", "istockphoto.com",
    "bbc.com", "bbc.co.uk", "cnn.com", "nbcnews.com", "cbsnews.com",
    "foxnews.com", "nytimes.com", "washingtonpost.com", "theguardian.com",
    "politico.com", "thehill.com", "axios.com",
    "afp.com", "afpforum.com", "zumapressimages.com",
}


def _is_news_photo_url(url):
    """Return True if the URL is from a photojournalism / stock-photo domain."""
    url_lower = url.lower()
    for domain in _NEWS_PHOTO_DOMAINS:
        if domain in url_lower:
            return True
    return False


def find_token_image(story_title, ticker, name, visual_hint="", keywords=None,
                     source_image_url=None):
    """
    Find or create an image for a token.

    Strategy:
    0. Source image (Reddit post image, Imgur direct link, etc.) — the actual
       viral image IS the trend. Always prefer this over a web search.
    1. DuckDuckGo image search — finds real memes/viral images
    2. Bing image search — scraping fallback
    3. Pollinations.ai — AI generation when web search finds nothing relevant
    4. Placeholder — colored square with ticker text
    """
    os.makedirs(IMAGE_DIR, exist_ok=True)

    # 0. Use the image from the source post itself (Reddit, Imgur, etc.)
    if source_image_url:
        fp = _download_and_save(source_image_url, ticker)
        if fp:
            logging.info(f"Image: source post image used for '{ticker}' ({source_image_url[:60]})")
            return fp

    queries = _build_search_queries(visual_hint, name, keywords)

    # 1. DuckDuckGo image search
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

    # 3. Pollinations.ai — AI generation fallback
    prompt = _build_pollinations_prompt(name, visual_hint, story_title, keywords)
    filepath = _generate_with_pollinations(prompt, ticker)
    if filepath:
        logging.info(f"Image: Pollinations.ai OK for '{ticker}'")
        return filepath

    # 4. Placeholder
    logging.warning(f"Image: all sources failed, using placeholder for '{ticker}'")
    return _create_placeholder(ticker, name)


# ---------------------------------------------------------------
# Pollinations.ai — AI generation (coherent cartoon mascots)
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
        logging.info(f"Pollinations: requesting image for '{ticker}'")
        resp = requests.get(url, timeout=60, headers={"User-Agent": "TrendBot/3.0"})

        if resp.status_code != 200:
            logging.warning(f"Pollinations: HTTP {resp.status_code}")
            return None

        # Must be an actual image, not an HTML error page
        content_type = resp.headers.get("content-type", "")
        if "image" not in content_type:
            logging.warning(f"Pollinations: got non-image content-type '{content_type}'")
            return None

        content = resp.content
        if len(content) < 3000:
            logging.warning(f"Pollinations: response too small ({len(content)} bytes)")
            return None

        filename = f"{_safe_ticker(ticker)}_{hashlib.md5(content[:500]).hexdigest()[:8]}_ai.png"
        filepath = os.path.join(IMAGE_DIR, filename)
        result = _save_image(content, filepath)
        if not result:
            logging.warning(f"Pollinations: save failed for '{ticker}'")
        return result

    except Exception as e:
        logging.warning(f"Pollinations failed: {e}")
        return None


# ---------------------------------------------------------------
# DuckDuckGo — clipart/illustration search
# ---------------------------------------------------------------

def _search_ddg(query, ticker):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=10))
        for r in results:
            url = r.get("image", "")
            if url and not _is_news_photo_url(url):
                fp = _download_and_save(url, ticker)
                if fp:
                    return fp
    except Exception as e:
        logging.warning(f"DDG search failed: {e}")
    return None


# ---------------------------------------------------------------
# Bing — scraping fallback (illustration-biased)
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
            logging.warning(f"Bing: HTTP {resp.status_code} for '{query}'")
            return None

        # Bing embeds image URLs in JSON-like blocks — two known patterns
        img_urls = re.findall(r'"murl"\s*:\s*"(https?://[^"]+)"', resp.text)
        if not img_urls:
            img_urls = re.findall(r'imgurl=([^&"]+)', resp.text)

        logging.info(f"Bing: found {len(img_urls)} URLs for '{query}'")
        for img_url in img_urls[:10]:
            if any(x in img_url.lower() for x in [".svg", "icon", "pixel"]):
                continue
            if _is_news_photo_url(img_url):
                continue
            fp = _download_and_save(img_url, ticker)
            if fp:
                return fp

    except Exception as e:
        logging.warning(f"Bing search failed: {e}")
    return None


def _build_search_queries(visual_hint, name, keywords):
    """Build search queries from visual description, name, and keywords."""
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
    # SSRF guard: reject private IPs, loopback, non-HTTP(S), etc.
    if not _is_safe_url(image_url):
        logging.warning(f"Image blocked (SSRF guard): {image_url[:80]}")
        return None
    try:
        resp = requests.get(image_url, timeout=8, stream=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        if resp.status_code != 200:
            return None

        content = resp.content
        if len(content) < 5000 or len(content) > 10_000_000:
            return None

        safe = _safe_ticker(ticker)
        img_hash = hashlib.md5(content[:1000]).hexdigest()[:8]
        filepath = os.path.join(IMAGE_DIR, f"{safe}_{img_hash}.png")
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
    # Plain colored square — no text, no words, no letters on any image
    if not HAS_PIL:
        return None
    try:
        seed = sum(ord(c) for c in ticker)
        colors = [
            (76, 175, 80), (33, 150, 243), (255, 152, 0),
            (156, 39, 176), (244, 67, 54), (0, 188, 212), (255, 193, 7),
        ]
        img = Image.new("RGB", TARGET_SIZE, colors[seed % len(colors)])
        filepath = os.path.join(IMAGE_DIR, f"{_safe_ticker(ticker)}_placeholder.png")
        img.save(filepath, "PNG")
        return filepath

    except Exception as e:
        logging.error(f"Placeholder failed: {e}")
        return None
