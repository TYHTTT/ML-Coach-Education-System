"""Canonical prerequisite evidence stays scoped after the Dify migration."""
import pytest
from app.core.types import Course
from app.services.dify import resource_snapshots


@pytest.mark.parametrize("metadata", [{}, {"course":"linear_algebra"}, {"course":"machine_learning","topic_id":"la.dot_product"}, {"course":"linear_algebra","topic_id":"la.vectors"}])
def test_prerequisite_sources_reject_missing_or_foreign_metadata(metadata):
    resources=[{"content":"内积原文","doc_metadata":metadata}]
    assert resource_snapshots(resources,course=Course.LINEAR_ALGEBRA,topic_ids=["la.dot_product"]) == []


def test_prerequisite_sources_use_only_canonical_dify_evidence():
    good={"content":"向量内积逐项相乘求和","document_id":"remote-doc","doc_metadata":{"course":"linear_algebra","topic_id":"la.dot_product"}}
    sources=resource_snapshots([good,good],course=Course.LINEAR_ALGEBRA,topic_ids=["la.dot_product"])
    assert len(sources) == 1
    assert sources[0]["document_id"] == "remote-doc"
    assert sources[0]["topic_id"] == "la.dot_product"
