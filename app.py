import os

import streamlit as st

from database import configure_database, current_database_path, init_db
from pages.achievements import show_achievements
from pages.applications import show_applications
from pages.home import show_home
from pages.internship import show_internship
from pages.thesis import show_thesis
from utils import apply_theme


def is_demo_only_mode():
    """读取公开部署开关；开启后仅允许使用演示数据库。"""
    env_value = os.getenv("WORKBENCH_DEMO_ONLY", "").strip().lower()
    if env_value in {"1", "true", "yes", "on"}:
        return True

    try:
        secret_value = st.secrets.get("WORKBENCH_DEMO_ONLY", False)
    except (FileNotFoundError, KeyError):
        secret_value = False
    return str(secret_value).strip().lower() in {"1", "true", "yes", "on"}


# 配置页面和统一样式。
st.set_page_config(page_title="个人研究与求职工作台", page_icon="📘", layout="wide")
apply_theme()

st.sidebar.markdown("## 个人研究与求职工作台")
st.sidebar.caption("研究、实习与求职进度集中管理")
demo_only = is_demo_only_mode()
if demo_only:
    mode = "demo"
    st.sidebar.info("当前为公开演示版本")
    st.sidebar.caption("公开环境已关闭个人模式，仅使用虚构示例数据。")
else:
    mode_label = st.sidebar.selectbox(
        "数据模式",
        ["演示模式", "个人模式"],
        index=0,
        help="公开展示和截图请使用演示模式；个人模式读取本机真实数据。",
    )
    mode = "demo" if mode_label == "演示模式" else "personal"

configure_database(mode)
init_db()
if mode == "demo":
    st.sidebar.success("当前使用完全虚构的演示数据")
else:
    st.sidebar.warning("当前使用本机个人数据，请勿公开截图")

page = st.sidebar.radio(
    "中文导航",
    ["总览", "论文进度", "实习与报告", "秋招投递", "成果归档"],
    label_visibility="collapsed",
)
st.sidebar.divider()
st.sidebar.caption(f"当前数据库：{current_database_path().name}")

if page == "总览":
    show_home()
elif page == "论文进度":
    show_thesis()
elif page == "实习与报告":
    show_internship()
elif page == "秋招投递":
    show_applications()
else:
    show_achievements()
