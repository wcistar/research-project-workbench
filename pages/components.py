from datetime import date
import sqlite3

import pandas as pd
import streamlit as st

from database import fetch_all, insert_row, log_activity, update_row
from utils import (
    confirm_delete_dialog,
    due_hint,
    safe_date,
    show_db_error,
    text_or_empty,
    truncate_text,
)

PRIORITIES = ["高", "中", "低"]
TASK_STATUSES = ["未开始", "进行中", "已完成", "暂停"]


def _task_form(category, record=None, key="task"):
    """显示页面内的相关事项表单。"""
    record = record or {}
    with st.form(f"{key}_form"):
        name = st.text_input("事项名称 *", text_or_empty(record.get("name")))
        c1, c2 = st.columns(2)
        priority = c1.selectbox(
            "优先级", PRIORITIES,
            index=PRIORITIES.index(record.get("priority", "中")),
        )
        status = c2.selectbox(
            "状态", TASK_STATUSES,
            index=TASK_STATUSES.index(record.get("status", "未开始")),
        )
        has_due = st.checkbox("设置截止日期", value=bool(record.get("due_date")))
        due_date = st.date_input(
            "截止日期", safe_date(record.get("due_date"), date.today())
        ) if has_due else None
        next_action = st.text_input("下一步行动", text_or_empty(record.get("next_action")))
        notes = st.text_area("备注", text_or_empty(record.get("notes")))
        submitted = st.form_submit_button("保存事项", type="primary")
    if not submitted:
        return None
    if not name.strip():
        st.error("事项名称不能为空。")
        return None
    return {
        "name": name.strip(), "category": category, "priority": priority,
        "status": status, "created_date": record.get("created_date") or str(date.today()),
        "due_date": str(due_date) if due_date else None,
        "next_action": next_action.strip(), "completion": record.get("completion", ""),
        "result_link": record.get("result_link", ""), "notes": notes.strip(),
    }


def related_tasks(categories, new_category, title="相关事项"):
    """在业务页面内管理原有通用任务。"""
    st.subheader(title)
    st.caption("保留原任务数据，并按业务类型放到对应页面。")
    try:
        rows = [row for row in fetch_all("tasks") if row["category"] in categories]
    except sqlite3.Error as error:
        show_db_error(error)
        return

    view_tab, new_tab = st.tabs(["查看事项", "新增事项"])
    with new_tab:
        data = _task_form(new_category, key=f"new_{new_category}")
        if data:
            try:
                insert_row("tasks", data)
                log_activity("事项", "新增", data["name"])
                st.success("事项已保存。")
                st.rerun()
            except sqlite3.Error as error:
                show_db_error(error)

    with view_tab:
        if not rows:
            st.info("暂无相关事项，可切换到“新增事项”创建。")
            return
        for row in rows:
            completed = row["status"] == "已完成"
            hint = due_hint(row["due_date"], completed)
            label = f'{row["name"]}　｜　{row["status"]}'
            if hint:
                label += f"　｜　{hint}"
            with st.expander(label):
                st.write(f"**下一步行动：** {truncate_text(row['next_action'], 80) or '未填写'}")
                st.write(f"**截止日期：** {row['due_date'] or '未设置'}")
                edit_key = f"edit_task_{row['id']}"
                if st.session_state.get(edit_key):
                    data = _task_form(row["category"], row, key=edit_key)
                    if data:
                        update_row("tasks", row["id"], data)
                        log_activity("事项", "更新", data["name"])
                        st.session_state[edit_key] = False
                        st.rerun()
                else:
                    left, right = st.columns([1, 1])
                    if left.button("编辑", key=f"task_edit_{row['id']}"):
                        st.session_state[edit_key] = True
                        st.rerun()
                    if right.button("删除", key=f"task_delete_{row['id']}"):
                        confirm_delete_dialog("tasks", row["id"], row["name"], "事项")
