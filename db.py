"""SQLite database layer for the Music Quiz application."""

import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DB_PATH = os.environ.get(
    "QUIZ_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "quiz.db"),
)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def slugify(text: str) -> str:
    """Create a URL-safe slug from a title."""
    replacements = {
        "å": "a",
        "ä": "a",
        "ö": "o",
        "Å": "a",
        "Ä": "a",
        "Ö": "o",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return slug or f"quiz-{secrets.token_hex(3)}"


def init_db() -> None:
    """Create tables if they do not exist and seed a sample quiz if empty."""
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS quizzes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quiz_id INTEGER NOT NULL,
                order_index INTEGER NOT NULL DEFAULT 0,
                prompt TEXT NOT NULL,
                question_type TEXT NOT NULL DEFAULT 'artist_song',
                options_json TEXT NOT NULL DEFAULT '[]',
                correct_answer TEXT NOT NULL DEFAULT '',
                points INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quiz_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submission_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                answer_text TEXT NOT NULL DEFAULT '',
                is_correct INTEGER DEFAULT NULL,
                awarded_points INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (submission_id) REFERENCES submissions(id) ON DELETE CASCADE,
                FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
            );
            """
        )

        count = conn.execute("SELECT COUNT(*) FROM quizzes").fetchone()[0]
        if count == 0:
            now = datetime.now(timezone.utc).isoformat()
            cur = conn.execute(
                "INSERT INTO quizzes (slug, title, description, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
                (
                    "fredagsquiz",
                    "Fredagens Musikquiz",
                    "Välkommen! Skriv in ditt namn eller lagnamn och svara på frågorna medan musiken spelas.",
                    now,
                ),
            )
            quiz_id = cur.lastrowid
            sample_questions = [
                (
                    quiz_id,
                    1,
                    "Låt 1: Vilken artist och låt hör vi?",
                    "artist_song",
                    "[]",
                    "ABBA - Dancing Queen",
                    2,
                ),
                (
                    quiz_id,
                    2,
                    "Låt 2: Vilket år släpptes den här klassikern?",
                    "multiple_choice",
                    json.dumps(["1979", "1984", "1991", "1996"]),
                    "1984",
                    1,
                ),
                (
                    quiz_id,
                    3,
                    "Låt 3: Vad heter sångaren/bandet?",
                    "text",
                    "[]",
                    "Kent",
                    1,
                ),
            ]
            conn.executemany(
                """
                INSERT INTO questions (quiz_id, order_index, prompt, question_type, options_json, correct_answer, points)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                sample_questions,
            )


def _row_to_quiz(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "slug": row["slug"],
        "title": row["title"],
        "description": row["description"],
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
    }


def _row_to_question(row: sqlite3.Row, include_answer: bool = False) -> Dict[str, Any]:
    raw_options = json.loads(row["options_json"] or "[]")
    q_type = row["question_type"]
    if q_type == "multi_fields" and not include_answer:
        options = [
            {k: v for k, v in f.items() if k != "correct"}
            for f in raw_options
            if isinstance(f, dict)
        ]
    else:
        options = raw_options

    data: Dict[str, Any] = {
        "id": row["id"],
        "quiz_id": row["quiz_id"],
        "order_index": row["order_index"],
        "prompt": row["prompt"],
        "question_type": q_type,
        "options": options,
        "points": row["points"],
    }
    if include_answer:
        data["correct_answer"] = row["correct_answer"]
    return data


def list_quizzes() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT q.*,
                   (SELECT COUNT(*) FROM questions qu WHERE qu.quiz_id = q.id) AS question_count,
                   (SELECT COUNT(*) FROM submissions s WHERE s.quiz_id = q.id) AS submission_count
            FROM quizzes q
            ORDER BY q.created_at DESC
            """
        ).fetchall()
        result = []
        for row in rows:
            item = _row_to_quiz(row)
            item["question_count"] = row["question_count"]
            item["submission_count"] = row["submission_count"]
            result.append(item)
        return result


def get_quiz_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM quizzes WHERE slug = ?", (slug,)).fetchone()
        if not row:
            return None
        quiz = _row_to_quiz(row)
        q_rows = conn.execute(
            "SELECT * FROM questions WHERE quiz_id = ? ORDER BY order_index ASC, id ASC",
            (quiz["id"],),
        ).fetchall()
        quiz["questions"] = [_row_to_question(r, include_answer=False) for r in q_rows]
        return quiz


def get_default_active_quiz() -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM quizzes WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return get_quiz_by_slug(row["slug"])


def create_quiz(title: str, description: str = "", slug: str = "") -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    base_slug = slugify(slug or title)
    with get_connection() as conn:
        candidate = base_slug
        suffix = 1
        while conn.execute("SELECT 1 FROM quizzes WHERE slug = ?", (candidate,)).fetchone():
            suffix += 1
            candidate = f"{base_slug}-{suffix}"
        cur = conn.execute(
            "INSERT INTO quizzes (slug, title, description, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
            (candidate, title.strip(), description.strip(), now),
        )
        row = conn.execute("SELECT * FROM quizzes WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_quiz(row)


def update_quiz(quiz_id: int, title: Optional[str], description: Optional[str], is_active: Optional[bool]) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
        if not row:
            return None
        new_title = title.strip() if title is not None else row["title"]
        new_desc = description.strip() if description is not None else row["description"]
        new_active = (1 if is_active else 0) if is_active is not None else row["is_active"]
        conn.execute(
            "UPDATE quizzes SET title = ?, description = ?, is_active = ? WHERE id = ?",
            (new_title, new_desc, new_active, quiz_id),
        )
        updated = conn.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
        return _row_to_quiz(updated)


def delete_quiz(quiz_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM quizzes WHERE id = ?", (quiz_id,))
        return cur.rowcount > 0


def list_questions(quiz_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM questions WHERE quiz_id = ? ORDER BY order_index ASC, id ASC",
            (quiz_id,),
        ).fetchall()
        return [_row_to_question(r, include_answer=True) for r in rows]


def add_question(
    quiz_id: int,
    prompt: str,
    question_type: str = "artist_song",
    options: Optional[List[Any]] = None,
    correct_answer: str = "",
    points: int = 1,
) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        if not conn.execute("SELECT 1 FROM quizzes WHERE id = ?", (quiz_id,)).fetchone():
            return None
        max_order = conn.execute(
            "SELECT COALESCE(MAX(order_index), 0) FROM questions WHERE quiz_id = ?",
            (quiz_id,),
        ).fetchone()[0]

        clean_options = options or []
        total_points = max(1, int(points))
        derived_correct = correct_answer.strip()
        if question_type == "multi_fields" and isinstance(clean_options, list):
            clean_options = clean_options[:5]
            total_points = sum(max(1, int(f.get("points", 1))) for f in clean_options) or 1
            if not derived_correct:
                facit_parts = [
                    f"{f.get('label', '')}: {f.get('correct', '').strip()}"
                    for f in clean_options
                    if str(f.get("correct", "")).strip()
                ]
                derived_correct = " | ".join(facit_parts)

        cur = conn.execute(
            """
            INSERT INTO questions (quiz_id, order_index, prompt, question_type, options_json, correct_answer, points)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                quiz_id,
                max_order + 1,
                prompt.strip(),
                question_type,
                json.dumps(clean_options, ensure_ascii=False),
                derived_correct,
                total_points,
            ),
        )
        row = conn.execute("SELECT * FROM questions WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_question(row, include_answer=True)


def update_question(
    question_id: int,
    prompt: Optional[str] = None,
    question_type: Optional[str] = None,
    options: Optional[List[str]] = None,
    correct_answer: Optional[str] = None,
    points: Optional[int] = None,
    order_index: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        if not row:
            return None
        conn.execute(
            """
            UPDATE questions
            SET prompt = ?, question_type = ?, options_json = ?, correct_answer = ?, points = ?, order_index = ?
            WHERE id = ?
            """,
            (
                prompt.strip() if prompt is not None else row["prompt"],
                question_type if question_type is not None else row["question_type"],
                json.dumps(options) if options is not None else row["options_json"],
                correct_answer.strip() if correct_answer is not None else row["correct_answer"],
                max(1, int(points)) if points is not None else row["points"],
                int(order_index) if order_index is not None else row["order_index"],
                question_id,
            ),
        )
        updated = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        return _row_to_question(updated, include_answer=True)


def delete_question(question_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))
        return cur.rowcount > 0


def _auto_grade(
    answer_text: str,
    correct_answer: str,
    max_points: int,
    question_type: str = "text",
    options_json: str = "[]",
) -> tuple[Optional[int], int]:
    """Simple exact/case-insensitive match when correct_answer is provided."""
    if question_type == "multi_fields":
        try:
            fields_cfg = json.loads(options_json or "[]")
            ans_obj = json.loads(answer_text or "{}")
            ans_fields = ans_obj.get("fields", {}) if isinstance(ans_obj, dict) else {}
        except json.JSONDecodeError:
            return (None, 0)

        has_any_facit = any(str(f.get("correct", "")).strip() for f in fields_cfg)
        if not has_any_facit:
            return (None, 0)

        awarded = 0
        all_checked_correct = True
        any_answered = False
        for f in fields_cfg:
            key = f.get("key", "")
            user_val = re.sub(r"\s+", " ", str(ans_fields.get(key, "")).strip().lower())
            corr_val = re.sub(r"\s+", " ", str(f.get("correct", "")).strip().lower())
            pts = max(1, int(f.get("points", 1)))
            if user_val:
                any_answered = True
            if corr_val:
                if user_val == corr_val:
                    awarded += pts
                else:
                    all_checked_correct = False
        if not any_answered:
            return (0, 0)
        return (1 if all_checked_correct else None, awarded)

    if not correct_answer.strip():
        return (None, 0)
    norm_ans = re.sub(r"\s+", " ", answer_text.strip().lower())
    norm_corr = re.sub(r"\s+", " ", correct_answer.strip().lower())
    if not norm_ans:
        return (0, 0)
    if norm_ans == norm_corr:
        return (1, max_points)
    return (None, 0)


def submit_quiz_answers(
    slug: str, username: str, answers: List[Dict[str, Any]]
) -> Dict[str, Any]:
    clean_name = username.strip()
    if not clean_name:
        raise ValueError("Användarnamn krävs.")

    with get_connection() as conn:
        quiz = conn.execute("SELECT * FROM quizzes WHERE slug = ?", (slug,)).fetchone()
        if not quiz:
            raise LookupError("Quizet hittades inte.")
        if not quiz["is_active"]:
            raise PermissionError("Det här quizet är stängt för nya svar.")

        q_rows = conn.execute(
            "SELECT * FROM questions WHERE quiz_id = ?", (quiz["id"],)
        ).fetchall()
        questions_by_id = {r["id"]: r for r in q_rows}

        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO submissions (quiz_id, username, submitted_at) VALUES (?, ?, ?)",
            (quiz["id"], clean_name, now),
        )
        submission_id = cur.lastrowid

        answer_map = {
            int(a["question_id"]): str(a.get("answer_text", "")).strip()
            for a in answers
            if "question_id" in a
        }

        for q_id, q_row in questions_by_id.items():
            ans_text = answer_map.get(q_id, "")
            is_correct, pts = _auto_grade(
                ans_text,
                q_row["correct_answer"],
                q_row["points"],
                q_row["question_type"],
                q_row["options_json"],
            )
            conn.execute(
                """
                INSERT INTO answers (submission_id, question_id, answer_text, is_correct, awarded_points)
                VALUES (?, ?, ?, ?, ?)
                """,
                (submission_id, q_id, ans_text, is_correct, pts),
            )

        return {
            "submission_id": submission_id,
            "username": clean_name,
            "submitted_at": now,
        }


def list_submissions(quiz_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        subs = conn.execute(
            "SELECT * FROM submissions WHERE quiz_id = ? ORDER BY submitted_at DESC",
            (quiz_id,),
        ).fetchall()
        results = []
        for sub in subs:
            ans_rows = conn.execute(
                """
                SELECT a.*, q.prompt, q.correct_answer, q.points AS max_points, q.order_index,
                       q.question_type, q.options_json
                FROM answers a
                JOIN questions q ON q.id = a.question_id
                WHERE a.submission_id = ?
                ORDER BY q.order_index ASC, q.id ASC
                """,
                (sub["id"],),
            ).fetchall()
            ans_list = []
            total_points = 0
            max_total = 0
            for a in ans_rows:
                total_points += a["awarded_points"]
                max_total += a["max_points"]
                display_text = a["answer_text"]
                if a["question_type"] == "multi_fields":
                    try:
                        cfg = json.loads(a["options_json"] or "[]")
                        obj = json.loads(a["answer_text"] or "{}")
                        fields_map = obj.get("fields", {}) if isinstance(obj, dict) else {}
                        parts = [
                            f"{f.get('label', f.get('key', ''))}: {fields_map.get(f.get('key', ''), '').strip() or '—'}"
                            for f in cfg
                        ]
                        display_text = " | ".join(parts)
                    except (json.JSONDecodeError, AttributeError):
                        pass

                ans_list.append(
                    {
                        "id": a["id"],
                        "question_id": a["question_id"],
                        "prompt": a["prompt"],
                        "correct_answer": a["correct_answer"],
                        "max_points": a["max_points"],
                        "answer_text": display_text,
                        "is_correct": (
                            None if a["is_correct"] is None else bool(a["is_correct"])
                        ),
                        "awarded_points": a["awarded_points"],
                    }
                )
            results.append(
                {
                    "id": sub["id"],
                    "quiz_id": sub["quiz_id"],
                    "username": sub["username"],
                    "submitted_at": sub["submitted_at"],
                    "total_points": total_points,
                    "max_points": max_total,
                    "answers": ans_list,
                }
            )
        return results


def grade_answer(
    answer_id: int, is_correct: Optional[bool], awarded_points: int
) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM answers WHERE id = ?", (answer_id,)).fetchone()
        if not row:
            return None
        corr_val = None if is_correct is None else (1 if is_correct else 0)
        pts = max(0, int(awarded_points))
        conn.execute(
            "UPDATE answers SET is_correct = ?, awarded_points = ? WHERE id = ?",
            (corr_val, pts, answer_id),
        )
        return {"id": answer_id, "is_correct": is_correct, "awarded_points": pts}
