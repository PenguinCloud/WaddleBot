import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  MusicalNoteIcon,
  ClockIcon,
  UserIcon,
  TrashIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { publicApi, adminApi } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import { getPlatformIcon, getPlatformColor, getPlatformLabel } from '../../utils/platformConfig';

// Normal poll cadence; widened to RATE_LIMIT_BACKOFF_MS whenever the server
// returns 429 so the page keeps working without hammering hub-api.
const POLL_INTERVAL_MS = 5000;
const RATE_LIMIT_BACKOFF_MS = 15000;

/** Formats a millisecond track duration as `m:ss`, mirroring the admin dashboard's convention. */
function formatDurationMs(durationMs) {
  if (!durationMs || durationMs <= 0) return '0:00';
  const totalSeconds = Math.floor(durationMs / 1000);
  const mins = Math.floor(totalSeconds / 60);
  const secs = totalSeconds % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/** Formats a second-based ETA as a short "~Xm Ys" / "~Ys" countdown string. */
function formatEtaSeconds(etaSeconds) {
  const mins = Math.floor(etaSeconds / 60);
  const secs = etaSeconds % 60;
  if (mins <= 0) return `~${secs}s`;
  return `~${mins}m ${secs.toString().padStart(2, '0')}s`;
}

/**
 * Resolves the ETA label for one queue item: a "playing now" badge for the
 * current track, "Next up" when eta_seconds is exactly 0 (or unset on the
 * position-1 slot), a formatted countdown when known, otherwise a dash.
 */
function resolveEtaLabel(item) {
  if (item.status === 'playing') return 'Playing now';
  const { eta_seconds: etaSeconds, position } = item;
  if (etaSeconds === 0) return 'Next up';
  if ((etaSeconds === null || etaSeconds === undefined) && position === 1) return 'Next up';
  if (etaSeconds === null || etaSeconds === undefined) return '--';
  return formatEtaSeconds(etaSeconds);
}

/** Renders the requester's display name with a small platform badge, or a muted fallback for autoplay. */
function RequesterBadge({ requestedBy }) {
  if (!requestedBy) {
    return <span className="text-xs text-navy-500 italic">Queued automatically</span>;
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-navy-400">
      <UserIcon className="w-3.5 h-3.5 flex-shrink-0" />
      <span className="truncate">{requestedBy.display_name}</span>
      <span className={`px-1.5 py-0.5 rounded border whitespace-nowrap ${getPlatformColor(requestedBy.platform)}`}>
        {getPlatformIcon(requestedBy.platform)} {getPlatformLabel(requestedBy.platform)}
      </span>
    </span>
  );
}

/** One queue row -- title/artist/requester/length/ETA, with an optional moderator Remove control. */
function QueueItemCard({ item, canModerate, onRemove, removing, testId }) {
  return (
    <div
      data-testid={testId}
      className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-4 bg-navy-900 rounded-lg border border-navy-700"
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          {item.position != null && (
            <span className="text-xs font-mono text-navy-500 flex-shrink-0">#{item.position}</span>
          )}
          <p className="font-medium text-sky-100 truncate">{item.title}</p>
        </div>
        <p className="text-sm text-navy-400 truncate">{item.artist}</p>
        <div className="mt-1">
          <RequesterBadge requestedBy={item.requested_by} />
        </div>
      </div>
      <div className="flex items-center gap-4 flex-shrink-0 self-end sm:self-auto">
        <div className="text-right">
          <p className="text-sm text-sky-200 flex items-center gap-1 justify-end">
            <ClockIcon className="w-4 h-4 text-navy-500" />
            {formatDurationMs(item.duration_ms)}
          </p>
          <p className="text-xs text-gold-400">{resolveEtaLabel(item)}</p>
        </div>
        {canModerate && (
          <button
            type="button"
            data-testid={`remove-${item.id}`}
            onClick={() => onRemove(item)}
            disabled={removing}
            aria-label={`Remove ${item.title} from the queue`}
            className="p-2 rounded-lg text-red-400 hover:text-red-300 hover:bg-red-500/10 focus:ring-2 focus:ring-red-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <TrashIcon className="w-5 h-5" />
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Public, unauthenticated song-queue page linked from chat via `!sq`. Polls
 * the public music-station queue every 5s (15s after a 429, paused while the
 * tab is hidden) and, for logged-in community admins/moderators, exposes a
 * Remove control that calls the authenticated moderation endpoint.
 */
function MusicQueuePage() {
  const { communityId } = useParams();
  const { isAuthenticated, hasRole, isCommunityAdmin } = useAuth();

  const [community, setCommunity] = useState(null);
  const [nowPlaying, setNowPlaying] = useState(null);
  const [queue, setQueue] = useState([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [modAllowed, setModAllowed] = useState(true);
  const [removingId, setRemovingId] = useState(null);
  const [feedback, setFeedback] = useState(null);

  // Server is the source of truth on 403 (modAllowed flips false and hides
  // the controls); client-side this is just a UX shortcut, not an authz gate.
  const canModerate = isAuthenticated
    && modAllowed
    && (hasRole('admin') || hasRole('super_admin') || isCommunityAdmin(communityId));

  useEffect(() => {
    let cancelled = false;
    let timeoutId = null;

    async function fetchQueue() {
      try {
        const response = await publicApi.getMusicQueue(communityId);
        if (cancelled) return null;
        const payload = response.data?.data ?? {};
        setCommunity(payload.community ?? null);
        setNowPlaying(payload.now_playing ?? null);
        setQueue(payload.queue ?? []);
        setNotFound(false);
        return POLL_INTERVAL_MS;
      } catch (err) {
        if (cancelled) return null;
        const status = err.response?.status;
        console.error('[MusicQueuePage] Fetch queue failed', { communityId, status: status ?? 'network' });
        if (status === 404) {
          setNotFound(true);
          return null;
        }
        if (status === 429) {
          return RATE_LIMIT_BACKOFF_MS;
        }
        return POLL_INTERVAL_MS;
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    async function runPoll() {
      if (cancelled || document.hidden) return;
      const nextDelay = await fetchQueue();
      if (cancelled || nextDelay === null) return;
      timeoutId = setTimeout(runPoll, nextDelay);
    }

    function handleVisibilityChange() {
      if (!document.hidden && !cancelled) {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(runPoll, 0);
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange);
    // Every fetch -- including the first -- runs off a scheduled timer so
    // "paused while hidden" and the 429 backoff share one code path.
    timeoutId = setTimeout(runPoll, 0);

    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [communityId]);

  const handleRemove = useCallback(async (item) => {
    setRemovingId((current) => {
      if (current) return current;
      return item.id;
    });

    const wasNowPlaying = nowPlaying?.id === item.id;
    const prevNowPlaying = nowPlaying;
    const prevQueue = queue;
    if (wasNowPlaying) {
      setNowPlaying(null);
    } else {
      setQueue((current) => current.filter((queued) => queued.id !== item.id));
    }

    try {
      await adminApi.removeMusicQueueItem(communityId, item.id);
      console.debug('[MusicQueuePage] Remove song', { communityId, itemId: item.id });
      setFeedback({ type: 'success', message: `Removed "${item.title}" from the queue.` });
    } catch (err) {
      const status = err.response?.status;
      console.error('[MusicQueuePage] Remove song failed', { communityId, itemId: item.id, status });
      if (status === 403) {
        setModAllowed(false);
        setFeedback({ type: 'error', message: "You don't have permission to remove songs." });
      } else {
        setNowPlaying(prevNowPlaying);
        setQueue(prevQueue);
        setFeedback({ type: 'error', message: 'Failed to remove song. Please try again.' });
      }
    } finally {
      setRemovingId(null);
    }
  }, [communityId, nowPlaying, queue]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]" data-testid="queue-loading">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gold-400"></div>
      </div>
    );
  }

  if (notFound) {
    return (
      <div className="max-w-xl mx-auto px-4 py-20 text-center" data-testid="queue-not-found">
        <MusicalNoteIcon className="w-16 h-16 mx-auto text-navy-600 mb-4" />
        <h1 className="text-2xl font-bold mb-2 text-sky-100">Community Not Found</h1>
        <p className="text-navy-400">This song queue could not be found.</p>
      </div>
    );
  }

  const isEmpty = !nowPlaying && queue.length === 0;

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-sky-100 flex items-center gap-2">
          <MusicalNoteIcon className="w-7 h-7 text-gold-400" />
          {community?.name ? `${community.name} Song Queue` : 'Song Queue'}
        </h1>
        <p className="text-sm text-navy-400 mt-1">Updates automatically every few seconds.</p>
      </div>

      {feedback && (
        <div
          data-testid="queue-feedback"
          className={`rounded-lg p-4 flex items-center justify-between border ${
            feedback.type === 'success'
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
              : 'bg-red-500/10 border-red-500/30 text-red-400'
          }`}
        >
          <span>{feedback.message}</span>
          <button
            type="button"
            onClick={() => setFeedback(null)}
            aria-label="Dismiss message"
            className="hover:opacity-75 focus:ring-2 focus:ring-sky-500 rounded"
          >
            <XMarkIcon className="w-5 h-5" />
          </button>
        </div>
      )}

      {isEmpty ? (
        <div className="text-center py-16 bg-navy-800 border border-navy-700 rounded-lg" data-testid="empty-queue">
          <MusicalNoteIcon className="w-12 h-12 text-navy-600 mx-auto mb-3" />
          <p className="text-navy-400">
            Nothing queued — type <span className="text-gold-400 font-mono">!sr &lt;song&gt;</span> in chat
          </p>
        </div>
      ) : (
        <>
          {nowPlaying && (
            <div>
              <h2 className="text-sm font-semibold text-navy-400 uppercase tracking-wide mb-2">Now Playing</h2>
              <QueueItemCard
                item={nowPlaying}
                canModerate={canModerate}
                onRemove={handleRemove}
                removing={removingId === nowPlaying.id}
                testId="now-playing"
              />
            </div>
          )}

          {queue.length > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-navy-400 uppercase tracking-wide mb-2">Up Next</h2>
              <div className="space-y-2">
                {queue.map((item) => (
                  <QueueItemCard
                    key={item.id}
                    item={item}
                    canModerate={canModerate}
                    onRemove={handleRemove}
                    removing={removingId === item.id}
                    testId={`queue-row-${item.id}`}
                  />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default MusicQueuePage;
