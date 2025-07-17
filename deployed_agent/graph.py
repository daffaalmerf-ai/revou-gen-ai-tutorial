# Initiating Langchain Chat Models
from langchain.chat_models import init_chat_model
from langgraph.graph import MessagesState
from langgraph.graph import StateGraph, START, END

model = init_chat_model("gpt-4.1-mini", model_provider= "openai")

# Node to invoke an LLM
def call_llm(state: MessagesState):
    return {"messages": model.invoke(state['messages'])}

# build the graph 
graph = (
    StateGraph(MessagesState)
    .add_node("call_llm", call_llm)
    .add_edge(START, "call_llm")
    .add_edge("call_llm", END)
    .compile(name = "simple agent")
)