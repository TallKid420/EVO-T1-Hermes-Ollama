from hermes.agents.types.chat_agent import ChatAgent
from hermes.agents.types.research_agent import ResearcherAgent
from hermes.agents.types.engineer_agent import EngineerAgent
from hermes.agents.types.planner_agent import PlannerAgent
from hermes.agents.types.design_agent import DesignAgent
from hermes.agents.types.secretary_agent import SecretaryAgent
from hermes.agents.system.server_agent import ServerAgent

AGENT_REGISTRY = {
    "chat":       ChatAgent,
    "researcher": ResearcherAgent,
    "engineer":   EngineerAgent,
    "planner":    PlannerAgent,
    "design":     DesignAgent,
    "secretary":  SecretaryAgent,
    "server":     ServerAgent,
}