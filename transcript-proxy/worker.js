/**
 * Cloudflare Worker — YouTube Transcript Proxy
 *
 * Deploy (free, 100K req/day):
 *   1. Go to https://dash.cloudflare.com → Workers & Pages → Create
 *   2. Name it e.g. "yt-transcript-proxy"
 *   3. Paste this entire file
 *   4. Deploy
 *   5. Copy the URL (e.g. https://yt-transcript-proxy.YOUR_SUBDOMAIN.workers.dev)
 *   6. Set TRANSCRIPT_PROXY env var on Render to that URL
 *
 * Usage:
 *   GET  https://<worker-url>/?v=dQw4w9WgXcQ
 *   GET  https://<worker-url>/dQw4w9WgXcQ
 *
 * Returns:
 *   { "ok": true,  "text": "..." }
 *   { "ok": false, "error": "..." }
 */

const HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
  Accept-Language: "en-US,en;q=0.9",
};

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function extractVideoId(url) {
  if (!url) return null;
  const m = url.match(/(?:v=|\/)([a-zA-Z0-9_-]{11})(?:[&?]|$)/);
  if (m) return m[1];
  const parts = url.split("/");
  const last = parts[parts.length - 1];
  return last && last.length === 11 ? last : null;
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

function stripTags(s) {
  return s.replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/\s+/g, " ").trim();
}

async function fetchTranscript(videoId) {
  const watchUrl = `https://www.youtube.com/watch?v=${videoId}`;

  const pageResp = await fetch(watchUrl, { headers: HEADERS, redirect: "follow" });
  if (!pageResp.ok) throw new Error(`YouTube returned ${pageResp.status}`);

  const html = await pageResp.text();

  // Look for captions in the ytInitialPlayerResponse
  const prMatch = html.match(/ytInitialPlayerResponse\s*=\s*(\{.+?\});\s*(?:var\s|<\/script>)/s);
  if (!prMatch) throw new Error("Could not find player response on page");

  let playerResponse;
  try {
    playerResponse = JSON.parse(prMatch[1]);
  } catch {
    throw new Error("Failed to parse player response JSON");
  }

  const captions = playerResponse?.captions?.playerCaptionsTracklistRenderer?.captionTracks;
  if (!captions || !captions.length) {
    throw new Error("No captions found for this video");
  }

  // Prefer English, fall back to first available
  let track =
    captions.find((t) => t.languageCode === "en") ||
    captions.find((t) => t.languageCode?.startsWith("en")) ||
    captions[0];

  let captionUrl = track.baseUrl;
  if (!captionUrl) throw new Error("Caption track has no URL");

  // Request JSON3 format for easier parsing
  if (!captionUrl.includes("fmt=")) {
    captionUrl += "&fmt=json3";
  }

  const capResp = await fetch(captionUrl, { headers: HEADERS });
  if (!capResp.ok) throw new Error(`Caption fetch returned ${capResp.status}`);

  const contentType = capResp.headers.get("content-type") || "";
  const body = await capResp.text();

  if (contentType.includes("json") || body.trim().startsWith("{")) {
    // JSON3 format
    try {
      const data = JSON.parse(body);
      const events = data.events || [];
      const parts = [];
      for (const ev of events) {
        if (ev.segs) {
          for (const seg of ev.segs) {
            if (seg.utf8 && seg.utf8 !== "\n") {
              parts.push(seg.utf8);
            }
          }
        }
      }
      return parts.join(" ").replace(/\s+/g, " ").trim();
    } catch {
      // Fall through to XML parsing
    }
  }

  // XML format — strip tags
  return stripTags(body);
}

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    // Extract video ID from query param or path
    let videoId = url.searchParams.get("v") || url.searchParams.get("videoId");
    if (!videoId) {
      const pathParts = url.pathname.split("/").filter(Boolean);
      if (pathParts.length >= 1) videoId = pathParts[pathParts.length - 1];
    }

    if (!videoId || videoId.length !== 11) {
      return json({ ok: false, error: "Missing or invalid video ID" }, 400);
    }

    try {
      const text = await fetchTranscript(videoId);
      return json({ ok: true, text });
    } catch (err) {
      return json({ ok: false, error: err.message || "Transcript fetch failed" }, 502);
    }
  },
};
