import hashlib
import json
import os
from flask import Flask, jsonify, render_template, request, send_from_directory

app = Flask(__name__)
DATA_FILE = "/data/drinks.json"
IMAGES_DIR = "/data/images"
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB

ALLOWED_EXT = {"jpg", "jpeg", "png", "gif", "webp"}


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
            if "people" in data:
                return data
    return {"people": []}


def save_data(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/count")
def get_count():
    return jsonify(load_data())


@app.post("/api/person")
def add_person():
    data = load_data()
    name = request.json.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name darf nicht leer sein"}), 400
    if any(p["name"] == name for p in data["people"]):
        return jsonify({"error": "Name existiert bereits"}), 400
    data["people"].append({"name": name, "count": 0})
    save_data(data)
    return jsonify(data)


@app.post("/api/person/image")
def upload_image():
    data = load_data()
    name = request.form.get("name", "").strip()
    person = next((p for p in data["people"] if p["name"] == name), None)
    if not person:
        return jsonify({"error": "Person nicht gefunden"}), 404

    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"error": "Keine Datei"}), 400
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXT:
        return jsonify({"error": "Ungültiges Format (jpg, png, gif, webp)"}), 400

    os.makedirs(IMAGES_DIR, exist_ok=True)
    if person.get("image"):
        old = os.path.join(IMAGES_DIR, person["image"])
        if os.path.exists(old):
            os.remove(old)

    filename = hashlib.sha256(name.encode()).hexdigest()[:16] + "." + ext
    file.save(os.path.join(IMAGES_DIR, filename))
    person["image"] = filename
    save_data(data)
    return jsonify(data)


@app.get("/api/image/<filename>")
def get_image(filename):
    resp = send_from_directory(IMAGES_DIR, filename)
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.post("/api/drink")
def update_drink():
    data = load_data()
    name = request.json.get("name", "").strip()
    delta = request.json.get("delta", 1)
    person = next((p for p in data["people"] if p["name"] == name), None)
    if not person:
        return jsonify({"error": "Person nicht gefunden"}), 404
    person["count"] = max(0, person["count"] + delta)
    save_data(data)
    return jsonify(data)


@app.post("/api/person/reset-count")
def reset_person_count():
    data = load_data()
    name = request.json.get("name", "").strip()
    person = next((p for p in data["people"] if p["name"] == name), None)
    if not person:
        return jsonify({"error": "Person nicht gefunden"}), 404
    person["count"] = 0
    save_data(data)
    return jsonify(data)


@app.post("/api/person/rename")
def rename_person():
    data = load_data()
    name = request.json.get("name", "").strip()
    new_name = request.json.get("newName", "").strip()
    if not new_name:
        return jsonify({"error": "Name darf nicht leer sein"}), 400
    if any(p["name"] == new_name for p in data["people"]):
        return jsonify({"error": "Name existiert bereits"}), 400
    person = next((p for p in data["people"] if p["name"] == name), None)
    if not person:
        return jsonify({"error": "Person nicht gefunden"}), 404
    person["name"] = new_name
    save_data(data)
    return jsonify(data)


@app.post("/api/person/remove")
def remove_person():
    data = load_data()
    name = request.json.get("name", "").strip()
    person = next((p for p in data["people"] if p["name"] == name), None)
    if not person:
        return jsonify({"error": "Person nicht gefunden"}), 404
    if person.get("image"):
        img = os.path.join(IMAGES_DIR, person["image"])
        if os.path.exists(img):
            os.remove(img)
    data["people"] = [p for p in data["people"] if p["name"] != name]
    save_data(data)
    return jsonify(data)


@app.post("/api/reset")
def reset():
    data = load_data()
    for p in data["people"]:
        p["count"] = 0
    save_data(data)
    return jsonify(data)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
