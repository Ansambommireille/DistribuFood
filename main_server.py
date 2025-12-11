import os
import json
import random
import string
import time
import bcrypt
import smtplib
from math import ceil
from email.mime.text import MIMEText
from flask import Flask, request, session, send_file, jsonify, render_template
from dotenv import load_dotenv
import sqlite3
import grpc
import storage_pb2
import storage_pb2_grpc_grpc

load_dotenv()

app = Flask(__name__)
app.secret_key = "change_this_in_production_please"

# === CONFIG ===
NODES = ["localhost:50051", "localhost:50052", "localhost:50053"]  # Add more if you start more nodes
REPLICATION = 2
BLOCK_SIZE = 1024 * 1024  # 1 MB blocks

EMAIL_FROM = os.getenv("EMAIL_ADDRESS")
EMAIL_PASS = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# === DATABASE ===
conn = sqlite3.connect("storage.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, password TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, filename TEXT, size INTEGER, blocks TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS otps (email TEXT PRIMARY KEY, otp TEXT, expires INTEGER)''')
conn.commit()

def send_otp(email, otp):
    msg = MIMEText(f"Your login OTP is: {otp}\nValid for 5 minutes.")
    msg["Subject"] = "Your Cloud Storage OTP"
    msg["From"] = EMAIL_FROM
    msg["To"] = email
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_FROM, EMAIL_PASS)
        server.sendmail(EMAIL_FROM, email, msg.as_string())

def new_otp():
    return "".join(random.choices(string.digits, k=6))

def get_stub(node):
    channel = grpc.insecure_channel(node)
    return storage_pb2_grpc.StorageNodeStub(channel)

def pick_nodes():
    return random.sample(NODES, min(REPLICATION, len(NODES)))

# === ROUTES ===
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/signup", methods=["POST"])
def signup():
    data = request.json
    email, pwd = data["email"], data["password"].encode()
    hashed = bcrypt.hashpw(pwd, bcrypt.gensalt())
    try:
        c.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, hashed))
        conn.commit()
        return jsonify(success=True, message="Account created")
    except sqlite3.IntegrityError:
        return jsonify(success=False, message="Email already registered"), 400

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    email, pwd = data["email"], data["password"].encode()
    c.execute("SELECT id, password FROM users WHERE email=?", (email,))
    user = c.fetchone()
    if user and bcrypt.checkpw(pwd, user[1].encode()):
        otp = new_otp()
        expires = int(time.time()) + 300
        c.execute("INSERT OR REPLACE INTO otps (email, otp, expires) VALUES (?, ?, ?)", (email, otp, expires))
        conn.commit()
        send_otp(email, otp)
        session["pending_email"] = email
        return jsonify(success=True, message="OTP sent")
    return jsonify(success=False, message="Wrong email or password"), 401

@app.route("/verify-otp", methods=["POST"])
def verify_otp():
    otp = request.json["otp"]
    email = session.get("pending_email")
    if not email:
        return jsonify(success=False, message="No login in progress"), 400
    c.execute("SELECT otp, expires FROM otps WHERE email=?", (email,))
    row = c.fetchone()
    if row and row[0] == otp and row[1] > time.time():
        c.execute("SELECT id FROM users WHERE email=?", (email,))
        user_id = c.fetchone()[0]
        session["user_id"] = user_id
        session.pop("pending_email", None)
        c.execute("DELETE FROM otps WHERE email=?", (email,))
        conn.commit()
        return jsonify(success=True, message="Logged in")
    return jsonify(success=False, message="Wrong or expired OTP"), 401

@app.route("/upload", methods=["POST"])
def upload():
    if "user_id" not in session:
        return jsonify(success=False, message="Login required"), 401
    file = request.files["file"]
    data = file.read()
    filename = file.filename
    user_id = session["user_id"]
    file_id = "".join(random.choices(string.hexdigits.lower(), k=16))
    blocks_meta = []

    for i in range(0, len(data), BLOCK_SIZE):
        block_data = data[i:i+BLOCK_SIZE]
        block_id = f"{file_id}_{i//BLOCK_SIZE}"
        nodes = pick_nodes()
        success = all(get_stub(n).StoreBlock(storage_pb2.StoreRequest(block_id=block_id, data=block_data)).success for n in nodes)
        if not success:
            return jsonify(success=False, message="Failed to store block"), 500
        blocks_meta.append({"id": block_id, "nodes": nodes})

    c.execute("INSERT INTO files (user_id, filename, size, blocks) VALUES (?, ?, ?, ?)",
              (user_id, filename, len(data), json.dumps(blocks_meta)))
    conn.commit()
    return jsonify(success=True, message="Uploaded")

@app.route("/files")
def files():
    if "user_id" not in session:
        return jsonify(success=False), 401
    c.execute("SELECT filename FROM files WHERE user_id=?", (session["user_id"],))
    return jsonify(files=[row[0] for row in c.fetchall()])

@app.route("/download/<filename>")
def download(filename):
    if "user_id" not in session:
        return "Login required", 401
    c.execute("SELECT blocks, size FROM files WHERE user_id=? AND filename=?", (session["user_id"], filename))
    row = c.fetchone()
    if not row: return "File not found", 404
    blocks_meta, total_size = json.loads(row[0]), row[1]
    result = bytearray(total_size)
    for meta in blocks_meta:
        block_id = meta["id"]
        for node in meta["nodes"]:
            try:
                resp = get_stub(node).GetBlock(storage_pb2.GetRequest(block_id=block_id))
                if resp.success:
                    offset = int(block_id.split("_")[-1]) * BLOCK_SIZE
                    result[offset:offset+len(resp.data)] = resp.data
                    break
            except:
                continue
        else:
            return "Could not retrieve all blocks", 500
    return send_file(
        bytes(result),
        200,
        {
            "Content-Type": "application/octet-stream",
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

@app.route("/delete/<filename>", methods=["POST"])
def delete(filename):
    if "user_id" not in session:
        return jsonify(success=False), 401
    c.execute("SELECT blocks FROM files WHERE user_id=? AND filename=?", (session["user_id"], filename))
    row = c.fetchone()
    if row:
        for meta in json.loads(row[0]):
            for node in meta["nodes"]:
                try:
                    get_stub(node).DeleteBlock(storage_pb2.DeleteRequest(block_id=meta["id"]))
        c.execute("DELETE FROM files WHERE user_id=? AND filename=?", (session["user_id"], filename))
        conn.commit()
    return jsonify(success=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)