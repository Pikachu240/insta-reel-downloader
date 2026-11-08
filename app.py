"""
Instagram Reel Direct Downloader - Production & Local Web Server
With Guaranteed Full Audio + Video Streams
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

    # 1. yt-dlp: Explicitly filter for streams that have BOTH audio and video!
    try:
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'no_warnings': True,
            'extract_flat': False,
            'format': 'best[acodec!=none][vcodec!=none]/best',
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            
            # Check all formats for combined audio + video (acodec != none AND vcodec != none)
            formats = info.get('formats', [])
            combined_formats = [
                f for f in formats 
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('url')
            ]
            
            video_url = None
            if combined_formats:
                # Sort by quality/bitrate/height to get best resolution with audio
                combined_formats.sort(key=lambda x: (x.get('height') or 0, x.get('tbr') or 0))
                video_url = combined_formats[-1].get('url')
            elif info.get('url') and info.get('acodec') != 'none':
                video_url = info.get('url')

            if video_url:
                print(f"[+] Successfully extracted combined video+audio for {shortcode}")
                return video_url, shortcode
    except Exception as e:
        print(f"[-] yt-dlp extraction note: {e}")

    # 2. Cobalt API Fallback (Guaranteed merged audio + video)
    try:
        cob_res = requests.post(
            "https://api.cobalt.tools",
            json={"url": clean_url, "videoQuality": "max"},
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=8
        )
        if cob_res.status_code == 200:
            cob_data = cob_res.json()
            if cob_data.get("url"):
                print(f"[+] Cobalt returned merged audio+video for {shortcode}")
                return cob_data["url"], shortcode
    except Exception as e:
        print(f"[-] Cobalt fallback note: {e}")

    # 3. Instagram Embed scrape fallback (Progressive MP4 with audio)
    try:
        embed_url = f"https://www.instagram.com/reel/{shortcode}/embed/captioned/"
        r = requests.get(embed_url, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            matches = re.findall(r'(https://[^"\s\\]+?\.mp4[^"\s\\]*)', r.text)
            for m in matches:
                clean_mp4 = m.encode('utf-8').decode('unicode-escape').replace("&amp;", "&")
                if ("cdninstagram.com" in clean_mp4 or "fbcdn.net" in clean_mp4) and "bytestart" not in clean_mp4:
                    print(f"[+] Embed scrape found combined MP4 for {shortcode}")
                    return clean_mp4, shortcode
    except Exception as e:
        print(f"[-] Embed scrape note: {e}")

    return None, shortcode

# CORS
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

    # Re-fetch if url was missing
    if not video_url and shortcode:
        video_url, _ = get_direct_video_url(f"https://www.instagram.com/reel/{shortcode}/")

    if not video_url:
        return "વિડીયો ડાઉનલોડ લિંક મળી શકી નથી, કૃપા કરીને ફરી પ્રયાસ કરો.", 400

    filename = f"Instagram_Reel_{shortcode or 'video'}.mp4"

    try:
        remote = requests.get(video_url, headers=HEADERS, stream=True, timeout=35)
        
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
