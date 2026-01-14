from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import requests
import math
import random
import os

app = Flask(__name__)
app.secret_key = "change_this_secret_key"

DB_NAME = "app.db"

# ---------------- DATABASE ----------------

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS favorites(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            place_id TEXT
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ---------------- UTILS ----------------

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return round(R * c, 2)

def estimate_rating(place_type):
    base = {"cafe":4.2,"restaurant":4.3,"fast_food":3.9,"food_court":4.0}
    return round(base.get(place_type,4.0) + random.uniform(-0.3,0.3), 1)

# ---------------- AUTH ----------------

@app.route("/", methods=["GET","POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("home"))

    error = None

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("home"))
        else:
            error = "Invalid credentials"

    return render_template("login.html", error=error)

@app.route("/signup", methods=["GET","POST"])
def signup():
    error = None

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        hashed = generate_password_hash(password)

        try:
            conn = get_db()
            conn.execute("INSERT INTO users(username,password_hash) VALUES(?,?)", (username,hashed))
            conn.commit()
            conn.close()
            return redirect(url_for("login"))
        except:
            error = "Username already exists"

    return render_template("signup.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/home")
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("index.html", user=session["username"])

# ---------------- FAVORITES API ----------------

@app.route("/favorite", methods=["POST"])
def toggle_favorite():
    if "user_id" not in session:
        return jsonify({"status":"unauthorized"})

    data = request.json
    place_id = data["place_id"]
    user_id = session["user_id"]

    conn = get_db()
    cur = conn.cursor()

    existing = cur.execute(
        "SELECT * FROM favorites WHERE user_id=? AND place_id=?",
        (user_id, place_id)
    ).fetchone()

    if existing:
        cur.execute("DELETE FROM favorites WHERE user_id=? AND place_id=?", (user_id, place_id))
        status = "removed"
    else:
        cur.execute("INSERT INTO favorites(user_id,place_id) VALUES(?,?)", (user_id, place_id))
        status = "added"

    conn.commit()
    conn.close()

    return jsonify({"status":status})

@app.route("/favorites")
def get_favorites():
    if "user_id" not in session:
        return jsonify([])

    conn = get_db()
    rows = conn.execute(
        "SELECT place_id FROM favorites WHERE user_id=?",
        (session["user_id"],)
    ).fetchall()
    conn.close()

    return jsonify([r["place_id"] for r in rows])

# ---------------- PLACES API ----------------

CACHE = {}

@app.route("/get_places")
def get_places():
    try:
        lat = float(request.args.get("lat"))
        lng = float(request.args.get("lng"))
        mood = request.args.get("mood")

        cache_key = f"{lat}_{lng}_{mood}"
        if cache_key in CACHE:
            return jsonify(CACHE[cache_key])

        tag_map = {
            "work":"amenity=cafe",
            "date":"amenity=restaurant",
            "quick":"amenity=fast_food",
            "budget":"amenity=food_court"
        }

        tag = tag_map.get(mood,"amenity=restaurant")

        query = f"""
        [out:json];
        node[{tag}](around:8000,{lat},{lng});
        out;
        """

        urls = [
            "https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter"
        ]

        response = None
        for u in urls:
            try:
                response = requests.post(u,data=query,timeout=20)
                if response.status_code==200:
                    break
            except:
                pass

        if not response or response.status_code!=200:
            return jsonify([])

        elements = response.json().get("elements",[])
        results = []

        for p in elements:
            if "lat" in p and "lon" in p:
                place_type = p.get("tags",{}).get("amenity","unknown")
                results.append({
                    "id": f"{p['lat']}_{p['lon']}",
                    "name": p.get("tags",{}).get("name","Unnamed Place"),
                    "type": place_type,
                    "lat": p["lat"],
                    "lon": p["lon"],
                    "distance": calculate_distance(lat,lng,p["lat"],p["lon"]),
                    "rating": estimate_rating(place_type)
                })

        results.sort(key=lambda x:x["distance"])
        final = results[:25]
        CACHE[cache_key] = final

        return jsonify(final)

    except Exception as e:
        print("ERROR:",e)
        return jsonify([])

if __name__ == "__main__":
    app.run()

