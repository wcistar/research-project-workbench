from datetime import date, datetime

import pandas as pd
import streamlit as st

from database import delete_row, log_activity


def safe_date(value, default=None):
    """把数据库日期转换为日期对象，空值或错误值返回默认值。"""
    if value in (None, ""):
        return default
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return default


def text_or_empty(value):
    """将数据库空值转换为空字符串。"""
    return "" if value is None else str(value)


def to_dataframe(rows):
    """将记录转换为 Pandas DataFrame。"""
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def show_db_error(error):
    """统一显示数据库错误。"""
    st.error(f"数据库操作失败：{error}")


def truncate_text(value, length=36):
    """缩略显示较长文本。"""
    text = text_or_empty(value)
    return text if len(text) <= length else f"{text[:length]}…"


def due_hint(value, completed=False, current_date=None):
    """生成截止日期的中文提醒标签。"""
    due = safe_date(value)
    if completed or due is None:
        return ""
    days = (due - (current_date or date.today())).days
    if days < 0:
        return f"🔴 已逾期 {abs(days)} 天"
    if days == 0:
        return "🟠 今天截止"
    if days <= 3:
        return f"🟠 {days} 天后截止"
    if days <= 7:
        return f"🔵 {days} 天后截止"
    return ""


def page_header(title, caption):
    """显示统一的页面标题与说明。"""
    st.title(title)
    st.caption(caption)


def progress_bar(label, value):
    """显示限制在 0 到 100 的进度条。"""
    number = max(0, min(100, int(value or 0)))
    st.write(f"{label}　**{number}%**")
    st.progress(number)


def apply_theme():
    """应用简洁蓝色系样式并隐藏 Streamlit 默认页面导航。"""
    st.markdown(
        """
        <style>
        [data-testid="stSidebarNav"],
        [data-testid="stElementToolbar"],
        [data-testid="stDecoration"],
        button[data-testid="stBaseButton-header"],
        button[data-testid="stMainMenuButton"] {display: none !important;}
        [data-testid="stHeader"] {background: rgba(248,250,247,.94);}
        .block-container {padding-top: 2rem; padding-bottom: 3rem; max-width: 1400px;}
        h1 {font-size: 1.75rem !important; color: #3F5F48;}
        h2, h3 {color: #4E6F57;}
        [data-testid="stMetric"] {
            border: 1px solid #D8E2D6;
            border-radius: 12px;
            padding: 14px 16px;
            background: #F2F6F0;
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
            border-color: #D8E2D6 !important;
            border-radius: 12px !important;
        }
        [data-testid="stSidebar"] {
            background: #EEF3EC;
            border-right: 1px solid #D8E2D6;
        }
        [data-testid="stProgressBar"] > div > div > div {
            background-color: #6F8F74 !important;
        }
        .status-green {color:#5E8066; font-weight:600;}
        .status-orange {color:#B27A45; font-weight:600;}
        .status-red {color:#A85F58; font-weight:600;}
        .status-gray {color:#747D76; font-weight:600;}
        @media (max-width: 700px) {
            .block-container {padding-left: 1rem; padding-right: 1rem;}
            h1 {font-size: 1.45rem !important;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.dialog("确认删除")
def confirm_delete_dialog(table, row_id, title, entity_type):
    """弹窗确认删除指定记录。"""
    st.warning(f"确定删除“{title}”吗？此操作无法在应用内撤销。")
    left, right = st.columns(2)
    if left.button("取消", width="stretch"):
        st.rerun()
    if right.button("确认删除", type="primary", width="stretch"):
        delete_row(table, row_id)
        log_activity(entity_type, "删除", title)
        st.rerun()
