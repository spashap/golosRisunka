# Gemini long-call drops (502 / "Server disconnected") — root cause + fix

> Cross-project note for **shepotZvezd**, written from the golosrisunka.ru fix (2026-06-26).
> Both projects share the same Fornex VPS and the same `*-proxy.spashap.workers.dev`
> Cloudflare-Worker pattern, and both call **Gemini Pro/Flash** for long report generation —
> so shepotZvezd is exposed to the identical failure. This note is self-contained: read it,
> find your own call site, apply the same one-line-shaped change.

---

## TL;DR

Long **non-streaming** Gemini calls (`generate_content`) intermittently fail with
`httpx.RemoteProtocolError: Server disconnected without sending a response` or `502 Bad Gateway`.
Cause: while Gemini 2.5 Pro "thinks" for 60–120 s, **zero bytes flow** over the connection, and an
idle-timeout somewhere in the path (Gemini's own frontend at ~60 s, and/or Cloudflare at ~100 s)
**kills the idle socket**. The fix is to **stream** the call (`generate_content_stream`) so chunks
flow continuously and no hop ever sees an idle connection. Output JSON/text is identical — just
assembled from chunks. **No proxy/Worker change is needed** (a passthrough Worker already streams).

---

## Symptom

In the report worker / generation logs, on calls that take a while:

```
attempt 1: RemoteProtocolError: Server disconnected without sending a response.
attempt 4: ServerError: 502 Bad Gateway   (Cloudflare HTML page, cf-host-status: Error)
```

It's **intermittent** because it depends on how long the model thinks on a given request: short
reports finish under the limit, long ones (full natal/PDF reports on Gemini **Pro**) cross it.
Raising the httpx `timeout` does **not** help — it's not the client timing out, it's an
intermediary actively closing a byte-less socket.

## Root cause (the mechanism)

A non-streaming `generate_content` opens the HTTP request, then **waits in silence** until the
entire answer is ready. For Gemini 2.5 **Pro** that silence is routinely 60–120 s. Two documented
idle-cut points sit in the path, either of which severs the connection:

1. **Google's own frontend** drops non-streamed calls that think **> ~60 s** (well-documented for
   `gemini-2.5-pro`/`flash`).
2. **Cloudflare** enforces a **~100 s idle/response timeout** on Free/Pro plans; long byte-less
   inference exceeds it.

Crucially: **a passthrough Worker can only stream bytes that exist.** During the think phase there
are *no* bytes to pass, so whether the Worker buffers or streams is irrelevant — the idle-cut
happens upstream of it. That's why the fix is on the **client (Python) side**, not the proxy.

## The fix — stream end-to-end

Switch the blocking call to the streaming variant and join the chunks. This is what we did in
golosrisunka `pipeline/gemini.py` (both the main generation call **and** the linter "repair" call):

```python
# BEFORE  (non-streaming — silent for 60-120s -> idle socket gets cut)
resp = client.models.generate_content(model=MODEL, contents=parts, config=config)
raw = resp.text or ""

# AFTER  (streaming — chunks flow continuously, every hop stays "alive")
chunks: list[str] = []
for chunk in client.models.generate_content_stream(
        model=MODEL, contents=parts, config=config):
    if chunk.text:
        chunks.append(chunk.text)
raw = "".join(chunks)
```

Notes that make this a safe, mechanical swap:
- **`response_mime_type="application/json"` still works.** Chunks are partial JSON text; concatenate
  all of them, then `json.loads` the whole — identical result to non-streaming.
- **Everything downstream is unchanged**: JSON parse, schema validation, retries, the per-request
  timeout. The timeout simply stops tripping because each chunk read resets the idle clock.
- **`if chunk.text:`** guards chunks that carry no text (thinking-only / safety blocks); a blocked
  response still surfaces as an exception inside your existing try/except → counts as a failed
  attempt → retries, same as before.
- **`google-genai` SDK**: `client.models.generate_content_stream(...)` (we verified on SDK 2.8.0).
  If you're on the older `google-generativeai` SDK, the equivalent is
  `model.generate_content(..., stream=True)` then iterate and join `chunk.text`.
- **Streaming hits `:streamGenerateContent?alt=sse`** (content-type `text/event-stream`), which
  Cloudflare does **not** buffer — a second reason SSE specifically avoids the cut.

## The Worker proxy needs NO change (but verify it's a passthrough)

golosrisunka's `gemini-proxy.spashap.workers.dev` is a clean streaming passthrough — it returns the
`fetch()` Response directly and forwards `pathname + search` verbatim, so `:streamGenerateContent`
just works:

```js
export default {
  async fetch(request) {
    const url = new URL(request.url);
    const target = "https://generativelanguage.googleapis.com" + url.pathname + url.search;
    const headers = new Headers(request.headers);
    headers.delete("host");
    return fetch(target, {
      method: request.method, headers,
      body: ["GET","HEAD"].includes(request.method) ? undefined : request.body,
    });
  },
};
```

If your Gemini-proxy Worker looks like this — **leave it alone**. The only thing that would make a
Worker *itself* the culprit is **buffering**: if it does `await response.text()` / `await
response.json()` before returning, it holds the whole reply and re-creates the idle-cut even after
you stream on the Python side. Fix that by returning `new Response(response.body, { headers })`
(stream the body through). The Worker above already does the right thing implicitly.

> Note: this is a *different* Worker from `tg-proxy.spashap.workers.dev` (Telegram long-polling).
> Telegram calls are short and not affected by this — this note is only about **Gemini** generation.

## Where shepotZvezd is exposed (apply here)

Per shepotZvezd CLAUDE.md:
- **Full PDF reports**: `report_worker → ephemeris → Gemini Pro/Flash → PDF → email` — **Gemini Pro
  is the high-risk path** (longest think time). Find the `generate_content(` call(s) in
  `src/services/report/` generators (basic/event/compat) and apply the streaming swap above.
- **Minireports (149/99₽)**: Gemini **Flash Lite** → `result_json`. Lower risk (Flash is fast), but
  apply the same swap for consistency and headroom — it's free to do and removes the tail risk.
- **Preview Reveal cells**: AI-generated cells; if they go through Gemini and can run long, same swap.

Grep the repo for `generate_content(` (note the open paren, to exclude `generate_content_stream(`)
to enumerate every non-streaming call site, then convert each. A tiny "ping"/healthcheck call that
returns instantly can stay non-streaming — only the long generation calls matter.

## Complementary safety net (optional but recommended)

Streaming removes the **root cause**; a worker-level **auto-retry** absorbs the residual genuine
blips. In golosrisunka we made the report worker, on a *transient* failure (network/5xx/timeout
markers), re-queue the order with exponential backoff (`[5,15,30,60,120]` min, bounded count)
instead of dying permanently — so an occasional drop self-heals with no manual regenerate, and the
admin is alerted only after auto-retries are exhausted. Worth mirroring if shepotZvezd currently
needs manual re-runs after a failed generation.

## Sources

- Google AI forum — "60s timeout from python sdk": https://discuss.ai.google.dev/t/60s-timeout-from-python-sdk/83274
- python-genai #1617 — "Server disconnected" on gemini-2.5-pro/flash: https://github.com/googleapis/python-genai/issues/1617
- LibreChat #6082 — 100-second Cloudflare timeout on long LLM requests: https://github.com/danny-avila/LibreChat/discussions/6082
- open-webui #16747 — API timeout after 100 s with long-running tools: https://github.com/open-webui/open-webui/issues/16747
- Cloudflare Workers limits (no default subrequest timeout; idle limits apply): https://developers.cloudflare.com/workers/platform/limits/

---
*Origin: golosrisunka.ru `pipeline/gemini.py` streaming switch, 2026-06-26. See that repo's
`UseCasesData.md` #27 and `DevelopmentStatus.md` (26.06) for the full incident trail.*
