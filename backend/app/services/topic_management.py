import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from psycopg.errors import UniqueViolation

from app.core.exceptions import CourseNotFoundError, TopicNotFoundError
from app.db.database import PostgresDatabase


def fail(message, status=409):
    raise HTTPException(status_code=status, detail=message)


class TopicManagement:
    def __init__(self, database_url):
        self.database = PostgresDatabase(database_url)

    @staticmethod
    def _now(): return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _course(connection, course, *, lock=False):
        row = connection.execute("SELECT * FROM courses WHERE id=? AND deleted_at IS NULL" + (" FOR UPDATE" if lock else ""), (str(course),)).fetchone()
        if row is None: raise CourseNotFoundError()
        return dict(row)

    @staticmethod
    def _owned(connection, course, topic_id):
        row = connection.execute("SELECT * FROM curriculum_topics WHERE id=?", (topic_id,)).fetchone()
        if row is None: raise TopicNotFoundError()
        if row["course"] != str(course): fail("只能在知识点所属课程编辑其内容。", 403)
        return dict(row)

    @staticmethod
    def _stage(connection, course, stage, title):
        row = connection.execute("SELECT group_title FROM topic_placements WHERE course_id=? AND parent_group_id=? LIMIT 1", (str(course), f"stage-{stage}")).fetchone()
        if row and row["group_title"] != title:
            fail("目标章节已存在，请使用现有名称，或通过“重命名章节”修改。")

    @staticmethod
    def _place(connection, course, topic_id, stage, title, reference):
        group = f"stage-{stage}"
        existing = connection.execute("SELECT parent_group_id,order_index FROM topic_placements WHERE course_id=? AND topic_id=?", (str(course), topic_id)).fetchone()
        if existing and existing["parent_group_id"] == group:
            return existing["order_index"]
        position = connection.execute("SELECT coalesce(max(order_index),0)+1 AS position FROM topic_placements WHERE course_id=? AND parent_group_id=?", (str(course), group)).fetchone()["position"]
        connection.execute("""INSERT INTO topic_placements(course_id,topic_id,parent_group_id,group_title,order_index,is_reference)
            VALUES (?,?,?,?,?,?) ON CONFLICT(course_id,topic_id) DO UPDATE SET parent_group_id=excluded.parent_group_id,
            group_title=excluded.group_title,order_index=excluded.order_index,is_reference=excluded.is_reference""",
            (str(course), topic_id, group, title, position, int(reference)))
        return position


    @staticmethod
    def _removable(connection, topic_id):
        reference = connection.execute("""SELECT c.title FROM topic_placements p JOIN courses c ON c.id=p.course_id
            WHERE p.topic_id=? AND p.is_reference=1 AND c.deleted_at IS NULL LIMIT 1""", (topic_id,)).fetchone()
        if reference: fail(f"“{reference['title']}”仍引用此知识点，请先移除该课程中的引用。")

    def outline(self, course):
        with self.database.connect() as connection:
            record = self._course(connection, course)
            rows = connection.execute("""SELECT t.*,p.parent_group_id,p.group_title,p.order_index AS placement_order,p.is_reference,
                c.title AS owner_title,c.active AS owner_active,c.deleted_at AS owner_deleted
                FROM topic_placements p JOIN curriculum_topics t ON t.id=p.topic_id JOIN courses c ON c.id=t.course
                WHERE p.course_id=? ORDER BY p.order_index,t.id""", (str(course),)).fetchall()
        groups, removed = {}, []
        for raw in rows:
            item = dict(raw)
            for key in ("learning_objectives", "aliases", "retrieval_keywords", "required_dimensions"):
                item[key] = json.loads(item.pop(key + "_json"))
            item.update(active=bool(item["active"]),
                        is_reference=bool(item["is_reference"]), available=bool(item["active"] and item["owner_active"] and not item["owner_deleted"]))
            group_id = item["parent_group_id"]
            match = re.fullmatch(r"stage-(\d+)", group_id)
            stage = int(match[1]) if match else None
            group_title = item["group_title"]
            group = groups.setdefault(group_id, {"id": group_id, "title": group_title, "stage": stage, "topics": []})
            if not item["active"] and not item["is_reference"]:
                removed.append(item); continue
            group["topics"].append(item)
        ordered = sorted(groups.values(), key=lambda group: (group["stage"] is not None, group["stage"] or 0, group["id"]))
        return {"course": {"id": record["id"], "title": record["title"], "active": bool(record["active"])}, "groups": ordered, "removed_topics": removed}

    def catalog(self, query=""):
        with self.database.connect() as connection:
            return [dict(row) for row in connection.execute("""SELECT t.id,t.title,t.course,c.title AS course_title
                FROM curriculum_topics t JOIN courses c ON c.id=t.course WHERE t.active=1 AND c.deleted_at IS NULL
                AND (t.title ILIKE ? OR t.id ILIKE ?) ORDER BY c.sort_order,t.stage,t.order_index LIMIT 1000""", (f"%{query}%", f"%{query}%"))]

    def save(self, course, values, topic_id=None):
        with self.database.connect() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(725498103)")
            self._course(connection, course, lock=True)
            if topic_id: self._owned(connection, course, topic_id)
            else: topic_id = f"{course}.t_{uuid4().hex[:12]}"
            self._stage(connection, course, values["stage"], values["stage_title"])
            existing = connection.execute("SELECT id FROM curriculum_topics WHERE id=?", (topic_id,)).fetchone()
            now = self._now()
            if not existing:
                position = connection.execute("SELECT coalesce(max(order_index),0)+1 AS position FROM curriculum_topics WHERE course=?", (str(course),)).fetchone()["position"]
                connection.execute("""INSERT INTO curriculum_topics(id,course,slug,title,stage,stage_title,order_index,description,
                    learning_objectives_json,aliases_json,retrieval_keywords_json,difficulty,required_dimensions_json,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (topic_id, str(course), topic_id.split('.',1)[1], values["title"], values["stage"],
                    values["stage_title"], position, values["description"], json.dumps(values["learning_objectives"]), json.dumps(values["aliases"]),
                    json.dumps(values["retrieval_keywords"] or [values["title"]]), values["difficulty"], '["concept"]', now, now))
            else:
                connection.execute("""UPDATE curriculum_topics SET title=?,stage=?,stage_title=?,description=?,learning_objectives_json=?,
                    aliases_json=?,retrieval_keywords_json=?,difficulty=?,updated_at=? WHERE id=?""", (values["title"], values["stage"], values["stage_title"],
                    values["description"], json.dumps(values["learning_objectives"]), json.dumps(values["aliases"]),
                    json.dumps(values["retrieval_keywords"] or [values["title"]]), values["difficulty"], now, topic_id))
            position = self._place(connection, course, topic_id, values["stage"], values["stage_title"], False)
            connection.execute("UPDATE curriculum_topics SET order_index=? WHERE id=?", (position, topic_id))
            connection.execute("UPDATE courses SET updated_at=? WHERE id=?", (now, str(course)))
        return self.outline(course)

    def reference(self, course, values, *, move=False):
        try:
            with self.database.connect() as connection:
                connection.execute("SELECT pg_advisory_xact_lock(725498103)")
                self._course(connection, course, lock=True)
                topic = connection.execute("""SELECT t.* FROM curriculum_topics t JOIN courses c ON c.id=t.course
                    WHERE t.id=? AND t.active=1 AND c.deleted_at IS NULL""", (values["topic_id"],)).fetchone()
                if not topic: raise TopicNotFoundError()
                if topic["course"] == str(course): fail("本课程知识点无需重复引用。")
                prior = connection.execute("SELECT is_reference FROM topic_placements WHERE course_id=? AND topic_id=?", (str(course), values["topic_id"])).fetchone()
                if bool(prior) != move: fail("引用已存在或已被移除，请刷新后重试。")
                self._stage(connection, course, values["stage"], values["stage_title"])
                self._place(connection, course, values["topic_id"], values["stage"], values["stage_title"], True)
        except UniqueViolation: fail("该知识点已在课程目录中。")
        return self.outline(course)

    def remove(self, course, topic_id, *, reference=False, restore=False):
        with self.database.connect() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(725498103)")
            self._course(connection, course, lock=True)
            if reference:
                result = connection.execute("DELETE FROM topic_placements WHERE course_id=? AND topic_id=? AND is_reference=1 RETURNING topic_id", (str(course), topic_id)).fetchone()
                if not result: raise TopicNotFoundError()
            else:
                self._owned(connection, course, topic_id)
                if not restore: self._removable(connection, topic_id)
                connection.execute("UPDATE curriculum_topics SET active=?,updated_at=? WHERE id=?", (int(restore), self._now(), topic_id))
        return self.outline(course)

    def reorder(self, course, group_id, ids):
        with self.database.connect() as connection:
            self._course(connection, course, lock=True)
            rows = connection.execute("""SELECT p.topic_id,p.is_reference,t.course FROM topic_placements p JOIN curriculum_topics t ON t.id=p.topic_id
                WHERE p.course_id=? AND p.parent_group_id=? AND (t.active=1 OR p.is_reference=1)""", (str(course), group_id)).fetchall()
            if set(ids) != {row["topic_id"] for row in rows}: fail("目录已变化，请刷新后重新排序。")
            for position, topic_id in enumerate(ids, 1):
                connection.execute("UPDATE topic_placements SET order_index=? WHERE course_id=? AND topic_id=?", (position, str(course), topic_id))
                if next(row for row in rows if row["topic_id"] == topic_id)["course"] == str(course):
                    connection.execute("UPDATE curriculum_topics SET order_index=?,updated_at=? WHERE id=?", (position, self._now(), topic_id))
        return self.outline(course)

    def rename_stage(self, course, stage, title):
        with self.database.connect() as connection:
            self._course(connection, course, lock=True)
            result = connection.execute("UPDATE topic_placements SET group_title=? WHERE course_id=? AND parent_group_id=? RETURNING topic_id", (title, str(course), f"stage-{stage}")).fetchone()
            if not result: fail("章节不存在，请刷新后重试。", 404)
            connection.execute("UPDATE curriculum_topics SET stage_title=?,updated_at=? WHERE course=? AND stage=?", (title, self._now(), str(course), stage))
        return self.outline(course)

    def reorder_stages(self, course, ids):
        with self.database.connect() as connection:
            self._course(connection, course, lock=True)
            groups = connection.execute("SELECT DISTINCT parent_group_id FROM topic_placements WHERE course_id=? AND parent_group_id ~ '^stage-[0-9]+$'", (str(course),)).fetchall()
            if set(ids) != {group["parent_group_id"] for group in groups}:
                fail("章节已变化，请刷新后重新排序。")
            temporary = "reorder-" + uuid4().hex
            for position, group_id in enumerate(ids, 1):
                old_stage = int(group_id.split('-')[1])
                connection.execute("UPDATE topic_placements SET parent_group_id=? WHERE course_id=? AND parent_group_id=?", (f"{temporary}-{position}", str(course), group_id))
                connection.execute("UPDATE curriculum_topics SET stage=? WHERE course=? AND stage=?", (10000 + position, str(course), old_stage))
            for position in range(1, len(ids) + 1):
                connection.execute("UPDATE topic_placements SET parent_group_id=? WHERE course_id=? AND parent_group_id=?", (f"stage-{position}", str(course), f"{temporary}-{position}"))
                connection.execute("UPDATE curriculum_topics SET stage=?,updated_at=? WHERE course=? AND stage=?", (position, self._now(), str(course), 10000 + position))
        return self.outline(course)
