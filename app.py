"""
Instagram Reel Direct Downloader - Production & Local Web Server
Ready for Render, Railway, Vercel & GitHub Deployment
"""

import sys
import subprocess
import os
import re
import requests
from flask import Flask, request, jsonify, Response

# Ensure yt-dlp is available
try:
    import yt_dlp
except ImportError:
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp"])
        import yt_dlp
    except Exception as e:
        print(f"Warning: yt-dlp import: {e}")

app = Flask(__name__)
HTML_FILE = os.path.join(os.path.dirname(__file__), "index.html")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def extract_shortcode(url):
    clean = url.split("?")[0].strip()
    match = re.search(r"(?:reel|reels|p)/([A-Za-z0-9_-]+)", clean)
    return match.group(1) if match else None

def get_direct_video_url(reel_url):
    shortcode = extract_shortcode(reel_url)
    clean_url = f"https://www.instagram.com/reel/{shortcode}/" if shortcode else reel_url

    # 1. yt-dlp
    try:
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            video_url = info.get('url')
            if not video_url and 'formats' in info:
                formats = [f for f in info['formats'] if f.get('vcodec') != 'none']
                if formats:
                    video_url = formats[-1].get('url')
            if video_url:
                return video_url, shortcode
    except Exception as e:
        print(f"yt-dlp note: {e}")

    # 2. Cobalt API Fallback
    try:
        cob_res = requests.post(
            "https://api.cobalt.tools",
            json={"url": clean_url},
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=8
        )
        if cob_res.status_code == 200:
            cob_data = cob_res.json()
            if cob_data.get("url"):
                return cob_data["url"], shortcode
    except Exception:
        pass

    # 3. Embed scrape fallback
    try:
        embed_url = f"https://www.instagram.com/reel/{shortcode}/embed/captioned/"
        r = requests.get(embed_url, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            matches = re.findall(r'(https://[^"\s\\]+?\.mp4[^"\s\\]*)', r.text)
            for m in matches:
                clean_mp4 = m.encode('utf-8').decode('unicode-escape').replace("&amp;", "&")
                if "cdninstagram.com" in clean_mp4 or "fbcdn.net" in clean_mp4:
                    return clean_mp4, shortcode
    except Exception:
        pass

    return None, shortcode

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

@app.route("/")
def home():
    if os.path.exists(HTML_FILE):
        with open(HTML_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return "index.html not found!"

@app.route("/api/get_video", methods=["POST", "OPTIONS"])
def api_get_video():
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"success": False, "error": "URL is required"}), 400

    video_url, shortcode = get_direct_video_url(url)
    
    return jsonify({
        "success": True,
        "shortcode": shortcode,
        "video_url": video_url,
        "embed_url": f"https://www.instagram.com/reel/{shortcode}/embed/captioned/" if shortcode else ""
    })

@app.route("/api/download")
def api_download():
    video_url = request.args.get("url", "").strip()
    shortcode = request.args.get("shortcode", "").strip()

    if not video_url and shortcode:
        video_url, _ = get_direct_video_url(f"https://www.instagram.com/reel/{shortcode}/")

    if not video_url:
        return "કૃપા કરીને લિંક ફરી તપાસો.", 400

    filename = f"Instagram_Reel_{shortcode or 'video'}.mp4"

    try:
        remote = requests.get(video_url, headers=HEADERS, stream=True, timeout=30)
        
        def generate():
            for chunk in remote.iter_content(chunk_size=128 * 1024):
                if chunk:
                    yield chunk

        resp_headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "video/mp4",
        }
        content_length = remote.headers.get("Content-Length")
        if content_length:
            resp_headers["Content-Length"] = content_length

        return Response(generate(), headers=resp_headers)

    except Exception as e:
        return f"Download stream failed: {e}", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print("  INSTAGRAM DIRECT REEL DOWNLOADER SERVER")
    print(f"  Running on port {port}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=False)
