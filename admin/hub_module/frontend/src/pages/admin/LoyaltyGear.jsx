/**
 * Placeholder for the loyalty gear-shop admin page (gh-317). The MVP
 * core-currency schema exposes `loyalty_shop_items` at the service layer
 * (`services.community_loyalty.upsert_item()`/`list_items()`) but the
 * admin blueprint has no CRUD routes for it yet — only the internal
 * (service-to-service) blueprint can list enabled items for chat-command
 * display; see `hub_api/blueprints/v1/community_loyalty.py`. Route is kept
 * so sidebar/tab navigation doesn't 404.
 */
function LoyaltyGear() {
  return (
    <div>
      <h1 className="text-2xl font-bold text-sky-100 mb-6">Loyalty Gear Shop</h1>
      <div className="card p-12 text-center" data-testid="loyalty-gear-empty">
        <div className="text-4xl mb-4">⚙️</div>
        <p className="text-lg font-semibold text-sky-100 mb-2">Coming after the MVP launch</p>
        <p className="text-navy-400 max-w-md mx-auto">
          Gear shop management isn&apos;t exposed to admins yet — the core-currency
          loyalty MVP (gh-317) has the shop-item schema but no admin routes for it.
          This page will return once that surface is built.
        </p>
      </div>
    </div>
  );
}

export default LoyaltyGear;
