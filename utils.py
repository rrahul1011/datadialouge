import os
import json
import pandas as pd
import streamlit as st
from typing import Iterator
from langchain_anthropic import ChatAnthropic
import time

model   =   ChatAnthropic(
                model="claude-3-5-sonnet-20240620",
                    temperature=0,
             max_tokens= 8192, top_p= 0
            )
    

def styled_markdown(text, font_size="16px", font_family="Arial, sans-serif", color="#4a4a4a"):
    styled_text = f"""
    <p style="font-size: {font_size}; font-family: {font_family}; color: {color}; font-weight: bold;">
    {text}
    </p>
    """
    st.markdown(styled_text, unsafe_allow_html=True)

def clear_chat_save_hist():
    st.session_state.chat_history_external = []

def reset_conversation():
    st.session_state.chat_history_external = []

# Remove the create_sidebar() function

def custom_css():
    st.markdown("""
    <style>
    .stApp {
        background-color: #f9f9f9;
    }
    .main .block-container {
        padding-top: 1rem;
    }
    .stButton > button {
        background-color: #1e3d7d;
        color: #ffffff;
        border-radius: 5px;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        background-color: #df433f;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    .stDownloadButton > button {
        background-color: #1e3d7d;
        color: #ffffff;
        border-radius: 5px;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    .stDownloadButton > button:hover {
        background-color: #df433f;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    .stTextInput > div > div > input {
        background-color: #ffffff;
        border: 1px solid #dedfe0;
        border-radius: 5px;
        padding: 0.5rem;
    }
    .stSelectbox > div > div > select {
        background-color: #ffffff;
        border: 1px solid #dedfe0;
        border-radius: 5px;
        padding: 0.5rem;
    }
    .stDataFrame {
        background-color: #ffffff;
        border-radius: 5px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        padding: 1rem;
    }
    .stGraphvizChart {
        background-color: #ffffff;
        border-radius: 5px;
        padding: 1rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .stTabs {
        background-color: #ffffff;
        padding: 1rem;
        border-radius: 0.5rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    </style>
    """, unsafe_allow_html=True)


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