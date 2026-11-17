# -*- coding: utf-8 -*-
"""生成《非遗影像文化元素智能分析系统V1.0-源代码》文档脚本

基于原「亿心通社区书记智能体软件V1.0-源代码.docx」模板：
  - 将页眉中的软件名称替换为本系统名称
  - 将正文中的旧源代码整体替换为项目真实源码
"""
import zipfile, shutil, os
from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'
ns = {'w': W}

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(BASE)  # video-vl 项目根目录

SRC = os.path.join(BASE, '3.亿心通社区书记智能体软件V1.0-源代码.docx')
OUT = os.path.join(BASE, '3.非遗影像文化元素智能分析系统V1.0-源代码.docx')

OLD_NAME = '亿心通社区书记智能体软件'
NEW_NAME = '非遗影像文化元素智能分析系统'

# 项目源码文件（按此顺序合并），值 (相对路径, 分隔注释前缀, 分隔注释后缀)
SOURCE_FILES = [
    ('web_app.py', '# ============ ', ' ============'),
    ('video_analysis_demo.py', '# ============ ', ' ============'),
    ('streamlit_app.py', '# ============ ', ' ============'),
    ('video.py', '# ============ ', ' ============'),
    ('video_vllm.py', '# ============ ', ' ============'),
    ('static/js/app.js', '// ============ ', ' ============'),
    ('templates/index.html', '<!-- ============ ', ' ============ -->'),
    ('static/css/style.css', '/* ============ ', ' ============ */'),
]


def collect_source_lines():
    lines = []
    for rel, pre, suf in SOURCE_FILES:
        path = os.path.join(PROJ, rel)
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read().splitlines()
        lines.append(pre + rel + suf)
        lines.extend(content)
    return lines


def make_paragraph(body, text):
    p = etree.SubElement(body, f'{{{W}}}p')
    pPr = etree.SubElement(p, f'{{{W}}}pPr')
    snap = etree.SubElement(pPr, f'{{{W}}}snapToGrid')
    snap.set(f'{{{W}}}val', '0')
    sp = etree.SubElement(pPr, f'{{{W}}}spacing')
    sp.set(f'{{{W}}}line', '276')
    sp.set(f'{{{W}}}lineRule', 'exact')
    rPr1 = etree.SubElement(pPr, f'{{{W}}}rPr')
    szCs1 = etree.SubElement(rPr1, f'{{{W}}}szCs')
    szCs1.set(f'{{{W}}}val', '21')
    r = etree.SubElement(p, f'{{{W}}}r')
    rPr = etree.SubElement(r, f'{{{W}}}rPr')
    rf = etree.SubElement(rPr, f'{{{W}}}rFonts')
    rf.set(f'{{{W}}}hint', 'eastAsia')
    szCs2 = etree.SubElement(rPr, f'{{{W}}}szCs')
    szCs2.set(f'{{{W}}}val', '21')
    t = etree.SubElement(r, f'{{{W}}}t')
    t.set(XML_SPACE, 'preserve')
    t.text = text
    return p


def replace_header(data):
    root = etree.fromstring(data)
    for t in root.findall('.//w:t', ns):
        if t.text == OLD_NAME:
            t.text = NEW_NAME
    return etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)


def rebuild_document(data, lines):
    root = etree.fromstring(data)
    body = root.find(f'{{{W}}}body')
    # 保留 sectPr（必须是 body 最后一个子元素），删除其余所有段落
    sectPr = body.find(f'{{{W}}}sectPr')
    for child in list(body):
        body.remove(child)
    for line in lines:
        make_paragraph(body, line)
    if sectPr is not None:
        body.append(sectPr)
    return etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)


lines = collect_source_lines()
print('源码总行数（不含分隔注释）:', sum(
    sum(1 for _ in open(os.path.join(PROJ, rel), encoding='utf-8'))
    for rel, _, _ in SOURCE_FILES
))
print('文档段落总数（含分隔注释）:', len(lines))

zin = zipfile.ZipFile(SRC)
zout = zipfile.ZipFile(OUT + '.tmp', 'w', zipfile.ZIP_DEFLATED)
for item in zin.infolist():
    if item.filename == 'word/document.xml':
        zout.writestr(item, rebuild_document(zin.read(item.filename), lines))
    elif item.filename == 'word/header1.xml':
        zout.writestr(item, replace_header(zin.read(item.filename)))
    else:
        zout.writestr(item, zin.read(item.filename))
zin.close()
zout.close()
shutil.move(OUT + '.tmp', OUT)

print('已生成源代码文档:', OUT)
