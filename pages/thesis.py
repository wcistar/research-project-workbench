from datetime import date, datetime
import sqlite3

import streamlit as st

from database import (
    fetch_all,
    get_settings,
    insert_row,
    log_activity,
    save_settings,
    update_row,
)
from pages.components import related_tasks
from utils import (
    confirm_delete_dialog,
    due_hint,
    page_header,
    progress_bar,
    safe_date,
    show_db_error,
    text_or_empty,
    truncate_text,
)

THESIS_STAGES = ["未开始", "资料搜集", "写作中", "待修改", "已完成"]


def _timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _progress_form(record=None, key="thesis_progress"):
    """显示论文进度记录表单。"""
    record = record or {}
    with st.form(f"{key}_form"):
        module = st.text_input("章节或研究模块 *", text_or_empty(record.get("module")))
        c1, c2 = st.columns(2)
        stage = c1.selectbox(
            "当前阶段", THESIS_STAGES,
            index=THESIS_STAGES.index(record.get("stage", "未开始")),
        )
        progress = c2.number_input(
            "完成比例（%）", min_value=0, max_value=100,
            value=int(record.get("progress", 0) or 0), step=5,
        )
        next_action = st.text_input("下一步行动", text_or_empty(record.get("next_action")))
        has_due = st.checkbox("设置截止日期", value=bool(record.get("due_date")))
        due_date = st.date_input(
            "截止日期", safe_date(record.get("due_date"), date.today())
        ) if has_due else None
        current_problem = st.text_area("当前问题", text_or_empty(record.get("current_problem")))
        file_link = st.text_input("相关文件链接或本地路径", text_or_empty(record.get("file_link")))
        submitted = st.form_submit_button("保存进度", type="primary")
    if not submitted:
        return None
    if not module.strip():
        st.error("章节或研究模块不能为空。")
        return None
    return {
        "module": module.strip(), "stage": stage, "progress": int(progress),
        "next_action": next_action.strip(), "due_date": str(due_date) if due_date else None,
        "current_problem": current_problem.strip(), "file_link": file_link.strip(),
        "updated_at": _timestamp(), "source_task_id": record.get("source_task_id"),
    }


def _log_form(record=None, key="thesis_log"):
    """显示论文工作记录表单。"""
    record = record or {}
    with st.form(f"{key}_form"):
        log_date = st.date_input("日期", safe_date(record.get("log_date"), date.today()))
        completed = st.text_area("今日完成 *", text_or_empty(record.get("completed_today")))
        problem = st.text_area("遇到的问题", text_or_empty(record.get("problem")))
        next_action = st.text_area("下一步行动", text_or_empty(record.get("next_action")))
        submitted = st.form_submit_button("保存工作记录", type="primary")
    if not submitted:
        return None
    if not completed.strip():
        st.error("“今日完成”不能为空。")
        return None
    return {
        "log_date": str(log_date), "completed_today": completed.strip(),
        "problem": problem.strip(), "next_action": next_action.strip(),
    }


def _show_thesis_info(settings):
    """显示并编辑论文总体信息。"""
    with st.container(border=True):
        st.subheader("论文总体信息")
        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown(f"### {settings.get('thesis_title') or '尚未填写论文题目'}")
            st.caption(
                f"当前阶段：{settings.get('thesis_stage', '未开始')}　｜　"
                f"最近更新：{settings.get('thesis_updated_at') or '未记录'}"
            )
            st.write(f"**下一阶段节点：** {settings.get('thesis_next_milestone') or '未填写'}")
        with c2:
            progress_bar("总体完成比例", settings.get("thesis_progress", 0))
        with st.expander("编辑论文总体信息"):
            with st.form("thesis_info_form"):
                title = st.text_input("论文题目", settings.get("thesis_title", ""))
                stage = st.selectbox(
                    "当前阶段", THESIS_STAGES,
                    index=THESIS_STAGES.index(settings.get("thesis_stage", "资料搜集")),
                )
                progress = st.number_input(
                    "总体完成比例（%）", 0, 100,
                    int(settings.get("thesis_progress", 0) or 0), 5,
                )
                milestone = st.text_input(
                    "下一阶段节点", settings.get("thesis_next_milestone", "")
                )
                if st.form_submit_button("保存总体信息", type="primary"):
                    save_settings({
                        "thesis_title": title.strip() or "我的硕士论文",
                        "thesis_stage": stage,
                        "thesis_progress": str(progress),
                        "thesis_updated_at": str(date.today()),
                        "thesis_next_milestone": milestone.strip(),
                    })
                    log_activity("论文", "更新", title.strip() or "论文总体信息")
                    st.rerun()


def _show_progress_records(rows):
    """展示论文模块进度并提供逐条编辑删除。"""
    view_tab, new_tab = st.tabs(["查看进度", "新增进度"])
    with new_tab:
        data = _progress_form(key="new_thesis_progress")
        if data:
            insert_row("thesis_progress", data)
            log_activity("论文进度", "新增", data["module"])
            st.rerun()
    with view_tab:
        if not rows:
            st.info("暂无论文进度记录，可在“新增进度”中创建。")
            return
        for row in rows:
            hint = due_hint(row["due_date"], row["stage"] == "已完成")
            with st.container(border=True):
                top = st.columns([2, 1])
                top[0].markdown(f"**{row['module']}**　`{row['stage']}`")
                top[1].caption(hint or f"截止：{row['due_date'] or '未设置'}")
                progress_bar("章节进度", row["progress"])
                st.caption(f"下一步：{truncate_text(row['next_action'], 80) or '未填写'}")
                with st.expander("查看详情与操作"):
                    st.write(f"**当前问题：** {row['current_problem'] or '未填写'}")
                    st.write(f"**文件链接或路径：** {row['file_link'] or '未填写'}")
                    st.write(f"**最近更新时间：** {row['updated_at']}")
                    edit_key = f"edit_thesis_{row['id']}"
                    if st.session_state.get(edit_key):
                        data = _progress_form(row, edit_key)
                        if data:
                            update_row("thesis_progress", row["id"], data)
                            log_activity("论文进度", "更新", data["module"])
                            st.session_state[edit_key] = False
                            st.rerun()
                    else:
                        c1, c2 = st.columns(2)
                        if c1.button("编辑", key=f"edit_thesis_btn_{row['id']}"):
                            st.session_state[edit_key] = True
                            st.rerun()
                        if c2.button("删除", key=f"delete_thesis_btn_{row['id']}"):
                            confirm_delete_dialog(
                                "thesis_progress", row["id"], row["module"], "论文进度"
                            )


def _show_logs(rows):
    """展示论文工作记录。"""
    view_tab, new_tab = st.tabs(["查看工作记录", "新增工作记录"])
    with new_tab:
        data = _log_form(key="new_thesis_log")
        if data:
            insert_row("thesis_logs", data)
            log_activity("论文工作记录", "新增", data["completed_today"])
            st.rerun()
    with view_tab:
        if not rows:
            st.info("暂无论文工作记录。")
            return
        for row in rows:
            with st.expander(f'{row["log_date"]}　｜　{truncate_text(row["completed_today"], 38)}'):
                st.write(f"**今日完成：** {row['completed_today']}")
                st.write(f"**遇到的问题：** {row['problem'] or '未填写'}")
                st.write(f"**下一步行动：** {row['next_action'] or '未填写'}")
                edit_key = f"edit_thesis_log_{row['id']}"
                if st.session_state.get(edit_key):
                    data = _log_form(row, edit_key)
                    if data:
                        update_row("thesis_logs", row["id"], data)
                        log_activity("论文工作记录", "更新", data["completed_today"])
                        st.session_state[edit_key] = False
                        st.rerun()
                else:
                    c1, c2 = st.columns(2)
                    if c1.button("编辑", key=f"edit_tlog_btn_{row['id']}"):
                        st.session_state[edit_key] = True
                        st.rerun()
                    if c2.button("删除", key=f"delete_tlog_btn_{row['id']}"):
                        confirm_delete_dialog(
                            "thesis_logs", row["id"], row["completed_today"], "论文工作记录"
                        )


def show_thesis():
    """展示论文总体信息、模块进度、工作记录和相关事项。"""
    page_header("论文进度", "管理论文总体节点、章节进度与每日研究记录。")
    try:
        settings = get_settings()
        progress_rows = fetch_all("thesis_progress")
        logs = fetch_all("thesis_logs")
    except sqlite3.Error as error:
        show_db_error(error)
        return

    _show_thesis_info(settings)
    st.divider()
    _show_progress_records(progress_rows)
    st.divider()
    _show_logs(logs)
    st.divider()
    related_tasks({"论文"}, "论文", "论文相关事项")
