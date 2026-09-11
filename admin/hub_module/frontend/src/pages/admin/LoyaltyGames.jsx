/**
 * Placeholder for the loyalty games admin page (gh-317). The MVP
 * core-currency schema (`services.community_loyalty`) has no
 * gambling/games tables or routes — that feature belonged to the separate
 * `loyalty-interaction` deployment being retired; see
 * `hub_api/blueprints/v1/community_loyalty.py`'s module docstring. Route
 * is kept so sidebar/tab navigation doesn't 404.
 */
function LoyaltyGames() {
  return (
    <div>
      <h1 className="text-2xl font-bold text-sky-100 mb-6">Loyalty Games</h1>
      <div className="card p-12 text-center" data-testid="loyalty-games-empty">
        <div className="text-4xl mb-4">🎰</div>
        <p className="text-lg font-semibold text-sky-100 mb-2">Coming after the MVP launch</p>
        <p className="text-navy-400 max-w-md mx-auto">
          Currency games (slots, coinflip, roulette) are not part of the core-currency
          loyalty MVP (gh-317) yet. This page will return once games are rebuilt on the
          new schema.
        </p>
      </div>
    </div>
  );
}

export default LoyaltyGames;
