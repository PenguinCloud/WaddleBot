/**
 * Tests for the community music admin settings page's YouTube Allowed
 * Labels control (Music Station policy) -- load, add/remove chips, client
 * limits, save (lowercased/deduped full policy body), clear, error toast.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import AdminMusicSettings from '../AdminMusicSettings';
import { adminApi } from '../../../services/api';

vi.mock('../../../services/api', () => ({
  adminApi: {
    updateModuleConfig: vi.fn(),
    getMusicStationPolicy: vi.fn(),
    updateMusicStationPolicy: vi.fn(),
  },
}));

function mount(communityId = '42') {
  return render(
    <MemoryRouter initialEntries={[`/admin/${communityId}/music/settings`]}>
      <Routes>
        <Route path="/admin/:communityId/music/settings" element={<AdminMusicSettings />} />
      </Routes>
    </MemoryRouter>,
  );
}

function type(input, value) {
  fireEvent.change(input, { target: { value } });
}

function pressEnter(input) {
  fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
}

beforeEach(() => {
  vi.clearAllMocks();
  adminApi.updateModuleConfig.mockResolvedValue({
    data: { success: true, config: { blacklist: [] } },
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('AdminMusicSettings — YouTube Allowed Labels', () => {
  it('loads and renders existing labels as chips', async () => {
    adminApi.getMusicStationPolicy.mockResolvedValue({
      data: { data: { youtube_allowed_labels: ['music', 'lofi'] } },
    });

    mount();

    expect(await screen.findByTestId('youtube-label-chip-music')).toHaveTextContent('music');
    expect(screen.getByTestId('youtube-label-chip-lofi')).toHaveTextContent('lofi');
    expect(adminApi.getMusicStationPolicy).toHaveBeenCalledWith('42');
  });

  it('adds a chip on Enter and on comma, normalizing to lowercase', async () => {
    adminApi.getMusicStationPolicy.mockResolvedValue({
      data: { data: { youtube_allowed_labels: [] } },
    });

    mount();
    await screen.findByTestId('youtube-labels-section');

    const input = screen.getByTestId('youtube-label-input');
    await act(async () => {
      type(input, 'Music');
      pressEnter(input);
    });
    expect(await screen.findByTestId('youtube-label-chip-music')).toBeInTheDocument();

    await act(async () => {
      type(input, 'lofi,');
    });
    expect(await screen.findByTestId('youtube-label-chip-lofi')).toBeInTheDocument();
  });

  it('removes a chip via its remove button', async () => {
    adminApi.getMusicStationPolicy.mockResolvedValue({
      data: { data: { youtube_allowed_labels: ['music', 'lofi'] } },
    });

    mount();
    await screen.findByTestId('youtube-label-chip-music');

    await act(async () => {
      fireEvent.click(screen.getByTestId('remove-youtube-label-music'));
    });

    expect(screen.queryByTestId('youtube-label-chip-music')).not.toBeInTheDocument();
    expect(screen.getByTestId('youtube-label-chip-lofi')).toBeInTheDocument();
  });

  it('rejects a duplicate label without adding a second chip', async () => {
    adminApi.getMusicStationPolicy.mockResolvedValue({
      data: { data: { youtube_allowed_labels: ['music'] } },
    });

    mount();
    await screen.findByTestId('youtube-label-chip-music');

    const input = screen.getByTestId('youtube-label-input');
    await act(async () => {
      type(input, 'MUSIC');
      pressEnter(input);
    });

    const section = screen.getByTestId('youtube-labels-section');
    expect(within(section).getAllByText('music')).toHaveLength(1);
  });

  it('shows inline validation at the 64-char label limit', async () => {
    adminApi.getMusicStationPolicy.mockResolvedValue({
      data: { data: { youtube_allowed_labels: [] } },
    });

    mount();
    await screen.findByTestId('youtube-labels-section');

    const input = screen.getByTestId('youtube-label-input');
    const tooLong = 'a'.repeat(65);
    await act(async () => {
      type(input, tooLong);
      pressEnter(input);
    });

    expect(await screen.findByTestId('youtube-labels-error')).toHaveTextContent(
      'Label must be 64 characters or fewer',
    );
    expect(screen.queryByTestId(`youtube-label-chip-${tooLong}`)).not.toBeInTheDocument();
  });

  it('shows inline validation at the 32-label limit', async () => {
    const existing = Array.from({ length: 32 }, (_, i) => `label${i}`);
    adminApi.getMusicStationPolicy.mockResolvedValue({
      data: { data: { youtube_allowed_labels: existing } },
    });

    mount();
    await screen.findByTestId(`youtube-label-chip-${existing[31]}`);

    const input = screen.getByTestId('youtube-label-input');
    await act(async () => {
      type(input, 'onemore');
      pressEnter(input);
    });

    expect(await screen.findByTestId('youtube-labels-error')).toHaveTextContent(
      'Maximum 32 labels allowed',
    );
    expect(screen.queryByTestId('youtube-label-chip-onemore')).not.toBeInTheDocument();
  });

  it('saves the lowercased, de-duplicated array in the full policy body', async () => {
    adminApi.getMusicStationPolicy.mockResolvedValue({
      data: { data: { songRequestsAllowed: true, youtube_allowed_labels: ['music'] } },
    });
    adminApi.updateMusicStationPolicy.mockResolvedValue({ data: { success: true } });

    mount();
    await screen.findByTestId('youtube-label-chip-music');

    const input = screen.getByTestId('youtube-label-input');
    await act(async () => {
      type(input, 'LOFI');
      pressEnter(input);
    });
    await screen.findByTestId('youtube-label-chip-lofi');

    await act(async () => {
      fireEvent.click(screen.getByTestId('youtube-labels-save'));
    });

    await waitFor(() =>
      expect(adminApi.updateMusicStationPolicy).toHaveBeenCalledWith('42', {
        songRequestsAllowed: true,
        youtube_allowed_labels: ['music', 'lofi'],
      }),
    );
    expect(await screen.findByTestId('youtube-labels-feedback')).toHaveTextContent(
      'saved successfully',
    );
  });

  it('clears all labels and sends an empty array on save', async () => {
    adminApi.getMusicStationPolicy.mockResolvedValue({
      data: { data: { youtube_allowed_labels: ['music', 'lofi'] } },
    });
    adminApi.updateMusicStationPolicy.mockResolvedValue({ data: { success: true } });

    mount();
    await screen.findByTestId('youtube-label-chip-music');

    await act(async () => {
      fireEvent.click(screen.getByTestId('youtube-labels-clear'));
    });
    expect(screen.queryByTestId('youtube-label-chip-music')).not.toBeInTheDocument();
    expect(screen.queryByTestId('youtube-label-chip-lofi')).not.toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByTestId('youtube-labels-save'));
    });

    await waitFor(() =>
      expect(adminApi.updateMusicStationPolicy).toHaveBeenCalledWith(
        '42',
        expect.objectContaining({ youtube_allowed_labels: [] }),
      ),
    );
  });

  it('shows an error toast on a 4xx save failure', async () => {
    adminApi.getMusicStationPolicy.mockResolvedValue({
      data: { data: { youtube_allowed_labels: ['music'] } },
    });
    adminApi.updateMusicStationPolicy.mockRejectedValue({
      response: { status: 400, data: { error: { message: 'Invalid label' } } },
    });

    mount();
    await screen.findByTestId('youtube-label-chip-music');

    await act(async () => {
      fireEvent.click(screen.getByTestId('youtube-labels-save'));
    });

    expect(await screen.findByTestId('youtube-labels-feedback')).toHaveTextContent('Invalid label');
  });
});
