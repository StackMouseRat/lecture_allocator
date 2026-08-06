# 统一查询入口（query.py）· 命令行规范 v1.0

> 外界访问系统数据的**唯一通道**（只读）。禁止绕过本入口直接读 db / data 文件。
> 实现：`query.py`（复用 `render_utils` / `virtual_time` 权威口径，无重复实现）

---

## 一、调用方式

```bash
python3 query.py <子命令> [选项]
python3 query.py help            # 查看全部命令与设计说明
```

## 二、子命令一览

| 子命令 | 功能 | 必填参数 |
|---|---|---|
| `timetable` | 查询学期课表（渲染层：课程/老师/地点/周次） | `--sem` |
| `course` | 查询课程信息（培养方案/老师/排课位置/授课方案） | `--name` |
| `syllabus` | 查询授课进度（逐节内容） | `--sem` |
| `now` | 虚拟时间当前在上的课（可选指定时刻） | — |
| `teacher` | 查询老师的授课课程与时间 | `--id` |
| `room` | 查询教室占用情况 | `--name` |
| `check` | 全量校验汇总（复用 check_* 脚本） | — |
| `summary` | 学期总览（门数/学分/课次/事件） | — |
| `progress` | 课程进度（某虚拟时间下 已学/当前/未学 清单） | `--course` |
| `girl` | 女孩档案（专业/体育/选修/个人调度/课表文件） | `--girl` |

## 三、通用参数

| 参数 | 取值 | 说明 |
|---|---|---|
| `--sem N` | 1-6 | 学期号（1=2022-23-1 … 6=2024-25-2） |
| `--girl X` | surrey/orage/sakawa/taiyuan | 女孩（默认 surrey） |
| `--week N` | 1-16 | 教学周过滤 |
| `--name X` | 课程名/教室名 | 渲染名（如"电机学（下）"、"复临舍202(中)"） |
| `--id X` | 老师ID | 如 T800 / E1100 / P19a |
| `--course X` | 课程名 | syllabus 单门过滤 |
| `--at "YYYY-MM-DD HH:MM"` | 时间 | `now`/`progress` 指定时刻（**只读，不污染虚拟时钟**） |
| `--json` | — | 输出结构化 JSON（供程序消费） |

## 四、输出规范

### 4.1 文本模式（默认）
- 人类可读：标题行 `# …`、Markdown 表格或 `键: 值` 行
- 课表与渲染层一致：课程=人设名、含老师/地点（与 `girl_schedules/*.md` 同口径）
- `progress` 状态行：在课=`🕐 正在上课【topic】`；非在课=`📍已学到: W周·次 topic`；未开课=`未在课上（尚未开课）`
- 未找到：stderr 提示 + 退出码 2

### 4.2 JSON 模式（`--json`）
- `json.dumps(ensure_ascii=False, indent=1)`，UTF-8
- 各子命令顶层结构：
  - `timetable`: `{semester, girl, term, cells: {"周几,槽位": [{course,weeks,teacher,location,type}]}}`
  - `course`: `{course, plan, teachers, schedules: {sem: [行]}, syllabus: {sem: {节数,每次学时}}}`
  - `syllabus`: `{课程: {rows: [{week,session,topic}], hps}}`
  - `now`: `VirtualClock.current_course` 原样返回（status/course/teacher/location/syllabus 等）
  - `teacher`: `{teacher, courses: {课: [女孩]}, schedules: {sem: [行]}}`
  - `room`: `{room, occupancy: {sem: [行]}}`
  - `check`: `{conflicts, render, locations, syllabus, data}`（末行结果串）
  - `summary`: `{sem: {门数, 学分, 课次行数, 事件}}`
  - `progress`: `{course, girl, semester, week, time, on_course, total,
                 position, learned: [rows], current: [rows], pending: [rows]}`
    - rows = `{week, session, topic}`；`position` = 当前进度锚点（已学到的最新一节，同 rows 格式；尚未开课为 `null`）
  - `girl`: `{girl, name, major, pe, electives, personal, schedules}`

## 五、退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 2 | 未找到（课程/教室无记录） |
| 3 | 数据异常（学期无数据/查询内部错误） |
| 4 | 参数错误（未知子命令/缺必填参数/非法取值） |

## 六、数据口径（与权威源一致）

| 数据 | 来源 |
|---|---|
| 课表行（S1-3/6） | `virtual_course_schedule` 共享行 + `render_utils.resolve` 渲染（选修/体育/四史按人设映射） |
| 课表行（S4/5） | `girl_course_schedule` per-girl（老师/地点已入库） |
| 授课进度 | `data/syllabus_semN.json`（`render_utils.syllabus_topic` 同口径） |
| 虚拟时间 | `virtual_time.VirtualClock.current_course`（`--at` 传 dt，不 set 不污染） |
| 课程进度（已学/当前/未学） | 当前节=`current_course.syllabus`（权威锚点）；已学/未学=按该课 syllabus 行序（week×session 时间线）相对当前时刻分割；非在课时按 db 行 `(week, weekday, slot)` 定位；`position`=已学清单末行（进度锚点，未开课为 null） |
| 老师/地点 | `data/teachers.json` + `data/locations_semN.json` |
| 学分（S1-3/6） | `virtual_course_schedule.credits`（build 权威，占位符含映射学分） |
| 学分（S4/5） | `data/plan_courses.json`（培养方案；实验课按独立课程计 1 学分；体育/形势/四史不在 plan 计 0） |
| 事件 | `semester_events`（slot_index=0 哨兵事件不占格，如线上劳动教育/集中综合设计） |

> ⚠️ 学分口径说明：S4/5 取培养方案，与课表渲染口径（实践学时并入理论课）存在合理差异
> （如 S5 plan=26.0 vs 课表=22.25、S4 plan=18.0 vs 课表=22.25）；S6=19.25 两口径一致。
> 学分权威基线见 `docs/进展记录.md` 五。

## 七、示例

```bash
python3 query.py timetable --sem 6 --girl surrey          # S6 萨里完整课表
python3 query.py timetable --sem 5 --week 3 --json        # S5 第3周 JSON
python3 query.py course --name 电机学（下）               # 课程信息
python3 query.py syllabus --sem 6 --course 电力系统过电压 --week 16
python3 query.py now --girl orage                          # 当前虚拟时刻在上的课
python3 query.py now --at "2025-03-14 16:15" --json        # 指定时刻（只读）
python3 query.py teacher --id T800                          # 老师课程
python3 query.py room --name "复临舍202(中)"                # 教室占用
python3 query.py check                                      # 全量校验
python3 query.py summary --sem 6                            # 学期总览
python3 query.py girl --girl sakawa                         # 女孩档案
python3 query.py progress --course 电力系统分析 --at "2025-03-14 14:35"
python3 query.py progress --course 传感与检测技术 --girl surrey   # 当前虚拟时间进度
python3 query.py progress --course 传感与检测技术 --at "2025-03-14 10:00" --json  # JSON（含 position 锚点）
```

## 八、约束

1. **只读**：本入口不修改 db / data / 课表文件；`now --at` 通过 `current_course(dt=…)` 传参，禁止 `VirtualClock.set`
2. **口径唯一**：渲染解析/进度/虚拟时间一律复用 `render_utils` / `virtual_time`；新增查询不得重复实现换算
3. 校验类命令以子进程运行 `check_*.py`，隔离 argv/全局，输出取末行
4. 新增数据字段 → 同步更新本文档 JSON schema 与示例
