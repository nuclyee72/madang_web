from flask import Flask, Blueprint, request, jsonify, render_template, Response, redirect, url_for, session
from flask_cors import CORS
import sqlite3
from datetime import datetime
import os
import sys
import secrets
import importlib.util
from functools import wraps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CLUB_NAME = "그릴마당"  # 동아리 이름 (변경 가능)

SCHEDULE_DB_PATH = os.path.join(BASE_DIR, "schedules.db")
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")


def _get_or_create_secret(path, label):
    """secret 파일이 있으면 읽고, 없으면 새로 생성해서 저장합니다 (instance/ 는 git에 커밋되지 않음)."""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            value = f.read().strip()
        if value:
            return value
    os.makedirs(os.path.dirname(path), exist_ok=True)
    value = secrets.token_urlsafe(16)
    with open(path, "w", encoding="utf-8") as f:
        f.write(value)
    print(f"[INFO] {label}이(가) 없어 새로 생성했습니다 → {path}")
    print(f"[INFO] {label}: {value}")
    return value


# 사이트 전역 관리자 비밀번호 (환경변수 우선, 없으면 instance/ 에 자동 생성)
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or _get_or_create_secret(
    os.path.join(INSTANCE_DIR, "admin_password.txt"), "관리자 비밀번호"
)


def get_schedule_db():
    conn = sqlite3.connect(SCHEDULE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_schedule_db():
    conn = get_schedule_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            date TEXT NOT NULL,
            time_start TEXT,
            time_end TEXT,
            location TEXT,
            description TEXT,
            requester_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── 마작 레이팅 서브모듈 import ──
# importlib을 사용해 파일 경로로 직접 import (이름 충돌 방지)
_mahjong_spec = importlib.util.spec_from_file_location(
    "mahjong_app",
    os.path.join(BASE_DIR, "mahjong_rating_site", "app.py")
)
mahjong_module = importlib.util.module_from_spec(_mahjong_spec)
_mahjong_spec.loader.exec_module(mahjong_module)

mahjong_module.configure(
    db_path=os.path.join(BASE_DIR, "games.db"),
    config_path=os.path.join(BASE_DIR, "config.json"),
    club_name=CLUB_NAME,
    admin_password=ADMIN_PASSWORD,
)
mahjong_module.init_db()

mahjong_bp = mahjong_module.mahjong_bp



app = Flask(__name__, static_folder="static", template_folder="templates")
# 한글 등 비아스키 문자 처리를 위해
app.config['JSON_AS_ASCII'] = False
# HTML 템플릿 자동 리로드 (파일 수정 시 서버 재시작 없이 반영)
app.config['TEMPLATES_AUTO_RELOAD'] = True
# 세션(로그인 상태) 서명을 위한 secret key
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or _get_or_create_secret(
    os.path.join(INSTANCE_DIR, "flask_secret.key"), "Flask SECRET_KEY"
)


def require_admin_page(f):
    """세션에 로그인된 관리자만 통과. 브라우저로 직접 여는 페이지 라우트용
    (미인증 시 로그인 페이지로 리다이렉트)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


def require_admin_api(f):
    """세션에 로그인된 관리자만 통과. fetch()로 호출되는 JSON API 라우트용
    (미인증 시 401 JSON을 반환)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return jsonify({"error": "관리자 로그인이 필요합니다."}), 401
        return f(*args, **kwargs)
    return wrapper

# 일정 캘린더 서브 앱 Blueprint
schedule_bp = Blueprint('schedule', __name__)


@app.context_processor
def inject_club_name():
    cfg = mahjong_module.get_config()
    return dict(club_name=CLUB_NAME, config=cfg)


CORS(app)
init_schedule_db()


# ================== 기본 페이지 ==================

@app.route("/")
def landing_page():
    return render_template("landing.html", club_name=CLUB_NAME)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    next_url = request.args.get("next") or request.form.get("next") or url_for("landing_page")
    if request.method == "POST":
        pw = request.form.get("password", "")
        if pw == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(next_url)
        error = "비밀번호가 올바르지 않습니다."
    return render_template("admin_login.html", club_name=CLUB_NAME, error=error, next_url=next_url)


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("landing_page"))


# ================== 동아리 일정 관리 (schedule) ==================

@schedule_bp.route("/")
def schedule_page():
    return render_template("schedule.html", club_name=CLUB_NAME)


@schedule_bp.route("/admin")
@require_admin_page
def schedule_admin_page():
    return render_template("schedule_admin.html", club_name=CLUB_NAME)


@schedule_bp.route("/api/events", methods=["GET"])
def get_schedule_events():
    conn = get_schedule_db()
    cur = conn.execute("SELECT * FROM schedules WHERE status = 'confirmed' ORDER BY date ASC, time_start ASC")
    rows = cur.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@schedule_bp.route("/api/pending", methods=["GET"])
@require_admin_api
def get_pending_schedules():
    conn = get_schedule_db()
    cur = conn.execute("SELECT * FROM schedules WHERE status = 'pending' ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@schedule_bp.route("/api/request", methods=["POST"])
def request_schedule():
    try:
        data = request.get_json() or {}
        title = data.get("title", "").strip()
        date = data.get("date", "").strip()
        time_start = data.get("time_start", "").strip()
        time_end = data.get("time_end", "").strip()
        location = data.get("location", "").strip()
        description = data.get("description", "").strip()
        requester = data.get("requester_name", "").strip()

        if not title or not date or not requester:
            return jsonify({"error": "필수 입력 항목(제목, 날짜, 신청자 이름)이 누락되었습니다."}), 400

        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = get_schedule_db()
        try:
            conn.execute(
                "INSERT INTO schedules (title, date, time_start, time_end, location, description, requester_name, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                (title, date, time_start, time_end, location, description, requester, created_at)
            )
            conn.commit()
        finally:
            conn.close()

        return jsonify({"ok": True, "message": "일정 신청이 완료되었습니다."})
    except Exception as e:
        print(f"Error in request_schedule: {e}")
        return jsonify({"error": str(e)}), 500


@schedule_bp.route("/api/confirm/<int:schedule_id>", methods=["PUT"])
@require_admin_api
def confirm_schedule(schedule_id):
    conn = get_schedule_db()
    conn.execute("UPDATE schedules SET status = 'confirmed' WHERE id = ?", (schedule_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@schedule_bp.route("/api/<int:schedule_id>", methods=["DELETE"])
@require_admin_api
def delete_schedule(schedule_id):
    conn = get_schedule_db()
    conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


app.register_blueprint(mahjong_bp, url_prefix="/mahjong_rating")
app.register_blueprint(schedule_bp, url_prefix="/schedule")

s1_review_bp = Blueprint('s1_review', __name__,
                         static_url_path='',
                         static_folder=os.path.join(BASE_DIR, "s1_mahjong_result_presentation", "web"))

@s1_review_bp.route("/")
def s1_review_index():
    return s1_review_bp.send_static_file("index.html")

app.register_blueprint(s1_review_bp, url_prefix="/s1_review")



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
