# -*- coding: utf-8 -*-
"""填写《说明文档》脚本（保留标题与图片占位，替换正文文字）"""
import zipfile, shutil
from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
ns = {'w': W}

SRC = '2.说明文档模板.docx'
OUT = SRC

def p_text(p):
    return ''.join(t.text or '' for t in p.findall('.//w:t', ns))

def set_p_text(p, text):
    runs = p.findall('./w:r', ns)
    if not runs:
        # 无 run 的段落：新建一个
        r = etree.SubElement(p, f'{{{W}}}r')
        runs = [r]
    # 清空第一个 run 的子 w:t，再写入
    for t in runs[0].findall('./w:t', ns):
        runs[0].remove(t)
    t = etree.SubElement(runs[0], f'{{{W}}}t')
    t.text = text
    if text != text.strip():
        t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    for r in runs[1:]:
        for t in r.findall('./w:t', ns):
            r.remove(t)

# 前缀匹配替换表：old_prefix -> new_text（new_text 为空表示清空）
REPL = [
    # ---- 产品概述 ----
    ('“亿心通”社区书记智能体是国内高校研发',
     '「非遗影像文化元素智能分析系统」是一款基于 Qwen2.5-VL 多模态大模型的非物质文化遗产影像智能分析软件，'
     '面向非遗保护、研究与数字化建档需求，对用户上传的视频进行端到端的自动化文化影像分析，并以结构化 JSON 形式输出结果。'),
    ('针对基层治理难题，“亿心通”的独有优势',
     '系统可对非遗影像进行四个维度的深度解析：非遗文化信息（类型分类、物质与非物质文化元素、社会文化语境与场域、'
     '技艺与仪式流程）、影像技术与风格（声音、场景景别、色彩、镜头运动与节奏）、人物与社会关系结构（人物身份、人物关系、'
     '社区群体结构）、叙事与语义层级（叙事结构、主题聚类、价值取向情感、冲突点），辅助研究者、文化机构与社会公众高效理解非遗影像的文化内涵。'),
    # ---- 界面概述 ----
    ('1.主登录界面',
     '1.主界面：\u3000系统采用左侧配置区与右侧内容区的布局。左侧配置区可填写模型本地路径、选择 GPU 并点击“加载模型”；'
     '右侧通过标签页切换“视频上传与分析”“分析结果”等功能。'),
    ('2.系统主界面',
     '2.模型配置区：\u3000用户填写 Qwen2.5-VL 模型的本地路径（默认 /home/u20240148/project/Qwen2.5-VL/Qwenvl_72B），'
     '选择使用的 GPU（如 0,1,2），点击“加载模型”后，界面实时显示加载状态（加载中/就绪/失败）。'),
    # ---- 流程 ----
    ('流程一：使用智能对话功能', '流程一：加载模型'),
    ('用户点击系统主界面的导航栏“对话交流”', '用户打开系统主界面，在左侧配置区确认模型路径与 GPU 配置。'),
    ('在下方输入框键入自然语言问题', '点击“加载模型”按钮，系统后台线程加载 Qwen2.5-VL 模型与处理器。'),
    ('前端通过Axios将问题发送', '加载完成后状态显示为“就绪”，即可进行视频分析。'),
    ('后端调用AI服务并结合知识库检索', ''),
    ('回答内容通过MarkdownIt解析渲染', ''),
    ('流程二：生成个性化方案', '流程二：上传视频并分析'),
    ('用户点击系统主界面的导航栏“方案定制”', '切换到“视频上传与分析”标签页，选择本地视频文件（支持 MP4、AVI、MOV、MKV）。'),
    ('根据表单提示，逐项填写社区名称', '点击“开始分析”，系统将视频上传至服务器并启动后台分析任务。'),
    ('点击“生成方案”按钮，前端将表单数据', '界面实时显示分析进度与当前阶段（模型推理中等）。'),
    ('后端根据输入数据，匹配规则模板', ''),
    ('生成的完整方案以结构化视图', ''),
    ('流程三：使用知识问答功能', '流程三：查看分析结果'),
    ('用户点击系统主界面的导航栏“知识问答”', '分析完成后，切换到“分析结果”标签页。'),
    ('面向从事社会工作服务的专业人员', '点击下载按钮保存完整的 JSON 格式分析报告。'),
    ('流程四：使用深度分析功能', '流程四：命令行与接口调用'),
    ('用户点击系统主界面的导航栏“深度分析”', '系统同时提供命令行方式：python video_analysis_demo.py --video <视频路径> --model_path <模型路径>。'),
    ('针对复杂议题，通过多维度建模', '亦可通过 Python 接口 import VideoAnalysisDemo 进行集成调用。'),
    # ---- 技术特点与独创性 ----
    ('总体技术架构：本软件采用前后端分离',
     '总体技术架构：本软件采用前后端分离的 Web 应用架构，后端基于 Python FastAPI 提供 RESTful API，'
     '前端采用 HTML/CSS/JavaScript 实现交互式界面。'),
    ('前端展现层： 使用Vue 3框架',
     '前端展现层：使用原生 HTML/CSS/JavaScript 实现响应式界面，包括模型配置、视频上传、进度展示与结果可视化等模块。'),
    ('后端业务逻辑层： 使用 Node.js平台',
     '后端服务层：使用 FastAPI 框架构建分析接口，通过后台线程异步执行长耗时的大模型推理任务，'
     '前端以轮询方式获取模型加载与分析进度。'),
    ('数据持久层：采用MySQL关系型数据库',
     '数据层：分析结果以结构化 JSON 格式保存，可下载、归档与二次利用，便于非遗影像数据的数字化建档。'),
    ('AI能力集成层：通过后端服务调用',
     'AI 能力集成层：集成 Qwen2.5-VL 多模态大模型，采用提示词工程将非遗影像分析目标转化为结构化输出模板，'
     '实现视频视觉信息到 JSON 分析结果的端到端转换。'),
    ('本软件并非通用聊天机器人，而是针对',
     '本软件面向“非物质文化遗产影像”这一垂直领域，独创性地设计了覆盖文化信息、影像技术、人物关系、叙事语义四个维度的'
     '结构化分析框架与提示词模板，将通用多模态大模型能力适配到非遗研究与数字化建档场景。'),
    ('在方案定制等核心功能中，软件独创性',
     '软件通过规范化的 JSON 输出协议，将大模型生成结果转化为可检索、可归档、可比较的结构化数据，'
     '解决了通用大模型输出不可控、不便于二次利用的问题，显著提升了非遗影像分析的专业性与可复用性。'),
    ('针对基层工作者可能不熟悉AI的特点',
     '系统采用异步任务与状态轮询机制，将分钟级甚至更长的模型推理过程与前端交互解耦，'
     '用户上传视频后即可查看实时进度，无需等待阻塞，体现了良好的用户体验设计。'),
]

data = zipfile.ZipFile(SRC).read('word/document.xml')
root = etree.fromstring(data)

# 处理两个 “。。。。。。” 占位符：第一个→流程三内容，第二个→清空
dotdot_count = 0
for p in root.findall('.//w:p', ns):
    txt = p_text(p)
    if not txt.strip():
        continue
    if txt.startswith('。。。。。。'):
        if dotdot_count == 0:
            set_p_text(p, '按“非遗文化信息”“影像技术与风格”“人物与社会关系”“叙事与语义层级”四个模块浏览结构化分析结果。')
        else:
            set_p_text(p, '')
        dotdot_count += 1
        continue
    for old_prefix, new in REPL:
        if txt.startswith(old_prefix):
            set_p_text(p, new)
            break

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
print('已填写说明文档:', OUT)
