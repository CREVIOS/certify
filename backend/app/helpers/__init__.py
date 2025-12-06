"""
Helper modules for advanced retrieval.

RSE (Relevance Segment Extraction):
Advanced retrieval algorithm that finds optimal document segments
instead of just individual chunks for better context and accuracy.
"""

from .rse import (
    get_best_segments,
    get_meta_document,
    get_chunk_value,
    get_relevance_values,
    adjust_relevance_values_for_chunk_length,
    RSE_PARAMS_PRESETS,
)

__all__ = [
    "get_best_segments",
    "get_meta_document",
    "get_chunk_value",
    "get_relevance_values",
    "adjust_relevance_values_for_chunk_length",
    "RSE_PARAMS_PRESETS",
]
