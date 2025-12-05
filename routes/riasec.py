# routes/riasec.py
from flask import Blueprint, request, jsonify, session, current_app
from services.riasec_service import RIASECService

riasec_bp = Blueprint('riasec_bp', __name__, url_prefix='/api/riasec')
service = RIASECService()

# Initialize keys helper
def _ensure_session_keys():
    # keep compatibility with your app.py keys
    if 'assessment_answers' not in session and 'answers' not in session:
        # some earlier code used 'answers' key — ensure we use 'assessment_answers' in API
        session['assessment_answers'] = {}
    if 'tie_breaker_phase' not in session:
        session['tie_breaker_phase'] = False
    if 'tie_breaker_questions' not in session:
        session['tie_breaker_questions'] = []
    if 'tie_breaker_answers' not in session:
        session['tie_breaker_answers'] = {}
    if 'active_tie_pairs' not in session:
        session['active_tie_pairs'] = []
    if 'completed_tie_pairs' not in session:
        session['completed_tie_pairs'] = []
    if 'pair_question_count' not in session:
        session['pair_question_count'] = {}
    if 'current_question' not in session:
        session['current_question'] = 1
    session.modified = True

@riasec_bp.route('/start-assessment', methods=['POST'])
def start_assessment():
    """
    Initialize assessment session
    """
    try:
        # You might require user login in session elsewhere
        # For now just initialize local session state
        _ensure_session_keys()
        session['current_question'] = 1
        session['assessment_answers'] = {}
        session['tie_breaker_phase'] = False
        session['tie_breaker_questions'] = []
        session['tie_breaker_answers'] = {}
        session['active_tie_pairs'] = []
        session['completed_tie_pairs'] = []
        session['pair_question_count'] = {}
        session.modified = True

        return jsonify({"success": True, "message": "Assessment started"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@riasec_bp.route('/get-questions', methods=['GET'])
def get_questions():
    try:
        _ensure_session_keys()
        main_questions = service.get_questions()
        # prepare a minimal payload for client
        client_questions = [service.prepare_question_for_client(q) for q in main_questions]
        return jsonify({"success": True, "questions": client_questions})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@riasec_bp.route('/submit-answer', methods=['POST'])
def submit_answer():
    """
    Expected payload:
    {
      question_number: int,
      answer: 'A' or 'B'
    }
    Returns: JSON including next_question (or null), riasec_scores, needs_tie_breaker, current_phase
    """
    try:
        _ensure_session_keys()
        data = request.get_json() or {}
        qnum = data.get('question_number')
        answer = data.get('answer')

        if qnum is None or answer is None:
            return jsonify({"error": "Missing question_number or answer"}), 400

        # Normalize storage keys (strings to keep JSON-serializable in session)
        qkey = str(qnum)

        # Determine whether this is a tie-breaker question (numbers > len(main_questions))
        main_count = len(service.questions)
        is_tie_q = int(qnum) > main_count

        if is_tie_q:
            question_obj = next(
                (q for q in session['tie_breaker_questions'] if str(q['number']) == qkey),
                None
            )
            if question_obj:
                session['tie_breaker_answers'][qkey] = {
                    "number": question_obj['number'],
                    "question": question_obj.get('question') or question_obj.get('text'),
                    "options": {k: v['text'] for k, v in question_obj.get('options', {}).items()},
                    "answer": answer
                }
        else:
            question_obj = service.questions[int(qnum) - 1]  # main questions are 1-indexed
            session['assessment_answers'][qkey] = {
                "number": question_obj['number'],
                "question": question_obj.get('question') or question_obj.get('text'),
                "options": {k: v['text'] for k, v in question_obj.get('options', {}).items()},
                "answer": answer
            }

        session.modified = True

        # Recalculate scores using session answers + tie answers
        all_answers = {}
        all_answers.update(session.get('assessment_answers', {}))
        all_answers.update(session.get('tie_breaker_answers', {}))

        riasec_scores, aptitude_scores = service.calculate_scores(all_answers, session.get('tie_breaker_questions', []))

        # Decide / update active tie pairs EVERY TIME after recalc
        delta = current_app.config.get('TIE_BREAKER_DELTA', None)
        active_pairs = service.select_tie_breaker_pairs(riasec_scores, delta=delta)

        # Remove pairs already completed
        completed_pairs = session.get('completed_tie_pairs', [])
        active_pairs = [p for p in active_pairs if p not in completed_pairs]

        session['active_tie_pairs'] = active_pairs

        # If not already in tie breaker phase and main finished -> turn on tie-breaker phase
        if not session.get('tie_breaker_phase', False):
            # if all main questions asked
            # Determine last main question answered index by counting main questions answered
            main_answered_count = sum(1 for k in session.get('assessment_answers', {}) if int(k) <= main_count)
            if main_answered_count >= main_count and active_pairs:
                session['tie_breaker_phase'] = True
                session.modified = True

        # If in tie-breaker phase: filter and possibly mark completed pairs (exhausted or resolved)
        if session.get('tie_breaker_phase', False):
            still_active = []
            completed = list(session.get('completed_tie_pairs', []))  # copy
            pair_question_count = session.get('pair_question_count', {})

            for pair in active_pairs:
                pair_str = '-'.join(sorted(pair))

                # If pair reached max questions, mark completed
                if service.has_reached_max_questions_for_pair(pair_str, pair_question_count, max_q=current_app.config.get('MAX_TIE_BREAKER_ROUNDS', None)):
                    if pair not in completed:
                        completed.append(pair)
                    continue

                # If delta no longer indicates need -> mark completed
                if not service.needs_tie_breaker_for_pair(pair, riasec_scores, delta=current_app.config.get('TIE_BREAKER_DELTA', None)):
                    if pair not in completed:
                        completed.append(pair)
                    continue

                # still needs tie-breaker
                still_active.append(pair)

            session['active_tie_pairs'] = still_active
            session['completed_tie_pairs'] = completed
            session.modified = True

        # Find next question to send (main or tie-breaker)
        next_question = None
        current_phase = "tie_breaker" if session.get('tie_breaker_phase') else "main"

        # If still in main phase, pick next main not-yet-answered
        if not session.get('tie_breaker_phase'):
            # calculate next main question index
            current_q = session.get('current_question', 1)
            # move forward to next unanswered
            while current_q <= len(service.questions) and str(current_q) in session.get('assessment_answers', {}):
                current_q += 1
            session['current_question'] = current_q
            if current_q <= len(service.questions):
                next_question = service.prepare_question_for_client(service.questions[current_q - 1])
            else:
                # main finished; tie-breakers may be triggered — handled below
                next_question = None
        else:
            # tie-breaker phase: show next unanswered tie question if present OR fetch new one
            tie_questions = session.get('tie_breaker_questions', [])
            tie_answered_count = len([k for k in session.get('tie_breaker_answers', {}) if int(k) > main_count])

            # If there is an existing appended tie question not yet answered, show it
            if tie_answered_count < len(tie_questions):
                qobj = tie_questions[tie_answered_count]
                next_question = service.prepare_question_for_client(qobj)
            else:
                # Need to fetch a new tie question for the first active pair with unasked pool question
                used_original_nums = [t.get('original_number') or t.get('number') for t in session.get('tie_breaker_questions', [])]
                pool_q, pair_str = service.get_next_tie_breaker_question(session.get('active_tie_pairs', []), used_original_numbers=used_original_nums)
                if pool_q:
                    # assign unique number and append to session list
                    numbered = service.assign_unique_number_to_tie_question(pool_q, existing_count_main=len(service.questions), existing_tie_session_count=len(session.get('tie_breaker_questions', [])))
                    # store original pool number as metadata to avoid reuse
                    numbered['original_number'] = pool_q.get('number', numbered['number'])
                    # normalize pair string store
                    numbered['pair'] = pair_str
                    session['tie_breaker_questions'].append(numbered)

                    # increment pair question count
                    counts = session.get('pair_question_count', {})
                    counts[pair_str] = counts.get(pair_str, 0) + 1
                    session['pair_question_count'] = counts

                    session['current_question'] = len(service.questions) + len(session['tie_breaker_questions'])
                    session.modified = True
                    next_question = service.prepare_question_for_client(numbered)
                else:
                    # no tie questions available; finished
                    next_question = None

        return jsonify({
            "success": True,
            "next_question": next_question,
            "riasec_scores": riasec_scores,
            "needs_tie_breaker": session.get('tie_breaker_phase', False),
            "current_phase": current_phase
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@riasec_bp.route('/current-scores', methods=['GET'])
def get_current_scores():
    try:
        _ensure_session_keys()
        # compose all answers and compute
        all_answers = {}
        all_answers.update(session.get('assessment_answers', {}))
        all_answers.update(session.get('tie_breaker_answers', {}))
        
        print(f"DEBUG: all_answers = {all_answers}")
        
        riasec_scores, aptitude_percentiles = service.calculate_scores(all_answers, session.get('tie_breaker_questions', []))
        riasec_code = service.generate_riasec_code(riasec_scores)
        
        print(f"DEBUG: riasec_scores = {riasec_scores}")
        print(f"DEBUG: riasec_code = {riasec_code}")
        print(f"DEBUG: aptitude_percentiles = {aptitude_percentiles}")
        
        return jsonify({
            "success": True,
            "riasec_scores": riasec_scores,
            "riasec_code": riasec_code,
            "aptitude_percentiles": aptitude_percentiles  # Updated key name
        })
    except Exception as e:
        print(f"ERROR in get_current_scores: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 400
    
from models.user import User

@riasec_bp.route('/submit-test', methods=['POST'])
def submit_test():
    try:
        _ensure_session_keys()

        # Combine main + tie-breaker answers
        all_answers = {}
        all_answers.update(session.get('assessment_answers', {}))
        all_answers.update(session.get('tie_breaker_answers', {}))

        # Calculate scores
        riasec_scores, aptitude_percentiles = service.calculate_scores(
            all_answers, 
            session.get('tie_breaker_questions', [])
        )
        riasec_code = service.generate_riasec_code(riasec_scores)

        # Save results to DB along with QA
        user_id = session.get('user_id')
        if user_id:
            user = User.get_user(user_id)
            if user:
                user.update_riasec_results(
                    riasec_scores=riasec_scores,
                    riasec_code=riasec_code,
                    answers=all_answers,
                    aptitude_percentiles=aptitude_percentiles
                )

        # Clean session
        for k in ['assessment_answers', 'tie_breaker_answers', 'tie_breaker_phase',
                  'tie_breaker_questions', 'active_tie_pairs', 'completed_tie_pairs',
                  'pair_question_count']:
            session.pop(k, None)
        session.modified = True

        return jsonify({
            "success": True,
            "riasec_scores": riasec_scores,
            "riasec_code": riasec_code,
            "aptitude_percentiles": aptitude_percentiles,
            "message": "RIASEC test completed successfully"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400
