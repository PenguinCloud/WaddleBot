/**
 * Tests for the MVP core-currency loyalty settings page (gh-317) — load,
 * bind to `ConfigDTO` fields, client-side validation, save, error toast.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import LoyaltySettings from '../LoyaltySettings';
import { adminApi } from '../../../services/api';

vi.mock('../../../services/api', () => ({
  adminApi: {
    getLoyaltyConfig: vi.fn(),
    updateLoyaltyConfig: vi.fn(),
  },
}));

const BASE_CONFIG = {
  community_id: 42,
  currency_name: 'Points',
  currency_symbol: '$',
  earn_chat_points: 1,
  earn_chat_cooldown_s: 30,
  earn_watch_points_per_min: 2,
  earn_watch_enabled: false,
  max_balance: null,
  enabled: true,
  updated_at: null,
};

function mount(communityId = '42') {
  return render(
    <MemoryRouter initialEntries={[`/admin/${communityId}/loyalty`]}>
      <Routes>
        <Route path="/admin/:communityId/loyalty" element={<LoyaltySettings />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('LoyaltySettings', () => {
  it('loads and binds config fields from the envelope response', async () => {
    adminApi.getLoyaltyConfig.mockResolvedValue({ data: { data: BASE_CONFIG } });

    mount();

    expect(await screen.findByTestId('loyalty-currency-name')).toHaveValue('Points');
    expect(screen.getByTestId('loyalty-currency-symbol')).toHaveValue('$');
    expect(screen.getByTestId('loyalty-earn-chat-points')).toHaveValue(1);
    expect(screen.getByTestId('loyalty-earn-chat-cooldown')).toHaveValue(30);
    expect(screen.getByTestId('loyalty-enabled')).toBeChecked();
    expect(screen.getByTestId('loyalty-earn-watch-enabled')).not.toBeChecked();
    expect(adminApi.getLoyaltyConfig).toHaveBeenCalledWith('42');
  });

  it('shows an error state if the load fails', async () => {
    adminApi.getLoyaltyConfig.mockRejectedValue({ response: { status: 500 } });

    mount();

    expect(await screen.findByText('Failed to load configuration')).toBeInTheDocument();
  });

  it('reveals the watch-points input only when watch earning is enabled', async () => {
    adminApi.getLoyaltyConfig.mockResolvedValue({ data: { data: BASE_CONFIG } });

    mount();
    await screen.findByTestId('loyalty-currency-name');

    expect(screen.queryByTestId('loyalty-earn-watch-points')).not.toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByTestId('loyalty-earn-watch-enabled'));
    });

    expect(screen.getByTestId('loyalty-earn-watch-points')).toBeInTheDocument();
  });

  it('blocks save with a validation toast when currency name is blank', async () => {
    adminApi.getLoyaltyConfig.mockResolvedValue({ data: { data: BASE_CONFIG } });

    mount();
    const nameInput = await screen.findByTestId('loyalty-currency-name');

    await act(async () => {
      fireEvent.change(nameInput, { target: { value: '   ' } });
      fireEvent.click(screen.getByTestId('loyalty-save'));
    });

    expect(await screen.findByTestId('loyalty-settings-feedback')).toHaveTextContent(
      'Currency name must not be blank',
    );
    expect(adminApi.updateLoyaltyConfig).not.toHaveBeenCalled();
  });

  it('blocks save with a validation toast on a negative max balance', async () => {
    adminApi.getLoyaltyConfig.mockResolvedValue({ data: { data: BASE_CONFIG } });

    mount();
    const maxBalanceInput = await screen.findByTestId('loyalty-max-balance');

    await act(async () => {
      fireEvent.change(maxBalanceInput, { target: { value: '-5' } });
      fireEvent.click(screen.getByTestId('loyalty-save'));
    });

    expect(await screen.findByTestId('loyalty-settings-feedback')).toHaveTextContent(
      'Max balance must be a whole number >= 0',
    );
    expect(adminApi.updateLoyaltyConfig).not.toHaveBeenCalled();
  });

  it('saves the edited config and shows a success toast', async () => {
    adminApi.getLoyaltyConfig.mockResolvedValue({ data: { data: BASE_CONFIG } });
    adminApi.updateLoyaltyConfig.mockResolvedValue({
      data: { data: { ...BASE_CONFIG, currency_name: 'Waddles' } },
    });

    mount();
    const nameInput = await screen.findByTestId('loyalty-currency-name');

    await act(async () => {
      fireEvent.change(nameInput, { target: { value: 'Waddles' } });
      fireEvent.click(screen.getByTestId('loyalty-save'));
    });

    await waitFor(() =>
      expect(adminApi.updateLoyaltyConfig).toHaveBeenCalledWith(
        '42',
        expect.objectContaining({ currency_name: 'Waddles', max_balance: null }),
      ),
    );
    expect(await screen.findByTestId('loyalty-settings-feedback')).toHaveTextContent(
      'saved successfully',
    );
  });

  it('shows the server error message on a failed save', async () => {
    adminApi.getLoyaltyConfig.mockResolvedValue({ data: { data: BASE_CONFIG } });
    adminApi.updateLoyaltyConfig.mockRejectedValue({
      response: { status: 402, data: { error: { message: 'Community loyalty requires a Professional plan or higher' } } },
    });

    mount();
    await screen.findByTestId('loyalty-currency-name');

    await act(async () => {
      fireEvent.click(screen.getByTestId('loyalty-save'));
    });

    expect(await screen.findByTestId('loyalty-settings-feedback')).toHaveTextContent(
      'Community loyalty requires a Professional plan or higher',
    );
  });
});
