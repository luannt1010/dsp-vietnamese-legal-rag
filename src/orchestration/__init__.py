"""Compose RAG components and run the bounded retrieval feedback loop."""

from src.orchestration.pipeline_factory import create_pipeline
from src.orchestration.rag_pipeline import RAGPipeline

__all__ = ["RAGPipeline", "create_pipeline"]
