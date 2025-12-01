from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from collections import Counter
import os
import json
import re
import random
import traceback
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

from config import config
from questions.main_questions import QUESTIONS
from questions.tie_breaker_questions import TIE_BREAKER_QUESTIONS

# -----------------------------
# Google Sheets config
# -----------------------------
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "R1"

# -----------------------------
# Create App
# -----------------------------
def create_app():
    app = Flask(__name__)
    env = os.environ.get('FLASK_ENV', 'default')
    app.config.from_object(config[env])
    app.secret_key = os.environ.get("SECRET_KEY", "123")
    return app

app = create_app()

# -----------------------------
# Google SA Key
# -----------------------------
def get_gspread_client():
    raw = os.environ.get("GCP_SA_KEY")
    if not raw:
        raise RuntimeError("ERROR: GCP_SA_KEY environment variable missing.")
    info = json.loads(raw)
    creds = Credentials.from_service_account_info(info, scopes=SCOPE)
    return gspread.authorize(creds)

# -----------------------------
# Aptitudes & Mapping
# -----------------------------
NEW_APTITUDES = [
    "Logical Reasoning", "Mechanical", "Creative", "Verbal Communication",
    "Numerical", "Social/Helping", "Leadership/Persuasion", "Digital/Computer",
    "Organizing/Structuring", "Writing/Expression", "Scientific", "Spatial/Design"
]

OLD_TO_NEW_APT_MAP = {
    "Analytical": ["Logical Reasoning"],
    "Technical": ["Mechanical"],
    "Spatial": ["Spatial/Design"],
    "Verbal": ["Verbal Communication"],
    "Creative": ["Creative"],
}

KEYWORD_TO_APTS = {
    r"mechanic|machin|tool|repair|operate|equipment|assembly": ["Mechanical", "Spatial/Design"],
    r"design|creative|art|visual|graphic|illustrat|style|compose": ["Creative", "Writing/Expression", "Spatial/Design"],
    r"analy|research|study|evaluate|experiment|data|statistic": ["Logical Reasoning", "Scientific", "Numerical"],
    r"teach|help|support|counsel|mentor|coach": ["Social/Helping", "Verbal Communication"],
    r"lead|manage|supervis|coordinate|direct|influence|persuad": ["Leadership/Persuasion", "Organizing/Structuring"],
    r"software|digital|computer|it|program|code|data entry|excel": ["Digital/Computer", "Organizing/Structuring"],
    r"write|document|report|communicat|present": ["Writing/Expression", "Verbal Communication"],
    r"budget|finance|cost|account|number|math|calculate": ["Numerical"],
}

# -----------------------------
# Session Initialization
# -----------------------------
def initialize_session():
    session['current_question'] = 1
    session['answers'] = {}

    # Only here we initialize empty RIASEC dict
    session['riasec_scores'] = {'R':0,'I':0,'A':0,'S':0,'E':0,'C':0}

    # Tie-breaker
    session['tie_breaker_phase'] = False
    session['tie_breaker_questions'] = []
    session['tie_breaker_pair'] = None
    session['tie_breaker_answered'] = 0

    # Shuffle main questions
    session['shuffled_questions'] = random.sample(QUESTIONS, len(QUESTIONS))
    session['total_questions'] = len(QUESTIONS)

# -----------------------------
# Score Calculation
# -----------------------------
def enrich_from_text(text):
    boosts = Counter()
    if not text or not isinstance(text, str):
        return boosts
    txt = text.lower()
    for patt, apt_list in KEYWORD_TO_APTS.items():
        if re.search(patt, txt):
            for a in apt_list:
                boosts[a] += 1
    return boosts


def calculate_scores(use_text_enrichment=False):
    riasec_scores = {'R':0,'I':0,'A':0,'S':0,'E':0,'C':0}
    aptitude_scores = Counter({a: 0 for a in NEW_APTITUDES})

    main_total = len(QUESTIONS)

    for qnum_key, selected in session.get('answers', {}).items():
        try:
            qnum = int(qnum_key)
        except:
            continue

        if qnum <= main_total:
            question = next((q for q in QUESTIONS if q['number'] == qnum), None)
        else:
            question = next((q for q in TIE_BREAKER_QUESTIONS if q['number'] == qnum), None)

        if not question or selected not in question['options']:
            continue

        option = question['options'][selected]
        q_weight = question.get('weight', 1)

        # RIASEC scoring
        riasec = option.get('riasec')
        if riasec in riasec_scores:
            riasec_scores[riasec] += q_weight

        # Aptitude scoring
        if qnum <= main_total:
            option_apts = option.get('aptitudes', {}) or {}
            for old_key, score in option_apts.items():
                if old_key in OLD_TO_NEW_APT_MAP:
                    for new_key in OLD_TO_NEW_APT_MAP[old_key]:
                        aptitude_scores[new_key] += int(score) * q_weight
                else:
                    if old_key in NEW_APTITUDES:
                        aptitude_scores[old_key] += int(score) * q_weight

            if use_text_enrichment:
                for f in ('explain', 'hint', 'job_text'):
                    if f in question:
                        boosts = enrich_from_text(question[f])
                        for k, v in boosts.items():
                            aptitude_scores[k] += v

    return riasec_scores, dict(aptitude_scores)


def convert_to_percentiles(score_dict):
    if not score_dict:
        return {}
    max_score = max(score_dict.values()) or 1
    return {k: round((v / max_score) * 100, 2) for k, v in score_dict.items()}

# -----------------------------
# Tie-breaker (Option C)
# -----------------------------
RIASEC_ORDER = ['R','I','A','S','E','C']
MAX_TIE_BREAKER_QS = 3

def need_tie_breaker(riasec_scores):
    sorted_scores = sorted(
        riasec_scores.items(),
        key=lambda x: (-x[1], RIASEC_ORDER.index(x[0]))
    )
    (c1, s1), (c2, s2) = sorted_scores[:2]
    return abs(s1 - s2) < 2


def get_tie_breaker_pair(riasec_scores):
    sorted_scores = sorted(
        riasec_scores.items(),
        key=lambda x: (-x[1], RIASEC_ORDER.index(x[0]))
    )
    c1, _ = sorted_scores[0]
    c2, _ = sorted_scores[1]
    return f"{c1}-{c2}"   # Preserve resolver order, not alphabetical


def get_tie_breaker_questions(pair):
    # Pull max 3
    return [q for q in TIE_BREAKER_QUESTIONS if q['pair'] == pair][:MAX_TIE_BREAKER_QS]

# -----------------------------
# Routes
# -----------------------------
@app.route('/')
def index():
    return redirect(url_for('basic_info'))

@app.route('/basic_info')
def basic_info():
    return render_template('basic_info.html')

@app.route('/save_basic_info', methods=['POST'])
def save_basic_info():
    session['user_info'] = {
        'name': request.form.get('name', 'Anonymous'),
        'occupation': request.form.get('occupation', ''),
        'education': request.form.get('education', '')
    }
    initialize_session()
    return redirect(url_for('assessment'))

@app.route('/assessment')
def assessment():

    if 'user_info' not in session:
        return redirect(url_for('basic_info'))

    # -----------------------------
    # MAIN QUESTIONS (1–30)
    # -----------------------------
    if not session.get('tie_breaker_phase', False):

        if session['current_question'] <= len(session['shuffled_questions']):
            q = session['shuffled_questions'][session['current_question'] - 1]
            return render_template(
                'assessment.html',
                question=q,
                phase="main",
                total_questions=len(session['shuffled_questions']),
                current_question=session['current_question']
            )

        # ------------- AFTER FINISHING MAIN QUESTIONS -------------
        riasec_scores, _ = calculate_scores()

        if need_tie_breaker(riasec_scores):
            pair = get_tie_breaker_pair(riasec_scores)

            session['tie_breaker_phase'] = True
            session['tie_breaker_pair'] = pair
            session['tie_breaker_questions'] = get_tie_breaker_questions(pair)

            session['tie_breaker_answered'] = 0
            session['total_questions'] = len(session['shuffled_questions']) + len(session['tie_breaker_questions'])

            return redirect(url_for('assessment'))

        return redirect(url_for('submit_all_answers'))

    # -----------------------------
    # TIE-BREAKER PHASE
    # -----------------------------
    tie_qs = session['tie_breaker_questions']
    answered = session['tie_breaker_answered']

    if answered < len(tie_qs):
        q = tie_qs[answered]
        display_idx = len(session['shuffled_questions']) + answered + 1
        return render_template(
            'assessment.html',
            question=q,
            phase="tie_breaker",
            total_questions=session['total_questions'],
            current_question=display_idx
        )

    return redirect(url_for('submit_all_answers'))


@app.route('/save_answer', methods=['POST'])
def save_answer():
    data = request.get_json(force=True)
    qnum = data.get('question_number')
    ans = data.get('answer')

    if qnum is None or ans is None:
        return jsonify({'success': False, 'msg': 'Missing question data'}), 400

    session['answers'][str(qnum)] = ans

    if not session.get('tie_breaker_phase', False):
        session['current_question'] += 1
    else:
        session['tie_breaker_answered'] += 1
        session['current_question'] = len(session['shuffled_questions']) + session['tie_breaker_answered'] + 1

    riasec_scores, _ = calculate_scores()
    session['riasec_scores'] = riasec_scores

    return jsonify({'success': True, 'redirect': url_for('assessment')})


@app.route('/submit_all_answers')
def submit_all_answers():
    if not session.get('answers'):
        return redirect(url_for('basic_info'))
    return redirect(url_for('results'))

# -----------------------------
# RIASEC Resolver
# -----------------------------
def resolve_riasec_code(riasec_scores):
    sorted_scores = sorted(
        riasec_scores.items(),
        key=lambda x: (-x[1], RIASEC_ORDER.index(x[0]))
    )
    top3 = [code for code, score in sorted_scores[:3]]
    return ''.join(top3)

# -----------------------------
# Save To Google Sheets
# -----------------------------
def save_to_google_sheet(riasec_code, riasec_scores, aptitude_scores, user_info=None):
    client = get_gspread_client()
    sheet = client.open(SHEET_NAME).sheet1

    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        user_info.get('name', 'Anonymous'),
        user_info.get('occupation', ''),
        user_info.get('education', ''),
        riasec_code
    ]

    for code in RIASEC_ORDER:
        row.append(riasec_scores.get(code, 0))

    ordered_apts = [
        "Logical Reasoning", "Mechanical", "Creative", "Verbal Communication",
        "Numerical", "Social/Helping", "Leadership/Persuasion", "Digital/Computer",
        "Organizing/Structuring", "Writing/Expression", "Scientific", "Spatial/Design"
    ]

    for apt in ordered_apts:
        row.append(aptitude_scores.get(apt, 0))

    sheet.append_row(row)
    return True

# -----------------------------
# Results Page
# -----------------------------
@app.route('/results')
def results():
    if not session.get('answers'):
        return redirect(url_for('index'))

    riasec_scores, aptitude_raw = calculate_scores()
    aptitudes = convert_to_percentiles(aptitude_raw)
    riasec_code = resolve_riasec_code(riasec_scores)

    session['last_riasec_code'] = riasec_code
    session['last_riasec_scores'] = riasec_scores
    session['last_aptitude_scores'] = aptitudes

    top_riasec = sorted(riasec_scores.items(), key=lambda x: x[1], reverse=True)[:3]
    top_apt = sorted(aptitudes.items(), key=lambda x: x[1], reverse=True)[:3]

    return render_template(
        'results.html',
        riasec_code=riasec_code,
        top_riasec=top_riasec,
        top_aptitudes=top_apt,
        all_riasec_scores=riasec_scores,
        all_aptitude_scores=aptitudes,
        max_riasec_score=max(riasec_scores.values()) if riasec_scores else 1,
        max_aptitude_score=max(aptitudes.values()) if aptitudes else 1
    )

@app.route('/save_results', methods=['POST'])
def save_results():
    try:
        save_to_google_sheet(
            session['last_riasec_code'],
            session['last_riasec_scores'],
            session['last_aptitude_scores'],
            session.get('user_info')
        )
        return jsonify({'success': True, 'msg': 'Saved successfully'})
    except Exception as e:
        return jsonify({'success': False, 'msg': str(e)})

@app.route('/restart')
def restart():
    session.clear()
    return redirect(url_for('basic_info'))

# -----------------------------
# Main
# -----------------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
