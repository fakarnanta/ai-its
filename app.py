from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, desc
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, emit, join_room 
import random
import sys
import os
import google.generativeai as genai
from datetime import datetime

# Import Data Awal
try:
    from soal_bank import SOAL_BANK
except ImportError:
    print("FATAL: soal_bank.py tidak ditemukan.")
    sys.exit()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'kunci_rahasia_gamifikasi_its_v2'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///its_gamified.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*") 

# --- GLOBAL STATE UNTUK TOURNAMENT ---
TOURNAMENT_STATE = {
    "is_active": False,
    "host_sid": None,
    "players": {}, 
    "questions": [], 
    "current_q_index": 0
}

# --- MODEL DATABASE ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    score = db.Column(db.Integer, default=0) # Skor Latihan Sendiri
    tournament_score = db.Column(db.Integer, default=0) # [BARU] Skor Tournament
    answers = db.relationship('UserAnswer', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    folder_name = db.Column(db.String(50)) 
    content = db.Column(db.Text, nullable=False)
    options = db.Column(db.Text, nullable=False)
    correct_key = db.Column(db.String(100), nullable=False)
    difficulty_label = db.Column(db.String(20)) 
    total_attempts = db.Column(db.Integer, default=0)
    total_correct = db.Column(db.Integer, default=0)

class UserAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False)
    points_earned = db.Column(db.Integer, default=0) 
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    question = db.relationship('Question')

# --- SEEDING DATA ---
def seed_database():
    print("Memeriksa pembaruan bank soal...")
    jumlah_baru = 0
    for materi, level_dict in SOAL_BANK.items():
        folder_nama = materi 
        for level, list_soal in level_dict.items():
            for item in list_soal:
                cek_soal = Question.query.filter_by(content=item['soal']).first()
                if not cek_soal:
                    opsi_str = "|".join(item['opsi'])
                    q = Question(
                        folder_name=folder_nama,
                        content=item['soal'],
                        options=opsi_str,
                        correct_key=item['kunci'],
                        difficulty_label=level
                    )
                    db.session.add(q)
                    jumlah_baru += 1
    if jumlah_baru > 0:
        db.session.commit()
        print(f"BERHASIL: Menambahkan {jumlah_baru} soal baru ke Database!")

# --- LOGIC SCORING ---
def calculate_score_change(question_obj, is_correct):
    if question_obj.total_attempts == 0:
        win_rate = 0.5
    else:
        win_rate = question_obj.total_correct / question_obj.total_attempts
    
    base_poin = 10
    difficulty_bonus = 20
    if is_correct:
        return base_poin + int((1 - win_rate) * difficulty_bonus)
    else:
        penalty_base = 5
        return -(penalty_base + int(win_rate * 10))

# ==========================================
# === SOCKET.IO EVENTS (LOGIKA TOURNAMENT) ===
# ==========================================

@socketio.on('join_tournament')
def handle_join(data):
    username = data['username']
    current_sid = request.sid
    
    role = 'player'
    if TOURNAMENT_STATE['host_sid'] is None:
        TOURNAMENT_STATE['host_sid'] = current_sid
        role = 'host'
    
    TOURNAMENT_STATE['players'][current_sid] = {'username': username, 'score': 0, 'role': role}
    join_room('tournament_room')
    
    emit('set_role', {'role': role, 'username': username})
    broadcast_player_list()

def broadcast_player_list():
    player_list = []
    for p in TOURNAMENT_STATE['players'].values():
        badge = " (HOST)" if p['role'] == 'host' else ""
        player_list.append(p['username'] + badge)
    emit('update_players', {'players': player_list}, room='tournament_room')

@socketio.on('start_game')
def handle_start():
    if request.sid != TOURNAMENT_STATE['host_sid']: return

    if not TOURNAMENT_STATE['is_active']:
        all_q = Question.query.all()
        selected_q = random.sample(all_q, min(len(all_q), 5))
        
        q_data = []
        for q in selected_q:
            opsi = q.options.split('|')
            random.shuffle(opsi)
            q_data.append({
                'id': q.id, 'soal': q.content, 'opsi': opsi, 'kunci_rahasia': q.correct_key
            })
            
        TOURNAMENT_STATE['questions'] = q_data
        TOURNAMENT_STATE['is_active'] = True
        TOURNAMENT_STATE['current_q_index'] = 0
        send_next_question()

def send_next_question():
    idx = TOURNAMENT_STATE['current_q_index']
    if idx < len(TOURNAMENT_STATE['questions']):
        q = TOURNAMENT_STATE['questions'][idx]
        emit('new_question', {
            'soal': q['soal'], 'opsi': q['opsi'], 
            'nomor': idx + 1, 'total': len(TOURNAMENT_STATE['questions'])
        }, room='tournament_room')
    else:
        sorted_players = sorted(TOURNAMENT_STATE['players'].values(), key=lambda x: x['score'], reverse=True)
        emit('game_over', {'leaderboard': sorted_players}, room='tournament_room')
        TOURNAMENT_STATE['is_active'] = False
        TOURNAMENT_STATE['questions'] = []

@socketio.on('submit_answer_live')
def handle_answer_live(data):
    idx = TOURNAMENT_STATE['current_q_index']
    if idx >= len(TOURNAMENT_STATE['questions']): return

    current_q = TOURNAMENT_STATE['questions'][idx]
    user_ans = data['answer']
    is_correct = (user_ans.lower() == current_q['kunci_rahasia'].lower())
    
    if is_correct:
        # Update RAM Score (Untuk Live View)
        points = 10
        TOURNAMENT_STATE['players'][request.sid]['score'] += points
        
        # Update DATABASE Score (Untuk Leaderboard Permanen)
        username = TOURNAMENT_STATE['players'][request.sid]['username']
        user_db = User.query.filter_by(username=username).first()
        if user_db:
            user_db.tournament_score += points
            db.session.commit()

        emit('feedback', {'msg': 'Benar! +10 Poin', 'correct': True})
    else:
        emit('feedback', {'msg': 'Salah!', 'correct': False})
    
    players_data = list(TOURNAMENT_STATE['players'].values())
    emit('live_score_update', {'players': players_data}, room='tournament_room')

@socketio.on('admin_next_question')
def handle_next():
    if request.sid != TOURNAMENT_STATE['host_sid']: return
    TOURNAMENT_STATE['current_q_index'] += 1
    send_next_question()

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in TOURNAMENT_STATE['players']:
        del TOURNAMENT_STATE['players'][request.sid]
        if request.sid == TOURNAMENT_STATE['host_sid']:
            TOURNAMENT_STATE['host_sid'] = None 
        broadcast_player_list()

# ==========================================
# === FLASK ROUTES ===
# ==========================================

@app.route('/')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    return render_template('dashboard.html', user=user)

@app.route('/materi')
def materi():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    bank_data_path = os.path.join(os.path.dirname(__file__), 'bank_data')
    if os.path.exists(bank_data_path):
        bank_files = [f for f in os.listdir(bank_data_path) if f.endswith('.py') and f.startswith('osk')]
    else:
        bank_files = []

    return render_template('materi.html', folders=bank_files)

@app.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        message = request.json['message']
        
        # Cek jika API key sudah diatur
        if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
            return jsonify({'reply': 'Error: API Key Gemini belum diatur oleh developer.'})
            
        try:
            response = model.generate_content(message)
            return jsonify({'reply': response.text})
        except Exception as e:
            return jsonify({'reply': f'Maaf, terjadi error: {e}'})

    return render_template('chatbot.html')

@app.route('/tournament')
def tournament_lobby():
    if 'user_id' not in session: return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))
    return render_template('tournament.html', username=user.username)

@app.route('/quiz/folder/<folder_name>')
def quiz_folder(folder_name):
    if 'user_id' not in session: return redirect(url_for('login'))
    user_id = session['user_id']
    questions = Question.query.filter_by(folder_name=folder_name).all()
    if not questions: return redirect(url_for('dashboard'))
    q_ids = [q.id for q in questions]
    
    answered_q_ids = db.session.query(UserAnswer.question_id).filter(
        UserAnswer.user_id == user_id, UserAnswer.question_id.in_(q_ids)).all()
    answered_ids_set = {x[0] for x in answered_q_ids}
    remaining_ids = [qid for qid in q_ids if qid not in answered_ids_set]

    if not remaining_ids:
        history = UserAnswer.query.filter(UserAnswer.user_id == user_id, UserAnswer.question_id.in_(q_ids)).all()
        score_total = sum(h.points_earned for h in history)
        benar_total = sum(1 for h in history if h.is_correct)
        return render_template('finished.html', folder=folder_name, score=score_total, benar=benar_total, total=len(q_ids))

    next_id = random.choice(remaining_ids)
    q = Question.query.get(next_id)
    return render_quiz(q, mode="folder")

@app.route('/reset_folder/<folder_name>')
def reset_folder(folder_name):
    if 'user_id' not in session: return redirect(url_for('login'))
    user_id = session['user_id']
    questions = Question.query.filter_by(folder_name=folder_name).all()
    q_ids = [q.id for q in questions]
    if q_ids:
        UserAnswer.query.filter(UserAnswer.user_id == user_id, UserAnswer.question_id.in_(q_ids)).delete(synchronize_session=False)
        db.session.commit()
    return redirect(url_for('quiz_folder', folder_name=folder_name))

@app.route('/quiz/mistakes')
def quiz_mistakes():
    if 'user_id' not in session: return redirect(url_for('login'))
    user_id = session['user_id']
    wrong_answers = db.session.query(UserAnswer, Question).join(Question).filter(UserAnswer.user_id == user_id).all()
    status_map = {}
    for ans, q_data in wrong_answers:
        status_map[ans.question_id] = {'status': ans.is_correct, 'data': q_data}
    soal_masih_salah = [val['data'] for val in status_map.values() if val['status'] is False]
    
    if not soal_masih_salah:
        return render_template('dashboard.html', user=User.query.get(user_id), 
                             folders=[f[0] for f in db.session.query(Question.folder_name).distinct()], 
                             error="Hebat! Tidak ada soal review. Semua soal sudah kamu perbaiki! 🎉")
    
    EPSILON = 0.3
    if random.random() < EPSILON:
        chosen_q = random.choice(soal_masih_salah)
    else:
        def get_win_rate(q): return 0.5 if q.total_attempts == 0 else q.total_correct / q.total_attempts
        soal_masih_salah.sort(key=get_win_rate)
        chosen_q = soal_masih_salah[0]
    return render_quiz(chosen_q, mode="mistake")

def render_quiz(question, mode):
    opsi = question.options.split('|')
    random.shuffle(opsi)
    data = {'id': question.id, 'soal': question.content, 'opsi': opsi, 'materi': question.folder_name, 'kesulitan': question.difficulty_label, 'mode': mode}
    return render_template('quiz.html', question=data)

@app.route('/submit_answer', methods=['POST'])
def submit_answer():
    if 'user_id' not in session: return jsonify({'error': 'Login required'}), 401
    data = request.json
    user = User.query.get(session['user_id'])
    q_db = Question.query.get(data['question_id'])
    user_ans = data['answer'].strip().lower()
    correct_ans = q_db.correct_key.strip().lower()
    is_correct = (user_ans == correct_ans)
    poin_change = calculate_score_change(q_db, is_correct)
    user.score += poin_change
    q_db.total_attempts += 1
    if is_correct: q_db.total_correct += 1
    new_history = UserAnswer(user_id=user.id, question_id=q_db.id, is_correct=is_correct, points_earned=poin_change)
    db.session.add(new_history)
    db.session.commit()
    mode = data.get('mode', 'folder')
    next_url = url_for('quiz_folder', folder_name=q_db.folder_name) if mode == 'folder' else url_for('quiz_mistakes')
    return jsonify({'result': 'correct' if is_correct else 'incorrect', 'poin_change': poin_change, 'total_score': user.score, 'correct_answer': q_db.correct_key, 'next_url': next_url})

# --- LEADERBOARD UPDATE (TAMBAH MODE TOURNAMENT) ---
@app.route('/leaderboard')
def leaderboard():
    selected_folder = request.args.get('folder')
    folders = [f[0] for f in db.session.query(Question.folder_name).distinct().all()]
    
    title = "🏆 Global Leaderboard"
    leaderboard_data = []

    if selected_folder == "Tournament":
        # Mode Tournament: Ambil kolom tournament_score dari tabel User
        top_users = User.query.order_by(User.tournament_score.desc()).limit(20).all()
        leaderboard_data = [{'username': u.username, 'score': u.tournament_score} for u in top_users]
        title = "⚔️ Tournament Ranking"
        
    elif selected_folder and selected_folder != "Global":
        # Mode Per Folder: Hitung manual dari UserAnswer
        results = db.session.query(User.username, func.sum(UserAnswer.points_earned).label('total_score')
        ).join(UserAnswer).join(Question).filter(Question.folder_name == selected_folder
        ).group_by(User.id).order_by(desc('total_score')).limit(20).all()
        leaderboard_data = [{'username': r[0], 'score': r[1] or 0} for r in results]
        title = f"📂 Rank: {selected_folder}"
        
    else:
        # Mode Global (Default)
        top_users = User.query.order_by(User.score.desc()).limit(20).all()
        leaderboard_data = [{'username': u.username, 'score': u.score} for u in top_users]
        selected_folder = "Global"

    return render_template('leaderboard.html', users=leaderboard_data, folders=folders, current_filter=selected_folder, title=title)

@app.route('/history')
def history():
    if 'user_id' not in session: return redirect(url_for('login'))
    correct_answers = UserAnswer.query.filter_by(user_id=session['user_id'], is_correct=True).order_by(UserAnswer.timestamp.desc()).all()
    history_data = []
    seen_ids = set()
    for ans in correct_answers:
        if ans.question_id not in seen_ids:
            q = ans.question
            wr = int((q.total_correct/q.total_attempts)*100) if q.total_attempts > 0 else 0
            history_data.append({'soal': q.content, 'kunci': q.correct_key, 'folder': q.folder_name, 'wr': f"{wr}%"})
            seen_ids.add(ans.question_id)
    return render_template('history.html', history=history_data)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            session['user_id'] = user.id
            return redirect(url_for('dashboard'))
        return render_template('auth.html', action='login', error="Login Gagal")
    return render_template('auth.html', action='login')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        if User.query.filter_by(username=request.form['username']).first():
            return render_template('auth.html', action='register', error="Username ada")
        user = User(username=request.form['username'])
        user.set_password(request.form['password'])
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('auth.html', action='register')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    if not os.path.exists('its_gamified.db'):
        with app.app_context():
            db.create_all()
            seed_database()
    else:
        with app.app_context():
            seed_database()
            
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)