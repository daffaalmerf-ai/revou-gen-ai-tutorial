import os 
from langchain_core.tools import tool
import sqlite3
from langchain.chat_models import init_chat_model

model = init_chat_model("gpt-4.1-mini", model_provider= "openai")
DB_PATH = os.environ['DB_PATH']

# Supporting function 
def create_cursor(path_to_db:str):
    connection = sqlite3.connect(path_to_db)
    return connection.cursor()

@tool("get_table_list", parse_docstring=True)
def get_table_list(db_name):
    """ 
        A tool to get a list of all tables from the database. The tool requires database connection and returns list of tables inside the database. 

        Args:
        db_name = database connection 

        Return: 
        list of table names
    """
    # create a cursor 
    cursor = create_cursor(db_name)

    # get table list
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()  

    # return
    return [table[0] for table in tables]

@tool("get_table_schema", parse_docstring=True)
def get_table_schema(table_list, db_name):
    """ 
        This tool fetches table schema and a connetion to the database. It will return column names, column data types, default values. 

        Args: 
        table_list = list of table names
        db_name = database name or path to database

        Return: 
        A string containing schema of tables in the table_list
    """
    # create a cursor 
    cursor = create_cursor(db_name)

    # get table info
    output_string = ""
    for table in table_list: 
        cursor.execute(f"PRAGMA table_info({table});")
        column_list = cursor.fetchall()  
    
        # constructing output 
        constructed_tbl_info = ""
        if len(column_list) == 0: 
            field_names = "Table is not found. Try a different name."
        else:
            field_names = " | ".join([column[0] for column in cursor.description])
            for column in column_list: 
                cid = column[0]
                name = column[1]
                type = column[2]
                notnull =  "True" if column[3] == 1 else "False"
                default_value = column[4]
                pk = "Primary Key" if column[5] == 1 else "Not PK"
                constructed_tbl_info += f"\t{cid} | {name} | {type} | {notnull} | {default_value} | {pk} \n"

        output_string += f"""Table name: {table}\n\t{field_names}\n{constructed_tbl_info}\n"""

    return output_string

## tool for running query 
@tool("running_query", parse_docstring=True)
def running_query(query:str, db_name:str):
    """
        This tool runs the given query against a database names db_name.

        Args: 
        query = query statement that will be executed 
        db_name = location of the database to which the query will be executed

        Return: 
        result of the query in string.
    """
    # creating cursor
    cursor = create_cursor(db_name)

    # executing the query
    cursor.execute(query)
    query_result = cursor.fetchall()

    # constructing output 
    data_string = ""
    if len(query_result) == 0: 
        field_names = "No data is returned."
    else:
        field_names = " | ".join([column[0] for column in cursor.description])
        for record in query_result: 
            data_string += " | ".join([str(cell) for cell in record]) + "\n"

    output_string = f"""{field_names}\n{data_string}\n"""
    return output_string


## Building the graph

from langgraph.prebuilt import ToolNode
from langgraph.graph import MessagesState
from typing import Any, Annotated, Literal
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

# expand the MessagesState
class DBGraphState(MessagesState):
    db_name: Annotated[Any, "Database location"]
    user_question: Annotated[str, "User question that must be answered by querying the database"]

# the first node
def list_tables(state: DBGraphState):
    tool_call = {
        "name": "get_table_list",
        "args": {
            "db_name": state["db_name"]
        },
        "id": "abc123",
        "type": "tool_call"
    }
    tool_call_message = AIMessage(content="I am calling a tool to get list of tables from the database.", tool_calls=[tool_call])
    tool_message = get_table_list.invoke(tool_call)
    response = AIMessage(content=f"Available tables: {tool_message.content}")

    return {'messages': response}

# the second node
def get_schema_node(state: DBGraphState):
    
    input_question = state["user_question"]
    available_tables = state["messages"][-1]
    db_name = state["db_name"]
    instruction = [SystemMessage(content=f'''You are a business analyst from Dexa and an SQL expert. You receive a question from the user and a list of available
                                table in the database. Use the tool to get the structures of possible tables that you will use to construct the query later.
                                db_name = {db_name}
                                Here is the question from the user: {input_question}''')
                    ] + [available_tables]
    model_with_tools = model.bind_tools([get_table_schema], tool_choice="any")
    response = model_with_tools.invoke(instruction)

    # invoking tool 
    return {"messages": response}

invoking_tool_node = ToolNode([get_table_schema], name="invoking_tool_node")
## Let's build the node

def write_query(state:DBGraphState):
    dialect = "sqlite"
    top_k = 10
    instruction = SystemMessage(content=f'''You are an agent designed to interact with a SQL database.
                        Given an input question, create a syntactically correct {dialect} query to run,
                        then look at the results of the query and return the answer. Unless the user
                        specifies a specific number of examples they wish to obtain, always limit your
                        query to at most {top_k} results.

                        You can order the results by a relevant column to return the most interesting
                        examples in the database. Never query for all the columns from a specific table,
                        only ask for the relevant columns given the question.

                        DO NOT make any DML statements (INSERT, UPDATE, DELETE, DROP etc.) to the database.''')
    
    response = model.invoke([instruction] + state["messages"])    
   
    return {"messages": response}

def check_query(state: DBGraphState):
    dialect = 'sqlite'
    instruction = SystemMessage(content=f'''You are a SQL expert with a strong attention to detail.
    Double check the {dialect} query for common mistakes, including:
    - Using NOT IN with NULL values
    - Using UNION when UNION ALL should have been used
    - Using BETWEEN for exclusive ranges
    - Data type mismatch in predicates
    - Properly quoting identifiers
    - Using the correct number of arguments for functions
    - Casting to the correct data type
    - Using the proper columns for joins

    If there are any of the above mistakes, rewrite the query. If there are no mistakes,
    just reproduce the original query.

    Forbid any DML statements (INSERT, UPDATE, DELETE, DROP, TRUNCATE). If the query statement contains those statements, respond by "Forbidden query"
    ''')
    
    response = model.invoke([instruction] + state["messages"])    
    return {"messages": response}

def run_query_node(state:DBGraphState):
    query_checking_result = state["messages"][-1]
    dialect = 'sqlite'
    db_name = DB_PATH
    instruction = [SystemMessage(content=f'''If the last node is resulted in a forbidden query, proceed to the next node, explain why it is forbidden and skip calling tool.
                                 If the result is a valid {dialect} query statement, run the query by calling the given tool.
                                database_name = {db_name}
                                '''), query_checking_result]
    
    # Let the model decide 
    model_with_tools = model.bind_tools([running_query])
    model_response = model_with_tools.invoke(instruction)
    
    response = [model_response]
    
    # Manually calling tools 
    if model_response.tool_calls: 
        result = []
        for tool_call in model_response.tool_calls:
            tool_invocation_result = running_query.invoke(tool_call['args'])
            result.append(ToolMessage(content=tool_invocation_result, tool_call_id=tool_call["id"]))
            
        response += result

    return {"messages": response}

def final_answer(state:DBGraphState):
    user_question = state['user_question']
    query_result = state['messages'][-1]
    instruction= [SystemMessage(content=f'''Decide whether you can answer user question from the query result. If you have enough information, 
                               respond with the answer. 
                               If you do not have enough information, tell me your plan to get more accurate answer.
                               Here is the user question: {user_question}
                               Here is the query result: \n {query_result}
                               ''')]
    response = model.invoke(instruction)

    return {"messages": response}

# conditional node
def is_enough(state:DBGraphState) -> Literal['write_query', END]:
    user_question = state['user_question']
    last_responses = state['messages'][-3:]
    instruction = [SystemMessage(content=f"""Answer only with 'enough' or 'not enough'. Answer with 'enough', if your response indicate that 
                                there is enough information from the tool message to answer user question. Answer with 'enough' when 
                                the user asks you to perform a forbidden query. Answer with 'not enough' if otherwise.
                                User question = {user_question}""")
                                ] + last_responses

    response = model.invoke(instruction)
    response.content
    if response.content == 'enough':
        return END
    else:
        return "write_query"

graph = (
    StateGraph(DBGraphState)
    .add_node("get_table_list", list_tables)
    .add_node(get_schema_node)
    .add_node(invoking_tool_node, "invoking_tool_node")
    .add_node(write_query)
    .add_node(check_query)
    .add_node(run_query_node)
    .add_node(final_answer)
    .add_edge(START, "get_table_list")
    .add_edge("get_table_list","get_schema_node")
    .add_edge("get_schema_node","invoking_tool_node")
    .add_edge("invoking_tool_node", "write_query")
    .add_edge("write_query", "check_query")
    .add_edge("check_query", "run_query_node")
    .add_edge("run_query_node", "final_answer")
    .add_conditional_edges("final_answer", is_enough)
    .compile(name = "DBQNA")    
)