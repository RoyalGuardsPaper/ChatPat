import streamlit as st
import ollama
import requests
import re

GOOGLE_API_KEY = "AIzaSyC4N2PStgB_USb-PoGTipQh_8jIpOCxCjk"
GOOGLE_CSE_ID = "80e97146f02324853"

st.set_page_config(page_title="ChatPat By Kaushik")

st.title("ChatPat")
st.caption("Your AI Assistant")

if "chats" not in st.session_state:
    st.session_state.chats = {}

if "chat_titles" not in st.session_state:
    st.session_state.chat_titles = {}

if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None

if "web_cache" not in st.session_state:
    st.session_state.web_cache = {}

def is_trivia_question(text: str) -> bool:
    trivia_patterns = [
        r"who is",
        r"who are",
        r"who was",
        r"who were",
        r"what is",
        r"what was",
        r"what were",
        r"what are",
        r"when did",
        r"where is",
        r"where was",
        r"how many",
        r"capital of",
        r"define",
        r"history of",
        r"population of",
        r"weather of",
        r"how do i",
    ]
    text = text.lower()
    return any(re.search(p, text) for p in trivia_patterns)

def web_search(query: str, max_results: int = 5):
    if query in st.session_state.web_cache:
        return st.session_state.web_cache[query]

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CSE_ID,
        "q": query,
        "num": max_results,
    }

    response = requests.get(url, params=params, timeout=10)
    data = response.json()

    results = []
    for item in data.get("items", []):
        results.append({
            "text": item.get("snippet", ""),
            "source": item.get("link", "")
        })

    st.session_state.web_cache[query] = results
    return results

def semantic_need_web(query: str) -> bool:
    q_emb = ollama.embeddings(model="llama3.1", prompt=query)["embedding"]
    fact_emb = ollama.embeddings(
        model="llama3.1",
        prompt="This question requires factual verification."
    )["embedding"]

    dot = sum(a * b for a, b in zip(q_emb, fact_emb))
    return dot > 0.75

IMPORTANCE_KEYWORDS = [
    "important",
    "key",
    "core",
    "main",
    "most important",
    "essential",
    "foundational",
    "primary"
]

def expresses_importance(query: str) -> bool:
    q = query.lower()
    return any(k in q for k in IMPORTANCE_KEYWORDS)

CANONICAL_TOPICS = {
    "howard marks": {
        "important_memos": [
            "The Most Important Thing",
            "Risk",
            "Cycles",
            "Second-Level Thinking",
            "Margin of Safety",
            "You Can’t Predict. You Can Prepare.",
            "Pendulum"
        ],
        "description": (
            "Howard Marks is known for his client memos at Oaktree Capital, "
            "many of which are summarized in or form the basis of his book "
            "'The Most Important Thing'."
        )
    }
}


def detect_canonical_context(query: str):
    """Return canonical topic dict if query mentions a canonical figure/topic."""
    q = query.lower()
    for key, val in CANONICAL_TOPICS.items():
        if key in q:
            return val
    return None

with st.sidebar:
    force_web = st.checkbox("🔍 Always use web for this chat", value=False)
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

user_input = st.chat_input("Ask me anything...")

if user_input:
    current_messages.append(
        {"role": "user", "content": user_input}
    )

    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        grounding_context = ""

        canonical_context = detect_canonical_context(user_input)
        importance_requested = expresses_importance(user_input)

        use_web = (
            force_web
            or is_trivia_question(user_input)
            or semantic_need_web(user_input)
        )

        # If the user asks for IMPORTANT / CORE works, we anchor first, search second
        if canonical_context and importance_requested:
            use_web = True

        if use_web:
            with st.spinner("Checking facts..."):
                grounding_results = web_search(user_input)
        else:
            grounding_results = []

        system_prompt = (
            "You are ChatPat, a careful and well-read assistant.\n"
            "If the user asks for IMPORTANT, KEY, or CORE works, you MUST:\n"
            "1) Start with widely recognized, canonical material.\n"
            "2) Explicitly label anything secondary or obscure.\n"
            "3) Do NOT lead with minor papers, interviews, or niche writings.\n"
            "Use web sources only to support or verify, not to redefine importance.\n"
            "If information is uncertain, say so clearly.\n"
            "Do not hallucinate."
        )

        messages = [
            {
                "role": "system",
                "content": system_prompt
            }
        ]

        if canonical_context:
            canonical_text = (
                "CANONICAL CONTEXT:\n"
                f"{canonical_context['description']}\n\n"
                "Key canonical works:\n"
                + "\n".join(f"- {t}" for t in canonical_context["important_memos"])
            )
            messages.append(
                {
                    "role": "system",
                    "content": canonical_text
                }
            )

        if canonical_context and importance_requested:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "ANSWER STRUCTURE:\n"
                        "- Start with a short list of the MOST IMPORTANT points.\n"
                        "- Explain why each is considered important.\n"
                        "- Optionally mention secondary points at the end, clearly labeled."
                    )
                }
            )

        if grounding_results:
            context_text = "\n".join(
                f"- {r['text']}" for r in grounding_results
            )
            messages.append(
                {
                    "role": "system",
                    "content": f"WEB CONTEXT:\n{context_text}"
                }
            )

        if use_web and not grounding_results:
            assistant_reply = (
                "I couldn’t find reliable information on that.\n\n"
                "Can you clarify or be more specific?"
            )
            st.markdown(assistant_reply)
            current_messages.append({"role": "assistant", "content": assistant_reply})
            st.stop()

        messages += current_messages

        response = ollama.chat(
            model="llama3.1",
            messages=messages
        )

        assistant_reply = response["message"]["content"]
        st.markdown(assistant_reply)

        if grounding_results:
            with st.expander("🔗 Sources"):
                for r in grounding_results:
                    st.markdown(f"- {r['source']}")

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