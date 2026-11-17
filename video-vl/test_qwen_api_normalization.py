import json

from qwen_api_analyzer import normalize_qwen_analysis


def test_normalize_real_qwen_shape_into_adapter_schema():
    raw = {
        "模块三_非遗文化信息": {
            "非遗类型": "民俗（祭祀/节庆习俗类）",
            "物质文化元素": ["黄纸/纸钱", "火堆"],
            "非物质文化元素": ["焚纸祭祀仪式"],
            "场景": "传统民居门口",
        },
        "模块四_影像技术与风格分析": {
            "镜头": "固定机位中近景",
            "景别": "中景/近景",
            "运镜": "基本固定",
            "是否有旁白": None,
        },
        "模块五_人物与社会关系结构": {
            "人物": [{"角色": "中年男子", "身份推测": "仪式主持者"}],
            "人物关系": "成年男性主导仪式操作",
        },
        "模块六_叙事与语义层级分析": {
            "叙事结构": "单一场景的线性记录",
            "主题": "民俗祭祀仪式及其在家庭中的传承",
        },
    }
    normalized = normalize_qwen_analysis(raw)
    assert normalized["模块三_非遗文化信息"]["类型"] == ["民俗"]
    assert normalized["模块三_非遗文化信息"]["物质文化元素"]["道具"] == ["黄纸/纸钱", "火堆"]
    assert normalized["模块三_非遗文化信息"]["非物质文化元素"]["仪式元素"] == ["焚纸祭祀仪式"]
    assert normalized["模块三_非遗文化信息"]["社会文化语境与场域"]["城乡场景"] == "其他"
    assert normalized["模块四_影像技术与风格分析"]["场景与景别"]["场景"] == "传统民居门口"
    assert normalized["模块四_影像技术与风格分析"]["镜头运动类型"] == ["固定机位"]
    assert normalized["模块五_人物与社会关系结构"]["人物关系"] == "成年男性主导仪式操作"
    assert normalized["模块六_叙事与语义层级分析"]["主题聚类"]["主要主题"] == "民俗祭祀仪式及其在家庭中的传承"


def test_normalize_preserves_canonical_analysis_shape():
    canonical = {
        "模块三_非遗文化信息": {"类型": ["传统技艺"]},
        "模块四_影像技术与风格分析": {},
        "模块五_人物与社会关系结构": {},
        "模块六_叙事与语义层级分析": {},
    }
    assert normalize_qwen_analysis(canonical) == canonical
