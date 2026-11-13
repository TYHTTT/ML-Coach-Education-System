from app.db.database import PostgresDatabase


class KnowledgeGraph:
    def __init__(self, database_url: str):
        self.database = PostgresDatabase(database_url)

    def read(self, *, admin: bool = False) -> dict:
        # Read all three collections from one snapshot while administrators edit.
        visible_course = "c.deleted_at IS NULL" + ("" if admin else " AND c.active=1")
        with self.database.connect() as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            courses = [dict(row) for row in connection.execute(
                f"SELECT c.id,c.title,c.active,c.sort_order FROM courses c WHERE {visible_course} ORDER BY c.sort_order,c.id"
            ).fetchall()]
            for course in courses:
                course["active"] = bool(course["active"])
            nodes = [dict(row) for row in connection.execute(f"""
                SELECT t.id,t.course,t.title,t.description,t.stage,t.stage_title,t.order_index
                FROM curriculum_topics t JOIN courses c ON c.id=t.course
                WHERE t.active=1 AND {visible_course}
                ORDER BY c.sort_order,c.id,t.stage,t.order_index,t.id
            """).fetchall()]
            ids = [node["id"] for node in nodes]
            edges = [dict(row) for row in connection.execute("""
                SELECT topic_a_id AS source,topic_b_id AS target,relation_type AS type
                FROM topic_relations WHERE topic_a_id=ANY(?) AND topic_b_id=ANY(?)
                ORDER BY topic_a_id,topic_b_id
            """, (ids, ids)).fetchall()] if ids else []
        return {"courses": courses, "nodes": nodes, "edges": edges}
