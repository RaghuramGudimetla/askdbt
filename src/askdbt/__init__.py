"""askdbt — AI-powered data dictionary for your dbt project."""

from .config import Config
from .indexer import Indexer
from .parser import ManifestParser, ModelChunk
from .retriever import Answer, Retriever

__version__ = "0.1.0"
__all__ = ["AskDBT", "Config", "ManifestParser", "ModelChunk", "Indexer", "Retriever", "Answer"]


class AskDBT:
    """High-level facade for programmatic use."""

    def __init__(
        self,
        manifest_path: str,
        catalog_path: str | None = None,
        config: Config | None = None,
    ):
        self.config = config or Config()
        self._parser = ManifestParser(manifest_path, catalog_path)
        self._indexer = Indexer(self.config)
        self._retriever = Retriever(self.config)
        self._indexed = False

    def index(self, show_progress: bool = True) -> int:
        chunks = self._parser.parse()
        n = self._indexer.index(chunks, show_progress=show_progress)
        self._indexed = True
        return n

    def ask(self, question: str) -> str:
        if not self._indexed:
            raise RuntimeError("Call .index() before .ask()")
        return self._retriever.ask(question).answer

    def ask_full(self, question: str) -> Answer:
        if not self._indexed:
            raise RuntimeError("Call .index() before .ask_full()")
        return self._retriever.ask(question)
