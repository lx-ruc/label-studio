# 快速核查：这些片子里到底有没有食物/供品（是/否 + 位置）
import base64, json, os, sys, urllib.request
import cv2

sys.path.insert(0, "scripts")
import qwen_boxes

PROMPT = (
    "画面中有没有食物或供品（饭菜、糕点、水果、供桌上的祭品、锅里碗里的吃食）？\n"
    "只回答两行：第一行「有」或「没有」；若有，第二行给归一化 bbox [x1,y1,x2,y2]（0-1000）。\n"
    "不要把锅碗瓢盆本身、桌子、人当食物。"
)

CLIPS = [("ea9fe2e3209eccbf5471ac6c6656b51a_raw.mp4", [8, 20, 35, 50, 65]),
         ("482344871227e9f9193de1e2a7e67ec5_raw.mp4", [10, 30, 50, 70]),
         ("SD0012003522630060003.mp4", [3, 10, 15]),
         ("SD0022004522630060044.mp4", [10, 25, 45, 60])]

for name, ts in CLIPS:
    cap = cv2.VideoCapture("data/clips4/" + name)
    for t in ts:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, fr = cap.read()
        if not ok:
            continue
        ok, buf = cv2.imencode(".jpg", fr, [cv2.IMWRITE_JPEG_QUALITY, 85])
        b64 = base64.b64encode(bytes(buf)).decode()
        body = {"model": qwen_boxes.MODEL, "temperature": 0,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url",
                     "image_url": {"url": "data:image/jpeg;base64," + b64}},
                    {"type": "text", "text": PROMPT}]}]}
        req = urllib.request.Request(
            qwen_boxes.API, data=json.dumps(body).encode(),
            headers={"Authorization": "Bearer " + os.environ["QWEN_API_KEY"],
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            txt = json.loads(r.read())["choices"][0]["message"]["content"]
        print(f"{name[:8]} @{t}s -> {txt.strip()[:80]}", flush=True)
    cap.release()
