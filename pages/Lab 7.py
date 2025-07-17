import streamlit as st
import numpy as np
import time

# Display the page title
st.title("RevoU Customer Agent")

# Let's explore how to display a message: 
#with st.chat_message("ai"):
#    st.write("Hello")
#    st.line_chart(np.random.randn(30,3))

# How to get user prompt
#prompt = st.chat_input("Say something")

# Echoing users 
#if prompt:
#    with st.chat_message("human"):
#        st.write(prompt)
#    with st.chat_message("assistant"):
#        text = f"User has sent the following prompt: {prompt}"
#        
#        def stream_char():
#            for char in text: 
#                time.sleep(0.01)
#                yield char

#        st.write_stream(stream_char)   

# Message state 
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages in the state
for message in st.session_state.messages:
    with st.chat_message(message['role']):
        st.markdown(message['content'])

# Accepting user input 
prompt = st.chat_input("Say something")


#if prompt:
#    st.session_state.messages.append({"role":"user", "content":prompt})
#    with st.chat_message("user"):
#        st.markdown(prompt)
#    
#    with st.chat_message("assistant"):
#        text = f"User has sent the following prompt: {prompt}"
#        
#        def stream_char():
#            for char in text: 
#                time.sleep(0.01)
##                yield char
#
#        st.write_stream(stream_char) 
#    st.session_state.messages.append({"role":"assistant", "content": f"User has sent the following prompt: {prompt}"})

# Try to clear cache
clicked = st.sidebar.button("Clear Chat")
if clicked:
    st.session_state.messages = []

# Get response from OpenAI 
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
llm = OpenAI()

if prompt:
    st.session_state.messages.append({"role":"user", "content":prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    with st.chat_message("assistant"):
        stream = llm.chat.completions.create(
            model = "gpt-4.1-nano",
            messages= [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.messages
            ],
            stream=True,
        )
        response = st.write_stream(stream) 
    st.session_state.messages.append({"role":"assistant", "content": response})

