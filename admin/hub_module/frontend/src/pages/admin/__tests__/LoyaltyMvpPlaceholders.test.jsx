/**
 * Tests for the loyalty giveaways/games/gear admin pages (gh-317) — these
 * routes stay mounted for nav but render an MVP "coming after launch"
 * empty state instead of hitting any API, since the core-currency schema
 * has no tables backing them.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import LoyaltyGiveaways from '../LoyaltyGiveaways';
import LoyaltyGames from '../LoyaltyGames';
import LoyaltyGear from '../LoyaltyGear';

describe('Loyalty MVP-excluded placeholder pages', () => {
  it('LoyaltyGiveaways renders an empty state with no API calls', () => {
    render(<LoyaltyGiveaways />);
    expect(screen.getByTestId('loyalty-giveaways-empty')).toHaveTextContent(
      'Coming after the MVP launch',
    );
  });

  it('LoyaltyGames renders an empty state with no API calls', () => {
    render(<LoyaltyGames />);
    expect(screen.getByTestId('loyalty-games-empty')).toHaveTextContent(
      'Coming after the MVP launch',
    );
  });

  it('LoyaltyGear renders an empty state with no API calls', () => {
    render(<LoyaltyGear />);
    expect(screen.getByTestId('loyalty-gear-empty')).toHaveTextContent(
      'Coming after the MVP launch',
    );
  });
});
