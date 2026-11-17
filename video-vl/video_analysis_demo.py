import os
import json
import torch
from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info
from typing import Dict, Any, Optional
import argparse

class VideoAnalysisDemo:
    """基于Qwen2.5-VL的视频理解分析Demo"""
    
    def __init__(self, model_path: str = "/home/u20240148/project/Qwen2.5-VL/Qwenvl_72B", gpu_ids: Optional[str] = None):
        """
        初始化模型和处理器
        
        Args:
            model_path: 模型路径
            gpu_ids: 指定使用的GPU ID，格式如 "0,1,2" 或 "0,1"。如果为None，使用所有可用GPU
        """
        self.model_path = model_path
        
        # 如果指定了GPU，设置环境变量
        if gpu_ids is not None:
            os.environ["CUDA_VISIBLE_DEVICES"] = gpu_ids
            print(f"指定使用GPU: {gpu_ids}")
        
        print("正在加载模型...")
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            model_path, torch_dtype="auto", device_map="auto"
        )
        self.processor = AutoProcessor.from_pretrained(model_path)
        print("✅ 模型加载完成")
    
    def _build_analysis_prompt(self) -> str:
        """构建详细的分析提示词"""
        prompt = """请对上传的视频进行全面的文化影像分析，按照以下结构输出JSON格式的分析结果。

请仔细分析视频的视觉内容、音频内容、字幕（如果有）等所有信息，并按照以下模块进行结构化分析：

模块三-非遗文化信息：
1）类型：从以下十大门类中选择（可多选）：民间文学、传统音乐、传统舞蹈、传统戏剧、曲艺、传统体育游艺与杂技、传统美术、传统技艺、传统医药、民俗。如果视频内容不属于这些类别，请标注为"其他"并说明。
2）非遗相关物质文化元素识别：识别并列出视频中出现的道具（如面具、锣鼓、法器、织布机等）、服饰（民族服饰、舞台服饰等）、建筑与场地（庙宇、戏台、作坊、庭院等），并尽可能关联至相应民族或地区。
3）非遗相关非物质文化元素识别：识别仪式元素、技艺流程、口述传统文本、身体动作序列（舞蹈/戏曲身段等）。
4）社会文化语境与场域识别：从影像和语音推断文化情境，包括：
   - 城乡场景：乡村社区/城市街区/市场场域
   - 使用语境：仪式化/娱乐化/商业化/教学演示
   - 观众类型：本地居民/游客/官方人员/学徒
5）技艺/仪式流程结构化解析：
   - 技艺流程自动分段（如"备料 → 制作 → 表演 → 收尾"）
   - 仪式程序自动分段（如"迎神 → 正仪式 → 送神"）
   - 关键步骤识别（如手工艺中的"揉泥、拉坯、施釉、烧制"等）

模块四-影像技术与风格分析：
1）声音内容分析：环境音类型、传统乐器识别、是否有旁白、唱腔类型等
2）场景与景别：列出全片涉及的所有场景（如家庭聚会、社区活动、舞台表演、后台准备、儿童教育等）和景别（特写、近景、中景、远景、大全景等）
3）色彩风格分析：分析色调、饱和度、民族色彩特征等
4）镜头运动类型识别：固定机位、推拉摇移、手持镜头、跟拍镜头、航拍镜头（无人机）等
5）镜头节奏与镜头长度统计：分析平均镜头长度（ASL）、稳定vs快剪比例、长镜头分布等

模块五-人物与社会关系结构：
1）人物的社会身份信息：从语义推断人物身份，如传承人、学徒、村干部/社区工作者、商业经营者等
2）涉及的人物关系：如师徒、家庭成员、社区角色等
3）社区或群体结构：如村落、剧团、家庭、组织的结构与互动方式

模块六-叙事与语义层级的自动分析：
1）叙事结构识别（可多选）：线性叙事、非线性叙事、环状结构、并置结构、多声部叙事、观察式叙事、提问式（访谈驱动）叙事、过程性（技艺流程）叙事、档案式/历史拼贴叙事、片段式/段落式叙事、仪式化叙事结构、师徒/传承叙事结构、空间迁移叙事、季节/节令叙事、冲突驱动文化叙事
2）主题聚类/扎根理论编码：识别视频中的主要主题和子主题
3）价值取向与情感分析：分析传承情感、乡愁、商业化焦虑等情感和价值取向
4）冲突点识别：如代际冲突、资源争夺、地方政策影响等

字段类型与标注规则（必须遵守）：
- 数组字段：输出JSON字符串数组；没有识别到内容时输出[]，不要输出逗号分隔的单个字符串。
- 多选枚举字段：只能从下面给出的选项中选择，可多选；不要创造选项外的新类别。
- 单选枚举字段：只能输出一个选项字符串；无法判断时输出“无法确定”。
- 布尔字段：只输出true或false；无法判断时输出null。
- 开放文本字段：输出字符串；无法判断时输出“根据视频内容无法确定”。
- 开放文本数组字段：每个独立事实作为数组的一项；无法判断时输出[]。
- 流程字段：输出按视频出现顺序排列的阶段/步骤字符串数组；不要伪造开始时间和结束时间，本版本不要求时间码。

多选枚举字段及允许选项：
1. 模块三_非遗文化信息.类型：民间文学、传统音乐、传统舞蹈、传统戏剧、曲艺、传统体育游艺与杂技、传统美术、传统技艺、传统医药、民俗、其他。
2. 模块三_非遗文化信息.使用语境：仪式化、娱乐化、商业化、教学演示、日常生活、其他。
3. 模块三_非遗文化信息.观众类型：本地居民、游客、官方人员、学徒、儿童、其他。
4. 模块四_影像技术与风格分析.镜头运动类型：固定机位、推镜头、拉镜头、摇镜头、移镜头、推拉摇移、手持镜头、跟拍镜头、航拍镜头（无人机）、其他。
5. 模块六_叙事与语义层级分析.叙事结构：线性叙事、非线性叙事、环状结构、并置结构、多声部叙事、观察式叙事、提问式（访谈驱动）叙事、过程性（技艺流程）叙事、档案式/历史拼贴叙事、片段式/段落式叙事、仪式化叙事结构、师徒/传承叙事结构、空间迁移叙事、季节/节令叙事、冲突驱动文化叙事、其他。

单选枚举字段及允许选项：
1. 模块三_非遗文化信息.社会文化语境与场域.城乡场景：乡村社区、城市街区、市场场域、家庭空间、宗教/仪式场所、舞台/表演场所、作坊/生产场所、其他、无法确定。
2. 模块四_影像技术与风格分析.声音内容分析.是否有旁白：true、false或null（JSON布尔值，不要输出字符串）。

开放文本数组字段：
- 道具、服饰、建筑与场地、仪式元素、技艺流程、身体动作序列、环境音类型、传统乐器识别、场景、景别、人物社会身份、人物关系、主要主题、子主题、价值取向、情感分析、冲突点识别。

开放文本字段：
- 民族或地区关联、口述传统文本、唱腔类型、色调、饱和度、民族色彩特征、平均镜头长度、稳定vs快剪比例、长镜头分布、社区群体结构。

嵌套流程字段的具体含义：
- 技艺流程分段：技艺从准备、制作到完成的阶段，例如“备料”“制作”“表演”“收尾”。
- 仪式程序分段：仪式按顺序划分的程序，例如“迎神”“正仪式”“送神”。
- 关键步骤：完成技艺或仪式不可缺少的具体动作，例如“揉泥”“拉坯”“施釉”“烧制”。
- 主题聚类：主要主题是核心议题，子主题是其下的具体议题；不要把整段分析塞入一个数组项。
- 价值取向与情感：价值取向描述视频表达的文化/社会态度，情感分析描述传承情感、乡愁、商业化焦虑等情绪。
- 冲突点识别：仅填写视频明确呈现或有充分证据推断的冲突，如代际冲突、资源争夺、地方政策影响；无证据时输出[]。

请严格按照以下JSON格式输出，确保输出是一个完整的JSON对象，以{开头，以}结尾：
{
  "模块三_非遗文化信息": {
    "类型": ["类别1", "类别2"],
    "物质文化元素": {
      "道具": ["道具1", "道具2"],
      "服饰": ["服饰1", "服饰2"],
      "建筑与场地": ["建筑1", "建筑2"],
      "民族或地区关联": "关联信息"
    },
    "非物质文化元素": {
      "仪式元素": ["元素1", "元素2"],
      "技艺流程": ["流程1", "流程2"],
      "口述传统文本": "文本内容或描述",
      "身体动作序列": ["动作1", "动作2"]
    },
    "社会文化语境与场域": {
      "城乡场景": "场景类型",
      "使用语境": ["语境1", "语境2"],
      "观众类型": ["类型1", "类型2"]
    },
    "技艺仪式流程解析": {
      "技艺流程分段": ["阶段1", "阶段2", "阶段3"],
      "仪式程序分段": ["程序1", "程序2", "程序3"],
      "关键步骤": ["步骤1", "步骤2", "步骤3"]
    }
  },
  "模块四_影像技术与风格分析": {
    "声音内容分析": {
      "环境音类型": ["类型1", "类型2"],
      "传统乐器识别": ["乐器1", "乐器2"],
      "是否有旁白": true/false,
      "唱腔类型": "唱腔类型或描述"
    },
    "场景与景别": {
      "场景": ["场景1", "场景2"],
      "景别": ["景别1", "景别2"]
    },
    "色彩风格分析": {
      "色调": "色调描述",
      "饱和度": "饱和度描述",
      "民族色彩特征": "特征描述"
    },
    "镜头运动类型": ["类型1", "类型2"],
    "镜头节奏统计": {
      "平均镜头长度": "ASL描述",
      "稳定vs快剪比例": "比例描述",
      "长镜头分布": "分布描述"
    }
  },
  "模块五_人物与社会关系结构": {
    "人物社会身份": ["身份1", "身份2"],
    "人物关系": ["关系1", "关系2"],
    "社区群体结构": "结构描述"
  },
  "模块六_叙事与语义层级分析": {
    "叙事结构": ["结构1", "结构2"],
    "主题聚类": {
      "主要主题": ["主题1", "主题2"],
      "子主题": ["子主题1", "子主题2"]
    },
    "价值取向与情感": {
      "价值取向": ["取向1", "取向2"],
      "情感分析": ["情感1", "情感2"]
    },
    "冲突点识别": ["冲突1", "冲突2"]
  }
}

请确保输出的JSON格式正确，所有字段都要填写，如果某项无法确定，请填写"根据视频内容无法确定"或空数组[]。"""
        return prompt
    
    def analyze_video(self, video_path: str, output_path: Optional[str] = None) -> Dict[str, Any]:
        """
        分析视频并返回结构化结果
        
        Args:
            video_path: 视频文件路径
            output_path: 输出JSON文件路径，如果为None则自动生成
            
        Returns:
            分析结果的字典
        """
        # 检查视频文件是否存在
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        
        print(f"📹 开始分析视频: {os.path.basename(video_path)}")
        
        # 构建消息
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的文化影像分析专家，擅长从视频中提取文化信息、技术特征和叙事结构。"
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": self._build_analysis_prompt()},
                    {
                        "type": "video",
                        "video": video_path,
                        "total_pixels": 4096 * 28 * 28,
                        "min_pixels": 16 * 28 * 28,
                        "nframes": 64
                    }
                ]
            }
        ]
        
        # 文本模板生成
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        
        # 提取视觉信息
        image_inputs, video_inputs, video_kwargs = process_vision_info(messages, return_video_kwargs=True)
        
        # 构建模型输入
        inputs = self.processor(
            text=[text],
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
            **video_kwargs,
        ).to("cuda")
        
        print("🔄 正在进行模型推理...")
        # 清理GPU缓存
        torch.cuda.empty_cache()
        
        # 推理生成（增加max_new_tokens以支持更长的输出）
        generated_ids = self.model.generate(
            **inputs,
            max_new_tokens=4096,  # 增加token数量以支持详细分析
            do_sample=True,
            temperature=0.7,
            top_p=0.95
        )
        
        generated_ids_trimmed = [
            out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = self.processor.batch_decode(
            generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]
        
        print("📝 正在解析分析结果...")
        
        # 尝试解析JSON
        result = self._parse_output(output_text)
        
        # 保存结果
        if output_path is None:
            base_name = os.path.splitext(os.path.basename(video_path))[0]
            output_path = os.path.join(os.path.dirname(video_path), f"{base_name}_analysis.json")
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"✅ 分析完成！结果已保存到: {output_path}")
        
        return result
    
    def _parse_output(self, output_text: str) -> Dict[str, Any]:
        """
        解析模型输出为JSON格式
        
        Args:
            output_text: 模型原始输出文本
            
        Returns:
            解析后的JSON字典
        """
        # 尝试提取JSON部分
        output_text = output_text.strip()
        
        # 查找第一个 { 和最后一个 }
        start_idx = output_text.find("{")
        end_idx = output_text.rfind("}")
        
        if start_idx == -1 or end_idx == -1 or start_idx >= end_idx:
            print("⚠️ 警告：无法找到完整的JSON结构，保存原始输出")
            return {
                "error": "无法解析为JSON格式",
                "raw_output": output_text
            }
        
        json_str = output_text[start_idx:end_idx + 1]
        
        try:
            result = json.loads(json_str)
            return result
        except json.JSONDecodeError as e:
            print(f"⚠️ JSON解析错误: {e}")
            print("尝试修复JSON格式...")
            
            # 尝试修复常见的JSON问题
            try:
                # 替换单引号为双引号
                json_str = json_str.replace("'", '"')
                # 尝试修复未转义的换行符
                json_str = json_str.replace('\n', '\\n')
                result = json.loads(json_str)
                return result
            except:
                # 如果还是失败，保存原始输出
                error_path = os.path.join(os.path.dirname(__file__), "error_output.txt")
                with open(error_path, "w", encoding="utf-8") as f:
                    f.write(output_text)
                print(f"❌ JSON解析失败，原始输出已保存到: {error_path}")
                return {
                    "error": "JSON解析失败",
                    "raw_output": output_text
                }


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="基于Qwen2.5-VL的视频理解分析Demo")
    parser.add_argument(
        "--video",
        type=str,
        required=True,
        help="视频文件路径"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出JSON文件路径（可选，默认自动生成）"
    )
    parser.add_argument(
        "--model_path",
        type=str,
        default="/home/u20240148/project/Qwen2.5-VL/Qwenvl_72B",
        help="模型路径"
    )
    parser.add_argument(
        "--gpu_ids",
        type=str,
        default=None,
        help="指定使用的GPU ID，格式如 '5,6' 或 '5'。如果为None，使用所有可用GPU"
    )
    
    args = parser.parse_args()
    
    # 创建分析器
    analyzer = VideoAnalysisDemo(model_path=args.model_path, gpu_ids=args.gpu_ids)
    
    # 分析视频
    try:
        result = analyzer.analyze_video(args.video, args.output)
        print("\n" + "="*50)
        print("分析结果预览:")
        print("="*50)
        print(json.dumps(result, indent=2, ensure_ascii=False)[:500] + "...")
    except Exception as e:
        print(f"❌ 分析过程中出现错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

