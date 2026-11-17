import streamlit as st
import os
import json
import tempfile
from typing import Optional, Iterable
from video_analysis_demo import VideoAnalysisDemo

# 页面配置
st.set_page_config(
    page_title="视频文化影像分析系统",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# 设计系统：统一的 CSS 样式
# -----------------------------------------------------------------------------
st.markdown("""
<style>
    :root {
        --primary: #4f46e5;
        --primary-dark: #3730a3;
        --primary-light: #eef2ff;
        --accent: #b45309;
        --accent-light: #fef3c7;
        --text-main: #1f2937;
        --text-muted: #6b7280;
        --border: #e5e7eb;
        --bg-card: #ffffff;
        --bg-soft: #f9fafb;
        --shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
        --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.08), 0 2px 4px -1px rgba(0,0,0,0.04);
    }

    /* 整体内边距与字体 */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
    }

    /* 主标题 Hero 区 */
    .hero {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 50%, #b45309 100%);
        padding: 2.2rem 2rem;
        border-radius: 1rem;
        color: #ffffff;
        margin-bottom: 1.5rem;
        box-shadow: var(--shadow-md);
        position: relative;
        overflow: hidden;
    }
    .hero::after {
        content: "";
        position: absolute;
        right: -40px; top: -40px;
        width: 220px; height: 220px;
        background: radial-gradient(circle, rgba(255,255,255,0.18) 0%, rgba(255,255,255,0) 70%);
        border-radius: 50%;
    }
    .hero h1 {
        font-size: 2rem;
        font-weight: 800;
        margin: 0 0 0.4rem 0;
        letter-spacing: 0.5px;
    }
    .hero p {
        font-size: 1rem;
        margin: 0;
        opacity: 0.92;
    }

    /* 模块标题 */
    .module-header {
        font-size: 1.25rem;
        font-weight: 700;
        color: var(--text-main);
        margin: 0.5rem 0 1rem 0;
        padding: 0.6rem 0.9rem;
        background: var(--primary-light);
        border-left: 4px solid var(--primary);
        border-radius: 0.5rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    /* 卡片容器 */
    .card {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 0.75rem;
        padding: 1rem 1.1rem;
        margin: 0.6rem 0;
        box-shadow: var(--shadow);
    }
    .card-title {
        font-size: 1.05rem;
        font-weight: 600;
        color: var(--text-main);
        margin: 0 0 0.6rem 0;
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }

    /* 标签 chip */
    .chip {
        display: inline-block;
        background: var(--primary-light);
        color: var(--primary-dark);
        border: 1px solid #c7d2fe;
        padding: 0.2rem 0.6rem;
        border-radius: 999px;
        font-size: 0.82rem;
        margin: 0.15rem 0.18rem;
        line-height: 1.4;
    }
    .chip-accent {
        background: var(--accent-light);
        color: #92400e;
        border-color: #fcd34d;
    }
    .chip-soft {
        background: var(--bg-soft);
        color: var(--text-muted);
        border-color: var(--border);
    }

    /* 空状态 */
    .empty-state {
        text-align: center;
        padding: 1.1rem 0.6rem;
        color: var(--text-muted);
        font-size: 0.88rem;
        background: var(--bg-soft);
        border: 1px dashed var(--border);
        border-radius: 0.5rem;
        margin: 0.4rem 0;
    }

    /* 状态徽章 */
    .badge {
        display: inline-block;
        padding: 0.25rem 0.65rem;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
    }
    .badge-success { background: #dcfce7; color: #166534; border: 1px solid #86efac;}
    .badge-warning { background: #fef3c7; color: #92400e; border: 1px solid #fcd34d;}
    .badge-info { background: #dbeafe; color: #1e40af; border: 1px solid #93c5fd;}

    /* 段落流（流程箭头） */
    .flow {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.3rem;
    }
    .flow-step {
        background: #ffffff;
        border: 1px solid var(--border);
        padding: 0.3rem 0.7rem;
        border-radius: 0.4rem;
        font-size: 0.85rem;
        color: var(--text-main);
    }
    .flow-arrow {
        color: var(--primary);
        font-weight: bold;
    }

    /* 信息项 */
    .kv {
        display: flex;
        gap: 0.4rem;
        margin: 0.2rem 0;
        font-size: 0.92rem;
    }
    .kv-key {
        color: var(--text-muted);
        min-width: 6rem;
        flex-shrink: 0;
    }
    .kv-val { color: var(--text-main); }

    /* 按钮统一样式 */
    .stButton>button {
        border-radius: 0.5rem;
        font-weight: 600;
    }

    /* 侧边栏标题 */
    .sidebar-section {
        font-size: 0.78rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: var(--text-muted);
        margin: 1rem 0 0.4rem 0;
    }

    /* 页脚 */
    .footer {
        text-align: center;
        color: var(--text-muted);
        font-size: 0.82rem;
        padding: 1.5rem 0 0 0;
        border-top: 1px solid var(--border);
        margin-top: 2rem;
    }

    /* tab 标签间距 */
    .stTabs [data-baseweb="tab-list"] { gap: 0.4rem; }
</style>
""", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 渲染辅助函数
# -----------------------------------------------------------------------------
def render_chips(items: Iterable, variant: str = "primary") -> str:
    """将列表渲染为 chip 标签的 HTML 字符串。"""
    cls = {"primary": "chip", "accent": "chip chip-accent", "soft": "chip chip-soft"}.get(variant, "chip")
    items = list(items) if items else []
    if not items:
        return ""
    return "".join(f'<span class="{cls}">{_esc(i)}</span>' for i in items)


def _esc(text) -> str:
    """简易 HTML 转义。"""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_card(title: str, icon: str = "", body_html: str = "") -> None:
    """渲染一个带标题的卡片。"""
    title_html = f'<div class="card-title">{icon} {_esc(title)}</div>' if title else ""
    st.markdown(
        f'<div class="card">{title_html}{body_html}</div>',
        unsafe_allow_html=True,
    )


def render_list_as_chips(items, variant="primary", empty_msg="未识别到相关内容") -> None:
    """把列表渲染为 chips；为空时显示空状态。"""
    items = list(items) if items else []
    if items:
        st.markdown(f'<div class="flow">{render_chips(items, variant)}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="empty-state">{empty_msg}</div>', unsafe_allow_html=True)


def render_kv(key: str, value) -> None:
    """渲染键值对。"""
    val = "" if value is None else str(value)
    if not val or val == "None":
        val = '<span style="color:#9ca3af">未确定</span>'
    else:
        val = _esc(val)
    st.markdown(
        f'<div class="kv"><span class="kv-key">{_esc(key)}</span><span class="kv-val">{val}</span></div>',
        unsafe_allow_html=True,
    )


def render_flow(steps, label: str = "") -> None:
    """渲染流程分段（带箭头）。"""
    steps = list(steps) if steps else []
    if not steps:
        st.markdown(f'<div class="empty-state">未识别到{label}流程</div>', unsafe_allow_html=True)
        return
    parts = []
    for idx, s in enumerate(steps):
        parts.append(f'<span class="flow-step">{_esc(s)}</span>')
        if idx != len(steps) - 1:
            parts.append('<span class="flow-arrow">→</span>')
    if label:
        st.markdown(f"**{_esc(label)}**", unsafe_allow_html=True)
    st.markdown(f'<div class="flow">{"".join(parts)}</div>', unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 模型加载与分析逻辑（保持原有功能）
# -----------------------------------------------------------------------------
# 初始化 session state
if 'analyzer' not in st.session_state:
    st.session_state.analyzer = None
if 'model_loaded' not in st.session_state:
    st.session_state.model_loaded = False
if 'analysis_result' not in st.session_state:
    st.session_state.analysis_result = None
if 'video_path' not in st.session_state:
    st.session_state.video_path = None


def load_model(model_path: str, gpu_ids: Optional[str] = None):
    """加载模型"""
    if st.session_state.model_loaded and st.session_state.analyzer is not None:
        return st.session_state.analyzer

    with st.spinner("正在加载Qwen2.5-VL模型，这可能需要几分钟..."):
        try:
            analyzer = VideoAnalysisDemo(model_path=model_path, gpu_ids=gpu_ids)
            st.session_state.analyzer = analyzer
            st.session_state.model_loaded = True
            return analyzer
        except Exception as e:
            st.error(f"模型加载失败: {str(e)}")
            return None


def format_analysis_result(result: dict) -> dict:
    """格式化分析结果以便展示"""
    formatted = {}

    if "模块三_非遗文化信息" in result:
        module3 = result["模块三_非遗文化信息"]
        formatted["模块三"] = {
            "类型": module3.get("类型", []),
            "物质文化元素": module3.get("物质文化元素", {}),
            "非物质文化元素": module3.get("非物质文化元素", {}),
            "社会文化语境与场域": module3.get("社会文化语境与场域", {}),
            "技艺仪式流程解析": module3.get("技艺仪式流程解析", {})
        }

    if "模块四_影像技术与风格分析" in result:
        module4 = result["模块四_影像技术与风格分析"]
        formatted["模块四"] = {
            "声音内容分析": module4.get("声音内容分析", {}),
            "场景与景别": module4.get("场景与景别", {}),
            "色彩风格分析": module4.get("色彩风格分析", {}),
            "镜头运动类型": module4.get("镜头运动类型", []),
            "镜头节奏统计": module4.get("镜头节奏统计", {})
        }

    if "模块五_人物与社会关系结构" in result:
        module5 = result["模块五_人物与社会关系结构"]
        formatted["模块五"] = {
            "人物社会身份": module5.get("人物社会身份", []),
            "人物关系": module5.get("人物关系", []),
            "社区群体结构": module5.get("社区群体结构", "")
        }

    if "模块六_叙事与语义层级分析" in result:
        module6 = result["模块六_叙事与语义层级分析"]
        formatted["模块六"] = {
            "叙事结构": module6.get("叙事结构", []),
            "主题聚类": module6.get("主题聚类", {}),
            "价值取向与情感": module6.get("价值取向与情感", {}),
            "冲突点识别": module6.get("冲突点识别", [])
        }

    return formatted


# -----------------------------------------------------------------------------
# 模块展示函数（卡片化）
# -----------------------------------------------------------------------------
def display_module3(data: dict):
    """展示模块三：非遗文化信息"""
    st.markdown('<div class="module-header">非遗文化信息 · 模块三</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)

    with c1:
        st.markdown('<div class="card"><div class="card-title">📋 类型分类（十大门类）</div></div>', unsafe_allow_html=True)
        types = data.get("类型", [])
        render_list_as_chips(types, variant="accent", empty_msg="未识别到非遗类型")

        st.markdown('<div class="card"><div class="card-title">🏛️ 物质文化元素</div></div>', unsafe_allow_html=True)
        material = data.get("物质文化元素", {})
        if material:
            if material.get("道具"):
                st.markdown("**道具**")
                render_list_as_chips(material["道具"], "primary", "")
            if material.get("服饰"):
                st.markdown("**服饰**")
                render_list_as_chips(material["服饰"], "primary", "")
            if material.get("建筑与场地"):
                st.markdown("**建筑与场地**")
                render_list_as_chips(material["建筑与场地"], "primary", "")
            if material.get("民族或地区关联"):
                render_kv("民族或地区关联", material["民族或地区关联"])
            if not any(material.get(k) for k in ["道具", "服饰", "建筑与场地", "民族或地区关联"]):
                st.markdown('<div class="empty-state">未识别到物质文化元素</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="empty-state">未识别到物质文化元素</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="card"><div class="card-title">🎭 非物质文化元素</div></div>', unsafe_allow_html=True)
        immaterial = data.get("非物质文化元素", {})
        if immaterial:
            if immaterial.get("仪式元素"):
                st.markdown("**仪式元素**")
                render_list_as_chips(immaterial["仪式元素"], "primary", "")
            if immaterial.get("技艺流程"):
                st.markdown("**技艺流程**")
                render_list_as_chips(immaterial["技艺流程"], "primary", "")
            if immaterial.get("身体动作序列"):
                st.markdown("**身体动作序列**")
                render_list_as_chips(immaterial["身体动作序列"], "primary", "")
            if immaterial.get("口述传统文本"):
                render_kv("口述传统文本", immaterial["口述传统文本"])
            if not any(immaterial.get(k) for k in ["仪式元素", "技艺流程", "身体动作序列", "口述传统文本"]):
                st.markdown('<div class="empty-state">未识别到非物质文化元素</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="empty-state">未识别到非物质文化元素</div>', unsafe_allow_html=True)

        st.markdown('<div class="card"><div class="card-title">🌍 社会文化语境与场域</div></div>', unsafe_allow_html=True)
        context = data.get("社会文化语境与场域", {})
        if context:
            render_kv("城乡场景", context.get("城乡场景", "未确定"))
            if context.get("使用语境"):
                st.markdown("**使用语境**")
                render_list_as_chips(context["使用语境"], "soft", "")
            if context.get("观众类型"):
                st.markdown("**观众类型**")
                render_list_as_chips(context["观众类型"], "soft", "")
            if not any(context.get(k) for k in ["城乡场景", "使用语境", "观众类型"]):
                st.markdown('<div class="empty-state">未识别到社会文化语境</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="empty-state">未识别到社会文化语境</div>', unsafe_allow_html=True)

    st.markdown('<div class="card"><div class="card-title">🔄 技艺/仪式流程解析</div></div>', unsafe_allow_html=True)
    process = data.get("技艺仪式流程解析", {})
    if process and any(process.get(k) for k in ["技艺流程分段", "仪式程序分段", "关键步骤"]):
        if process.get("技艺流程分段"):
            render_flow(process["技艺流程分段"], "技艺流程分段")
        if process.get("仪式程序分段"):
            render_flow(process["仪式程序分段"], "仪式程序分段")
        if process.get("关键步骤"):
            st.markdown("**关键步骤**")
            render_list_as_chips(process["关键步骤"], "accent", "")
    else:
        st.markdown('<div class="empty-state">未识别到流程解析</div>', unsafe_allow_html=True)


def display_module4(data: dict):
    """展示模块四：影像技术与风格分析"""
    st.markdown('<div class="module-header">影像技术与风格分析 · 模块四</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)

    with c1:
        st.markdown('<div class="card"><div class="card-title">🔊 声音内容分析</div></div>', unsafe_allow_html=True)
        audio = data.get("声音内容分析", {})
        if audio:
            if audio.get("环境音类型"):
                st.markdown("**环境音类型**")
                render_list_as_chips(audio["环境音类型"], "soft", "")
            if audio.get("传统乐器识别"):
                st.markdown("**传统乐器识别**")
                render_list_as_chips(audio["传统乐器识别"], "accent", "")
            render_kv("是否有旁白", "是" if audio.get("是否有旁白") else "否")
            if audio.get("唱腔类型"):
                render_kv("唱腔类型", audio["唱腔类型"])
            if not any(audio.get(k) for k in ["环境音类型", "传统乐器识别", "是否有旁白", "唱腔类型"]):
                st.markdown('<div class="empty-state">未识别到声音内容</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="empty-state">未识别到声音内容</div>', unsafe_allow_html=True)

        st.markdown('<div class="card"><div class="card-title">🎨 色彩风格分析</div></div>', unsafe_allow_html=True)
        color = data.get("色彩风格分析", {})
        if color and any(color.get(k) for k in ["色调", "饱和度", "民族色彩特征"]):
            render_kv("色调", color.get("色调", "未确定"))
            render_kv("饱和度", color.get("饱和度", "未确定"))
            render_kv("民族色彩特征", color.get("民族色彩特征", "未确定"))
        else:
            st.markdown('<div class="empty-state">未识别到色彩风格</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="card"><div class="card-title">📹 场景与景别</div></div>', unsafe_allow_html=True)
        scene = data.get("场景与景别", {})
        if scene:
            if scene.get("场景"):
                st.markdown("**场景**")
                render_list_as_chips(scene["场景"], "primary", "")
            if scene.get("景别"):
                st.markdown("**景别**")
                render_list_as_chips(scene["景别"], "soft", "")
            if not any(scene.get(k) for k in ["场景", "景别"]):
                st.markdown('<div class="empty-state">未识别到场景与景别</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="empty-state">未识别到场景与景别</div>', unsafe_allow_html=True)

        st.markdown('<div class="card"><div class="card-title">🎬 镜头运动类型</div></div>', unsafe_allow_html=True)
        movement = data.get("镜头运动类型", [])
        render_list_as_chips(movement, "primary", "未识别到镜头运动类型")

        st.markdown('<div class="card"><div class="card-title">⏱️ 镜头节奏统计</div></div>', unsafe_allow_html=True)
        rhythm = data.get("镜头节奏统计", {})
        if rhythm and any(rhythm.get(k) for k in ["平均镜头长度", "稳定vs快剪比例", "长镜头分布"]):
            render_kv("平均镜头长度", rhythm.get("平均镜头长度", "未确定"))
            render_kv("稳定 vs 快剪比例", rhythm.get("稳定vs快剪比例", "未确定"))
            render_kv("长镜头分布", rhythm.get("长镜头分布", "未确定"))
        else:
            st.markdown('<div class="empty-state">未识别到镜头节奏统计</div>', unsafe_allow_html=True)


def display_module5(data: dict):
    """展示模块五：人物与社会关系结构"""
    st.markdown('<div class="module-header">人物与社会关系结构 · 模块五</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)

    with c1:
        st.markdown('<div class="card"><div class="card-title">👤 人物社会身份</div></div>', unsafe_allow_html=True)
        identity = data.get("人物社会身份", [])
        render_list_as_chips(identity, "accent", "未识别到人物身份")

        st.markdown('<div class="card"><div class="card-title">🤝 人物关系</div></div>', unsafe_allow_html=True)
        relations = data.get("人物关系", [])
        render_list_as_chips(relations, "primary", "未识别到人物关系")

    with c2:
        st.markdown('<div class="card"><div class="card-title">🏘️ 社区或群体结构</div></div>', unsafe_allow_html=True)
        community = data.get("社区群体结构", "")
        if community:
            st.markdown(
                f'<div style="color:var(--text-main); font-size:0.92rem; line-height:1.6;">{_esc(community)}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div class="empty-state">未识别到社区群体结构</div>', unsafe_allow_html=True)


def display_module6(data: dict):
    """展示模块六：叙事与语义层级分析"""
    st.markdown('<div class="module-header">叙事与语义层级分析 · 模块六</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)

    with c1:
        st.markdown('<div class="card"><div class="card-title">📖 叙事结构</div></div>', unsafe_allow_html=True)
        narrative = data.get("叙事结构", [])
        render_list_as_chips(narrative, "accent", "未识别到叙事结构")

        st.markdown('<div class="card"><div class="card-title">🏷️ 主题聚类</div></div>', unsafe_allow_html=True)
        themes = data.get("主题聚类", {})
        if themes and any(themes.get(k) for k in ["主要主题", "子主题"]):
            if themes.get("主要主题"):
                st.markdown("**主要主题**")
                render_list_as_chips(themes["主要主题"], "primary", "")
            if themes.get("子主题"):
                st.markdown("**子主题**")
                render_list_as_chips(themes["子主题"], "soft", "")
        else:
            st.markdown('<div class="empty-state">未识别到主题</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="card"><div class="card-title">💭 价值取向与情感</div></div>', unsafe_allow_html=True)
        values = data.get("价值取向与情感", {})
        if values and any(values.get(k) for k in ["价值取向", "情感分析"]):
            if values.get("价值取向"):
                st.markdown("**价值取向**")
                render_list_as_chips(values["价值取向"], "primary", "")
            if values.get("情感分析"):
                st.markdown("**情感分析**")
                render_list_as_chips(values["情感分析"], "accent", "")
        else:
            st.markdown('<div class="empty-state">未识别到价值取向与情感</div>', unsafe_allow_html=True)

        st.markdown('<div class="card"><div class="card-title">⚔️ 冲突点识别</div></div>', unsafe_allow_html=True)
        conflicts = data.get("冲突点识别", [])
        render_list_as_chips(conflicts, "soft", "未识别到冲突点")


def display_summary(formatted: dict) -> None:
    """分析概览：以指标卡 + 关键标签的形式快速呈现核心信息。"""
    st.markdown('<div class="module-header">📊 分析概览</div>', unsafe_allow_html=True)

    # 顶部指标卡
    m1, m2, m3, m4 = st.columns(4)

    def _count(d, *keys):
        """统计某模块下识别到的项目总数。"""
        total = 0
        for k in keys:
            v = d.get(k)
            if isinstance(v, list):
                total += len(v)
            elif isinstance(v, dict):
                total += sum(len(sv) for sv in v.values() if isinstance(sv, list))
            elif isinstance(v, (str, int, float)) and v not in ("", "未确定", None):
                total += 1
        return total

    mod3 = formatted.get("模块三", {})
    mod4 = formatted.get("模块四", {})
    mod5 = formatted.get("模块五", {})
    mod6 = formatted.get("模块六", {})

    c3 = _count(mod3, "类型", "物质文化元素", "非物质文化元素", "社会文化语境与场域", "技艺仪式流程解析")
    c4 = _count(mod4, "声音内容分析", "场景与景别", "色彩风格分析", "镜头运动类型", "镜头节奏统计")
    c5 = _count(mod5, "人物社会身份", "人物关系", "社区群体结构")
    c6 = _count(mod6, "叙事结构", "主题聚类", "价值取向与情感", "冲突点识别")

    for col, label, val, color in [
        (m1, "非遗文化元素", c3, "#4f46e5"),
        (m2, "影像技术风格", c4, "#b45309"),
        (m3, "人物社会关系", c5, "#0e7490"),
        (m4, "叙事语义层级", c6, "#7c3aed"),
    ]:
        col.markdown(
            f"""<div class="card" style="text-align:center;">
                <div style="font-size:1.8rem; font-weight:800; color:{color};">{val}</div>
                <div style="color:var(--text-muted); font-size:0.82rem; margin-top:0.2rem;">{label}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    # 关键信息速览
    st.markdown("---")
    q1, q2 = st.columns(2)
    with q1:
        st.markdown('<div class="card"><div class="card-title">📋 非遗类型</div></div>', unsafe_allow_html=True)
        render_list_as_chips(mod3.get("类型", []), "accent", "未识别到非遗类型")

        st.markdown('<div class="card"><div class="card-title">📖 叙事结构</div></div>', unsafe_allow_html=True)
        render_list_as_chips(mod6.get("叙事结构", []), "primary", "未识别到叙事结构")

    with q2:
        st.markdown('<div class="card"><div class="card-title">🎭 非遗相关元素</div></div>', unsafe_allow_html=True)
        material = mod3.get("物质文化元素", {})
        elements = []
        for k in ["道具", "服饰", "建筑与场地"]:
            elements.extend(material.get(k, []) or [])
        render_list_as_chips(elements, "primary", "未识别到相关元素")

        st.markdown('<div class="card"><div class="card-title">🎬 镜头运动</div></div>', unsafe_allow_html=True)
        render_list_as_chips(mod4.get("镜头运动类型", []), "soft", "未识别到镜头运动类型")


# -----------------------------------------------------------------------------
# 主界面
# -----------------------------------------------------------------------------
st.markdown(
    '<div class="hero">'
    '<h1>🎬 非遗影像文化元素智能分析系统</h1>'
    '<p>基于多模态大模型 Qwen2.5-VL，从视频中解析非遗文化、影像风格、人物关系与叙事结构</p>'
    '</div>',
    unsafe_allow_html=True,
)

# 侧边栏配置
with st.sidebar:
    st.markdown('<div class="sidebar-section">模型配置</div>', unsafe_allow_html=True)
    model_path = st.text_input(
        "模型路径",
        value="/home/u20240148/project/Qwen2.5-VL/Qwenvl_72B",
        help="Qwen2.5-VL模型的路径",
    )

    gpu_ids = st.text_input(
        "GPU ID（可选）",
        value="0,1,2",
        help="指定使用的GPU，格式如 '0,1,2' 或 '0,1'。留空则使用所有可用GPU",
    )

    if st.button("加载模型", type="primary"):
        with st.spinner("正在加载模型..."):
            gpu_ids_value = gpu_ids.strip() if gpu_ids.strip() else None
            analyzer = load_model(model_path, gpu_ids=gpu_ids_value)
            if analyzer:
                gpu_info = f"（使用GPU: {gpu_ids_value}）" if gpu_ids_value else "（使用所有可用GPU）"
                st.success(f"模型加载成功！{gpu_info}")
            else:
                st.error("模型加载失败")

    # 状态徽章
    st.markdown("---")
    st.markdown('<div class="sidebar-section">运行状态</div>', unsafe_allow_html=True)
    if st.session_state.model_loaded:
        st.markdown('<span class="badge badge-success">● 模型已就绪</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="badge badge-warning">● 模型未加载</span>', unsafe_allow_html=True)

    if st.session_state.analysis_result is not None:
        st.markdown('<span class="badge badge-info">● 已有分析结果</span>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown('<div class="sidebar-section">使用说明</div>', unsafe_allow_html=True)
    st.markdown(
        """
        1. 侧边栏加载模型（首次约数分钟）  
        2. 上传视频，点击 **开始分析**  
        3. 在 **分析结果** 标签查看详情  
        4. 可下载 JSON 格式结果
        """,
    )

# 主内容区
tab1, tab2 = st.tabs(["📤 视频上传与分析", "📊 分析结果"])

with tab1:
    st.subheader("上传视频")

    uploaded_file = st.file_uploader(
        "选择视频文件",
        type=['mp4', 'avi', 'mov', 'mkv'],
        help="支持MP4、AVI、MOV、MKV格式",
    )

    if uploaded_file is not None:
        # 文件信息卡片
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="card-title">📄 文件信息</div>', unsafe_allow_html=True)
        file_details = {
            "文件名": uploaded_file.name,
            "文件类型": uploaded_file.type,
            "文件大小": f"{uploaded_file.size / (1024*1024):.2f} MB",
        }
        for k, v in file_details.items():
            render_kv(k, v)
        st.markdown('</div>', unsafe_allow_html=True)

        # 保存上传的视频到临时文件
        if 'temp_video_path' not in st.session_state or st.session_state.get('uploaded_file_name') != uploaded_file.name:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp_file:
                tmp_file.write(uploaded_file.read())
                temp_video_path = tmp_file.name
            st.session_state.temp_video_path = temp_video_path
            st.session_state.uploaded_file_name = uploaded_file.name
        else:
            temp_video_path = st.session_state.temp_video_path

        # 视频预览
        st.markdown('<div class="card"><div class="card-title">🎞️ 视频预览</div></div>', unsafe_allow_html=True)
        st.video(temp_video_path)

        # 模型状态提示
        if not st.session_state.model_loaded or st.session_state.analyzer is None:
            st.markdown(
                '<span class="badge badge-warning">⚠️ 请先在左侧边栏加载模型后再开始分析</span><br>'
                '<span style="color:var(--text-muted); font-size:0.85rem;">提示：点击侧边栏"加载模型"，等待加载完成（可能需要几分钟）</span>',
                unsafe_allow_html=True,
            )

        # 开始分析按钮
        if st.button("开始分析", type="primary"):
            if st.session_state.analyzer is None or not st.session_state.model_loaded:
                st.error('模型未加载！请先在左侧边栏点击「加载模型」，等待加载完成后再试。')
                st.stop()
            else:
                st.session_state.video_path = temp_video_path

                progress_bar = st.progress(0)
                status_text = st.empty()

                try:
                    status_text.markdown(
                        '<span class="badge badge-info">● 正在分析视频，请耐心等待…</span>',
                        unsafe_allow_html=True,
                    )
                    progress_bar.progress(10)

                    # 执行分析
                    result = st.session_state.analyzer.analyze_video(
                        temp_video_path,
                        output_path=None
                    )

                    progress_bar.progress(100)
                    status_text.markdown(
                        '<span class="badge badge-success">● 分析完成！</span>',
                        unsafe_allow_html=True,
                    )

                    st.session_state.analysis_result = result
                    st.success('分析完成！请切换到「分析结果」标签页查看详细结果。')

                    json_str = json.dumps(result, indent=2, ensure_ascii=False)
                    st.download_button(
                        label="📥 下载分析结果 (JSON)",
                        data=json_str,
                        file_name=f"{uploaded_file.name}_analysis.json",
                        mime="application/json",
                    )

                except Exception as e:
                    st.error(f"分析过程中出现错误: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())
                finally:
                    if os.path.exists(temp_video_path):
                        os.unlink(temp_video_path)

with tab2:
    st.subheader("分析结果")

    if st.session_state.analysis_result is None:
        st.markdown(
            '<div class="empty-state" style="padding:3rem 1rem;">'
            '👆 请先在"视频上传与分析"标签上传视频并完成分析'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        result = st.session_state.analysis_result

        if "error" in result:
            st.error(f"分析出错: {result.get('error')}")
            if "raw_output" in result:
                with st.expander("查看原始输出"):
                    st.text(result["raw_output"])
        else:
            formatted_result = format_analysis_result(result)

            module_tabs = st.tabs([
                "📊 分析概览",
                "模块三 · 非遗文化",
                "模块四 · 影像风格",
                "模块五 · 人物关系",
                "模块六 · 叙事语义",
                "📄 完整 JSON",
            ])

            with module_tabs[0]:
                display_summary(formatted_result)

            with module_tabs[1]:
                if "模块三" in formatted_result:
                    display_module3(formatted_result["模块三"])
                else:
                    st.markdown('<div class="empty-state">未找到模块三的分析结果</div>', unsafe_allow_html=True)

            with module_tabs[2]:
                if "模块四" in formatted_result:
                    display_module4(formatted_result["模块四"])
                else:
                    st.markdown('<div class="empty-state">未找到模块四的分析结果</div>', unsafe_allow_html=True)

            with module_tabs[3]:
                if "模块五" in formatted_result:
                    display_module5(formatted_result["模块五"])
                else:
                    st.markdown('<div class="empty-state">未找到模块五的分析结果</div>', unsafe_allow_html=True)

            with module_tabs[4]:
                if "模块六" in formatted_result:
                    display_module6(formatted_result["模块六"])
                else:
                    st.markdown('<div class="empty-state">未找到模块六的分析结果</div>', unsafe_allow_html=True)

            with module_tabs[5]:
                st.json(result)

                json_str = json.dumps(result, indent=2, ensure_ascii=False)
                st.download_button(
                    label="📥 下载完整 JSON 结果",
                    data=json_str,
                    file_name="video_analysis_result.json",
                    mime="application/json",
                )

# 页脚
st.markdown(
    "<div class='footer'>基于 Qwen2.5-VL 模型 · 视频文化影像分析系统</div>",
    unsafe_allow_html=True,
)
