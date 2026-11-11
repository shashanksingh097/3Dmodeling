from . import handlers  # noqa: F401  (registers the commands)
from .processor import REGISTRY, CommandError, Entry, Processor, Result

__all__ = ["Processor", "Result", "Entry", "CommandError", "REGISTRY"]
