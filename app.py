import streamlit as st
import os
import pandas as pd
import sqlite3
import uuid
import time
import graphviz
from utils import  custom_css
from streamlit_option_menu import option_menu
from langchain_anthropic import ChatAnthropic
from typing import Iterator
model   =   ChatAnthropic(
                model="claude-3-5-sonnet-20240620",
                    temperature=0,
             max_tokens= 8192, top_p= 0
            )

def format_answer_in_text_form(user_question: str, answer: pd.DataFrame, sql_query: str) -> Iterator[str]:
    if isinstance(answer, pd.DataFrame) and len(answer) <= 104:
        answer_dict = answer.to_dict()
        answer_format = f'''Summarize the answer to the question: "{user_question}" using the provided JSON data: "{answer_dict}", and the SQL query used to obtain this data: "{sql_query}".

                            1. Analyze the SQL query to understand:
                            - The tables and columns being queried
                            - Any joins, aggregations, or transformations applied
                            - The meaning and context of each column in the result set

                            2. Based on this analysis, interpret the data in the JSON, understanding what each field represents.

                            3. Summarize the answer for a business executive audience:
                            - Use bullet points for clarity
                            - Highlight key numbers using bold formatting (e.g., **1000**)
                            - Use tables only when necessary for clarity
                            - Focus on directly answering the question without extra recommendations or reasoning
                            - Keep the summary concise and to the point

                            4. Formatting guidelines:
                            - Start directly with the answer, without mentioning the audience or using phrases like "Here is a summary..."
                            - Use a single blank line between bullet points
                            - Replace any '$' with "\$" in the final text
                            - Present the information as a natural, conversational response without referencing the data source

                            Aim for a clear, concise summary that directly addresses the question based on the provided data and query analysis.'''
        response = model.stream(answer_format)
        for chunk in response:
            yield chunk
            time.sleep(0.001)

def validate_api_key(api_key):
    try:
        model = ChatAnthropic(
            api_key=api_key,
            model="claude-3-5-sonnet-20240620",
            temperature=0, top_p=0
        )
        model.invoke("Hello")
        st.success("API Key validated successfully!")
        return True
    except Exception as e:
        return False

if 'current_chat_id' not in st.session_state:
    st.session_state.current_chat_id = str(uuid.uuid4())

# Function to migrate the database
def migrate_database():
    conn = sqlite3.connect('chat_history.db')
    cursor = conn.cursor()
    
    # Check if the chat_history table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_history'")
    table_exists = cursor.fetchone()
    
    if table_exists:
        # Check if chat_id column exists
        cursor.execute("PRAGMA table_info(chat_history)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'chat_id' not in columns:
            # Add chat_id column
            cursor.execute("ALTER TABLE chat_history ADD COLUMN chat_id TEXT")
            
            # Update existing rows with a default chat_id
            default_chat_id = str(uuid.uuid4())
            cursor.execute("UPDATE chat_history SET chat_id = ? WHERE chat_id IS NULL", (default_chat_id,))
            
            conn.commit()
            print("Database migrated: added chat_id column")
    else:
        # Create the chat_history table with the correct schema
        cursor.execute("""
        CREATE TABLE chat_history
        (id TEXT PRIMARY KEY, chat_id TEXT, user_input TEXT, bot_response TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
        """)
        print("Database migrated: created chat_history table")
    
    conn.close()

# Call the migration function at the start of the app
migrate_database()

# Function to handle file upload
def upload_file():
    file = st.file_uploader("Upload CSV or Excel file", type=["csv", "xlsx"])
    if file is not None:
        if file.name.endswith('csv'):
            df = pd.read_csv(file)
        elif file.name.endswith('xlsx'):
            df = pd.read_excel(file)
        st.session_state['uploaded_df'] = df
        return df
    return st.session_state.get('uploaded_df', None)

# Function to save DataFrame to database using raw SQL commands
def save_to_db(df):
    conn = sqlite3.connect('mydatabase.db')
    cursor = conn.cursor()
    
    # Drop table if it exists
    cursor.execute("DROP TABLE IF EXISTS my_table")
    
    # Create table with columns based on DataFrame
    columns = ', '.join([f'"{col}" TEXT' for col in df.columns])
    cursor.execute(f"CREATE TABLE my_table ({columns})")
    
    # Insert data into table
    placeholders = ', '.join(['?'] * len(df.columns))
    insert_query = f"INSERT INTO my_table VALUES ({placeholders})"
    
    for row in df.itertuples(index=False):
        cursor.execute(insert_query, row)
    
    conn.commit()
    conn.close()

    # Update the schema in session state
    st.session_state['schema'] = get_schema()

def create_table_node(dot, table_name, schema, is_fact_table=False):
    table_label = f"<<TABLE BORDER='0' CELLBORDER='1' CELLSPACING='0'>"
    table_label += f"<TR><TD COLSPAN='2' BGCOLOR='{'lightblue' if is_fact_table else 'lightgrey'}'><B>{table_name}</B></TD></TR>"
    
    for col_name, col_type in schema:
        table_label += f"<TR><TD>{col_name}</TD><TD>{col_type}</TD></TR>"
    
    table_label += "</TABLE>>"
    
    dot.node(table_name, label=table_label, shape='plaintext')

def get_schema():
    conn = sqlite3.connect('mydatabase.db')
    table_name = "my_table"
    query = f"PRAGMA table_info({table_name})"
    schema_df = pd.read_sql(query, con=conn)
    conn.close()
    return schema_df

def show_schema():
    if 'schema' not in st.session_state or st.session_state['schema'].empty:
        st.write("No schema information available.")
        return
    
    schema_df = st.session_state['schema']
    
    # Convert schema DataFrame to a list of tuples for processing
    table_schema = [(row['name'], row['type']) for _, row in schema_df.iterrows()]
    
    dot = graphviz.Digraph(engine='dot')
    dot.attr(rankdir='LR', nodesep='0.5', ranksep='2', splines='curved', concentrate='true')
    
    # Create the table node (assuming it's the fact table)
    with dot.subgraph(name='cluster_fact') as c:
        c.attr(label='', style='invis')
        create_table_node(c, "my_table", table_schema, is_fact_table=True)
    
    # Assuming relationships are defined by `_ID` or `_DIM_ID` suffix in column names
    keys = [col[0] for col in table_schema if col[0].lower().endswith(('_id', '_dim_id'))]
    
    for key in keys:
        dot.edge(f'"my_table":"{key}"', f'"my_table":"{key}"', 
                 label=key,
                 fontsize='10', fontcolor='#333333',
                 dir='none',
                 arrowhead='none', arrowtail='none',
                 penwidth='2', color='#5D5D5D',
                 minlen='2', style='bold')

    st.graphviz_chart(dot)
# Function to execute SQL queries
def execute_query(query):
    conn = sqlite3.connect('mydatabase.db')
    try:
        result_df = pd.read_sql(query, con=conn)
        return result_df
    except sqlite3.Error as e:
        st.error(f"Error executing query: {e}")
        return None
    finally:
        conn.close()

# Function to generate SQL query using ChatBedrock
def generate_sql_query(user_question):
    model   =   ChatAnthropic(
                model="claude-3-5-sonnet-20240620",
                    temperature=0,
             max_tokens= 8192, top_p= 0
            )
    
    # Get the schema information
    conn = sqlite3.connect('mydatabase.db')
    query = "PRAGMA table_info(my_table)"
    schema_df = pd.read_sql(query, con=conn)
    conn.close()
    
    schema_info = schema_df.to_string()
    
    prompt = f"""Given the following schema for the 'my_table' table:

{schema_info}

Generate a SQL query to answer the following question:

{user_question}

Return only the SQL query without any explanations."""

    response = model.invoke(prompt)
    return response.content

# Function to save chat history to database
def save_chat_history(chat_id, user_input, bot_response):
    conn = sqlite3.connect('chat_history.db')
    cursor = conn.cursor()
    
    # Create table if it doesn't exist
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_history
    (id TEXT PRIMARY KEY, chat_id TEXT, user_input TEXT, bot_response TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
    """)
    
    # Insert new chat entry
    entry_id = str(uuid.uuid4())
    cursor.execute("INSERT INTO chat_history (id, chat_id, user_input, bot_response) VALUES (?, ?, ?, ?)",
                   (entry_id, chat_id, user_input, bot_response))
    
    conn.commit()
    conn.close()

# Function to load chat history from database
def load_chat_history(chat_id):
    conn = sqlite3.connect('chat_history.db')
    cursor = conn.cursor()
    
    # Create table if it doesn't exist (this ensures the chat_id column exists)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_history
    (id TEXT PRIMARY KEY, chat_id TEXT, user_input TEXT, bot_response TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
    """)
    
    cursor.execute("SELECT user_input, bot_response FROM chat_history WHERE chat_id = ? ORDER BY timestamp", (chat_id,))
    history = cursor.fetchall()
    
    conn.close()
    return history

# Function to get all chat IDs
def get_all_chat_ids():
    conn = sqlite3.connect('chat_history.db')
    cursor = conn.cursor()
    
    # Create table if it doesn't exist
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_history
    (id TEXT PRIMARY KEY, chat_id TEXT, user_input TEXT, bot_response TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
    """)
    
    cursor.execute("SELECT DISTINCT chat_id FROM chat_history ORDER BY timestamp DESC")
    chat_ids = cursor.fetchall()
    
    conn.close()
    return [chat_id[0] for chat_id in chat_ids]

# Function to delete a chat
def delete_chat(chat_id):
    conn = sqlite3.connect('chat_history.db')
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM chat_history WHERE chat_id = ?", (chat_id,))
    
    conn.commit()
    conn.close()

def main():
    st.set_page_config(page_title="SQL Assistant", page_icon="🤖", layout="wide")

    custom_css()

    # Initialize session state for API key validation
    if 'api_key_validated' not in st.session_state:
        st.session_state.api_key_validated = False

    if not st.session_state.api_key_validated:
        show_auth_ui()
    else:
        show_main_app()

def show_auth_ui():
    st.markdown("""
    <div style="display: flex; justify-content: center; align-items: center; height: 80vh;">
        <div style="background-color: #ffffff; padding: 40px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); width: 400px;">
            <h1 style="text-align: center; color: #1e3d7d; margin-bottom: 30px;">Welcome to DataDialogue</h1>
            <p style="text-align: center; color: #666; margin-bottom: 1px;">Please enter your Anthropic API Key to get started.</p>
    """, unsafe_allow_html=True)

    api_key = st.text_input("Anthropic API Key", type="password", help="Your API key will be securely stored as an environment variable")
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        if st.button("Validate API Key", use_container_width=True):
            with st.spinner("Validating API Key..."):
                if validate_api_key(api_key):
                    os.environ["ANTHROPIC_API_KEY"] = api_key
                    st.session_state.api_key_validated = True
                    st.success("API Key validated successfully!")
                    st.experimental_rerun()
                else:
                    st.error("Failed to validate API Key. Please check and try again.")

    st.markdown("""
        </div>
    </div>
    """, unsafe_allow_html=True)

def show_main_app():
    # Initialize session state for uploaded data and current chat ID
    if 'uploaded_df' not in st.session_state:
        st.session_state['uploaded_df'] = None
    if 'current_chat_id' not in st.session_state:
        st.session_state.current_chat_id = str(uuid.uuid4())

    # Sidebar navigation using option_menu
    with st.sidebar:
        selected = option_menu(
            menu_title="DataDialogue",
            options=["AI Bot", "Data Management"],
            icons=["chat", "database"],
            menu_icon="cast",
            default_index=0,
            styles={
                "container": {"padding": "0!important", "background-color": "#f9f9f9"},
                "icon": {"color": "#1e3d7d", "font-size": "25px"}, 
                "nav-link": {
                    "font-size": "16px", 
                    "text-align": "left", 
                    "margin":"0px", 
                    "--hover-color": "#f5f5f5",
                    "color": "#1e3d7d",
                },
                "nav-link-selected": {"background-color": "#dedfe0", "color": "#d81e18"},
            }
        )

    if selected == "AI Bot":
        show_chat_interface()
    elif selected == "Data Management":
        show_data_management()

def show_data_management():
    st.markdown("""
    <div style="background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px;">
        <h1 style='text-align: center; color: #1e3d7d; margin-top: 0;'>Data Management</h1>
        <hr style='border: 2px solid #df433f; width: 100%; margin-top: 10px; margin-bottom: 0;'>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("""
        <div style="background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px;">
            <h3 style='color: #1e3d7d;'>Upload Data</h3>
        """, unsafe_allow_html=True)
        
        df = upload_file()
        if df is not None:
            save_to_db(df)
            st.success("✅ Data successfully uploaded and saved to database!")
            st.session_state['data_uploaded'] = True

            st.markdown("<h3 style='color: #1e3d7d;'>Data Preview</h3>", unsafe_allow_html=True)
            st.dataframe(df.head(), use_container_width=True)
        
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <div style="background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px;">
            <h3 style='color: #1e3d7d;'>Schema Visualization</h3>
        """, unsafe_allow_html=True)
        
        if 'schema' in st.session_state and not st.session_state['schema'].empty:
            show_schema()
        else:
            st.info("📤 Please upload a file to view the schema.")
        
        st.markdown("</div>", unsafe_allow_html=True)

def show_chat_interface():
    st.markdown("""
    <div style="background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px;">
        <h1 style='text-align: center; color: #1e3d7d; margin-top: 0;'>DataDialogue</h1>
        <hr style='border: 2px solid #df433f; width: 100%; margin-top: 10px; margin-bottom: 0;'>
    </div>
    """, unsafe_allow_html=True)
    user_input = st.chat_input("Ask a question about your data:")
    

    col1, col2= st.columns([6, 2])
    with col1:
        # Initialize chat history if not present
        if "messages" not in st.session_state:
            st.session_state.messages = []
        with st.container(border=True,height=600):
        #with st.container(border=True,height=600): Display chat messages
            for message in st.session_state.messages:
                if message["role"] == "user":
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])
                elif message["role"] == "assistant":
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])
                if message["role"] == "sql_assistant" and "user_df" in message["content"]:
                    st.dataframe(message["content"]["user_df"])

            # Chat input
            if user_input:
                st.session_state.messages.append({"role": "user", "content": user_input})
                with st.chat_message("user"):
                    st.markdown(user_input)
                
                process_user_input(user_input)
            
   

    with col2:
        download_chat()
        # Clear chat button
        if st.button("Clear Chat", use_container_width=True):
            st.session_state.messages = []
        if upload_file is not None:           
            show_schema()
        else:
            st.info("📤 Please upload a file to view the schema.")
        

def download_chat():
    chat_content = "\n".join([f"{msg['role']}: {msg['content']}" for msg in st.session_state.messages])
    st.download_button(
        label="Download Chat",
        data=chat_content,
        file_name="chat_history.txt",
        mime="text/plain",
        use_container_width=True
    )

# Update process_user_input function
def process_user_input(user_input):
    with st.spinner("Generating SQL..."):
        sql_query = generate_sql_query(user_input)

    try:
        result = execute_query(sql_query)
    except Exception as e:
        result = None
        st.error(f"Error executing query: {e}")
    with st.chat_message("assistant"):
        bot_response =  st.write_stream(format_answer_in_text_form(user_input, result, sql_query))
        st.session_state.messages.append({"role": "assistant", "content": bot_response})
    # with st.chat_message("assistant"):
    #     st.markdown(bot_response)
    
    if result is not None and not result.empty:
        st.session_state.messages.append({
            "role": "sql_assistant",
            "content": {
                "user_df": result
            }
        })
        with st.chat_message("assistant"):
            st.dataframe(result, use_container_width=True)
    elif result is None:
        st.session_state.messages.append({"role": "assistant", "content": "The query encountered an error."})
        with st.chat_message("assistant"):
            st.error("The query encountered an error.")
    else:
        st.session_state.messages.append({"role": "assistant", "content": "The query returned no results."})
        with st.chat_message("assistant"):
            st.warning("The query returned no results.")

    save_chat_history(st.session_state.current_chat_id, user_input, bot_response)

if __name__ == "__main__":
    main()

