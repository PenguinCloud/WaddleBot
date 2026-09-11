"""Server-side HTML renderers for every OBS browser-source surface.

Vanilla HTML+JS, no build step, no heavy framework (task requirement) --
every surface embeds a small inline `<script>` that opens a real
`EventSource` against this same service's `/overlay/<community>/<surface>/
live` SSE route (`services/presentation_hub.py`) for live push updates.
Community/surface path segments are `html.escape()`d wherever reflected
(security.md Input Validation: escape outputs) -- the surfaces this module
renders are otherwise open (no per-community overlay-key auth wired yet,
matching this scaffold's pre-existing, explicitly-documented posture; see
`docs/plans/2026-08-31-music-station-design.md` §11.9, still an open
decision, not silently skipped).
"""

from __future__ import annotations

import html
import json
from typing import Any

#: Shared dark-glass styling, close to
#: `core/browser_source_core_module/templates/music-player-overlay.html`'s
#: existing look so the Music Station reads as a sibling of the legacy
#: overlay it supersedes, not a visual break.
_BASE_STYLE = """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: var(--wb-font, 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif);
      background: transparent; overflow: hidden; color: #fff; }
    .hidden { display: none !important; }
"""


def _theme_style(
    *,
    primary_color: str | None = None,
    secondary_color: str | None = None,
    font_family: str | None = None,
) -> str:
    """Build a `:root{...}` CSS-variable block from `presentation_config` overrides.

    Real per-community theming, not decoration: `services/render.py`'s
    callers pull these three fields from
    `services/presentation_config_service.get_theme_config()` (backed by
    the `presentation_config` table, migration 073) and every surface
    below consumes them via `var(--wb-primary, <default>)` -- an unset
    field falls through to the same default it always had.
    """
    primary = html.escape(primary_color) if primary_color else "#1db954"
    secondary = html.escape(secondary_color) if secondary_color else "#1ed760"
    default_font = "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif"
    font = html.escape(font_family) if font_family else default_font
    return f"""
    <style>
      :root {{
        --wb-primary: {primary};
        --wb-secondary: {secondary};
        --wb-font: {font};
      }}
    </style>
    """


def _sse_bootstrap_script(community: str, surface: str, on_message_body: str) -> str:
    """Build the `<script>` block every surface uses to open its live SSE connection.

    `on_message_body` is raw, trusted JS (authored in this file only, never
    from a request) injected into the `EventSource.onmessage` handler body.
    """
    safe_community = json.dumps(community)
    safe_surface = json.dumps(surface)
    return f"""
    <script>
      const community = {safe_community};
      const surface = {safe_surface};
      const source = new EventSource(`/overlay/${{community}}/${{surface}}/live`);
      source.onmessage = (event) => {{
        const data = JSON.parse(event.data);
        {on_message_body}
      }};
      source.onerror = (err) => {{
        console.error('presentation live connection error', err);
      }};
    </script>
    """


def render_full_screen(
    community: str,
    surface: str,
    *,
    primary_color: str | None = None,
    secondary_color: str | None = None,
    font_family: str | None = None,
) -> str:
    """Full-bleed overlay surface -- pushed content replaces the entire visible area."""
    safe_community = html.escape(community)
    safe_surface = html.escape(surface)
    theme_style = _theme_style(
        primary_color=primary_color, secondary_color=secondary_color, font_family=font_family
    )
    on_message = """
        if (!data || data.type === 'clear') {
          document.getElementById('content').classList.add('hidden');
          return;
        }
        const el = document.getElementById('content');
        el.classList.remove('hidden');
        document.getElementById('title').textContent = data.title || '';
        document.getElementById('body').textContent = data.body || '';
        const img = document.getElementById('image');
        if (data.image_url && /^https?:\\/\\//.test(data.image_url)) {
          img.src = data.image_url;
          img.classList.remove('hidden');
        } else {
          img.classList.add('hidden');
          img.removeAttribute('src');
        }
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>svc-presentation -- full_screen -- {safe_community}</title>
{theme_style}
<style>
{_BASE_STYLE}
    #content {{ position: fixed; inset: 0; display: flex; flex-direction: column;
      align-items: center; justify-content: center; text-align: center; padding: 40px; }}
    #image {{ max-width: 80%; max-height: 60%; border-radius: 12px; margin-bottom: 24px; }}
    #title {{ font-size: 48px; font-weight: bold; color: var(--wb-primary, #fff);
      text-shadow: 0 2px 8px rgba(0,0,0,0.7); }}
    #body {{ font-size: 24px; margin-top: 12px; text-shadow: 0 1px 4px rgba(0,0,0,0.7); }}
</style>
</head>
<body data-community="{safe_community}" data-surface="{safe_surface}">
  <div id="content" class="hidden">
    <img id="image" class="hidden" alt="">
    <div id="title"></div>
    <div id="body"></div>
  </div>
  {_sse_bootstrap_script(community, surface, on_message)}
</body>
</html>"""


def render_media(
    community: str,
    surface: str,
    *,
    primary_color: str | None = None,
    secondary_color: str | None = None,
    font_family: str | None = None,
) -> str:
    """Media / lower-third overlay surface -- bottom-left card, pushed content updates it."""
    safe_community = html.escape(community)
    safe_surface = html.escape(surface)
    theme_style = _theme_style(
        primary_color=primary_color, secondary_color=secondary_color, font_family=font_family
    )
    on_message = """
        const card = document.getElementById('card');
        if (!data || data.type === 'clear') {
          card.classList.add('hidden');
          return;
        }
        card.classList.remove('hidden');
        document.getElementById('title').textContent = data.title || '';
        document.getElementById('body').textContent = data.body || '';
        const img = document.getElementById('image');
        if (data.image_url && /^https?:\\/\\//.test(data.image_url)) {
          img.src = data.image_url;
          img.classList.remove('hidden');
        } else {
          img.classList.add('hidden');
          img.removeAttribute('src');
        }
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>svc-presentation -- media -- {safe_community}</title>
{theme_style}
<style>
{_BASE_STYLE}
    #card {{ position: fixed; bottom: 24px; left: 24px; max-width: 480px;
      background: linear-gradient(135deg, rgba(0,0,0,0.85), rgba(20,20,20,0.85));
      border-radius: 14px; padding: 18px 22px; backdrop-filter: blur(10px);
      box-shadow: 0 8px 32px rgba(0,0,0,0.5); display: flex; gap: 14px; align-items: center; }}
    #image {{ width: 72px; height: 72px; border-radius: 8px; object-fit: cover; }}
    #title {{ font-size: 20px; font-weight: bold; color: var(--wb-primary, #fff); }}
    #body {{ font-size: 15px; color: #ccc; margin-top: 4px; }}
</style>
</head>
<body data-community="{safe_community}" data-surface="{safe_surface}">
  <div id="card" class="hidden">
    <img id="image" class="hidden" alt="">
    <div>
      <div id="title"></div>
      <div id="body"></div>
    </div>
  </div>
  {_sse_bootstrap_script(community, surface, on_message)}
</body>
</html>"""


def render_crawler(
    community: str,
    surface: str,
    *,
    primary_color: str | None = None,
    secondary_color: str | None = None,
    font_family: str | None = None,
) -> str:
    """Bottom-screen scrolling ticker surface -- pushed text scrolls right-to-left."""
    safe_community = html.escape(community)
    safe_surface = html.escape(surface)
    theme_style = _theme_style(
        primary_color=primary_color, secondary_color=secondary_color, font_family=font_family
    )
    on_message = """
        const track = document.getElementById('track');
        track.textContent = (data && data.text) ? data.text : '';
        track.classList.toggle('hidden', !track.textContent);
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>svc-presentation -- crawler -- {safe_community}</title>
{theme_style}
<style>
{_BASE_STYLE}
    #ticker {{ position: fixed; bottom: 0; left: 0; right: 0; height: 56px;
      background: rgba(0,0,0,0.75); display: flex; align-items: center; overflow: hidden; }}
    #track {{ white-space: nowrap; font-size: 26px; font-weight: 600;
      color: var(--wb-primary, #fff);
      padding-left: 100%; animation: scroll-left 20s linear infinite; }}
    @keyframes scroll-left {{
      0% {{ transform: translateX(0); }}
      100% {{ transform: translateX(-100%); }}
    }}
</style>
</head>
<body data-community="{safe_community}" data-surface="{safe_surface}">
  <div id="ticker">
    <div id="track" class="hidden"></div>
  </div>
  {_sse_bootstrap_script(community, surface, on_message)}
</body>
</html>"""


def render_music(
    community: str,
    *,
    primary_color: str | None = None,
    secondary_color: str | None = None,
    font_family: str | None = None,
) -> str:
    """Music Station browser-source player -- now-playing + upcoming queue, polling `/queue`.

    Embeds the YouTube IFrame API player for `provider == "youtube"` tracks
    and a Spotify Embed Controller (iFrame API) for `provider == "spotify"`
    tracks (task scope). Other providers (e.g. SoundCloud) still render in
    the now-playing/queue list, honestly without a player embed.

    Queue advance is client-driven off real playback end signals (YouTube
    `onStateChange === ENDED`; Spotify's Embed Controller `playback_update`
    event reaching `position >= duration - END_THRESHOLD_MS`, PLUS a
    `duration_ms`-based timer fallback since Spotify's iFrame API documents
    no explicit "ended" event -- only periodic `playback_update` ticks, so
    a dropped/never-fired tick must not permanently stall the overlay) and
    by the server's own lazy auto-advance surfacing on the next 5s poll
    (a changed `now_playing.queue_id` reloads the player exactly like a
    client-triggered advance does).
    """
    safe_community = html.escape(community)
    theme_style = _theme_style(
        primary_color=primary_color, secondary_color=secondary_color, font_family=font_family
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>svc-presentation -- music -- {safe_community}</title>
{theme_style}
<style>
{_BASE_STYLE}
    #station {{ position: fixed; bottom: 20px; right: 20px; width: 420px;
      background: linear-gradient(135deg, rgba(0,0,0,0.88), rgba(20,20,20,0.88));
      border-radius: 16px; padding: 20px; backdrop-filter: blur(10px);
      box-shadow: 0 8px 32px rgba(0,0,0,0.5); }}
    #player-slot {{ width: 100%; height: 200px; border-radius: 10px; margin-bottom: 14px;
      background: #111; overflow: hidden; }}
    #player-slot iframe {{ width: 100%; height: 100%; border: 0; }}
    #now-playing .title {{ font-size: 19px; font-weight: bold; }}
    #now-playing .artist {{ font-size: 15px; color: #ccc; margin-top: 2px; }}
    #progress-bar {{ width: 100%; height: 4px; background: rgba(255,255,255,0.2);
      border-radius: 2px; margin-top: 12px; overflow: hidden; }}
    #progress-fill {{ height: 100%; width: 0%;
      background: linear-gradient(90deg, var(--wb-primary, #1db954), var(--wb-secondary, #1ed760));
      transition: width 0.25s linear; }}
    #up-next {{ margin-top: 16px; font-size: 13px; color: #aaa; }}
    #up-next-list {{ list-style: none; margin-top: 6px; max-height: 120px; overflow-y: auto; }}
    #up-next-list li {{ padding: 4px 0; border-top: 1px solid rgba(255,255,255,0.08); }}
    #empty-state {{ font-size: 14px; color: #999; text-align: center; padding: 20px 0; }}
    #np-requested-by {{ font-size: 12px; color: #888; margin-top: 4px; }}
    #np-paused-badge {{ font-size: 12px; font-weight: 600; margin-top: 4px;
      color: var(--wb-primary, #1db954); }}
</style>
</head>
<body data-community="{safe_community}" data-surface="music">
  <div id="station">
    <div id="player-slot"></div>
    <div id="now-playing" class="hidden">
      <div class="title" id="np-title"></div>
      <div class="artist" id="np-artist"></div>
      <div id="np-requested-by"></div>
      <div id="np-paused-badge" class="hidden">⏸ paused</div>
      <div id="progress-bar"><div id="progress-fill"></div></div>
    </div>
    <div id="empty-state">No tracks queued</div>
    <div id="up-next">
      Up next
      <ul id="up-next-list"></ul>
    </div>
  </div>
  <!-- No Subresource Integrity attribute on either embed script: YouTube
       and Spotify both serve these files dynamically and neither publishes
       a stable hash to pin against (the same accepted exception every
       site embedding either player relies on) -- first-party domains,
       loaded over HTTPS. -->
  <script src="https://www.youtube.com/iframe_api"></script>
  <script src="https://open.spotify.com/embed/iframe-api/v1" async></script>
  <script>
    const community = {json.dumps(community)};
    const POLL_INTERVAL_MS = 5000;
    // How close to the end (ms) a Spotify `playback_update` tick counts as
    // "ended" -- the iFrame API reports periodic position/duration, not a
    // discrete end event, so this is a threshold, not an exact boundary.
    const END_THRESHOLD_MS = 500;

    // How far (ms) the embed's actual position may drift from the server's
    // `playback.position_ms` on resume before this client seeks to correct it.
    const SEEK_DRIFT_THRESHOLD_MS = 2000;

    let currentQueueId = null;
    let trackStartedAtMs = null;
    let currentDurationMs = 0;
    let ytPlayer = null;
    let ytReady = false;
    let spotifyController = null;
    let spotifyApiReady = false;
    let spotifyIFrameAPI = null;
    let spotifyPositionMs = 0;
    let endFallbackTimer = null;
    let advanceInFlight = false;
    // Mirrors the server's last-seen `playback.paused` -- drives pause/
    // resume/seek on the embed and gates the ended handlers below so a
    // stale playback tick can never fire an advance while paused.
    let isPaused = false;

    window.onYouTubeIframeAPIReady = () => {{ ytReady = true; }};
    // Spotify's iFrame API convention: this global is called once, ever,
    // with the controller factory -- see the embed script above.
    window.onSpotifyIframeApiReady = (IFrameAPI) => {{
      spotifyApiReady = true;
      spotifyIFrameAPI = IFrameAPI;
    }};

    function clearEndFallbackTimer() {{
      if (endFallbackTimer) {{
        clearTimeout(endFallbackTimer);
        endFallbackTimer = null;
      }}
    }}

    async function advanceTrack(queueId) {{
      // Guards: never advance a track that's already been superseded by a
      // poll (server-side lazy advance already moved on), never fire two
      // overlapping advance calls for the same end event.
      if (advanceInFlight || queueId == null || queueId !== currentQueueId) return;
      advanceInFlight = true;
      try {{
        await fetch(`/overlay/${{community}}/music/advance`, {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ item_id: queueId }}),
        }});
      }} catch (err) {{
        console.error('music queue advance failed', err);
      }} finally {{
        advanceInFlight = false;
        pollQueue();
      }}
    }}

    function onYouTubeStateChange(event) {{
      // isPaused guard: a paused embed can still queue a stale ENDED event
      // (e.g. a seek-to-end race) -- never advance while the server says
      // paused, the next resumed poll is the only thing allowed to move on.
      if (window.YT && event.data === YT.PlayerState.ENDED && !isPaused) {{
        advanceTrack(currentQueueId);
      }}
    }}

    function renderPlayer(track) {{
      clearEndFallbackTimer();
      spotifyPositionMs = 0;
      const slot = document.getElementById('player-slot');
      if (track.provider === 'spotify' && track.external_id) {{
        slot.innerHTML = '<div id="spotify-target"></div>';
        ytPlayer = null;
        spotifyController = null;
        if (spotifyApiReady && spotifyIFrameAPI) {{
          spotifyIFrameAPI.createController(
            document.getElementById('spotify-target'),
            {{ uri: `spotify:track:${{track.external_id}}` }},
            (controller) => {{
              spotifyController = controller;
              controller.addListener('playback_update', (e) => {{
                const data = (e && e.data) || {{}};
                if (typeof data.position === 'number') {{
                  spotifyPositionMs = data.position;
                }}
                // isPaused guard: same rationale as onYouTubeStateChange above.
                if (
                  !isPaused &&
                  typeof data.position === 'number' &&
                  typeof data.duration === 'number' &&
                  data.duration > 0 &&
                  data.position >= data.duration - END_THRESHOLD_MS
                ) {{
                  advanceTrack(track.queue_id);
                }}
              }});
            }}
          );
        }}
        // Fallback: `duration_ms`-based timer. Spotify's iFrame API has no
        // documented explicit "ended" event -- only `playback_update`
        // ticks -- so a missed/never-fired tick must not stall the
        // overlay forever.
        if (track.duration_ms) {{
          endFallbackTimer = setTimeout(
            () => advanceTrack(track.queue_id),
            track.duration_ms + END_THRESHOLD_MS
          );
        }}
      }} else if (track.provider === 'youtube' && track.external_id) {{
        slot.innerHTML = '<div id="yt-target"></div>';
        spotifyController = null;
        if (ytReady && window.YT) {{
          ytPlayer = new YT.Player('yt-target', {{
            videoId: track.external_id,
            playerVars: {{ autoplay: 1, controls: 0, modestbranding: 1 }},
            events: {{ onStateChange: onYouTubeStateChange }},
          }});
        }}
      }} else {{
        const label = track.provider ? track.provider + ' (no embeddable player)' : '';
        slot.innerHTML =
          '<div style="display:flex;align-items:center;justify-content:center;' +
          'height:100%;color:#888;">' + label + '</div>';
        ytPlayer = null;
        spotifyController = null;
      }}
    }}

    function resetPlaybackState() {{
      isPaused = false;
      const badge = document.getElementById('np-paused-badge');
      if (badge) badge.classList.add('hidden');
    }}

    // Applies one poll's `playback` state to the live embed: pauses/resumes
    // it, seeks it back in sync with the server's `position_ms` on resume
    // (past `SEEK_DRIFT_THRESHOLD_MS`), toggles the paused badge, and
    // pauses/resumes the Spotify end-detection fallback timer alongside it
    // -- a paused track must never silently keep counting toward "ended".
    function applyPlaybackState(playback) {{
      const paused = !!(playback && playback.paused);
      const positionMs = playback && typeof playback.position_ms === 'number'
        ? playback.position_ms
        : null;
      const badge = document.getElementById('np-paused-badge');

      if (paused && !isPaused) {{
        if (ytPlayer && ytPlayer.pauseVideo) ytPlayer.pauseVideo();
        if (spotifyController && spotifyController.pause) spotifyController.pause();
        clearEndFallbackTimer();
        if (badge) badge.classList.remove('hidden');
      }} else if (!paused && isPaused) {{
        const playerPositionMs = ytPlayer && ytPlayer.getCurrentTime
          ? ytPlayer.getCurrentTime() * 1000
          : spotifyPositionMs;
        const driftMs = positionMs !== null ? Math.abs(playerPositionMs - positionMs) : 0;
        if (positionMs !== null && driftMs > SEEK_DRIFT_THRESHOLD_MS) {{
          if (ytPlayer && ytPlayer.seekTo) ytPlayer.seekTo(positionMs / 1000, true);
          if (spotifyController && spotifyController.seek) {{
            spotifyController.seek(positionMs / 1000);
          }}
        }}
        if (ytPlayer && ytPlayer.playVideo) ytPlayer.playVideo();
        if (spotifyController && spotifyController.resume) spotifyController.resume();
        if (spotifyController && currentDurationMs) {{
          const resumedAtMs = positionMs !== null ? positionMs : spotifyPositionMs;
          clearEndFallbackTimer();
          endFallbackTimer = setTimeout(
            () => advanceTrack(currentQueueId),
            Math.max(0, currentDurationMs - resumedAtMs) + END_THRESHOLD_MS
          );
        }}
        trackStartedAtMs = Date.now() - (positionMs !== null ? positionMs : playerPositionMs);
        if (badge) badge.classList.add('hidden');
      }}
      isPaused = paused;
    }}

    function renderQueue(payload) {{
      const npEl = document.getElementById('now-playing');
      const emptyEl = document.getElementById('empty-state');
      const list = document.getElementById('up-next-list');

      if (payload.available === false) {{
        npEl.classList.add('hidden');
        document.getElementById('player-slot').innerHTML = '';
        emptyEl.textContent = payload.unavailable_reason === 'service_key_not_configured'
          ? 'queue unavailable: service key not configured'
          : 'queue unavailable';
        emptyEl.classList.remove('hidden');
        list.innerHTML = '';
        currentQueueId = null;
        clearEndFallbackTimer();
        resetPlaybackState();
        return;
      }}

      const nowPlaying = payload.now_playing;
      const upcoming = payload.upcoming || [];

      if (!nowPlaying) {{
        npEl.classList.add('hidden');
        emptyEl.textContent = 'No tracks queued';
        emptyEl.classList.remove('hidden');
        document.getElementById('player-slot').innerHTML = '';
        currentQueueId = null;
        clearEndFallbackTimer();
        resetPlaybackState();
      }} else {{
        emptyEl.classList.add('hidden');
        npEl.classList.remove('hidden');
        document.getElementById('np-title').textContent = nowPlaying.name;
        document.getElementById('np-artist').textContent = nowPlaying.artist;
        const requestedBy = nowPlaying.requested_by;
        document.getElementById('np-requested-by').textContent = requestedBy
          ? `requested by ${{requestedBy.display_name}} (${{requestedBy.platform}})`
          : '';

        // Covers both a client-triggered advance's own re-fetch AND
        // hub-api's server-side lazy auto-advance showing up on an
        // ordinary 5s poll -- either way, a changed `queue_id` means load
        // the new track exactly the same way.
        if (nowPlaying.queue_id !== currentQueueId) {{
          currentQueueId = nowPlaying.queue_id;
          trackStartedAtMs = Date.now();
          currentDurationMs = nowPlaying.duration_ms || 0;
          isPaused = false;
          renderPlayer(nowPlaying);
        }}
        applyPlaybackState(payload.playback);
      }}

      list.innerHTML = '';
      for (const track of upcoming) {{
        const li = document.createElement('li');
        li.textContent = `${{track.name}} -- ${{track.artist}}`;
        list.appendChild(li);
      }}
    }}

    async function pollQueue() {{
      try {{
        const resp = await fetch(`/overlay/${{community}}/music/queue`);
        if (!resp.ok) return;
        const payload = await resp.json();
        renderQueue(payload);
      }} catch (err) {{
        console.error('music queue poll failed', err);
      }}
    }}

    setInterval(() => {{
      if (!currentQueueId || !trackStartedAtMs || !currentDurationMs || isPaused) return;
      const elapsed = Date.now() - trackStartedAtMs;
      const pct = Math.min(100, (elapsed / currentDurationMs) * 100);
      document.getElementById('progress-fill').style.width = pct + '%';
    }}, 250);

    pollQueue();
    setInterval(pollQueue, POLL_INTERVAL_MS);
  </script>
</body>
</html>"""


#: Pinned HLS.js build (issue #287 S7 §3) -- `core/svc_streaming`'s HLS
#: egress sink is the only producer this player ever points at, so a fixed
#: version (not `@latest`) matches this repo's dependency-pinning rule
#: (`rules/critical-rules.md` Dependency Pinning) even for a CDN script tag.
_HLS_JS_VERSION = "1.5.13"
_HLS_JS_SRC = f"https://cdnjs.cloudflare.com/ajax/libs/hls.js/{_HLS_JS_VERSION}/hls.min.js"


def render_live(
    community: str,
    *,
    live: bool,
    master_url: str | None,
    primary_color: str | None = None,
    secondary_color: str | None = None,
    font_family: str | None = None,
) -> str:
    """Live-stream (HLS) browser-source surface -- HLS.js player + LIVE/offline badge.

    `live`/`master_url` are the caller's own initial server-side read
    (`blueprints/live_stream.py`'s own `GET {STREAMING_URL}/live/<community_id>`
    proxy call) so the first paint never flashes "offline" while the first
    client-side poll is still in flight. The embedded script then polls this
    service's own `/overlay/<community>/live/status` endpoint every 10s and
    swaps the player source / badge state as svc-streaming pipelines start
    and stop -- same "server holds the internal call, browser polls a local
    JSON endpoint" shape `render_music`'s queue polling already established
    for hub-api.
    """
    safe_community = html.escape(community)
    theme_style = _theme_style(
        primary_color=primary_color, secondary_color=secondary_color, font_family=font_family
    )
    initial_url = json.dumps(master_url) if master_url else "null"
    initial_live = "true" if (live and master_url) else "false"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>svc-presentation -- live -- {safe_community}</title>
{theme_style}
<style>
{_BASE_STYLE}
    #live-wrap {{ position: fixed; inset: 0; background: #000; }}
    video {{ width: 100%; height: 100%; object-fit: contain; }}
    #badge {{ position: fixed; top: 16px; left: 16px; padding: 6px 14px; border-radius: 20px;
      font-size: 13px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; }}
    #badge.live {{ color: #fff; background: #e0245e; }}
    #badge.offline {{ color: #aaa; background: rgba(0,0,0,0.6); }}
    #offline-message {{ position: fixed; inset: 0; display: flex; align-items: center;
      justify-content: center; color: #888; font-size: 18px; }}
</style>
</head>
<body data-community="{safe_community}" data-surface="live">
  <div id="live-wrap">
    <video id="player" autoplay muted playsinline class="hidden"></video>
    <div id="offline-message">stream offline</div>
  </div>
  <div id="badge" class="offline">offline</div>
  <script src="{_HLS_JS_SRC}"></script>
  <script>
    const community = {json.dumps(community)};
    const POLL_INTERVAL_MS = 10000;
    let hls = null;
    let currentUrl = null;

    function setLive(isLive) {{
      const badge = document.getElementById('badge');
      const video = document.getElementById('player');
      const offline = document.getElementById('offline-message');
      badge.textContent = isLive ? 'LIVE' : 'offline';
      badge.classList.toggle('live', isLive);
      badge.classList.toggle('offline', !isLive);
      video.classList.toggle('hidden', !isLive);
      offline.classList.toggle('hidden', isLive);
    }}

    function attach(url) {{
      if (url === currentUrl) return;
      currentUrl = url;
      const video = document.getElementById('player');
      if (hls) {{ hls.destroy(); hls = null; }}
      if (!url) {{ video.removeAttribute('src'); return; }}
      if (window.Hls && Hls.isSupported()) {{
        hls = new Hls();
        hls.loadSource(url);
        hls.attachMedia(video);
      }} else if (video.canPlayType('application/vnd.apple.mpegurl')) {{
        video.src = url;
      }}
    }}

    async function poll() {{
      try {{
        const resp = await fetch(`/overlay/${{community}}/live/status`);
        if (!resp.ok) {{ setLive(false); attach(null); return; }}
        const data = await resp.json();
        const pipelines = data.pipelines || [];
        const first = pipelines[0];
        const isLive = !!(data.live && first);
        setLive(isLive);
        attach(isLive ? first.url : null);
      }} catch (err) {{
        console.error('live status poll failed', err);
        setLive(false);
        attach(null);
      }}
    }}

    setLive({initial_live});
    attach({initial_url});
    poll();
    setInterval(poll, POLL_INTERVAL_MS);
  </script>
</body>
</html>"""


RENDERERS: dict[str, Any] = {
    "full_screen": render_full_screen,
    "media": render_media,
    "crawler": render_crawler,
}
