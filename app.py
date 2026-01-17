from flask import Flask, render_template, request, redirect, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
import psycopg2.extras
import os
import requests

app = Flask(__name__)
app.secret_key = "super-secret-key"  # change in production

# =======================
# DATABASE
# =======================

def get_db():
    DATABASE_URL = os.environ.get("DATABASE_URL")

    if not DATABASE_URL:
        raise Exception("DATABASE_URL environment variable not set")

    conn = psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor,
        sslmode="require"
    )
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            place_id TEXT NOT NULL
        );
    """)

    conn.commit()
    cur.close()
    conn.close()


init_db()

# =======================
# AUTH ROUTES
# =======================

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user"] = username
            return redirect("/dashboard")

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        hashed = generate_password_hash(password)

        conn = get_db()
        cur = conn.cursor()

        try:
            cur.execute(
                "INSERT INTO users (username, password) VALUES (%s,%s)",
                (username, hashed)
            )
            conn.commit()
        except:
            cur.close()
            conn.close()
            return render_template("signup.html", error="Username already exists")

        cur.close()
        conn.close()
        return redirect("/")

    return render_template("signup.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# =======================
# DASHBOARD
# =======================

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")
    return render_template("index.html", user=session["user"])


# =======================
# FAVORITES
# =======================

@app.route("/favorites")
def favorites():
    if "user" not in session:
        return jsonify([])

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT place_id FROM favorites WHERE username=%s",
        (session["user"],)
    )

    rows = cur.fetchall()
    favs = [r["place_id"] for r in rows]

    cur.close()
    conn.close()

    return jsonify(favs)


@app.route("/favorite", methods=["POST"])
def toggle_favorite():
    if "user" not in session:
        return jsonify({"status": "error"})

    place_id = request.json["place_id"]
    user = session["user"]

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM favorites WHERE username=%s AND place_id=%s",
        (user, place_id)
    )
    exists = cur.fetchone()

    if exists:
        cur.execute(
            "DELETE FROM favorites WHERE username=%s AND place_id=%s",
            (user, place_id)
        )
        status = "removed"
    else:
        cur.execute(
            "INSERT INTO favorites (username, place_id) VALUES (%s,%s)",
            (user, place_id)
        )
        status = "added"

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"status": status})


# =======================
# PLACES API
# =======================

@app.route("/get_places")
def get_places():
    lat = float(request.args.get("lat"))
    lng = float(request.args.get("lng"))
    mood = request.args.get("mood")

    name_map = {
        "work": ["Coworking Hub", "Startup Space", "Business Center", "Tech Workspace"],
        "date": ["Cafe Bliss", "Romantic Dine", "Garden Restaurant", "Sky Lounge"],
        "quick": ["Burger Point", "Snack Shack", "Fast Bites", "Food Express"],
        "budget": ["Budget Bites", "Street Food Hub", "Tasty Corner", "Food Court"]
    }

    names = name_map.get(mood, ["Nearby Place"])

    places = []

    for i in range(10):
        places.append({
            "id": f"{mood}_{i}",
            "name": f"{names[i % len(names)]}",
            "type": mood.title(),
            "rating": round(3.5 + (i % 4) * 0.4, 1),
            "distance": round(0.4 + i * 0.35, 2),
            "lat": lat + (i * 0.0012),
            "lon": lng + (i * 0.0011)
        })

    return jsonify(places)



# =======================
# MAIN
# =======================

if __name__ == "__main__":
    app.run(debug=True)
