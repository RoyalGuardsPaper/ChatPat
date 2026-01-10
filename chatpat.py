import streamlit as st
import requests
import re
import os
from dotenv import load_dotenv
import hashlib
import uuid
from streamlit_cookies_manager import EncryptedCookieManager
from supabase import create_client

# -------------------- ENV SETUP --------------------
load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")

RAW_USERS = os.getenv("CHATPAT_USERS", "")
USERS = {}

for pair in RAW_USERS.split(","):
    if ":" in pair:
        u, p = pair.split(":", 1)
        USERS[u.strip()] = hashlib.sha256(p.strip().encode()).hexdigest()

if not OPENROUTER_API_KEY:
    st.error("OPENROUTER_API_KEY missing in .env")
    st.stop()

OPENROUTER_HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "http://localhost:8501",
    "X-Title": "ChatPat"
}

# -------------------- SUPABASE SETUP --------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# -------------------- STREAMLIT CONFIG --------------------
st.set_page_config(page_title="ChatPat", layout="wide")
st.markdown("""
<style>
/* Chat list layout helpers */
.chat-row {
    display: flex;
    align-items: center;
}

/* Perfectly centered square dots button */
.dots-btn {
    width: 32px;
    height: 32px;
    border-radius: 8px;
    border: none;
    background: rgba(255,255,255,0.08);
    color: inherit;
    font-size: 20px;
    line-height: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
}

.dots-btn:hover {
    background: rgba(255,255,255,0.16);
}
</style>
""", unsafe_allow_html=True)
st.title("ChatPat")
st.caption("Cloud-deployed, web-grounded AI assistant (OpenRouter)")

cookies = EncryptedCookieManager(
    prefix="chatpat_",
    password=os.getenv("COOKIE_SECRET", "dev-secret-change-me")
)

if not cookies.ready():
    st.stop()

def safe_get_cookie(key: str):
    try:
        return cookies.get(key)
    except Exception:
        return None

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def authenticate(username: str, password: str) -> bool:
    return USERS.get(username) == hash_password(password)

if "user" not in st.session_state:
    st.session_state.user = None

if not st.session_state.user:
    cookie_user = safe_get_cookie("user")
    if cookie_user:
        st.session_state.user = cookie_user

if not st.session_state.user:
    st.title("🔐 Login or Create an Account")

    tab1, tab2 = st.tabs(["Login", "Sign up"])

    with tab1:
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")

        if st.button("Login", key="login_btn"):
            if authenticate(username, password):
                st.session_state.user = username
                cookies["user"] = username
                cookies.save()
                st.rerun()
            else:
                st.error("Invalid username or password")

    with tab2:
        st.info("Create a new account. Passwords are stored hashed in memory for this session.")
        new_user = st.text_input("Choose a username", key="signup_user")
        new_pass = st.text_input("Choose a password", type="password", key="signup_pass")
        confirm_pass = st.text_input("Confirm password", type="password", key="signup_confirm")

        if st.button("Create account", key="signup_btn"):
            if not new_user or not new_pass:
                st.error("Username and password cannot be empty")
            elif new_user in USERS or ("user_db" in st.session_state and new_user in st.session_state.user_db):
                st.error("Username already exists")
            elif new_pass != confirm_pass:
                st.error("Passwords do not match")
            else:
                # register in-memory for this deployment
                hashed = hash_password(new_pass)
                USERS[new_user] = hashed
                if "user_db" not in st.session_state:
                    st.session_state.user_db = {}
                st.session_state.user_db[new_user] = hashed

                # auto-login
                st.session_state.user = new_user
                cookies["user"] = new_user
                cookies.save()
                st.success("Account created and logged in")
                st.rerun()

    st.stop()

# -------------------- SESSION STATE --------------------
if "chats" not in st.session_state:
    st.session_state.chats = {}

if "chat_titles" not in st.session_state:
    st.session_state.chat_titles = {}

if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None

if "web_cache" not in st.session_state:
    st.session_state.web_cache = {}

if "open_menu" not in st.session_state:
    st.session_state.open_menu = None

if "renaming_chat" not in st.session_state:
    st.session_state.renaming_chat = None


# Load chats for user from Supabase
if st.session_state.user not in st.session_state.chats:
    st.session_state.chats[st.session_state.user] = {}
    st.session_state.chat_titles[st.session_state.user] = {}

    resp = (
        supabase.table("chats")
        .select("chat_id, title, messages")
        .eq("user_id", st.session_state.user)
        .execute()
    )

    for row in resp.data or []:
        cid = row["chat_id"]
        st.session_state.chats[st.session_state.user][cid] = row["messages"]
        st.session_state.chat_titles[st.session_state.user][cid] = row["title"]

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


def save_chat(user, chat_id):
    supabase.table("chats").upsert({
        "user_id": user,
        "chat_id": chat_id,
        "title": st.session_state.chat_titles[user][chat_id],
        "messages": st.session_state.chats[user][chat_id]
    }).execute()

def delete_chat(user, chat_id):
    supabase.table("chats") \
        .delete() \
        .eq("user_id", user) \
        .eq("chat_id", chat_id) \
        .execute()

# -------------------- SIDEBAR --------------------
with st.sidebar:
    force_web = st.checkbox("🔍 Always use web", value=False)
    st.header("🗂 Chats")

    if st.button("➕ New Chat"):
        cid = str(uuid.uuid4())
        st.session_state.chats[st.session_state.user][cid] = []
        st.session_state.chat_titles[st.session_state.user][cid] = "New chat"
        st.session_state.current_chat_id = cid
        save_chat(st.session_state.user, cid)

    st.divider()

    for cid, title in reversed(list(st.session_state.chat_titles[st.session_state.user].items())):
        cols = st.columns([0.9, 0.1])

        # ---- CHAT TITLE / RENAME ----
        with cols[0]:
            if st.session_state.renaming_chat == cid:
                new_title = st.text_input(
                    "Rename chat",
                    value=title,
                    key=f"rename_{cid}",
                    label_visibility="collapsed"
                )
                if new_title and new_title != title:
                    st.session_state.chat_titles[st.session_state.user][cid] = new_title
                    save_chat(st.session_state.user, cid)
                if st.button("✔️", key=f"rename_ok_{cid}"):
                    st.session_state.renaming_chat = None
                    st.rerun()
            else:
                if st.button(title, key=f"chat_{cid}", use_container_width=True):
                    st.session_state.current_chat_id = cid
                    st.session_state.open_menu = None

        # ---- DOTS + POPUP ----
        with cols[1]:
            clicked = st.button("⋯", key=f"dots_{cid}", help="Chat options")
            if clicked:
                st.session_state.open_menu = cid if st.session_state.open_menu != cid else None

            if st.session_state.open_menu == cid:
                if st.button("✏️ Rename", key=f"rename_action_{cid}", help="rename", use_container_width=True):
                    st.session_state.renaming_chat = cid
                    st.session_state.open_menu = None
                    st.rerun()

                if st.button("🗑 Delete chat", key=f"delete_action_{cid}", help="delete", use_container_width=True):
                    delete_chat(st.session_state.user, cid)
                    st.session_state.chats[st.session_state.user].pop(cid, None)
                    st.session_state.chat_titles[st.session_state.user].pop(cid, None)

                    if st.session_state.current_chat_id == cid:
                        remaining = list(st.session_state.chats[st.session_state.user].keys())
                        st.session_state.current_chat_id = remaining[0] if remaining else None

                    st.session_state.open_menu = None
                    st.rerun()

    st.divider()

    with st.popover(f"👤 {st.session_state.user}", use_container_width=True):
        st.caption("🍪 Signed in")

        if st.button("🔄 Switch account", use_container_width=True):
            try:
                cookies.pop("user")
                cookies.save()
            except Exception:
                pass

            # clear only auth + chat selection, not entire app memory
            st.session_state.user = None
            st.session_state.current_chat_id = None
            st.rerun()

        if st.button("🚪 Logout", use_container_width=True):
            try:
                cookies.pop("user")
                cookies.save()
            except Exception:
                pass
            st.session_state.clear()
            st.rerun()


# -------------------- CHAT INIT --------------------
if st.session_state.current_chat_id is None:
    if st.session_state.chats[st.session_state.user]:
        st.session_state.current_chat_id = next(
            iter(st.session_state.chats[st.session_state.user])
        )
    else:
        cid = str(uuid.uuid4())
        st.session_state.chats[st.session_state.user][cid] = []
        st.session_state.chat_titles[st.session_state.user][cid] = "New chat"
        st.session_state.current_chat_id = cid
        save_chat(st.session_state.user, cid)

messages = st.session_state.chats[st.session_state.user][st.session_state.current_chat_id]

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
            "If the user asks an INFORMATIONAL or FACT-BASED question (definitions, explanations, history, lists, overviews), "
            "you MUST respond in clear bullet points. "
            "Each point should be concise and factual. "
            "If the user asks for IMPORTANT or KEY information, "
            "prioritize canonical and widely recognized material. "
            "Do not hallucinate. Be explicit about uncertainty."
            "For scientific questions, do deep research and tell the user that you dove deep."
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

            if r.status_code != 200:
                reply = f"LLM error {r.status_code}: {r.text}"
            else:
                data = r.json()
                if "choices" not in data or not data["choices"]:
                    reply = f"LLM error: empty response ({data})"
                else:
                    reply = data["choices"][0]["message"]["content"]

        except Exception as e:
            reply = f"LLM exception: {e}"

        st.markdown(reply)
        if reply.startswith("LLM error"):
            st.error(reply)
        messages.append({"role": "assistant", "content": reply})
        save_chat(st.session_state.user, st.session_state.current_chat_id)

        if grounding:
            with st.expander("🔗 Sources"):
                for r in grounding:
                    st.markdown(f"- {r['source']}")

    if st.session_state.chat_titles[st.session_state.user][st.session_state.current_chat_id] == "New chat":
        st.session_state.chat_titles[st.session_state.user][
            st.session_state.current_chat_id
        ] = user_input[:40] + "…" 
        save_chat(st.session_state.user, st.session_state.current_chat_id)

# (Menu action handler removed; now handled after sidebar)
