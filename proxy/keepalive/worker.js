/**
 * Keep-alive Worker — pings the Render backend on a schedule so the free-tier
 * instance never sleeps (Render sleeps after ~15min of inactivity and takes
 * ~1min to cold-start, during which Cloudflare returns 502/CORS errors to the
 * browser).
 *
 * Deploy via: wrangler deploy --name transcript-keepalive
 * Schedule is in keepalive/wrangler.toml (every 5 minutes).
 */

const BACKEND_HEALTH = "https://transcript-ai-tutor.onrender.com/debug/cookies";

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(pingBackend());
  },
  async fetch(request) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204 });
    }
    try {
      const resp = await pingBackend();
      return new Response("keepalive ok", {
        status: 200,
        headers: { "Content-Type": "text/plain" },
      });
    } catch (err) {
      return new Response("keepalive error: " + err.message, { status: 502 });
    }
  },
};

async function pingBackend() {
  const resp = await fetch(BACKEND_HEALTH, {
    method: "GET",
    headers: { "User-Agent": "keepalive/1.0" },
  });
  if (!resp.ok) {
    throw new Error("health check returned " + resp.status);
  }
  return resp;
}
