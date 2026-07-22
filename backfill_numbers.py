import mysql.connector
import os
import requests
from dotenv import load_dotenv

load_dotenv()

db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME")
}
API_KEY = os.getenv("POKEMON_TCG_API_KEY")

conn = mysql.connector.connect(**db_config)
cursor = conn.cursor(dictionary=True)
cursor.execute("SELECT id, name, set_name FROM products WHERE card_number IS NULL OR card_number = ''")
products = cursor.fetchall()

print(f"Backfilling {len(products)} cards...")

for p in products:
    url = "https://api.pokemontcg.io/v2/cards"
    headers = {"X-Api-Key": API_KEY}
    params = {"q": f'name:"{p["name"]}" set.name:"{p["set_name"]}"', "pageSize": 1}
    r = requests.get(url, headers=headers, params=params).json()
    if r.get("data"):
        number = r["data"][0].get("number", "")
        cursor.execute("UPDATE products SET card_number = %s WHERE id = %s", (number, p["id"]))
        print(f"  {p['name']} ({p['set_name']}) -> {number}")
    else:
        print(f"  {p['name']}: not found in API")

conn.commit()
cursor.close()
conn.close()
print("Done")
