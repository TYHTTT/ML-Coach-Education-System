import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

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
    def _place(connection, course, topic_id, stage, title):
        group = f"stage-{stage}"
        existing = connection.execute("SELECT parent_group_id,order_index FROM topic_placements WHERE course_id=? AND topic_id=?", (str(course), topic_id)).fetchone()
        if existing and existing["parent_group_id"] == group:
            return existing["order_index"]
        position = connection.execute("SELECT coalesce(max(order_index),0)+1 AS position FROM topic_placements WHERE course_id=? AND parent_group_id=?", (str(course), group)).fetchone()["position"]
        connection.execute("""INSERT INTO topic_placements(course_id,topic_id,parent_group_id,group_title,order_index)
            VALUES (?,?,?,?,?) ON CONFLICT(course_id,topic_id) DO UPDATE SET parent_group_id=excluded.parent_group_id,
            group_title=excluded.group_title,order_index=excluded.order_index""",
            (str(course), topic_id, group, title, position))
        return position

    @staticmethod
    def _related(connection, topic_ids):
        result = {topic_id: [] for topic_id in topic_ids}
        if not topic_ids:
            return result
        rows = connection.execute("""SELECT e.topic_a_id,e.topic_b_id,t.id,t.title,t.course,c.title AS course_title,
            t.active,c.active AS course_active,c.deleted_at
            FROM topic_relations e
            CROSS JOIN LATERAL (VALUES (e.topic_a_id,e.topic_b_id),(e.topic_b_id,e.topic_a_id)) AS pair(topic_id,related_id)
            JOIN curriculum_topics t ON t.id=pair.related_id JOIN courses c ON c.id=t.course
            WHERE e.relation_type='related' AND pair.topic_id=ANY(?) ORDER BY t.title,t.id""", (topic_ids,)).fetchall()
        for row in rows:
            source = row["topic_b_id"] if row["id"] == row["topic_a_id"] else row["topic_a_id"]
            result[source].append({"id": row["id"], "title": row["title"], "course": row["course"],
                                   "course_title": row["course_title"], "course_active": bool(row["course_active"]),
                                   "available": bool(row["active"] and row["deleted_at"] is None)})
        return result

    @staticmethod
    def _save_related(connection, topic_id, ids):
        if topic_id in ids:
            fail("不能将知识点自身设为相关知识点。", 422)
        old = {item["id"] for item in TopicManagement._related(connection, [topic_id])[topic_id]}
        added = list(set(ids) - old)
        if added:
            valid = connection.execute("""SELECT t.id FROM curriculum_topics t JOIN courses c ON c.id=t.course
                WHERE t.id=ANY(?) AND t.active=1 AND c.deleted_at IS NULL""", (added,)).fetchall()
            if len(valid) != len(added):
                fail("部分相关知识点不存在或已移除，请刷新后重试。", 422)
        connection.execute("""DELETE FROM topic_relations WHERE relation_type='related'
            AND ((topic_a_id=? AND NOT(topic_b_id=ANY(?))) OR (topic_b_id=? AND NOT(topic_a_id=ANY(?))))""",
            (topic_id, ids, topic_id, ids))
        for target in ids:
            connection.execute("""INSERT INTO topic_relations(topic_a_id,topic_b_id)
                VALUES (LEAST(?::text,?::text),GREATEST(?::text,?::text)) ON CONFLICT DO NOTHING""",
                (topic_id, target, topic_id, target))

    def related_candidates(self, query="", course=None, exclude=None, page=1, page_size=30):
        with self.database.connect() as connection:
            courses = [dict(row) for row in connection.execute("SELECT id,title,active FROM courses WHERE deleted_at IS NULL ORDER BY sort_order,id")]
            where = "t.active=1 AND c.deleted_at IS NULL AND (t.title ILIKE ? OR t.id ILIKE ? OR c.title ILIKE ?)"
            params = [f"%{query}%"] * 3
            if course is not None:
                where += " AND t.course=?"; params.append(str(course))
            if exclude is not None:
                where += " AND t.id<>?"; params.append(exclude)
            total = connection.execute("SELECT count(*) AS n FROM curriculum_topics t JOIN courses c ON c.id=t.course WHERE " + where, params).fetchone()["n"]
            rows = connection.execute("""SELECT t.id,t.title,t.course,c.title AS course_title,c.active AS course_active
                FROM curriculum_topics t JOIN courses c ON c.id=t.course WHERE """ + where +
                " ORDER BY c.sort_order,c.id,t.stage,t.order_index,t.id LIMIT ? OFFSET ?", (*params, page_size, (page - 1) * page_size)).fetchall()
        return {"items": [{**dict(row), "course_active": bool(row["course_active"]), "available": True} for row in rows],
                "courses": [{**course, "active": bool(course["active"])} for course in courses],
                "total": total, "page": page, "page_size": page_size}



    def outline(self, course):
        with self.database.connect() as connection:
            record = self._course(connection, course)
            rows = connection.execute("""SELECT t.*,p.parent_group_id,p.group_title,p.order_index AS placement_order
                FROM topic_placements p JOIN curriculum_topics t ON t.id=p.topic_id AND t.course=p.course_id
                WHERE p.course_id=? ORDER BY p.order_index,t.id""", (str(course),)).fetchall()
            related = self._related(connection, [row["id"] for row in rows])
        groups, removed = {}, []
        for raw in rows:
            item = dict(raw)
            for key in ("learning_objectives", "aliases", "retrieval_keywords", "required_dimensions"):
                item[key] = json.loads(item.pop(key + "_json"))
            item["active"] = bool(item["active"])
            item["related_topics"] = related[item["id"]]
            item["related_topic_ids"] = [topic["id"] for topic in item["related_topics"]]
            group_id = item["parent_group_id"]
            match = re.fullmatch(r"stage-(\d+)", group_id)
            stage = int(match[1]) if match else None
            group_title = item["group_title"]
            group = groups.setdefault(group_id, {"id": group_id, "title": group_title, "stage": stage, "topics": []})
            if not item["active"]:
                removed.append(item); continue
            group["topics"].append(item)
        ordered = sorted(groups.values(), key=lambda group: (group["stage"] is not None, group["stage"] or 0, group["id"]))
        return {"course": {"id": record["id"], "title": record["title"], "active": bool(record["active"])}, "groups": ordered, "removed_topics": removed}


    def save(self, course, values, topic_id=None):
        with self.database.connect() as connection:
            if values.get("related_topic_ids") is not None:
                connection.execute("SELECT pg_advisory_xact_lock(725498104)")
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
            position = self._place(connection, course, topic_id, values["stage"], values["stage_title"])
            connection.execute("UPDATE curriculum_topics SET order_index=? WHERE id=?", (position, topic_id))
            if values.get("related_topic_ids") is not None:
                self._save_related(connection, topic_id, values["related_topic_ids"])
            connection.execute("UPDATE courses SET updated_at=? WHERE id=?", (now, str(course)))
        return self.outline(course)


    def remove(self, course, topic_id, *, restore=False):
        with self.database.connect() as connection:
            self._course(connection, course, lock=True)
            self._owned(connection, course, topic_id)
            connection.execute("UPDATE curriculum_topics SET active=?,updated_at=? WHERE id=?", (int(restore), self._now(), topic_id))
        return self.outline(course)

    def reorder(self, course, group_id, ids):
        with self.database.connect() as connection:
            self._course(connection, course, lock=True)
            rows = connection.execute("""SELECT p.topic_id FROM topic_placements p JOIN curriculum_topics t ON t.id=p.topic_id
                WHERE p.course_id=? AND p.parent_group_id=? AND t.active=1 AND t.course=p.course_id""", (str(course), group_id)).fetchall()
            if set(ids) != {row["topic_id"] for row in rows}: fail("目录已变化，请刷新后重新排序。")
            for position, topic_id in enumerate(ids, 1):
                connection.execute("UPDATE topic_placements SET order_index=? WHERE course_id=? AND topic_id=?", (position, str(course), topic_id))
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
