/**
 * Cloudflare Worker — YouTube Transcript Proxy (v2, innertube API)
 *
 * Deploy (free, 100K req/day):
 *   1. Go to https://dash.cloudflare.com → Workers & Pages → Create → Create Worker
 *   2. Name it e.g. "transcript-proxy"
 *   3. Paste this entire file
 *   4. Deploy → Save and deploy
 *   5. Copy the URL → e.g. https://transcript-proxy.YOUR_SUBDOMAIN.workers.dev
 *   6. Set TRANSCRIPT_PROXY env var on Render to that URL
 *
 * Usage:
 *   GET  https://<worker-url>/?v=dQw4w9WgXcQ
 *
 * Returns:
 *   { "ok": true,  "text": "..." }
 *   { "ok": false, "error": "..." }
 */

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

const HEADERS = {
  "User-Agent": UA,
  "Accept-Language": "en-US,en;q=0.9",
};

const INNERTUBE_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8";
const INNERTUBE_API = "https://www.youtube.com/youtubei/v1/player";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

function stripTags(s) {
  return s
    .replace(/<[^>]+>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&#39;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/\s+/g, " ")
    .trim();
}

async function getCaptionTracks(videoId) {
  // Try the innertube player API first (robust, no HTML parsing)
  const body = JSON.stringify({
    context: {
      client: {
        clientName: "WEB",
        clientVersion: "2.20240827.00.00",
        hl: "en",
        visitorData: "CgtIRFlsdHVXd2lBSSjTscuSBzIKCwIJHJCv6euGBQ%3D%3D",
      },
    },
    videoId,
    contentCheckOk: true,
    racyCheckOk: true,
  });

  const apiResp = await fetch(`${INNERTUBE_API}?key=${INNERTUBE_KEY}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "User-Agent": UA,
      "Accept-Language": "en-US,en;q=0.9",
    },
    body,
  });

  if (apiResp.ok) {
    const data = await apiResp.json();
    const tracks =
      data?.captions?.playerCaptionsTracklistRenderer?.captionTracks;
    if (tracks && tracks.length) return tracks;
  }

  // Fallback: parse the watch page HTML
  const pageResp = await fetch(`https://www.youtube.com/watch?v=${videoId}`, {
    headers: HEADERS,
    redirect: "follow",
  });
  if (!pageResp.ok) throw new Error(`YouTube returned ${pageResp.status}`);
  const html = await pageResp.text();

  const prMatch = html.match(
    /ytInitialPlayerResponse\s*=\s*(\{.+?\});\s*(?:var\s|<\/script>)/s
  );
  if (!prMatch) throw new Error("Could not find player response on page");

  let pr;
  try {
    pr = JSON.parse(prMatch[1]);
  } catch {
    throw new Error("Failed to parse player response JSON");
  }

  const tracks =
    pr?.captions?.playerCaptionsTracklistRenderer?.captionTracks;
  if (!tracks || !tracks.length)
    throw new Error("No captions found for this video");
  return tracks;
}

async function fetchTranscript(videoId) {
  const tracks = await getCaptionTracks(videoId);

  const track =
    tracks.find((t) => t.languageCode === "en") ||
    tracks.find((t) => t.languageCode?.startsWith("en")) ||
    tracks.find((t) => t.kind !== "asr") ||
    tracks[0];

  let captionUrl = track.baseUrl;
  if (!captionUrl) throw new Error("Caption track has no URL");
  if (!captionUrl.includes("fmt=")) captionUrl += "&fmt=json3";

  const capResp = await fetch(captionUrl, {
    headers: { ...HEADERS, Referer: `https://www.youtube.com/watch?v=${videoId}` },
  });
  if (!capResp.ok)
    throw new Error(`Caption fetch returned ${capResp.status}`);

  const body = await capResp.text();

  if (body.trim().startsWith("{")) {
    try {
      const data = JSON.parse(body);
      const parts = [];
      for (const ev of data.events || []) {
        for (const seg of ev.segs || []) {
          if (seg.utf8 && seg.utf8 !== "\n") parts.push(seg.utf8);
        }
      }
      if (parts.length) return parts.join(" ").replace(/\s+/g, " ").trim();
    } catch {
      // fall through to XML parsing
    }
  }

  return stripTags(body);
}

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    let videoId =
      url.searchParams.get("v") || url.searchParams.get("videoId");
    if (!videoId) {
      const parts = url.pathname.split("/").filter(Boolean);
      if (parts.length) videoId = parts[parts.length - 1];
    }

    if (!videoId || videoId.length !== 11) {
      return json({ ok: false, error: "Missing or invalid video ID" }, 400);
    }

    try {
      const text = await fetchTranscript(videoId);
      return json({ ok: true, text });
    } catch (err) {
      return json(
        { ok: false, error: err.message || "Transcript fetch failed" },
        502
      );
    }
  },
};