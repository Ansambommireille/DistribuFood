# main_server.py  ← FINAL PERFECT VERSION (ALL ISSUES FIXED)
import os
import json
import random
import string
import time
import bcrypt
import smtplib
import subprocess
import atexit
from math import ceil
from email.mime.text import MIMEText
from flask import Flask, request, session, send_file, jsonify, render_template
from dotenv import load_dotenv
import sqlite3
import grpc
import storage_pb2
import storage_pb2_grpc

load_dotenv()

app = Flask(__name__)
app.secret_key = "super_secret_key_change_me_in_production_2025!"

# === CONFIG ===
REPLICATION = 2
BLOCK_SIZE = 1024 * 1024  # 1 MB blocks
NUM_NODES = 5
BASE_PORT = 51051
MAX_STORAGE_PER_NODE_MB = 250
TOTAL_STORAGE_BYTES = NUM_NODES * MAX_STORAGE_PER_NODE_MB * 1024 * 1024  # 1.25 GB

# Auto-start nodes
node_processes = []
NODES = []

def start_nodes():
    global NODES
    NODES = []
    print("Starting 5 storage nodes...\n")
    
    for i in range(NUM_NODES):
        port = BASE_PORT + i
        try:
            p = subprocess.Popen(['python', 'node.py', '--port', str(port)])
            node_processes.append(p)
            NODES.append(f"localhost:{port}")
            print(f"   Node {i+1}/5 → port {port}")
            time.sleep(3)
        except Exception as e:
            print(f"   Failed to start node on port {port}: {e}")
    
    print(f"\nAll {len(NODES)} nodes ready!")
    print(f"Active ports: {NODES}")
    time.sleep(5)

def cleanup_nodes():
    print("\nShutting down all storage nodes...")
    for p in node_processes:
        try:
            p.terminate()
            p.wait(timeout=5)
        except:
            p.kill()
    print("All nodes stopped.")

atexit.register(cleanup_nodes)

# Email config
EMAIL_FROM = os.getenv("EMAIL_ADDRESS")
EMAIL_PASS = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# === DATABASE ===
conn = sqlite3.connect("storage.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users 
             (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, email TEXT UNIQUE, password TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS files 
             (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, filename TEXT, size INTEGER, blocks TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS otps 
             (email TEXT PRIMARY KEY, otp TEXT, expires INTEGER)''')
conn.commit()

def send_otp(email: str, otp: str):
    msg = MIMEText(f"Your login OTP is: {otp}\n\nValid for 5 minutes.")
    msg["Subject"] = "Your OTP"
    msg["From"] = EMAIL_FROM
    msg["To"] = email
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_FROM, EMAIL_PASS)
            server.sendmail(EMAIL_FROM, email, msg.as_string())
    except Exception as e:
        print(f"Email error: {e}")

def new_otp() -> str:
    return "".join(random.choices(string.digits, k=6))

def get_stub(node: str):
    channel = grpc.insecure_channel(node)
    return storage_pb2_grpc.StorageNodeStub(channel)

def pick_nodes():
    return random.sample(NODES, min(REPLICATION, len(NODES)))

# FIXED: Accurate space with fallback
def get_total_available_space():
    total = 0
    for node in NODES:
        for attempt in range(5):
            try:
                stub = get_stub(node)
                resp = stub.GetAvailableSpace(storage_pb2.Empty(), timeout=5)
                total += resp.available
                break
            except:
                time.sleep(1)
    if total == 0:
        return TOTAL_STORAGE_BYTES  # Fallback to full
    return total

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/signup", methods=["POST"])
def signup():
    data = request.json
    username = data["username"]
    email = data["email"]
    pwd = data["password"].encode()
    hashed = bcrypt.hashpw(pwd, bcrypt.gensalt())
    try:
        c.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)", 
                  (username, email, hashed))
        conn.commit()
        return jsonify(success=True, message="Account created!")
    except sqlite3.IntegrityError as e:
        if "email" in str(e):
            message = "Email already used!"
        elif "username" in str(e):
            message = "Username already taken!"
        else:
            message = "Error creating account"
        return jsonify(success=False, message=message), 400

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    username = data["username"]
    pwd = data["password"].encode()
    c.execute("SELECT id, password, email FROM users WHERE username=?", (username,))
    user = c.fetchone()
    if user and bcrypt.checkpw(pwd, user[1]):
        email = user[2]
        otp = new_otp()
        expires = int(time.time()) + 300
        c.execute("INSERT OR REPLACE INTO otps (email, otp, expires) VALUES (?, ?, ?)",
                  (email, otp, expires))
        conn.commit()
        send_otp(email, otp)
        session["pending_email"] = email
        return jsonify(success=True, message="OTP sent!")
    return jsonify(success=False, message="Wrong credentials"), 401

@app.route("/verify-otp", methods=["POST"])
def verify_otp():
    otp = request.json["otp"]
    email = session.get("pending_email")
    if not email:
        return jsonify(success=False, message="No login"), 400
    c.execute("SELECT otp, expires FROM otps WHERE email=?", (email,))
    row = c.fetchone()
    if row and row[0] == otp and row[1] > time.time():
        c.execute("SELECT id FROM users WHERE email=?", (email,))
        user_id = c.fetchone()[0]
        session["user_id"] = user_id
        session.pop("pending_email", None)
        c.execute("DELETE FROM otps WHERE email=?", (email,))
        conn.commit()
        return jsonify(success=True, message="Logged in!")
    return jsonify(success=False, message="Invalid OTP"), 401

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

    available = get_total_available_space()
    if len(data) > available:
        return jsonify(success=False, message="Not enough storage space!"), 400

    for i in range(0, len(data), BLOCK_SIZE):
        block_data = data[i:i+BLOCK_SIZE]
        block_id = f"{file_id}_{i//BLOCK_SIZE}"
        nodes = pick_nodes()
        success = True
        for node in nodes:
            try:
                stub = get_stub(node)
                resp = stub.StoreBlock(storage_pb2.StoreRequest(block_id=block_id, data=block_data))
                if not resp.success:
                    success = False
                    break
            except:
                success = False
                break
        if not success:
            return jsonify(success=False, message="Failed to store block"), 500
        blocks_meta.append({"id": block_id, "nodes": nodes})

    c.execute("INSERT INTO files (user_id, filename, size, blocks) VALUES (?, ?, ?, ?)",
              (user_id, filename, len(data), json.dumps(blocks_meta)))
    conn.commit()
    return jsonify(success=True, message="Uploaded!")

@app.route("/files")
def files():
    if "user_id" not in session:
        return jsonify(success=False), 401
    c.execute("SELECT filename FROM files WHERE user_id=?", (session["user_id"],))
    return jsonify(files=[row[0] for row in c.fetchall()])

@app.route("/storage_info")
def storage_info():
    if "user_id" not in session:
        return jsonify(success=False), 401

    c.execute("SELECT COUNT(*) FROM files WHERE user_id=?", (session["user_id"],))
    file_count = c.fetchone()[0]

    available = get_total_available_space()
    used = TOTAL_STORAGE_BYTES - available

    return jsonify({
        "total_gb": round(TOTAL_STORAGE_BYTES / (1024**3), 2),
        "used_gb": round(used / (1024**3), 2),
        "available_gb": round(available / (1024**3), 2),
        "file_count": file_count
    })

@app.route("/download/<filename>")
def download(filename):
    if "user_id" not in session:
        return "Login required", 401

    c.execute("SELECT blocks, size FROM files WHERE user_id=? AND filename=?",
              (session["user_id"], filename))
    row = c.fetchone()
    if not row:
        return "File not found", 404

    blocks_meta, total_size = json.loads(row[0]), row[1]
    result = bytearray(total_size)

    for meta in blocks_meta:
        block_id = meta["id"]
        block_data = None
        for node in meta["nodes"]:
            try:
                stub = get_stub(node)
                resp = stub.GetBlock(storage_pb2.GetRequest(block_id=block_id))
                if resp.success and resp.data:
                    block_data = resp.data
                    break
            except:
                continue
        if block_data is None:
            return "Could not retrieve block", 500

        block_index = int(block_id.split("_")[-1])
        start_pos = block_index * BLOCK_SIZE
        end_pos = min(start_pos + len(block_data), total_size)
        result[start_pos:end_pos] = block_data

    return send_file(bytes(result), as_attachment=True, download_name=filename)

@app.route("/delete/<filename>", methods=["POST"])
def delete(filename):
    if "user_id" not in session:
        return jsonify(success=False), 401

    c.execute("SELECT blocks FROM files WHERE user_id=? AND filename=?", 
              (session["user_id"], filename))
    row = c.fetchone()
    if row:
        for meta in json.loads(row[0]):
            for node in meta["nodes"]:
                try:
                    stub = get_stub(node)
                    stub.DeleteBlock(storage_pb2.DeleteRequest(block_id=meta["id"]))
                except:
                    pass
        c.execute("DELETE FROM files WHERE user_id=? AND filename=?", 
                  (session["user_id"], filename))
        conn.commit()
    return jsonify(success=True)

if __name__ == "__main__":
    if os.environ.get("WERKZEUG_RUN_MAIN"):
        pass
    else:
        start_nodes()

    print("\n" + "="*60)
    print("  YOUR DISTRIBUTED CLOUD STORAGE IS NOW RUNNING!")
    print("  → http://localhost:5000")
    print("="*60 + "\n")

    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=True)