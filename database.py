import os
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

DB_DIR = Path(__file__).resolve().parent / "data"
DEMO_DB_PATH = DB_DIR / "demo.db"
LOCAL_DB_PATH = DB_DIR / "local_data.db"
LEGACY_DB_PATH = DB_DIR / "workbench.db"
RUNTIME_DEMO_DB_PATH = Path(tempfile.gettempdir()) / "research_workbench_demo.db"
DB_PATH = DEMO_DB_PATH

TABLES = {
    "tasks",
    "applications",
    "achievements",
    "app_settings",
    "thesis_progress",
    "thesis_logs",
    "internship_projects",
    "work_logs",
    "activity_log",
}


@contextmanager
def get_connection():
    """创建数据库连接，并在结束时提交或回滚。"""
    DB_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()


def _column_names(conn, table):
    """读取数据表已有字段名称。"""
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_column_if_missing(conn, table, definition):
    """仅在字段不存在时使用 ALTER TABLE 安全追加字段。"""
    column = definition.split()[0]
    if column not in _column_names(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _now():
    """返回适合数据库保存的当前时间。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def configure_database(mode):
    """按演示或个人模式切换数据库文件。"""
    global DB_PATH
    if mode == "demo":
        # 公开云端的仓库目录可能只读，先复制演示库到临时可写目录。
        demo_only = os.getenv("WORKBENCH_DEMO_ONLY", "").strip().lower()
        if demo_only in {"1", "true", "yes", "on"}:
            if not RUNTIME_DEMO_DB_PATH.exists() and DEMO_DB_PATH.exists():
                shutil.copy2(DEMO_DB_PATH, RUNTIME_DEMO_DB_PATH)
            DB_PATH = RUNTIME_DEMO_DB_PATH
        else:
            DB_PATH = DEMO_DB_PATH
    elif mode == "personal":
        DB_PATH = LOCAL_DB_PATH
    else:
        raise ValueError("未知的数据模式")
    return DB_PATH


def current_database_path():
    """返回当前模式使用的数据库路径。"""
    return DB_PATH


def _seed_demo_data(conn):
    """写入完全虚构且不含本地路径的公开演示数据。"""
    today = date.today()
    conn.executemany(
        """INSERT INTO applications
        (company, position, city, job_type, channel, applied_date, due_date,
         status, jd_link, next_action, notes, resume_version, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                "示例科技公司A", "行业研究岗", "示例城市", "研究类", "校园招聘",
                str(today - timedelta(days=5)), None, "已投递", "", "等待后续通知",
                "完全虚构的演示数据", "演示版简历", _now(),
            ),
            (
                "某产业咨询公司", "研究助理", "示例城市", "咨询研究", "校园招聘",
                str(today - timedelta(days=8)), None, "笔试", "", "准备笔试",
                "完全虚构的演示数据", "演示版简历", _now(),
            ),
            (
                "示例国企集团", "战略规划岗", "示例城市", "战略规划", "校园招聘",
                str(today - timedelta(days=12)), None, "一面", "", "准备一面",
                "完全虚构的演示数据", "演示版简历", _now(),
            ),
        ],
    )
    conn.execute(
        """INSERT INTO thesis_progress
        (module, stage, progress, next_action, due_date, current_problem,
         file_link, updated_at, source_task_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "机制分析章节", "写作中", 60, "完善机制假说与论证",
            str(today + timedelta(days=10)), "需要进一步梳理文献逻辑",
            "", _now(), None,
        ),
    )
    conn.execute(
        """INSERT INTO internship_projects
        (project_name, report_name, current_module, status, progress,
         due_date, next_action, source_link, report_path, mentor_feedback,
         updated_at, source_task_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "示例产业研究项目", "人工智能产业研究报告", "瓶颈分析模块",
            "撰写中", 50, str(today + timedelta(days=7)), "补充案例并完善结构",
            "", "", "演示反馈：结构清晰，可继续补充证据。", _now(), None,
        ),
    )
    conn.execute(
        """INSERT INTO achievements
        (name, type, project, completed_date, file_link, description)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (
            "公开资料整理样表", "政策整理", "示例产业研究项目",
            str(today - timedelta(days=3)), "", "完全虚构的演示成果。",
        ),
    )
    conn.executemany(
        """INSERT INTO activity_log
        (entity_type, action, title, updated_at) VALUES (?, ?, ?, ?)""",
        [
            ("论文进度", "更新", "机制分析章节", _now()),
            ("实习报告", "更新", "人工智能产业研究报告", _now()),
            ("秋招投递", "更新", "示例国企集团｜战略规划岗", _now()),
        ],
    )
    demo_settings = {
        "thesis_title": "新兴市场外债问题研究",
        "thesis_stage": "写作中",
        "thesis_progress": "60",
        "thesis_updated_at": str(today),
        "thesis_next_milestone": "完成机制分析章节初稿",
        "weekly_application_target": "5",
        "ia_refactor_migrated": "1",
    }
    conn.executemany(
        """INSERT INTO app_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
        demo_settings.items(),
    )


def init_db():
    """创建及迁移数据库；保留旧表和已有数据。"""
    is_new_database = not DB_PATH.exists()
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                priority TEXT NOT NULL,
                status TEXT NOT NULL,
                created_date TEXT NOT NULL,
                due_date TEXT,
                next_action TEXT,
                completion TEXT,
                result_link TEXT,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                position TEXT NOT NULL,
                city TEXT,
                job_type TEXT,
                channel TEXT,
                applied_date TEXT,
                due_date TEXT,
                status TEXT NOT NULL,
                jd_link TEXT,
                next_action TEXT,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                project TEXT,
                completed_date TEXT NOT NULL,
                file_link TEXT,
                description TEXT
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS thesis_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module TEXT NOT NULL,
                stage TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),
                next_action TEXT,
                due_date TEXT,
                current_problem TEXT,
                file_link TEXT,
                updated_at TEXT NOT NULL,
                source_task_id INTEGER UNIQUE
            );

            CREATE TABLE IF NOT EXISTS thesis_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_date TEXT NOT NULL,
                completed_today TEXT NOT NULL,
                problem TEXT,
                next_action TEXT
            );

            CREATE TABLE IF NOT EXISTS internship_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                report_name TEXT NOT NULL,
                current_module TEXT,
                status TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),
                due_date TEXT,
                next_action TEXT,
                source_link TEXT,
                report_path TEXT,
                mentor_feedback TEXT,
                updated_at TEXT NOT NULL,
                source_task_id INTEGER UNIQUE
            );

            CREATE TABLE IF NOT EXISTS work_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_date TEXT NOT NULL,
                project_name TEXT NOT NULL,
                completed_today TEXT NOT NULL,
                tomorrow_plan TEXT,
                problem TEXT
            );

            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                action TEXT NOT NULL,
                title TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        _add_column_if_missing(conn, "applications", "resume_version TEXT")
        _add_column_if_missing(conn, "applications", "updated_at TEXT")
        conn.execute(
            "UPDATE applications SET updated_at = COALESCE(updated_at, applied_date, ?)",
            (_now(),),
        )

        defaults = {
            "thesis_title": "我的硕士论文",
            "thesis_stage": "资料搜集",
            "thesis_progress": "0",
            "thesis_updated_at": str(date.today()),
            "thesis_next_milestone": "",
            "weekly_application_target": "5",
        }
        conn.executemany(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
            defaults.items(),
        )

        # 旧任务只迁移一次；删除迁移后的记录时不会在下次启动重新出现。
        migration_done = conn.execute(
            "SELECT 1 FROM app_settings WHERE key = 'ia_refactor_migrated'"
        ).fetchone()
        if not migration_done:
            status_to_thesis = {
                "未开始": "未开始", "进行中": "写作中",
                "已完成": "已完成", "暂停": "待修改",
            }
            status_to_internship = {
                "未开始": "未开始", "进行中": "撰写中",
                "已完成": "已完成", "暂停": "暂停",
            }
            for task in conn.execute("SELECT * FROM tasks ORDER BY id"):
                progress = (
                    100 if task["status"] == "已完成"
                    else (40 if task["status"] == "进行中" else 0)
                )
                if task["category"] == "论文":
                    conn.execute(
                        """INSERT OR IGNORE INTO thesis_progress
                        (module, stage, progress, next_action, due_date, current_problem,
                         file_link, updated_at, source_task_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            task["name"], status_to_thesis.get(task["status"], "未开始"),
                            progress, task["next_action"], task["due_date"], task["notes"],
                            task["result_link"], task["created_date"], task["id"],
                        ),
                    )
                elif task["category"] in {"实习", "报告"}:
                    conn.execute(
                        """INSERT OR IGNORE INTO internship_projects
                        (project_name, report_name, current_module, status, progress,
                         due_date, next_action, source_link, report_path, mentor_feedback,
                         updated_at, source_task_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            task["category"], task["name"], task["completion"],
                            status_to_internship.get(task["status"], "未开始"), progress,
                            task["due_date"], task["next_action"], "", task["result_link"],
                            task["notes"], task["created_date"], task["id"],
                        ),
                    )
            conn.execute(
                "INSERT INTO app_settings (key, value) VALUES ('ia_refactor_migrated', '1')"
            )

        if is_new_database and DB_PATH == DEMO_DB_PATH:
            _seed_demo_data(conn)


def fetch_all(table):
    """读取白名单数据表的全部记录。"""
    if table not in TABLES:
        raise ValueError("不允许访问的数据表")
    order = "updated_at DESC, id DESC" if table in {
        "activity_log", "thesis_progress", "internship_projects"
    } else "id DESC"
    with get_connection() as conn:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY {order}")]


def insert_row(table, data):
    """新增记录并返回编号。"""
    if table not in TABLES:
        raise ValueError("不允许访问的数据表")
    columns = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    with get_connection() as conn:
        cursor = conn.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
            tuple(data.values()),
        )
        return cursor.lastrowid


def update_row(table, row_id, data):
    """按编号更新记录。"""
    if table not in TABLES:
        raise ValueError("不允许访问的数据表")
    assignments = ", ".join(f"{column} = ?" for column in data)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE {table} SET {assignments} WHERE id = ?",
            (*data.values(), row_id),
        )


def delete_row(table, row_id):
    """按编号删除记录。"""
    if table not in TABLES:
        raise ValueError("不允许访问的数据表")
    with get_connection() as conn:
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))


def get_settings():
    """读取全部工作台设置。"""
    with get_connection() as conn:
        return {row["key"]: row["value"] for row in conn.execute("SELECT * FROM app_settings")}


def save_settings(values):
    """保存工作台设置，不影响其他配置。"""
    with get_connection() as conn:
        conn.executemany(
            """INSERT INTO app_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            values.items(),
        )


def log_activity(entity_type, action, title):
    """写入一条最近更新记录。"""
    insert_row(
        "activity_log",
        {"entity_type": entity_type, "action": action, "title": title, "updated_at": _now()},
    )
