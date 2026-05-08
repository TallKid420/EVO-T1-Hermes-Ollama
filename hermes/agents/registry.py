"""
hermes/agents/registry.py

This module defines the AGENT_REGISTRY, which maps agent type strings to their corresponding classes. 
This allows for dynamic instantiation of agents based on configuration or runtime parameters.
This also prevents circular imports.
"""

from hermes.agents.types.chat_agent import ChatAgent
from hermes.agents.types.research_agent import ResearcherAgent
from hermes.agents.types.engineer_agent import EngineerAgent
from hermes.agents.system.server_agent import ServerAgent
# from agents.types.monitor_agent import MonitorAgent
# from agents.types.scheduler_agent import SchedulerAgent

AGENT_REGISTRY = {
    "chat":       ChatAgent,
    "researcher": ResearcherAgent,
    "engineer":   EngineerAgent,
    "server":     ServerAgent,
    # "monitor":    MonitorAgent,
    # "scheduler":  SchedulerAgent,
}