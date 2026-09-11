import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { communityApi } from '../../../services/api';
import CommunityReputationPanel from '../CommunityReputationPanel';

vi.mock('../../../services/api', () => ({
  communityApi: {
    getMyReputation: vi.fn(),
    getReputationLeaderboard: vi.fn(),
  },
}));

function meResponse(data) {
  return { data: { status: 'success', data, meta: { version: 1 } } };
}

function leaderboardResponse(entries) {
  return { data: { status: 'success', data: { entries }, meta: { version: 1 } } };
}

describe('CommunityReputationPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders both score blocks and their tier chips once loaded', async () => {
    communityApi.getMyReputation.mockResolvedValueOnce(
      meResponse({
        community_score: 720,
        community_tier: 'Respected',
        global_score: 600,
        global_tier: 'Trusted',
        total_events: 12,
        last_event_at: '2026-09-01T00:00:00+00:00',
      })
    );
    communityApi.getReputationLeaderboard.mockResolvedValueOnce(leaderboardResponse([]));

    render(<CommunityReputationPanel communityId={4} />);

    await waitFor(() => {
      expect(screen.getByTestId('reputation-community-score')).toBeInTheDocument();
    });
    expect(screen.getByText('720')).toBeInTheDocument();
    expect(screen.getByText('600')).toBeInTheDocument();
    expect(screen.getByTestId('reputation-community-score-tier-chip')).toHaveTextContent(
      'Respected'
    );
    expect(screen.getByTestId('reputation-global-score-tier-chip')).toHaveTextContent('Trusted');
    expect(communityApi.getMyReputation).toHaveBeenCalledWith(4);
    expect(communityApi.getReputationLeaderboard).toHaveBeenCalledWith(4, { limit: 10 });
  });

  it('renders leaderboard entries with display name, score, and tier chip', async () => {
    communityApi.getMyReputation.mockResolvedValueOnce(
      meResponse({
        community_score: 600,
        community_tier: 'Trusted',
        global_score: 600,
        global_tier: 'Trusted',
        total_events: 0,
        last_event_at: null,
      })
    );
    communityApi.getReputationLeaderboard.mockResolvedValueOnce(
      leaderboardResponse([
        { display_name: 'alice', score: 840, tier: 'Legend' },
        { display_name: 'bob', score: 500, tier: 'Trusted' },
      ])
    );

    render(<CommunityReputationPanel communityId={4} />);

    await waitFor(() => {
      expect(screen.getAllByTestId('reputation-leaderboard-entry')).toHaveLength(2);
    });
    expect(screen.getByText('alice')).toBeInTheDocument();
    expect(screen.getByText('840')).toBeInTheDocument();
    // No PII beyond display name -- no user id / platform id ever rendered.
    expect(screen.queryByText(/user_id/i)).not.toBeInTheDocument();
  });

  it('shows the empty state when the leaderboard has no entries', async () => {
    communityApi.getMyReputation.mockResolvedValueOnce(
      meResponse({
        community_score: 600,
        community_tier: 'Trusted',
        global_score: 600,
        global_tier: 'Trusted',
        total_events: 0,
        last_event_at: null,
      })
    );
    communityApi.getReputationLeaderboard.mockResolvedValueOnce(leaderboardResponse([]));

    render(<CommunityReputationPanel communityId={4} />);

    await waitFor(() => {
      expect(screen.getByTestId('reputation-leaderboard-empty')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('reputation-leaderboard-list')).not.toBeInTheDocument();
  });

  it('shows a forbidden state on a 403 response, not the generic error', async () => {
    const forbiddenError = { response: { status: 403 } };
    communityApi.getMyReputation.mockRejectedValueOnce(forbiddenError);
    communityApi.getReputationLeaderboard.mockRejectedValueOnce(forbiddenError);

    render(<CommunityReputationPanel communityId={4} />);

    await waitFor(() => {
      expect(screen.getByTestId('reputation-forbidden')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('reputation-error')).not.toBeInTheDocument();
  });

  it('shows the generic error state on a non-403 failure', async () => {
    const serverError = { response: { status: 500 } };
    communityApi.getMyReputation.mockRejectedValueOnce(serverError);
    communityApi.getReputationLeaderboard.mockRejectedValueOnce(serverError);

    render(<CommunityReputationPanel communityId={4} />);

    await waitFor(() => {
      expect(screen.getByTestId('reputation-error')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('reputation-forbidden')).not.toBeInTheDocument();
  });
});
