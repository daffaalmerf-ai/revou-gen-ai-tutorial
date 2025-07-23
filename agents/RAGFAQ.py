import os
from langchain.chat_models import init_chat_model
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_core.tools import tool
from langgraph.graph import MessagesState, StateGraph
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import ToolNode
from langgraph.graph import END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_milvus import Milvus
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv
from langchain_core.documents import Document

load_dotenv(override=True)

import pdfplumber
from collections import Counter, defaultdict
from collections import defaultdict
import pdfplumber
import re
import os

pdf_filename = "FAQ Dexa Medica.pdf"
pdf_path = os.path.join(".\docs", pdf_filename)

font_sizes_dict = {}

def fetch_font_stats(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        stats_arr_dict = []
        word = ""
        for page in pdf.pages:
            x0s = []
            y1s = []
            for char in page.chars:
                size = round(char.get("size", 0), 1)
                fontname = char.get("fontname", "").lower()
                text = char.get("text", "")
                x0 = char.get("x0", 0)
                y1 = char.get("y1", 0)
                if text != " ":
                    word += text
                    x0s.append(x0)
                    y1s.append(y1)
                else:
                    stats_arr_dict.append({
                        "text": word,
                        "font_size": size,
                        "font_style": fontname,
                        "x0": min(x0s) if len(x0s) > 1 else 0,
                        "y1": min(y1s) if len(y1s) > 1 else 0
                    })
                    x0s = []
                    word = ""
        return stats_arr_dict

def fetch_qa_categories(pdf_path):
    data = []
    category = ""
    question = ""
    answer = ""
    prev_class = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            line_dict = defaultdict(list)
            for char in page.chars:
                y0 = round(char.get("top", 1), 1)
                line_dict[y0].append(char)
            for y0 in sorted(line_dict):
                line_chars = sorted(line_dict[y0], key=lambda c: c["x0"])
                line = "".join([char["text"] for char in line_chars]).strip()
                category_pattern = [f"{char['size']}-{char['fontname'].lower()}" for char in line_chars]
                category_pattern = " ".join(category_pattern)
                is_category = True if "bold" in category_pattern and "13.4" in category_pattern else False
                question_pattern = r"^\d+\.\s?.*\?$"
                if line in ("o", " ", ""):
                    continue
                line_class = "answer"
                if re.match(question_pattern, line):
                    line_class = "question"
                elif is_category:
                    line_class = "category"
                if prev_class == "":
                    prev_class = line_class

                if line_class == "category":
                    if prev_class == "answer":
                        category = line
                    else:
                        category = category + " " + line
                elif line_class == "question":
                    if prev_class in ("category", "answer") and answer != "" and question != "":
                        cleaned_question = re.sub(r"^\d+\.\s*", "", question.strip())
                        data.append({
                            "filename": pdf_filename.strip(),
                            "category": category.strip(),
                            "question": cleaned_question.strip(),
                            "answer": answer.strip()
                        })
                        question = line
                        answer = ""
                    else:
                        question = question + " " + line
                else:
                    answer = answer + " " + line
                prev_class = line_class
        if question and question != "" and answer and answer != "" and category and category != "":
            data.append({
                "filename": pdf_filename.strip(),
                "category": category.strip(),
                "question": question.strip(),
                "answer": answer.strip(),
            })
    return data

def connect_milvus(embedding_model, milvus_db, milvus_host, milvus_port, milvus_collection):
    embedding_model = OpenAIEmbeddings(model=embedding_model)

    vector_store = Milvus(
        embedding_function=embedding_model,
        connection_args={
            "uri": f"http://{milvus_host}:{milvus_port}",
            "db_name": milvus_db
        },
        collection_name=milvus_collection,
    )

    return vector_store

milvus_db = os.getenv("MILVUS_DB")
milvus_host = os.getenv("MILVUS_HOST")
milvus_port = os.getenv("MILVUS_PORT")
milvus_collection = os.getenv("MILVUS_COLLECTION")

vector_store = connect_milvus("text-embedding-3-small", milvus_db, milvus_host, milvus_port, milvus_collection)
llm = init_chat_model("gpt-4.1-mini", model_provider="openai")
@tool(response_format="content_and_artifact")
def retrieve_faq(query: str):
    """Retrieve information related to a query."""
    retrieved_docs = vector_store.similarity_search(query, k=5)
    serialized = "\n\n".join(
        (f"Source: {doc.metadata}\n" f"Content: {doc.page_content}")
        for doc in retrieved_docs
    )
    return serialized, retrieved_docs

def query_or_respond_faq(state: MessagesState):
    """Generate tool call for retrieval or respond."""
    llm_with_tools = llm.bind_tools([retrieve_faq])
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}

tools_faq = ToolNode([retrieve_faq], name="tools_faq")

def generate_faq(state: MessagesState):
    """Generate answer."""
    recent_tool_messages = []
    for message in reversed(state["messages"]):
        if message.type == "tool":
            recent_tool_messages.append(message)
        else:
            break
    tool_messages = recent_tool_messages[::-1]

    docs_content = "\n\n".join(
        doc.page_content
        for m in tool_messages
        if hasattr(m, "artifact") and isinstance(m.artifact, list)
        for doc in m.artifact
        if isinstance(doc, Document)
    )
    system_message_content = (
        "You are an assistant for question-answering tasks. "
        "Use the following pieces of retrieved context to answer "
        "the question. If you don't know the answer, say that you "
        "don't know. Keep the answer concise."
        "\n\n"
        f"{docs_content}"
    )
    conversation_messages = [
        message
        for message in state["messages"]
        if message.type in ("human", "system")
        or (message.type == "ai" and not message.tool_calls)
    ]
    prompt = [SystemMessage(system_message_content)] + conversation_messages

    response = llm.invoke(prompt)

    return {"messages": [response]}


graph = (
    StateGraph(MessagesState)
    .add_node(query_or_respond_faq)
    .add_node(tools_faq)
    .add_node(generate_faq)
    .set_entry_point("query_or_respond_faq")
    .add_conditional_edges(
    "query_or_respond_faq",
        tools_condition,
        {END: END, "tools": "tools_faq"},
    )
    .add_edge("tools_faq", "generate_faq")
    .add_edge("generate_faq", END)
    .compile(name="RAGFAQ")
)