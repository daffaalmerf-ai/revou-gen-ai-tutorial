import streamlit as st 
import pandas as pd
import numpy as np


# Write a text
st.write("Hello, World!")

# Write a dataframe
df = pd.DataFrame({'first_col': [1,2,3], 'second': [4,5,6]})
st.write("We will show how a dataframe is written by Streamlit.")
st.write(df)

# Other options for displaying a Dataframe
st.write("There are other methods for displaying tables on streamlit.")
st.write("Using st.table() :")
st.table(df)

st.write("Using st.dataframe() :")
st.dataframe(df)

# Draw a chart
st.line_chart(df['first_col'])
df2 = pd.DataFrame(np.random.randn(20,3), columns=["a","b","c"])
st.line_chart(df2)

# Plot a map
# @st.cache_data
def show_map():
    map_data = pd.DataFrame(
        np.random.randn(1000, 2) / [50, 50] + [37.76, -122.4],
        columns=['lat', 'lon'])
    st.map(map_data)

show_map()

## A Divider
st.divider()

## Exploring widgets
st.subheader("Exploring Widgets in Streamlit")
st.text("Adding a slider")
x = st.slider(label = 'x')
st.write(x, 'squared is', x*x)

st.divider()
st.write("A checkbox can be used to toggle a conditional statement")
if st.checkbox('Show dataframe'):
    chart_data = pd.DataFrame(
       np.random.randn(20, 3),
       columns=['a', 'b', 'c'])

    st.write(chart_data)

st.divider()
st.write("Use selectbox to write from ")
df = pd.DataFrame({
    'first column': [1, 2, 3, 4],
    'second column': [10, 20, 30, 40]
    })

option = st.selectbox(
    'Which number do you like best?',
     df['first column'])

st.write('You selected: ', option)

st.divider()
st.text("A text input can be used to get ipnuts from users. We can store the input into a state variable. In this example, we store user name into a variable called 'name'.")
st.text_input("Your name", key="name")
if st.session_state.name: 
    st.write("Your Name is ", st.session_state.name)

st.sidebar.title("RevoU Tutorial on Streamlit")
st.sidebar.write("This sentence will be written on the sidebar.")

