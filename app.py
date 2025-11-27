from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from collections import Counter
import os
import re
import random
from datetime import datetime

# Google Sheets
import gspread
from google.oauth2.service_account import Credentials

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
    app.secret_key = os.urandom(24)
    return app

app = create_app()

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
    session['riasec_scores'] = {'R':0,'I':0,'A':0,'S':0,'E':0,'C':0}
    session['tie_breaker_phase'] = False
    session['tie_breaker_questions'] = []
    session['tie_breaker_pairs_asked'] = []
    session['tie_breaker_answered'] = 0
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

        if not question or selected not in question.get('options', {}):
            continue

        option = question['options'][selected]
        q_weight = question.get('weight', 1)

        riasec_code = option.get('riasec')
        if riasec_code in riasec_scores:
            riasec_scores[riasec_code] += q_weight

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
                for field in ('explain','hint','job_text'):
                    if field in question:
                        boosts = enrich_from_text(question[field])
                        for k,v in boosts.items():
                            aptitude_scores[k] += v

    return riasec_scores, dict(aptitude_scores)

# -----------------------------
# Tie-breaker Logic
# -----------------------------
MAX_TIE_BREAKER_QS = 3
RIASEC_ORDER = ['R','I','A','S','E','C']

def sort_pairs_resolver_style(pairs):
    def key_func(pair):
        a, b = pair.split('-')
        return (RIASEC_ORDER.index(a), RIASEC_ORDER.index(b))
    return sorted(pairs, key=key_func)

def identify_tie_pairs(riasec_scores):
    sorted_scores = sorted(
        riasec_scores.items(),
        key=lambda x: (-x[1], RIASEC_ORDER.index(x[0]))
    )
    pairs = set()

    top1_code, top1_score = sorted_scores[0]
    top2_code, top2_score = sorted_scores[1]

    if abs(top1_score - top2_score) <= 1:
        pairs.add(f"{min(top1_code, top2_code)}-{max(top1_code, top2_code)}")

    if len(sorted_scores) >= 3:
        top3_code, top3_score = sorted_scores[2]
        if abs(top2_score - top3_score) <= 1:
            pairs.add(f"{min(top2_code, top3_code)}-{max(top2_code, top3_code)}")

    return pairs

def get_questions_for_pairs(pairs, already_asked):
    new_qs = []
    for pair in pairs:
        if pair in already_asked:
            continue
        matched = [q for q in TIE_BREAKER_QUESTIONS if q.get('pair') == pair]
        new_qs.extend(matched[:MAX_TIE_BREAKER_QS])
    return new_qs

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

        riasec_scores,_ = calculate_scores()
        pairs_needed = identify_tie_pairs(riasec_scores)
        already = set(session.get('tie_breaker_pairs_asked', []))
        remaining_pairs = pairs_needed - already

        if remaining_pairs:
            session['tie_breaker_phase'] = True
            new_qs = get_questions_for_pairs(remaining_pairs, already)

            session['tie_breaker_questions'] = new_qs
            session['tie_breaker_answered'] = 0
            session['total_questions'] = len(session['shuffled_questions']) + len(new_qs)
            session['tie_breaker_pairs_asked'].extend(remaining_pairs)

            return redirect(url_for('assessment'))

        return redirect(url_for('submit_all_answers'))

    tie_qs = session.get('tie_breaker_questions', [])
    answered = session.get('tie_breaker_answered', 0)
    if answered < len(tie_qs):
        q = tie_qs[answered]
        display_index = len(session['shuffled_questions']) + answered + 1
        return render_template(
            'assessment.html',
            question=q,
            phase="tie_breaker",
            total_questions=session.get('total_questions'),
            current_question=display_index
        )

    return redirect(url_for('submit_all_answers'))

@app.route('/save_answer', methods=['POST'])
def save_answer():
    if 'current_question' not in session:
        return jsonify({'success': False, 'redirect': url_for('basic_info')})

    data = request.get_json(force=True)
    qnum = data.get('question_number')
    ans = data.get('answer')

    session['answers'][str(qnum)] = ans
    session.modified = True

    if not session.get('tie_breaker_phase', False):
        session['current_question'] += 1
    else:
        session['tie_breaker_answered'] += 1
        session['current_question'] = (
            len(session['shuffled_questions']) +
            session['tie_breaker_answered'] + 1
        )

    riasec_scores, _ = calculate_scores()
    session['riasec_scores'] = riasec_scores

    return jsonify({'success': True, 'redirect': url_for('assessment')})

@app.route('/submit_all_answers')
def submit_all_answers():
    if 'answers' not in session or not session['answers']:
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
# Google Sheets Saving (UPDATED)
# -----------------------------
def save_to_google_sheet(riasec_code, riasec_scores, aptitude_scores, user_info=None):

    SERVICE_ACCOUNT_INFO = {
  "type": "service_account",
  "project_id": "riasec-responses",
  "private_key_id": "5bb4f460c8b974ec9436202ef94bb9bda5471dba",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEugIBADANBgkqhkiG9w0BAQEFAASCBKQwggSgAgEAAoIBAQCvPyNEE+T0WpK3\nnazpoo8LVb4eDAJi3ObDLsC1D04kmHeH38XdPXJHR2oo/YdJtY8rysIyDeUOUos5\nnTBQMKpBG/lGR/F/8tZE6Ep/t/JQUvcuxZYQgHxgURYiOfSPIGY+aIy5KzyxaFSm\nU7qJO74e1r1GixwNNH2iUfsZpeFByAXw0t7hPb2gTtnl9JmmUvSw0VGzaR0ZZbKq\n3H3tYtIDXt1r5XWw+aeWbLNIQV7TsNHME1XecHeDjGsIGza4QNu4PqbfcQwyaMQ2\nRtUIYFzzv9Pk1ukntKKwOaZTd8xktFxq+Y15tJWn/scFN+H5acIUaUewsvHBLmWd\nH9IEkIhxAgMBAAECgf9wm6GNnTsByTF9y1PQzSQdpHsF07G01T1zLhemQK911IL6\nTFBYWaOVKc6NiFvmgUP+X8tpXoRRL7lGzDq/TIYaUF9dSd1k2iXVIW69ovWRp74t\nz8kd0XIacgBG/faoAamxcHz8f0wAs4mxVxwGEt2X82Ssb7cWxSP1qbgwQub73PuC\nioucL2d8FOFnozfSmBjx4VWMPDaGwrRnEZvoGSnpas0FDTsBXBTCfjMP29fvY7/J\npS1Uc2J+cFdxw6nclWM7zy8YcquwdLzMJQ7KRrEB9jUEYO3a/zNRIWWW0Aq5idOU\nX46y6BS3tW8j7tk0gMfixs2FqT29dOxDKfRP5IMCgYEA3NIjt8LS3O2+rbtgqjgC\nD9QkgOg4TEwrbXEayWzIXGZ2NJspqPPTFH46Hee7GbeOFLrD6kTYIYeV0SViqZv4\nPxyyvbEIFrn1nwRDhpziD05ynN7aaqMfV9zS3NcQ4LntUgly9ANQ2bPT3l1dXnPz\n7nPxnxOqMpl13SRixXot578CgYEAyypRsWNPnxJLIUs7CfLjTdjRux5XUMiZnnR3\nxBpY/P1E7JwNHMvLZo5bG+fTc1bo3wdb7M5O2+gBwDHshFrtLy2Gl6CWdBb8/FbE\ngRlFh5AN2nXmymivqUR9zEG3pAWxLG84kyATJyP1wsNLW59egVHJ2GRJstvvhpMP\nMSY/G88CgYAabEK94GAe84vXeg5tD9qfTkE385GY/5xKsjgEVjH7bH9EeDSZ9OMT\nFq+ZmHr47s/fhyGeTLKYAINazWBq7zDbTHHO5PoUzhen+XijCO676iUoxDnafL5p\nYxEQP+PTICxXnq3UqPjps+zsNLvRa4qKw/DrmgzJlTdXSN1Qx/fqPQKBgFsaYv+0\nlOO0BFSts4/Ghv9FlubduDHVgm13tK0PU5A+0kV3xLmA+XjHpTtiPYOfGVXJqwMJ\nkHs0EnTo7jJ7w5hARfaAYHc2R8Ov9PYfKvqbMlsgO5nQT9ULjY2men7mvog6Z5gx\n7eTDT1VC1ewEDxDWaDjM3++AiGxETa+wguQpAoGAPAOOVixNOO/DBf9He2yKdQux\nw5WvHpDU/g1dpaDz/e0jibrbqq1dC/x/INiB2kR5btyz2pht612pQZAoMiT+6glI\nvZmtm9yp+yN+uvpV202SVHRFvsPgdJnjtRNYM6FCz1LbSlKywA/u5K+msskLlb64\naK8csq5raB6t7dLhkmQ=\n-----END PRIVATE KEY-----\n",
  "client_email": "riasec-client@riasec-responses.iam.gserviceaccount.com",
  "client_id": "109370773003926881947",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/riasec-client%40riasec-responses.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}

    SCOPE = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    SHEET_NAME = "R1"

    creds = Credentials.from_service_account_info(SERVICE_ACCOUNT_INFO, scopes=SCOPE)
    client = gspread.authorize(creds)
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

    for apt in NEW_APTITUDES:
        row.append(aptitude_scores.get(apt, 0))

    sheet.append_row(row)
    return True

# -----------------------------
# Results Page
# -----------------------------
@app.route('/results')
def results():
    if 'answers' not in session or not session['answers']:
        return redirect(url_for('index'))

    riasec_scores, aptitude_scores = calculate_scores()
    riasec_code = resolve_riasec_code(riasec_scores)

    session['last_riasec_code'] = riasec_code
    session['last_riasec_scores'] = riasec_scores
    session['last_aptitude_scores'] = aptitude_scores

    top_riasec = sorted(riasec_scores.items(), key=lambda x:x[1], reverse=True)[:3]
    top_aptitudes = sorted(aptitude_scores.items(), key=lambda x:x[1], reverse=True)[:3]

    return render_template(
        'results.html',
        riasec_code=riasec_code,
        top_riasec=top_riasec,
        top_aptitudes=top_aptitudes,
        all_riasec_scores=riasec_scores,
        all_aptitude_scores=aptitude_scores,
        max_riasec_score=max(riasec_scores.values()) if riasec_scores else 1,
        max_aptitude_score=max(aptitude_scores.values()) if aptitude_scores else 1
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
        return jsonify({'success': True, 'msg': 'Results saved successfully!'})
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
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
