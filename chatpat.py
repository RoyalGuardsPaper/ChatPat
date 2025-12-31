import streamlit as st
import ollama

st.set_page_config(page_title="ChatPat By Kaushik")

st.title("ChatPat")
st.caption("Your AI Assistant")

if "chats" not in st.session_state:
    st.session_state.chats = {}

if "chat_titles" not in st.session_state:
    st.session_state.chat_titles = {}

if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None

with st.sidebar:
    st.header("🗂 Chat History")

    if st.button("➕ New Chat"):
        chat_id = str(len(st.session_state.chats))
        st.session_state.chats[chat_id] = []
        st.session_state.chat_titles[chat_id] = "New chat"
        st.session_state.current_chat_id = chat_id

    for chat_id, title in reversed(list(st.session_state.chat_titles.items())):
        if st.button(title, key=f"chat_{chat_id}"):
            st.session_state.current_chat_id = chat_id

if st.session_state.current_chat_id is None:
    chat_id = "0"
    st.session_state.chats[chat_id] = []
    st.session_state.chat_titles[chat_id] = "New chat"
    st.session_state.current_chat_id = chat_id

current_messages = st.session_state.chats[st.session_state.current_chat_id]

for msg in current_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_input = st.chat_input("Ask me anything... or pluh")

if user_input:
    current_messages.append(
        {"role": "user", "content": user_input}
    )

    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = ollama.chat(
                model="llama3.1",
                messages=[
                    {
                        "role": "system",
                        "content": "You are ChatPat, a witty, expressive, and thoughtful AI. Be concise, human, and a little playful."
                    }
                ] + current_messages
            )

            assistant_reply = response["message"]["content"]
            st.markdown(assistant_reply)

    # Auto-name chat based on context (first exchange)
    if st.session_state.chat_titles[st.session_state.current_chat_id] == "New chat":
        first_user_message = next(
            (m["content"] for m in current_messages if m["role"] == "user"),
            None
        )
        if first_user_message:
            st.session_state.chat_titles[
                st.session_state.current_chat_id
            ] = first_user_message[:40] + "..."

    current_messages.append(
        {"role": "assistant", "content": assistant_reply}
    )