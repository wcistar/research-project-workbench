from datetime import date, datetime
import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st

from database import fetch_all, insert_row, log_activity, update_row
from pages.components import related_tasks
from utils import (
    confirm_delete_dialog,
    page_header,
    safe_date,
    show_db_error,
    text_or_empty,
    to_dataframe,
    truncate_text,
)

STATUSES = ["待投递", "已投递", "测评", "笔试", "一面", "二面", "终面", "Offer", "拒绝", "主动放弃"]


def _timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _normalized_status(value):
    """兼容旧版投递状态名称。"""
    mapping = {"收藏": "待投递", "录用": "Offer"}
    return mapping.get(value, value if value in STATUSES else "待投递")


def calculate_application_metrics(df):
    """计算页面顶部投递状态指标。"""
    if df.empty:
        return {"pending": 0, "submitted": 0, "written": 0, "interview": 0, "offer": 0}
    status = df["status"].replace({"收藏": "待投递", "录用": "Offer"})
    return {
        "pending": int((status == "待投递").sum()),
        "submitted": int((status == "已投递").sum()),
        "written": int((status == "笔试").sum()),
        "interview": int(status.isin(["一面", "二面", "终面"]).sum()),
        "offer": int((status == "Offer").sum()),
    }


def _funnel_values(df):
    """按当前状态近似汇总招聘进度漏斗。"""
    if df.empty:
        return [0, 0, 0, 0]
    status = df["status"].replace({"收藏": "待投递", "录用": "Offer"})
    submitted = int((~status.isin(["待投递", "主动放弃"])).sum())
    written = int(status.isin(["笔试", "一面", "二面", "终面", "Offer"]).sum())
    interview = int(status.isin(["一面", "二面", "终面", "Offer"]).sum())
    offer = int((status == "Offer").sum())
    return [submitted, written, interview, offer]


def _application_form(record=None, key="application"):
    """显示投递记录表单并处理可空日期和链接。"""
    record = record or {}
    with st.form(f"{key}_form"):
        c1, c2 = st.columns(2)
        company = c1.text_input("公司名称 *", text_or_empty(record.get("company")))
        position = c2.text_input("岗位名称 *", text_or_empty(record.get("position")))
        c3, c4 = st.columns(2)
        job_type = c3.text_input("岗位类型", text_or_empty(record.get("job_type")))
        city = c4.text_input("城市", text_or_empty(record.get("city")))
        channel = st.text_input("招聘渠道", text_or_empty(record.get("channel")))
        jd_link = st.text_input("JD 网页链接", text_or_empty(record.get("jd_link")))
        dates = st.columns(2)
        has_applied = dates[0].checkbox(
            "设置投递日期", value=bool(record.get("applied_date")), key=f"{key}_applied"
        )
        has_due = dates[1].checkbox(
            "设置截止日期", value=bool(record.get("due_date")), key=f"{key}_due"
        )
        applied_date = st.date_input(
            "投递日期", safe_date(record.get("applied_date"), date.today()),
            key=f"{key}_applied_date",
        ) if has_applied else None
        due_date = st.date_input(
            "截止日期", safe_date(record.get("due_date"), date.today()),
            key=f"{key}_due_date",
        ) if has_due else None
        status = st.selectbox(
            "当前状态", STATUSES,
            index=STATUSES.index(_normalized_status(record.get("status", "待投递"))),
        )
        next_action = st.text_input("下一步行动", text_or_empty(record.get("next_action")))
        resume_version = st.text_input("使用的简历版本", text_or_empty(record.get("resume_version")))
        notes = st.text_area("备注", text_or_empty(record.get("notes")))
        submitted = st.form_submit_button("保存投递记录", type="primary")
    if not submitted:
        return None
    if not company.strip() or not position.strip():
        st.error("公司名称和岗位名称不能为空。")
        return None
    if applied_date and due_date and due_date < applied_date:
        st.error("截止日期不能早于投递日期。")
        return None
    return {
        "company": company.strip(), "position": position.strip(),
        "job_type": job_type.strip(), "city": city.strip(), "channel": channel.strip(),
        "jd_link": jd_link.strip(), "applied_date": str(applied_date) if applied_date else None,
        "due_date": str(due_date) if due_date else None, "status": status,
        "next_action": next_action.strip(), "resume_version": resume_version.strip(),
        "updated_at": _timestamp(), "notes": notes.strip(),
    }


def _record_details(rows):
    """逐条显示完整投递信息和编辑删除操作。"""
    if not rows:
        st.info("没有符合当前筛选条件的投递记录。")
        return
    for row in rows:
        with st.expander(
            f'{row["company"]}　｜　{row["position"]}　｜　{_normalized_status(row["status"])}'
        ):
            c1, c2 = st.columns(2)
            c1.write(f"**岗位类型：** {row['job_type'] or '未填写'}")
            c1.write(f"**城市：** {row['city'] or '未填写'}")
            c1.write(f"**招聘渠道：** {row['channel'] or '未填写'}")
            c1.write(f"**简历版本：** {row.get('resume_version') or '未填写'}")
            c2.write(f"**投递日期：** {row['applied_date'] or '未设置'}")
            c2.write(f"**截止日期：** {row['due_date'] or '未设置'}")
            c2.write(f"**下一步行动：** {row['next_action'] or '未填写'}")
            c2.write(f"**最近更新时间：** {row.get('updated_at') or '未记录'}")
            st.write(f"**备注：** {row['notes'] or '未填写'}")
            if row["jd_link"]:
                st.link_button("查看 JD", row["jd_link"])
            else:
                st.caption("未填写 JD 链接")
            edit_key = f"edit_application_{row['id']}"
            if st.session_state.get(edit_key):
                data = _application_form(row, edit_key)
                if data:
                    update_row("applications", row["id"], data)
                    log_activity("秋招投递", "更新", f"{data['company']}｜{data['position']}")
                    st.session_state[edit_key] = False
                    st.rerun()
            else:
                b1, b2 = st.columns(2)
                if b1.button("编辑", key=f"edit_app_btn_{row['id']}"):
                    st.session_state[edit_key] = True
                    st.rerun()
                if b2.button("删除", key=f"delete_app_btn_{row['id']}"):
                    confirm_delete_dialog(
                        "applications", row["id"],
                        f'{row["company"]}｜{row["position"]}', "秋招投递",
                    )


def show_applications():
    """展示秋招统计、漏斗、筛选和投递记录管理。"""
    page_header("秋招投递", "追踪目标岗位、投递节点与下一步行动。")
    try:
        records = fetch_all("applications")
    except sqlite3.Error as error:
        show_db_error(error)
        return

    df = to_dataframe(records)
    metrics = calculate_application_metrics(df)
    cards = st.columns(5)
    for column, label, key in zip(
        cards,
        ["待投递", "已投递", "笔试", "面试", "Offer"],
        ["pending", "submitted", "written", "interview", "offer"],
    ):
        column.metric(label, metrics[key])

    if not df.empty:
        funnel = pd.DataFrame({
            "阶段": ["已投递", "笔试", "面试", "Offer"],
            "数量": _funnel_values(df),
        })
        if funnel["数量"].sum() > 0:
            with st.container(border=True):
                st.subheader("招聘进度漏斗")
                figure = px.funnel(
                    funnel, x="数量", y="阶段",
                    color_discrete_sequence=["#6F8F74"],
                )
                figure.update_layout(height=280, margin=dict(l=20, r=20, t=10, b=10))
                st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})

    st.divider()
    view_tab, new_tab = st.tabs(["查看记录", "新增记录"])
    with new_tab:
        data = _application_form(key="new_application")
        if data:
            try:
                insert_row("applications", data)
                log_activity("秋招投递", "新增", f"{data['company']}｜{data['position']}")
                st.rerun()
            except sqlite3.Error as error:
                show_db_error(error)
    with view_tab:
        if df.empty:
            st.info("暂无投递记录，可切换到“新增记录”创建。")
        else:
            filters = st.columns(4)
            selected_status = filters[0].multiselect("状态", STATUSES, placeholder="全部状态")
            cities = sorted(value for value in df["city"].dropna().unique() if value)
            types = sorted(value for value in df["job_type"].dropna().unique() if value)
            selected_city = filters[1].multiselect("城市", cities, placeholder="全部城市")
            selected_type = filters[2].multiselect(
                "岗位类型", types, placeholder="全部岗位类型"
            )
            keyword = filters[3].text_input("公司关键词")
            filtered = df.copy()
            normalized = filtered["status"].map(_normalized_status)
            if selected_status:
                filtered = filtered[normalized.isin(selected_status)]
            if selected_city:
                filtered = filtered[filtered["city"].isin(selected_city)]
            if selected_type:
                filtered = filtered[filtered["job_type"].isin(selected_type)]
            if keyword.strip():
                filtered = filtered[
                    filtered["company"].str.contains(keyword.strip(), case=False, na=False)
                ]
            display = filtered[[
                "company", "position", "city", "applied_date", "status", "next_action"
            ]].copy()
            display["status"] = display["status"].map(_normalized_status)
            display["next_action"] = display["next_action"].map(lambda value: truncate_text(value, 30))
            st.dataframe(
                display.rename(columns={
                    "company": "公司", "position": "岗位", "city": "城市",
                    "applied_date": "投递日期", "status": "当前状态",
                    "next_action": "下一步行动",
                }),
                hide_index=True, width="stretch",
            )
            st.caption("点击下方记录可查看完整信息、JD、编辑或删除。")
            filtered_ids = set(filtered["id"].tolist())
            _record_details([row for row in records if row["id"] in filtered_ids])

    st.divider()
    related_tasks({"秋招"}, "秋招", "秋招相关事项")
