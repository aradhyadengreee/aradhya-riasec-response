from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from collections import defaultdict
import os

from config import config
from questions.main_questions import QUESTIONS
from questions.tie_breaker_questions import TIE_BREAKER_QUESTIONS

# -----------------------------
# App Initialization
# -----------------------------
def create_app():
    app = Flask(__name__)
    env = os.environ.get('FLASK_ENV', 'default')
    app.config.from_object(config[env])
    return app

app = create_app()

# -----------------------------
# Session Initialization
# -----------------------------
def initialize_session():
    session['current_question'] = 1
    session['answers'] = {}
    session['riasec_scores'] = {'R':0,'I':0,'A':0,'S':0,'E':0,'C':0}
    session['aptitude_scores'] = defaultdict(int)
    session['tie_breaker_phase'] = False
    session['tie_breaker_questions'] = []
    session['tie_breaker_answered'] = 0
    session['total_questions'] = len(QUESTIONS)

# -----------------------------
# Score Calculation
# -----------------------------
def calculate_scores():
    riasec_scores = {'R':0,'I':0,'A':0,'S':0,'E':0,'C':0}
    aptitude_scores = defaultdict(int)
    main_total = len(QUESTIONS)

    for q_num_str, answer in session['answers'].items():
        q_num = int(q_num_str)
        question = None

        if q_num <= main_total:
            question = next((q for q in QUESTIONS if q['number']==q_num), None)
        else:
            question = next((q for q in TIE_BREAKER_QUESTIONS if q['number']==q_num), None)

        if question and answer in question['options']:
            option = question['options'][answer]
            riasec_scores[option['riasec']] += 1
            if q_num <= main_total:
                for apt, score in option.get('aptitudes', {}).items():
                    aptitude_scores[apt] += score

    return riasec_scores, dict(aptitude_scores)

# -----------------------------
# Tie-Breaker Logic
# -----------------------------
def needs_tie_breaker(riasec_scores):
    delta = app.config['TIE_BREAKER_DELTA']
    sorted_scores = sorted(riasec_scores.items(), key=lambda x: x[1], reverse=True)
    top_three = sorted_scores[:3]
    first_score, second_score, third_score = top_three[0][1], top_three[1][1], top_three[2][1]

    # Check top differences
    if first_score - second_score < delta or second_score - third_score < delta:
        return True

    # Check ties for third place
    third_place_codes = [c for c,s in sorted_scores if s==third_score]
    if len(third_place_codes) > 1:
        return True

    return False

def get_tie_breaker_questions(riasec_scores):
    delta = app.config['TIE_BREAKER_DELTA']
    sorted_scores = sorted(riasec_scores.items(), key=lambda x: x[1], reverse=True)
    top_three = sorted_scores[:3]

    needed_pairs = set()
    first_code, first_score = top_three[0]
    second_code, second_score = top_three[1]
    third_code, third_score = top_three[2]

    if first_score - second_score < delta:
        needed_pairs.add(frozenset([first_code, second_code]))
    if second_score - third_score < delta:
        needed_pairs.add(frozenset([second_code, third_code]))

    third_place_codes = [c for c,s in sorted_scores if s==third_score]
    if len(third_place_codes)>1:
        for i in range(len(third_place_codes)):
            for j in range(i+1, len(third_place_codes)):
                needed_pairs.add(frozenset([third_place_codes[i], third_place_codes[j]]))

    already_used = set(q['pair'] for q in session.get('tie_breaker_questions', []))
    new_questions = []

    def pair_str(pair):
        a,b = sorted(list(pair))
        return f"{a}-{b}"

    for pair in needed_pairs:
        p_str = pair_str(pair)
        if p_str in already_used:
            continue
        qs = [q for q in TIE_BREAKER_QUESTIONS if q['pair']==p_str]
        new_questions.extend(qs[:2])  # max 2 per pair

    return new_questions

def should_continue_tie_breakers(riasec_scores):
    return needs_tie_breaker(riasec_scores)

# -----------------------------
# Routes
# -----------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start_assessment():
    initialize_session()
    return redirect(url_for('assessment'))

@app.route('/assessment')
def assessment():
    if 'current_question' not in session:
        return redirect(url_for('index'))

    current_q = session['current_question']

    # Main questions
    if not session['tie_breaker_phase']:
        if current_q <= len(QUESTIONS):
            question = QUESTIONS[current_q-1]
            return render_template('assessment.html', question=question,
                                   phase="main",
                                   total_questions=len(QUESTIONS),
                                   current_question=current_q)
        else:
            # Main finished, check tie-breaker
            riasec_scores, _ = calculate_scores()
            if needs_tie_breaker(riasec_scores):
                session['tie_breaker_phase'] = True
                session['tie_breaker_questions'] = get_tie_breaker_questions(riasec_scores)
                session['tie_breaker_answered'] = 0
                session['total_questions'] = len(QUESTIONS) + len(session['tie_breaker_questions'])
                return redirect(url_for('assessment'))
            else:
                return redirect(url_for('submit_all_answers'))

    # Tie-breaker phase
    tie_questions = session['tie_breaker_questions']
    tie_answered = session['tie_breaker_answered']
    if tie_answered < len(tie_questions):
        question = tie_questions[tie_answered]
        current_q = len(QUESTIONS) + tie_answered + 1
        return render_template('assessment.html', question=question,
                               phase="tie_breaker",
                               total_questions=session['total_questions'],
                               current_question=current_q)
    else:
        # Recalculate scores
        riasec_scores, _ = calculate_scores()
        if should_continue_tie_breakers(riasec_scores):
            new_qs = get_tie_breaker_questions(riasec_scores)
            if new_qs:
                session['tie_breaker_questions'].extend(new_qs)
                session['total_questions'] += len(new_qs)
                return redirect(url_for('assessment'))
        return redirect(url_for('submit_all_answers'))

@app.route('/save_answer', methods=['POST'])
def save_answer():
    if 'current_question' not in session:
        return jsonify({'success': False, 'redirect': url_for('index')})

    data = request.get_json()
    question_number = data.get('question_number')
    answer = data.get('answer')

    if question_number and answer:
        session['answers'][str(question_number)] = answer
        session.modified = True

        if not session['tie_breaker_phase']:
            session['current_question'] += 1
        else:
            session['tie_breaker_answered'] += 1
            session['current_question'] = len(QUESTIONS) + session['tie_breaker_answered'] + 1

        return jsonify({'success': True, 'redirect': url_for('assessment')})

    return jsonify({'success': False})

@app.route('/submit_all_answers')
def submit_all_answers():
    if 'answers' not in session or not session['answers']:
        return redirect(url_for('index'))
    return redirect(url_for('results'))

@app.route('/results')
def results():
    if 'answers' not in session or not session['answers']:
        return redirect(url_for('index'))

    riasec_scores, aptitude_scores = calculate_scores()
    top_riasec = sorted(riasec_scores.items(), key=lambda x:x[1], reverse=True)[:3]
    top_aptitudes = sorted(aptitude_scores.items(), key=lambda x:x[1], reverse=True)[:3]

    riasec_code = ''.join([c for c,_ in top_riasec])
    max_riasec_score = max(riasec_scores.values()) if riasec_scores else 1
    max_aptitude_score = max(aptitude_scores.values()) if aptitude_scores else 1

    return render_template('results.html',
                           riasec_code=riasec_code,
                           top_riasec=top_riasec,
                           top_aptitudes=top_aptitudes,
                           all_riasec_scores=riasec_scores,
                           all_aptitude_scores=aptitude_scores,
                           max_riasec_score=max_riasec_score,
                           max_aptitude_score=max_aptitude_score)

@app.route('/restart')
def restart():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    if app.config['DEBUG']:
        app.run(debug=True)
    else:
        port = os.getenv("port", 5000)
        app.run(host='0.0.0.0', port=int(port))
