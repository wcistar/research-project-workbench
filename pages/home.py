from datetime import date
import sqlite3

import pandas as pd
import streamlit as st

from database import fetch_all, get_settings
from utils import due_hint, page_header, progress_bar, show_db_error, to_dataframe, truncate_text


def calculate_overview_metrics(
    tasks, applications, settings, thesis=None, internships=None, current_date=None
):
    """计算总览顶部四项指标。"""
    today = pd.Timestamp(current_date or date.today())
    migrated_task_ids = {
        row.get("source_task_id")
        for row in (thesis or []) + (internships or [])
        if row.get("source_task_id") is not None
    }
    deadline_items = []
    for row in tasks:
        if row.get("id") in migrated_task_ids:
            continue
        deadline_items.append({
            "due_date": row.get("due_date"),
            "completed": row.get("status") == "已完成",
        })
    for row in thesis or []:
        deadline_items.append({
            "due_date": row.get("due_date"),
            "completed": row.get("stage") == "已完成",
        })
    for row in internships or []:
        deadline_items.append({
            "due_date": row.get("due_date"),
            "completed": row.get("status") == "已完成",
        })
    for row in applications:
        deadline_items.append({
            "due_date": row.get("due_date"),
            "completed": row.get("status") in {"Offer", "录用", "拒绝", "主动放弃"},
        })
    task_df = to_dataframe(deadline_items)
    app_df = to_dataframe(applications)
    if task_df.empty:
        today_count = future_count = 0
    else:
        due = pd.to_datetime(task_df["due_date"], errors="coerce")
        active = ~task_df["completed"]
        today_count = int(((due == today) & active).sum())
        future_count = int(((due >= today) & (due <= today + pd.Timedelta(days=7)) & active).sum())
    if app_df.empty:
        applied_count = 0
    else:
        applied_count = int((~app_df["status"].isin(["待投递", "收藏"])).sum())
    return {
        "today": today_count,
        "next_7_days": future_count,
        "thesis_progress": int(settings.get("thesis_progress", 0) or 0),
        "applications_submitted": applied_count,
    }


def _collect_focus(tasks, thesis, internships, applications):
    """汇总本周重点和即将截止事项。"""
    migrated_task_ids = {
        row.get("source_task_id")
        for row in thesis + internships
        if row.get("source_task_id") is not None
    }
    items = []
    for row in tasks:
        if row.get("id") in migrated_task_ids:
            continue
        items.append({
            "事项": row["name"], "类型": row["category"],
            "截止日期": row["due_date"], "状态": row["status"],
            "完成": row["status"] == "已完成",
        })
    for row in thesis:
        items.append({
            "事项": row["module"], "类型": "论文",
            "截止日期": row["due_date"], "状态": row["stage"],
            "完成": row["stage"] == "已完成",
        })
    for row in internships:
        items.append({
            "事项": row["report_name"], "类型": "实习/报告",
            "截止日期": row["due_date"], "状态": row["status"],
            "完成": row["status"] == "已完成",
        })
    for row in applications:
        items.append({
            "事项": f'{row["company"]}｜{row["position"]}', "类型": "秋招",
            "截止日期": row["due_date"], "状态": row["status"],
            "完成": row["status"] in {"Offer", "录用", "拒绝", "主动放弃"},
        })
    if not items:
        return pd.DataFrame()
    frame = pd.DataFrame(items)
    frame["_due"] = pd.to_datetime(frame["截止日期"], errors="coerce")
    return frame.sort_values("_due", na_position="last")


def show_home():
    """展示跨页面汇总、重点事项与最近记录。"""
    page_header("总览", "集中查看论文、实习报告、秋招与成果的近期进展。")
    try:
        tasks = fetch_all("tasks")
        applications = fetch_all("applications")
        thesis = fetch_all("thesis_progress")
        internships = fetch_all("internship_projects")
        achievements = fetch_all("achievements")
        activities = fetch_all("activity_log")
        settings = get_settings()
    except sqlite3.Error as error:
        show_db_error(error)
        return

    metrics = calculate_overview_metrics(
        tasks, applications, settings, thesis=thesis, internships=internships
    )
    cards = st.columns(4)
    labels = ["今日待办", "未来7天截止", "论文总体进度", "秋招已投递"]
    values = [
        metrics["today"], metrics["next_7_days"],
        f'{metrics["thesis_progress"]}%', metrics["applications_submitted"],
    ]
    for column, label, value in zip(cards, labels, values):
        column.metric(label, value)

    focus = _collect_focus(tasks, thesis, internships, applications)
    st.divider()
    left, right = st.columns([1.35, 1], gap="large")
    with left:
        with st.container(border=True):
            st.subheader("本周重点")
            today = pd.Timestamp(date.today())
            week_end = today + pd.Timedelta(days=7)
            if focus.empty:
                st.info("暂无重点事项。")
            else:
                weekly = focus[
                    (focus["_due"] >= today) & (focus["_due"] <= week_end) & (~focus["完成"])
                ].head(7)
                if weekly.empty:
                    st.info("未来 7 天暂无截止事项。")
                else:
                    st.dataframe(
                        weekly[["事项", "类型", "截止日期", "状态"]],
                        hide_index=True, width="stretch",
                    )
    with right:
        with st.container(border=True):
            st.subheader("项目进度")
            progress_bar("硕士论文", settings.get("thesis_progress", 0))
            active_internships = [row for row in internships if row["status"] not in {"已完成", "暂停"}]
            internship_progress = (
                round(sum(row["progress"] for row in active_internships) / len(active_internships))
                if active_internships else 0
            )
            progress_bar("当前实习报告", internship_progress)
            target = max(1, int(settings.get("weekly_application_target", 5) or 5))
            app_df = to_dataframe(applications)
            submitted_this_week = 0
            if not app_df.empty:
                applied = pd.to_datetime(app_df["applied_date"], errors="coerce")
                monday = pd.Timestamp(date.today()) - pd.Timedelta(days=date.today().weekday())
                submitted_this_week = int(
                    ((applied >= monday) & (applied <= monday + pd.Timedelta(days=6))).sum()
                )
            progress_bar("本周秋招投递目标", min(100, round(submitted_this_week / target * 100)))

    st.divider()
    bottom = st.columns(3, gap="large")
    with bottom[0]:
        st.subheader("即将截止事项")
        if focus.empty:
            st.info("暂无截止事项。")
        else:
            upcoming = focus[(~focus["完成"]) & focus["_due"].notna()].head(6)
            if upcoming.empty:
                st.info("暂无截止事项。")
            else:
                for _, row in upcoming.iterrows():
                    hint = due_hint(row["截止日期"])
                    st.markdown(f"**{truncate_text(row['事项'], 26)}**  \n{row['截止日期']}　{hint}")
    with bottom[1]:
        st.subheader("最近更新记录")
        if not activities:
            st.info("暂无更新记录。")
        else:
            for row in activities[:6]:
                st.markdown(
                    f"**{row['entity_type']} · {row['action']}**  \n"
                    f"{truncate_text(row['title'], 28)}　`{row['updated_at']}`"
                )
    with bottom[2]:
        st.subheader("最近完成的成果")
        if not achievements:
            st.info("暂无成果记录。")
        else:
            for row in sorted(achievements, key=lambda item: item["completed_date"], reverse=True)[:5]:
                st.markdown(
                    f"**{truncate_text(row['name'], 28)}**  \n"
                    f"{row['type']}　`{row['completed_date']}`"
                )
