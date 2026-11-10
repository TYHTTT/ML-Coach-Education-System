from __future__ import annotations

import json
import hashlib
import hmac
import math
import secrets
import uuid
from collections.abc import Sequence
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg

from app.core.exceptions import (
    CourseTopicMismatchError,
    DuplicateSubmissionError,
    PracticeSetAlreadySubmittedError,
    PracticeSetNotFoundError,
    StudentNotFoundError,
    TopicNotFoundError,
)
from app.core.types import Course
from app.curriculum.models import CurriculumSeed
from app.curriculum.validation import CrossCourseDependencyError
from app.db.database import PostgresConnection, PostgresDatabase
from app.schemas.learning import EvaluationResultInternal
from app.schemas.practice import PracticeQuestionInternal, PracticeSetInternal


class LearningRepository:
    """Persistence boundary for curriculum, students, and learning-loop state."""

    TOPIC_STATE_UPDATE_FIELDS = frozenset(
        {
            "alpha",
            "beta",
            "mastery",
            "confidence",
            "evidence_count",
            "attempt_count",
            "practice_set_count",
            "checkpoint_count",
            "latest_score",
            "best_score",
            "latest_checkpoint_score",
            "status",
            "started_at",
            "last_practiced_at",
            "mastered_at",
        }
    )
    DIMENSION_STATE_UPDATE_FIELDS = frozenset(
        {"alpha", "beta", "mastery", "confidence", "evidence_count"}
    )

    def __init__(self, database_url: str | PostgresDatabase) -> None:
        self.database = (
            database_url
            if isinstance(database_url, PostgresDatabase)
            else PostgresDatabase(database_url)
        )

    def _connect(self) -> PostgresConnection:
        """Return the shared configured connection for integrated Phase 2 services."""

        return self.database.connect()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _row(row: dict[str, Any] | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def create_anonymous_student(self) -> dict[str, Any]:
        student_id = str(uuid.uuid4())
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO students(id, created_at, last_active_at) VALUES (?, ?, ?)",
                (student_id, now, now),
            )
        return {"id": student_id, "created_at": now, "last_active_at": now}

    @staticmethod
    def _password_hash(password: str, salt: bytes | None = None) -> str:
        salt = salt or secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 600_000)
        return f"pbkdf2_sha256$600000${salt.hex()}${digest.hex()}"

    @staticmethod
    def _password_matches(password: str, encoded: str) -> bool:
        try:
            algorithm, rounds, salt_hex, digest_hex = encoded.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return False
            calculated = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds))
            return hmac.compare_digest(calculated.hex(), digest_hex)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def register_student(self, *, username: str, password: str, display_name: str) -> dict[str, Any]:
        student_id, now = str(uuid.uuid4()), self._now()
        normalized_username = username.strip().lower()
        with self._connect() as connection:
            existing = connection.execute("SELECT 1 FROM students WHERE username = ?", (normalized_username,)).fetchone()
            if existing is not None:
                raise ValueError("username_taken")
            connection.execute(
                """INSERT INTO students(id, username, display_name, password_hash, created_at, last_active_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (student_id, normalized_username, display_name.strip(), self._password_hash(password), now, now),
            )
        return self._issue_session(student_id)

    def authenticate_student(self, *, username: str, password: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            student = connection.execute(
                "SELECT id, username, display_name, password_hash, created_at FROM students WHERE username = ? AND active = 1",
                (username.strip().lower(),),
            ).fetchone()
        if student is None or not self._password_matches(password, student["password_hash"] or ""):
            return None
        return self._issue_session(student["id"])

    def _issue_session(self, student_id: str) -> dict[str, Any]:
        token, session_id, now = secrets.token_urlsafe(32), str(uuid.uuid4()), self._now()
        expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO student_sessions(id, student_id, token_hash, expires_at, created_at, last_used_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, student_id, self._token_hash(token), expires_at, now, now),
            )
            student = connection.execute(
                "SELECT id, username, display_name, created_at FROM students WHERE id = ?", (student_id,)
            ).fetchone()
        return {**dict(student), "access_token": token}

    def student_from_token(self, token: str, *, touch: bool = True) -> dict[str, Any]:
        now = self._now()
        with self._connect() as connection:
            student = connection.execute(
                """SELECT s.id, s.username, s.display_name, s.created_at, s.last_active_at
                   FROM student_sessions ss JOIN students s ON s.id = ss.student_id
                   WHERE ss.token_hash = ? AND ss.expires_at > ? AND s.active = 1""",
                (self._token_hash(token), now),
            ).fetchone()
            if student is None:
                raise StudentNotFoundError()
            if touch:
                connection.execute("UPDATE student_sessions SET last_used_at = ? WHERE token_hash = ?", (now, self._token_hash(token)))
                connection.execute("UPDATE students SET last_active_at = ? WHERE id = ?", (now, student["id"]))
        return dict(student)

    def revoke_session(self, token: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM student_sessions WHERE token_hash = ?", (self._token_hash(token),))

    def get_student(self, student_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, created_at, last_active_at FROM students WHERE id = ?",
                (student_id,),
            ).fetchone()
        return self._row(row)

    def require_student(self, student_id: str, *, touch: bool = True) -> dict[str, Any]:
        try:
            normalized = str(uuid.UUID(student_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise StudentNotFoundError() from exc
        now = self._now()
        with self._connect() as connection:
            if touch:
                cursor = connection.execute(
                    "UPDATE students SET last_active_at = ? WHERE id = ?",
                    (now, normalized),
                )
                if cursor.rowcount == 0:
                    raise StudentNotFoundError()
            row = connection.execute(
                "SELECT id, created_at, last_active_at FROM students WHERE id = ?",
                (normalized,),
            ).fetchone()
        if row is None:
            raise StudentNotFoundError()
        return dict(row)

    def touch_student(self, student_id: str) -> dict[str, Any]:
        return self.require_student(student_id, touch=True)

    def upsert_curriculum(self, seeds: Sequence[CurriculumSeed]) -> None:
        """Upsert stable topics and replace prerequisites for the supplied topics atomically."""

        now = self._now()
        topics = [
            (seed.course.value, topic)
            for seed in seeds
            for topic in seed.topics
        ]
        with self._connect() as connection:
            for course, topic in topics:
                existing = connection.execute(
                    "SELECT course FROM curriculum_topics WHERE id = ?", (topic.id,)
                ).fetchone()
                if existing is not None and existing["course"] != course:
                    raise CrossCourseDependencyError(
                        f"稳定知识点 ID {topic.id} 不能从 {existing['course']} 迁移到 {course}"
                    )
                connection.execute(
                    """
                    INSERT INTO curriculum_topics (
                        id, course, slug, title, stage, stage_title, order_index,
                        description, learning_objectives_json, aliases_json,
                        retrieval_keywords_json, difficulty, required_dimensions_json,
                        active, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        slug = excluded.slug,
                        title = excluded.title,
                        stage = excluded.stage,
                        stage_title = excluded.stage_title,
                        order_index = excluded.order_index,
                        description = excluded.description,
                        learning_objectives_json = excluded.learning_objectives_json,
                        aliases_json = excluded.aliases_json,
                        retrieval_keywords_json = excluded.retrieval_keywords_json,
                        difficulty = excluded.difficulty,
                        required_dimensions_json = excluded.required_dimensions_json,
                        active = excluded.active,
                        updated_at = excluded.updated_at
                    """,
                    (
                        topic.id,
                        course,
                        topic.slug,
                        topic.title,
                        topic.stage,
                        topic.stage_title,
                        topic.order_index,
                        topic.description,
                        self._dump_json(topic.learning_objectives),
                        self._dump_json(topic.aliases),
                        self._dump_json(topic.retrieval_keywords),
                        topic.difficulty,
                        self._dump_json(topic.required_dimensions),
                        int(topic.active),
                        now,
                        now,
                    ),
                )

            seeded_ids = [topic.id for _, topic in topics]
            connection.executemany(
                "DELETE FROM topic_prerequisites WHERE topic_id = ?",
                ((topic_id,) for topic_id in seeded_ids),
            )
            for course, topic in topics:
                for prerequisite in topic.prerequisites:
                    row = connection.execute(
                        "SELECT course FROM curriculum_topics WHERE id = ?",
                        (prerequisite.topic_id,),
                    ).fetchone()
                    if row is None:
                        raise ValueError(
                            f"知识点 {topic.id} 引用了不存在的前置知识点 "
                            f"{prerequisite.topic_id}"
                        )
                    connection.execute(
                        """
                        INSERT INTO topic_prerequisites(
                            topic_id, prerequisite_topic_id, required_mastery,
                            relation_type, reason, required_competencies_json, scope, section_id, rule_version
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (topic.id, prerequisite.topic_id, prerequisite.required_mastery,
                         prerequisite.relation_type, prerequisite.reason,
                         self._dump_json(prerequisite.required_competencies), prerequisite.scope,
                         prerequisite.section_id, prerequisite.rule_version),
                    )
            for course, topic in topics:
                connection.execute("""INSERT INTO topic_placements(course_id,topic_id,parent_group_id,group_title,order_index,is_reference)
                    VALUES (?,?,?,?,?,0) ON CONFLICT(course_id,topic_id) DO UPDATE SET
                    parent_group_id=excluded.parent_group_id,group_title=excluded.group_title,order_index=excluded.order_index""",
                    (course,topic.id,f"stage-{topic.stage}",topic.stage_title,topic.order_index))

    @staticmethod
    def _dump_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _load_json(value: str | None, fallback: Any) -> Any:
        return json.loads(value) if value else fallback

    def _topic_record(self, row: dict[str, Any]) -> dict[str, Any]:
        record = dict(row)
        for column, output in (
            ("learning_objectives_json", "learning_objectives"),
            ("aliases_json", "aliases"),
            ("retrieval_keywords_json", "retrieval_keywords"),
            ("required_dimensions_json", "required_dimensions"),
        ):
            record[output] = self._load_json(record.pop(column), [])
        record["active"] = bool(record["active"])
        return record

    def list_topics(
        self,
        course: Course | str,
        *,
        active_only: bool = True,
        student_id: str | None = None,
    ) -> list[dict[str, Any]]:
        course_value = course.value if isinstance(course, Course) else Course(course).value
        params: list[Any] = []
        state_columns = "NULL AS state_status, NULL AS state_mastery, NULL AS state_confidence, NULL AS state_evidence_count"
        join = ""
        if student_id is not None:
            params.append(student_id)
            join = (
                "LEFT JOIN student_topic_states sts "
                "ON sts.topic_id = t.id AND sts.student_id = ?"
            )
            state_columns = (
                "sts.status AS state_status, sts.mastery AS state_mastery, "
                "sts.confidence AS state_confidence, sts.evidence_count AS state_evidence_count"
            )
        params.append(course_value)
        active_clause = "AND t.active = 1" if active_only else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT t.*, {state_columns}
                FROM curriculum_topics t
                {join}
                WHERE t.course = ? {active_clause}
                ORDER BY t.stage, t.order_index
                """,
                tuple(params),
            ).fetchall()
        prerequisites_by_topic = self.list_prerequisites_for_topics(
            [row["id"] for row in rows]
        )
        records = []
        for row in rows:
            record = self._topic_record(row)
            record["prerequisites"] = prerequisites_by_topic[record["id"]]
            records.append(record)
        return records

    def get_topic(
        self, topic_id: str, *, student_id: str | None = None
    ) -> dict[str, Any] | None:
        params: list[Any] = []
        join = ""
        state_columns = "NULL AS state_status, NULL AS state_mastery, NULL AS state_confidence"
        if student_id is not None:
            params.append(student_id)
            join = (
                "LEFT JOIN student_topic_states sts "
                "ON sts.topic_id = t.id AND sts.student_id = ?"
            )
            state_columns = (
                "sts.status AS state_status, sts.mastery AS state_mastery, "
                "sts.confidence AS state_confidence"
            )
        params.append(topic_id)
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT t.*, {state_columns}
                FROM curriculum_topics t
                {join}
                WHERE t.id = ?
                """,
                tuple(params),
            ).fetchone()
        if row is None:
            return None
        record = self._topic_record(row)
        record["prerequisites"] = self.list_prerequisites(topic_id)
        return record

    def require_topic(
        self, topic_id: str, *, student_id: str | None = None
    ) -> dict[str, Any]:
        topic = self.get_topic(topic_id, student_id=student_id)
        if topic is None:
            raise TopicNotFoundError()
        return topic

    def list_prerequisites(self, topic_id: str) -> list[dict[str, Any]]:
        return self.list_prerequisites_for_topics([topic_id])[topic_id]

    def list_prerequisites_for_topics(
        self, topic_ids: Sequence[str]
    ) -> dict[str, list[dict[str, Any]]]:
        result = {topic_id: [] for topic_id in topic_ids}
        if not topic_ids:
            return result
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT p.id, p.slug, p.title, p.course, tp.topic_id, tp.required_mastery,
                       tp.relation_type, tp.reason, tp.required_competencies_json,
                       tp.scope, tp.section_id, tp.rule_version
                FROM topic_prerequisites tp
                JOIN curriculum_topics p ON p.id = tp.prerequisite_topic_id
                WHERE tp.topic_id = ANY(?)
                ORDER BY tp.topic_id, p.order_index
                """,
                (list(topic_ids),),
            ).fetchall()
        for row in rows:
            item = dict(row)
            item["dependent_topic_id"] = item.pop("topic_id")
            item["required_competencies"] = self._load_json(item.pop("required_competencies_json"), [])
            result[item["dependent_topic_id"]].append(item)
        return result

    def prerequisite_statuses(
        self, student_id: str | None, topic_ids: Sequence[str]
    ) -> dict[str, list[dict[str, Any]]]:
        result = {topic_id: [] for topic_id in topic_ids}
        if not topic_ids:
            return result
        with self._connect() as connection:
            rows = [dict(row) for row in connection.execute(
                """SELECT p.id,p.slug,p.title,p.course,tp.topic_id,tp.required_mastery,
                    tp.relation_type,tp.reason,tp.required_competencies_json,tp.scope,tp.section_id,tp.rule_version
                    FROM topic_prerequisites tp JOIN curriculum_topics p ON p.id=tp.prerequisite_topic_id
                    WHERE tp.topic_id = ANY(?) ORDER BY tp.topic_id,p.order_index""",
                (list(topic_ids),),
            )]
            prerequisite_ids = list({row["id"] for row in rows})
            states = {}
            verified_competencies: dict[tuple[str, str], set[str]] = {}
            if student_id is not None and prerequisite_ids:
                states = {
                    row["topic_id"]: dict(row)
                    for row in connection.execute(
                        "SELECT topic_id,mastery,status FROM student_topic_states WHERE student_id=? AND topic_id = ANY(?)",
                        (student_id, prerequisite_ids),
                    )
                }
                for row in connection.execute(
                    """SELECT prerequisite_topic_id,rule_version,competency FROM prerequisite_verifications
                        WHERE student_id=? AND prerequisite_topic_id = ANY(?)""",
                    (student_id, prerequisite_ids),
                ):
                    verified_competencies.setdefault(
                        (row["prerequisite_topic_id"], row["rule_version"]), set()
                    ).add(row["competency"])
        for item in rows:
            topic_id = item.pop("topic_id")
            item["dependent_topic_id"] = topic_id
            item["required_competencies"] = self._load_json(item.pop("required_competencies_json"), [])
            state = states.get(item["id"])
            verified = verified_competencies.get((item["id"], item["rule_version"]), set())
            needed = set(item["required_competencies"])
            item["verified_competencies"] = sorted(verified)
            item["mastery"] = state["mastery"] if state else None
            item["status"] = state["status"] if state else None
            item["satisfied"] = bool(
                state and state["status"] == "mastered" and state["mastery"] >= item["required_mastery"]
            ) or bool(needed and needed <= verified)
            result[topic_id].append(item)
        return result

    def get_unmet_prerequisites(
        self, student_id: str, topic_id: str
    ) -> list[dict[str, Any]]:
        return [item for item in self.prerequisite_status(student_id, topic_id)
                if item["relation_type"] == "required" and item["scope"] == "topic" and not item["satisfied"]]

    def prerequisite_status(self, student_id: str | None, topic_id: str) -> list[dict[str, Any]]:
        return self.prerequisite_statuses(student_id, [topic_id])[topic_id]

    def ensure_topic_state(
        self,
        student_id: str,
        topic_id: str,
        *,
        status: str = "not_started",
    ) -> dict[str, Any]:
        self.require_student(student_id, touch=False)
        self.require_topic(topic_id)
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO student_topic_states(student_id, topic_id, status, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(student_id, topic_id) DO NOTHING
                """,
                (student_id, topic_id, status, now),
            )
        state = self.get_topic_state(student_id, topic_id)
        assert state is not None
        return state

    def get_topic_state(self, student_id: str, topic_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM student_topic_states WHERE student_id = ? AND topic_id = ?",
                (student_id, topic_id),
            ).fetchone()
        return self._row(row)

    def list_topic_states(
        self, student_id: str, course: Course | str | None = None
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT sts.* FROM student_topic_states sts "
            "JOIN curriculum_topics t ON t.id = sts.topic_id "
            "WHERE sts.student_id = ?"
        )
        params: list[Any] = [student_id]
        if course is not None:
            course_value = course.value if isinstance(course, Course) else Course(course).value
            query += " AND t.course = ?"
            params.append(course_value)
        query += " ORDER BY t.stage, t.order_index"
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def update_topic_state(
        self,
        student_id: str,
        topic_id: str,
        **changes: Any,
    ) -> dict[str, Any]:
        invalid = set(changes) - self.TOPIC_STATE_UPDATE_FIELDS
        if invalid:
            raise ValueError(f"不允许更新字段: {', '.join(sorted(invalid))}")
        self.ensure_topic_state(student_id, topic_id)
        if not changes:
            state = self.get_topic_state(student_id, topic_id)
            assert state is not None
            return state
        changes["updated_at"] = self._now()
        assignments = ", ".join(f"{field} = ?" for field in changes)
        with self._connect() as connection:
            connection.execute(
                f"""
                UPDATE student_topic_states SET {assignments}
                WHERE student_id = ? AND topic_id = ?
                """,
                (*changes.values(), student_id, topic_id),
            )
        state = self.get_topic_state(student_id, topic_id)
        assert state is not None
        return state

    def ensure_dimension_state(
        self, student_id: str, topic_id: str, dimension: str
    ) -> dict[str, Any]:
        self.ensure_topic_state(student_id, topic_id)
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO student_dimension_states(
                    student_id, topic_id, dimension, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(student_id, topic_id, dimension) DO NOTHING
                """,
                (student_id, topic_id, dimension, now),
            )
        state = self.get_dimension_state(student_id, topic_id, dimension)
        assert state is not None
        return state

    def get_dimension_state(
        self, student_id: str, topic_id: str, dimension: str
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM student_dimension_states
                WHERE student_id = ? AND topic_id = ? AND dimension = ?
                """,
                (student_id, topic_id, dimension),
            ).fetchone()
        return self._row(row)

    def update_dimension_state(
        self,
        student_id: str,
        topic_id: str,
        dimension: str,
        **changes: Any,
    ) -> dict[str, Any]:
        invalid = set(changes) - self.DIMENSION_STATE_UPDATE_FIELDS
        if invalid:
            raise ValueError(f"不允许更新字段: {', '.join(sorted(invalid))}")
        self.ensure_dimension_state(student_id, topic_id, dimension)
        if changes:
            changes["updated_at"] = self._now()
            assignments = ", ".join(f"{field} = ?" for field in changes)
            with self._connect() as connection:
                connection.execute(
                    f"""
                    UPDATE student_dimension_states SET {assignments}
                    WHERE student_id = ? AND topic_id = ? AND dimension = ?
                    """,
                    (*changes.values(), student_id, topic_id, dimension),
                )
        state = self.get_dimension_state(student_id, topic_id, dimension)
        assert state is not None
        return state

    def list_dimension_states(
        self, student_id: str, topic_id: str
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM student_dimension_states
                WHERE student_id = ? AND topic_id = ?
                ORDER BY dimension
                """,
                (student_id, topic_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_recent_question_texts(
        self,
        student_id: str,
        topic_id: str,
        *,
        limit: int = 20,
    ) -> list[str]:
        """Return only question text used recently by this student and topic."""

        normalized_limit = max(0, int(limit))
        if normalized_limit == 0:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT q.question
                FROM practice_questions q
                JOIN practice_sets ps ON ps.id = q.practice_set_id
                WHERE ps.student_id = ? AND ps.topic_id = ?
                ORDER BY ps.created_at DESC, q.position DESC, q.id DESC
                LIMIT ?
                """,
                (student_id, topic_id, normalized_limit),
            ).fetchall()
        return [str(row["question"]) for row in rows]

    def list_recent_question_hashes(
        self,
        student_id: str,
        topic_id: str,
        *,
        limit: int = 20,
    ) -> set[str]:
        normalized_limit = max(0, int(limit))
        if normalized_limit == 0:
            return set()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT q.question_hash
                FROM practice_questions q
                JOIN practice_sets ps ON ps.id = q.practice_set_id
                WHERE ps.student_id = ? AND ps.topic_id = ?
                ORDER BY ps.created_at DESC, q.position DESC, q.id DESC
                LIMIT ?
                """,
                (student_id, topic_id, normalized_limit),
            ).fetchall()
        return {str(row["question_hash"]) for row in rows}

    def create_practice_set(
        self,
        *,
        student_id: str,
        practice_set: PracticeSetInternal,
        requested_difficulty: str = "adaptive",
        target_misconception_tags: Sequence[str] | None = None,
        _connection: PostgresConnection | None = None,
    ) -> str:
        """Persist the immutable grading snapshot and all questions atomically."""

        self.require_student(student_id, touch=False)
        topic = self.require_topic(practice_set.topic_id)
        if topic["course"] != practice_set.course.value:
            raise CourseTopicMismatchError()

        tags: list[str] = []
        seen_tags: set[str] = set()
        for tag in target_misconception_tags or ():
            normalized = str(tag).strip()
            if normalized and normalized not in seen_tags:
                tags.append(normalized)
                seen_tags.add(normalized)

        now = self._now()
        with (nullcontext(_connection) if _connection is not None else self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO practice_sets(
                    id, student_id, topic_id, course, mode, status,
                    requested_difficulty, source_snapshot_json,
                    target_misconception_tags_json, created_at
                ) VALUES (?, ?, ?, ?, ?, 'generated', ?, ?, ?, ?)
                """,
                (
                    practice_set.practice_set_id,
                    student_id,
                    practice_set.topic_id,
                    practice_set.course.value,
                    practice_set.kind,
                    requested_difficulty,
                    self._dump_json(
                        [item.model_dump(mode="json") for item in practice_set.source_snapshot]
                    ),
                    self._dump_json(tags),
                    now,
                ),
            )
            for question in practice_set.questions:
                connection.execute(
                    """
                    INSERT INTO practice_questions(
                        id, practice_set_id, position, question_type, difficulty,
                        question, options_json, dimensions_json, answer_key_json,
                        rubric_json, source_ids_json, question_hash, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        question.question_id,
                        practice_set.practice_set_id,
                        question.position,
                        question.question_type,
                        question.difficulty,
                        question.question,
                        (
                            self._dump_json(
                                [item.model_dump(mode="json") for item in question.options]
                            )
                            if question.options is not None
                            else None
                        ),
                        self._dump_json(question.dimensions),
                        self._dump_json(question.answer_key.model_dump(mode="json")),
                        self._dump_json(
                            [item.model_dump(mode="json") for item in question.rubric]
                        ),
                        self._dump_json(question.source_ids),
                        question.normalized_question_hash,
                        now,
                    ),
                )
        return practice_set.practice_set_id

    @staticmethod
    def _practice_question_from_row(row: dict[str, Any]) -> PracticeQuestionInternal:
        return PracticeQuestionInternal.model_validate(
            {
                "question_id": row["id"],
                "question_type": row["question_type"],
                "difficulty": row["difficulty"],
                "question": row["question"],
                "options": json.loads(row["options_json"]) if row["options_json"] else None,
                "dimensions": json.loads(row["dimensions_json"]),
                "answer_key": json.loads(row["answer_key_json"]),
                "rubric": json.loads(row["rubric_json"]),
                "source_ids": json.loads(row["source_ids_json"]),
                "position": row["position"],
                "max_score": 100,
            }
        )

    def get_practice_set_internal(
        self,
        practice_set_id: str,
        *,
        student_id: str | None = None,
    ) -> PracticeSetInternal:
        """Load the internal-only answer/rubric/source snapshot contract."""

        params: list[Any] = [practice_set_id]
        ownership_clause = ""
        if student_id is not None:
            ownership_clause = "AND ps.student_id = ?"
            params.append(student_id)
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT ps.*, t.required_dimensions_json
                FROM practice_sets ps
                JOIN curriculum_topics t ON t.id = ps.topic_id
                WHERE ps.id = ? {ownership_clause}
                """,
                tuple(params),
            ).fetchone()
            if row is None:
                raise PracticeSetNotFoundError()
            question_rows = connection.execute(
                """
                SELECT * FROM practice_questions
                WHERE practice_set_id = ?
                ORDER BY position, id
                """,
                (practice_set_id,),
            ).fetchall()

        return PracticeSetInternal(
            practice_set_id=row["id"],
            course=Course(row["course"]),
            topic_id=row["topic_id"],
            kind=row["mode"],
            required_dimensions=self._load_json(row["required_dimensions_snapshot_json"] or row["required_dimensions_json"], []),
            questions=[self._practice_question_from_row(item) for item in question_rows],
            source_snapshot=self._load_json(row["source_snapshot_json"], []),
            assessment_purpose=row['purpose'],
        )

    def get_practice_set_status(
        self,
        practice_set_id: str,
        *,
        student_id: str | None = None,
    ) -> str:
        query = "SELECT status FROM practice_sets WHERE id = ?"
        params: list[Any] = [practice_set_id]
        if student_id is not None:
            query += " AND student_id = ?"
            params.append(student_id)
        with self._connect() as connection:
            row = connection.execute(query, tuple(params)).fetchone()
        if row is None:
            raise PracticeSetNotFoundError()
        return str(row["status"])

    def get_submission_by_client_id(
        self,
        client_submission_id: str,
        *,
        student_id: str | None = None,
        practice_set_id: str | None = None,
    ) -> dict[str, Any] | None:
        query = "SELECT * FROM practice_submissions WHERE client_submission_id = ?"
        params: list[Any] = [client_submission_id]
        if student_id is not None:
            query += " AND student_id = ?"
            params.append(student_id)
        if practice_set_id is not None:
            query += " AND practice_set_id = ?"
            params.append(practice_set_id)
        with self._connect() as connection:
            row = connection.execute(query, tuple(params)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["gate_result"] = self._load_json(result["gate_result_json"], {})
        return result

    def reserve_submission(
        self,
        *,
        practice_set_id: str,
        student_id: str,
        client_submission_id: str,
        mastery_before: float,
    ) -> str:
        """Reserve one in-flight submission without creating empty attempts."""

        if not math.isfinite(mastery_before) or not 0 <= mastery_before <= 1:
            raise ValueError("mastery_before 必须是 0 到 1 之间的有限数")
        submission_id = str(uuid.uuid4())
        now = self._now()
        try:
            with self._connect() as connection:
                practice_set = connection.execute(
                    "SELECT student_id, status FROM practice_sets WHERE id = ? FOR UPDATE",
                    (practice_set_id,),
                ).fetchone()
                if practice_set is None or practice_set["student_id"] != student_id:
                    raise PracticeSetNotFoundError()
                if practice_set["status"] == "submitted":
                    raise PracticeSetAlreadySubmittedError()

                duplicate = connection.execute(
                    """
                    SELECT id FROM practice_submissions
                    WHERE client_submission_id = ?
                    """,
                    (client_submission_id,),
                ).fetchone()
                processing = connection.execute(
                    """
                    SELECT id FROM practice_submissions
                    WHERE practice_set_id = ? AND evaluation_status = 'processing'
                    """,
                    (practice_set_id,),
                ).fetchone()
                if duplicate is not None or processing is not None:
                    raise DuplicateSubmissionError()

                connection.execute(
                    """
                    INSERT INTO practice_submissions(
                        id, practice_set_id, student_id, client_submission_id,
                        total_score, evaluation_status, mastery_before,
                        mastery_after, gate_result_json, response_json, created_at
                    ) VALUES (?, ?, ?, ?, 0, 'processing', ?, ?, '{}', NULL, ?)
                    """,
                    (
                        submission_id,
                        practice_set_id,
                        student_id,
                        client_submission_id,
                        mastery_before,
                        mastery_before,
                        now,
                    ),
                )
        except psycopg.IntegrityError as exc:
            raise DuplicateSubmissionError() from exc
        return submission_id

    @staticmethod
    def _validated_evaluations(
        evaluations: Sequence[EvaluationResultInternal | dict[str, Any]],
    ) -> list[EvaluationResultInternal]:
        return [
            item
            if isinstance(item, EvaluationResultInternal)
            else EvaluationResultInternal.model_validate(item)
            for item in evaluations
        ]

    @classmethod
    def _validate_state_changes(
        cls,
        topic_changes: dict[str, Any],
        dimension_changes: dict[str, dict[str, Any]],
    ) -> None:
        invalid_topic = set(topic_changes) - cls.TOPIC_STATE_UPDATE_FIELDS
        if invalid_topic:
            raise ValueError(
                f"不允许更新字段: {', '.join(sorted(invalid_topic))}"
            )
        for dimension, changes in dimension_changes.items():
            if not str(dimension).strip():
                raise ValueError("能力维度不能为空")
            invalid_dimension = set(changes) - cls.DIMENSION_STATE_UPDATE_FIELDS
            if invalid_dimension:
                raise ValueError(
                    "不允许更新能力维度字段: "
                    + ", ".join(sorted(invalid_dimension))
                )

    def finalize_submission(
        self,
        *,
        submission_id: str,
        practice_set: PracticeSetInternal,
        answers: dict[str, str],
        evaluations: Sequence[EvaluationResultInternal | dict[str, Any]],
        attempt_ids: dict[str, str],
        total_score: float,
        evaluation_status: str,
        mastery_before: float,
        mastery_after: float,
        gate_result: dict[str, Any],
        response_json: str,
        topic_changes: dict[str, Any],
        dimension_changes: dict[str, dict[str, Any]],
        mark_submitted: bool,
        allow_evidence: bool = True,
    ) -> None:
        """Finalize attempts, diagnoses, mastery, and set status in one transaction."""

        normalized_evaluations = self._validated_evaluations(evaluations)
        expected_question_ids = [item.question_id for item in practice_set.questions]
        expected_question_set = set(expected_question_ids)
        if (
            len(expected_question_ids) != len(expected_question_set)
            or set(answers) != expected_question_set
            or set(attempt_ids) != expected_question_set
            or len(normalized_evaluations) != len(expected_question_ids)
        ):
            raise ValueError("提交答案、评价和 attempt_ids 必须完整匹配练习题")
        if len(set(attempt_ids.values())) != len(attempt_ids):
            raise ValueError("attempt_ids 不能重复")
        if any(not str(value).strip() for value in attempt_ids.values()):
            raise ValueError("attempt_id 不能为空")
        if any(not str(value).strip() for value in answers.values()):
            raise ValueError("答案不能为空")
        if any(
            not item.feedback.strip() or not item.reference_answer.strip()
            for item in normalized_evaluations
        ):
            raise ValueError("评价记录必须包含反馈和参考答案")
        for value, name, upper in (
            (total_score, "total_score", 100),
            (mastery_before, "mastery_before", 1),
            (mastery_after, "mastery_after", 1),
        ):
            if not math.isfinite(value) or not 0 <= value <= upper:
                raise ValueError(f"{name} 超出允许范围")
        if evaluation_status not in {"evaluated", "evaluation_uncertain"}:
            raise ValueError("evaluation_status 无效")
        if not isinstance(response_json, str) or not response_json.strip():
            raise ValueError("response_json 不能为空")

        all_reliable = all(item.evaluation_reliable for item in normalized_evaluations)
        if evaluation_status == "evaluated":
            if not all_reliable or not mark_submitted:
                raise ValueError("evaluated 提交必须全部可靠并标记为已提交")
        elif mark_submitted:
            raise ValueError("不可靠评价不能将练习标记为已提交")
        self._validate_state_changes(topic_changes, dimension_changes)
        mastery_updates_allowed = evaluation_status == "evaluated" and all_reliable and allow_evidence
        now = self._now()

        with self._connect() as connection:
            reservation = connection.execute(
                """
                SELECT s.practice_set_id, s.student_id, s.evaluation_status,
                       s.response_json, ps.status AS practice_set_status,
                       ps.topic_id, ps.target_misconception_tags_json
                FROM practice_submissions s
                JOIN practice_sets ps ON ps.id = s.practice_set_id
                WHERE s.id = ? FOR UPDATE OF s, ps
                """,
                (submission_id,),
            ).fetchone()
            if reservation is None:
                raise DuplicateSubmissionError()
            if (
                reservation["practice_set_id"] != practice_set.practice_set_id
                or reservation["topic_id"] != practice_set.topic_id
            ):
                raise DuplicateSubmissionError()
            if reservation["evaluation_status"] != "processing":
                # A retried database callback must not apply mastery evidence twice.
                if reservation["response_json"] == response_json:
                    return
                raise DuplicateSubmissionError()
            if reservation["practice_set_status"] == "submitted":
                raise PracticeSetAlreadySubmittedError()

            persisted_questions = {
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM practice_questions WHERE practice_set_id = ?",
                    (practice_set.practice_set_id,),
                ).fetchall()
            }
            if persisted_questions != expected_question_set:
                raise ValueError("数据库中的练习题与提交快照不一致")

            student_id = str(reservation["student_id"])
            target_tags = [
                str(tag).strip()
                for tag in self._load_json(
                    reservation["target_misconception_tags_json"], []
                )
                if str(tag).strip()
            ]
            if mastery_updates_allowed and total_score >= 80 and target_tags:
                placeholders = ", ".join("?" for _ in target_tags)
                connection.execute(
                    f"""
                    UPDATE misconception_events
                    SET resolved_at = ?
                    WHERE student_id = ? AND topic_id = ?
                      AND resolved_at IS NULL
                      AND tag IN ({placeholders})
                    """,
                    (now, student_id, practice_set.topic_id, *target_tags),
                )

            for question, evaluation in zip(
                practice_set.questions,
                normalized_evaluations,
                strict=True,
            ):
                attempt_id = str(attempt_ids[question.question_id])
                connection.execute(
                    """
                    INSERT INTO practice_attempts(
                        id, submission_id, question_id, student_id, answer_text,
                        score, verdict, dimension_scores_json,
                        correct_points_json, missing_points_json,
                        misconception_tags_json, critical_misconception,
                        feedback, reference_answer, evidence_source_ids_json,
                        evaluator_confidence, evaluation_reliable, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        attempt_id,
                        submission_id,
                        question.question_id,
                        student_id,
                        answers[question.question_id].strip(),
                        evaluation.score,
                        evaluation.verdict,
                        self._dump_json(evaluation.dimension_scores),
                        self._dump_json(evaluation.correct_points),
                        self._dump_json(evaluation.missing_points),
                        self._dump_json(evaluation.misconception_tags),
                        int(evaluation.critical_misconception),
                        evaluation.feedback.strip(),
                        evaluation.reference_answer.strip(),
                        self._dump_json(evaluation.evidence_source_ids),
                        evaluation.evaluator_confidence,
                        int(evaluation.evaluation_reliable),
                        now,
                    ),
                )

                # Diagnoses affect the Mastery Gate only when the entire scoring
                # result was reliable enough to update mastery.
                if mastery_updates_allowed:
                    for tag in evaluation.misconception_tags:
                        normalized_tag = tag.strip()
                        if not normalized_tag:
                            continue
                        connection.execute(
                            """
                            INSERT INTO misconception_events(
                                id, student_id, topic_id, attempt_id, tag,
                                critical, evidence, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                str(uuid.uuid4()),
                                student_id,
                                practice_set.topic_id,
                                attempt_id,
                                normalized_tag,
                                int(evaluation.critical_misconception),
                                evaluation.feedback.strip(),
                                now,
                            ),
                        )

            if mastery_updates_allowed:
                connection.execute(
                    """
                    INSERT INTO student_topic_states(
                        student_id, topic_id, updated_at
                    ) VALUES (?, ?, ?)
                    ON CONFLICT(student_id, topic_id) DO NOTHING
                    """,
                    (student_id, practice_set.topic_id, now),
                )
                if topic_changes:
                    persisted_topic_changes = dict(topic_changes)
                    persisted_topic_changes["updated_at"] = now
                    assignments = ", ".join(
                        f"{field} = ?" for field in persisted_topic_changes
                    )
                    connection.execute(
                        f"""
                        UPDATE student_topic_states SET {assignments}
                        WHERE student_id = ? AND topic_id = ?
                        """,
                        (
                            *persisted_topic_changes.values(),
                            student_id,
                            practice_set.topic_id,
                        ),
                    )
                for dimension, changes in dimension_changes.items():
                    connection.execute(
                        """
                        INSERT INTO student_dimension_states(
                            student_id, topic_id, dimension, updated_at
                        ) VALUES (?, ?, ?, ?)
                        ON CONFLICT(student_id, topic_id, dimension) DO NOTHING
                        """,
                        (student_id, practice_set.topic_id, dimension, now),
                    )
                    if changes:
                        persisted_dimension_changes = dict(changes)
                        persisted_dimension_changes["updated_at"] = now
                        assignments = ", ".join(
                            f"{field} = ?" for field in persisted_dimension_changes
                        )
                        connection.execute(
                            f"""
                            UPDATE student_dimension_states SET {assignments}
                            WHERE student_id = ? AND topic_id = ? AND dimension = ?
                            """,
                            (
                                *persisted_dimension_changes.values(),
                                student_id,
                                practice_set.topic_id,
                                dimension,
                            ),
                        )

            connection.execute(
                """
                UPDATE practice_submissions
                SET total_score = ?, evaluation_status = ?, mastery_before = ?,
                    mastery_after = ?, gate_result_json = ?, response_json = ?
                WHERE id = ? AND evaluation_status = 'processing'
                """,
                (
                    total_score,
                    evaluation_status,
                    mastery_before,
                    mastery_after if mastery_updates_allowed else mastery_before,
                    self._dump_json(gate_result),
                    response_json,
                    submission_id,
                ),
            )
            connection.execute(
                """
                UPDATE practice_sets
                SET status = ?, submitted_at = ?
                WHERE id = ?
                """,
                (
                    "submitted" if mark_submitted else "evaluation_uncertain",
                    now if mark_submitted else None,
                    practice_set.practice_set_id,
                ),
            )
            # Feedback exposes solutions even for uncertain evaluations. Preserve
            # this fact so retrying after reading it cannot add fresh evidence.
            connection.execute(
                "UPDATE practice_questions SET attempt_count=attempt_count+1 WHERE practice_set_id=?",
                (practice_set.practice_set_id,),
            )
            if practice_set.assessment_purpose != "legacy":
                connection.execute(
                    "INSERT INTO content_exposures(student_id,content_id,content_version,family_id,kind,assessment_id,created_at) SELECT ?,id,1,COALESCE(family_id,id),'feedback',practice_set_id,? FROM practice_questions WHERE practice_set_id=?",
                    (student_id,now,practice_set.practice_set_id),
                )

    def count_unresolved_critical_misconceptions(
        self,
        student_id: str,
        topic_id: str,
    ) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM misconception_events me
                JOIN practice_attempts pa ON pa.id = me.attempt_id
                WHERE me.student_id = ? AND me.topic_id = ?
                  AND me.critical = 1 AND me.resolved_at IS NULL
                  AND pa.evaluation_reliable = 1
                """,
                (student_id, topic_id),
            ).fetchone()
        return int(row["count"])

    def get_prerequisite_masteries(
        self,
        student_id: str,
        topic_id: str,
    ) -> dict[str, float]:
        result = {}
        for item in self.prerequisite_status(student_id, topic_id):
            if item["relation_type"] != "required" or item["scope"] != "topic":
                continue
            if not item["satisfied"]:
                result[item["id"]] = 0.0
            elif item["status"] == "mastered" and float(item["mastery"] or 0) >= item["required_mastery"]:
                result[item["id"]] = float(item["mastery"])
            else:
                result[item["id"]] = 1.0  # The adapter represents verified competence, not a Beta update.
        return result

    def get_latest_checkpoint_dimensions(
        self,
        student_id: str,
        topic_id: str,
    ) -> list[str]:
        with self._connect() as connection:
            latest = connection.execute(
                """
                SELECT s.id
                FROM practice_submissions s
                JOIN practice_sets ps ON ps.id = s.practice_set_id
                WHERE s.student_id = ? AND ps.topic_id = ?
                  AND ps.mode = 'checkpoint'
                  AND s.evaluation_status = 'evaluated'
                  AND (ps.purpose='legacy' OR NOT EXISTS (SELECT 1 FROM practice_questions pq WHERE pq.practice_set_id=ps.id AND (pq.evidence_eligible=0 OR pq.used_hint=1 OR pq.solution_revealed=1 OR pq.attempt_count>1)))
                ORDER BY s.created_at DESC, s.id DESC
                LIMIT 1
                """,
                (student_id, topic_id),
            ).fetchone()
            if latest is None:
                return []
            rows = connection.execute(
                """
                SELECT dimension_scores_json
                FROM practice_attempts
                WHERE submission_id = ? AND evaluation_reliable = 1
                """,
                (latest["id"],),
            ).fetchall()
        return sorted(
            {
                dimension
                for row in rows
                for dimension in self._load_json(row["dimension_scores_json"], {})
            }
        )

    def create_learning_session(
        self,
        *,
        student_id: str,
        course: Course | str,
        topic_id: str | None,
        state: str,
    ) -> str:
        self.require_student(student_id, touch=False)
        course_value = course.value if isinstance(course, Course) else Course(course).value
        if topic_id is not None:
            topic = self.require_topic(topic_id)
            if topic["course"] != course_value:
                raise CourseTopicMismatchError()
        normalized_state = str(state).strip()
        if not normalized_state:
            raise ValueError("learning session state 不能为空")
        session_id = str(uuid.uuid4())
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO learning_sessions(
                    id, student_id, course, topic_id, state, started_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    student_id,
                    course_value,
                    topic_id,
                    normalized_state,
                    now,
                    now,
                    now,
                ),
            )
        return session_id

    @staticmethod
    def _submission_history_record(row: dict[str, Any]) -> dict[str, Any]:
        score = float(row["total_score"])
        return {
            "event_type": "submission",
            "id": row["id"],
            "submission_id": row["id"],
            "practice_set_id": row["practice_set_id"],
            "topic_id": row["topic_id"],
            "topic_title": row["topic_title"],
            "mode": row["mode"],
            "score": score,
            "total_score": score,
            "status": row["evaluation_status"],
            "evaluation_status": row["evaluation_status"],
            "mastery_before": (
                float(row["mastery_before"])
                if row["mastery_before"] is not None
                else None
            ),
            "mastery_after": (
                float(row["mastery_after"])
                if row["mastery_after"] is not None
                else None
            ),
            "created_at": row["created_at"],
        }

    def list_recent_submissions(
        self,
        student_id: str,
        *,
        course: Course | str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        normalized_limit = max(0, int(limit))
        if normalized_limit == 0:
            return []
        query = """
            SELECT s.id, s.practice_set_id, s.total_score,
                   s.evaluation_status, s.mastery_before, s.mastery_after,
                   s.created_at, ps.topic_id, ps.mode, t.title AS topic_title
            FROM practice_submissions s
            JOIN practice_sets ps ON ps.id = s.practice_set_id
            JOIN curriculum_topics t ON t.id = ps.topic_id
            WHERE s.student_id = ? AND s.evaluation_status <> 'processing'
        """
        params: list[Any] = [student_id]
        if course is not None:
            course_value = course.value if isinstance(course, Course) else Course(course).value
            query += " AND ps.course = ?"
            params.append(course_value)
        query += " ORDER BY s.created_at DESC, s.id DESC LIMIT ?"
        params.append(normalized_limit)
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._submission_history_record(row) for row in rows]

    def list_learning_history(
        self,
        student_id: str,
        *,
        course: Course | str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Combine learning-session and finalized-submission events chronologically."""

        normalized_limit = max(0, int(limit))
        if normalized_limit == 0:
            return []
        course_value = course.value if isinstance(course, Course) else Course(course).value
        with self._connect() as connection:
            submission_rows = connection.execute(
                """
                SELECT s.id, s.practice_set_id, s.total_score,
                       s.evaluation_status, s.mastery_before, s.mastery_after,
                       s.created_at, ps.topic_id, ps.mode,
                       t.title AS topic_title
                FROM practice_submissions s
                JOIN practice_sets ps ON ps.id = s.practice_set_id
                JOIN curriculum_topics t ON t.id = ps.topic_id
                WHERE s.student_id = ? AND ps.course = ?
                  AND s.evaluation_status <> 'processing'
                ORDER BY s.created_at DESC, s.id DESC
                LIMIT ?
                """,
                (student_id, course_value, normalized_limit),
            ).fetchall()
            session_rows = connection.execute(
                """
                SELECT ls.id, ls.topic_id, ls.state, ls.created_at,
                       t.title AS topic_title
                FROM learning_sessions ls
                LEFT JOIN curriculum_topics t ON t.id = ls.topic_id
                WHERE ls.student_id = ? AND ls.course = ?
                ORDER BY ls.created_at DESC, ls.id DESC
                LIMIT ?
                """,
                (student_id, course_value, normalized_limit),
            ).fetchall()

        events = [self._submission_history_record(row) for row in submission_rows]
        events.extend(
            {
                "event_type": "session",
                "id": row["id"],
                "topic_id": row["topic_id"],
                "topic_title": row["topic_title"],
                "state": row["state"],
                "status": row["state"],
                "created_at": row["created_at"],
            }
            for row in session_rows
        )
        events.sort(key=lambda item: (str(item["created_at"]), str(item["id"])), reverse=True)
        return events[:normalized_limit]

    def get_attempt_context(
        self,
        attempt_id: str,
        *,
        student_id: str,
    ) -> dict[str, Any] | None:
        """Return immutable internal context for a student-owned remediation attempt."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT pa.*, s.practice_set_id, ps.topic_id, ps.course, ps.mode,
                       ps.source_snapshot_json,
                       ps.target_misconception_tags_json,
                       q.position, q.question_type, q.difficulty, q.question,
                       q.options_json, q.dimensions_json, q.answer_key_json,
                       q.rubric_json, q.source_ids_json
                FROM practice_attempts pa
                JOIN practice_submissions s ON s.id = pa.submission_id
                JOIN practice_sets ps ON ps.id = s.practice_set_id
                JOIN practice_questions q ON q.id = pa.question_id
                WHERE pa.id = ? AND pa.student_id = ?
                """,
                (attempt_id, student_id),
            ).fetchone()
        if row is None:
            return None

        question = PracticeQuestionInternal.model_validate(
            {
                "question_id": row["question_id"],
                "question_type": row["question_type"],
                "difficulty": row["difficulty"],
                "question": row["question"],
                "options": self._load_json(row["options_json"], None),
                "dimensions": self._load_json(row["dimensions_json"], {}),
                "answer_key": self._load_json(row["answer_key_json"], {}),
                "rubric": self._load_json(row["rubric_json"], []),
                "source_ids": self._load_json(row["source_ids_json"], []),
                "position": row["position"],
                "max_score": 100,
            }
        ).model_dump(mode="json")
        evaluation = {
            "score": float(row["score"]),
            "verdict": row["verdict"],
            "dimension_scores": self._load_json(row["dimension_scores_json"], {}),
            "correct_points": self._load_json(row["correct_points_json"], []),
            "missing_points": self._load_json(row["missing_points_json"], []),
            "misconception_tags": self._load_json(
                row["misconception_tags_json"], []
            ),
            "critical_misconception": bool(row["critical_misconception"]),
            "feedback": row["feedback"],
            "reference_answer": row["reference_answer"],
            "evidence_source_ids": self._load_json(
                row["evidence_source_ids_json"], []
            ),
            "evaluator_confidence": float(row["evaluator_confidence"]),
            "evaluation_reliable": bool(row["evaluation_reliable"]),
        }
        result = {
            "attempt_id": row["id"],
            "submission_id": row["submission_id"],
            "student_id": row["student_id"],
            "practice_set_id": row["practice_set_id"],
            "topic_id": row["topic_id"],
            "course": row["course"],
            "mode": row["mode"],
            "question_id": row["question_id"],
            "question": question,
            "question_text": question["question"],
            "student_answer": row["answer_text"],
            "answer_text": row["answer_text"],
            "evaluation": evaluation,
            "source_snapshot": self._load_json(row["source_snapshot_json"], []),
            "target_misconception_tags": self._load_json(
                row["target_misconception_tags_json"], []
            ),
            "created_at": row["created_at"],
        }
        # Flat aliases keep internal callers simple while the structured values
        # remain the canonical remediation contract.
        result.update(evaluation)
        return result
