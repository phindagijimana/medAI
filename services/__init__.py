"""
Med42 Services Module
Provides modular services for the Med42 medical AI platform.

Legacy Flask-served submodules (``med42_model``, ``file_processor``,
``prompt_engine``) require werkzeug / flask; they are re-exported only if
their dependencies are installed so that the MedCAT+medspaCy pipeline can
be imported from a lightweight ``venv-medcat`` environment that does not
ship the Flask stack.
"""

__all__: list[str] = []

try:  # pragma: no cover - environment-dependent
    from .med42_model import Med42ModelService  # noqa: F401
    __all__.append("Med42ModelService")
except Exception:
    pass

try:  # pragma: no cover
    from .file_processor import FileProcessor, generate_tabular_output  # noqa: F401
    __all__ += ["FileProcessor", "generate_tabular_output"]
except Exception:
    pass

try:  # pragma: no cover
    from .prompt_engine import Med42PromptEngine  # noqa: F401
    __all__.append("Med42PromptEngine")
except Exception:
    pass



