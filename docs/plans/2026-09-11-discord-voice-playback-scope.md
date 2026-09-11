# Discord Voice Playback -- Server-Side Scope

Status: **DESIGN/SIZING ONLY -- not implementation.** Scopes whether/how to add server-side
playback into a **designated Discord voice channel** (`!sr set discord #music`) as an
alternative sink to today's client-side OBS overlay. Extends
`docs/plans/2026-08-31-music-station-design.md` (queue model; §8.4's explicit "client-side,
not server-side" decision -- **this doc scopes reversing that decision for the Discord-voice
case only**, not a repeal of §8.4 for the overlay path). Every claim cites the real file it's
grounded in.

**Headline finding**: the PM's shortcut -- "if a Discord voice channel is set we can just
disable Spotify" -- is directionally right but incomplete. Spotify has **no raw-audio API at
all** (§2), so it was never a server-playback candidate regardless of the voice decision.
The real gate is **YouTube**, whose only server-extractable stream comes from `yt-dlp`-class
scraping -- zero precedent in this repo (grep clean, confirmed) and ToS-risky to ship (§2).
SoundCloud is the one source already both ToS-clean *and* server-fetchable today
(`soundcloud_provider.py:338` `_get_stream_url` -- real OAuth2 stream URLs, no scraping).

---

## 1. Options

| # | Option | Deps (origin check) | Effort (person-days) | Verdict |
|---|---|---|---|---|
| a | Voice client **inside existing** svc-ingest gateway (`discord_gateway.py`) -- py-cord `VoiceClient` + PyNaCl + ffmpeg subprocess | py-cord (Pycord Dev, MIT, int'l) · PyNaCl (Python Cryptographic Authority, Apache/BSD) · ffmpeg (Xiph/FFmpeg project). **No PRC-origin, no unmaintained flags.** | **8-12** | **Recommended for P1** -- only option avoiding a second Discord gateway session (§3) |
| b | Separate Python `svc-voice` container, subscribed to queue events | Same deps as (a) + new IPC to forward `VOICE_SERVER_UPDATE` | 15-20 | More isolation, pays the dual-gateway-session tax (§3) for no proven benefit yet |
| c | Rust `svc-voice` -- serenity + songbird | serenity-rs org (MIT, int'l), songbird (same org). **No PRC-origin.** Standards-aligned (Data Plane tier, `critical-rules.md`) | 25-35 | Right **target-state**, not right MVP -- greenfield Rust audio stack, no repo precedent |
| d | Off-the-shelf Lavalink node | Kotlin/JVM, lavalink-devs (Apache 2.0, int'l). **No PRC-origin**, but a new JVM runtime -- no precedent anywhere in this stack (Python/Rust/Go/Node only) | 6-10 (integration only) | Fastest to stand up; doesn't need its own gateway session -- but a 5th language runtime for one feature is a hard sell |

**Recommendation (as scoped)**: (a) now, (c) later -- mirrors `svc-streaming`'s original
precedent (`docs/plans/2026-08-31-svc-streaming-design.md` §7). Embedding in svc-ingest is the
only option that reuses the already-solved single-gateway-connection problem (`socket_lease.py`).

**Decision (product owner, 2026-09-11, supersedes the recommendation above)**: all streaming
to / inside / from the Waddles ecosystem lives in **`svc-streaming`, written in Rust** -- so
Discord voice playback is option **(c)** (`serenity` + `songbird`) implemented as an audio *sink*
of svc-streaming, not a separate `svc-voice` and not embedded in the Python gateway. The
gateway-coupling constraint in §3 still applies: svc-streaming needs the voice session on the
same Discord gateway session that identified, so the design must either (i) hand svc-streaming
its own gateway session for voice (second session on the same bot token, per-guild lease) or
(ii) forward `VOICE_STATE_UPDATE`/`VOICE_SERVER_UPDATE` from svc-ingest's lease-holder over the
Valkey stream -- open question 3 below becomes the first design decision of that chunk. P0
(manual client-side audio share) remains the demo-week route.

---

## 2. Audio source legality / ToS

| Source | Server-side mechanism | ToS posture | Ship in product? |
|---|---|---|---|
| YouTube | `yt-dlp`-class stream extraction (URL scraping; no official API for raw audio) | Violates YouTube ToS (anti-circumvention/scraping clause); takedown/IP-ban risk | **Demo-only, never ship** |
| Spotify | None exists -- Web API is metadata/control only; Web Playback SDK is DRM'd, browser-only, raw stream never leaves Spotify's player | N/A -- not a server-side candidate under any option | **Cannot ship server-side, period** (technical wall, not a policy choice) |
| SoundCloud | Official OAuth2 `stream_url` (already implemented, `soundcloud_provider.py:338-354`) | Within ToS -- official API | **Safe to ship** |
| User-uploaded / royalty-free / internet radio (Icecast/Shoutcast URL) | Direct HTTP(S) stream fetch, no scraping | Clean -- streamer supplies their own licensed source | **Safe to ship** |

**Net**: P1 ships SoundCloud + radio/uploaded-URL only. YouTube-via-voice stays demo-only
until a licensed alternative is decided (open question 1).

---

## 3. Infra

| Concern | Finding |
|---|---|
| **Gateway coupling (blocking)** | Discord requires `VOICE_STATE_UPDATE`/`VOICE_SERVER_UPDATE` on the **same gateway session** that IDENTIFY'd. Today that's one platform-wide `discord.Bot` connection, lease-guarded to one svc-ingest replica (`socket_lease.py:1-30`, `PLATFORM_COMMUNITY` sentinel). Option (a) inherits this for free; (b)/(c)/(d) need a second full gateway session on the same token, or a new event-forward channel from the lease-holder -- neither exists in `waddle_transports` today |
| **guild<->community mapping (blocking)** | `discord_gateway.py:175-179` -- `guild_id` is captured but explicitly "carried for FUTURE use only... no real guild->community mapping lookup table exists yet." `!sr set discord #music` cannot resolve to a `community_id` without this. (Note: #311's `community_servers`-based resolver closes this gap for chat commands; voice needs the same lookup from the gateway side.) |
| **UDP egress** | Voice is bot-initiated (egress) UDP to a Discord voice-region IP resolved at session start -- **not** the inbound-SFU problem `svc-rtc`/`svc-streaming` §7.1 already flagged (no hostPort/hostNetwork/NET_ADMIN needed, standard NAT/conntrack). Discord publishes **no stable CIDR list** for voice endpoints, so the CiliumNetworkPolicy egress-allowlist pattern `devops-kubernetes.md` mandates doesn't cleanly fit -- likely a documented broad UDP-egress exception, not a tight allowlist |
| **Current NetworkPolicy gap** | `k8s/helm/waddlebot/templates/network-policies.yaml` today is ingress-only, plain K8s `NetworkPolicy` (not yet `CiliumNetworkPolicy` per `devops-kubernetes.md`) -- egress policy for voice is greenfield work regardless of language choice |
| **CPU** | Opus 48kHz stereo *encode* is cheap; the real cost is *decoding/transcoding* the source into Opus (ffmpeg). Rough: ~0.15-0.3 vCPU per **concurrent active voice session**, not amortized -- sizing scales with `communities-with-voice-enabled x concurrency`, not svc-ingest's shared budget (`values.yaml:423-433`: 500m/2000m for the whole platform gateway pod today) |
| **Bot token / intents** | Token resolution reusable as-is (`resolve_secret`/`token_ref`, `discord_gateway.py:110-125`). New: `intents.voice_states = True` (not privileged, no portal toggle) alongside today's `message_content`/`guilds` (`discord_gateway.py:130-132`) |
| **One session per guild** | Discord-enforced hard limit: exactly one bot voice connection per guild; independent across guilds. Matches "one designated channel per community" naturally, *if* guild==community 1:1 holds |
| **Reconnect/lease** | Option (a) rides the existing `ReceiverSupervisor` restart-on-exit + `LeasedReceiver` renew/lease-loss handling (`socket_lease.py:149-403`) for free. Options (b)/(c)/(d) need their **own** lease scoped **per-guild** (not `PLATFORM_COMMUNITY`), since voice concurrency is per-guild, not one shared socket |

---

## 4. Integration

| Aspect | Design |
|---|---|
| **Queue consumption** | Poll hub-api's internal queue endpoint (`GET /api/v1/internal/music/queue?community_id=`, `X-Service-Key`) exactly as `svc_presentation/services/queue_reader.py` does after the 2026-09-11 re-point -- the Postgres `music_station_queue` is the single source of truth; no Valkey mirror, no dependency on the parent doc's unresolved §9.2 shared-queue-isolation decision |
| **New capability, not parity** | Client-side playback reports track-end via the overlay's `advance` call; server-side voice playback can report real track-end authoritatively (no browser required) -- it becomes the preferred caller of `POST /api/v1/internal/music/queue/advance` when voice is the sink |
| **Config storage** | `community_music_settings` (`0012_schema_drift_columns.py:328-340`) fields confirmed: `community_id, default_provider, autoplay_enabled, require_dj_approval, volume_limit, allowed_genres, blocked_artists, is_active` -- **no discord/voice field exists**. Recommend reusing `community_music_providers` (`community_id, provider_name, is_connected, is_active, config` TEXT) with `provider_name="discord"`, `config={"voice_channel_id": ...}` -- matches the existing per-provider config shape, no new migration |
| **"Spotify disabled when voice set"** | Enforce at request-time in ingest/process (mirrors `music_policy.requests_category_restricted`'s existing gate pattern, parent doc §7): reject/route around `!sr` Spotify requests when Discord-voice config is active for a community -- moot per §2 (Spotify was never a server-playback candidate), but still needed so a Spotify request doesn't silently no-op |
| **Overlay when voice is the sink** | No player embed -- same precedent already live for SoundCloud (`EMBEDDABLE_PROVIDERS = {youtube, spotify}`, `queue_reader.py:41-44`; SoundCloud already renders metadata-only). Add a "Playing in Discord: #channel" badge; playback control stays in chat commands, not the browser source |

---

## 5. Phased plan

| Phase | Scope | Acceptance criteria | Tests | OTel |
|---|---|---|---|---|
| **P0** | Manual bridge, zero new code: streamer routes OBS/desktop audio into Discord's own "Share App Audio" (or a virtual-cable) -- document as a runbook | Runbook published; one manual walkthrough confirms audio audible in a test voice channel | None (no server code) | None |
| **P1** | svc-voice MVP: embed in svc-ingest gateway (option a), SoundCloud + radio/upload sources only, guild<->community lookup via `community_servers`, `community_music_providers` discord row | `!sr set discord #channel` joins the right guild's channel; SoundCloud track plays end-to-end; disconnects cleanly on empty channel/community deactivation | Unit: guild-map resolution, voice-join/leave state machine (mock py-cord). Integration: real SoundCloud stream URL -> ffmpeg -> mock voice socket | `voice.session.active` (gauge, per guild), `voice.track.duration_ms` (histogram), `voice.connect.latency_ms` (histogram), `voice.session.errors` (counter, reason-tagged) |
| **P2** | Rust `svc-voice` (serenity+songbird), multi-guild concurrency, all ToS-safe sources, playback-progress write-back, moderation parity (`music.queue:moderate` skip/pause) | Load test: N concurrent guild sessions within sized CPU budget (§3); moderator skip reflected in <1s | Rust `rstest` table-driven voice-state-machine tests; load test harness | Same signals as P1 + `voice.moderation.action` (counter) |

---

## 6. Open questions (<=5)

1. **YouTube in voice**: ship without it (SoundCloud/radio only) indefinitely, or pursue a licensed YouTube path (paid API) later?
2. **guild<->community mapping**: is guild==community always 1:1 today, or can one community span multiple guilds (breaks "one designated channel")? (#311 already allows one channel -> many communities; voice needs the inverse guarantee.)
3. Is a **second Discord gateway session** (option b/c/d) ever acceptable, or is "must share svc-ingest's existing lease" a hard constraint going forward?
4. **CPU budget owner**: does Discord-voice concurrency get its own node-pool/tier (like `svc-streaming`'s transcode-heavy proposal), or share svc-ingest's pod budget?
5. Should the **UDP-egress allowlist gap** (no stable Discord voice CIDR) block beta rollout, or ship with a documented broad-egress exception first?
