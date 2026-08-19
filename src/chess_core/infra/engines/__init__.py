"""Engine package."""

from chess_core.infra.engines.discovery import EngineDescriptor, EngineDiscovery
from chess_core.infra.engines.process import EngineProcess, hidden_popen_kwargs
from chess_core.infra.engines.uci import UciClient, UciInfo

__all__ = [
    "EngineDescriptor",
    "EngineDiscovery",
    "EngineProcess",
    "UciClient",
    "UciInfo",
    "hidden_popen_kwargs",
]
