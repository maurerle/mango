from .agent.core import Agent
from .agent.role import Role, RoleAgent, RoleContext
from .container.factory import create as create_container

from importlib.metadata import version

__version__ = version("mango-agents-assume")