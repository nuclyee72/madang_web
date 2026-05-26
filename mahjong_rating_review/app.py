from flask import Flask, Blueprint, jsonify, render_template, request
import sqlite3
import os
import json
import datetime
import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 외부(madang_web)에서 경로를 주입받을 수 있도록 모듈 레벨 변수로 분리
DB_PATH = os.path.join(BASE_DIR, "games.db")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
CLUB_NAME = "<동아리명>"

def get_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def configure(db_path=None, config_path=None, club_name=None):
    """외부 프로젝트(madang_web 등)에서 DB/Config 경로와 동아리명을 주입할 때 사용합니다."""
    global DB_PATH, CONFIG_PATH, CLUB_NAME
    if db_path:
        DB_PATH = db_path
    if config_path:
        CONFIG_PATH = config_path
    if club_name:
        CLUB_NAME = club_name

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# 결산용 Blueprint 생성 (절대 경로 지정으로 TemplateNotFound 방지)
review_bp = Blueprint(
    'review', 
    __name__, 
    template_folder=os.path.join(BASE_DIR, 'templates'), 
    static_folder=os.path.join(BASE_DIR, 'static')
)

@review_bp.route("/")
def index_page():
    # 간단한 테스트 쿼리 (총 게임 수)
    conn = get_db()
    try:
        cur = conn.execute("SELECT COUNT(*) as count FROM games")
        total_games = cur.fetchone()["count"]
    except Exception:
        total_games = 0
    finally:
        conn.close()

    return render_template("review_index.html", club_name=CLUB_NAME, total_games=total_games)

# API: 전체 시즌 결산 데이터
@review_bp.route("/api/summary/global")
def get_global_summary():
    conn = get_db()
    try:
        # 이번 시즌 게임 목록
        cur = conn.execute("SELECT created_at, player1_name, player2_name, player3_name, player4_name FROM games")
        games = cur.fetchall()
        
        total_games = len(games)
        
        # 이번 시즌 참여 인원
        players = set()
        day_of_week_counts = [0] * 7 # 월(0) ~ 일(6)
        month_counts = {}
        late_night = 0
        normal_time = 0
        
        exam_dates = set()
        normal_dates = set()
        exam_games = 0
        normal_games = 0

        config_data = get_config()
        review_config = config_data.get("REVIEW_CONFIG", {})

        # 시험기간 정의 (config.json에서 불러오기, 없으면 기본값)
        exam_ranges = review_config.get("EXAM_PERIODS", [
            ["04-15", "04-30"], # 1학기 중간
            ["06-08", "06-21"], # 1학기 기말
            ["10-15", "10-31"], # 2학기 중간
            ["12-08", "12-21"], # 2학기 기말
        ])

        def is_exam_period(md):
            for start, end in exam_ranges:
                if start <= md <= end:
                    return True
            return False

        for g in games:
            players.add(g["player1_name"])
            players.add(g["player2_name"])
            players.add(g["player3_name"])
            players.add(g["player4_name"])
            
            # 시간 파싱 (예: 2026-05-26T15:00)
            created_at = g["created_at"]
            if len(created_at) >= 16:
                try:
                    dt = datetime.datetime.fromisoformat(created_at)
                except ValueError:
                    dt = None
            else:
                dt = None
            
            if dt:
                day_of_week_counts[dt.weekday()] += 1
                month_key = dt.strftime("%Y-%m")
                month_counts[month_key] = month_counts.get(month_key, 0) + 1
                
                # 밤샘 마작 (00:00 ~ 05:59)
                if 0 <= dt.hour < 6:
                    late_night += 1
                else:
                    normal_time += 1
                
                # 시험기간 여부
                md = dt.strftime("%m-%d")
                date_str = dt.strftime("%Y-%m-%d")
                if is_exam_period(md):
                    exam_games += 1
                    exam_dates.add(date_str)
                else:
                    normal_games += 1
                    normal_dates.add(date_str)

        total_players = len(players)

        # config에 정의된 아카이브 데이터 수집 (비교용)
        compare_archives = review_config.get("COMPARE_ARCHIVES", [])
        archive_stats = []
        for arch_name in compare_archives:
            cur = conn.execute("SELECT id, name FROM archives WHERE name = ?", (arch_name,))
            row = cur.fetchone()
            if row:
                arch_id = row["id"]
                c2 = conn.execute("SELECT COUNT(*) as count FROM archive_games WHERE archive_id = ?", (arch_id,))
                cnt = c2.fetchone()["count"]
                archive_stats.append({"name": arch_name, "total_games": cnt})

        # 시험기간 vs 일반기간 일평균
        avg_exam = exam_games / len(exam_dates) if exam_dates else 0
        avg_normal = normal_games / len(normal_dates) if normal_dates else 0

        return jsonify({
            "ok": True,
            "total_games": total_games,
            "archive_stats": archive_stats,
            "total_players": total_players,
            "day_of_week": day_of_week_counts,
            "month_counts": month_counts,
            "time_distribution": {"late_night": late_night, "normal": normal_time},
            "exam_stats": {
                "avg_exam": round(avg_exam, 1),
                "avg_normal": round(avg_normal, 1)
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        conn.close()
# API: 개인별 시즌 결산 데이터
@review_bp.route("/api/summary/player/<name>")
def get_player_summary(name):
    conn = get_db()
    try:
        # 개인의 모든 게임 가져오기 (시간순 정렬 중요)
        cur = conn.execute("""
            SELECT * FROM games 
            WHERE player1_name = ? OR player2_name = ? OR player3_name = ? OR player4_name = ?
            ORDER BY created_at ASC
        """, (name, name, name, name))
        games = cur.fetchall()

        if not games:
            return jsonify({"ok": False, "error": "해당 플레이어의 기록이 없습니다."}), 404

        total_games = len(games)
        
        # 1. 날짜별 집계 및 출석 연승
        date_counts = {}
        for g in games:
            dt_str = g["created_at"][:10] # YYYY-MM-DD
            date_counts[dt_str] = date_counts.get(dt_str, 0) + 1
            
        most_played_date = max(date_counts.items(), key=lambda x: x[1]) if date_counts else ("", 0)

        # 연속 출석일 계산
        sorted_dates = sorted(list(date_counts.keys()))
        max_attendance_streak = 1
        current_attendance_streak = 1
        for i in range(1, len(sorted_dates)):
            d1 = datetime.datetime.strptime(sorted_dates[i-1], "%Y-%m-%d").date()
            d2 = datetime.datetime.strptime(sorted_dates[i], "%Y-%m-%d").date()
            if (d2 - d1).days == 1:
                current_attendance_streak += 1
                if current_attendance_streak > max_attendance_streak:
                    max_attendance_streak = current_attendance_streak
            else:
                current_attendance_streak = 1

        # 2. 게임별 성적 및 연속 기록 계산
        max_score = -99999
        bankrupt_count = 0
        
        # Streak tracking
        max_1st_streak = 0
        cur_1st_streak = 0
        
        max_yonde_streak = 0 # 1,2등
        cur_yonde_streak = 0
        
        max_4th_streak = 0
        cur_4th_streak = 0
        
        max_avoid_4th_streak = 0 # 4등 아님
        cur_avoid_4th_streak = 0
        
        # 3. 상성 분석 (같이 친 사람)
        co_players = {} # name -> {"games": 0, "my_rank_sum": 0, "their_rank_sum": 0}
        
        # 점수에 따른 등수 판별 로직
        def get_ranks(g):
            p = [
                (g["player1_name"], g["player1_score"]),
                (g["player2_name"], g["player2_score"]),
                (g["player3_name"], g["player3_score"]),
                (g["player4_name"], g["player4_score"])
            ]
            p.sort(key=lambda x: x[1], reverse=True) # 점수 내림차순
            ranks = {}
            for idx, (pname, pscore) in enumerate(p):
                ranks[pname] = idx + 1
            return ranks

        for g in games:
            ranks = get_ranks(g)
            my_rank = ranks[name]
            my_score = 0
            
            # 내 점수 찾기
            if g["player1_name"] == name: my_score = g["player1_score"]
            elif g["player2_name"] == name: my_score = g["player2_score"]
            elif g["player3_name"] == name: my_score = g["player3_score"]
            elif g["player4_name"] == name: my_score = g["player4_score"]
            
            if my_score > max_score:
                max_score = my_score
            if my_score < 0:
                bankrupt_count += 1
                
            # 연속 기록 업데이트
            if my_rank == 1:
                cur_1st_streak += 1
                max_1st_streak = max(max_1st_streak, cur_1st_streak)
            else:
                cur_1st_streak = 0
                
            if my_rank <= 2:
                cur_yonde_streak += 1
                max_yonde_streak = max(max_yonde_streak, cur_yonde_streak)
            else:
                cur_yonde_streak = 0
                
            if my_rank == 4:
                cur_4th_streak += 1
                max_4th_streak = max(max_4th_streak, cur_4th_streak)
                cur_avoid_4th_streak = 0
            else:
                cur_avoid_4th_streak += 1
                max_avoid_4th_streak = max(max_avoid_4th_streak, cur_avoid_4th_streak)
                cur_4th_streak = 0

            # 상성 계산
            for p in ["player1_name", "player2_name", "player3_name", "player4_name"]:
                other_name = g[p]
                if other_name != name:
                    if other_name not in co_players:
                        co_players[other_name] = {"games": 0, "my_rank_sum": 0, "their_rank_sum": 0}
                    co_players[other_name]["games"] += 1
                    co_players[other_name]["my_rank_sum"] += my_rank
                    co_players[other_name]["their_rank_sum"] += ranks[other_name]

        bankrupt_rate = (bankrupt_count / total_games) * 100 if total_games > 0 else 0

        # 상성 분석 정리
        most_played = []
        for p_name, p_data in co_players.items():
            avg_my = p_data["my_rank_sum"] / p_data["games"]
            avg_their = p_data["their_rank_sum"] / p_data["games"]
            most_played.append({
                "name": p_name,
                "games": p_data["games"],
                "my_avg_rank": round(avg_my, 2),
                "their_avg_rank": round(avg_their, 2),
                "win_gap": round(avg_their - avg_my, 2) # 양수면 내가 더 잘함
            })
        
        # 많이 같이 한 사람 순 정렬
        most_played.sort(key=lambda x: x["games"], reverse=True)
        top_co_players = most_played[:5]
        
        # 승률(평균등수 차이) 상성 - 최소 5판 이상 같이 한 사람 기준
        valid_opponents = [p for p in most_played if p["games"] >= 5]
        valid_opponents.sort(key=lambda x: x["win_gap"], reverse=True)
        
        best_opponent = valid_opponents[0] if valid_opponents else None
        worst_opponent = valid_opponents[-1] if valid_opponents else None

        # 4. 뱃지 가져오기
        badges = []
        try:
            # 테이블이 존재할 경우에만
            cur = conn.execute("""
                SELECT b.name, b.description, b.grade
                FROM player_badges pb
                JOIN badges b ON pb.badge_id = b.id
                WHERE pb.player_name = ?
            """, (name,))
            badges = [dict(r) for r in cur.fetchall()]
        except sqlite3.OperationalError:
            pass # 테이블 없음 (에러 무시)

        return jsonify({
            "ok": True,
            "total_games": total_games,
            "most_played_date": most_played_date[0],
            "most_played_date_count": most_played_date[1],
            "max_attendance_streak": max_attendance_streak,
            "max_score": max_score,
            "bankrupt_rate": round(bankrupt_rate, 1),
            "streaks": {
                "max_1st": max_1st_streak,
                "max_yonde": max_yonde_streak,
                "max_4th": max_4th_streak,
                "max_avoid_4th": max_avoid_4th_streak
            },
            "top_co_players": top_co_players,
            "best_opponent": best_opponent,
            "worst_opponent": worst_opponent,
            "badges": badges
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        conn.close()

# 단독 실행용 Flask App
app = Flask(__name__)
# 한글 인코딩 처리
app.config['JSON_AS_ASCII'] = False
app.register_blueprint(review_bp, url_prefix="/")

if __name__ == "__main__":
    # 포트 5001을 사용하여 메인 서버(5000)와 충돌 방지
    app.run(host="0.0.0.0", port=5001, debug=True)
