import os
import json
import torch
from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info

# 设置视频路径
video_path = "/home/u20240148/project/video-vl/ea9fe2e3209eccbf5471ac6c6656b51a_raw.mp4"
assert os.path.exists(video_path), f"❌ 视频文件不存在: {video_path}"

# 加载模型和处理器
model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
    "/home/u20240148/project/Qwen2.5-VL/Qwenvl_72B", torch_dtype="auto", device_map="auto"
)
processor = AutoProcessor.from_pretrained("/home/u20240148/project/Qwen2.5-VL/Qwenvl_72B")

# 构建消息
messages = [
    {"role": "system", "content": "你是一个纪录片分析高手，善于发现影片中少数民族特色"},
    {"role": "user", "content": [
        {"type": "text", "text": "请你结合视频字幕和视频中包含的音频，详细描述视频片段的内容，并判断类别，类别的定义是所属视频素材素材内容类别，可以分【风光】、【采访】、【人物特写】、【服饰】、【祭祀】、【舞蹈】等，你也可以根据素材内容总结出新的具体分类。景别项：包括全景、近景、中景、远景、半身近景、半身中景、特写等。尝试分析出来视频中的方言、民族，如果方言、民族不能确定请回复“根据视频内容不能确定”。请用纯文本中文，不要转义，输出一定要以{开头，以}结尾，只有一个json对象,class列出影片所属的类别，可有多个类别用逗号隔开；object请列举视频片段出现的物体，不用重复；description请详细描述，除英文原文外，全部使用中文，dialect描述视频中的语言或“根据视频内容不能确定”，可以有多个；Minzu描述视频中的中国民族类别或“根据视频内容不能确定”，shot描述景别类，可以有多个，形成以下格式：{\"class\":\"a,b,c,...\",\"object\": \"a,b,c,...\",\"dialect\"：\"判断出的所属的民族或“根据视频内容不能确定”\",\"Minzu\"：\"判断出的所属的民族或“根据视频内容不能确定”\",\"shot\"：\"判断出的所采用的景别\",\"description\":\"描述性语句\"}"},
        {
            "type": "video",
            "video": video_path,
            "total_pixels": 20480 * 28 * 28,
            "min_pixels": 16 * 28 * 28
        }
    ]}
]

# 文本模板生成
text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

# 提取视觉信息
image_inputs, video_inputs, video_kwargs = process_vision_info(messages, return_video_kwargs=True)

# 构建模型输入
inputs = processor(
    text=[text],
    #images=image_inputs,
    videos=video_inputs,
    padding=True,
    return_tensors="pt",
    **video_kwargs,
).to("cuda")

# 推理生成
generated_ids = model.generate(**inputs, max_new_tokens=512, do_sample=True, temperature=0.7, top_p=0.95)
generated_ids_trimmed = [
    out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
]
output_text = processor.batch_decode(
    generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
)[0]

# 尝试解析为 JSON 对象
try:
    # 确保结尾有 }
    json_str = output_text.strip().split("}")[0] + "}"
    output_json = json.loads(json_str)

    # 获取输出文件名
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    json_output_path = os.path.join(os.path.dirname(video_path), base_name + ".json")

    # 保存为 json 文件
    with open(json_output_path, "w", encoding="utf-8") as f:
        json.dump(output_json, f, indent=2, ensure_ascii=False)

    print(f"✅ 成功保存分析结果到: {json_output_path}")
except Exception as e:
    print("❌ 无法解析输出为JSON：")
    print(output_text)
    # 可选：保存原始结果
    error_path = os.path.join(os.path.dirname(video_path), "error_" + base_name + ".txt")
    with open(error_path, "w", encoding="utf-8") as f:
        f.write(output_text)
    print(f"⛔ 原始结果已保存到: {error_path}")
