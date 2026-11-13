from fastapi import APIRouter, Depends, Request

from app.api.admins import require_admin
from app.api.dependencies import require_student_from_header
from app.services.knowledge_graph import KnowledgeGraph

router = APIRouter(tags=["knowledge-graph"])


def service(request: Request):
    return KnowledgeGraph(request.app.state.settings.database_url)


@router.get("/api/v1/knowledge-graph", dependencies=[Depends(require_student_from_header)])
def student_graph(graph=Depends(service)):
    return graph.read()


@router.get("/api/v1/admin/knowledge-graph", dependencies=[Depends(require_admin)])
def admin_graph(graph=Depends(service)):
    return graph.read(admin=True)
