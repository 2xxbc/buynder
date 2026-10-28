"""Keep tracked_sets in line with PokeTrace's real set list.

DRY RUN by default: prints what it could change and writes nothing.
    ~/pokemarket/venv/bin/python load_all_sets.py                      # report only
Writing needs --apply AND at least one action (back up first). Every action is opt-in:
    --add scripts/approved_sets.txt   add ONLY the slugs in that file (one per line, # comments allowed).
                                      A slug PokeTrace doesn't list stops the run before anything is written.
    --deactivate-gone                 active = 0 on slugs PokeTrace no longer lists (rows kept, never deleted)
    --fix-names                       update names PokeTrace changed
e.g. ~/pokemarket/venv/bin/python load_all_sets.py --apply --add scripts/approved_sets.txt --deactivate-gone
PokeTrace cost: about 1 request per 100 sets (~5 in total). The next 3 AM sweep then costs
about 1 request per 20 cards of each added set.
"""
import os, sys, time, requests, mysql.connector
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("POKETRACE_API_KEY")
APPLY = "--apply" in sys.argv
DEACTIVATE = "--deactivate-gone" in sys.argv
FIX_NAMES = "--fix-names" in sys.argv
ADD_FILE = sys.argv[sys.argv.index("--add") + 1] if "--add" in sys.argv[:-1] else None

db_config = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME", "pokemarket"),
}


def poketrace_sets():
    """Every Pokemon set PokeTrace lists that has cards: {slug: {"name", "cardCount"}}."""
    headers = {"X-API-Key": API_KEY}
    out, cursor_token = {}, None
    while True:
        params = {"game": "pokemon", "limit": 100}
        if cursor_token:
            params["cursor"] = cursor_token
        r = requests.get("https://api.poketrace.com/v1/sets", headers=headers, params=params, timeout=60)
        if r.status_code != 200:
            sys.exit(f"PokeTrace /sets returned {r.status_code}; nothing changed.")
        body = r.json()
        for s in body.get("data", []):
            if s.get("cardCount"):
                released = s.get("releaseDate") or s.get("release_date")  # if PokeTrace sends one
                out[s["slug"]] = {"name": s["name"], "cardCount": s["cardCount"],
                                  "release_date": str(released)[:10] if released else None}
        p = body.get("pagination") or {}
        if not (p.get("hasMore") and p.get("nextCursor")):
            return out
        cursor_token = p["nextCursor"]
        time.sleep(0.3)


def norm(name):
    return " ".join((name or "").lower().replace("&", "and").replace("-", " ").split())


def plan(theirs, ours):
    """Work out the changes. theirs: {slug: {...}} from PokeTrace; ours: {slug: {"name", "active"}}."""
    by_name = {}
    for slug, s in theirs.items():
        by_name.setdefault(norm(s["name"]), []).append(slug)
    add = [slug for slug in theirs if slug not in ours]
    deactivate, renamed, rename_names = [], [], []
    for slug, o in ours.items():
        if slug in theirs:
            if theirs[slug]["name"] != o["name"]:
                rename_names.append((slug, o["name"], theirs[slug]["name"]))
            continue
        if o["active"]:
            deactivate.append(slug)
        new_slugs = [x for x in by_name.get(norm(o["name"]), []) if x not in ours]
        if new_slugs:
            renamed.append((slug, new_slugs))
    return add, deactivate, renamed, rename_names


def read_approved(path):
    """Slugs from an approved-list file: one per line, anything after # is a comment."""
    with open(path) as f:
        return [line.split("#")[0].strip() for line in f if line.split("#")[0].strip()]


def main():
    if "--add" in sys.argv and not ADD_FILE:
        sys.exit("--add needs a file, e.g. --add scripts/approved_sets.txt")
    if APPLY and not (ADD_FILE or DEACTIVATE or FIX_NAMES):
        sys.exit("--apply needs an action: --add <file>, --deactivate-gone and/or --fix-names. Nothing changed.")
    theirs = poketrace_sets()
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT slug, name, active FROM tracked_sets")
    ours = {r["slug"]: r for r in cursor.fetchall()}
    add, deactivate, renamed, rename_names = plan(theirs, ours)

    first_sweep = sum(-(-theirs[s]["cardCount"] // 20) for s in add)
    print(f"PokeTrace lists {len(theirs)} sets with cards; we track {len(ours)}.")
    print(f"Untracked sets PokeTrace has: {len(add)} (adding all would cost about {first_sweep} requests on the first sweep):")
    for s in add:
        print(f"   + {s:42} {theirs[s]['name']} ({theirs[s]['cardCount']} cards)")
    print(f"Renamed by PokeTrace ({len(renamed)}):")
    for old, new in renamed:
        print(f"   {old} -> {', '.join(new)}")
    print(f"Set active = 0 on {len(deactivate)} slugs PokeTrace no longer has (rows kept):")
    for s in deactivate:
        print(f"   - {s:42} {ours[s]['name']}")
    print(f"Name updates: {len(rename_names)}")
    for slug, old, new in rename_names:
        print(f"   {slug}: '{old}' -> '{new}'")
    dated = sorted((s["release_date"], slug) for slug, s in theirs.items() if s.get("release_date"))
    print(f"Release dates: PokeTrace sends one for {len(dated)} of {len(theirs)} sets"
          + (f" (newest: {dated[-1][1]} on {dated[-1][0]})" if dated else " (the home 'New set' section stays hidden)"))

    approved = []
    if ADD_FILE:
        wanted = read_approved(ADD_FILE)
        unknown = [x for x in wanted if x not in theirs]
        if unknown:
            sys.exit(f"Not in PokeTrace's set list: {', '.join(unknown)}. Fix {ADD_FILE}; nothing changed.")
        already = [x for x in wanted if x in ours]
        approved = [x for x in wanted if x not in ours]
        cost = sum(-(-theirs[x]["cardCount"] // 20) for x in approved)
        print(f"\nApproved list {ADD_FILE}: {len(approved)} to add (first sweep about {cost} requests)"
              + (f", already tracked: {', '.join(already)}" if already else ""))
        for x in approved:
            print(f"   + {x:42} {theirs[x]['name']} ({theirs[x]['cardCount']} cards)")
        skipped = [x for x in add if x not in approved]
        print(f"Not added (not on the list): {len(skipped)}")

    if not APPLY:
        print("\nDry run: nothing was written. Back up, then run again with --apply and the actions you want.")
    else:
        for s in approved:
            cursor.execute("INSERT IGNORE INTO tracked_sets (slug, name, active) VALUES (%s, %s, 1)", (s, theirs[s]["name"]))
        if DEACTIVATE:
            for s in deactivate:
                cursor.execute("UPDATE tracked_sets SET active = 0 WHERE slug = %s", (s,))
        if FIX_NAMES:
            for slug, _, new in rename_names:
                cursor.execute("UPDATE tracked_sets SET name = %s WHERE slug = %s", (new, slug))
        print(f"Added {len(approved)}, deactivated {len(deactivate) if DEACTIVATE else 0}, "
              f"renamed {len(rename_names) if FIX_NAMES else 0}.")
        # Release dates for the home page's "New set", once migration 005 added the column
        cursor.execute("""SELECT COUNT(*) AS n FROM information_schema.columns WHERE table_schema = DATABASE()
                          AND table_name = 'tracked_sets' AND column_name = 'release_date'""")
        if cursor.fetchone()["n"]:
            dated = [(s["release_date"], slug) for slug, s in theirs.items() if s.get("release_date")]
            for released, slug in dated:
                cursor.execute("UPDATE tracked_sets SET release_date = %s WHERE slug = %s", (released, slug))
            print(f"Release dates stored for {len(dated)} sets.")
        conn.commit()
        print("\nApplied.")
    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()
