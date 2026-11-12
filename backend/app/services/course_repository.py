from datetime import datetime, timezone

from psycopg.errors import UniqueViolation

from app.core.exceptions import CourseNotFoundError, CourseConflictError
from app.db.database import PostgresDatabase


COURSE_SELECT = """SELECT c.*,
    (SELECT count(*) FROM curriculum_topics t WHERE t.course=c.id AND t.active=1) AS topic_count,
    (SELECT count(DISTINCT t.stage) FROM curriculum_topics t WHERE t.course=c.id AND t.active=1) AS stage_count
    FROM courses c"""


class CourseRepository:
    def __init__(self, database_url: str):
        self.database = PostgresDatabase(database_url)

    def list(self, *, query="", status="all", page=1, page_size=20, public=False):
        where = "c.deleted_at IS NULL"
        parameters = []
        if public or status != "all":
            where += " AND c.active=?"
            parameters.append(1 if public or status == "active" else 0)
        if query.strip():
            where += " AND (c.id ILIKE ? OR c.title ILIKE ?)"
            parameters.extend([f"%{query.strip()}%"] * 2)
        with self.database.connect() as connection:
            total = connection.execute(f"SELECT count(*) AS count FROM courses c WHERE {where}", tuple(parameters)).fetchone()["count"]
            query_sql = COURSE_SELECT + f" WHERE {where} ORDER BY c.sort_order,c.created_at,c.id"
            if not public:
                query_sql += " LIMIT ? OFFSET ?"
                parameters.extend([page_size, (page - 1) * page_size])
            items = [dict(row) for row in connection.execute(query_sql, tuple(parameters))]
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def get(self, course_id, *, detail=False):
        with self.database.connect() as connection:
            row = connection.execute(COURSE_SELECT + " WHERE c.id=? AND c.deleted_at IS NULL", (str(course_id),)).fetchone()
            if row is None:
                raise CourseNotFoundError()
            result = dict(row)
            if detail:
                result["topics"] = [dict(topic) for topic in connection.execute(
                    "SELECT id,title,stage,stage_title,active FROM curriculum_topics WHERE course=? ORDER BY stage,order_index",
                    (str(course_id),),
                )]
        return result

    def create(self, values):
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self.database.connect() as connection:
                connection.execute("""INSERT INTO courses(id,title,description,active,sort_order,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?)""", (str(values["id"]), values["title"], values["description"],
                    int(values["active"]), values["sort_order"], now, now))
        except UniqueViolation:
            raise CourseConflictError() from None
        return self.get(values["id"])

    def update(self, course_id, values):
        # Column names come only from the validated request's fixed allowlist.
        allowed = {"title", "description", "active", "sort_order"}
        if not values or not set(values) <= allowed:
            raise ValueError("Invalid course update fields")
        values = {**values, "updated_at": datetime.now(timezone.utc).isoformat()}
        if "active" in values:
            values["active"] = int(values["active"])
        assignments = ", ".join(f"{name}=?" for name in values)
        with self.database.connect() as connection:
            row = connection.execute(f"UPDATE courses SET {assignments} WHERE id=? AND deleted_at IS NULL RETURNING id",
                                     (*values.values(), str(course_id))).fetchone()
            if row is None:
                raise CourseNotFoundError()
        return self.get(course_id)

    def delete(self, course_id):
        now = datetime.now(timezone.utc).isoformat()
        with self.database.connect() as connection:
            row = connection.execute("""UPDATE courses SET active=0,deleted_at=?,updated_at=?
                WHERE id=? AND deleted_at IS NULL RETURNING id""", (now, now, str(course_id))).fetchone()
            if row is None:
                raise CourseNotFoundError()
