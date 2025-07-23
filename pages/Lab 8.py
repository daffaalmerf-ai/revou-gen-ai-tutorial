import streamlit as st
import os
from langchain_core.messages import AIMessageChunk, HumanMessage, AIMessage, SystemMessage
import agents.graph as gr
import agents.DBQNA as DBQNA
import agents.RAG as RAG
import agents.RAGFAQ as RAGFAQ
from langgraph.graph import MessagesState, StateGraph, START, END
from langgraph.types import Command
from typing import Literal
from pydantic import BaseModel, Field
from langgraph.checkpoint.memory import InMemorySaver
from langchain.chat_models import init_chat_model

st.title("Dexa Medica Agent")

from dotenv import load_dotenv
load_dotenv(override=True)

if "chat_rooms" not in st.session_state:
    st.session_state["chat_rooms"] = []
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = dict()
if "chat_memory" not in st.session_state:
    st.session_state["chat_memory"] = dict()
if "chat_agent" not in st.session_state:
    st.session_state["chat_agent"] = dict()
if "curr_chat_history_index" not in st.session_state:
    st.session_state["curr_chat_history_index"] = None

DB_PATH = os.environ['DB_PATH']

model = init_chat_model("gpt-4.1-mini", model_provider= "openai")

class BestAgent(BaseModel):
    agent_name: str = Field(description = "The best agent to handle specific request from users.")

class SupervisorState(MessagesState):
    user_question : str 

def supervisor(state: SupervisorState) -> Command[Literal["DBQNA", "RAG", "RAGFAQ", END]]:
    last_message = state["messages"][-1]
    instruction = [SystemMessage(content=f"""
                                 You are an intelligent router between agents. Based on the user's last message and the previous agent's response, decide the next step.
                                 Rules:
                                 - If the user's question can be answered using structured data (e.g., product codes, prices, stock, invoices), delegate to the **DBQNA** agent.
                                 - If the user's question is about Dexa Medica's company profile, such as vision, values, history, or business model, delegate to the **RAG** agent.
                                 - If the user's question is about Dexa Medica's frequently asked questions, such as products being manufactured, innovations, acronyms, research, facilities, career, etc., delegate to the **RAGFAQ** agent.
                                 - If the **RAG** agent failed to return a meaningful or relevant answer, fallback to **RAGFAQ** agent to try again.
                                 - If a sufficient answer has already been given, you may choose to **END** the conversation.
                                 You must reply ONLY with a JSON object like this:
                                 {{ "agent_name": "RAGFAQ" }}""")]
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

def callRAGFAQ(state: SupervisorState) -> Command[Literal['supervisor']]:
    prompt = state['user_question']
    response = RAGFAQ.graph.invoke({"messages":HumanMessage(content=prompt)})
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

def build_agent():
    memory = InMemorySaver()
    supervisor_agent = (
        StateGraph(SupervisorState)
        .add_node(supervisor)
        .add_node("RAG", callRAG)
        .add_node("RAGFAQ", callRAGFAQ)
        .add_node("DBQNA", callDBQNA)
        .add_edge(START, "supervisor")
        .compile(name= "supervisor", checkpointer=memory)
    )
    return memory, supervisor_agent

thread_id = st.session_state["curr_chat_history_index"]

with st.sidebar:
    if st.button("➕ New Chat", use_container_width=True):
        curr_len_rooms = len(st.session_state["chat_rooms"])
        st.session_state["chat_rooms"].append({
            "id": curr_len_rooms + 1,
            "title": "",
        })
        st.session_state["chat_history"][curr_len_rooms+1] = []
        st.session_state["curr_chat_history_index"] = curr_len_rooms + 1
        memory, supervisor_agent = build_agent()
        st.session_state["chat_memory"][curr_len_rooms+1] = memory
        st.session_state["chat_agent"][curr_len_rooms+1] = supervisor_agent

        st.rerun()
    st.title("💬 Chat Sessions")
        
    if len(st.session_state["chat_rooms"]) > 0:
        for chat_room in st.session_state["chat_rooms"]:
            label = chat_room["title"] if chat_room["title"] else ""
            if label != "":
                with st.sidebar.container():
                    cols = st.columns([0.8, 0.2])
                    with cols[0]:
                        if st.button(label, key=f"chat_room_{chat_room['id']}", type="tertiary", use_container_width=True):
                            st.session_state["curr_chat_history_index"] = chat_room["id"]
                            thread_id = chat_room["id"]
                    with cols[1]:
                        if st.button("🗑️", key=f"delete_btn_{chat_room['id']}", use_container_width=True):
                            deleted_id = chat_room["id"]
        
                            st.session_state["chat_rooms"] = [
                                chat for chat in st.session_state["chat_rooms"] if chat["id"] != deleted_id
                            ]
                            st.session_state["chat_history"].pop(deleted_id, None)
                            st.session_state["chat_memory"].pop(deleted_id, None)
                            st.session_state["chat_agent"].pop(deleted_id, None)

                            if st.session_state["curr_chat_history_index"] == deleted_id:
                                remaining_rooms = st.session_state["chat_rooms"]
                                if remaining_rooms:
                                    # Redirect to the previous room (or first one available)
                                    idx = next((i for i, chat in enumerate(remaining_rooms) if chat["id"] == deleted_id), None)
                                    prev_chat = remaining_rooms[idx - 1] if idx and idx > 0 else remaining_rooms[0]
                                    st.session_state["curr_chat_history_index"] = prev_chat["id"]
                                else:
                                    st.session_state["curr_chat_history_index"] = None

                            st.rerun()
        
if "chat_history" in st.session_state:
    curr_index = st.session_state["curr_chat_history_index"]
    if curr_index is not None and curr_index in st.session_state["chat_history"]:
        for chat in st.session_state["chat_history"][curr_index]:
            with st.chat_message("human"):
                st.markdown(chat["question"])
            with st.chat_message("ai"):
                st.markdown(chat["answer"])

prompt = st.chat_input("Write your question here ... ")
if prompt:
    if len(st.session_state["chat_rooms"]) == 0:
        new_id = 1
        st.session_state["chat_rooms"].append({"id": new_id, "title": prompt})
        st.session_state["chat_history"][new_id] = []
        memory, supervisor_agent = build_agent()
        st.session_state["chat_memory"][new_id] = memory
        st.session_state["chat_agent"][new_id] = supervisor_agent
        st.session_state["curr_chat_history_index"] = new_id
        thread_id = new_id
    question = ""
    answer = ""
    with st.chat_message("human"):
        st.markdown(prompt)
        question = prompt

    final_answer = ""
    with st.chat_message("ai"):
        status_placeholder = st.empty()
        question_placeholder = st.empty()
        answer_placeholder = st.empty()
        status_placeholder.status(label="Process Start")
        state = "Process Start"
        memory = None
        supervisor_agent = None

        thread_id = st.session_state["curr_chat_history_index"]
        memory = st.session_state["chat_memory"][st.session_state["curr_chat_history_index"]]
        supervisor_agent = st.session_state["chat_agent"][st.session_state["curr_chat_history_index"]]
        
        config = {"configurable": {"thread_id": thread_id}}
        
        for chunk, metadata in supervisor_agent.stream({"messages":HumanMessage(content=prompt)}, stream_mode="messages", config=config):
            if metadata['langgraph_node'] != state:
                status_placeholder.status(label=metadata['langgraph_node'])
                state = metadata['langgraph_node']
                final_answer = "" 
            
            if metadata['langgraph_node'] == "final_answer":
                final_answer += chunk.content
                answer_placeholder.markdown(final_answer)
            
            if metadata['langgraph_node'] == "generate" or metadata['langgraph_node'] == 'generate_faq':
                final_answer += chunk.content
                answer_placeholder.markdown(final_answer)
            
        answer = final_answer
        st.session_state["chat_history"][st.session_state["curr_chat_history_index"]].append({"question": question, "answer": answer})
        for i in range(len(st.session_state["chat_rooms"])):
            if st.session_state["chat_rooms"][i]["id"] == st.session_state["curr_chat_history_index"]:
                st.session_state["chat_rooms"][i]["title"] = st.session_state["chat_history"][st.session_state["curr_chat_history_index"]][0]["question"][:20] + "..."
        status_placeholder.status(label="Complete", state='complete')
        st.rerun()

# DBQNA.graph.stream({"messages":HumanMessage(content=prompt), "db_name": DB_PATH, "user_question" : prompt}, stream_mode="messages")
# RAG.graph.stream({"messages":HumanMessage(content=prompt)}, stream_mode="messages")
            