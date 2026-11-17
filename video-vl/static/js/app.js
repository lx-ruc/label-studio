/* =========================================================================
   视频文化影像分析系统 - 前端交互
   ========================================================================= */
(function () {
    "use strict";

    // ---- 工具函数 ----
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    function esc(s) {
        if (s === null || s === undefined) return "";
        return String(s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function fmtSize(bytes) {
        if (!bytes) return "0 B";
        const units = ["B", "KB", "MB", "GB"];
        let i = 0;
        while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
        return bytes.toFixed(2) + " " + units[i];
    }

    // ---- 状态 ----
    let modelReady = false;
    let modelPollTimer = null;
    let analysisPollTimer = null;
    let selectedFile = null;

    // ---- 标签切换 ----
    $$(".tab").forEach((tab) => {
        tab.addEventListener("click", () => {
            $$(".tab").forEach((t) => t.classList.remove("active"));
            $$(".tab-panel").forEach((p) => p.classList.remove("active"));
            tab.classList.add("active");
            $("#tab-" + tab.dataset.tab).classList.add("active");
        });
    });

    function switchTab(name) {
        const tab = document.querySelector(`.tab[data-tab="${name}"]`);
        if (tab) tab.click();
    }

    // ---- 模型状态 ----
    function setModelBadge(status, text) {
        const badge = $("#modelStatusBadge");
        badge.className = "status-dot " + (status || "");
        $("#modelStatusText").textContent = text;
    }

    async function refreshModelStatus() {
        try {
            const res = await fetch("/api/model-status");
            const data = await res.json();
            if (data.status === "ready") {
                modelReady = true;
                setModelBadge("ready", "模型已就绪");
                $("#loadModelBtn").disabled = false;
                $("#loadModelBtn").textContent = "模型已加载";
                $("#analyzeBtn").disabled = !selectedFile;
            } else if (data.status === "loading") {
                modelReady = false;
                setModelBadge("loading", "模型加载中…");
                $("#loadModelBtn").disabled = true;
                $("#loadModelBtn").textContent = "加载中…";
            } else if (data.status === "error") {
                modelReady = false;
                setModelBadge("error", "模型加载失败");
                $("#loadModelBtn").disabled = false;
                $("#loadModelBtn").textContent = "重新加载";
            } else {
                modelReady = false;
                setModelBadge("", "模型未加载");
                $("#loadModelBtn").disabled = false;
                $("#loadModelBtn").textContent = "加载模型";
            }
        } catch (e) {
            console.error(e);
        }
    }

    // 加载模型
    $("#loadModelBtn").addEventListener("click", async () => {
        const modelPath = $("#modelPath").value.trim();
        const gpuIds = $("#gpuIds").value.trim();
        if (!modelPath) { alert("请填写模型路径"); return; }

        const fd = new FormData();
        fd.append("model_path", modelPath);
        fd.append("gpu_ids", gpuIds);

        setModelBadge("loading", "模型加载中…");
        $("#loadModelBtn").disabled = true;
        $("#loadModelBtn").textContent = "加载中…";

        try {
            const res = await fetch("/api/load-model", { method: "POST", body: fd });
            const data = await res.json();
            if (!data.ok) {
                setModelBadge("error", "加载失败");
                $("#loadModelBtn").disabled = false;
                $("#loadModelBtn").textContent = "加载模型";
                alert(data.msg || "加载失败");
                return;
            }
            // 开始轮询
            if (modelPollTimer) clearInterval(modelPollTimer);
            modelPollTimer = setInterval(refreshModelStatus, 3000);
        } catch (e) {
            setModelBadge("error", "加载失败");
            $("#loadModelBtn").disabled = false;
            $("#loadModelBtn").textContent = "加载模型";
            alert("请求失败: " + e.message);
        }
    });

    // ---- 文件上传 ----
    const uploadZone = $("#uploadZone");
    const videoInput = $("#videoInput");

    videoInput.addEventListener("change", (e) => {
        if (e.target.files.length) handleFile(e.target.files[0]);
    });

    ["dragover", "dragenter"].forEach((evt) => {
        uploadZone.addEventListener(evt, (e) => {
            e.preventDefault();
            uploadZone.classList.add("dragover");
        });
    });
    ["dragleave", "drop"].forEach((evt) => {
        uploadZone.addEventListener(evt, (e) => {
            e.preventDefault();
            uploadZone.classList.remove("dragover");
        });
    });
    uploadZone.addEventListener("drop", (e) => {
        e.preventDefault();
        if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
    });

    function handleFile(file) {
        selectedFile = file;
        $("#fileName").textContent = file.name;
        $("#fileSize").textContent = fmtSize(file.size);
        $("#fileInfoWrap").style.display = "block";

        // 视频预览
        const video = $("#videoPreview");
        if (video.src) URL.revokeObjectURL(video.src);
        video.src = URL.createObjectURL(file);

        // 分析按钮状态
        $("#analyzeBtn").disabled = !modelReady;
        $("#downloadWrap").style.display = "none";
    }

    // ---- 分析 ----
    $("#analyzeBtn").addEventListener("click", async () => {
        if (!selectedFile) { alert("请先选择视频文件"); return; }
        if (!modelReady) { alert("模型未加载，请先加载模型"); return; }

        const fd = new FormData();
        fd.append("video", selectedFile);

        $("#analyzeBtn").disabled = true;
        $("#analyzeBtn").textContent = "分析中…";
        $("#progressWrap").style.display = "block";
        $("#downloadWrap").style.display = "none";
        setProgress(5, "提交分析任务…");

        try {
            const res = await fetch("/api/analyze", { method: "POST", body: fd });
            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.detail || "分析请求失败");
            }
            // 开始轮询分析状态
            if (analysisPollTimer) clearInterval(analysisPollTimer);
            analysisPollTimer = setInterval(pollAnalysis, 2000);
        } catch (e) {
            showAlert("error", "分析失败: " + e.message);
            $("#analyzeBtn").disabled = false;
            $("#analyzeBtn").textContent = "开始分析";
            $("#progressWrap").style.display = "none";
        }
    });

    function setProgress(percent, stage) {
        $("#progressFill").style.width = percent + "%";
        $("#progressPercent").textContent = Math.round(percent) + "%";
        if (stage) $("#progressStage").textContent = stage;
    }

    async function pollAnalysis() {
        try {
            const res = await fetch("/api/analysis-status");
            const data = await res.json();

            if (data.status === "running") {
                setProgress(data.progress || 30, data.stage || "分析中…");
            } else if (data.status === "done") {
                setProgress(100, "分析完成");
                clearInterval(analysisPollTimer);
                analysisPollTimer = null;
                $("#analyzeBtn").disabled = false;
                $("#analyzeBtn").textContent = "开始分析";
                $("#downloadWrap").style.display = "block";
                showResult(data.result);
                switchTab("result");
            } else if (data.status === "error") {
                clearInterval(analysisPollTimer);
                analysisPollTimer = null;
                $("#analyzeBtn").disabled = false;
                $("#analyzeBtn").textContent = "开始分析";
                $("#progressWrap").style.display = "none";
                showResult(null, data.error);
                switchTab("result");
            }
        } catch (e) {
            console.error(e);
        }
    }

    function showAlert(type, msg) {
        const wrap = $("#analysisAlert");
        wrap.innerHTML = `<div class="alert alert-${type}">${esc(msg)}</div>`;
        setTimeout(() => { wrap.innerHTML = ""; }, 6000);
    }

    // =========================================================================
    // 结果渲染
    // =========================================================================
    function showResult(result, error) {
        const container = $("#resultContainer");
        if (error) {
            container.innerHTML = `
                <div class="alert alert-error">分析出错: ${esc(error)}</div>`;
            return;
        }
        if (!result) {
            container.innerHTML = `
                <div class="result-empty">
                    <div class="empty-icon">📊</div>
                    <div class="empty-text">暂无分析结果</div>
                    <div class="empty-hint">请先上传视频并完成分析</div>
                </div>`;
            return;
        }
        if (result.error) {
            container.innerHTML = `
                <div class="alert alert-error">分析出错: ${esc(result.error)}</div>`;
            return;
        }

        const formatted = formatResult(result);
        container.innerHTML = renderSummary(formatted) + renderModules(formatted) + renderJson(result);
    }

    function formatResult(result) {
        const f = {};
        if (result["模块三_非遗文化信息"]) {
            f.m3 = result["模块三_非遗文化信息"];
        }
        if (result["模块四_影像技术与风格分析"]) {
            f.m4 = result["模块四_影像技术与风格分析"];
        }
        if (result["模块五_人物与社会关系结构"]) {
            f.m5 = result["模块五_人物与社会关系结构"];
        }
        if (result["模块六_叙事与语义层级分析"]) {
            f.m6 = result["模块六_叙事与语义层级分析"];
        }
        return f;
    }

    function countItems(d, keys) {
        let total = 0;
        keys.forEach((k) => {
            const v = d ? d[k] : null;
            if (Array.isArray(v)) total += v.length;
            else if (v && typeof v === "object") {
                Object.values(v).forEach((sv) => {
                    if (Array.isArray(sv)) total += sv.length;
                    else if (sv && !["", "未确定", "根据视频内容无法确定"].includes(String(sv))) total += 1;
                });
            } else if (v !== null && v !== undefined && !["", "未确定", "根据视频内容无法确定"].includes(String(v))) {
                total += 1;
            }
        });
        return total;
    }

    function renderSummary(f) {
        const c3 = countItems(f.m3, ["类型", "物质文化元素", "非物质文化元素", "社会文化语境与场域", "技艺仪式流程解析"]);
        const c4 = countItems(f.m4, ["声音内容分析", "场景与景别", "色彩风格分析", "镜头运动类型", "镜头节奏统计"]);
        const c5 = countItems(f.m5, ["人物社会身份", "人物关系", "社区群体结构"]);
        const c6 = countItems(f.m6, ["叙事结构", "主题聚类", "价值取向与情感", "冲突点识别"]);

        const metrics = [
            { v: c3, l: "非遗文化元素", c: "#b45309" },
            { v: c4, l: "影像技术风格", c: "#1d4ed8" },
            { v: c5, l: "人物社会关系", c: "#0e7490" },
            { v: c6, l: "叙事语义层级", c: "#7c3aed" },
        ].map((m) => `
            <div class="metric" style="--accent:${m.c}">
                <div class="metric-value" style="color:${m.c}">${m.v}</div>
                <div class="metric-label">${esc(m.l)}</div>
            </div>`).join("");

        const types = (f.m3 && f.m3["类型"]) || [];
        const narrative = (f.m6 && f.m6["叙事结构"]) || [];
        const material = (f.m3 && f.m3["物质文化元素"]) || {};
        const elements = [].concat(material["道具"] || [], material["服饰"] || [], material["建筑与场地"] || []);
        const movement = (f.m4 && f.m4["镜头运动类型"]) || [];

        return `
        <div class="module-title">📊 分析概览</div>
        <div class="metrics">${metrics}</div>

        <div class="grid-2">
            <div class="card">
                <div class="card-header"><div class="card-title"><span class="icon">📋</span>非遗类型</div></div>
                <div class="card-body tight">${chips(types, "chip-accent", "未识别到非遗类型")}</div>
            </div>
            <div class="card">
                <div class="card-header"><div class="card-title"><span class="icon">📖</span>叙事结构</div></div>
                <div class="card-body tight">${chips(narrative, "chip-info", "未识别到叙事结构")}</div>
            </div>
            <div class="card">
                <div class="card-header"><div class="card-title"><span class="icon">🎭</span>非遗相关元素</div></div>
                <div class="card-body tight">${chips(elements, "", "未识别到相关元素")}</div>
            </div>
            <div class="card">
                <div class="card-header"><div class="card-title"><span class="icon">🎬</span>镜头运动</div></div>
                <div class="card-body tight">${chips(movement, "", "未识别到镜头运动类型")}</div>
            </div>
        </div>`;
    }

    function renderModules(f) {
        return `
        <div class="card">
            <div class="card-header"><div class="card-title"><span class="icon">🏛️</span>模块三 · 非遗文化信息</div></div>
            <div class="card-body">${renderModule3(f.m3)}</div>
        </div>
        <div class="card">
            <div class="card-header"><div class="card-title"><span class="icon">🎥</span>模块四 · 影像技术与风格分析</div></div>
            <div class="card-body">${renderModule4(f.m4)}</div>
        </div>
        <div class="card">
            <div class="card-header"><div class="card-title"><span class="icon">👥</span>模块五 · 人物与社会关系结构</div></div>
            <div class="card-body">${renderModule5(f.m5)}</div>
        </div>
        <div class="card">
            <div class="card-header"><div class="card-title"><span class="icon">📖</span>模块六 · 叙事与语义层级分析</div></div>
            <div class="card-body">${renderModule6(f.m6)}</div>
        </div>`;
    }

    // ---- 模块三 ----
    function renderModule3(d) {
        if (!d) return emptyInline("未找到模块三的分析结果");
        const types = d["类型"] || [];
        const material = d["物质文化元素"] || {};
        const immaterial = d["非物质文化元素"] || {};
        const context = d["社会文化语境与场域"] || {};
        const process = d["技艺仪式流程解析"] || {};

        return `
        <div class="sub-title">📋 类型分类（十大门类）</div>
        ${chips(types, "chip-accent", "未识别到非遗类型")}

        <div class="grid-2" style="margin-top:14px;">
            <div>
                <div class="sub-title">🏛️ 物质文化元素</div>
                ${material["道具"] ? `<div class="sub-title" style="font-size:12px;color:var(--text-muted)">道具</div>${chips(material["道具"])}` : ""}
                ${material["服饰"] ? `<div class="sub-title" style="font-size:12px;color:var(--text-muted)">服饰</div>${chips(material["服饰"])}` : ""}
                ${material["建筑与场地"] ? `<div class="sub-title" style="font-size:12px;color:var(--text-muted)">建筑与场地</div>${chips(material["建筑与场地"])}` : ""}
                ${material["民族或地区关联"] ? kv("民族或地区关联", material["民族或地区关联"]) : ""}
                ${!material["道具"] && !material["服饰"] && !material["建筑与场地"] && !material["民族或地区关联"] ? emptyInline("未识别到物质文化元素") : ""}
            </div>
            <div>
                <div class="sub-title">🎭 非物质文化元素</div>
                ${immaterial["仪式元素"] ? `<div class="sub-title" style="font-size:12px;color:var(--text-muted)">仪式元素</div>${chips(immaterial["仪式元素"])}` : ""}
                ${immaterial["技艺流程"] ? `<div class="sub-title" style="font-size:12px;color:var(--text-muted)">技艺流程</div>${chips(immaterial["技艺流程"])}` : ""}
                ${immaterial["身体动作序列"] ? `<div class="sub-title" style="font-size:12px;color:var(--text-muted)">身体动作序列</div>${chips(immaterial["身体动作序列"])}` : ""}
                ${immaterial["口述传统文本"] ? kv("口述传统文本", immaterial["口述传统文本"]) : ""}
                ${!immaterial["仪式元素"] && !immaterial["技艺流程"] && !immaterial["身体动作序列"] && !immaterial["口述传统文本"] ? emptyInline("未识别到非物质文化元素") : ""}
            </div>
        </div>

        <div class="grid-2" style="margin-top:14px;">
            <div>
                <div class="sub-title">🌍 社会文化语境与场域</div>
                ${kv("城乡场景", context["城乡场景"])}
                ${context["使用语境"] ? `<div class="sub-title" style="font-size:12px;color:var(--text-muted)">使用语境</div>${chips(context["使用语境"], "chip-info")}` : ""}
                ${context["观众类型"] ? `<div class="sub-title" style="font-size:12px;color:var(--text-muted)">观众类型</div>${chips(context["观众类型"])}` : ""}
                ${!context["城乡场景"] && !context["使用语境"] && !context["观众类型"] ? emptyInline("未识别到社会文化语境") : ""}
            </div>
            <div>
                <div class="sub-title">🔄 技艺/仪式流程解析</div>
                ${process["技艺流程分段"] ? flow(process["技艺流程分段"], "技艺流程分段") : ""}
                ${process["仪式程序分段"] ? flow(process["仪式程序分段"], "仪式程序分段") : ""}
                ${process["关键步骤"] ? `<div class="sub-title" style="font-size:12px;color:var(--text-muted)">关键步骤</div>${chips(process["关键步骤"], "chip-accent")}` : ""}
                ${!process["技艺流程分段"] && !process["仪式程序分段"] && !process["关键步骤"] ? emptyInline("未识别到流程解析") : ""}
            </div>
        </div>`;
    }

    // ---- 模块四 ----
    function renderModule4(d) {
        if (!d) return emptyInline("未找到模块四的分析结果");
        const audio = d["声音内容分析"] || {};
        const scene = d["场景与景别"] || {};
        const color = d["色彩风格分析"] || {};
        const movement = d["镜头运动类型"] || [];
        const rhythm = d["镜头节奏统计"] || {};

        return `
        <div class="grid-2">
            <div>
                <div class="sub-title">🔊 声音内容分析</div>
                ${audio["环境音类型"] ? `<div class="sub-title" style="font-size:12px;color:var(--text-muted)">环境音类型</div>${chips(audio["环境音类型"])}` : ""}
                ${audio["传统乐器识别"] ? `<div class="sub-title" style="font-size:12px;color:var(--text-muted)">传统乐器识别</div>${chips(audio["传统乐器识别"], "chip-accent")}` : ""}
                ${kv("是否有旁白", audio["是否有旁白"] === true ? "是" : (audio["是否有旁白"] === false ? "否" : audio["是否有旁白"]))}
                ${audio["唱腔类型"] ? kv("唱腔类型", audio["唱腔类型"]) : ""}
                ${!audio["环境音类型"] && !audio["传统乐器识别"] && audio["是否有旁白"] === undefined && !audio["唱腔类型"] ? emptyInline("未识别到声音内容") : ""}
            </div>
            <div>
                <div class="sub-title">🎨 色彩风格分析</div>
                ${kv("色调", color["色调"])}
                ${kv("饱和度", color["饱和度"])}
                ${kv("民族色彩特征", color["民族色彩特征"])}
                ${!color["色调"] && !color["饱和度"] && !color["民族色彩特征"] ? emptyInline("未识别到色彩风格") : ""}
            </div>
        </div>
        <div class="grid-2" style="margin-top:14px;">
            <div>
                <div class="sub-title">📹 场景与景别</div>
                ${scene["场景"] ? `<div class="sub-title" style="font-size:12px;color:var(--text-muted)">场景</div>${chips(scene["场景"])}` : ""}
                ${scene["景别"] ? `<div class="sub-title" style="font-size:12px;color:var(--text-muted)">景别</div>${chips(scene["景别"], "chip-info")}` : ""}
                ${!scene["场景"] && !scene["景别"] ? emptyInline("未识别到场景与景别") : ""}
            </div>
            <div>
                <div class="sub-title">🎬 镜头运动类型</div>
                ${chips(movement, "chip-accent", "未识别到镜头运动类型")}
                <div class="sub-title" style="margin-top:12px;">⏱️ 镜头节奏统计</div>
                ${kv("平均镜头长度", rhythm["平均镜头长度"])}
                ${kv("稳定 vs 快剪比例", rhythm["稳定vs快剪比例"])}
                ${kv("长镜头分布", rhythm["长镜头分布"])}
                ${!rhythm["平均镜头长度"] && !rhythm["稳定vs快剪比例"] && !rhythm["长镜头分布"] ? emptyInline("未识别到镜头节奏统计") : ""}
            </div>
        </div>`;
    }

    // ---- 模块五 ----
    function renderModule5(d) {
        if (!d) return emptyInline("未找到模块五的分析结果");
        const identity = d["人物社会身份"] || [];
        const relations = d["人物关系"] || [];
        const community = d["社区群体结构"] || "";
        return `
        <div class="grid-2">
            <div>
                <div class="sub-title">👤 人物社会身份</div>
                ${chips(identity, "chip-accent", "未识别到人物身份")}
                <div class="sub-title" style="margin-top:12px;">🤝 人物关系</div>
                ${chips(relations, "chip-info", "未识别到人物关系")}
            </div>
            <div>
                <div class="sub-title">🏘️ 社区或群体结构</div>
                ${community ? `<div style="font-size:13px;color:var(--text);line-height:1.7;">${esc(community)}</div>` : emptyInline("未识别到社区群体结构")}
            </div>
        </div>`;
    }

    // ---- 模块六 ----
    function renderModule6(d) {
        if (!d) return emptyInline("未找到模块六的分析结果");
        const narrative = d["叙事结构"] || [];
        const themes = d["主题聚类"] || {};
        const values = d["价值取向与情感"] || {};
        const conflicts = d["冲突点识别"] || [];
        return `
        <div class="grid-2">
            <div>
                <div class="sub-title">📖 叙事结构</div>
                ${chips(narrative, "chip-accent", "未识别到叙事结构")}
                <div class="sub-title" style="margin-top:12px;">🏷️ 主题聚类</div>
                ${themes["主要主题"] ? `<div class="sub-title" style="font-size:12px;color:var(--text-muted)">主要主题</div>${chips(themes["主要主题"])}` : ""}
                ${themes["子主题"] ? `<div class="sub-title" style="font-size:12px;color:var(--text-muted)">子主题</div>${chips(themes["子主题"], "chip-info")}` : ""}
                ${!themes["主要主题"] && !themes["子主题"] ? emptyInline("未识别到主题") : ""}
            </div>
            <div>
                <div class="sub-title">💭 价值取向与情感</div>
                ${values["价值取向"] ? `<div class="sub-title" style="font-size:12px;color:var(--text-muted)">价值取向</div>${chips(values["价值取向"])}` : ""}
                ${values["情感分析"] ? `<div class="sub-title" style="font-size:12px;color:var(--text-muted)">情感分析</div>${chips(values["情感分析"], "chip-accent")}` : ""}
                ${!values["价值取向"] && !values["情感分析"] ? emptyInline("未识别到价值取向与情感") : ""}
                <div class="sub-title" style="margin-top:12px;">⚔️ 冲突点识别</div>
                ${chips(conflicts, "chip-info", "未识别到冲突点")}
            </div>
        </div>`;
    }

    function renderJson(result) {
        const json = JSON.stringify(result, null, 2);
        return `
        <div class="card">
            <div class="card-header">
                <div class="card-title"><span class="icon">📄</span>完整 JSON 数据</div>
                <a class="btn btn-outline" href="/api/download" download style="padding:6px 12px;font-size:12px;">📥 下载</a>
            </div>
            <div class="card-body" style="padding:0;">
                <div class="json-viewer"><pre>${esc(json)}</pre></div>
            </div>
        </div>`;
    }

    // ---- 渲染辅助 ----
    function chips(items, cls, emptyMsg) {
        items = (Array.isArray(items) && items) || [];
        if (!items.length) return emptyInline(emptyMsg || "未识别到相关内容");
        const c = cls ? " " + cls : "";
        return `<div class="chips">${items.map((i) => `<span class="chip${c}">${esc(i)}</span>`).join("")}</div>`;
    }

    function kv(key, val) {
        let v = val;
        if (v === null || v === undefined || v === "" || v === "None" ||
            v === "未确定" || v === "根据视频内容无法确定") {
            v = `<span class="muted">未确定</span>`;
        } else {
            v = esc(v);
        }
        return `<div class="kv"><span class="kv-key">${esc(key)}</span><span class="kv-val">${v}</span></div>`;
    }

    function flow(steps, label) {
        steps = (Array.isArray(steps) && steps) || [];
        if (!steps.length) return emptyInline("未识别到" + (label || "流程"));
        const parts = [];
        steps.forEach((s, i) => {
            parts.push(`<span class="flow-step">${esc(s)}</span>`);
            if (i !== steps.length - 1) parts.push(`<span class="flow-arrow">→</span>`);
        });
        return `<div class="sub-title" style="font-size:12px;color:var(--text-muted)">${esc(label)}</div><div class="flow">${parts.join("")}</div>`;
    }

    function emptyInline(msg) {
        return `<div class="empty-inline">${esc(msg)}</div>`;
    }

    // ---- 初始化 ----
    refreshModelStatus();
})();
