from datetime import date, datetime
import sqlite3

import streamlit as st

from database import fetch_all, insert_row, log_activity, update_row
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

PROJECT_STATUSES = ["未开始", "资料搜集", "撰写中", "修改中", "等待反馈", "已完成", "暂停"]


def _timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _project_form(record=None, key="internship_project"):
    """显示实习项目或报告表单。"""
    record = record or {}
    with st.form(f"{key}_form"):
        c1, c2 = st.columns(2)
        project_name = c1.text_input("项目名称 *", text_or_empty(record.get("project_name")))
        report_name = c2.text_input("报告名称 *", text_or_empty(record.get("report_name")))
        current_module = st.text_input("当前模块", text_or_empty(record.get("current_module")))
        c3, c4 = st.columns(2)
        status = c3.selectbox(
            "当前状态", PROJECT_STATUSES,
            index=PROJECT_STATUSES.index(record.get("status", "未开始")),
        )
        progress = c4.number_input(
            "完成比例（%）", 0, 100, int(record.get("progress", 0) or 0), 5
        )
        has_due = st.checkbox("设置截止日期", value=bool(record.get("due_date")))
        due_date = st.date_input(
            "截止日期", safe_date(record.get("due_date"), date.today())
        ) if has_due else None
        next_action = st.text_input("下一步行动", text_or_empty(record.get("next_action")))
        source_link = st.text_input("资料来源链接", text_or_empty(record.get("source_link")))
        report_path = st.text_input("报告文件路径", text_or_empty(record.get("report_path")))
        mentor_feedback = st.text_area("带教反馈", text_or_empty(record.get("mentor_feedback")))
        submitted = st.form_submit_button("保存项目", type="primary")
    if not submitted:
        return None
    if not project_name.strip() or not report_name.strip():
        st.error("项目名称和报告名称不能为空。")
        return None
    return {
        "project_name": project_name.strip(), "report_name": report_name.strip(),
        "current_module": current_module.strip(), "status": status,
        "progress": int(progress), "due_date": str(due_date) if due_date else None,
        "next_action": next_action.strip(), "source_link": source_link.strip(),
        "report_path": report_path.strip(), "mentor_feedback": mentor_feedback.strip(),
        "updated_at": _timestamp(), "source_task_id": record.get("source_task_id"),
    }


def _work_log_form(project_names, record=None, key="work_log"):
    """显示每日工作记录表单。"""
    record = record or {}
    options = project_names or ["未分类项目"]
    current = record.get("project_name", options[0])
    if current not in options:
        options = [current] + options
    with st.form(f"{key}_form"):
        log_date = st.date_input("日期", safe_date(record.get("log_date"), date.today()))
        project_name = st.selectbox("所属项目", options, index=options.index(current))
        completed = st.text_area("今日完成 *", text_or_empty(record.get("completed_today")))
        tomorrow = st.text_area("明日计划", text_or_empty(record.get("tomorrow_plan")))
        problem = st.text_area("遇到的问题", text_or_empty(record.get("problem")))
        submitted = st.form_submit_button("保存工作记录", type="primary")
    if not submitted:
        return None
    if not completed.strip():
        st.error("“今日完成”不能为空。")
        return None
    return {
        "log_date": str(log_date), "project_name": project_name,
        "completed_today": completed.strip(), "tomorrow_plan": tomorrow.strip(),
        "problem": problem.strip(),
    }


def _active_cards(projects):
    """用卡片展示当前进行中的报告。"""
    active = [row for row in projects if row["status"] not in {"已完成", "暂停"}]
    st.subheader("正在进行的报告")
    if not active:
        st.info("暂无正在进行的报告。")
        return
    columns = st.columns(min(3, len(active)))
    for index, row in enumerate(active):
        with columns[index % len(columns)]:
            with st.container(border=True):
                st.markdown(f"**{truncate_text(row['report_name'], 28)}**")
                st.caption(f"{row['project_name']} · {row['status']}")
                progress_bar("当前进度", row["progress"])
                st.write(f"**当前模块：** {truncate_text(row['current_module'], 34) or '未填写'}")
                st.write(f"**截止日期：** {row['due_date'] or '未设置'}")
                hint = due_hint(row["due_date"])
                if hint:
                    st.caption(hint)
                st.write(f"**下一步：** {truncate_text(row['next_action'], 46) or '未填写'}")


def _project_records(projects):
    """展示、新增、编辑和删除实习项目。"""
    view_tab, new_tab = st.tabs(["查看项目", "新增项目"])
    with new_tab:
        data = _project_form(key="new_project")
        if data:
            insert_row("internship_projects", data)
            log_activity("实习报告", "新增", data["report_name"])
            st.rerun()
    with view_tab:
        if not projects:
            st.info("暂无项目记录，可在“新增项目”中创建。")
            return
        for row in projects:
            with st.expander(
                f'{row["report_name"]}　｜　{row["status"]}　｜　{row["progress"]}%'
            ):
                st.write(f"**项目名称：** {row['project_name']}")
                st.write(f"**当前模块：** {row['current_module'] or '未填写'}")
                st.write(f"**下一步行动：** {row['next_action'] or '未填写'}")
                st.write(f"**截止日期：** {row['due_date'] or '未设置'}")
                st.write(f"**资料来源：** {row['source_link'] or '未填写'}")
                st.write(f"**报告路径：** {row['report_path'] or '未填写'}")
                st.write(f"**带教反馈：** {row['mentor_feedback'] or '未填写'}")
                st.caption(f"最近更新时间：{row['updated_at']}")
                edit_key = f"edit_project_{row['id']}"
                if st.session_state.get(edit_key):
                    data = _project_form(row, edit_key)
                    if data:
                        update_row("internship_projects", row["id"], data)
                        log_activity("实习报告", "更新", data["report_name"])
                        st.session_state[edit_key] = False
                        st.rerun()
                else:
                    c1, c2 = st.columns(2)
                    if c1.button("编辑", key=f"edit_project_btn_{row['id']}"):
                        st.session_state[edit_key] = True
                        st.rerun()
                    if c2.button("删除", key=f"delete_project_btn_{row['id']}"):
                        confirm_delete_dialog(
                            "internship_projects", row["id"], row["report_name"], "实习报告"
                        )


def _work_logs(logs, project_names):
    """展示和管理每日工作记录。"""
    view_tab, new_tab = st.tabs(["查看每日记录", "新增每日记录"])
    with new_tab:
        data = _work_log_form(project_names, key="new_work_log")
        if data:
            insert_row("work_logs", data)
            log_activity("每日工作记录", "新增", data["project_name"])
            st.rerun()
    with view_tab:
        if not logs:
            st.info("暂无每日工作记录。")
            return
        for row in logs:
            with st.expander(
                f'{row["log_date"]}　｜　{row["project_name"]}　｜　'
                f'{truncate_text(row["completed_today"], 28)}'
            ):
                st.write(f"**今日完成：** {row['completed_today']}")
                st.write(f"**明日计划：** {row['tomorrow_plan'] or '未填写'}")
                st.write(f"**遇到的问题：** {row['problem'] or '未填写'}")
                edit_key = f"edit_work_log_{row['id']}"
                if st.session_state.get(edit_key):
                    data = _work_log_form(project_names, row, edit_key)
                    if data:
                        update_row("work_logs", row["id"], data)
                        log_activity("每日工作记录", "更新", data["project_name"])
                        st.session_state[edit_key] = False
                        st.rerun()
                else:
                    c1, c2 = st.columns(2)
                    if c1.button("编辑", key=f"edit_worklog_btn_{row['id']}"):
                        st.session_state[edit_key] = True
                        st.rerun()
                    if c2.button("删除", key=f"delete_worklog_btn_{row['id']}"):
                        confirm_delete_dialog(
                            "work_logs", row["id"], row["completed_today"], "每日工作记录"
                        )


def show_internship():
    """展示实习项目、报告与每日工作记录。"""
    page_header("实习与报告", "以项目和报告为主线，记录进度、反馈与每日工作。")
    try:
        projects = fetch_all("internship_projects")
        logs = fetch_all("work_logs")
    except sqlite3.Error as error:
        show_db_error(error)
        return

    _active_cards(projects)
    st.divider()
    _project_records(projects)
    st.divider()
    _work_logs(logs, sorted({row["project_name"] for row in projects}))
    st.divider()
    related_tasks({"实习", "报告"}, "实习", "实习与报告相关事项")
