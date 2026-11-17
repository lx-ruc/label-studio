# -*- coding: utf-8 -*-
"""填写《计算机软件著作权登记申请表》脚本"""
import zipfile, shutil, os
from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
W14 = 'http://schemas.microsoft.com/office/word/2010/wordml'
ns = {'w': W, 'w14': W14}

SRC = '1.计算机软件著作权登记申请表.docx'
OUT = SRC  # 原地覆盖（已备份）

# ---------------- 待填内容 ----------------
SOFT_NAME = '非遗影像文化元素智能分析系统'

DEV_PURPOSE = '利用多模态大模型自动解析非遗影像中的文化元素、影像风格、人物关系与叙事结构，服务非遗保护与研究'

INDUSTRY = '非物质文化遗产保护、文化影像分析与研究、数字人文'

MAIN_FUNCS = (
    '本软件是一款基于 Qwen2.5-VL 多模态大模型的非遗影像文化元素智能分析系统，'
    '面向非物质文化遗产保护、研究与数字化建档需求，对用户上传的视频进行端到端的自动化文化影像分析，'
    '并将分析结果以结构化 JSON 格式输出与可视化展示。'
    '系统提供 Web 可视化界面，用户可配置本地模型路径并加载模型，上传 MP4、AVI、MOV、MKV 等格式视频后一键启动分析，'
    '实时查看分析进度，分析完成后按模块浏览结果并下载完整 JSON 报告。'
    '系统核心功能包括四大分析模块：'
    '（1）非遗文化信息分析模块：对视频内容进行非遗类型分类（民间文学、传统音乐、传统舞蹈、传统戏剧、曲艺、'
    '传统体育游艺与杂技、传统美术、传统技艺、传统医药、民俗十大门类）；识别物质文化元素（道具、服饰、建筑与场地）'
    '与非物质文化元素（仪式、技艺、口述传统、身体动作）；推断社会文化语境与场域（城乡场景、使用语境、观众类型）；'
    '并对技艺流程与仪式程序进行结构化分段解析。'
    '（2）影像技术与风格分析模块：分析声音内容（环境音、传统乐器、旁白与唱腔）、场景与景别、色彩风格、'
    '镜头运动类型（固定机位、推拉摇移、手持、跟拍、航拍等）以及镜头节奏与镜头长度统计。'
    '（3）人物与社会关系结构分析模块：识别人物社会身份（传承人、学徒、社区工作者等）、人物关系（师徒、家庭、社区角色）'
    '及社区或群体结构。'
    '（4）叙事与语义层级分析模块：识别叙事结构类型、进行主题聚类与扎根理论编码、分析价值取向与情感、识别冲突点。'
    '此外，系统还提供命令行与 Python 接口调用方式，便于集成到科研与业务流程中。'
)

TECH_FEATURES = (
    '采用 Qwen2.5-VL 多模态大模型与提示词工程，实现非遗影像端到端结构化解析；'
    '后端基于 FastAPI，前端采用 HTML/CSS/JavaScript，提供分析结果可视化展示。'
)

# 文本替换表：old(匹配当前单元格文本) -> new
REPLACEMENTS = [
    ('亿心通社区书记智能体软件', SOFT_NAME),
    ('亿心通', ''),  # 软件简称
    ('2025年10月20日', '2026年8月15日'),  # 开发完成日期
    ('Linux', 'Linux 服务器（GPU 服务器，4×NVIDIA A800）'),  # 开发的硬件环境
    ('CPU 8核，内存 64GB，硬盘 500GB可用空间', 'GPU 服务器（4×NVIDIA A800 80GB），32核 CPU，内存 468GB'),  # 运行的硬件环境
    ('Ubuntu 20.4', 'Rocky Linux 8.10'),  # 开发操作系统 / 运行平台
    ('Node.js v16.0+，Express v4.18+，MySQL v8.0+，大模型推理环境',
     'Python 3.10、PyTorch 2.9、Transformers、FastAPI、Qwen2.5-VL 大模型'),  # 开发工具
    ('服务器端：Node.js；Express；MySQL；大模型推理环境客户端：现代浏览器，支持ES6+',
     '服务器端：Python、PyTorch、FastAPI、Uvicorn、Qwen2.5-VL 大模型；客户端：现代浏览器'),  # 支撑环境
    ('17400', '2942'),  # 源程序量
    ('旨在构建一个深度融合领域知识与大语言模型能力的智能工作平台，提升社区工作的精细化、专业化与科学化水平',
     DEV_PURPOSE),  # 开发目的
    ('社区服务、基层治理', INDUSTRY),  # 面向领域/行业
    ('采用Langchain架构的Agent技术编排智能体工作流，设计文档检索、问题分析、案例撰写等引擎，使用社会治理领域高质量数据集驱动知识问答。',
     TECH_FEATURES),  # 技术特点描述
    ('2025年10月23日', ''),  # 首次发表日期（未发表，清空）
    ('北京市海淀区', ''),  # 首次发表省份（未发表，清空）
]
# 长字段用“包含”匹配（避免空格/换行差异）
CONTAINS_REPLACEMENTS = [
    ('该软件是一种深度融合大模型与基层治理具体问题的生成式人工智能系统', MAIN_FUNCS),
]

# 复选框切换：段落全文 -> 是否勾选
CHECKBOX_TOGGLE = {
    '☐未发表': True,   # 未发表 -> 勾选
    '☒已发表': False,  # 已发表 -> 取消勾选
    '☒SQL': False,     # SQL -> 取消勾选（本项目无数据库）
}

# ---------------- 工具函数 ----------------
def cell_text(tc):
    return ''.join(t.text or '' for t in tc.findall('.//w:t', ns))

def p_text(p):
    return ''.join(t.text or '' for t in p.findall('.//w:t', ns))

def set_run_text(r, text):
    for t in r.findall('./w:t', ns):
        r.remove(t)
    t = etree.SubElement(r, f'{{{W}}}t')
    t.text = text
    if text != text.strip():
        t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')

def set_cell_value(tc, new_text):
    runs = []
    for p in tc.findall('./w:p', ns):
        runs.extend(p.findall('./w:r', ns))
    if not runs:
        return
    set_run_text(runs[0], new_text)
    for r in runs[1:]:
        set_run_text(r, '')

def toggle_checkbox(p, checked):
    cb = p.find('.//w14:checkbox', ns)
    if cb is None:
        return
    ce = cb.find('./w14:checked', ns)
    if ce is None:
        ce = etree.SubElement(cb, f'{{{W14}}}checked')
    ce.set(f'{{{W14}}}val', '1' if checked else '0')
    sdt = p.find('./w:sdt', ns)
    if sdt is not None:
        t = sdt.find('.//w:t', ns)
        if t is not None:
            t.text = '☒' if checked else '☐'

def accept_changes(root):
    for d in root.findall('.//w:del', ns):
        d.getparent().remove(d)
    for ins in root.findall('.//w:ins', ns):
        parent = ins.getparent()
        idx = parent.index(ins)
        for child in list(ins):
            parent.insert(idx, child)
            idx += 1
        parent.remove(ins)

# ---------------- 主流程 ----------------
data = zipfile.ZipFile(SRC).read('word/document.xml')
root = etree.fromstring(data)
accept_changes(root)

# 1) 文本替换（单元格级）
for tc in root.findall('.//w:tc', ns):
    t = cell_text(tc).strip()
    if not t:
        continue
    # 长字段：包含匹配
    matched = False
    for old, new in CONTAINS_REPLACEMENTS:
        if old in t:
            set_cell_value(tc, new)
            matched = True
            break
    if matched:
        continue
    # 短字段：精确匹配（'亿心通' 用精确匹配避免误伤全称）
    for old, new in REPLACEMENTS:
        if t == old:
            set_cell_value(tc, new)
            break

# 2) 复选框切换
for p in root.findall('.//w:p', ns):
    pt = p_text(p)
    if pt in CHECKBOX_TOGGLE:
        toggle_checkbox(p, CHECKBOX_TOGGLE[pt])

# 写回（保留其它部件）
zin = zipfile.ZipFile(SRC)
zout = zipfile.ZipFile(OUT + '.tmp', 'w', zipfile.ZIP_DEFLATED)
for item in zin.infolist():
    if item.filename == 'word/document.xml':
        zout.writestr(item, etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True))
    else:
        zout.writestr(item, zin.read(item.filename))
zin.close()
zout.close()
shutil.move(OUT + '.tmp', OUT)

print('已填写申请表:', OUT)
print('主要功能字数:', len(MAIN_FUNCS))
print('技术特点字数:', len(TECH_FEATURES))
print('开发目的字数:', len(DEV_PURPOSE))
