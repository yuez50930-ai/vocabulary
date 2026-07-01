import streamlit as st
import sqlite3
from datetime import datetime

st.title("📘 AI错词系统（在线版）")

# ===== DB =====
conn = sqlite3.connect("vocab.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS words (
    word TEXT PRIMARY KEY,
    error_count INTEGER DEFAULT 0,
    last_seen TEXT
)
""")
conn.commit()

# ===== 输入 =====
st.subheader("输入错词")
input_words = st.text_input("例如：abandon hesitate consume")

if st.button("提交分析"):

    words = input_words.split()
    today = datetime.now().strftime("%Y-%m-%d")

    for w in words:
        cursor.execute("SELECT error_count FROM words WHERE word=?", (w,))
        result = cursor.fetchone()

        if result:
            cursor.execute("""
            UPDATE words
            SET error_count = error_count + 1,
                last_seen = ?
            WHERE word = ?
            """, (today, w))
        else:
            cursor.execute("""
            INSERT INTO words (word, error_count, last_seen)
            VALUES (?, 1, ?)
            """, (w, today))

    conn.commit()
    st.success("已更新错词库")

# ===== 排行榜 =====
st.subheader("🔥 高频错词Top10")

cursor.execute("""
SELECT word, error_count
FROM words
ORDER BY error_count DESC
LIMIT 10
""")

for w, c in cursor.fetchall():
    st.write(f"{w} — {c}")
