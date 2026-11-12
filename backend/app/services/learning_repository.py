from __future__ import annotations

import json
import secrets
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg

from app.core.exceptions import (
    CourseTopicMismatchError,
    CourseNotFoundError,
    StudentNotFoundError,
    TopicNotFoundError,
)
from app.core.security import hash_password, hash_session_token, verify_password
from app.core.types import Course
from app.curriculum.models import CurriculumSeed
from app.curriculum.validation import CrossCourseDependencyError
from app.db.database import PostgresConnection, PostgresDatabase


class LearningRepository:
    """Persistence for accounts, curriculum, study state and read-only historical results."""

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

    def __init__(self, database_url: str | PostgresDatabase) -> None:
        self.database = (
            database_url
            if isinstance(database_url, PostgresDatabase)
            else PostgresDatabase(database_url)
        )

    def _connect(self) -> PostgresConnection:
        """Return a connection to the configured PostgreSQL database."""

        return self.database.connect()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _row(row: dict[str, Any] | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

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
                (student_id, normalized_username, display_name.strip(), hash_password(password), now, now),
            )
        return self._issue_session(student_id)

    def authenticate_student(self, *, username: str, password: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            student = connection.execute(
                "SELECT id, username, display_name, password_hash, created_at FROM students WHERE username = ? AND active = 1",
                (username.strip().lower(),),
            ).fetchone()
        if student is None or not verify_password(password, student["password_hash"] or ""):
            return None
        return self._issue_session(student["id"])

    def _issue_session(self, student_id: str) -> dict[str, Any]:
        token, session_id, now = secrets.token_urlsafe(32), str(uuid.uuid4()), self._now()
        expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO student_sessions(id, student_id, token_hash, expires_at, created_at, last_used_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, student_id, hash_session_token(token), expires_at, now, now),
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
                (hash_session_token(token), now),
            ).fetchone()
            if student is None:
                raise StudentNotFoundError()
            if touch:
                connection.execute("UPDATE student_sessions SET last_used_at = ? WHERE token_hash = ?", (now, hash_session_token(token)))
                connection.execute("UPDATE students SET last_active_at = ? WHERE id = ?", (now, student["id"]))
        return dict(student)

    def revoke_session(self, token: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM student_sessions WHERE token_hash = ?", (hash_session_token(token),))

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

    def require_course(self, course: Course | str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM courses WHERE id=? AND active=1 AND deleted_at IS NULL", (course.value if isinstance(course, Course) else course,)
            ).fetchone()
        if row is None:
            raise CourseNotFoundError()
        return dict(row)

    def list_topics(
        self,
        course: Course | str,
        *,
        active_only: bool = True,
        student_id: str | None = None,
    ) -> list[dict[str, Any]]:
        course_value = course.value if isinstance(course, Course) else Course(course).value
        self.require_course(course_value)
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
                JOIN courses owner_course ON owner_course.id=t.course AND owner_course.active=1 AND owner_course.deleted_at IS NULL
                {join}
                WHERE t.id = ? AND t.active = 1
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
