from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent

from dotenv import load_dotenv
load_dotenv(override=True)

def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b

model = init_chat_model("openai:gpt-4.1-nano", temperature=0)
tools = [add, multiply]
agent = create_react_agent(
    # disable parallel tool calls
    model=model.bind_tools(tools, parallel_tool_calls=False),
    tools=tools
)