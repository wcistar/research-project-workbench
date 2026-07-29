from datetime import date
import sqlite3

import pandas as pd
import streamlit as st

from database import fetch_all, get_settings, insert_row, log_activity, update_row
from utils import (
    confirm_delete_dialog,
    page_header,
    safe_date,
    show_db_error,
    text_or_empty,
    truncate_text,
)

TYPES = ["论文章节", "政策整理", "行业报告", "周报", "简历", "面试复盘", "其他"]


def _normalized_type(value):
    """兼容旧版“论文”成果类型。"""
    return "论文章节" if value == "论文" else (value if value in TYPES else "其他")


def _achievement_form(record=None, key="achievement"):
    """显示成果新增或编辑表单。"""
    record = record or {}
    with st.form(f"{key}_form"):
        name = st.text_input("成果名称 *", text_or_empty(record.get("name")))
        c1, c2 = st.columns(2)
        result_type = c1.selectbox(
            "成果类型", TYPES,
            index=TYPES.index(_normalized_type(record.get("type", "论文章节"))),
        )
        project = c2.text_input("所属项目", text_or_empty(record.get("project")))
        completed_date = st.date_input(
            "完成日期", safe_date(record.get("completed_date"), date.today())
        )
        file_link = st.text_input(
            "文件链接或本地路径", text_or_empty(record.get("file_link"))
        )
        description = st.text_area("成果说明", text_or_empty(record.get("description")))
        submitted = st.form_submit_button("保存成果", type="primary")
    if not submitted:
        return None
    if not name.strip():
        st.error("成果名称不能为空。")
        return None
    return {
        "name": name.strip(), "type": result_type, "project": project.strip(),
        "completed_date": str(completed_date), "file_link": file_link.strip(),
        "description": description.strip(),
    }


def _details(records):
    """逐条展示成果详情和操作。"""
    for row in records:
        with st.expander(
            f'{row["name"]}　｜　{_normalized_type(row["type"])}　｜　{row["completed_date"]}'
        ):
            st.write(f"**所属项目：** {row['project'] or '未填写'}")
            st.write(f"**成果说明：** {row['description'] or '未填写'}")
            if row["file_link"]:
                if row["file_link"].startswith(("http://", "https://")):
                    st.link_button("打开成果文件", row["file_link"])
                else:
                    st.write(f"**本地文件路径：** {row['file_link']}")
            else:
                st.caption("未填写成果文件链接或路径")
            edit_key = f"edit_achievement_{row['id']}"
            if st.session_state.get(edit_key):
                data = _achievement_form(row, edit_key)
                if data:
                    update_row("achievements", row["id"], data)
                    log_activity("成果", "更新", data["name"])
                    st.session_state[edit_key] = False
                    st.rerun()
            else:
                c1, c2 = st.columns(2)
                if c1.button("编辑", key=f"edit_achievement_btn_{row['id']}"):
                    st.session_state[edit_key] = True
                    st.rerun()
                if c2.button("删除", key=f"delete_achievement_btn_{row['id']}"):
                    confirm_delete_dialog(
                        "achievements", row["id"], row["name"], "成果"
                    )


def _archive_candidates(thesis_rows, project_rows, achievements, thesis_title):
    """生成已完成但尚未归档的论文与报告成果。"""
    archived = {
        (row["name"].strip(), (row["project"] or "").strip())
        for row in achievements
    }
    candidates = []
    for row in thesis_rows:
        key = (row["module"].strip(), thesis_title.strip())
        if row["stage"] == "已完成" and key not in archived:
            candidates.append({
                "source": "论文模块",
                "name": row["module"],
                "type": "论文章节",
                "project": thesis_title,
                "completed_date": (row["updated_at"] or str(date.today()))[:10],
                "file_link": row["file_link"] or "",
                "description": row["next_action"] or "论文模块已完成。",
            })
    for row in project_rows:
        key = (row["report_name"].strip(), row["project_name"].strip())
        if row["status"] == "已完成" and key not in archived:
            candidates.append({
                "source": "实习报告",
                "name": row["report_name"],
                "type": "行业报告",
                "project": row["project_name"],
                "completed_date": (row["updated_at"] or str(date.today()))[:10],
                "file_link": row["report_path"] or "",
                "description": (
                    f"完成模块：{row['current_module']}"
                    if row["current_module"] else "报告已完成。"
                ),
            })
    return candidates


def _show_archive_candidates(candidates):
    """展示可由用户确认归档的已完成记录。"""
    with st.container(border=True):
        st.subheader("待归档成果")
        st.caption("仅显示已标记为“已完成”、且尚未进入成果归档的论文模块和报告。")
        if not candidates:
            st.info("当前没有新的已完成记录可归档。进行中的内容不会自动计入成果。")
            return
        for index, item in enumerate(candidates):
            row = st.columns([2, 1, 1])
            row[0].markdown(
                f"**{item['name']}**  \n{item['source']} · {item['project']}"
            )
            row[1].write(item["completed_date"])
            if row[2].button("归档此成果", key=f"archive_candidate_{index}"):
                data = {key: item[key] for key in (
                    "name", "type", "project", "completed_date", "file_link", "description"
                )}
                insert_row("achievements", data)
                log_activity("成果", "归档", data["name"])
                st.success(f"“{data['name']}”已加入成果归档。")
                st.rerun()


def show_achievements():
    """展示成果归档的筛选、新增和逐条管理。"""
    page_header("成果归档", "集中保存论文、报告、简历与复盘等已完成材料。")
    try:
        records = fetch_all("achievements")
        thesis_rows = fetch_all("thesis_progress")
        project_rows = fetch_all("internship_projects")
        settings = get_settings()
    except sqlite3.Error as error:
        show_db_error(error)
        return

    frame = pd.DataFrame(records)
    this_month = date.today().strftime("%Y-%m")
    cards = st.columns(4)
    cards[0].metric("成果总数", len(records))
    cards[1].metric(
        "本月完成",
        sum(str(row["completed_date"]).startswith(this_month) for row in records),
    )
    cards[2].metric(
        "论文章节",
        sum(_normalized_type(row["type"]) == "论文章节" for row in records),
    )
    cards[3].metric(
        "报告成果",
        sum(_normalized_type(row["type"]) in {"行业报告", "周报"} for row in records),
    )

    candidates = _archive_candidates(
        thesis_rows, project_rows, records,
        settings.get("thesis_title", "我的硕士论文"),
    )
    st.divider()
    _show_archive_candidates(candidates)
    st.divider()

    view_tab, new_tab = st.tabs(["查看记录", "新增记录"])
    with new_tab:
        data = _achievement_form(key="new_achievement")
        if data:
            try:
                insert_row("achievements", data)
                log_activity("成果", "新增", data["name"])
                st.rerun()
            except sqlite3.Error as error:
                show_db_error(error)
    with view_tab:
        if not records:
            st.info("暂无成果记录，可切换到“新增记录”创建。")
            return
        frame["显示类型"] = frame["type"].map(_normalized_type)
        c1, c2 = st.columns(2)
        selected_types = c1.multiselect("成果类型", TYPES, placeholder="全部类型")
        projects = sorted(value for value in frame["project"].dropna().unique() if value)
        selected_projects = c2.multiselect("所属项目", projects, placeholder="全部项目")
        filtered = frame
        if selected_types:
            filtered = filtered[filtered["显示类型"].isin(selected_types)]
        if selected_projects:
            filtered = filtered[filtered["project"].isin(selected_projects)]
        filtered = filtered.sort_values("completed_date", ascending=False)
        display = filtered[[
            "name", "显示类型", "project", "completed_date", "description"
        ]].copy()
        display["description"] = display["description"].map(lambda value: truncate_text(value, 40))
        st.dataframe(
            display.rename(columns={
                "name": "成果名称", "显示类型": "成果类型", "project": "所属项目",
                "completed_date": "完成日期", "description": "成果说明",
            }),
            hide_index=True, width="stretch",
        )
        filtered_ids = set(filtered["id"].tolist())
        _details([row for row in records if row["id"] in filtered_ids])
