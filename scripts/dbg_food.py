# 打印一帧的食物检测原始回复，排查 0 框原因
import base64, json, os, sys, urllib.request
import cv2

sys.path.insert(0, "scripts")
import qwen_boxes
from det_extra import FOOD_PROMPT

# 与 detect_food 内相同的词表扩充
qwen_boxes.ALLOWED = list(qwen_boxes.ALLOWED) + [
    "食物", "食物与供品", "供品", "祭品", "糕点", "水果", "点心", "饭菜"]

clip = sys.argv[1]
times = [float(x) for x in (sys.argv[2].split(",") if len(sys.argv) > 2 else ["10"])]

cap = cv2.VideoCapture("data/clips4/" + clip)
for t in times:
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, fr = cap.read()
    if not ok:
        print(f"@{t}s 读帧失败")
        continue
    ok, buf = cv2.imencode(".jpg", fr, [cv2.IMWRITE_JPEG_QUALITY, 85])
    b64 = base64.b64encode(bytes(buf)).decode()

    body = {
        "model": qwen_boxes.MODEL,
        "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
            {"type": "text", "text": FOOD_PROMPT},
        ]}],
    }
    req = urllib.request.Request(
        qwen_boxes.API, data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + os.environ["QWEN_API_KEY"],
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        txt = json.loads(r.read())["choices"][0]["message"]["content"]
    print(f"=== @{t}s 原始回复 ===")
    print(txt[:600])
