"""Pick the speech synthesiser (design §8.6, docs/meeting-mode-v0.1.md §9).

One factory rather than a ``build_*`` in each provider module: synthesis has three implementations
and the choice between them is a deployment decision, not a property of any single one. The
providers are imported inside their branches so that a broken optional dependency (piper-tts,
edge-tts) cannot break importing the app itself.
"""

from __future__ import annotations

from app.ai.speech_synthesis import SpeechSynthesisProvider
from app.core.config import Settings


def build_synthesis_provider(settings: Settings) -> SpeechSynthesisProvider:
    """Build the synthesiser from settings, failing closed on an unknown configuration."""
    if settings.speech_synthesis_provider == "mock":
        from app.ai.speech_synthesis import FakeSpeechSynthesisProvider

        return FakeSpeechSynthesisProvider()

    if settings.speech_synthesis_provider == "piper":
        from app.ai.piper_synthesis import build_piper_provider

        return build_piper_provider(settings)

    if settings.speech_synthesis_provider == "edge_tts":
        from app.ai.edge_tts_synthesis import build_edge_tts_provider

        return build_edge_tts_provider(settings)

    raise RuntimeError(
        f"Unsupported SPEECH_SYNTHESIS_PROVIDER {settings.speech_synthesis_provider!r}: "
        "use 'mock', 'piper' or 'edge_tts'."
    )
