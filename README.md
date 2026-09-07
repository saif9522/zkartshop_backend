# zKart.shop — Backend (Phase 1: Authentication & Roles)

## Stack
Django 5 + DRF + SimpleJWT + SQLite (default, PostgreSQL optional) + Redis + Channels + Swagger/ReDoc — Python 3.14.5

## What's included in this phase
- Custom `User` model (phone-based login, roles: customer / vendor / delivery / admin / super_admin)
- OTP login & signup (`/api/v1/auth/login/otp/send/`, `/login/otp/verify/`)
- Phone + password login & registration
- Google login endpoint (verifies Google ID token server-side)
- JWT access/refresh tokens with blacklist-on-logout
- Address book (multiple delivery addresses per customer)
- Role-based permission classes (`IsCustomer`, `IsVendor`, `IsDeliveryPartner`, `IsAdmin`, `IsSuperAdmin`)
- Audit log middleware (every non-GET API call is recorded)
- Minimal `Vendor` model stub (fleshed out in the vendor-panel phase)

## Local setup

Requires **Python 3.14.5** (see `.python-version`).

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
pip install google-auth          # needed for Google login token verification

# 3. Configure environment
cp .env.example .env
# Defaults to SQLite — no database setup needed. To use PostgreSQL instead,
# uncomment DB_ENGINE=postgresql (and the DB_* vars) in .env.

# 4. Run migrations
python manage.py migrate

# 5. Create a super admin
python manage.py createsuperuser

# 6. (Optional) Seed sample data so the storefront isn't empty
python manage.py seed_demo_data      # categories, a demo vendor, sample products
python manage.py seed_banners        # homepage hero banners (zKart Corner promos)
python manage.py import_ariba_products  # imports 1097 real products from the Ariba Mart export
                                          # (name, description, real MRP/price, category — see below)

# 7. Run the dev server
python manage.py runserver
```

That's it — `db.sqlite3` is created automatically on first migrate. Swap to
PostgreSQL later just by setting `DB_ENGINE=postgresql` in `.env`; nothing in
the code needs to change.

## API docs (Swagger / ReDoc)

Interactive API documentation is served once the server is running:

| URL | What |
|---|---|
| `http://localhost:8000/swagger/` | Swagger UI — browse and try every endpoint |
| `http://localhost:8000/redoc/` | ReDoc — cleaner read-only reference |
| `http://localhost:8000/swagger.json` | Raw OpenAPI 2.0 schema |

To call authenticated endpoints from Swagger UI: log in via `POST /api/v1/auth/login/otp/verify/` (or `/login/`) elsewhere to get an access token, then click **Authorize** in Swagger UI and paste `Bearer <your access token>`.

## Testing

## Ariba Mart product import

`python manage.py import_ariba_products` loads `seed_assets/ariba_products.json`
(extracted from the Ariba Mart WooCommerce export) and creates:
- A vendor account ("Ariba Mart", phone `+919471500119`)
- 39 categories
- 1097 products with real names, descriptions, and MRP/selling price
  (WooCommerce's actual regular-price/sale-price, not made up)

**Product images are not included** — only the *expected* filename is
recorded on each product (matching what WooCommerce had). To make the
images show up:

1. Copy your image files into `backend/media/products/`
2. Filenames must match exactly what's already recorded — check one in the
   admin panel or via `python manage.py shell` (`Product.objects.first().images.first().image.name`)
3. No re-import needed — images appear as soon as the matching filename exists

Safe to re-run the import command any time (matches by product name, updates instead of duplicating).



```bash
pip install -r requirements.txt   # pytest/pytest-django/factory-boy already included
pytest                             # runs the full suite (43 tests) against an in-memory SQLite DB
pytest --cov=apps --cov-report=term-missing   # with coverage
pytest apps/orders                 # just one app
pytest -k wallet                   # anything matching "wallet"
```

Tests use `mall_of_garhwa.settings.test` (fast password hashing, synchronous
Celery, no throttling, no real third-party API calls — everything takes its
already-tested "not configured" fallback path). Runs automatically in CI on
every push/PR (`.github/workflows/ci.yml`).

## Background jobs (Celery + Redis)

OTP/SMS delivery, order auto-cancel, inventory expiry checks, and AI report
generation all run as Celery tasks so the API never blocks on a slow SMS
provider or a long-running report.

```bash
pip install celery redis

# Terminal 1 — worker (processes tasks: OTP SMS, notifications, etc.)
celery -A mall_of_garhwa worker -l info

# Terminal 2 — beat (fires the scheduled jobs below)
celery -A mall_of_garhwa beat -l info
```

Scheduled jobs (`mall_of_garhwa/celery.py`):
| Task | Schedule | Status |
|---|---|---|
| `send_otp_sms_task` | on-demand (every OTP request) | ✅ live — wired to APITxT |
| `auto_cancel_stale_orders` | every 2 minutes | 🚧 stub — needs Order model (Phase 2) |
| `check_expiring_stock` | daily 6 AM IST | 🚧 stub — needs Inventory model (Phase 5) |
| `generate_daily_ai_sales_report` | daily 11:45 PM IST | 🚧 stub — needs Order model + Anthropic API call |

### SMS/OTP provider — APITxT

`apps/notifications/services.py` calls [APITxT](https://apitxt.com)'s
`POST /api/sendOTP` endpoint. Set your key in `.env`:

```
APITXT_API_KEY=your-real-key-here
APITXT_SENDER_ID=MALLGW
```

If `APITXT_API_KEY` is blank (e.g. local dev), the client logs the OTP to
the console instead of calling the network — so you can develop without a
live key, exactly like before.

**Note**: I wasn't able to make a live call to `apitxt.com` from this
sandbox (its egress network only allows a fixed list of package-registry
domains), so the integration is verified against APITxT's published
`/api/sendOTP` request/response contract but not fired against their live
server here. Test it for real once you deploy, or run
`celery -A mall_of_garhwa worker -l info` locally with your key set — it
should log a success payload like `{"status": "success", "message": "OTP
Sent Successfully", ...}`.

## API endpoints (Phase 1 + 2)

**Auth (Phase 1)**

| Method | Endpoint                              | Purpose                          |
|--------|----------------------------------------|-----------------------------------|
| POST   | `/api/v1/auth/register/`               | Phone + password signup           |
| POST   | `/api/v1/auth/login/`                  | Phone + password login            |
| POST   | `/api/v1/auth/login/otp/send/`         | Send OTP                          |
| POST   | `/api/v1/auth/login/otp/verify/`       | Verify OTP → login/signup         |
| POST   | `/api/v1/auth/login/google/`           | Google login                      |
| POST   | `/api/v1/auth/logout/`                 | Blacklist refresh token           |
| POST   | `/api/v1/auth/token/refresh/`          | Get a new access token            |
| GET/PUT| `/api/v1/auth/profile/`                | View/update own profile           |
| GET/POST| `/api/v1/auth/addresses/`             | List/add delivery addresses       |

**Catalog (Phase 2 — public browse, vendor-owned write)**

| Method | Endpoint                                          | Purpose                              |
|--------|-----------------------------------------------------|----------------------------------------|
| GET    | `/api/v1/catalog/categories/tree/`                  | Nested category tree (for nav/home)    |
| GET    | `/api/v1/catalog/categories/`                       | Flat category list                     |
| GET    | `/api/v1/catalog/brands/`                           | Brand list                             |
| GET    | `/api/v1/catalog/products/`                         | Browse — filters below + search/sort   |
| GET    | `/api/v1/catalog/products/{slug}/`                  | Product detail + similar products      |
| GET    | `/api/v1/catalog/products/featured/`                | Featured/trending products             |
| GET    | `/api/v1/catalog/products/my-products/`             | Vendor's own full product list         |
| POST   | `/api/v1/catalog/products/`                         | Vendor creates a product               |
| PATCH/DELETE | `/api/v1/catalog/products/{slug}/`            | Vendor updates/deletes own product     |

Product filters (query params): `category`, `brand`, `vendor`, `min_price`, `max_price`, `in_stock`, `min_discount`, `is_featured`, `search`, `ordering` (`selling_price`, `-selling_price`, `created_at`, `-rating_avg`, etc).

**Cart & Wishlist (Phase 2 — customer only)**

| Method | Endpoint                                | Purpose                        |
|--------|--------------------------------------------|----------------------------------|
| GET    | `/api/v1/cart/`                            | Current cart with totals         |
| DELETE | `/api/v1/cart/`                            | Clear cart                       |
| POST   | `/api/v1/cart/items/`                      | Add product (or bump quantity)   |
| PATCH  | `/api/v1/cart/items/{item_id}/`            | Change quantity                  |
| DELETE | `/api/v1/cart/items/{item_id}/`            | Remove line item                 |
| GET/POST| `/api/v1/cart/wishlist/`                  | List / add to wishlist           |
| DELETE | `/api/v1/cart/wishlist/{id}/`              | Remove from wishlist             |

Cart response includes `subtotal`, `item_count`, `delivery_charge` (flat `DELIVERY_CHARGE`, waived above `FREE_DELIVERY_THRESHOLD` — both configurable in `.env`), and `grand_total`.

**Vendor panel (Phase 5 — vendor role only)**

| Method | Endpoint                                          | Purpose                                |
|--------|-----------------------------------------------------|-------------------------------------------|
| POST   | `/api/v1/vendors/onboard/`                          | Register shop (once, after signup)        |
| GET/PUT| `/api/v1/vendors/profile/`                          | View/update own shop                      |
| GET    | `/api/v1/vendors/dashboard/`                        | Summary: products, low-stock, expiry, earnings |
| GET    | `/api/v1/vendors/transactions/`                     | Earnings ledger (credits/commission/payouts) |
| GET/POST| `/api/v1/inventory/stock-batches/`                 | List/add stock batches for own products   |
| DELETE | `/api/v1/inventory/stock-batches/{id}/`             | Remove a batch                            |
| GET    | `/api/v1/inventory/stock-batches/expiring-soon/`    | Batches expiring within 3 days            |
| GET    | `/api/v1/inventory/stock-batches/low-stock/`        | Products at/below the low-stock threshold |

Adding or deleting a stock batch automatically recalculates the parent product's `stock_quantity` (sum of all its batches) — the catalog API always reflects the true total without the vendor needing to update both places.

`VendorTransaction` is the earnings ledger: signed `amount` (positive = credit, negative = commission/payout/adjustment), so `balance = sum(amount)`. Right now entries are created manually (admin/shell); Phase 7 wires order settlement to auto-create a credit + commission pair when an order is delivered.

**Orders & Checkout (Phase 7)**

| Method | Endpoint                                              | Purpose                                    | Role      |
|--------|----------------------------------------------------------|-----------------------------------------------|-----------|
| POST   | `/api/v1/orders/checkout/`                                | Cart → one Order per vendor                   | Customer  |
| POST   | `/api/v1/orders/payments/verify/`                          | Verify Razorpay payment signature             | Customer  |
| GET    | `/api/v1/orders/coupons/validate/?code=X`                  | Preview a coupon's discount on the cart       | Customer  |
| GET    | `/api/v1/orders/`                                          | My orders (filter: `?status=`)                | Customer  |
| GET    | `/api/v1/orders/{id}/`                                     | Order detail (items, status history)          | Customer  |
| POST   | `/api/v1/orders/{id}/cancel/`                               | Cancel (restocks items)                       | Customer  |
| GET    | `/api/v1/orders/vendor/`                                    | Incoming orders for my shop                   | Vendor    |
| POST   | `/api/v1/orders/vendor/{id}/accept/`                        | placed → accepted                             | Vendor    |
| POST   | `/api/v1/orders/vendor/{id}/reject/`                        | placed → cancelled (restocks)                 | Vendor    |
| POST   | `/api/v1/orders/vendor/{id}/advance-status/`                | accepted→packing→ready                        | Vendor    |

**How checkout works**: a cart spanning multiple vendors is split into one `Order` per vendor (each shop fulfills independently). Stock is locked (`select_for_update`) and decremented atomically per line item; if any item is short on stock, the whole checkout rolls back — nothing is partially created. A coupon's discount is split proportionally across the vendor sub-orders by their share of the combined subtotal. For Razorpay payments, one Razorpay Order covers the combined total across all sub-orders, so the customer pays once even for a multi-shop cart.

**Order status state machine** (`Order.ALL_TRANSITIONS` in `apps/orders/models.py`): `placed → accepted → packing → ready → pickup → out_for_delivery → nearby → delivered`, with `cancelled` reachable from any pre-pickup state. Vendors can only drive `placed`→`ready`; `pickup` onward belongs to the delivery app (Phase 6) — the same `transition_order()` service function is ready for it to call. Reaching `delivered` auto-settles the vendor's earnings ledger (credit minus commission, via `VendorTransaction`) — verified end-to-end in testing.

Stale unaccepted orders (`placed` for longer than `ORDER_ACCEPT_TIMEOUT_MINUTES`, default 5) are auto-cancelled and restocked by the `auto_cancel_stale_orders` Celery Beat job (every 2 minutes).

**Note on Razorpay**: like APITxT, `api.razorpay.com` isn't reachable from the sandbox this was built in, so the live payment call couldn't be tested end-to-end here — but the failure path was: the code hit the network, Razorpay's SDK raised an error, and it was caught and returned as a clean `400` with the whole checkout rolled back (no partial orders, stock, or cart changes). Test the happy path with your real keys once deployed.

**Delivery Partner Panel (Phase 6)**

| Method | Endpoint                                              | Purpose                                    |
|--------|-----------------------------------------------------------|-------------------------------------------|
| POST   | `/api/v1/delivery/onboard/`                                | Register as a delivery partner (once)      |
| GET/PUT| `/api/v1/delivery/profile/`                                | View/update own profile                    |
| POST   | `/api/v1/delivery/go-online/`                              | Toggle online/offline                      |
| POST   | `/api/v1/delivery/location/`                               | Push current GPS location                  |
| GET    | `/api/v1/delivery/dashboard/`                              | Active orders, delivered today, earnings   |
| GET    | `/api/v1/delivery/orders/available/`                       | Pool of READY, unclaimed orders            |
| GET    | `/api/v1/delivery/orders/mine/`                            | My assigned orders (filter `?status=`)     |
| POST   | `/api/v1/delivery/orders/{id}/assign/`                     | Claim an order (READY → still READY, now owned) |
| POST   | `/api/v1/delivery/orders/{id}/confirm-pickup/`             | `{otp}` → READY → PICKUP (vendor's code)   |
| POST   | `/api/v1/delivery/orders/{id}/start-delivery/`             | PICKUP → OUT_FOR_DELIVERY                  |
| POST   | `/api/v1/delivery/orders/{id}/mark-nearby/`                | OUT_FOR_DELIVERY → NEARBY                  |
| POST   | `/api/v1/delivery/orders/{id}/confirm-delivery/`           | `{otp}` → NEARBY → DELIVERED (customer's code) |
| GET    | `/api/v1/delivery/orders/{id}/route/`                      | Distance/ETA to vendor or customer          |
| GET    | `/api/v1/delivery/transactions/`                           | Earnings ledger                            |
| POST   | `/api/v1/delivery/attendance/check-in/` / `check-out/`     | Daily attendance                            |
| GET    | `/api/v1/delivery/attendance/`                             | Attendance history                          |

**Two separate OTPs per order** (generated at checkout, in `apps/orders/services.py`): `pickup_otp` is shown to the *vendor*, who reads it to the delivery partner to confirm the right order left the shop; `delivery_otp` is shown to the *customer*, who reads it to the delivery partner to confirm final handoff. Both are verified server-side — wrong codes are rejected, tested end-to-end.

**Order claiming is race-safe**: `assign_order()` uses `select_for_update()`, so two delivery partners hitting "accept" on the same order at once can't both win it — verified with a second partner correctly getting "already claimed."

**Route/ETA** (`apps/delivery/services.get_route`): calls Google Directions API when `GOOGLE_MAPS_API_KEY` is set; otherwise falls back to a haversine straight-line distance with an estimated ETA, so navigation still returns something useful without a live Maps key. Destination auto-switches from the vendor's shop to the customer's address the moment pickup is confirmed.

**Live GPS today vs. Phase 8**: `/delivery/location/` is REST/polling-based — the delivery partner's app pushes coordinates periodically, stored on `DeliveryProfile`. Phase 8 adds the Django Channels WebSocket layer so the customer's tracking map updates in real time instead of polling.

**Earnings**: delivering an order pays the partner a flat `DELIVERY_PARTNER_PAYOUT_PER_ORDER` (default ₹20, configurable) via `DeliveryTransaction`, credited automatically the moment `confirm_delivery()` succeeds — verified: dashboard showed `delivered_today: 1`, `balance: 20.0` immediately after.

## Live order tracking (Phase 8 — WebSocket)

`manage.py runserver` only speaks HTTP. WebSocket connections need an ASGI server:

```bash
pip install daphne
daphne -p 8000 mall_of_garhwa.asgi:application
```

**Endpoint**: `ws://<host>/ws/orders/<order_id>/track/?token=<JWT access token>`

The rest of the API authenticates with JWT bearer tokens, not session cookies, so the token is passed as a query param (browsers can't easily set custom WebSocket headers). Only the order's customer, its assigned delivery partner, or an admin/super_admin may connect — every other case (no token, invalid token, an unrelated logged-in user) gets a clean rejection, verified in testing.

On connect you get a `snapshot` (current status + last known location), then live pushes as things happen:
```json
{"type": "snapshot", "status": "ready", "order_number": "MOG...", "location": null}
{"type": "status_update", "status": "pickup", "order_number": "MOG..."}
{"type": "location_update", "latitude": "24.156000", "longitude": "83.810000"}
{"type": "status_update", "status": "out_for_delivery", "order_number": "MOG..."}
{"type": "status_update", "status": "nearby", "order_number": "MOG..."}
{"type": "status_update", "status": "delivered", "order_number": "MOG..."}
```
Verified end-to-end: a WebSocket client connected as the customer received every one of these events in real time while the delivery partner's REST calls (`confirm-pickup`, `/location/`, `start-delivery`, `mark-nearby`, `confirm-delivery`) drove the order through its lifecycle.

`GET /api/v1/orders/{id}/track/` is a REST fallback for the tracking page's first paint (snapshot only, before the socket connects).

**How it's wired**: `apps/core/realtime.broadcast_to_order()` pushes into a Channels group named `order_<id>` via the Redis channel layer; `apps/orders/services.transition_order()` and `apps/delivery/services.update_location()` call it whenever something changes. `apps/delivery/consumers.OrderTrackingConsumer` is the only thing that reads from that group. A broadcast failure (e.g. Redis briefly down) is caught and logged — it never breaks the underlying order/location update itself.

**Admin Panel (Phase 3 — admin/super_admin role only)**

| Method | Endpoint                                              | Purpose                                    |
|--------|-----------------------------------------------------------|-------------------------------------------|
| GET    | `/api/v1/admin/dashboard/`                                 | Platform-wide stats (users, vendors, orders, revenue) |
| GET/PATCH| `/api/v1/admin/users/` / `{id}/`                          | List/view/edit any user                    |
| POST   | `/api/v1/admin/users/{id}/activate/` / `deactivate/`       | Suspend or restore an account              |
| GET/PATCH| `/api/v1/admin/vendors/` / `{id}/`                        | List/view/edit any shop (`?status=`)       |
| POST   | `/api/v1/admin/vendors/{id}/approve/` / `suspend/`         | Vendor approval workflow                   |
| PATCH  | `/api/v1/admin/vendors/{id}/commission/`                   | Change a vendor's commission rate          |
| GET    | `/api/v1/admin/delivery-partners/`                          | List delivery partners (`?status=`)        |
| POST   | `/api/v1/admin/delivery-partners/{id}/approve/` / `suspend/`| Delivery partner approval workflow         |
| GET    | `/api/v1/admin/orders/`                                     | Every order, any vendor (`?status=&vendor=&from=&to=`) |
| CRUD   | `/api/v1/admin/coupons/`                                    | Full coupon management                      |
| CRUD   | `/api/v1/admin/categories/`                                 | Full category management                    |
| GET    | `/api/v1/admin/inventory/low-stock/` / `expiring-soon/`     | Platform-wide (not just one vendor's) stock health |
| POST   | `/api/v1/admin/notifications/broadcast/`                    | Push notification to a role or everyone     |

Users and vendors are exposed via explicit `list/retrieve/update` mixins rather than full `ModelViewSet` — admins can edit or deactivate an account, but can't create raw user/vendor records through this API (those go through proper signup/onboarding); confirmed `POST /admin/users/` returns 405.

Verified end-to-end: vendor approve + commission change, delivery-partner approve, coupon and category creation, user deactivation, platform-wide order/inventory visibility, and broadcast queuing all work — and a customer or vendor token hitting any `/admin/*` endpoint gets a clean 403.

**Super Admin Panel (Phase 4 — super_admin only, unless noted)**

| Method | Endpoint                                              | Purpose                                    |
|--------|-----------------------------------------------------------|-------------------------------------------|
| GET/PATCH| `/api/v1/super-admin/settings/`                            | Platform-wide defaults (commission, delivery pricing, order timeout, maintenance mode) — DB-editable, no redeploy needed |
| CRUD   | `/api/v1/super-admin/cities/`                              | Manage operating cities, each with its own delivery pricing override |
| CRUD   | `/api/v1/super-admin/warehouses/`                           | Manage warehouses per city                  |
| POST   | `/api/v1/super-admin/staff/create-admin/`                   | Create a new admin-role staff account with an initial RBAC permission set |
| GET/PATCH| `/api/v1/super-admin/staff-permissions/`                   | View/edit an existing admin's RBAC flags   |
| GET    | `/api/v1/super-admin/logs/`                                 | Full audit trail (`?user=&method=&path_contains=`) |
| POST   | `/api/v1/super-admin/backups/trigger/`                      | Backs up the DB in the background (Celery) |
| GET    | `/api/v1/super-admin/backups/`                               | Backup run history (status, size, errors) |
| GET    | `/api/v1/super-admin/monitoring/`                            | Request volume, error rate, top endpoints (last 24h) |

**Multi-city delivery pricing, wired into real checkout behavior** (not just a decorative registry): `Vendor.city_ref` optionally links a shop to a managed `City`; `apps/orders/services._delivery_charge_for()` uses the city's `delivery_charge`/`free_delivery_threshold` when set, otherwise falls back to the platform-wide `PlatformSettings` defaults. Verified: a vendor linked to a city with a ₹15 delivery charge / ₹150 free threshold got ₹15 delivery at checkout, even though the super-admin-edited platform default was ₹30 — the city override took precedence correctly.

**Fine-grained RBAC** (`apps/superadmin/permissions.HasStaffPermission` and subclasses): `super_admin` always has full access; an `admin` needs the matching `StaffPermission` flag. Wired as a real demonstration into `AdminVendorViewSet`'s mutating actions (approve/suspend/commission) — browsing stays open to any admin, but changing a vendor's status needs `can_manage_vendors=True`. Verified end-to-end: a limited admin got `403` on vendor-approve, was granted the flag by the super admin, and the *same JWT* immediately succeeded on retry — permissions are checked live against the DB, not baked into the token. (Other admin-panel actions still use the coarser `IsAdmin` check from Phase 3; wiring the remaining `CanManage*` classes into them is the same pattern, just not done for every single endpoint here.)

**Audit logs & monitoring** build on the `AuditLog` middleware from Phase 1 — every non-GET request across the *entire* project has been logged since day one, so `/logs/` and `/monitoring/` reflect real historical traffic, not synthetic data (verified: 134 requests, 20% error rate — mostly from the intentional negative-permission tests run throughout this build).

**Database backup** works with either engine: on SQLite (the default) it copies `db.sqlite3` directly; on PostgreSQL it runs `pg_dump`. Triggering it produced a real 651 KB `.sqlite3` copy on disk with byte-accurate size logged in `BackupLog`. In production, point the task at S3/R2 (already configured via django-storages) instead of local disk.

**Notifications & Reports (Phase 9)**

| Method | Endpoint                                              | Purpose                                    |
|--------|-----------------------------------------------------------|-------------------------------------------|
| GET    | `/api/v1/notifications/`                                    | In-app notification inbox                  |
| GET    | `/api/v1/notifications/unread_count/`                       | Badge count                                |
| POST   | `/api/v1/notifications/{id}/read/` / `mark-all-read/`        | Mark read                                  |
| GET    | `/api/v1/reports/sales/?from=&to=&export=csv\|xlsx`          | Daily order count + revenue (admin)        |
| GET    | `/api/v1/reports/orders/?from=&to=&status=&export=`          | Raw order export (admin)                   |
| GET    | `/api/v1/reports/vendors/?export=`                           | Per-vendor revenue + commission breakdown (admin) |
| GET    | `/api/v1/reports/inventory/?export=`                          | Stock levels — admin sees all, a vendor sees only their own |
| GET    | `/api/v1/reports/gst/?from=&to=&export=`                      | Estimated GST breakdown per delivered order (admin) |
| GET    | `/api/v1/reports/ai-summary/?date=`                           | Latest AI-generated plain-language sales summary |
| POST   | `/api/v1/reports/ai-summary/trigger/`                          | Regenerate today's AI summary on demand    |

**A real bug found and fixed during testing**: DRF reserves the `?format=` query parameter for its own content-negotiation (choosing `json`/`api`/etc. renderers). Using it for "csv vs xlsx" silently broke every report endpoint — a request with `?format=csv` returned a bare `404 Not Found` with no other clue, even though the exact same URL without the query string worked fine. Renamed the parameter to `?export=` everywhere; all five report endpoints were retested afterward and work correctly.

**In-app notifications** are now real, persisted rows — `send_push_notification_task` used to just log a stub; it now creates a `Notification` the owning user can list, count, and mark read (verified end-to-end, including the unread badge dropping from 1 to 0).

**Email** sends through Django's `EMAIL_BACKEND` (console backend in dev — verified a full email with headers/subject/body printed by the worker); swap to a real SMTP/API backend in production settings.

**WhatsApp** reuses the APITxT client with `channel=whatsapp`, same dev-mode-log-when-no-key pattern as SMS — I couldn't find APITxT's WhatsApp-specific request contract in their docs (only DLT/WABA registration steps), so double-check the exact payload shape against their dashboard before relying on it in production.

**Reports** support CSV (built-in, no dependency) and Excel (`openpyxl`) for the same data. The GST report is an *estimate* — it back-calculates a flat 5% GST-inclusive split from `order.subtotal` (verified: ₹27.00 → ₹25.71 taxable + ₹1.29 GST, correctly summing back to ₹27.00); real per-category GST slabs (0/5/12/18%) would need a `gst_rate` field on `Category` — noted as a follow-up, not built here.

**AI sales report** calls the real Anthropic Messages API (`api.anthropic.com` is reachable from this environment — confirmed with a genuine `401` rather than a connection failure when no key is set). Set `ANTHROPIC_API_KEY` in `.env` to get real AI-written summaries; without it, the task falls back to a clearly-labeled `[DEV]` placeholder built from the same aggregates, verified end-to-end: *"7 orders today, 4 delivered, revenue ₹305.34."* The nightly Celery Beat job (`generate_daily_ai_sales_report`, 23:45 IST) and the on-demand trigger both use the same code path.

## Next phases
1. ~~Authentication & Roles~~ ← done
2. ~~Customer-facing catalog & cart APIs~~ ← done
3. ~~Admin panel APIs~~ ← done
4. ~~Super admin (multi-city, RBAC, logs, backups)~~ ← done
5. ~~Vendor panel (product mgmt, inventory, earnings)~~ ← done
6. ~~Delivery partner panel (GPS, OTP handoff, earnings)~~ ← done
7. ~~Order placement + Payment gateway~~ ← done
8. ~~Live order tracking (WebSocket)~~ ← done
9. ~~Notifications & reports~~ ← done
10. React Native mobile apps — same REST/WebSocket API this whole backend already exposes

**All ten backend phases from the original roadmap are now built and individually verified.** What's left of the original plan is entirely frontend: the React customer/vendor/admin web apps, and eventually the React Native mobile apps reusing these same APIs.
# zkart-backend-
# zkart-backend-
# zkart-backend
# zkartshop_backend
