import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from streamlit.components.v1 import html

st.set_page_config(page_title="AI错词复习系统", layout="centered")
st.title("📘 AI错词系统（在线版）")

# ===== DB =====
conn = sqlite3.connect("vocab.db", check_same_thread=False)
cursor = conn.cursor()

# 1. 创建基础表
cursor.execute("""
CREATE TABLE IF NOT EXISTS words (
    word TEXT PRIMARY KEY,
    error_count INTEGER DEFAULT 0,
    last_seen TEXT
)
""")
conn.commit()

# 2. 数据库迁移：平滑追加遗忘曲线所需的字段
try:
    cursor.execute("ALTER TABLE words ADD COLUMN stage INTEGER DEFAULT 0")
    conn.commit()
except sqlite3.OperationalError:
    pass  # 字段已存在

try:
    cursor.execute("ALTER TABLE words ADD COLUMN next_review TEXT")
    conn.commit()
except sqlite3.OperationalError:
    pass

try:
    cursor.execute("ALTER TABLE words ADD COLUMN status TEXT DEFAULT 'learning'")
    conn.commit()
except sqlite3.OperationalError:
    pass

# ===== 艾宾浩斯记忆间隔 (天数) =====
INTERVALS = [1, 2, 4, 7, 15, 30]

# ===== 初始化 Session State 用于复习模块 =====
if "review_words" not in st.session_state:
    st.session_state.review_words = []
    st.session_state.review_index = 0
    st.session_state.review_initialized = False

# 用于记录刚刚点击了不认识的单词，用作弹窗触发
if "just_forgot_word" not in st.session_state:
    st.session_state.just_forgot_word = None

# 自动获取今日需要复习的词
def load_review_words():
    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT word, stage, error_count 
        FROM words 
        WHERE (next_review IS NULL OR next_review <= ?) 
          AND status = 'learning'
        ORDER BY error_count DESC
    """, (today_str,))
    st.session_state.review_words = cursor.fetchall()
    st.session_state.review_index = 0
    st.session_state.review_initialized = True

if not st.session_state.review_initialized:
    load_review_words()


# ===== 页面标签分栏 =====
tab1, tab2, tab3, tab4 = st.tabs(["📥 录入错词", "🔁 智能复习", "📚 错词库管理", "🔥 高频排行"])

# ==================== Tab 1: 录入错词 ====================
with tab1:
    st.subheader("输入新错词")
    input_words = st.text_input("例如：abandon hesitate consume", key="input_words")

    if st.button("提交分析", key="submit_btn"):
        if input_words.strip():
            words = input_words.split()
            today = datetime.now().strftime("%Y-%m-%d")
            # 新错词默认安排在明天进行第一次复习
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

            for w in words:
                cursor.execute("SELECT error_count FROM words WHERE word=?", (w,))
                result = cursor.fetchone()

                if result:
                    # 再次写错的词：错误次数递增，记忆阶段重置为 0，安排在明天复习，状态恢复为 'learning'
                    cursor.execute("""
                    UPDATE words
                    SET error_count = error_count + 1,
                        last_seen = ?,
                        stage = 0,
                        next_review = ?,
                        status = 'learning'
                    WHERE word = ?
                    """, (today, tomorrow, w))
                else:
                    # 全新错词
                    cursor.execute("""
                    INSERT INTO words (word, error_count, last_seen, stage, next_review, status)
                    VALUES (?, 1, ?, 0, ?, 'learning')
                    """, (w, today, tomorrow))

            conn.commit()
            st.success("已更新错词库，并已安排在明日进行首次复习！")
            load_review_words()  # 重新加载复习列表
        else:
            st.warning("请输入单词后再提交。")


# ==================== Tab 2: 智能复习 ====================
with tab2:
    st.subheader("🔁 艾宾浩斯智能复习")
    
    if st.button("🔄 刷新今日复习列表"):
        load_review_words()
        st.rerun()

    # 处理“不认识”点击后的自动弹窗跳转
    if st.session_state.just_forgot_word:
        forgot_w = st.session_state.just_forgot_word
        st.session_state.just_forgot_word = None # 立即清空，防止循环弹窗
        
        # 1. 注入轻量 JavaScript 脚本自动在新标签页打开有道词典
        html(f"""
            <script type="text/javascript">
                window.open('https://dict.youdao.com/w/{forgot_w}', '_blank');
            </script>
        """, height=0)
        
        # 2. 界面友好提示
        st.toast(f"已为您跳转有道词典查询 '{forgot_w}'")
        st.markdown(f"ℹ️ 已自动尝试打开词典。若弹窗被浏览器拦截，请手动点击：[👉 查看 '{forgot_w}' 的有道释义](https://dict.youdao.com/w/{forgot_w})")

    review_list = st.session_state.review_words
    current_idx = st.session_state.review_index

    if review_list and current_idx < len(review_list):
        word, stage, err_count = review_list[current_idx]
        
        # 进度条与数量提示
        st.progress((current_idx) / len(review_list))
        st.write(f"今日复习进度: {current_idx + 1} / {len(review_list)}")
        
        # 单词展示卡片
        st.info(f"👉 **单词**:  `{word}`")
        st.write(f"当前记忆阶段: **Stage {stage}** | 累计错误次数: **{err_count}**")

        # 【核心修改点】：直接显示“认识”和“不认识”按钮，省去中间确认环节
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ 认识 (进入下一阶段)", use_container_width=True):
                # 计算下次复习时间（升级记忆阶段）
                next_stage = stage + 1
                status = 'learning'
                if next_stage >= len(INTERVALS):
                    status = 'mastered'
                    days = 365  # 已掌握的词放进长期归档，365天后再看
                else:
                    days = INTERVALS[next_stage]
                
                next_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
                
                cursor.execute("""
                    UPDATE words 
                    SET stage = ?, next_review = ?, status = ?, last_seen = ?
                    WHERE word = ?
                """, (next_stage, next_date, status, datetime.now().strftime("%Y-%m-%d"), word))
                conn.commit()
                
                st.session_state.review_index += 1
                st.rerun()
                
        with col2:
            if st.button("❌ 不认识 (跳转有道并重置)", use_container_width=True):
                # 1. 暂存当前错词，用于页面重载时触发 JS 弹窗
                st.session_state.just_forgot_word = word
                
                # 2. 忘记了，重置该词记忆阶段到 0，安排在明天重新复习
                next_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                cursor.execute("""
                    UPDATE words 
                    SET stage = 0, next_review = ?, last_seen = ?
                    WHERE word = ?
                """, (next_date, datetime.now().strftime("%Y-%m-%d"), word))
                conn.commit()
                
                # 3. 推进至下一个单词
                st.session_state.review_index += 1
                st.rerun()
    else:
        st.success("🎉 今日需要复习的单词已经全部完成，或者目前暂无需要复习的词。")


# ==================== Tab 3: 错词库管理 ====================
with tab3:
    st.subheader("📚 错词库全量管理")
    
    # 获取全量数据并转换为 DataFrame
    cursor.execute("""
        SELECT word, error_count, stage, next_review, status, last_seen 
        FROM words
    """)
    db_data = cursor.fetchall()

    if db_data:
        df = pd.DataFrame(db_data, columns=["单词", "错误次数", "记忆阶段", "下次复习日期", "学习状态", "最后遇到时间"])
        
        # 简单过滤/搜索框
        search_kw = st.text_input("🔍 搜索单词", key="search_bar")
        if search_kw:
            df = df[df["单词"].str.contains(search_kw, case=False, na=False)]
            
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # 快捷管理工具
        st.markdown("---")
        st.write("🔧 **快捷管理**")
        selected_word = st.selectbox("选择目标单词", [""] + list(df["单词"].values))
        if selected_word:
            sub_col1, sub_col2 = st.columns(2)
            with sub_col1:
                if st.button("🏆 直接标记为已掌握", key="master_btn"):
                    cursor.execute("UPDATE words SET status = 'mastered' WHERE word = ?", (selected_word,))
                    conn.commit()
                    st.success(f"已将 '{selected_word}' 标记为已掌握！")
                    load_review_words()
                    st.rerun()
            with sub_col2:
                if st.button("🗑️ 从数据库中删除", key="del_btn"):
                    cursor.execute("DELETE FROM words WHERE word = ?", (selected_word,))
                    conn.commit()
                    st.success(f"已从词库中删除 '{selected_word}'")
                    load_review_words()
                    st.rerun()
    else:
        st.info("词库里还没有单词，请先在录入板块添加。")


# ==================== Tab 4: 高频排行 ====================
with tab4:
    st.subheader("🔥 高频错词Top10")

    cursor.execute("""
    SELECT word, error_count
    FROM words
    ORDER BY error_count DESC
    LIMIT 10
    """)

    rank_data = cursor.fetchall()
    if rank_data:
        for i, (w, c) in enumerate(rank_data):
            st.write(f"**No.{i+1}** {w} — 错误次数: `{c}`")
    else:
        st.info("暂无错词排行数据。")
