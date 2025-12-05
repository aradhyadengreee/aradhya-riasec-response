# services/riasec_service.py
import os
from copy import deepcopy
from collections import defaultdict
from itertools import permutations
from questions.main_questions import QUESTIONS
from questions.tie_breaker_questions import TIE_BREAKER_QUESTIONS

class RIASECService:
    """
    Service encapsulating RIASEC scoring and tie-breaker question logic.
    """

    def __init__(self):
        # Load static question sets once
        self.questions = deepcopy(QUESTIONS)
        self.tie_breaker_questions_pool = deepcopy(TIE_BREAKER_QUESTIONS)

    # -------------------------
    # Public helpers for routes
    # -------------------------
    def get_questions(self):
        """Return main questions (safe to send to client)."""
        return deepcopy(self.questions)

    def calculate_scores(self, all_answers, session_tie_questions=None):
        """
        Calculate RIASEC and aptitude scores from answers.
        - all_answers: dict mapping question_number (string or int) -> answer key ('A'/'B' etc.)
        - session_tie_questions: list of tie question dicts that were appended into session (with assigned numbers)
        Returns: (riasec_scores, aptitude_percentiles)
        """
        riasec_scores = {'R': 0, 'I': 0, 'A': 0, 'S': 0, 'E': 0, 'C': 0}
        aptitude_scores = defaultdict(int)

        # Build lookup for main and tie questions
        main_lookup = {q['number']: q for q in self.questions}
        tie_lookup = {}
        if session_tie_questions:
            tie_lookup = {q['number']: q for q in session_tie_questions}

        for q_num_str, answer in (all_answers or {}).items():
            try:
                q_num = int(q_num_str)
            except (ValueError, TypeError):
                continue

            question = main_lookup.get(q_num) or tie_lookup.get(q_num)
            if not question:
                continue

            # Extract letter if answer is now a dict
            answer_letter = answer if isinstance(answer, str) else answer.get('answer')

            # validate option exists
            if not answer_letter or answer_letter not in question.get('options', {}):
                continue

            option = question['options'][answer_letter]

            # RIASEC
            riasec_code = option.get('riasec')
            if riasec_code and riasec_code in riasec_scores:
                riasec_scores[riasec_code] += 1

            # Aptitudes only from main questions
            if q_num <= len(self.questions):
                for aptitude, score in option.get('aptitudes', {}).items():
                    aptitude_scores[aptitude] += score

        # Convert aptitude scores to percentiles
        aptitude_percentiles = self.convert_to_percentiles(dict(aptitude_scores))
        
        return riasec_scores, aptitude_percentiles

    def convert_to_percentiles(self, score_dict):
        """
        Converts aptitude scores into percentiles (0–100 scale)
        based on the highest score.
        Returns integer percentiles (rounded).
        """
        if not score_dict:
            return {}

        max_score = max(score_dict.values()) or 1

        percentiles = {
            key: int(round((value / max_score) * 100))
            for key, value in score_dict.items()
        }

        return percentiles
    
    def get_top_three(self, scores_dict):
        """Get top 3 RIASEC codes by score"""
        sorted_items = sorted(scores_dict.items(), key=lambda x: (-x[1], x[0]))
        return sorted_items[:3]
    
    def get_top_four(self, scores_dict):
        """Get top 4 RIASEC codes by score"""
        sorted_items = sorted(scores_dict.items(), key=lambda x: (-x[1], x[0]))
        return sorted_items[:4]

    def generate_riasec_code(self, riasec_scores):
        """Generate the standard 3-letter RIASEC code from scores"""
        top_three = self.get_top_three(riasec_scores)
        return ''.join([code for code, _ in top_three])
    
    def generate_riasec_permutations_for_matching(self, riasec_scores):
        """
        Generate all relevant RIASEC permutations for job matching.
        
        Rules:
        1. Get top 4 letters from RIASEC scores (sorted by score)
        2. Generate all possible permutations of:
           - All 3-letter permutations of top 4 letters
           - All 2-letter permutations of top 4 letters  
           - All single letters from top 4
        3. Exclude bottom 2 letters (5th and 6th)
        4. Return as list of strings (codes) for matching
        
        Args:
            riasec_scores (dict): RIASEC scores dictionary
            
        Returns:
            list: List of RIASEC codes/permutations for job matching
        """
        # Sort letters by score (descending)
        sorted_letters = sorted(
            riasec_scores.items(), 
            key=lambda x: (-x[1], x[0])  # Sort by score desc, then letter asc
        )
        
        # Get top 4 letters
        top_4_letters = [letter for letter, _ in sorted_letters[:4]]
        
        all_codes = set()  # Use set to avoid duplicates
        
        # Generate 3-letter permutations from top 4
        for perm in permutations(top_4_letters, 3):
            # Convert to string and add
            code_str = ''.join(perm)
            all_codes.add(code_str)
        
        # Generate 2-letter permutations from top 4
        for perm in permutations(top_4_letters, 2):
            code_str = ''.join(perm)
            all_codes.add(code_str)
        
        # Add single letters
        for letter in top_4_letters:
            all_codes.add(letter)
        
        # Also add the original top 3 code for backward compatibility
        top_3_code = self.generate_riasec_code(riasec_scores)
        all_codes.add(top_3_code)
        
        return list(all_codes)
    
    def test_riasec_permutations(self, test_scores=None):
        """
        Test function to verify RIASEC permutation logic.
        
        Args:
            test_scores (dict): Optional test scores. If not provided, uses example from requirements.
            
        Returns:
            list: Generated permutations for verification
        """
        if test_scores is None:
            # Example from requirements
            test_scores = {
                'I': 9,
                'S': 7,
                'R': 5,
                'C': 4,
                'A': 3,
                'E': 2
            }
        
        # Get top 4 letters
        top_4 = self.get_top_four(test_scores)
        print(f"Top 4 letters: {[letter for letter, _ in top_4]}")
        
        # Generate permutations
        permutations = self.generate_riasec_permutations_for_matching(test_scores)
        
        print(f"\nTotal permutations: {len(permutations)}")
        print("\nGenerated codes:")
        
        # Group by length for better readability
        by_length = {}
        for code in permutations:
            length = len(code)
            by_length.setdefault(length, []).append(code)
        
        for length in sorted(by_length.keys()):
            print(f"\n{length}-letter codes ({len(by_length[length])}):")
            # Sort alphabetically for readability
            sorted_codes = sorted(by_length[length])
            for i, code in enumerate(sorted_codes):
                if i % 6 == 0 and i > 0:
                    print()
                print(f"  {code}", end=" ")
        
        # Verify no bottom 2 letters are included
        sorted_all = sorted(test_scores.items(), key=lambda x: (-x[1], x[0]))
        bottom_letters = [letter for letter, _ in sorted_all[4:]]  # 5th and 6th letters
        
        invalid_codes = []
        for code in permutations:
            for letter in bottom_letters:
                if letter in code:
                    invalid_codes.append(code)
                    break
        
        if invalid_codes:
            print(f"\n\n❌ ERROR: Codes containing bottom letters {bottom_letters}: {invalid_codes}")
        else:
            print(f"\n\n✅ SUCCESS: No codes contain bottom letters {bottom_letters}")
        
        return permutations

    # -------------------------
    # Tie-breaker logic
    # -------------------------
    def needs_tie_breaker_for_pair(self, pair, riasec_scores, delta=None):
        """
        Returns True if absolute difference < delta (i.e. needs tie-breaker).
        pair: tuple/list of 2 codes, e.g. ('R','I')
        """
        if not pair or len(pair) != 2:
            return False
        d = delta if delta is not None else int(os.getenv('TIE_BREAKER_DELTA', 1))
        score1 = riasec_scores.get(pair[0], 0)
        score2 = riasec_scores.get(pair[1], 0)
        return abs(score1 - score2) < d

    def select_tie_breaker_pairs(self, riasec_scores, delta=None):
        """
        Return list of normalized tuple pairs (alphabetically sorted) that need tie-breakers
        considering only the TOP 3 codes.
        """
        # Sort codes by score desc, then by code to keep deterministic ordering.
        sorted_scores = sorted(riasec_scores.items(), key=lambda x: (-x[1], x[0]))
        if len(sorted_scores) < 2:
            return []

        top_three = sorted_scores[:3]
        d = delta if delta is not None else int(os.getenv('TIE_BREAKER_DELTA', 1))

        pairs = []
        for i in range(len(top_three)):
            for j in range(i + 1, len(top_three)):
                c1, s1 = top_three[i]
                c2, s2 = top_three[j]
                if abs(s1 - s2) < d:
                    pair = tuple(sorted((c1, c2)))
                    if pair not in pairs:
                        pairs.append(pair)
        return pairs

    def has_reached_max_questions_for_pair(self, pair_str, pair_question_count_map=None, max_q=None):
        """
        pair_str: normalized string 'C-R' (alphabetically sorted)
        pair_question_count_map: session map of counts per pair
        """
        pq = pair_question_count_map or {}
        m = max_q if max_q is not None else int(os.getenv('MAX_TIE_BREAKER_ROUNDS', 3))
        return pq.get(pair_str, 0) >= m

    def get_next_tie_breaker_question(self, active_pairs, used_original_numbers=None):
        """
        Pick next tie question for the first active pair that has an unasked question.
        Returns (question_copy, normalized_pair_str) or (None, None)
        used_original_numbers: set/list of original_numbers of tie questions already used (if questions in pool have fixed 'number' field)
        """
        used = set(used_original_numbers or [])

        # Build map: normalized pair -> list of pool questions (preserve original question identity)
        pair_map = {}
        for q in self.tie_breaker_questions_pool:
            pair_field = q.get('pair') or ''
            if not pair_field:
                continue
            codes = pair_field.split('-')
            normalized = '-'.join(sorted(codes))
            pair_map.setdefault(normalized, []).append(q)

        for pair in active_pairs:
            pair_str = '-'.join(sorted(pair))
            candidate_questions = pair_map.get(pair_str, [])
            if not candidate_questions:
                continue

            # find first pool question not used yet (compare by pool 'number' if present, else by id())
            for pq in candidate_questions:
                original_num = pq.get('number', id(pq))
                if original_num not in used:
                    # return a copy; caller should assign a unique session number
                    return deepcopy(pq), pair_str

        return None, None

    def assign_unique_number_to_tie_question(self, question, existing_count_main, existing_tie_session_count):
        """
        Give a unique in-session 'number' to tie question to avoid collisions.
        existing_count_main: len(main questions)
        existing_tie_session_count: how many tie questions currently in session (so start index)
        """
        start = existing_count_main + existing_tie_session_count + 1
        question['number'] = start
        return question

    # -------------------------
    # Utilities for transport
    # -------------------------
    def prepare_question_for_client(self, question):
        """
        Remove internal-only keys from question before sending to client.
        Keep: number, question/text, options (with text).
        """
        q = {
            'number': question.get('number'),
            'question': question.get('question') or question.get('text'),
            'text': question.get('question') or question.get('text'),
            'options': {}
        }
        for key, opt in question.get('options', {}).items():
            # send only text (and value if you want)
            q['options'][key] = {
                'text': opt.get('text')
            }
        # if tie pair info exists, include it for debugging / UI
        if question.get('pair'):
            q['pair'] = question.get('pair')
        return q