from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException, status

from .codes import generate_join_code
from .database import connection
from .schemas import QuestionInput, QuizCreate, QuizUpdate

router = APIRouter(prefix="/api", tags=["quizzes and sessions"])


def _get_quiz(conn: sqlite3.Connection, quiz_id: int) -> sqlite3.Row:
    quiz = conn.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
    if quiz is None:
        raise HTTPException(status_code=404, detail="Викторина не найдена.")
    return quiz


def _get_session(conn: sqlite3.Connection, session_id: int) -> sqlite3.Row:
    session = conn.execute(
        "SELECT * FROM game_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if session is None:
        raise HTTPException(status_code=404, detail="Игровая сессия не найдена.")
    return session


def _quiz_summary(conn: sqlite3.Connection, quiz: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": quiz["id"],
        "title": quiz["title"],
        "created_at": quiz["created_at"],
        "question_count": conn.execute(
            "SELECT COUNT(*) FROM questions WHERE quiz_id = ?", (quiz["id"],)
        ).fetchone()[0],
        "session_count": conn.execute(
            "SELECT COUNT(*) FROM game_sessions WHERE quiz_id = ?", (quiz["id"],)
        ).fetchone()[0],
    }


def _quiz_details(conn: sqlite3.Connection, quiz: sqlite3.Row) -> dict[str, Any]:
    result = _quiz_summary(conn, quiz)
    result["questions"] = []
    questions = conn.execute(
        "SELECT * FROM questions WHERE quiz_id = ? ORDER BY position", (quiz["id"],)
    ).fetchall()
    for question in questions:
        options = conn.execute(
            """SELECT id, label, position, is_correct
               FROM question_options WHERE question_id = ? ORDER BY position""",
            (question["id"],),
        ).fetchall()
        result["questions"].append(
            {
                "id": question["id"],
                "prompt": question["prompt"],
                "position": question["position"],
                "points": question["points"],
                "options": [dict(option) for option in options],
            }
        )
    return result


def _session_details(conn: sqlite3.Connection, session: sqlite3.Row) -> dict[str, Any]:
    quiz = _get_quiz(conn, session["quiz_id"])
    return {
        "id": session["id"],
        "quiz_id": session["quiz_id"],
        "quiz_title": quiz["title"],
        "join_code": session["join_code"],
        "status": session["status"],
        "created_at": session["created_at"],
    }


def _ensure_quiz_editable(conn: sqlite3.Connection, quiz_id: int) -> None:
    has_session = conn.execute(
        "SELECT 1 FROM game_sessions WHERE quiz_id = ? LIMIT 1", (quiz_id,)
    ).fetchone()
    if has_session:
        raise HTTPException(
            status_code=409,
            detail="Нельзя менять вопросы после создания игровой сессии.",
        )


def _normalized_options(payload: QuestionInput) -> list[tuple[str, int]]:
    options = [(option.label.strip(), int(option.is_correct)) for option in payload.options]
    if any(not label for label, _ in options):
        raise HTTPException(status_code=422, detail="Текст варианта ответа не может быть пустым.")
    if sum(correct for _, correct in options) > 1:
        raise HTTPException(status_code=422, detail="У вопроса может быть не более одного правильного ответа.")
    return options


def _insert_options(
    conn: sqlite3.Connection, question_id: int, options: list[tuple[str, int]]
) -> None:
    for position, (label, is_correct) in enumerate(options, start=1):
        conn.execute(
            """INSERT INTO question_options
               (question_id, label, position, is_correct) VALUES (?, ?, ?, ?)""",
            (question_id, label, position, is_correct),
        )


def _unique_code(conn: sqlite3.Connection, current: str | None = None) -> str:
    for _ in range(50):
        code = generate_join_code()
        if code == current:
            continue
        if conn.execute(
            "SELECT 1 FROM game_sessions WHERE join_code = ?", (code,)
        ).fetchone() is None:
            return code
    raise HTTPException(status_code=503, detail="Не удалось сгенерировать уникальный код доступа.")


@router.post("/quizzes", status_code=status.HTTP_201_CREATED)
def create_quiz(payload: QuizCreate) -> dict[str, Any]:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Название викторины не может быть пустым.")
    with connection() as conn:
        cursor = conn.execute("INSERT INTO quizzes (title) VALUES (?)", (title,))
        return _quiz_summary(conn, _get_quiz(conn, cursor.lastrowid))


@router.get("/quizzes")
def list_quizzes() -> dict[str, Any]:
    with connection() as conn:
        quizzes = conn.execute("SELECT * FROM quizzes ORDER BY id DESC").fetchall()
        return {"quizzes": [_quiz_summary(conn, quiz) for quiz in quizzes], "count": len(quizzes)}


@router.get("/quizzes/{quiz_id}")
def get_quiz(quiz_id: int) -> dict[str, Any]:
    with connection() as conn:
        return _quiz_details(conn, _get_quiz(conn, quiz_id))


@router.patch("/quizzes/{quiz_id}")
def update_quiz(quiz_id: int, payload: QuizUpdate) -> dict[str, Any]:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Название викторины не может быть пустым.")
    with connection() as conn:
        _get_quiz(conn, quiz_id)
        conn.execute("UPDATE quizzes SET title = ? WHERE id = ?", (title, quiz_id))
        return _quiz_summary(conn, _get_quiz(conn, quiz_id))


@router.delete("/quizzes/{quiz_id}")
def delete_quiz(quiz_id: int) -> dict[str, bool]:
    try:
        with connection() as conn:
            cursor = conn.execute("DELETE FROM quizzes WHERE id = ?", (quiz_id,))
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Викторина не найдена.")
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Нельзя удалить викторину, у которой есть игровые сессии.",
        ) from exc
    return {"deleted": True}


@router.post("/quizzes/{quiz_id}/questions", status_code=status.HTTP_201_CREATED)
def add_question(quiz_id: int, payload: QuestionInput) -> dict[str, Any]:
    prompt = payload.prompt.strip()
    options = _normalized_options(payload)
    if not prompt:
        raise HTTPException(status_code=422, detail="Текст вопроса не может быть пустым.")
    with connection() as conn:
        _get_quiz(conn, quiz_id)
        _ensure_quiz_editable(conn, quiz_id)
        position = conn.execute(
            "SELECT COALESCE(MAX(position), 0) + 1 FROM questions WHERE quiz_id = ?",
            (quiz_id,),
        ).fetchone()[0]
        cursor = conn.execute(
            "INSERT INTO questions (quiz_id, prompt, position, points) VALUES (?, ?, ?, ?)",
            (quiz_id, prompt, position, payload.points),
        )
        question_id = cursor.lastrowid
        _insert_options(conn, question_id, options)
        return _quiz_details(conn, _get_quiz(conn, quiz_id))["questions"][-1]


@router.put("/quizzes/{quiz_id}/questions/{question_id}")
def update_question(quiz_id: int, question_id: int, payload: QuestionInput) -> dict[str, Any]:
    prompt = payload.prompt.strip()
    options = _normalized_options(payload)
    if not prompt:
        raise HTTPException(status_code=422, detail="Текст вопроса не может быть пустым.")
    with connection() as conn:
        _get_quiz(conn, quiz_id)
        _ensure_quiz_editable(conn, quiz_id)
        question = conn.execute(
            "SELECT * FROM questions WHERE id = ? AND quiz_id = ?", (question_id, quiz_id)
        ).fetchone()
        if question is None:
            raise HTTPException(status_code=404, detail="Вопрос не найден.")
        conn.execute(
            "UPDATE questions SET prompt = ?, points = ? WHERE id = ?",
            (prompt, payload.points, question_id),
        )
        conn.execute("DELETE FROM question_options WHERE question_id = ?", (question_id,))
        _insert_options(conn, question_id, options)
        updated = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        option_rows = conn.execute(
            "SELECT id, label, position, is_correct FROM question_options "
            "WHERE question_id = ? ORDER BY position",
            (question_id,),
        ).fetchall()
        return {
            "id": updated["id"],
            "prompt": updated["prompt"],
            "position": updated["position"],
            "points": updated["points"],
            "options": [dict(row) for row in option_rows],
        }


@router.delete("/quizzes/{quiz_id}/questions/{question_id}")
def delete_question(quiz_id: int, question_id: int) -> dict[str, bool]:
    with connection() as conn:
        _get_quiz(conn, quiz_id)
        _ensure_quiz_editable(conn, quiz_id)
        cursor = conn.execute(
            "DELETE FROM questions WHERE id = ? AND quiz_id = ?", (question_id, quiz_id)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Вопрос не найден.")
    return {"deleted": True}


@router.post("/quizzes/{quiz_id}/sessions", status_code=status.HTTP_201_CREATED)
def create_session(quiz_id: int) -> dict[str, Any]:
    with connection() as conn:
        quiz = _get_quiz(conn, quiz_id)
        for attempt in range(50):
            code = _unique_code(conn)
            try:
                cursor = conn.execute(
                    "INSERT INTO game_sessions (quiz_id, join_code) VALUES (?, ?)",
                    (quiz_id, code),
                )
                return _session_details(conn, _get_session(conn, cursor.lastrowid))
            except sqlite3.IntegrityError:
                if attempt == 49:
                    raise HTTPException(status_code=503, detail="Не удалось создать код доступа.")
        raise HTTPException(status_code=503, detail="Не удалось создать игровую сессию.")


@router.get("/sessions")
def list_sessions() -> dict[str, Any]:
    with connection() as conn:
        sessions = conn.execute("SELECT * FROM game_sessions ORDER BY id DESC").fetchall()
        return {"sessions": [_session_details(conn, row) for row in sessions], "count": len(sessions)}


@router.get("/sessions/by-code/{join_code}")
def get_session_by_code(join_code: str) -> dict[str, Any]:
    with connection() as conn:
        session = conn.execute(
            "SELECT * FROM game_sessions WHERE join_code = ?", (join_code.strip().upper(),)
        ).fetchone()
        if session is None:
            raise HTTPException(status_code=404, detail="Код входа не найден.")
        return _session_details(conn, session)


@router.get("/sessions/{session_id}")
def get_session(session_id: int) -> dict[str, Any]:
    with connection() as conn:
        return _session_details(conn, _get_session(conn, session_id))


@router.post("/sessions/{session_id}/regenerate-code")
def regenerate_code(session_id: int) -> dict[str, Any]:
    with connection() as conn:
        session = _get_session(conn, session_id)
        if session["status"] != "waiting":
            raise HTTPException(status_code=409, detail="Код можно менять только до начала сессии.")
        code = _unique_code(conn, session["join_code"])
        conn.execute("UPDATE game_sessions SET join_code = ? WHERE id = ?", (code, session_id))
        return {"session_id": session_id, "join_code": code}


@router.post("/sessions/{session_id}/start")
def start_session(session_id: int) -> dict[str, Any]:
    with connection() as conn:
        session = _get_session(conn, session_id)
        if session["status"] != "waiting":
            raise HTTPException(status_code=409, detail="Начать можно только ожидающую сессию.")
        questions = conn.execute(
            """SELECT q.id, COUNT(o.id) AS option_count,
                      COALESCE(SUM(o.is_correct), 0) AS correct_count
               FROM questions q
               LEFT JOIN question_options o ON o.question_id = q.id
               WHERE q.quiz_id = ?
               GROUP BY q.id ORDER BY q.position""",
            (session["quiz_id"],),
        ).fetchall()
        if not questions:
            raise HTTPException(status_code=409, detail="Добавьте вопросы перед запуском сессии.")
        if any(row["option_count"] < 2 or row["correct_count"] != 1 for row in questions):
            raise HTTPException(
                status_code=409,
                detail="У каждого вопроса должно быть минимум два варианта и один правильный.",
            )
        conn.execute("UPDATE game_sessions SET status = 'active' WHERE id = ?", (session_id,))
        return _session_details(conn, _get_session(conn, session_id))


@router.post("/sessions/{session_id}/finish")
def finish_session(session_id: int) -> dict[str, Any]:
    with connection() as conn:
        session = _get_session(conn, session_id)
        if session["status"] != "finished":
            conn.execute("UPDATE game_sessions SET status = 'finished' WHERE id = ?", (session_id,))
            session = _get_session(conn, session_id)
        return _session_details(conn, session)
