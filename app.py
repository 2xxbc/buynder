from flask import Flask, request, jsonify, session
from flask.sessions import SecureCookieSessionInterface
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import bcrypt
import mysql.connector
import os
import requests
import pytesseract
from PIL import Image
import io
import re
import ipaddress
import time
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,   # JavaScript can't read the session cookie (blocks XSS theft)
    SESSION_COOKIE_SAMESITE="Lax",  # cookie won't be sent on cross-site requests (blocks CSRF)
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",  # HTTPS-only when true
    # Logins last 30 days. A "permanent" session cookie gets an expiry date, so browsers keep it across
    # reloads and restarts (iPhone Safari drops date-less cookies whenever it unloads the page). Each
    # request pushes the date forward again, so it's 30 days since the last visit.
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # refuse uploads/requests over 16 MB (scanner photos are far smaller)
)
# Addresses the API is opened at over plain http while testing on the LAN / Tailscale: localhost plus
# DEV_HOSTS from .env (comma-separated, e.g. DEV_HOSTS=192.168.1.20,100.x.y.z), so no IPs live in the code.
DEV_HOSTS = {"localhost"} | {h.strip().lower() for h in os.getenv("DEV_HOSTS", "").split(",") if h.strip()}

# CORS with credentials so session cookies work cross-origin (dev frontend on :5173, prod build on :5180)
CORS(app, supports_credentials=True,
     origins=[f"http://{h}:{port}" for h in sorted(DEV_HOSTS) for port in (5173, 5180)]
     + ["https://buyndermarket.com", "https://www.buyndermarket.com"])
# The Cloudflare tunnel runs on this machine, so every public request reaches us from loopback.
# Cloudflare puts the real visitor's IP in CF-Connecting-IP (and overwrites any copy a visitor sends),
# so trust that header only when the request came from loopback, i.e. through the tunnel.
TUNNEL_ADDRS = {"127.0.0.1", "::1"}


def client_ip():
    remote = get_remote_address()
    if remote in TUNNEL_ADDRS:
        forwarded = request.headers.get("CF-Connecting-IP", "").strip()
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return remote


def via_tunnel():
    """True when the request came from a visitor on the public site, through the Cloudflare tunnel."""
    return get_remote_address() in TUNNEL_ADDRS and "CF-Connecting-IP" in request.headers


class TunnelAwareSessions(SecureCookieSessionInterface):
    """Decides, per request, whether the login cookie gets the Secure flag (browser only sends it over HTTPS).
    Public visitors (through the tunnel) always get Secure. Direct requests to a dev address are plain http,
    so they get a non-Secure cookie or login wouldn't stick. Everything else follows COOKIE_SECURE."""
    def get_cookie_secure(self, app):
        if via_tunnel():
            return True                                    # buyndermarket.com is always HTTPS
        if request.host.split(":")[0].lower() in DEV_HOSTS:
            return False                                   # http://<dev host>:5051 etc. (port stripped)
        return app.config["SESSION_COOKIE_SECURE"]


app.session_interface = TunnelAwareSessions()


@app.before_request
def keep_logins_permanent():
    """Sessions made before 2026-10-24 had no expiry date; upgrade them on their next request."""
    if "_user_id" in session and not session.permanent:
        session.permanent = True


@app.after_request
def no_store(resp):
    """API answers depend on who is logged in, so browsers must never reuse a saved copy: Safari could
    otherwise answer /me from an old copy that says "logged out". A route can still set its own rule."""
    resp.headers.setdefault("Cache-Control", "no-store")
    return resp


# Rate limiting — caps how often an IP can hit sensitive routes (blocks brute-force)
limiter = Limiter(
    client_ip,            # limit per real visitor IP
    app=app,
    default_limits=[],    # no global cap; we limit specific routes only
    storage_uri="memory://",
)

# --- Flask-Login setup ---
login_manager = LoginManager()
login_manager.init_app(app)

class User(UserMixin):
    def __init__(self, id, username, email):
        self.id = id
        self.username = username
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, username, email FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if row:
        return User(row["id"], row["username"], row["email"])
    return None

# Return JSON 401 instead of redirecting when not logged in
@login_manager.unauthorized_handler
def unauthorized():
    return {"error": "Not authenticated"}, 401

db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME")
}

POKEMON_TCG_API_KEY = os.getenv("POKEMON_TCG_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")


def send_discord_alert(title, description, image_url=None, color=0xED4245):
    if not DISCORD_WEBHOOK_URL:
        return False

    embed = {
        "title": title,
        "description": description,
        "color": color
    }

    if image_url:
        embed["thumbnail"] = {"url": image_url}

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]})
        return response.status_code == 204
    except Exception as e:
        print(f"Discord alert failed: {e}")
        return False

def server_error(where):
    """Log the real exception (see `journalctl -u buynder-api`) and give the browser a generic message,
    so database and upstream error details never reach the public."""
    app.logger.exception("%s failed", where)
    return "Something went wrong. Please try again."


# Upload over MAX_CONTENT_LENGTH → a JSON error the scanner can show, instead of Flask's HTML page
@app.errorhandler(413)
def too_large(e):
    return {"error": "That photo is too big. Please use one under 16 MB."}, 413


# Rate limit hit → JSON the frontend can show (Flask-Limiter's default is an HTML page)
@app.errorhandler(429)
def too_many(e):
    # Counted by agents/ops_report.py (path only, never who)
    app.logger.warning("rate limit hit on %s", request.path)
    return {"error": "Too many tries. Please wait a bit and try again."}, 429


# ---- "last seen" for the ops report's active-user count (migration 002_users_last_seen.sql) ----
_LAST_SEEN = {"on": None, "checked": 0}  # whether users.last_seen exists; "no" is re-checked every 10 minutes


@app.before_request
def touch_last_seen():
    """Record when a logged-in user was last active, at most once every 5 minutes per session.
    Does nothing until the migration has added users.last_seen (picked up within 10 minutes, no restart)."""
    if not current_user.is_authenticated:
        return
    now = time.time()
    if _LAST_SEEN["on"] is False and now - _LAST_SEEN["checked"] < 600:
        return
    if now - session.get("seen_at", 0) < 300:
        return
    session["seen_at"] = now
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        if not _LAST_SEEN["on"]:
            cursor.execute("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() "
                           "AND table_name = 'users' AND column_name = 'last_seen'")
            _LAST_SEEN.update(on=cursor.fetchone()[0] > 0, checked=now)
        if _LAST_SEEN["on"]:
            cursor.execute("UPDATE users SET last_seen = NOW() WHERE id = %s", (current_user.id,))
            conn.commit()
        cursor.close()
        conn.close()
    except Exception:
        app.logger.warning("last_seen update failed")  # never block the actual request


@app.route("/")
def home():
    return "PokeMarket backend is running!"


@app.route("/all-cards")
@login_required
def all_cards():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT p.id, p.name, p.set_name, p.image_url, p.poketrace_id,
                   (SELECT price FROM price_history 
                    WHERE product_id = p.id 
                    ORDER BY recorded_at DESC LIMIT 1) AS latest_price
            FROM products p
            WHERE p.user_id = %s AND p.on_watchlist = 1
            ORDER BY p.created_at DESC
        """, (current_user.id,))
        cards = cursor.fetchall()
        cursor.close()
        conn.close()
        return {"cards": cards}
    except Exception:
        return server_error("all_cards")


@app.route("/delete-card/<int:product_id>", methods=["DELETE"])
@login_required
def delete_card(product_id):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        # Verify ownership first
        cursor.execute("SELECT user_id FROM products WHERE id = %s", (product_id,))
        owner = cursor.fetchone()
        if not owner or owner[0] != current_user.id:
            cursor.close()
            conn.close()
            return {"success": False, "error": "Not found"}, 404

        # "Remove from watchlist" used to delete the card outright, taking its collection and sold rows
        # with it. If the card is still in the collection or sold history, only take it off the watchlist.
        cursor.execute("SELECT EXISTS(SELECT 1 FROM collection WHERE product_id = %s) OR "
                       "EXISTS(SELECT 1 FROM sold WHERE product_id = %s)", (product_id, product_id))
        if cursor.fetchone()[0]:
            cursor.execute("UPDATE products SET on_watchlist = 0 WHERE id = %s", (product_id,))
            conn.commit()
            cursor.close()
            conn.close()
            return {"success": True, "kept": True}

        cursor.execute("DELETE FROM price_history WHERE product_id = %s", (product_id,))
        cursor.execute("DELETE FROM alerts WHERE product_id = %s", (product_id,))
        cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return {"success": True, "kept": False}
    except Exception:
        return {"success": False, "error": server_error("delete_card")}


@app.route("/price-history/<int:product_id>")
def price_history(product_id):
    try:
        import json
        from datetime import datetime
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        
        # Try PokeTrace history first (preferred — up to 365 days of daily data)
        cursor.execute(
            "SELECT poketrace_history, justtcg_history FROM products WHERE id = %s",
            (product_id,)
        )
        row = cursor.fetchone()
        
        history = []
        
       # Source 1: PokeTrace (preferred) — TCGPlayer source only, dedupe by date
        if row and row.get("poketrace_history"):
            raw = row["poketrace_history"]
            pt_history = json.loads(raw) if isinstance(raw, str) else raw
            tcg_only = {}  # date -> point (TCGPlayer source only)
            for point in pt_history:
                if point.get("source") != "tcgplayer":
                    continue  # Skip eBay & other sources
                date_str = point.get("date")
                price_val = point.get("median7d") or point.get("avg") or point.get("low") or point.get("high")
                if date_str is None or price_val is None:
                    continue
                # If a date somehow shows up twice from tcgplayer, last one wins
                tcg_only[date_str] = {
                    "price": float(price_val),
                    "recorded_at": date_str + "T00:00:00"
                }
            history = sorted(tcg_only.values(), key=lambda h: h["recorded_at"])
        
        # Source 2: JustTCG history (legacy — fallback if no PokeTrace data)
        if not history and row and row.get("justtcg_history"):
            raw = row["justtcg_history"]
            jt_history = json.loads(raw) if isinstance(raw, str) else raw
            for point in jt_history:
                # JustTCG shape: {"p": 384.18, "t": 1778803200}
                if point.get("p") is None or point.get("t") is None:
                    continue
                history.append({
                    "price": float(point["p"]),
                    "recorded_at": datetime.utcfromtimestamp(point["t"]).isoformat()
                })
        
        # Source 3: Local price_history table (last-ditch fallback)
        if not history:
            cursor.execute("""
                SELECT price, recorded_at 
                FROM price_history 
                WHERE product_id = %s 
                ORDER BY recorded_at ASC
            """, (product_id,))
            history = cursor.fetchall()
            for h in history:
                if hasattr(h["recorded_at"], "isoformat"):
                    h["recorded_at"] = h["recorded_at"].isoformat()
                h["price"] = float(h["price"])
        
        cursor.close()
        conn.close()

        # Gate: logged-out visitors only get the last 30 days
        if not current_user.is_authenticated:
            from datetime import timedelta
            cutoff = (datetime.now() - timedelta(days=30)).isoformat()
            history = [h for h in history if h.get("recorded_at", "") >= cutoff]

        return {"history": history}
    except Exception:
        return {"error": server_error("price_history")}, 500

@app.route("/signal/<int:product_id>")
def get_signal(product_id):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT price, recorded_at 
            FROM price_history 
            WHERE product_id = %s 
            ORDER BY recorded_at ASC
        """, (product_id,))

        history = cursor.fetchall()
        cursor.close()
        conn.close()

        if len(history) < 3:
            return {"signal": "WATCH", "reason": "Not enough data yet"}

        prices = [float(h["price"]) for h in history]
        current = prices[-1]
        oldest = prices[0]
        all_time_high = max(prices)

        recent_7 = prices[-7:] if len(prices) >= 7 else prices
        avg_7 = sum(recent_7) / len(recent_7)

        change_pct = ((current - oldest) / oldest) * 100
        near_high = (current / all_time_high) >= 0.95
        above_avg = current > avg_7

        if near_high and change_pct > 15:
            signal = "SELL"
            reason = "Near all-time high, strong uptrend. Lock in gains."
        elif change_pct > 10 and above_avg:
            signal = "HOLD"
            reason = "Trending up, above 7-day average. Let it ride."
        elif change_pct < -10:
            signal = "BUY"
            reason = "Price dropped. Possible good entry point."
        else:
            signal = "HOLD"
            reason = "Stable. No strong signal either way."

        return {
            "signal": signal,
            "reason": reason,
            "change_pct": round(change_pct, 2),
            "current": current,
            "all_time_high": all_time_high
        }
    except Exception:
        return {"error": server_error("get_signal")}


# ---- Price paid: "unknown" is not the same as $0 ----
# A card added without a purchase price has NO cost basis; counting it as $0 made its whole
# value look like profit. Once collection.price_paid allows NULL (migration 004), NULL means
# "unknown" and 0 means "really paid $0" (a gift, a pack pull). Before that, the column can't
# hold "unknown", so a stored 0 is treated as unknown.
_PAID_NULLABLE = False


def paid_nullable(cursor):
    """True when collection.price_paid accepts NULL. Cached once true (it never goes back)."""
    global _PAID_NULLABLE
    if not _PAID_NULLABLE:
        cursor.execute("""
            SELECT IS_NULLABLE FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'collection' AND COLUMN_NAME = 'price_paid'
        """)
        row = cursor.fetchone()
        value = row["IS_NULLABLE"] if isinstance(row, dict) else (row[0] if row else None)
        _PAID_NULLABLE = value == "YES"
    return _PAID_NULLABLE


def known_paid(value, nullable):
    """The price paid as a float, or None when it's unknown."""
    if value is None:
        return None
    paid = float(value)
    if paid == 0 and not nullable:
        return None
    return paid


def parse_paid(raw):
    """Read a price paid sent by the browser. Returns (value, error); value None = left blank."""
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None, None
    try:
        paid = round(float(raw), 2)
    except (TypeError, ValueError):
        return None, "Price paid must be a number"
    if paid != paid or paid < 0 or paid > 1_000_000:  # paid != paid catches NaN
        return None, "Price paid must be between $0 and $1,000,000"
    return paid, None


@app.route("/add-to-collection/<int:product_id>", methods=["POST"])
@login_required
def add_to_collection(product_id):
    data = request.get_json() or {}
    try:
        quantity = int(data.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 0
    if not 1 <= quantity <= 999:
        return {"success": False, "error": "Quantity must be a whole number from 1 to 999"}, 400
    price_paid, error = parse_paid(data.get("price_paid"))
    if error:
        return {"success": False, "error": error}, 400
    priority = data.get("priority", "normal")
    if priority not in ("normal", "high"):
        priority = "normal"
    from_watchlist = bool(data.get("from_watchlist"))  # "Move to collection": also take it off the watchlist
    card_condition = data.get("condition", "NEAR_MINT")
    valid = {"NEAR_MINT", "LIGHTLY_PLAYED", "MODERATELY_PLAYED", "HEAVILY_PLAYED", "DAMAGED"}
    if card_condition not in valid:
        card_condition = "NEAR_MINT"
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        # Only your own saved cards (every save goes through /save-card-poketrace under your account)
        cursor.execute("SELECT id FROM products WHERE id = %s AND user_id = %s", (product_id, current_user.id))
        if cursor.fetchone() is None:
            cursor.close()
            conn.close()
            return {"success": False, "error": "Card not found"}, 404
        if price_paid is None and not paid_nullable(cursor):
            price_paid = 0  # column can't hold "unknown" yet; 0 is read back as unknown
        cursor.execute(
            "INSERT INTO collection (user_id, product_id, quantity, price_paid, priority, card_condition) VALUES (%s, %s, %s, %s, %s, %s)",
            (current_user.id, product_id, quantity, price_paid, priority, card_condition)
        )
        if from_watchlist:
            cursor.execute("UPDATE products SET on_watchlist = 0 WHERE id = %s AND user_id = %s",
                           (product_id, current_user.id))
        conn.commit()
        cursor.close()
        conn.close()
        return {"success": True}
    except Exception:
        return {"success": False, "error": server_error("add_to_collection")}

@app.route("/remove-from-collection/<int:collection_id>", methods=["DELETE"])
@login_required
def remove_from_collection(collection_id):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM collection WHERE id = %s AND user_id = %s", (collection_id, current_user.id))
        conn.commit()
        cursor.close()
        conn.close()

        return {"success": True}
    except Exception:
        return {"success": False, "error": server_error("remove_from_collection")}


@app.route("/update-price-paid/<int:collection_id>", methods=["POST"])
@login_required
@limiter.limit("60 per minute")
def update_price_paid(collection_id):
    """Set (or clear) what the user paid for one collection item. Body: {"price_paid": 12.5 | null}."""
    data = request.get_json(silent=True) or {}
    price_paid, error = parse_paid(data.get("price_paid"))
    if error:
        return {"success": False, "error": error}, 400
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        # Only the owner's own items (same answer for "not yours" and "doesn't exist")
        cursor.execute("SELECT id FROM collection WHERE id = %s AND user_id = %s", (collection_id, current_user.id))
        if cursor.fetchone() is None:
            cursor.close()
            conn.close()
            return {"success": False, "error": "Card not found in your collection"}, 404
        nullable = paid_nullable(cursor)
        if price_paid is None and not nullable:
            price_paid = 0
        cursor.execute("UPDATE collection SET price_paid = %s WHERE id = %s AND user_id = %s",
                       (price_paid, collection_id, current_user.id))
        conn.commit()
        cursor.close()
        conn.close()
        return {"success": True, "price_paid": known_paid(price_paid, nullable)}
    except Exception:
        return {"success": False, "error": server_error("update_price_paid")}


@app.route("/collection")
@login_required
def get_collection():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                c.id AS collection_id,
                c.quantity,
                c.price_paid,
                c.priority,
                c.card_condition,
                c.date_added,
                p.id AS product_id,
                p.name,
                p.set_name,
                p.image_url,
                (SELECT price FROM price_history 
                 WHERE product_id = p.id 
                 ORDER BY recorded_at DESC LIMIT 1) AS current_price
            FROM collection c
            JOIN products p ON c.product_id = p.id
            WHERE c.user_id = %s
            ORDER BY c.date_added DESC
        """, (current_user.id,))

        items = cursor.fetchall()

        nullable = paid_nullable(cursor)
        total_paid = 0
        total_value = 0
        priced_value = 0  # value of only the cards with a known price paid, so P&L compares like with like
        unpriced = 0

        for item in items:
            qty = item["quantity"] or 1
            paid = known_paid(item["price_paid"], nullable)
            current = float(item["current_price"] or 0)
            item["price_paid"] = paid
            item["total_value"] = current * qty
            total_value += current * qty
            if paid is None:
                item["total_paid"] = None
                item["profit_loss"] = None
                unpriced += 1
            else:
                item["total_paid"] = paid * qty
                item["profit_loss"] = (current - paid) * qty
                total_paid += paid * qty
                priced_value += current * qty

        cursor.close()
        conn.close()

        return {
            "items": items,
            "stats": {
                "total_paid": round(total_paid, 2),
                "total_value": round(total_value, 2),
                "unrealized_pnl": round(priced_value - total_paid, 2),
                "unpriced_count": unpriced,
                "zero_means_unknown": not nullable,  # before migration 004 a $0 can't be stored as "really $0"
            }
        }
    except Exception:
        return {"error": server_error("get_collection")}


@app.route("/mark-sold/<int:collection_id>", methods=["POST"])
@login_required
def mark_sold(collection_id):
    data = request.get_json() or {}
    sale_price = data.get("sale_price", 0)
    platform = data.get("platform", "")
    notes = data.get("notes", "")

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT product_id, quantity, price_paid FROM collection WHERE id = %s AND user_id = %s", (collection_id, current_user.id))
        item = cursor.fetchone()

        if not item:
            return {"success": False, "error": "Collection item not found"}

        cursor.execute(
            "INSERT INTO sold (user_id, product_id, sale_price, platform, notes) VALUES (%s, %s, %s, %s, %s)",
            (current_user.id, item["product_id"], sale_price, platform, notes)
        )

        cursor.execute("DELETE FROM collection WHERE id = %s AND user_id = %s", (collection_id, current_user.id))

        conn.commit()
        cursor.close()
        conn.close()

        return {"success": True}
    except Exception:
        return {"success": False, "error": server_error("mark_sold")}


@app.route("/sold")
@login_required
def get_sold():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT 
                s.id AS sold_id,
                s.sale_price,
                s.platform,
                s.notes,
                s.sold_at,
                p.name,
                p.set_name,
                p.image_url
            FROM sold s
            JOIN products p ON s.product_id = p.id
            WHERE s.user_id = %s
            ORDER BY s.sold_at DESC
        """, (current_user.id,))

        items = cursor.fetchall()

        total_sold = sum(float(item["sale_price"] or 0) for item in items)

        cursor.close()
        conn.close()

        return {
            "items": items,
            "stats": {
                "total_sold": round(total_sold, 2),
                "count": len(items)
            }
        }
    except Exception:
        return {"error": server_error("get_sold")}


@app.route("/portfolio")
@login_required
def portfolio():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT 
                c.quantity,
                c.price_paid,
                (SELECT price FROM price_history 
                 WHERE product_id = c.product_id 
                 ORDER BY recorded_at DESC LIMIT 1) AS current_price
            FROM collection c
            WHERE c.user_id = %s
        """, (current_user.id,))
        collection_items = cursor.fetchall()

        nullable = paid_nullable(cursor)
        total_paid = 0
        total_value = 0
        priced_value = 0
        unpriced = 0
        for item in collection_items:
            qty = item["quantity"] or 1
            paid = known_paid(item["price_paid"], nullable)
            current = float(item["current_price"] or 0)
            total_value += current * qty
            if paid is None:
                unpriced += 1  # unknown cost: in the binder's worth, not in P&L
            else:
                total_paid += paid * qty
                priced_value += current * qty

        unrealized_pnl = priced_value - total_paid

        cursor.execute("""
            SELECT 
                s.sale_price,
                (SELECT price_paid FROM collection 
                 WHERE product_id = s.product_id 
                 ORDER BY date_added DESC LIMIT 1) AS price_paid
            FROM sold s
            WHERE s.user_id = %s
        """, (current_user.id,))
        sold_items = cursor.fetchall()

        total_sold = sum(float(s["sale_price"] or 0) for s in sold_items)
        realized_pnl = 0

        cursor.execute("""
            SELECT p.name, p.set_name, p.image_url,
                   (SELECT price FROM price_history 
                    WHERE product_id = p.id 
                    ORDER BY recorded_at DESC LIMIT 1) AS current_price,
                   (SELECT price FROM price_history 
                    WHERE product_id = p.id 
                    ORDER BY recorded_at ASC LIMIT 1) AS first_price
            FROM products p
            WHERE p.user_id = %s
        """, (current_user.id,))
        trend_items = cursor.fetchall()

        biggest_gainer = None
        biggest_loser = None
        best_pct = -9999
        worst_pct = 9999

        for item in trend_items:
            current = float(item["current_price"] or 0)
            first = float(item["first_price"] or 0)
            if first > 0 and current > 0:
                pct = ((current - first) / first) * 100
                if pct > best_pct:
                    best_pct = pct
                    biggest_gainer = {
                        "name": item["name"],
                        "set_name": item["set_name"],
                        "image_url": item["image_url"],
                        "change_pct": round(pct, 2),
                        "current_price": current
                    }
                if pct < worst_pct:
                    worst_pct = pct
                    biggest_loser = {
                        "name": item["name"],
                        "set_name": item["set_name"],
                        "image_url": item["image_url"],
                        "change_pct": round(pct, 2),
                        "current_price": current
                    }

        cursor.close()
        conn.close()

        return {
            "binder_worth": round(total_value, 2),
            "total_paid": round(total_paid, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "total_sold": round(total_sold, 2),
            "realized_pnl": round(realized_pnl, 2),
            "total_pnl": round(unrealized_pnl + realized_pnl, 2),
            "unpriced_count": unpriced,
            "biggest_gainer": biggest_gainer,
            "biggest_loser": biggest_loser
        }
    except Exception:
        return {"error": server_error("portfolio")}


SCAN_FORMATS = {"JPEG", "MPO", "PNG", "WEBP"}  # MPO = the JPEG variant some phones save
SCAN_MAX_PIXELS = 50_000_000                   # ~50 megapixels; bigger is a "decompression bomb" risk


@app.route("/scan-card", methods=["POST"])
@login_required
@limiter.limit("10 per minute;100 per day", key_func=lambda: f"scan:{current_user.get_id()}")
def scan_card():
    from flask import request
    from PIL import ImageFilter, ImageOps, ImageEnhance

    if "image" not in request.files:
        return {"error": "No image uploaded"}, 400

    file = request.files["image"]

    try:
        # Image.open only reads the header, so check the type and size before decoding any pixels
        try:
            image = Image.open(io.BytesIO(file.read()))
        except Exception:
            return {"error": "Please upload a JPG, PNG or WebP photo"}, 400
        if image.format not in SCAN_FORMATS:
            return {"error": "Please upload a JPG, PNG or WebP photo"}, 400
        if image.width * image.height > SCAN_MAX_PIXELS:
            return {"error": "That photo is too large. Please use a smaller one."}, 400

        if image.mode != "RGB":
            image = image.convert("RGB")

        top_portion = image.crop((0, 0, image.width, image.height // 4))

        gray = ImageOps.grayscale(top_portion)

        contrast = ImageEnhance.Contrast(gray).enhance(2.0)
        sharp = contrast.filter(ImageFilter.SHARPEN)

        threshold = sharp.point(lambda p: 255 if p > 130 else 0)

        text_normal = pytesseract.image_to_string(sharp, config="--psm 7")
        text_threshold = pytesseract.image_to_string(threshold, config="--psm 7")
        text_full = pytesseract.image_to_string(sharp, config="--psm 6")

        all_text = text_normal + "\n" + text_threshold + "\n" + text_full

        candidates = []
        for line in all_text.split("\n"):
            cleaned = re.sub(r"[^a-zA-Z\s]", "", line).strip()
            if 3 <= len(cleaned) <= 25 and not cleaned.lower() in ["stage", "basic", "trainer", "energy", "pokemon", "hp"]:
                words = cleaned.split()
                if len(words) <= 4:
                    candidates.append(cleaned)

        card_name = None
        for c in candidates:
            if c[0].isupper():
                card_name = c
                break

        if not card_name and candidates:
            card_name = candidates[0]

        if not card_name:
            return {"error": "Could not read card name"}

        url = "https://api.pokemontcg.io/v2/cards"
        headers = {"X-Api-Key": POKEMON_TCG_API_KEY}
        params = {"q": f'name:"{card_name}"', "pageSize": 5}

        response = requests.get(url, headers=headers, params=params, timeout=10)
        data = response.json()

        if not data.get("data"):
            first_word = card_name.split()[0]
            params = {"q": f'name:{first_word}*', "pageSize": 5}
            response = requests.get(url, headers=headers, params=params, timeout=10)
            data = response.json()

        return {
            "detected_name": card_name,
            "matches": data.get("data", [])
        }
    except Exception:
        return {"error": server_error("scan_card")}

# ============================================================
# PokeTrace routes
# ============================================================

# Public card pages ask PokeTrace for the same card again and again. Keep successful answers
# for 10 minutes (per gunicorn worker) so visitors can't burn through the API quota.
PT_CACHE = {}          # (path, params) -> (expires_at, data)
PT_CACHE_SECONDS = 600
PT_CACHE_MAX = 2000
PT_REMAINING = {"value": None}  # PokeTrace requests left today, from its last reply (per worker)


POKETRACE_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def valid_poketrace_id(poketrace_id):
    """PokeTrace ids are UUIDs. Anything else (like an encoded ../) must never reach their API."""
    return bool(POKETRACE_ID.fullmatch(poketrace_id or ""))


def poketrace_get(path, params=None, timeout=15):
    """GET https://api.poketrace.com/v1{path}. Returns (status_code, json or None)."""
    key = (path, tuple(sorted((params or {}).items())))
    hit = PT_CACHE.get(key)
    if hit and hit[0] > time.time():
        return 200, hit[1]
    r = requests.get(f"https://api.poketrace.com/v1{path}",
                     headers={"X-API-Key": os.getenv("POKETRACE_API_KEY")}, params=params, timeout=timeout)
    remaining = r.headers.get("x-ratelimit-remaining")
    if remaining and remaining.isdigit():
        PT_REMAINING["value"] = int(remaining)  # what PokeTrace says is left today (see card_prices)
    if r.status_code != 200:
        return r.status_code, None
    data = r.json()
    if len(PT_CACHE) >= PT_CACHE_MAX:
        PT_CACHE.pop(next(iter(PT_CACHE)))  # drop the oldest entry
    PT_CACHE[key] = (time.time() + PT_CACHE_SECONDS, data)
    return 200, data


# ---- Card search ----
# People type things like "absol ex", "absol magma", "charizard 4/102" or just "96/95". PokeTrace's search
# matches card names, and names often lack "ex" (Absol 96/95 is just "Absol"), so:
#   - "ex" / "EX" / "-EX" is optional: it's dropped from the PokeTrace query, and ex cards rank first
#   - words that match a set name in our tracked_sets ("magma") pick the set: PokeTrace's own set filter
#   - a card number ("96/95", "XY62") narrows the results; a number alone is looked up in market_cards
#   - more than 20 results: PokeTrace's page cursor is passed back as next_cursor ("Load more")
# PokeTrace cost: 1 request per search or "Load more"; up to 3 when set words match 2-3 sets; 0 for a bare number.
SEARCH_LIMIT = 20
SEARCH_MAX_SETS = 3
NUMBER_RE = re.compile(r"^(?:[a-z]{0,5}\d{1,4}[a-z]?/[a-z]{0,5}\d{1,4}|[a-z]{1,5}\d{1,4})$")
_SETS_CACHE = {"at": 0, "sets": []}


def parse_search(query):
    """Split what someone typed into name words, an optional card number, and whether they said "ex"."""
    words, number, wants_ex = [], None, False
    for token in query.lower().replace(",", " ").split():
        token = token.strip(".")
        if token in ("ex", "-ex"):
            wants_ex = True
            continue
        if token.endswith("-ex"):          # "Absol-EX"
            wants_ex, token = True, token[:-3]
        if NUMBER_RE.match(token) and any(ch.isdigit() for ch in token):
            number = token
            continue
        if token:
            words.append(token)
    return words, number, wants_ex


def same_number(a, b):
    """'096/095' matches '96/95'; '96' matches '96/95'; promo numbers compare as text."""
    def parts(n):
        return [p.lstrip("0") or "0" for p in (n or "").lower().split("/")]
    pa, pb = parts(a), parts(b)
    return pa == pb or (len(pa) == 1 and pa[0] == pb[0])


def tracked_set_names():
    """[(slug, lowercased name)] of active sets, cached for an hour."""
    if time.time() - _SETS_CACHE["at"] > 3600:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("SELECT slug, name FROM tracked_sets WHERE active = 1")
        _SETS_CACHE["sets"] = [(slug, (name or "").lower()) for slug, name in cursor.fetchall()]
        cursor.close()
        conn.close()
        _SETS_CACHE["at"] = time.time()
    return _SETS_CACHE["sets"]


def pick_sets(words):
    """The first word is the card's name. Later words that appear in set names choose the set(s).
    Returns (name_words, set_slugs): set_slugs is empty when no set fits or too many do."""
    if len(words) < 2:
        return words, []
    sets = tracked_set_names()
    set_words = [w for w in words[1:] if len(w) >= 3 and any(w in name for _, name in sets)]
    if not set_words:
        return words, []
    matches = [slug for slug, name in sets if all(w in name for w in set_words)]
    if not 1 <= len(matches) <= SEARCH_MAX_SETS:
        return words, []
    return [w for w in words if w not in set_words], matches


def card_rows(cards):
    """PokeTrace cards -> our search result rows (TCGplayer NM price as the display price)."""
    rows = []
    for card in cards:
        tcg = ((card.get("prices") or {}).get("tcgplayer") or {})
        display_price = (tcg.get("NEAR_MINT") or {}).get("avg")
        if display_price is None:
            display_price = next((c.get("avg") for c in tcg.values() if c and c.get("avg")), None)
        rows.append({
            "poketrace_id": card.get("id"),
            "name": card.get("name"),
            "set_name": (card.get("set") or {}).get("name"),
            "set_slug": (card.get("set") or {}).get("slug"),
            "number": card.get("cardNumber"),
            "rarity": card.get("rarity"),
            "image": card.get("image"),
            "display_price": display_price,
        })
    return rows


def dedupe(rows):
    """PokeTrace sometimes has two records for one physical card (same set + number + name + rarity),
    one with a price and one without. Keep one, preferring the priced one."""
    kept = {}
    for r in rows:
        key = (r["set_slug"], r["number"], r["name"], r["rarity"])
        if key not in kept or (kept[key]["display_price"] is None and r["display_price"] is not None):
            kept[key] = r
    return list(kept.values())


def local_number_search(number, words):
    """A card number with little else: look it up in market_cards (no PokeTrace request)."""
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    # PokeTrace writes some numbers with leading zeros ("033/167"), some without ("96/95"): try the forms
    # people type, without zeros, and padded to 3 digits; same_number() below does the exact check
    parts = [p.lstrip("0") or "0" for p in number.split("/")]
    forms = {number, "/".join(parts), "/".join(p.zfill(3) if p.isdigit() else p for p in parts)}
    sql = """SELECT poketrace_id, name, set_name, set_slug, card_number, rarity, image_url, avg
             FROM market_cards WHERE (card_number IN (""" + ", ".join(["%s"] * len(forms)) + """)"""
    params = list(forms)
    if "/" not in number:  # "96" alone: any card numbered 96/...
        sql += " OR card_number LIKE %s OR card_number LIKE %s"
        params += [parts[0] + "/%", parts[0].zfill(3) + "/%"]
    sql += ")"
    for w in words:
        sql += " AND (LOWER(name) LIKE %s OR LOWER(set_name) LIKE %s)"
        params += [f"%{w}%", f"%{w}%"]
    cursor.execute(sql + " ORDER BY avg DESC LIMIT %s", params + [SEARCH_LIMIT])
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [{"poketrace_id": r["poketrace_id"], "name": r["name"], "set_name": r["set_name"], "set_slug": r["set_slug"],
             "number": r["card_number"], "rarity": r["rarity"], "image": r["image_url"],
             "display_price": float(r["avg"]) if r["avg"] is not None else None}
            for r in rows if same_number(number, r["card_number"])]


@app.route("/poketrace-search/<path:query>")  # path: card numbers contain "/" (96/95)
@limiter.limit("60 per minute;1000 per day")
def poketrace_search(query):
    """Search cards: name words, set words, card number, optional "ex". Query: ?cursor=<from next_cursor>."""
    if not os.getenv("POKETRACE_API_KEY"):
        return {"error": "PokeTrace API key not configured"}, 500
    query = query.strip()[:100]
    cursor = (request.args.get("cursor") or "")[:200] or None
    words, number, wants_ex = parse_search(query)
    try:
        if not words and number:
            results = local_number_search(number, [])
            return {"results": results, "total": len(results), "next_cursor": None,
                    "hint": None if results else "Add the card's name too, e.g. \"absol 96/95\"."}
        if not words:
            return {"results": [], "total": 0, "next_cursor": None}

        name_words, set_slugs = pick_sets(words)
        searches = [{"set": slug} for slug in set_slugs] or [{}]
        cards, next_cursor = [], None
        for extra in searches:
            params = {"search": " ".join(name_words), "market": "US", "limit": SEARCH_LIMIT, **extra}
            if cursor and len(searches) == 1:
                params["cursor"] = cursor
            status, body = poketrace_get("/cards", params, timeout=10)
            if status != 200 or not body:
                return {"error": f"PokeTrace returned {status}"}, 502
            cards += body.get("data", []) or []
            pagination = body.get("pagination") or {}
            if len(searches) == 1 and pagination.get("hasMore"):
                next_cursor = pagination.get("nextCursor")

        results = dedupe(card_rows(cards))
        if set_slugs:
            # Whatever PokeTrace does with search + set together, keep only real matches: the chosen set(s)
            # and every name word in the card's name. Nothing left? One plain name search, same filter,
            # and if that's empty too, the plain name results (better than nothing).
            wanted = lambda r: r["set_slug"] in set_slugs and all(w in (r["name"] or "").lower() for w in name_words)
            in_set = [r for r in results if wanted(r)]
            if not in_set and not cursor:
                status, body = poketrace_get("/cards", {"search": " ".join(name_words), "market": "US",
                                                        "limit": SEARCH_LIMIT}, timeout=10)
                plain = dedupe(card_rows((body or {}).get("data", []) or [])) if status == 200 else []
                in_set = [r for r in plain if wanted(r)] or plain
                next_cursor = None
            results = in_set
        if number:
            results = [r for r in results if same_number(number, r["number"])]
            next_cursor = None  # paging would only continue the name search; the number already narrowed it
            if not results and not cursor:
                results = local_number_search(number, words)
        if wants_ex:  # cards that really are "ex" first, the rest (like "Absol" 96/95) after
            results.sort(key=lambda r: 0 if re.search(r"(^|[\s-])ex\b", (r["name"] or "").lower()) else 1)
        return {"results": results, "total": len(results), "next_cursor": next_cursor,
                "searched": {"name": " ".join(name_words), "sets": set_slugs, "number": number}}
    except Exception:
        return {"error": server_error("poketrace_search")}, 500


@app.route("/public-card/<path:poketrace_id>")
@limiter.limit("30 per minute;600 per day")
def public_card(poketrace_id):
    """View any card's price + history straight from PokeTrace. No login needed.
    Logged-out visitors get only the last 30 days of history."""
    if not valid_poketrace_id(poketrace_id):
        return {"error": "Card not found"}, 404
    POKETRACE_API_KEY = os.getenv("POKETRACE_API_KEY")
    if not POKETRACE_API_KEY:
        return {"error": "PokeTrace API key not configured"}, 500

    try:
        from datetime import datetime, timedelta

        status, detail = poketrace_get(f"/cards/{poketrace_id}", timeout=10)
        if status != 200:
            return {"error": f"PokeTrace returned {status}"}, 500
        card = detail.get("data")
        if not card:
            return {"error": "Card not found"}, 404

        name = card.get("name", "Unknown")
        set_name = (card.get("set") or {}).get("name", "Unknown")
        image_url = card.get("image") or ""
        prices = card.get("prices", {}) or {}
        nm = (prices.get("tcgplayer", {}) or {}).get("NEAR_MINT") or {}
        current_price = nm.get("avg")

        h_status, h_data = poketrace_get(f"/cards/{poketrace_id}/prices/NEAR_MINT/history",
                                         params={"period": "all", "limit": 365})
        history = []
        if h_status == 200:
            raw = h_data.get("data", []) or []
            tcg_only = {}
            for point in raw:
                if point.get("source") != "tcgplayer":
                    continue
                date_str = point.get("date")
                price_val = point.get("median7d") or point.get("avg") or point.get("low") or point.get("high")
                if date_str and price_val is not None:
                    tcg_only[date_str] = {"price": float(price_val), "recorded_at": date_str + "T00:00:00"}
            history = sorted(tcg_only.values(), key=lambda x: x["recorded_at"])

        if not current_user.is_authenticated:
            cutoff = (datetime.now() - timedelta(days=30)).isoformat()
            history = [pt for pt in history if pt["recorded_at"] >= cutoff]

        return {
            "poketrace_id": poketrace_id,
            "name": name,
            "set_name": set_name,
            "image_url": image_url,
            "current_price": current_price,
            "history": history,
            "is_limited": not current_user.is_authenticated,
        }
    except Exception:
        return {"error": server_error("public_card")}, 500


@app.route("/save-card-poketrace/<path:poketrace_id>")
@login_required
def save_card_poketrace(poketrace_id):
    """Save a card using its PokeTrace ID. Pulls card detail + full price history."""
    if not valid_poketrace_id(poketrace_id):
        return {"error": "Card not found"}, 404
    # ?watchlist=0 means track the card but keep it off the watchlist (used by trades)
    on_watchlist = 0 if request.args.get("watchlist") == "0" else 1
    POKETRACE_API_KEY = os.getenv("POKETRACE_API_KEY")
    if not POKETRACE_API_KEY:
        return {"error": "PokeTrace API key not configured"}, 500
    
    try:
        import json as json_mod
        headers = {"X-API-Key": POKETRACE_API_KEY}
        
        # 1. Fetch card detail
        detail_url = f"https://api.poketrace.com/v1/cards/{poketrace_id}"
        r = requests.get(detail_url, headers=headers, timeout=10)
        if r.status_code != 200:
            return {"error": f"PokeTrace card lookup returned {r.status_code}"}, 500
        
        card = r.json().get("data")
        if not card:
            return {"error": "Card not found"}, 404
        
        name = card.get("name", "Unknown")
        set_name = (card.get("set") or {}).get("name", "Unknown")
        card_number = card.get("cardNumber") or ""
        image_url = card.get("image") or ""
        
        # Pull current price from tcgplayer NEAR_MINT (configurable later)
        prices = card.get("prices", {}) or {}
        tcg_prices = prices.get("tcgplayer", {}) or {}
        nm = tcg_prices.get("NEAR_MINT") or {}
        current_price = nm.get("avg")
        
        # Build stats from the card detail
        stats = {
            "tcgplayer_NM_avg1d": nm.get("avg1d"),
            "tcgplayer_NM_avg7d": nm.get("avg7d"),
            "tcgplayer_NM_avg30d": nm.get("avg30d"),
            "tcgplayer_NM_saleCount": nm.get("saleCount"),
            "topPrice": card.get("topPrice"),
            "totalSaleCount": card.get("totalSaleCount"),
            "hasGraded": card.get("hasGraded"),
            "lastUpdated": card.get("lastUpdated"),
            "tier": "NEAR_MINT",
            "source": "tcgplayer",
        }
        
        # 2. Fetch FULL price history (period=all, limit=365)
        hist_url = f"https://api.poketrace.com/v1/cards/{poketrace_id}/prices/NEAR_MINT/history"
        h = requests.get(hist_url, headers=headers, params={"period": "all", "limit": 365}, timeout=15)
        history_points = []
        if h.status_code == 200:
            history_points = h.json().get("data", []) or []
            print(f"[POKETRACE SAVE] {name}: fetched {len(history_points)} history points")
        else:
            print(f"[POKETRACE SAVE] {name}: history fetch returned {h.status_code}")
        
       # 3. Save to database
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        # If this user already has this exact card, reuse it (no duplicate).
        # Refresh its history/stats/price instead of inserting a new row.
        cursor.execute(
            "SELECT id FROM products WHERE user_id = %s AND poketrace_id = %s LIMIT 1",
            (current_user.id, poketrace_id)
        )
        existing = cursor.fetchone()
        if existing:
            product_id = existing[0]
            cursor.execute(
                "UPDATE products SET poketrace_history = %s, poketrace_stats = %s, image_url = %s WHERE id = %s",
                (json_mod.dumps(history_points), json_mod.dumps(stats), image_url, product_id)
            )
            if on_watchlist:
                # A card saved earlier for the collection or a trade (watchlist=0) joins the watchlist now.
                # (watchlist=0 never takes a card OFF the watchlist.)
                cursor.execute("UPDATE products SET on_watchlist = 1 WHERE id = %s", (product_id,))
            if current_price:
                cursor.execute(
                    "INSERT INTO price_history (product_id, price) VALUES (%s, %s)",
                    (product_id, current_price)
                )
            conn.commit()
            cursor.close()
            conn.close()
            return {
                "success": True,
                "product_id": product_id,
                "name": name,
                "set_name": set_name,
                "card_number": card_number,
                "price": current_price,
                "history_points": len(history_points),
                "image_url": image_url,
                "already_existed": True,
            }

        cursor.execute(
            """INSERT INTO products
            (user_id, on_watchlist, name, type, set_name, card_number, poketrace_id, poketrace_history, poketrace_stats, image_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (current_user.id, on_watchlist, name, "card", set_name, card_number, poketrace_id,
             json_mod.dumps(history_points), json_mod.dumps(stats), image_url)
        )
        product_id = cursor.lastrowid
        
        # Seed local price_history table with current price (keeps legacy code working)
        if current_price:
            cursor.execute(
                "INSERT INTO price_history (product_id, price) VALUES (%s, %s)",
                (product_id, current_price)
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return {
            "success": True,
            "product_id": product_id,
            "name": name,
            "set_name": set_name,
            "card_number": card_number,
            "price": current_price,
            "history_points": len(history_points),
            "image_url": image_url,
        }
    except Exception:
        return {"error": server_error("save_card_poketrace")}, 500
# ============================================================
# Authentication routes
# ============================================================

# Open signup (no invite code since 2026-10-24). Bots are slowed by the per-IP limit below and
# caught by a honeypot: a "website" field that people never see, so only a bot fills it in.
USERNAME_MAX = 30
PASSWORD_MAX_BYTES = 72  # bcrypt only uses the first 72 bytes, and bcrypt 5 refuses anything longer


def password_too_long(password):
    return len(password.encode("utf-8")) > PASSWORD_MAX_BYTES


@app.route("/signup", methods=["POST"])
@limiter.limit("3 per hour")
def signup():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    # Honeypot: a real person can't see or tab to this field. Answer like any failed signup, without
    # saying why, so a bot learns nothing; log it so we can see how often it happens.
    if (data.get("website") or "").strip():
        app.logger.warning("signup honeypot filled")
        return {"error": "Signup failed. Please try again."}, 400

    # Validate inputs
    if not username or not email or not password:
        return {"error": "All fields are required"}, 400
    if len(username) < 3 or len(username) > USERNAME_MAX:
        return {"error": f"Username must be 3 to {USERNAME_MAX} characters"}, 400
    if "@" not in email or "." not in email.split("@")[-1] or len(email) > 254:
        return {"error": "Enter a valid email address"}, 400
    if len(password) < 8:
        return {"error": "Password must be at least 8 characters"}, 400
    if password_too_long(password):
        return {"error": "Password is too long (72 characters at most)"}, 400

    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    try:
        # Check username/email not taken
        cursor.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
        if cursor.fetchone():
            return {"error": "Username or email already in use"}, 400

        # Hash password and create user
        pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        try:
            cursor.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
                (username, email, pw_hash)
            )
        except mysql.connector.IntegrityError:
            # Two signups with the same name at the same moment: the second one lands here
            conn.rollback()
            return {"error": "Username or email already in use"}, 400
        new_user_id = cursor.lastrowid
        conn.commit()

        # Log them in immediately
        user = User(new_user_id, username, email)
        session.permanent = True  # 30-day login (see PERMANENT_SESSION_LIFETIME)
        login_user(user)
        return {"success": True, "user": {"id": new_user_id, "username": username, "email": email}}
    except Exception:
        conn.rollback()
        return {"error": server_error("signup")}, 500
    finally:
        cursor.close()
        conn.close()


def login_username_key():
    data = request.get_json(silent=True) or {}
    return "login-user:" + str(data.get("username") or "").strip().lower()


@app.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
# Per-username cap that only counts failed logins, so one account can't be guessed slowly from many IPs
@limiter.limit("10 per 15 minutes", key_func=login_username_key, deduct_when=lambda r: r.status_code == 401)
def login():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return {"error": "Username and password required"}, 400
    if password_too_long(password):
        # No real password is this long (signup refuses them), and bcrypt 5 would crash on it
        return {"error": "Invalid username or password"}, 401

    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, username, email, password_hash FROM users WHERE username = %s",
            (username,)
        )
        row = cursor.fetchone()
        # Constant-ish behavior whether or not the user exists
        if not row or not bcrypt.checkpw(password.encode("utf-8"), row["password_hash"].encode("utf-8")):
            app.logger.warning("login failed")  # counted by agents/ops_report.py; no username logged
            return {"error": "Invalid username or password"}, 401

        user = User(row["id"], row["username"], row["email"])
        session.permanent = True  # 30-day login (see PERMANENT_SESSION_LIFETIME)
        login_user(user)
        return {"success": True, "user": {"id": row["id"], "username": row["username"], "email": row["email"]}}
    finally:
        cursor.close()
        conn.close()


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.clear()  # nothing left in the session, so Flask deletes the cookie instead of re-sending it
    return {"success": True}


# ============================================================
# Trade logging routes
# ============================================================

def _current_price(cursor, product_id):
    """Get a card's latest price from price_history. Returns float or None."""
    if not product_id:
        return None
    cursor.execute(
        "SELECT price FROM price_history WHERE product_id = %s ORDER BY recorded_at DESC LIMIT 1",
        (product_id,)
    )
    row = cursor.fetchone()
    if row:
        # row may be a dict or tuple depending on cursor type
        return float(row["price"]) if isinstance(row, dict) else float(row[0])
    return None
@app.route("/log-trade", methods=["POST"])
@login_required
def log_trade():
    data = request.get_json() or {}
    from datetime import date

    trade_date = data.get("trade_date") or str(date.today())
    cash_amount = float(data.get("cash_amount") or 0)
    cash_direction = data.get("cash_direction") or "none"
    notes = (data.get("notes") or "").strip()

    gave_items = data.get("gave") or []
    got_items = data.get("got") or []

    if not gave_items or not got_items:
        return {"success": False, "error": "Add at least one card on each side"}, 400

    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """INSERT INTO trades
            (user_id, trade_date, cash_amount, cash_direction, notes)
            VALUES (%s, %s, %s, %s, %s)""",
            (current_user.id, trade_date, cash_amount, cash_direction, notes)
        )
        trade_id = cursor.lastrowid

        def add_item(side, item):
            pid = item.get("product_id") or None
            name = (item.get("name") or "").strip()
            val = item.get("agreed_value")
            val = float(val) if val not in (None, "") else None
            cursor.execute(
                "INSERT INTO trade_items (trade_id, side, product_id, card_name, agreed_value) VALUES (%s, %s, %s, %s, %s)",
                (trade_id, side, pid, name, val)
            )
            return pid, val

        for item in gave_items:
            pid, val = add_item("gave", item)
            if pid:
                cursor.execute(
                    "SELECT id, quantity FROM collection WHERE product_id = %s AND user_id = %s ORDER BY date_added ASC LIMIT 1",
                    (pid, current_user.id)
                )
                row = cursor.fetchone()
                if row:
                    if row["quantity"] and row["quantity"] > 1:
                        cursor.execute("UPDATE collection SET quantity = quantity - 1 WHERE id = %s", (row["id"],))
                    else:
                        cursor.execute("DELETE FROM collection WHERE id = %s", (row["id"],))

        for item in got_items:
            pid, val = add_item("got", item)
            if pid:
                cursor.execute(
                    "SELECT id, quantity FROM collection WHERE product_id = %s AND user_id = %s LIMIT 1",
                    (pid, current_user.id)
                )
                row = cursor.fetchone()
                if row:
                    cursor.execute("UPDATE collection SET quantity = quantity + 1 WHERE id = %s", (row["id"],))
                else:
                    cursor.execute(
                        "INSERT INTO collection (user_id, product_id, quantity, price_paid, priority) VALUES (%s, %s, %s, %s, %s)",
                        (current_user.id, pid, 1, val or 0, "normal")
                    )

        conn.commit()
        return {"success": True, "trade_id": trade_id}
    except Exception:
        conn.rollback()
        return {"success": False, "error": server_error("log_trade")}, 500
    finally:
        cursor.close()
        conn.close()


@app.route("/trades")
@login_required
def get_trades():
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM trades WHERE user_id = %s ORDER BY trade_date DESC, id DESC",
            (current_user.id,)
        )
        trades = cursor.fetchall()
        result = []
        for t in trades:
            cash = float(t["cash_amount"] or 0)
            direction = t["cash_direction"] or "none"

            cursor.execute(
                "SELECT side, product_id, card_name, agreed_value FROM trade_items WHERE trade_id = %s",
                (t["id"],)
            )
            items = cursor.fetchall()

            gave_cards = []
            got_cards = []
            gave_market_total = 0.0
            got_market_total = 0.0
            gave_has_price = False
            got_has_price = False

            for it in items:
                market = _current_price(cursor, it["product_id"])
                agreed = float(it["agreed_value"]) if it["agreed_value"] is not None else None
                card = {
                    "name": it["card_name"],
                    "agreed": agreed,
                    "market_now": market,
                }
                if it["side"] == "gave":
                    gave_cards.append(card)
                    if market is not None:
                        gave_market_total += market
                        gave_has_price = True
                else:
                    got_cards.append(card)
                    if market is not None:
                        got_market_total += market
                        got_has_price = True

            net_now = None
            pct_now = None
            if gave_has_price and got_has_price:
                gave_total = gave_market_total + (cash if direction == "paid" else 0)
                got_total = got_market_total + (cash if direction == "received" else 0)
                net_now = round(got_total - gave_total, 2)
                if gave_total > 0:
                    pct_now = round((net_now / gave_total) * 100, 1)

            result.append({
                "id": t["id"],
                "trade_date": t["trade_date"].isoformat() if hasattr(t["trade_date"], "isoformat") else t["trade_date"],
                "gave_cards": gave_cards,
                "got_cards": got_cards,
                "gave_market_total": round(gave_market_total, 2) if gave_has_price else None,
                "got_market_total": round(got_market_total, 2) if got_has_price else None,
                "cash_amount": cash,
                "cash_direction": direction,
                "notes": t["notes"],
                "net_now": net_now,
                "pct_now": pct_now,
            })

        return {"trades": result}
    except Exception:
        return {"error": server_error("get_trades")}, 500
    finally:
        cursor.close()
        conn.close()



@app.route("/delete-trade/<int:trade_id>", methods=["DELETE"])
@login_required
def delete_trade(trade_id):
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM trades WHERE id = %s AND user_id = %s", (trade_id, current_user.id))
        conn.commit()
        return {"success": True}
    except Exception:
        return {"success": False, "error": server_error("delete_trade")}, 500
    finally:
        cursor.close()
        conn.close()
@app.route("/me")
def me():
    if current_user.is_authenticated:
        return {"user": {"id": current_user.id, "username": current_user.username, "email": current_user.email}}
    return {"user": None}
# ============================================================
# Share link routes
# ============================================================

@app.route("/create-share", methods=["POST"])
@login_required
def create_share():
    import secrets
    from datetime import datetime, timedelta
    data = request.get_json() or {}
    duration = data.get("duration", "24h")  # '1h', '12h', '24h', 'infinite'
    label = (data.get("label") or "").strip() or None

    # Work out when it expires
    hours_map = {"1h": 1, "12h": 12, "24h": 24}
    if duration == "infinite":
        expires_at = None
    else:
        hrs = hours_map.get(duration, 24)
        expires_at = datetime.now() + timedelta(hours=hrs)

    token = secrets.token_urlsafe(24)  # unguessable random code

    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO share_links (token, owner_id, label, expires_at) VALUES (%s, %s, %s, %s)",
            (token, current_user.id, label, expires_at)
        )
        conn.commit()
        return {"success": True, "token": token}
    except Exception:
        return {"success": False, "error": server_error("create_share")}, 500
    finally:
        cursor.close()
        conn.close()


@app.route("/my-shares")
@login_required
def my_shares():
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, token, label, expires_at, active, created_at FROM share_links WHERE owner_id = %s ORDER BY created_at DESC",
            (current_user.id,)
        )
        rows = cursor.fetchall()
        shares = []
        for r in rows:
            shares.append({
                "id": r["id"],
                "token": r["token"],
                "label": r["label"],
                "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
                "active": bool(r["active"]),
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            })
        return {"shares": shares}
    finally:
        cursor.close()
        conn.close()


@app.route("/revoke-share/<int:share_id>", methods=["POST"])
@login_required
def revoke_share(share_id):
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE share_links SET active = 0 WHERE id = %s AND owner_id = %s",
            (share_id, current_user.id)
        )
        conn.commit()
        return {"success": True}
    finally:
        cursor.close()
        conn.close()


@app.route("/shared/<token>")
@login_required
def view_shared(token):
    from datetime import datetime
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Find the link
        cursor.execute("SELECT * FROM share_links WHERE token = %s", (token,))
        link = cursor.fetchone()
        if not link or not link["active"]:
            return {"error": "This share link is invalid or was turned off."}, 404

        # 2. Check expiry
        if link["expires_at"] is not None and link["expires_at"] < datetime.now():
            return {"error": "This share link has expired."}, 410

        owner_id = link["owner_id"]

        # Record that this viewer has access (skip if owner views their own link)
        if current_user.id != owner_id:
            cursor.execute(
                "INSERT IGNORE INTO share_access (share_link_id, viewer_id) VALUES (%s, %s)",
                (link["id"], current_user.id)
            )
            conn.commit()

        # 3. Owner's username
        cursor.execute("SELECT username FROM users WHERE id = %s", (owner_id,))
        owner = cursor.fetchone()
        owner_name = owner["username"] if owner else "Unknown"

        # 4. Owner's collection
        cursor.execute("""
            SELECT c.quantity, c.price_paid, p.name, p.set_name, p.image_url,
                   (SELECT price FROM price_history WHERE product_id = p.id ORDER BY recorded_at DESC LIMIT 1) AS current_price
            FROM collection c
            JOIN products p ON c.product_id = p.id
            WHERE c.user_id = %s
            ORDER BY c.date_added DESC
        """, (owner_id,))
        collection = cursor.fetchall()
        nullable = paid_nullable(cursor)
        for item in collection:
            item["price_paid"] = known_paid(item.get("price_paid"), nullable)
            if item.get("current_price") is not None:
                item["current_price"] = float(item["current_price"])

        # 5. Owner's trades
        cursor.execute(
            "SELECT * FROM trades WHERE user_id = %s ORDER BY trade_date DESC, id DESC",
            (owner_id,)
        )
        trade_rows = cursor.fetchall()
        trades = []
        for t in trade_rows:
            cursor.execute(
                "SELECT side, card_name, agreed_value FROM trade_items WHERE trade_id = %s",
                (t["id"],)
            )
            items = cursor.fetchall()
            gave = [{"name": it["card_name"], "agreed": float(it["agreed_value"]) if it["agreed_value"] is not None else None} for it in items if it["side"] == "gave"]
            got = [{"name": it["card_name"], "agreed": float(it["agreed_value"]) if it["agreed_value"] is not None else None} for it in items if it["side"] == "got"]
            trades.append({
                "id": t["id"],
                "trade_date": t["trade_date"].isoformat() if hasattr(t["trade_date"], "isoformat") else t["trade_date"],
                "gave_cards": gave,
                "got_cards": got,
                "cash_amount": float(t["cash_amount"] or 0),
                "cash_direction": t["cash_direction"] or "none",
                "notes": t["notes"],
            })

        return {
            "owner_name": owner_name,
            "expires_at": link["expires_at"].isoformat() if link["expires_at"] else None,
            "collection": collection,
            "trades": trades,
        }
    except Exception:
        return {"error": server_error("view_shared")}, 500
    finally:
        cursor.close()
        conn.close()


@app.route("/shared-with-me")
@login_required
def shared_with_me():
    """List everyone who has shared their collection with me (via links I've opened)."""
    from datetime import datetime
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT sl.token, sl.label, sl.expires_at, u.username AS owner_name
            FROM share_access sa
            JOIN share_links sl ON sa.share_link_id = sl.id
            JOIN users u ON sl.owner_id = u.id
            WHERE sa.viewer_id = %s AND sl.active = 1
            ORDER BY sa.first_opened DESC
        """, (current_user.id,))
        rows = cursor.fetchall()
        shares = []
        for r in rows:
            if r["expires_at"] is not None and r["expires_at"] < datetime.now():
                continue
            shares.append({
                "token": r["token"],
                "owner_name": r["owner_name"],
                "label": r["label"],
                "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
            })
        return {"shares": shares}
    except Exception:
        return {"error": server_error("shared_with_me")}, 500
    finally:
        cursor.close()
        conn.close()


# ============================================================
# Discovery — global market movers
# ============================================================

def table_exists(cursor, name):
    cursor.execute("SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s",
                   (name,))
    row = cursor.fetchone()
    return bool(row) and (row["n"] if isinstance(row, dict) else row[0]) > 0


def column_exists(cursor, table, column):
    cursor.execute("SELECT COUNT(*) AS n FROM information_schema.columns WHERE table_schema = DATABASE() "
                   "AND table_name = %s AND column_name = %s", (table, column))
    row = cursor.fetchone()
    return bool(row) and (row["n"] if isinstance(row, dict) else row[0]) > 0


# Movers and the set list skip market_cards rows the nightly sweep hasn't refreshed in this many days.
# A row stops being refreshed when PokeTrace renames its set (the sweep asks for the old name and the card
# isn't returned), and its prices then freeze while still looking current.
MARKET_FRESH_DAYS = 7
# The home page's set section. A slug here = show that set as "Featured set" (our pick, not a claim that it's
# the newest). "" = pick the newest dated English set instead (needs release dates from PokeTrace, which it
# doesn't send yet). Change this one line, then deploy.
FEATURED_SET = "me-30th-celebration-classic-collection"


@app.route("/market-sets")
def market_sets():
    """Sets that have enough ranked cards to be worth filtering by."""
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT set_slug, MAX(set_name) AS set_name, COUNT(*) AS card_count
            FROM market_cards
            WHERE avg30d >= 10 AND sale_count >= 50 AND last_synced >= NOW() - INTERVAL %s DAY
            GROUP BY set_slug
            HAVING card_count >= 3
            ORDER BY set_name ASC
        """, (MARKET_FRESH_DAYS,))
        return {"sets": cursor.fetchall()}
    except Exception:
        return {"error": server_error("market_sets")}, 500
    finally:
        cursor.close()
        conn.close()


@app.route("/new-set")
def new_set():
    """The home page's set section: its cards by price (high to low).
    FEATURED_SET set -> that set, labeled as our pick ("featured": true, no release date claimed).
    Otherwise the newest English set by PokeTrace's release date (tracked_sets.release_date, migration 005);
    English = none of its cards is a "(Japanese)" card. Nothing to show -> {"set": null, "reason": ...}."""
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    try:
        if FEATURED_SET:
            cursor.execute("SELECT MAX(set_name) AS name FROM market_cards WHERE set_slug = %s", (FEATURED_SET,))
            row = cursor.fetchone()
            found = {"slug": FEATURED_SET, "name": row["name"] if row else None, "release_date": None}
        else:
            if not column_exists(cursor, "tracked_sets", "release_date"):
                return {"set": None, "cards": [], "reason": "no release dates yet"}
            cursor.execute("""
                SELECT t.slug, t.name, t.release_date FROM tracked_sets t
                WHERE t.active = 1 AND t.release_date IS NOT NULL
                  AND EXISTS (SELECT 1 FROM market_cards m WHERE m.set_slug = t.slug AND m.avg1d IS NOT NULL
                              AND m.last_synced >= NOW() - INTERVAL %s DAY)
                  AND NOT EXISTS (SELECT 1 FROM market_cards j WHERE j.set_slug = t.slug AND j.name LIKE %s)
                ORDER BY t.release_date DESC LIMIT 1
            """, (MARKET_FRESH_DAYS, "%(Japanese)%"))
            found = cursor.fetchone()
            if not found:
                return {"set": None, "cards": [], "reason": "no dated English set with prices yet"}
        cursor.execute("""
            SELECT poketrace_id, name, set_name, card_number, rarity, image_url, avg1d, sale_count
            FROM market_cards WHERE set_slug = %s AND avg1d IS NOT NULL AND last_synced >= NOW() - INTERVAL %s DAY
            ORDER BY avg1d DESC LIMIT 12
        """, (found["slug"], MARKET_FRESH_DAYS))
        cards = [{"poketrace_id": r["poketrace_id"], "name": r["name"], "set_name": r["set_name"],
                  "card_number": r["card_number"], "rarity": r["rarity"], "image_url": r["image_url"],
                  "price": float(r["avg1d"]), "sale_count": r["sale_count"]} for r in cursor.fetchall()]
        if not cards:
            # e.g. the featured set isn't tracked yet: add it with load_all_sets.py, then wait for the 3 AM sweep
            return {"set": None, "cards": [], "reason": f"no priced cards yet for {found['slug']}"}
        released = found["release_date"]
        return {"set": {"slug": found["slug"], "name": found["name"] or cards[0]["set_name"],
                        "release_date": released.isoformat() if released else None,
                        "featured": bool(FEATURED_SET)},
                "cards": cards}
    except Exception:
        return {"error": server_error("new_set")}, 500
    finally:
        cursor.close()
        conn.close()


@app.route("/discovery")
def discovery():
    """Top gainers, losers, most-traded. Public market data.
    Query params: ?set=<slug>&window=7d|30d"""
    set_slug = request.args.get("set") or None
    window = request.args.get("window", "30d")
    pct_col = "pct_7d" if window == "7d" else "pct_30d"

    MIN_PRICE = 10
    MIN_SALES = 50
    LIMIT = 10

    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    try:
        where = """
            WHERE avg1d IS NOT NULL AND avg30d IS NOT NULL AND avg7d IS NOT NULL
              AND avg30d >= %s AND sale_count >= %s
              AND last_synced >= NOW() - INTERVAL %s DAY
        """
        params = [MIN_PRICE, MIN_SALES, MARKET_FRESH_DAYS]
        if set_slug:
            where += " AND set_slug = %s"
            params.append(set_slug)

        base = """
            SELECT poketrace_id, name, set_name, set_slug, card_number, rarity, image_url,
                   avg1d, avg7d, avg30d, sale_count,
                   ROUND(((avg1d - avg30d) / avg30d) * 100, 1) AS pct_30d,
                   ROUND(((avg1d - avg7d) / avg7d) * 100, 1) AS pct_7d
            FROM market_cards
        """ + where

        cursor.execute(base + f" ORDER BY {pct_col} DESC LIMIT %s", params + [LIMIT])
        gainers = cursor.fetchall()

        cursor.execute(base + f" ORDER BY {pct_col} ASC LIMIT %s", params + [LIMIT])
        losers = cursor.fetchall()

        # "Most sold": PokeTrace's sale_count is a lifetime total, so the last 30 days come from the
        # daily snapshots the sweep keeps (migration 006): today's count minus the oldest one in the window.
        # No snapshots yet -> rank by lifetime sales and say so (volume_window_days = None).
        volume_days = None
        if table_exists(cursor, "market_card_sales_daily"):
            cursor.execute("SELECT MIN(day) AS d, DATEDIFF(CURDATE(), MIN(day)) AS n FROM market_card_sales_daily "
                           "WHERE day >= CURDATE() - INTERVAL 30 DAY")
            snap = cursor.fetchone()
            if snap and snap["d"] and snap["n"] >= 1:
                volume_days = int(snap["n"])
                cursor.execute(
                    "SELECT b.*, b.sale_count - s.sale_count AS sold_window FROM (" + base + ") b "
                    "JOIN market_card_sales_daily s ON s.poketrace_id = b.poketrace_id AND s.day = %s "
                    "WHERE b.sale_count - s.sale_count > 0 ORDER BY sold_window DESC LIMIT %s",
                    params + [snap["d"], LIMIT])
                volume = cursor.fetchall()
        if volume_days is None:
            cursor.execute(base + " ORDER BY sale_count DESC LIMIT %s", params + [LIMIT])
            volume = cursor.fetchall()

        def clean(rows):
            out = []
            for r in rows:
                out.append({
                    "poketrace_id": r["poketrace_id"],
                    "name": r["name"],
                    "set_name": r["set_name"],
                    "set_slug": r["set_slug"],
                    "card_number": r["card_number"],
                    "rarity": r["rarity"],
                    "image_url": r["image_url"],
                    "price": float(r["avg1d"]) if r["avg1d"] is not None else None,
                    "pct_30d": float(r["pct_30d"]) if r["pct_30d"] is not None else None,
                    "pct_7d": float(r["pct_7d"]) if r["pct_7d"] is not None else None,
                    "sale_count": r["sale_count"],
                    "sold_window": int(r["sold_window"]) if r.get("sold_window") is not None else None,
                })
            return out

        meta_sql = "SELECT MAX(last_synced) AS synced, COUNT(*) AS total FROM market_cards"
        if set_slug:
            cursor.execute(meta_sql + " WHERE set_slug = %s", (set_slug,))
        else:
            cursor.execute(meta_sql)
        meta = cursor.fetchone()

        return {
            "gainers": clean(gainers),
            "losers": clean(losers),
            "volume": clean(volume),
            "window": window,
            "volume_window_days": volume_days,
            "set": set_slug,
            "last_synced": meta["synced"].isoformat() if meta["synced"] else None,
            "cards_tracked": meta["total"],
        }
    except Exception:
        return {"error": server_error("discovery")}, 500
    finally:
        cursor.close()
        conn.close()


@app.route("/share-viewers/<int:share_id>")
@login_required
def share_viewers(share_id):
    """Who has opened one of MY share links. Shows first 10."""
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    try:
        # Confirm this link belongs to the person asking
        cursor.execute(
            "SELECT id FROM share_links WHERE id = %s AND owner_id = %s",
            (share_id, current_user.id)
        )
        if not cursor.fetchone():
            return {"error": "Not found"}, 404

        cursor.execute("""
            SELECT u.username, sa.first_opened
            FROM share_access sa
            JOIN users u ON sa.viewer_id = u.id
            WHERE sa.share_link_id = %s
            ORDER BY sa.first_opened DESC
            LIMIT 10
        """, (share_id,))
        rows = cursor.fetchall()

        cursor.execute(
            "SELECT COUNT(*) AS n FROM share_access WHERE share_link_id = %s",
            (share_id,)
        )
        total = cursor.fetchone()["n"]

        viewers = [{
            "username": r["username"],
            "first_opened": r["first_opened"].isoformat() if r["first_opened"] else None,
        } for r in rows]

        return {"viewers": viewers, "total": total}
    except Exception:
        return {"error": server_error("share_viewers")}, 500
    finally:
        cursor.close()
        conn.close()


# ---- Honest condition prices ----
# The card page shows, for each condition: TCGplayer's price, how many TCGplayer sales backed it in the
# last 30 days, and a status. PokeTrace's own saleCount is a LIFETIME total, so it can't tell a busy card
# from one that last sold a year ago; the 30-day count comes from each condition's daily history.
#   ok    10+ TCGplayer sales in 30 days
#   low   1-9 sales: price shown, marked "Low data"
#   none  0 sales: TCGplayer keeps re-publishing its last price every day, so we show "No recent sales"
#         instead of that carried-forward number. We never make up a price.
# That's 6 PokeTrace requests per card (1 detail + 5 histories), so the result is kept for 6 hours in a
# small file per card, shared by all gunicorn workers and kept across restarts.
CONDITION_KEYS = ["NEAR_MINT", "LIGHTLY_PLAYED", "MODERATELY_PLAYED", "HEAVILY_PLAYED", "DAMAGED"]
PRICE_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "card-prices")
PRICE_CACHE_SECONDS = 6 * 3600
PRICE_CACHE_VERSION = 3   # bump when the cached summary's shape changes
PRICE_CACHE_SHORT = 30 * 60   # a summary made without sale counts (budget guard) is retried sooner
LOW_DATA_SALES = 10
SALES_WINDOW_DAYS = 30
PT_RESERVE = 1500             # below this many PokeTrace requests left today, skip the 5 history calls


SOURCE_LABELS = {"tcgplayer": "TCGplayer", "ebay": "eBay"}
SOURCE_ORDER = ["tcgplayer", "ebay"]   # which site's price we show first when both have recent sales


def condition_summary(detail, histories, today):
    """detail: PokeTrace /cards/<id> data. histories: {condition: [daily points, newest first]} or {} when
    the history calls were skipped (budget guard). Returns {condition: {...}}.

    The shown price comes from the first site in SOURCE_ORDER that had a sale in the last 30 days, and is
    always labelled with that site. A site's price with no sale behind it in 30 days is a carried-forward
    number (TCGplayer kept Absol 96/95's Near mint at $164.98 from June to October), so it's never shown."""
    cutoff = (today - timedelta(days=SALES_WINDOW_DAYS)).isoformat()
    prices = detail.get("prices") or {}
    out = {}
    for cond in CONDITION_KEYS:
        points = histories.get(cond)
        if points is None:
            # Counts unavailable (budget guard): show TCGplayer's price, status unknown, unless PokeTrace says
            # it hasn't been refreshed in 30+ days. (A price can be refreshed daily with no sales behind it;
            # without the history we can't see that, which is why the page says "sale count unavailable".)
            tcg = (prices.get("tcgplayer") or {}).get(cond) or {}
            fresh = (tcg.get("lastUpdated") or "")[:10] >= cutoff
            out[cond] = {"price": tcg.get("avg") if fresh else None,
                         "source": "TCGplayer" if fresh and tcg.get("avg") is not None else None,
                         "status": None if fresh else "none", "sales_30d": None, "sales_30d_by_source": {},
                         "last_sale": None, "history_from": None, "sales": []}
            continue

        with_sales = [p for p in points if (p.get("saleCount") or 0) > 0]
        by_source = {}
        for p in with_sales:
            if (p.get("date") or "") >= cutoff:
                by_source[p.get("source")] = by_source.get(p.get("source"), 0) + p["saleCount"]

        source = next((src for src in SOURCE_ORDER
                       if by_source.get(src) and ((prices.get(src) or {}).get(cond) or {}).get("avg") is not None), None)
        n = by_source.get(source, 0) if source else 0
        last = with_sales[0] if with_sales else None  # history is newest first
        out[cond] = {
            "price": ((prices.get(source) or {}).get(cond) or {}).get("avg") if source else None,
            "source": SOURCE_LABELS.get(source, source),
            "status": "none" if not source else ("ok" if n >= LOW_DATA_SALES else "low"),
            "sales_30d": n,
            "sales_30d_by_source": {SOURCE_LABELS.get(k, k): v for k, v in by_source.items()},
            # The most recent real sale on any site: low/high are actual sale prices ("avg" is smoothed)
            "last_sale": {"date": last.get("date"), "source": SOURCE_LABELS.get(last.get("source"), last.get("source")),
                          "low": last.get("low"), "high": last.get("high"), "count": last.get("saleCount")} if last else None,
            # How far back the history we fetched goes, so "no sale since at least <date>" can be said honestly
            "history_from": points[-1].get("date") if points else None,
            "sales": [{"date": p.get("date"), "sale_count": p.get("saleCount"), "low": p.get("low"),
                       "high": p.get("high"), "source": p.get("source")} for p in with_sales[:10]],
        }
    return out


GRADERS = ["PSA", "CGC", "BGS", "TAG", "ACE", "SGC"]   # shown in this order; others after


def graded_summary(detail, today):
    """Graded prices (PSA 10, CGC 9.5, ...) from the card detail we already fetch: 0 extra requests.
    PokeTrace reports graded sales under eBay. For eBay, lastUpdated is the date of the last sale
    (checked against the sales history 4 times out of 4), so it's our "last sold". There is no 30-day
    count per grade without one more request per grade, so the count shown is PokeTrace's lifetime
    total (it says it's approximate). Same honesty rules as conditions: a grade with no sale in 30 days
    shows "No recent sales" (with its last sale), and fewer than 10 sales ever is "Low data"."""
    cutoff = (today - timedelta(days=SALES_WINDOW_DAYS)).isoformat()
    out = []
    for source, block in (detail.get("prices") or {}).items():
        for key, p in (block or {}).items():
            company, _, grade = key.partition("_")
            # A grade is a grading company plus a number ("PSA_10", "CGC_9_5"); "NEAR_MINT" is a condition
            if not company.isalpha() or not re.fullmatch(r"\d{1,2}(_5)?", grade) or not isinstance(p, dict) or p.get("avg") is None:
                continue
            last = (p.get("lastUpdated") or "")[:10] or None
            n = p.get("saleCount") or 0
            recent = bool(last) and last >= cutoff
            out.append({
                "key": key, "company": company, "grade": grade.replace("_", "."),
                "source": SOURCE_LABELS.get(source, source),
                "price": p["avg"] if recent else None,
                "last_sold": last, "last_price": p["avg"],
                "sales_ever": n, "approx": bool(p.get("approxSaleCount")),
                "status": "none" if not recent else ("low" if n < LOW_DATA_SALES else "ok"),
            })
    rank = {c: i for i, c in enumerate(GRADERS)}
    out.sort(key=lambda g: (rank.get(g["company"], len(GRADERS)), g["company"], -float(g["grade"])))
    return out


def _price_cache_path(poketrace_id):
    import hashlib
    # The version is part of the name, so a change to the summary's shape never reads an older file
    return os.path.join(PRICE_CACHE_DIR, f"v{PRICE_CACHE_VERSION}-" + hashlib.sha1(poketrace_id.encode()).hexdigest() + ".json")


def cached_condition_prices(poketrace_id):
    """The card's condition summary, from the 6-hour file cache or fresh from PokeTrace. None if PokeTrace fails."""
    import json
    path = _price_cache_path(poketrace_id)
    try:
        with open(path) as f:
            hit = json.load(f)
        if hit.get("expires", 0) > time.time():
            return hit
    except (OSError, ValueError):
        pass

    status, detail = poketrace_get(f"/cards/{poketrace_id}")
    if status != 200 or not detail:
        return None
    detail = detail.get("data", {}) or {}
    remaining = PT_REMAINING["value"]
    counts = remaining is None or remaining >= PT_RESERVE
    histories = {}
    if counts:
        for cond in CONDITION_KEYS:
            h_status, hist = poketrace_get(f"/cards/{poketrace_id}/prices/{cond}/history",
                                           params={"period": "all", "limit": 60})
            histories[cond] = (hist.get("data", []) or []) if h_status == 200 and hist else []
    else:
        app.logger.warning("PokeTrace budget low (%s left): condition prices without sale counts", remaining)

    from datetime import datetime, timezone
    result = {
        "conditions": condition_summary(detail, histories, datetime.now(timezone.utc).date()),
        "graded": graded_summary(detail, datetime.now(timezone.utc).date()),
        "counts_available": counts,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "expires": time.time() + (PRICE_CACHE_SECONDS if counts else PRICE_CACHE_SHORT),
    }
    try:  # write to a temp file, then rename: another worker never reads a half-written file
        os.makedirs(PRICE_CACHE_DIR, exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w") as f:
            json.dump(result, f)
        os.replace(tmp, path)
    except OSError:
        app.logger.warning("could not write the price cache")
    return result


@app.route("/card-prices/<path:poketrace_id>")
@limiter.limit("60 per minute;1000 per day")
def card_prices(poketrace_id):
    """Every condition's price with its 30-day sale count and status, plus the chosen condition's
    recent sales. Public market data. Query: ?condition=NEAR_MINT|LIGHTLY_PLAYED|..."""
    if not valid_poketrace_id(poketrace_id):
        return {"error": "Card not found"}, 404
    condition = request.args.get("condition", "NEAR_MINT")
    if condition not in CONDITION_KEYS:
        condition = "NEAR_MINT"
    try:
        data = cached_condition_prices(poketrace_id)
        if data is None:
            return {"error": "Price service is busy. Try again in a minute."}, 502
        conds = data["conditions"]
        chosen = conds[condition]
        return {
            "condition": condition,
            "price": chosen["price"],
            "prices": {c: v["price"] for c, v in conds.items()},  # older pages read this
            "sales": chosen["sales"],
            "conditions": {c: {k: v for k, v in e.items() if k != "sales"} for c, e in conds.items()},
            "graded": data.get("graded", []),
            "counts_available": data["counts_available"],
            "low_data_below": LOW_DATA_SALES,
            "window_days": SALES_WINDOW_DAYS,
            "fetched_at": data["fetched_at"],
        }
    except Exception:
        return {"error": server_error("card_prices")}, 500


if __name__ == "__main__":
    # Debug mode is controlled by .env — MUST be false in production.
    # Flask's debugger allows remote code execution if exposed publicly.
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=5050, debug=debug_mode)