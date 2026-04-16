"""Message bus module for decoupled transport-agent communication."""

from athena_agent.bus.events import InboundMessage, OutboundMessage
from athena_agent.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
