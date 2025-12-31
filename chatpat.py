import streamlit as st
import requests
import re
import os
from dotenv import load_dotenv

# -------------------- ENV SETUP --------------------
load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")

if not OPENROUTER_API_KEY:
    st.error("OPENROUTER_API_KEY missing in .env")
    st.stop()

OPENROUTER_HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "HTTP-Referer": "http://localhost:8501",
    "X-Title": "ChatPat"
}

# -------------------- STREAMLIT CONFIG --------------------
st.set_page_config(page_title="ChatPat", layout="wide")
st.title("ChatPat")
st.caption("Cloud-deployed, web-grounded AI assistant (OpenRouter)")

# -------------------- SESSION STATE --------------------
if "chats" not in st.session_state:
    st.session_state.chats = {}
if "chat_titles" not in st.session_state:
    st.session_state.chat_titles = {}
if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None
if "web_cache" not in st.session_state:
    st.session_state.web_cache = {}

# -------------------- HELPERS --------------------
def is_trivia(text: str) -> bool:
    triggers = [
        "who is", "what is", "when did", "where is", "how many",
        "define", "history of", "capital of", "population of"
    ]
    t = text.lower()
    return any(k in t for k in triggers)


def web_search(query: str, max_results: int = 5):
    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        return []

    if query in st.session_state.web_cache:
        return st.session_state.web_cache[query]

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CSE_ID,
        "q": query,
        "num": max_results,
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
    except Exception:
        return []

    results = []
    for item in data.get("items", []):
        results.append({
            "text": item.get("snippet", ""),
            "source": item.get("link", "")
        })

    st.session_state.web_cache[query] = results
    return results


IMPORTANCE_KEYWORDS = [
    "important", "key", "core", "main", "most important",
    "essential", "foundational", "primary"
]


def expresses_importance(q: str) -> bool:
    q = q.lower()
    return any(k in q for k in IMPORTANCE_KEYWORDS)


def detect_canonical_context(q: str) -> bool:
    return bool(re.search(r"by\\s+|works of|papers by|memos by", q, re.I))


# -------------------- SIDEBAR --------------------
with st.sidebar:
    force_web = st.checkbox("🔍 Always use web", value=False)
    st.header("🗂 Chats")

    if st.button("➕ New Chat"):
        cid = str(len(st.session_state.chats))
        st.session_state.chats[cid] = []
        st.session_state.chat_titles[cid] = "New chat"
        st.session_state.current_chat_id = cid

    for cid, title in reversed(list(st.session_state.chat_titles.items())):
        if st.button(title, key=f"chat_{cid}"):
            st.session_state.current_chat_id = cid

# -------------------- CHAT INIT --------------------
if st.session_state.current_chat_id is None:
    cid = "0"
    st.session_state.chats[cid] = []
    st.session_state.chat_titles[cid] = "New chat"
    st.session_state.current_chat_id = cid

messages = st.session_state.chats[st.session_state.current_chat_id]

for m in messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# -------------------- INPUT --------------------
user_input = st.chat_input("Ask me anything…")

if user_input:
    messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        use_web = force_web or is_trivia(user_input)
        grounding = web_search(user_input) if use_web else []

        system_prompt = (
            "You are ChatPat, a careful assistant. "
            "If the user asks for IMPORTANT or KEY information, "
            "prioritize canonical and widely recognized material. "
            "Do not hallucinate. Be explicit about uncertainty."
        )

        llm_messages = [{"role": "system", "content": system_prompt}]

        if grounding:
            context = "\n".join(f"- {r['text']}" for r in grounding)
            llm_messages.append({
                "role": "system",
                "content": f"WEB CONTEXT:\n{context}"
            })

        llm_messages += messages

        payload = {
            "model": "mistralai/mistral-7b-instruct",
            "messages": llm_messages
        }

        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=OPENROUTER_HEADERS,
                json=payload,
                timeout=60
            )
            data = r.json()
            reply = data["choices"][0]["message"]["content"]
        except Exception as e:
            reply = f"LLM error: {e}"

        st.markdown(reply)
        messages.append({"role": "assistant", "content": reply})

        if grounding:
            with st.expander("🔗 Sources"):
                for r in grounding:
                    st.markdown(f"- {r['source']}")

    if st.session_state.chat_titles[st.session_state.current_chat_id] == "New chat":
        st.session_state.chat_titles[
            st.session_state.current_chat_id
        ] = user_input[:40] + "…"