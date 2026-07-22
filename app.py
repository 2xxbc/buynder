from flask import Flask, request, jsonify
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
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,                                                                
    SESSION_COOKIE_SAMESITE="Lax",                                                             
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",                        
)
                                                                                                  
CORS(app, supports_credentials=True, origins=["http://localhost:5173", "http://localhost:5180", "http://10.0.0.84:5180", "http://100.107.77.5:5180", "https://buyndermarket.com", "https://www.buyndermarket.com"])
                                                                                    
limiter = Limiter(
    get_remote_address,                        
    app=app,
    default_limits=[],                                                  
    storage_uri="memory://",
)

                           
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

def scrape_tcgplayer_price(tcgplayer_url):
    """
    Get a card's market price from TCGPlayer.
    Follows the redirect to find the product ID, then queries TCGPlayer's
    public pricing API for the actual price.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
                                                        
        response = requests.get(tcgplayer_url, headers=headers, allow_redirects=True, timeout=10)
        final_url = response.url
        
                                                                                             
        match = re.search(r"/product/(\d+)", final_url)
        if not match:
            print(f"Could not find product ID in {final_url}")
            return None
        
        product_id = match.group(1)
        
                                              
        price_url = f"https://mpapi.tcgplayer.com/v2/product/{product_id}/pricepoints"
        price_response = requests.get(price_url, headers=headers, timeout=10)
        
        if price_response.status_code != 200:
            print(f"Price API returned {price_response.status_code} for product {product_id}")
            return None
        
        price_data = price_response.json()
        
                                                                             
        for point in price_data:
            market = point.get("marketPrice")
            if market and market > 0:
                return float(market)
        
        return None
    except Exception as e:
        print(f"Scrape error: {e}")
        return None

@app.route("/")
def home():
    return "PokeMarket backend is running!"


@app.route("/test-db")
def test_db():
    try:
        conn = mysql.connector.connect(**db_config)
        conn.close()
        return "Database connected successfully!"
    except Exception as e:
        return f"Database connection failed: {e}"


@app.route("/test-api-key")
def test_api_key():
    if POKEMON_TCG_API_KEY:
        return "API key loaded successfully!"
    else:
        return "API key not found. Check your .env file."


@app.route("/test-discord")
def test_discord():
    success = send_discord_alert(
        title="PokeMarket Test Alert",
        description="If you can see this in Discord, the alert system is working.",
        color=0x00FF00
    )
    if success:
        return {"success": True, "message": "Sent! Check Discord."}
    else:
        return {"success": False, "message": "Failed. Check your .env file."}


@app.route("/search-card/<card_name>")
def search_card(card_name):
    url = "https://api.pokemontcg.io/v2/cards"
    headers = {"X-Api-Key": POKEMON_TCG_API_KEY}
    params = {
        "q": f"name:{card_name}",
        "pageSize": 50,
        "orderBy": "-set.releaseDate"
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        return data
    except Exception as e:
        return f"Error: {e}"


@app.route("/save-card/<card_id>")
def save_card(card_id):
    url = f"https://api.pokemontcg.io/v2/cards/{card_id}"
    headers = {"X-Api-Key": POKEMON_TCG_API_KEY}

    try:
        response = requests.get(url, headers=headers)
        card = response.json()["data"]

        name = card["name"]
        set_name = card["set"]["name"]
        image_url = card["images"]["large"]
        card_number = card.get("number", "")

        price = None
        if "tcgplayer" in card and "prices" in card["tcgplayer"]:
            prices = card["tcgplayer"]["prices"]
            if prices:
                first_variant = list(prices.values())[0]
                price = first_variant.get("market")

        if not price and "cardmarket" in card and "prices" in card["cardmarket"]:
            price = card["cardmarket"]["prices"].get("trendPrice")

        if not price and "tcgplayer" in card and card["tcgplayer"].get("url"):
            print(f"No API price for {name}, scraping TCGPlayer...")
            price = scrape_tcgplayer_price(card["tcgplayer"]["url"])

        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO products (name, type, set_name, card_number, image_url) VALUES (%s, %s, %s, %s, %s)",
            (name, "card", set_name, card_number, image_url)
        )
        product_id = cursor.lastrowid

        if price:
            cursor.execute(
                "INSERT INTO price_history (product_id, price) VALUES (%s, %s)",
                (product_id, price)
            )

        conn.commit()
        cursor.close()
        conn.close()

        return f"Saved '{name}' (ID: {product_id}) at ${price}"
    except Exception as e:
        return f"Error: {e}"


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
    except Exception as e:
        return f"Error: {e}"


@app.route("/delete-card/<int:product_id>", methods=["DELETE"])
@login_required
def delete_card(product_id):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

                                
        cursor.execute("SELECT user_id FROM products WHERE id = %s", (product_id,))
        owner = cursor.fetchone()
        if not owner or owner[0] != current_user.id:
            cursor.close()
            conn.close()
            return {"success": False, "error": "Not found"}, 404

        cursor.execute("DELETE FROM price_history WHERE product_id = %s", (product_id,))
        cursor.execute("DELETE FROM collection WHERE product_id = %s", (product_id,))
        cursor.execute("DELETE FROM sold WHERE product_id = %s", (product_id,))
        cursor.execute("DELETE FROM alerts WHERE product_id = %s", (product_id,))
        cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.route("/price-history/<int:product_id>")
def price_history(product_id):
    try:
        import json
        from datetime import datetime
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        
                                                                                
        cursor.execute(
            "SELECT poketrace_history, justtcg_history FROM products WHERE id = %s",
            (product_id,)
        )
        row = cursor.fetchone()
        
        history = []
        
                                                                                
        if row and row.get("poketrace_history"):
            raw = row["poketrace_history"]
            pt_history = json.loads(raw) if isinstance(raw, str) else raw
            tcg_only = {}                                         
            for point in pt_history:
                if point.get("source") != "tcgplayer":
                    continue                             
                date_str = point.get("date")
                price_val = point.get("median7d") or point.get("avg") or point.get("low") or point.get("high")
                if date_str is None or price_val is None:
                    continue
                                                                                
                tcg_only[date_str] = {
                    "price": float(price_val),
                    "recorded_at": date_str + "T00:00:00"
                }
            history = sorted(tcg_only.values(), key=lambda h: h["recorded_at"])
        
                                                                            
        if not history and row and row.get("justtcg_history"):
            raw = row["justtcg_history"]
            jt_history = json.loads(raw) if isinstance(raw, str) else raw
            for point in jt_history:
                                                               
                if point.get("p") is None or point.get("t") is None:
                    continue
                history.append({
                    "price": float(point["p"]),
                    "recorded_at": datetime.utcfromtimestamp(point["t"]).isoformat()
                })
        
                                                                   
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

                                                             
        if not current_user.is_authenticated:
            from datetime import timedelta
            cutoff = (datetime.now() - timedelta(days=30)).isoformat()
            history = [h for h in history if h.get("recorded_at", "") >= cutoff]

        return {"history": history}
    except Exception as e:
        return {"error": str(e)}, 500

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
    except Exception as e:
        return {"error": str(e)}


@app.route("/add-to-collection/<int:product_id>", methods=["POST"])
@login_required
def add_to_collection(product_id):
    data = request.get_json() or {}
    quantity = data.get("quantity", 1)
    price_paid = data.get("price_paid", 0)
    priority = data.get("priority", "normal")
    card_condition = data.get("condition", "NEAR_MINT")
    valid = {"NEAR_MINT", "LIGHTLY_PLAYED", "MODERATELY_PLAYED", "HEAVILY_PLAYED", "DAMAGED"}
    if card_condition not in valid:
        card_condition = "NEAR_MINT"
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO collection (user_id, product_id, quantity, price_paid, priority, card_condition) VALUES (%s, %s, %s, %s, %s, %s)",
            (current_user.id, product_id, quantity, price_paid, priority, card_condition)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

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
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.route("/collection")
@login_required
def get_collection():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT 
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

        total_paid = 0
        total_value = 0

        for item in items:
            qty = item["quantity"] or 1
            paid = float(item["price_paid"] or 0)
            current = float(item["current_price"] or 0)
            item["total_paid"] = paid * qty
            item["total_value"] = current * qty
            item["profit_loss"] = (current - paid) * qty
            total_paid += paid * qty
            total_value += current * qty

        cursor.close()
        conn.close()

        return {
            "items": items,
            "stats": {
                "total_paid": round(total_paid, 2),
                "total_value": round(total_value, 2),
                "unrealized_pnl": round(total_value - total_paid, 2)
            }
        }
    except Exception as e:
        return {"error": str(e)}


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
    except Exception as e:
        return {"success": False, "error": str(e)}


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
    except Exception as e:
        return {"error": str(e)}


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

        total_paid = 0
        total_value = 0
        for item in collection_items:
            qty = item["quantity"] or 1
            paid = float(item["price_paid"] or 0)
            current = float(item["current_price"] or 0)
            total_paid += paid * qty
            total_value += current * qty

        unrealized_pnl = total_value - total_paid

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
            "biggest_gainer": biggest_gainer,
            "biggest_loser": biggest_loser
        }
    except Exception as e:
        return {"error": str(e)}


@app.route("/scan-card", methods=["POST"])
def scan_card():
    from flask import request
    from PIL import ImageFilter, ImageOps, ImageEnhance

    if "image" not in request.files:
        return {"error": "No image uploaded"}, 400

    file = request.files["image"]

    try:
        image = Image.open(io.BytesIO(file.read()))

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
            return {"error": "Could not read card name", "raw_text": all_text}

        url = "https://api.pokemontcg.io/v2/cards"
        headers = {"X-Api-Key": POKEMON_TCG_API_KEY}
        params = {"q": f'name:"{card_name}"', "pageSize": 5}

        response = requests.get(url, headers=headers, params=params)
        data = response.json()

        if not data.get("data"):
            first_word = card_name.split()[0]
            params = {"q": f'name:{first_word}*', "pageSize": 5}
            response = requests.get(url, headers=headers, params=params)
            data = response.json()

        return {
            "detected_name": card_name,
            "raw_text": all_text,
            "candidates": candidates,
            "matches": data.get("data", [])
        }
    except Exception as e:
        return {"error": str(e)}

@app.route("/justtcg-search/<query>")
def justtcg_search(query):
    """Search JustTCG and return cards with their variants and prices."""
    JUSTTCG_API_KEY = os.getenv("JUSTTCG_API_KEY")
    if not JUSTTCG_API_KEY:
        return {"error": "JustTCG API key not configured"}, 500
    
    try:
        url = "https://api.justtcg.com/v1/cards"
        headers = {"X-API-Key": JUSTTCG_API_KEY}
        params = {
            "game": "pokemon",
            "q": query,
            "limit": 20
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code != 200:
            return {"error": f"JustTCG returned {response.status_code}"}, 500
        
        data = response.json()
        cards = data.get("data", [])
        
                                                                      
        results = []
        for card in cards:
            variants = card.get("variants", [])
            
                                                      
            display_price = None
            display_printing = None
            for v in variants:
                if v.get("condition") == "Near Mint" and v.get("printing") == "Holofoil":
                    display_price = v.get("price")
                    display_printing = "Holofoil"
                    break
            
            if display_price is None:
                for v in variants:
                    if v.get("condition") == "Near Mint":
                        display_price = v.get("price")
                        display_printing = v.get("printing", "Normal")
                        break
            
            results.append({
                "justtcg_id": card.get("id"),
                "set": card.get("set"),
                "name": card.get("name"),
                "set_name": card.get("set_name"),
                "number": card.get("number"),
                "rarity": card.get("rarity"),
                "tcgplayer_id": card.get("tcgplayerId"),
                "display_price": display_price,
                "display_printing": display_printing,
                "variant_count": len(variants)
            })
        
        return {"results": results, "total": len(results)}
    except Exception as e:
        return {"error": str(e)}, 500

@app.route("/save-card-justtcg/<path:justtcg_id>")
def save_card_justtcg(justtcg_id):
    """Save a card using its JustTCG ID. Fetches price + history + image."""
    JUSTTCG_API_KEY = os.getenv("JUSTTCG_API_KEY")
    if not JUSTTCG_API_KEY:
        return {"error": "JustTCG API key not configured"}, 500
    
    try:
                                                                                     
                                                         
                                                             
                                                                            
        
                                                       
                                                             
        clean_id = justtcg_id.replace("pokemon-", "", 1)
        parts = clean_id.split("-")
        
                                                                            
        rarity_endings = ["holo-rare", "rare", "common", "uncommon", "promo", "secret-rare",
                          "double-rare", "ultra-rare", "illustration-rare", "special-illustration-rare",
                          "hyper-rare", "shiny-rare", "classic-collection", "ace-spec"]
        
                                                                         
        url = "https://api.justtcg.com/v1/cards"
        headers = {"X-API-Key": JUSTTCG_API_KEY}
        
                                                                     
        set_slug = request.args.get("set", "")
        
                                                                    
                                                          
        if set_slug:
            params = {
                "game": "pokemon",
                "set": set_slug,
                "limit": 100
            }
        else:
            params = {
                "game": "pokemon",
                "q": justtcg_id.replace("pokemon-", "").replace("-", " "),
                "limit": 20
            }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code != 200:
            return {"error": f"JustTCG returned {response.status_code}"}, 500
        
        all_cards = response.json().get("data", [])
        print(f"[SAVE] Searching set='{set_slug}' for id='{justtcg_id}' — got {len(all_cards)} cards back")
        
        card = None
        for c in all_cards:
            if c.get("id") == justtcg_id:
                card = c
                break
        
        if not card:
            return {"error": f"Card with ID {justtcg_id} not found in set {set_slug}"}, 404
        
        name = card.get("name", "Unknown")
        set_name = card.get("set_name", "Unknown")
        card_number = card.get("number", "")
        variants = card.get("variants", [])
        
                                                          
        price = None
        price_history = []
        stats = {}
        chosen_variant = None
        
        priority = [
            ("Near Mint", "Holofoil"),
            ("Near Mint", "Foil"),
            ("Near Mint", "1st Edition"),
            ("Near Mint", "Normal"),
            ("Near Mint", "Reverse Holofoil"),
        ]
        
        for cond, printing in priority:
            for v in variants:
                if v.get("condition") == cond and v.get("printing") == printing:
                    if v.get("price"):
                        chosen_variant = v
                        break
            if chosen_variant:
                break
        
        if not chosen_variant:
            for v in variants:
                if v.get("condition") == "Near Mint" and v.get("price"):
                    chosen_variant = v
                    break
        
        if not chosen_variant:
            for v in variants:
                if v.get("price"):
                    chosen_variant = v
                    break
        
        if chosen_variant:
            price = chosen_variant.get("price")
            price_history = chosen_variant.get("priceHistory") or []
            stats = {
                "priceChange7d": chosen_variant.get("priceChange7d"),
                "priceChange30d": chosen_variant.get("priceChange30d"),
                "priceChange90d": chosen_variant.get("priceChange90d"),
                "minPrice1y": chosen_variant.get("minPrice1y"),
                "maxPrice1y": chosen_variant.get("maxPrice1y"),
                "minPriceAllTime": chosen_variant.get("minPriceAllTime"),
                "maxPriceAllTime": chosen_variant.get("maxPriceAllTime"),
                "minPriceAllTimeDate": chosen_variant.get("minPriceAllTimeDate"),
                "maxPriceAllTimeDate": chosen_variant.get("maxPriceAllTimeDate"),
                "condition": chosen_variant.get("condition"),
                "printing": chosen_variant.get("printing"),
            }
        
                                              
        image_url = ""
        try:
            import re
            tcg_headers = {}
            if POKEMON_TCG_API_KEY:
                tcg_headers["X-Api-Key"] = POKEMON_TCG_API_KEY

                                                                     
            number_raw = card_number.split("/")[0].strip()
            number_clean = number_raw.lstrip("0") or number_raw

                                                                    
            search_name = name.split(" - ")[0].strip()

                                                                                            
            clean_set = re.sub(r'^[A-Z]+\d*:\s*', '', set_name).strip()

            print(f"[IMG LOOKUP] name='{search_name}' set='{clean_set}' number='{number_clean}'")

                                                            
            tcg_params = {
                "q": f'name:"{search_name}" set.name:"{clean_set}" number:{number_clean}',
                "pageSize": 1
            }
            tcg_response = requests.get(
                "https://api.pokemontcg.io/v2/cards",
                headers=tcg_headers, params=tcg_params, timeout=5
            )
            tcg_data = tcg_response.json().get("data", [])
            print(f"[IMG LOOKUP] attempt 1 (name+set+number) returned {len(tcg_data)} results")

                                                 
            if not tcg_data:
                tcg_params = {
                    "q": f'name:"{search_name}" set.name:"{clean_set}"',
                    "pageSize": 1
                }
                tcg_response = requests.get(
                    "https://api.pokemontcg.io/v2/cards",
                    headers=tcg_headers, params=tcg_params, timeout=5
                )
                tcg_data = tcg_response.json().get("data", [])
                print(f"[IMG LOOKUP] attempt 2 (name+set) returned {len(tcg_data)} results")

                                                                                    
            if not tcg_data:
                tcg_params = {
                    "q": f'name:"{search_name}" number:{number_clean}',
                    "pageSize": 1
                }
                tcg_response = requests.get(
                    "https://api.pokemontcg.io/v2/cards",
                    headers=tcg_headers, params=tcg_params, timeout=5
                )
                tcg_data = tcg_response.json().get("data", [])
                print(f"[IMG LOOKUP] attempt 3 (name+number) returned {len(tcg_data)} results")

            if tcg_data:
                image_url = tcg_data[0].get("images", {}).get("large", "")
                print(f"[IMG LOOKUP] SUCCESS: {image_url}")
            else:
                print(f"[IMG LOOKUP] FAILED — no results for any query")
        except Exception as e:
            print(f"[IMG LOOKUP] Exception: {e}")
        
                          
        import json
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        cursor.execute(
    """INSERT INTO products 
    (name, type, set_name, card_number, justtcg_id, justtcg_set_slug, justtcg_history, justtcg_stats, image_url) 
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
    (name, "card", set_name, card_number, justtcg_id, set_slug,
     json.dumps(price_history), json.dumps(stats), image_url)
)
        product_id = cursor.lastrowid
        
        if price:
            cursor.execute(
                "INSERT INTO price_history (product_id, price) VALUES (%s, %s)",
                (product_id, price)
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return {
            "success": True,
            "product_id": product_id,
            "name": name,
            "set_name": set_name,
            "price": price,
            "image_url": image_url
        }
    except Exception as e:
        return {"error": str(e)}, 500
                                                              
                                                              
                                                              

@app.route("/poketrace-search/<query>")
def poketrace_search(query):
    """Search PokeTrace for US cards, return list with id/name/set/number/price."""
    POKETRACE_API_KEY = os.getenv("POKETRACE_API_KEY")
    if not POKETRACE_API_KEY:
        return {"error": "PokeTrace API key not configured"}, 500
    try:
        url = "https://api.poketrace.com/v1/cards"
        headers = {"X-API-Key": POKETRACE_API_KEY}
        params = {"search": query, "market": "US", "limit": 20}
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code != 200:
            return {"error": f"PokeTrace returned {response.status_code}"}, 500
        
        data = response.json()
        cards = data.get("data", [])
        results = []
        for card in cards:
                                                                                 
            display_price = None
            prices = card.get("prices", {}) or {}
            tcg = prices.get("tcgplayer", {}) or {}
            nm = tcg.get("NEAR_MINT") or {}
            if nm.get("avg"):
                display_price = nm.get("avg")
            else:
                                                                
                for cond, cond_data in tcg.items():
                    if cond_data and cond_data.get("avg"):
                        display_price = cond_data.get("avg")
                        break
            results.append({
                "poketrace_id": card.get("id"),
                "name": card.get("name"),
                "set_name": card.get("set", {}).get("name"),
                "set_slug": card.get("set", {}).get("slug"),
                "number": card.get("cardNumber"),
                "rarity": card.get("rarity"),
                "image": card.get("image"),
                "display_price": display_price,
            })

                                                                                 
                                                                                     
                                                               
        deduped = {}
        for r in results:
            key = (r["set_slug"], r["number"], r["name"], r["rarity"])
            existing = deduped.get(key)
            if existing is None:
                deduped[key] = r
            else:
                                                                                           
                if existing["display_price"] is None and r["display_price"] is not None:
                    deduped[key] = r
        results = list(deduped.values())

        return {"results": results, "total": len(results)}
    except Exception as e:
        return {"error": str(e)}, 500


@app.route("/public-card/<path:poketrace_id>")
def public_card(poketrace_id):
    """View any card's price + history straight from PokeTrace. No login needed.
    Logged-out visitors get only the last 30 days of history."""
    POKETRACE_API_KEY = os.getenv("POKETRACE_API_KEY")
    if not POKETRACE_API_KEY:
        return {"error": "PokeTrace API key not configured"}, 500

    try:
        from datetime import datetime, timedelta
        headers = {"X-API-Key": POKETRACE_API_KEY}

        detail_url = f"https://api.poketrace.com/v1/cards/{poketrace_id}"
        r = requests.get(detail_url, headers=headers, timeout=10)
        if r.status_code != 200:
            return {"error": f"PokeTrace returned {r.status_code}"}, 500
        card = r.json().get("data")
        if not card:
            return {"error": "Card not found"}, 404

        name = card.get("name", "Unknown")
        set_name = (card.get("set") or {}).get("name", "Unknown")
        image_url = card.get("image") or ""
        prices = card.get("prices", {}) or {}
        nm = (prices.get("tcgplayer", {}) or {}).get("NEAR_MINT") or {}
        current_price = nm.get("avg")

        hist_url = f"https://api.poketrace.com/v1/cards/{poketrace_id}/prices/NEAR_MINT/history"
        h = requests.get(hist_url, headers=headers, params={"period": "all", "limit": 365}, timeout=15)
        history = []
        if h.status_code == 200:
            raw = h.json().get("data", []) or []
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
    except Exception as e:
        return {"error": str(e)}, 500


@app.route("/save-card-poketrace/<path:poketrace_id>")
@login_required
def save_card_poketrace(poketrace_id):
    """Save a card using its PokeTrace ID. Pulls card detail + full price history."""
                                                                                      
    on_watchlist = 0 if request.args.get("watchlist") == "0" else 1
    POKETRACE_API_KEY = os.getenv("POKETRACE_API_KEY")
    if not POKETRACE_API_KEY:
        return {"error": "PokeTrace API key not configured"}, 500
    
    try:
        import json as json_mod
        headers = {"X-API-Key": POKETRACE_API_KEY}
        
                              
        detail_url = f"https://api.poketrace.com/v1/cards/{poketrace_id}"
        r = requests.get(detail_url, headers=headers, timeout=10)
        if r.status_code != 200:
            return {"error": f"PokeTrace card lookup returned {r.status_code}: {r.text[:200]}"}, 500
        
        card = r.json().get("data")
        if not card:
            return {"error": "Card not found"}, 404
        
        name = card.get("name", "Unknown")
        set_name = (card.get("set") or {}).get("name", "Unknown")
        card_number = card.get("cardNumber") or ""
        image_url = card.get("image") or ""
        
                                                                          
        prices = card.get("prices", {}) or {}
        tcg_prices = prices.get("tcgplayer", {}) or {}
        nm = tcg_prices.get("NEAR_MINT") or {}
        current_price = nm.get("avg")
        
                                          
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
        
                                                             
        hist_url = f"https://api.poketrace.com/v1/cards/{poketrace_id}/prices/NEAR_MINT/history"
        h = requests.get(hist_url, headers=headers, params={"period": "all", "limit": 365}, timeout=15)
        history_points = []
        if h.status_code == 200:
            history_points = h.json().get("data", []) or []
            print(f"[POKETRACE SAVE] {name}: fetched {len(history_points)} history points")
        else:
            print(f"[POKETRACE SAVE] {name}: history fetch returned {h.status_code}")
        
                            
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

                                                                            
                                                                         
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
    except Exception as e:
        return {"error": str(e)}, 500
                                                              
                       
                                                              

@app.route("/signup", methods=["POST"])
@limiter.limit("3 per hour")
def signup():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    code = (data.get("code") or "").strip()

                     
    if not username or not email or not password or not code:
        return {"error": "All fields are required"}, 400
    if len(password) < 8:
        return {"error": "Password must be at least 8 characters"}, 400
    if len(username) < 3:
        return {"error": "Username must be at least 3 characters"}, 400

    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    try:
                                               
        cursor.execute("SELECT code, used_by FROM signup_codes WHERE code = %s", (code,))
        code_row = cursor.fetchone()
        if not code_row:
            return {"error": "Invalid invite code"}, 400
        if code_row["used_by"] is not None:
            return {"error": "Invite code already used"}, 400

                                        
        cursor.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
        if cursor.fetchone():
            return {"error": "Username or email already in use"}, 400

                                       
        pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        cursor.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
            (username, email, pw_hash)
        )
        new_user_id = cursor.lastrowid

                                      
        cursor.execute("UPDATE signup_codes SET used_by = %s WHERE code = %s", (new_user_id, code))
        conn.commit()

                                 
        user = User(new_user_id, username, email)
        login_user(user)
        return {"success": True, "user": {"id": new_user_id, "username": username, "email": email}}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}, 500
    finally:
        cursor.close()
        conn.close()


@app.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return {"error": "Username and password required"}, 400

    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, username, email, password_hash FROM users WHERE username = %s",
            (username,)
        )
        row = cursor.fetchone()
                                                              
        if not row or not bcrypt.checkpw(password.encode("utf-8"), row["password_hash"].encode("utf-8")):
            return {"error": "Invalid username or password"}, 401

        user = User(row["id"], row["username"], row["email"])
        login_user(user)
        return {"success": True, "user": {"id": row["id"], "username": row["username"], "email": row["email"]}}
    finally:
        cursor.close()
        conn.close()


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return {"success": True}


                                                              
                      
                                                              

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
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}, 500
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
    except Exception as e:
        return {"error": str(e)}, 500
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
    except Exception as e:
        return {"success": False, "error": str(e)}, 500
    finally:
        cursor.close()
        conn.close()
@app.route("/me")
def me():
    if current_user.is_authenticated:
        return {"user": {"id": current_user.id, "username": current_user.username, "email": current_user.email}}
    return {"user": None}
                                                              
                   
                                                              

@app.route("/create-share", methods=["POST"])
@login_required
def create_share():
    import secrets
    from datetime import datetime, timedelta
    data = request.get_json() or {}
    duration = data.get("duration", "24h")                                  
    label = (data.get("label") or "").strip() or None

                              
    hours_map = {"1h": 1, "12h": 12, "24h": 24}
    if duration == "infinite":
        expires_at = None
    else:
        hrs = hours_map.get(duration, 24)
        expires_at = datetime.now() + timedelta(hours=hrs)

    token = secrets.token_urlsafe(24)                           

    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO share_links (token, owner_id, label, expires_at) VALUES (%s, %s, %s, %s)",
            (token, current_user.id, label, expires_at)
        )
        conn.commit()
        return {"success": True, "token": token}
    except Exception as e:
        return {"success": False, "error": str(e)}, 500
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
                          
        cursor.execute("SELECT * FROM share_links WHERE token = %s", (token,))
        link = cursor.fetchone()
        if not link or not link["active"]:
            return {"error": "This share link is invalid or was turned off."}, 404

                         
        if link["expires_at"] is not None and link["expires_at"] < datetime.now():
            return {"error": "This share link has expired."}, 410

        owner_id = link["owner_id"]

                                                                                 
        if current_user.id != owner_id:
            cursor.execute(
                "INSERT IGNORE INTO share_access (share_link_id, viewer_id) VALUES (%s, %s)",
                (link["id"], current_user.id)
            )
            conn.commit()

                             
        cursor.execute("SELECT username FROM users WHERE id = %s", (owner_id,))
        owner = cursor.fetchone()
        owner_name = owner["username"] if owner else "Unknown"

                               
        cursor.execute("""
            SELECT c.quantity, c.price_paid, p.name, p.set_name, p.image_url,
                   (SELECT price FROM price_history WHERE product_id = p.id ORDER BY recorded_at DESC LIMIT 1) AS current_price
            FROM collection c
            JOIN products p ON c.product_id = p.id
            WHERE c.user_id = %s
            ORDER BY c.date_added DESC
        """, (owner_id,))
        collection = cursor.fetchall()
        for item in collection:
            if item.get("price_paid") is not None:
                item["price_paid"] = float(item["price_paid"])
            if item.get("current_price") is not None:
                item["current_price"] = float(item["current_price"])

                           
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
    except Exception as e:
        return {"error": str(e)}, 500
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
    except Exception as e:
        return {"error": str(e)}, 500
    finally:
        cursor.close()
        conn.close()


                                                              
                                  
                                                              

@app.route("/market-sets")
def market_sets():
    """Sets that have enough ranked cards to be worth filtering by."""
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT set_slug, MAX(set_name) AS set_name, COUNT(*) AS card_count
            FROM market_cards
            WHERE avg30d >= 10 AND sale_count >= 50
            GROUP BY set_slug
            HAVING card_count >= 3
            ORDER BY set_name ASC
        """)
        return {"sets": cursor.fetchall()}
    except Exception as e:
        return {"error": str(e)}, 500
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
        """
        params = [MIN_PRICE, MIN_SALES]
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
            "set": set_slug,
            "last_synced": meta["synced"].isoformat() if meta["synced"] else None,
            "cards_tracked": meta["total"],
        }
    except Exception as e:
        return {"error": str(e)}, 500
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
    except Exception as e:
        return {"error": str(e)}, 500
    finally:
        cursor.close()
        conn.close()


@app.route("/card-prices/<path:poketrace_id>")
def card_prices(poketrace_id):
    """Current price + last 10 days of sales for a given condition.
    Public — market data. Query: ?condition=NEAR_MINT|LIGHTLY_PLAYED|..."""
    condition = request.args.get("condition", "NEAR_MINT")
    valid = {"NEAR_MINT", "LIGHTLY_PLAYED", "MODERATELY_PLAYED", "HEAVILY_PLAYED", "DAMAGED"}
    if condition not in valid:
        condition = "NEAR_MINT"

    API_KEY = os.getenv("POKETRACE_API_KEY")
    headers = {"X-API-Key": API_KEY}
    try:
                                                               
        detail = requests.get(f"https://api.poketrace.com/v1/cards/{poketrace_id}",
                              headers=headers, timeout=15)
        price = None
        if detail.status_code == 200:
            d = detail.json().get("data", {}) or {}
            tcg = (d.get("prices", {}) or {}).get("tcgplayer", {}) or {}
            block = tcg.get(condition) or {}
            price = block.get("avg")

                                                 
        hist = requests.get(
            f"https://api.poketrace.com/v1/cards/{poketrace_id}/prices/{condition}/history",
            headers=headers, params={"period": "all", "limit": 60}, timeout=15
        )
        sales = []
        if hist.status_code == 200:
            points = hist.json().get("data", []) or []
                                                                           
            with_sales = [p for p in points if (p.get("saleCount") or 0) > 0]
            for p in with_sales[:10]:
                sales.append({
                    "date": p.get("date"),
                    "sale_count": p.get("saleCount"),
                    "low": p.get("low"),
                    "high": p.get("high"),
                    "avg": p.get("avg"),
                    "source": p.get("source"),
                })

        return {"condition": condition, "price": price, "sales": sales}
    except Exception as e:
        return {"error": str(e)}, 500


if __name__ == "__main__":
                                                                     
                                                                        
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=5050, debug=debug_mode)