"""HTTP server for the Music Quiz backend API and static frontend."""

import csv
import io
import json
import mimetypes
import os
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

import db

PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
ADMIN_PIN = os.environ.get("ADMIN_PIN", "1234")
ACTIVE_TOKENS: set[str] = set()


class QuizHandler(BaseHTTPRequestHandler):
    server_version = "MusikQuiz/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        # Clean concise logging
        print(f"[{self.address_string()}] {format % args}")

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_csv(self, filename: str, content: str) -> None:
        body = content.encode("utf-8-sig")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Optional[Dict[str, Any]]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Ogiltig JSON-data."})
            return None

    def _require_admin(self) -> bool:
        auth = self.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        if not token or token not in ACTIVE_TOKENS:
            self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Admin-inloggning krävs."})
            return False
        return True

    def _serve_file(self, rel_path: str) -> None:
        safe_path = os.path.normpath(os.path.join(PUBLIC_DIR, rel_path.lstrip("/")))
        if not safe_path.startswith(PUBLIC_DIR) or not os.path.isfile(safe_path):
            self.send_error(HTTPStatus.NOT_FOUND, "Sidan hittades inte")
            return
        mime, _ = mimetypes.guess_type(safe_path)
        with open(safe_path, "rb") as f:
            data = f.read()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{mime or 'application/octet-stream'}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        # API routes
        if path == "/api/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return

        if path == "/api/quiz/active":
            quiz = db.get_default_active_quiz()
            if not quiz:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Inget aktivt quiz hittades."})
                return
            self._send_json(HTTPStatus.OK, quiz)
            return

        if path.startswith("/api/quizzes/") and path.count("/") == 3:
            slug = path.split("/")[3]
            quiz = db.get_quiz_by_slug(slug)
            if not quiz:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Quizet hittades inte."})
                return
            self._send_json(HTTPStatus.OK, quiz)
            return

        if path == "/api/admin/quizzes":
            if not self._require_admin():
                return
            self._send_json(HTTPStatus.OK, {"quizzes": db.list_quizzes()})
            return

        if path.startswith("/api/admin/quizzes/") and path.endswith("/questions"):
            if not self._require_admin():
                return
            try:
                quiz_id = int(path.split("/")[4])
            except (IndexError, ValueError):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Ogiltigt quiz-ID."})
                return
            self._send_json(HTTPStatus.OK, {"questions": db.list_questions(quiz_id)})
            return

        if path.startswith("/api/admin/quizzes/") and path.endswith("/submissions"):
            if not self._require_admin():
                return
            try:
                quiz_id = int(path.split("/")[4])
            except (IndexError, ValueError):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Ogiltigt quiz-ID."})
                return
            self._send_json(HTTPStatus.OK, {"submissions": db.list_submissions(quiz_id)})
            return

        if path.startswith("/api/admin/quizzes/") and path.endswith("/export"):
            if not self._require_admin():
                return
            try:
                quiz_id = int(path.split("/")[4])
            except (IndexError, ValueError):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Ogiltigt quiz-ID."})
                return
            subs = db.list_submissions(quiz_id)
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(["Användarnamn", "Inskickad", "Totalpoäng", "Maxpoäng", "Fråga", "Svar", "Poäng"])
            for s in subs:
                for a in s["answers"]:
                    writer.writerow([
                        s["username"],
                        s["submitted_at"],
                        s["total_points"],
                        s["max_points"],
                        a["prompt"],
                        a["answer_text"],
                        a["awarded_points"],
                    ])
            self._send_csv(f"quiz-{quiz_id}-resultat.csv", buf.getvalue())
            return

        # Frontend routes
        if path == "/" or path.startswith("/quiz/"):
            self._serve_file("index.html")
            return
        if path == "/admin" or path == "/admin/":
            self._serve_file("admin.html")
            return

        self._serve_file(path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/admin/login":
            data = self._read_json_body()
            if data is None:
                return
            pin = str(data.get("pin", ""))
            if not secrets.compare_digest(pin, ADMIN_PIN):
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Fel PIN-kod."})
                return
            token = secrets.token_urlsafe(24)
            ACTIVE_TOKENS.add(token)
            self._send_json(HTTPStatus.OK, {"token": token})
            return

        if path.startswith("/api/quizzes/") and path.endswith("/submit"):
            slug = path.split("/")[3]
            data = self._read_json_body()
            if data is None:
                return
            try:
                res = db.submit_quiz_answers(
                    slug=slug,
                    username=str(data.get("username", "")),
                    answers=data.get("answers", []),
                )
                self._send_json(HTTPStatus.CREATED, res)
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except LookupError as exc:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except PermissionError as exc:
                self._send_json(HTTPStatus.FORBIDDEN, {"error": str(exc)})
            return

        if path == "/api/admin/quizzes":
            if not self._require_admin():
                return
            data = self._read_json_body()
            if data is None:
                return
            title = str(data.get("title", "")).strip()
            if not title:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Titel krävs."})
                return
            quiz = db.create_quiz(
                title=title,
                description=str(data.get("description", "")),
                slug=str(data.get("slug", "")),
            )
            self._send_json(HTTPStatus.CREATED, quiz)
            return

        if path.startswith("/api/admin/quizzes/") and path.endswith("/questions"):
            if not self._require_admin():
                return
            try:
                quiz_id = int(path.split("/")[4])
            except (IndexError, ValueError):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Ogiltigt quiz-ID."})
                return
            data = self._read_json_body()
            if data is None:
                return
            prompt = str(data.get("prompt", "")).strip()
            if not prompt:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Frågetext krävs."})
                return
            q = db.add_question(
                quiz_id=quiz_id,
                prompt=prompt,
                question_type=str(data.get("question_type", "artist_song")),
                options=data.get("options", []),
                correct_answer=str(data.get("correct_answer", "")),
                points=int(data.get("points", 1)),
            )
            if not q:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Quizet hittades inte."})
                return
            self._send_json(HTTPStatus.CREATED, q)
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Endpoint hittades inte."})

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/admin/quizzes/") and path.count("/") == 4:
            if not self._require_admin():
                return
            try:
                quiz_id = int(path.split("/")[4])
            except ValueError:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Ogiltigt quiz-ID."})
                return
            data = self._read_json_body()
            if data is None:
                return
            updated = db.update_quiz(
                quiz_id=quiz_id,
                title=data.get("title"),
                description=data.get("description"),
                is_active=data.get("is_active"),
            )
            if not updated:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Quizet hittades inte."})
                return
            self._send_json(HTTPStatus.OK, updated)
            return

        if path.startswith("/api/admin/questions/") and path.count("/") == 4:
            if not self._require_admin():
                return
            try:
                q_id = int(path.split("/")[4])
            except ValueError:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Ogiltigt fråge-ID."})
                return
            data = self._read_json_body()
            if data is None:
                return
            updated = db.update_question(
                question_id=q_id,
                prompt=data.get("prompt"),
                question_type=data.get("question_type"),
                options=data.get("options"),
                correct_answer=data.get("correct_answer"),
                points=data.get("points"),
                order_index=data.get("order_index"),
            )
            if not updated:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Frågan hittades inte."})
                return
            self._send_json(HTTPStatus.OK, updated)
            return

        if path.startswith("/api/admin/answers/") and path.endswith("/grade"):
            if not self._require_admin():
                return
            try:
                ans_id = int(path.split("/")[4])
            except (IndexError, ValueError):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Ogiltigt svars-ID."})
                return
            data = self._read_json_body()
            if data is None:
                return
            res = db.grade_answer(
                answer_id=ans_id,
                is_correct=data.get("is_correct"),
                awarded_points=int(data.get("awarded_points", 0)),
            )
            if not res:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Svaret hittades inte."})
                return
            self._send_json(HTTPStatus.OK, res)
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Endpoint hittades inte."})

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/admin/quizzes/") and path.count("/") == 4:
            if not self._require_admin():
                return
            try:
                quiz_id = int(path.split("/")[4])
            except ValueError:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Ogiltigt quiz-ID."})
                return
            if not db.delete_quiz(quiz_id):
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Quizet hittades inte."})
                return
            self._send_json(HTTPStatus.OK, {"deleted": True})
            return

        if path.startswith("/api/admin/questions/") and path.count("/") == 4:
            if not self._require_admin():
                return
            try:
                q_id = int(path.split("/")[4])
            except ValueError:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Ogiltigt fråge-ID."})
                return
            if not db.delete_question(q_id):
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Frågan hittades inte."})
                return
            self._send_json(HTTPStatus.OK, {"deleted": True})
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Endpoint hittades inte."})


def run_server(host: str = "0.0.0.0", port: Optional[int] = None) -> None:
    db.init_db()
    listen_port = port or int(os.environ.get("PORT", "8000"))
    httpd = ThreadingHTTPServer((host, listen_port), QuizHandler)
    print(f"Musikquiz-servern körs på http://localhost:{listen_port}")
    print(f"Admin-panel: http://localhost:{listen_port}/admin (PIN: {ADMIN_PIN})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStänger ner servern...")
        httpd.server_close()


if __name__ == "__main__":
    run_server()
