"""Re-export configuration-driven layer relevance."""

from app.config.layer_config import layers_for_topics, TOPIC_LAYER_RELEVANCE, LAYER_NAMES

__all__ = ["layers_for_topics", "TOPIC_LAYER_RELEVANCE", "LAYER_NAMES"]
