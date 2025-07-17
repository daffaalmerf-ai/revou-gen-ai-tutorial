import streamlit as st
import os
from langchain_core.messages import AIMessageChunk, HumanMessage, AIMessage, SystemMessage
import agents.graph as gr
import agents.DBQNA as DBQNA
import agents.RAG as RAG
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.graph import MessagesState, StateGraph, START, END
from langgraph.types import Command
from typing import Literal
from pydantic import BaseModel, Field
from langgraph.checkpoint.memory import InMemorySaver

st.title("Simple Graph with Streamlit")

from dotenv import load_dotenv
load_dotenv(override=True)

def get_stream():
    for chunk, metadata in gr.agent.stream({"messages":"what is 4 + 7"}, stream_mode="messages"):
        if isinstance(chunk, AIMessageChunk):
            yield chunk

st.write_stream(get_stream)

DB_PATH = os.environ['DB_PATH']

from langchain.chat_models import init_chat_model
model = init_chat_model("gpt-4.1-mini", model_provider= "openai")

class BestAgent(BaseModel):
    agent_name: str = Field(description = "The best agent to handle specific request from users.")

class SupervisorState(MessagesState):
    user_question : str 

def supervisor(state: SupervisorState) -> Command[Literal["DBQNA", "RAG", END]]:
    last_message = state["messages"][-1]
    instruction = [SystemMessage(content=f"""You receive the following question from users. Decide which agent is the most suitable for completing the task.
                                    Delegate to DBQNA agent if users ask a question that can be answered by data inside a database. 
                                    Delegate to RAG agent if users ask a question about Dexa Medica. 
                                    End the conversation after you receive answer from agents.
                                 """)]
    model_with_structure = model.with_structured_output(BestAgent)
    response = model_with_structure.invoke(instruction + [last_message])
    return Command(
        update= {'user_question': last_message.content},
        goto=response.agent_name
    )

def callRAG(state: SupervisorState) -> Command[Literal['supervisor']]:
    prompt = state['user_question']
    response = RAG.graph.invoke({"messages":HumanMessage(content=prompt)})
    return Command(
        goto=END,
        update={"messages": response['messages'][-1]}
    )

def callDBQNA(state: SupervisorState) -> Command[Literal['supervisor']]:
    prompt = state['user_question']
    response = DBQNA.graph.invoke({"messages":HumanMessage(content=prompt), "db_name": DB_PATH, "user_question" : prompt})
    return Command(
        goto=END,
        update={"messages": response['messages'][-1]}
    )

# memory = InMemorySaver()
supervisor_agent = (
    StateGraph(SupervisorState)
    .add_node(supervisor)
    .add_node("RAG", callRAG)
    .add_node("DBQNA", callDBQNA)
    .add_edge(START, "supervisor")
    .compile(name= "supervisor")
)

prompt = st.chat_input("Write your question here ... ")
if prompt:
    with st.chat_message("human"):
        st.markdown(prompt)

    final_answer = ""
    with st.chat_message("ai"):
        status_placeholder = st.empty()
        answer_placeholder = st.empty()
        status_placeholder.status(label="Process Start")
        state = "Process Start"
        for chunk, metadata in supervisor_agent.stream({"messages":HumanMessage(content=prompt)}, stream_mode="messages"):
            if metadata['langgraph_node'] != state:
                status_placeholder.status(label=metadata['langgraph_node'])
                state = metadata['langgraph_node']
                final_answer = "" 
            
            if metadata['langgraph_node'] == "final_answer":
                final_answer += chunk.content
                answer_placeholder.markdown(final_answer)
            
            if metadata['langgraph_node'] == "generate":
                final_answer += chunk.content
                answer_placeholder.markdown(final_answer)
        
        status_placeholder.status(label="Complete", state='complete')

# DBQNA.graph.stream({"messages":HumanMessage(content=prompt), "db_name": DB_PATH, "user_question" : prompt}, stream_mode="messages")
# RAG.graph.stream({"messages":HumanMessage(content=prompt)}, stream_mode="messages")
            