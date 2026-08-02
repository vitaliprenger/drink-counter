import hashlib
import json
import os
import uuid
from flask import Flask, jsonify, render_template, request, send_from_directory

app = Flask(__name__)
DATA_FILE = "/data/drinks.json"
IMAGES_DIR = "/data/images"
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB

ALLOWED_EXT = {"jpg", "jpeg", "png", "gif", "webp"}


def migrate_legacy_counts(data):
    """Move the old single 'count' int per person into counts[categoryId]."""
    legacy_people = [p for p in data["people"] if "count" in p]
    if legacy_people and not data["categories"]:
        data["categories"].append({"id": "default", "name": "Getränk", "price": 1.0})
    default_id = data["categories"][0]["id"] if data["categories"] else None
    changed = bool(legacy_people)
    for p in data["people"]:
        counts = p.setdefault("counts", {})
        if "count" in p:
            legacy = p.pop("count")
            if default_id:
                counts[default_id] = counts.get(default_id, 0) + legacy
    return changed


def migrate_category_images(data):
    """Move the old single 'image' string per category into an 'images' list."""
    changed = False
    for c in data["categories"]:
        if "image" in c:
            img = c.pop("image")
            images = c.setdefault("images", [])
            if img and img not in images:
                images.append(img)
            changed = True
        else:
            c.setdefault("images", [])
    return changed


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
            if "people" in data:
                data.setdefault("categories", [])
                changed = migrate_legacy_counts(data)
                changed = migrate_category_images(data) or changed
                if changed:
                    save_data(data)
                return data
    return {"people": [], "categories": []}


def parse_price(value):
    try:
        price = round(float(value), 2)
    except (TypeError, ValueError):
        return None
    if price < 0:
        return None
    return price


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
    data["people"].append({"name": name, "counts": {}})
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
    category_id = request.json.get("categoryId", "")
    delta = request.json.get("delta", 1)
    person = next((p for p in data["people"] if p["name"] == name), None)
    if not person:
        return jsonify({"error": "Person nicht gefunden"}), 404
    if not any(c["id"] == category_id for c in data["categories"]):
        return jsonify({"error": "Kategorie nicht gefunden"}), 404
    counts = person.setdefault("counts", {})
    counts[category_id] = max(0, counts.get(category_id, 0) + delta)
    save_data(data)
    return jsonify(data)


@app.post("/api/person/reset-count")
def reset_person_count():
    data = load_data()
    name = request.json.get("name", "").strip()
    person = next((p for p in data["people"] if p["name"] == name), None)
    if not person:
        return jsonify({"error": "Person nicht gefunden"}), 404
    person["counts"] = {}
    save_data(data)
    return jsonify(data)


@app.post("/api/category")
def add_category():
    data = load_data()
    name = request.json.get("name", "").strip()
    price = parse_price(request.json.get("price"))
    if not name:
        return jsonify({"error": "Name darf nicht leer sein"}), 400
    if price is None:
        return jsonify({"error": "Ungültiger Preis"}), 400
    data["categories"].append({"id": uuid.uuid4().hex[:8], "name": name, "price": price})
    save_data(data)
    return jsonify(data)


@app.post("/api/category/update")
def update_category():
    data = load_data()
    cat_id = request.json.get("id", "")
    name = request.json.get("name", "").strip()
    price = parse_price(request.json.get("price"))
    category = next((c for c in data["categories"] if c["id"] == cat_id), None)
    if not category:
        return jsonify({"error": "Kategorie nicht gefunden"}), 404
    if not name:
        return jsonify({"error": "Name darf nicht leer sein"}), 400
    if price is None:
        return jsonify({"error": "Ungültiger Preis"}), 400
    category["name"] = name
    category["price"] = price
    save_data(data)
    return jsonify(data)


@app.post("/api/category/image")
def upload_category_image():
    data = load_data()
    cat_id = request.form.get("id", "").strip()
    category = next((c for c in data["categories"] if c["id"] == cat_id), None)
    if not category:
        return jsonify({"error": "Kategorie nicht gefunden"}), 404

    uploads = [(f, f.filename) for f in request.files.getlist("images") if f and f.filename]
    if not uploads:
        return jsonify({"error": "Keine Datei"}), 400
    for _, orig_name in uploads:
        ext = orig_name.rsplit(".", 1)[-1].lower() if "." in orig_name else ""
        if ext not in ALLOWED_EXT:
            return jsonify({"error": "Ungültiges Format (jpg, png, gif, webp)"}), 400

    os.makedirs(IMAGES_DIR, exist_ok=True)
    images = category.setdefault("images", [])
    for f, orig_name in uploads:
        ext = orig_name.rsplit(".", 1)[-1].lower()
        filename = f"cat_{cat_id}_{uuid.uuid4().hex[:8]}.{ext}"
        f.save(os.path.join(IMAGES_DIR, filename))
        images.append(filename)
    save_data(data)
    return jsonify(data)


@app.post("/api/category/image/remove")
def remove_category_image():
    data = load_data()
    cat_id = request.json.get("id", "")
    filename = request.json.get("filename", "")
    category = next((c for c in data["categories"] if c["id"] == cat_id), None)
    if not category:
        return jsonify({"error": "Kategorie nicht gefunden"}), 404
    images = category.get("images", [])
    if filename not in images:
        return jsonify({"error": "Bild nicht gefunden"}), 404
    images.remove(filename)
    path = os.path.join(IMAGES_DIR, filename)
    if os.path.exists(path):
        os.remove(path)
    save_data(data)
    return jsonify(data)


@app.post("/api/category/remove")
def remove_category():
    data = load_data()
    cat_id = request.json.get("id", "")
    category = next((c for c in data["categories"] if c["id"] == cat_id), None)
    if not category:
        return jsonify({"error": "Kategorie nicht gefunden"}), 404
    for img_name in category.get("images", []):
        img = os.path.join(IMAGES_DIR, img_name)
        if os.path.exists(img):
            os.remove(img)
    data["categories"] = [c for c in data["categories"] if c["id"] != cat_id]
    for p in data["people"]:
        p.get("counts", {}).pop(cat_id, None)
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
        p["counts"] = {}
    save_data(data)
    return jsonify(data)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
