/**
 * Tests for the public, unauthenticated song-queue page (`/c/:communityId/music/queue`)
 * linked from chat via `!sq`: rendering + ETA formatting, moderator-only
 * Remove controls, 404/429 handling, and visibility-gated polling.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import MusicQueuePage from '../MusicQueuePage';
import { publicApi, adminApi } from '../../../services/api';
import * as AuthContext from '../../../contexts/AuthContext';

vi.mock('../../../services/api', () => ({
  publicApi: { getMusicQueue: vi.fn() },
  adminApi: { removeMusicQueueItem: vi.fn() },
}));

function mockAuth(overrides = {}) {
  vi.spyOn(AuthContext, 'useAuth').mockReturnValue({
    isAuthenticated: false,
    hasRole: () => false,
    isCommunityAdmin: () => false,
    ...overrides,
  });
}

function samplePayload(overrides = {}) {
  return {
    community: { id: 42, name: 'Test Community' },
    now_playing: {
      id: 1,
      position: 1,
      status: 'playing',
      title: 'Now Playing Song',
      artist: 'Now Artist',
      duration_ms: 200000,
      artwork_url: null,
      provider: 'youtube',
      external_id: 'abc',
      url: 'https://example.com/1',
      eta_seconds: 0,
      started_at: '2026-09-11T00:00:00Z',
      requested_by: { display_name: 'Requester One', platform: 'twitch' },
    },
    playback: { paused: false, paused_since: null, position_ms: 30000 },
    queue: [
      {
        id: 2,
        position: 1,
        status: 'queued',
        title: 'Up Next Song',
        artist: 'Next Artist',
        duration_ms: 185000,
        artwork_url: null,
        provider: 'spotify',
        external_id: 'def',
        url: 'https://example.com/2',
        eta_seconds: 0,
        started_at: null,
        requested_by: { display_name: 'Requester Two', platform: 'discord' },
      },
      {
        id: 3,
        position: 2,
        status: 'queued',
        title: 'Third Song',
        artist: 'Third Artist',
        duration_ms: 210000,
        artwork_url: null,
        provider: 'youtube',
        external_id: 'ghi',
        url: 'https://example.com/3',
        eta_seconds: 245,
        started_at: null,
        requested_by: null,
      },
    ],
    ...overrides,
  };
}

function mount(communityId = '42') {
  return render(
    <MemoryRouter initialEntries={[`/c/${communityId}/music/queue`]}>
      <Routes>
        <Route path="/c/:communityId/music/queue" element={<MusicQueuePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('MusicQueuePage', () => {
  it('renders now playing, queue items, requester badges, and ETA formatting', async () => {
    mockAuth();
    publicApi.getMusicQueue.mockResolvedValue({ data: { data: samplePayload() } });

    mount();

    expect(await screen.findByText('Now Playing Song')).toBeInTheDocument();
    expect(screen.getByText('Up Next Song')).toBeInTheDocument();
    expect(screen.getByText('Third Song')).toBeInTheDocument();

    // Duration m:ss
    expect(screen.getByTestId('now-playing')).toHaveTextContent('3:20');
    expect(screen.getByTestId('queue-row-2')).toHaveTextContent('3:05');
    expect(screen.getByTestId('queue-row-3')).toHaveTextContent('3:30');

    // ETA: currently playing -> "Playing now"; eta_seconds=0 -> "Next up";
    // known eta_seconds -> formatted countdown
    expect(screen.getByTestId('now-playing')).toHaveTextContent('Playing now');
    expect(screen.getByTestId('queue-row-2')).toHaveTextContent('Next up');
    expect(screen.getByTestId('queue-row-3')).toHaveTextContent('~4m 05s');

    // Requester + platform badge; null requester falls back to "automatically"
    expect(screen.getByTestId('now-playing')).toHaveTextContent('Requester One');
    expect(screen.getByTestId('now-playing')).toHaveTextContent('Twitch');
    expect(screen.getByTestId('queue-row-2')).toHaveTextContent('Requester Two');
    expect(screen.getByTestId('queue-row-3')).toHaveTextContent('Queued automatically');

    // Playback progress (m:ss / m:ss) on now-playing only, no paused badge
    // while playing; queue rows never show a progress readout.
    expect(screen.getByTestId('now-playing')).toHaveTextContent('0:30 / 3:20');
    expect(screen.queryByTestId('playback-paused-badge')).not.toBeInTheDocument();
    expect(screen.queryByTestId('queue-row-2')).not.toHaveTextContent('/');
  });

  it('shows the "⏸ Paused" badge and freezes progress at position_ms while paused', async () => {
    vi.useFakeTimers();
    mockAuth();
    publicApi.getMusicQueue.mockResolvedValue({
      data: {
        data: samplePayload({
          playback: { paused: true, paused_since: '2026-09-11T00:05:00Z', position_ms: 45000 },
        }),
      },
    });

    mount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(screen.getByTestId('now-playing')).toHaveTextContent('⏸ Paused');
    expect(screen.getByTestId('now-playing')).toHaveTextContent('0:45 / 3:20');

    // Frozen: even after several seconds of wall-clock time, the paused
    // position never advances (no local ticker runs while paused).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(screen.getByTestId('now-playing')).toHaveTextContent('0:45 / 3:20');
  });

  it('advances the progress readout locally between polls while playing', async () => {
    vi.useFakeTimers();
    mockAuth();
    publicApi.getMusicQueue.mockResolvedValue({ data: { data: samplePayload() } });

    mount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByTestId('now-playing')).toHaveTextContent('0:30 / 3:20');

    // 3s of local wall-clock ticking, no new poll response yet -> position
    // projects forward from the last synced 30000ms.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(screen.getByTestId('now-playing')).toHaveTextContent('0:33 / 3:20');
  });

  it('omits the progress readout when playback is absent from the payload', async () => {
    mockAuth();
    publicApi.getMusicQueue.mockResolvedValue({
      data: { data: samplePayload({ playback: undefined }) },
    });

    mount();
    await screen.findByText('Now Playing Song');

    expect(screen.queryByTestId('playback-progress')).not.toBeInTheDocument();
    expect(screen.queryByTestId('playback-paused-badge')).not.toBeInTheDocument();
  });

  it('shows the empty state when nothing is queued', async () => {
    mockAuth();
    publicApi.getMusicQueue.mockResolvedValue({
      data: { data: { community: { id: 42, name: 'Empty Co' }, now_playing: null, queue: [] } },
    });

    mount();

    expect(await screen.findByTestId('empty-queue')).toHaveTextContent('!sr <song>');
  });

  it('shows the not-found state on a 404', async () => {
    mockAuth();
    publicApi.getMusicQueue.mockRejectedValue({ response: { status: 404 } });

    mount();

    expect(await screen.findByTestId('queue-not-found')).toBeInTheDocument();
  });

  it('hides the Remove button for anonymous viewers', async () => {
    mockAuth({ isAuthenticated: false });
    publicApi.getMusicQueue.mockResolvedValue({ data: { data: samplePayload() } });

    mount();
    await screen.findByText('Now Playing Song');

    expect(screen.queryByTestId('remove-1')).not.toBeInTheDocument();
    expect(screen.queryByTestId('remove-2')).not.toBeInTheDocument();
    expect(screen.queryByTestId('remove-3')).not.toBeInTheDocument();
  });

  it('shows Remove for a logged-in community moderator, calls DELETE, and removes the row optimistically', async () => {
    mockAuth({ isAuthenticated: true, hasRole: () => false, isCommunityAdmin: () => true });
    publicApi.getMusicQueue.mockResolvedValue({ data: { data: samplePayload() } });
    adminApi.removeMusicQueueItem.mockResolvedValue({ data: { success: true } });

    mount();
    await screen.findByText('Up Next Song');

    await act(async () => {
      screen.getByTestId('remove-2').click();
    });

    expect(adminApi.removeMusicQueueItem).toHaveBeenCalledWith('42', 2);
    await waitFor(() => expect(screen.queryByText('Up Next Song')).not.toBeInTheDocument());
    expect(await screen.findByTestId('queue-feedback')).toHaveTextContent('Removed "Up Next Song"');
  });

  it('reverts the optimistic removal and shows an error on a non-403 failure', async () => {
    mockAuth({ isAuthenticated: true, hasRole: () => false, isCommunityAdmin: () => true });
    publicApi.getMusicQueue.mockResolvedValue({ data: { data: samplePayload() } });
    adminApi.removeMusicQueueItem.mockRejectedValue({ response: { status: 500 } });

    mount();
    await screen.findByText('Up Next Song');

    await act(async () => {
      screen.getByTestId('remove-2').click();
    });

    await waitFor(() => expect(screen.getByTestId('queue-feedback')).toHaveTextContent('Failed to remove song'));
    expect(screen.getByText('Up Next Song')).toBeInTheDocument();
  });

  it('hides moderation controls after a 403 and shows the permission message', async () => {
    mockAuth({ isAuthenticated: true, hasRole: () => false, isCommunityAdmin: () => true });
    publicApi.getMusicQueue.mockResolvedValue({ data: { data: samplePayload() } });
    adminApi.removeMusicQueueItem.mockRejectedValue({ response: { status: 403 } });

    mount();
    await screen.findByText('Up Next Song');

    await act(async () => {
      screen.getByTestId('remove-2').click();
    });

    await waitFor(() =>
      expect(screen.getByTestId('queue-feedback')).toHaveTextContent("don't have permission"),
    );
    expect(screen.queryByTestId('remove-3')).not.toBeInTheDocument();
  });

  it('backs off to 15s polling after a 429 and resumes normal cadence after recovering', async () => {
    vi.useFakeTimers();
    mockAuth();
    publicApi.getMusicQueue
      .mockResolvedValueOnce({ data: { data: samplePayload() } })
      .mockRejectedValueOnce({ response: { status: 429 } })
      .mockResolvedValue({ data: { data: samplePayload() } });

    mount();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(publicApi.getMusicQueue).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(publicApi.getMusicQueue).toHaveBeenCalledTimes(2); // this call 429s

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000); // only 5s of the 15s backoff elapsed
    });
    expect(publicApi.getMusicQueue).toHaveBeenCalledTimes(2);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000); // remaining 10s -> 15s total
    });
    expect(publicApi.getMusicQueue).toHaveBeenCalledTimes(3);
  });

  it('pauses polling while the tab is hidden and resumes on visibilitychange', async () => {
    vi.useFakeTimers();
    mockAuth();
    publicApi.getMusicQueue.mockResolvedValue({ data: { data: samplePayload() } });

    mount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(publicApi.getMusicQueue).toHaveBeenCalledTimes(1);

    vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(20000);
    });
    expect(publicApi.getMusicQueue).toHaveBeenCalledTimes(1); // still paused

    vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(publicApi.getMusicQueue).toHaveBeenCalledTimes(2);
  });
});
