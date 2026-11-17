// ==UserScript==
// @name         Label Studio 中文界面
// @namespace    ich-prelabel
// @version      1.0
// @description  把 Label Studio 社区版界面翻译成简体中文。社区版 1.23.x 没有内置 i18n（前端无语言包、后端无 USE_I18N），只能在浏览器端补。
// @match        http://ich.8.160.123.92.nip.io/*
// @match        http://8.160.123.92:8089/*
// @match        http://localhost:8080/*
// @match        http://127.0.0.1:8080/*
// @match        http://127.0.0.1:8089/*
// @run-at       document-idle
// @grant        none
// ==/UserScript==
/* eslint-disable */

/**
 * 用法：装 Tampermonkey / 油猴，新建脚本把本文件内容粘进去，保存即可。
 * 按 Ctrl + \ 可临时关闭并刷新回英文原界面。
 *
 * 原理：Label Studio 前端是 React SPA，直接改 DOM 会在重渲染时被覆盖，
 * 所以用 MutationObserver 持续扫描 —— 每次 React 重新渲染出英文，
 * 我们就再翻一次。翻译结果不再命中英文词典，所以会自动收敛，不会死循环。
 *
 * 词典是从 LSF 前端源码（sourcemap 里的 sourcesContent）实际提取的 UI 字符串，
 * 不是猜的。匹配规则：文本节点去空白后「完全相等」才替换，避免误伤数据内容。
 */
(function () {
  'use strict';

  // 防重复执行：本地是内联进 Django 模板的，而登录页/主应用用的是不同的基础模板，
  // 可能注入多份。加个全局标记，保证只跑一次。
  if (window.__lsZhLoaded) return;
  window.__lsZhLoaded = true;

  // ---------------------------------------------------------------- 词典
  const ZH = {
    // ---- 通用按钮 / 操作
    Save: '保存',
    Saved: '已保存',
    Cancel: '取消',
    Delete: '删除',
    Edit: '编辑',
    Copy: '复制',
    Submit: '提交',
    Update: '更新',
    Skip: '跳过',
    Accept: '接受',
    Reject: '拒绝',
    Reset: '重置',
    Undo: '撤销',
    Redo: '重做',
    Clear: '清空',
    Confirm: '确认',
    Create: '创建',
    Import: '导入',
    Export: '导出',
    Search: '搜索',
    Select: '选择',
    Close: '关闭',
    Add: '添加',
    Remove: '移除',
    Apply: '应用',
    Back: '返回',
    Next: '下一个',
    Previous: '上一个',
    Continue: '继续',
    Finish: '完成',
    Done: '完成',
    Loading: '加载中',
    Error: '错误',
    Warning: '警告',
    Success: '成功',
    Help: '帮助',
    Rename: '重命名',
    Duplicate: '复制副本',
    Download: '下载',
    Upload: '上传',
    Refresh: '刷新',

    // ---- 导航 / 页面
    Projects: '项目',
    Tasks: '任务',
    Annotations: '标注',
    Annotation: '标注',
    Predictions: '预标注',
    Settings: '设置',
    Models: '模型',
    Files: '文件',
    Admin: '管理',
    'My Account': '我的账户',
    'Create Project': '创建项目',
    'Create new project': '新建项目',
    'Project Name': '项目名称',
    'Back to projects': '返回项目列表',
    'Labeling Instructions': '标注说明',
    'Export data': '导出数据',
    'Import Data': '导入数据',
    'Data Manager': '数据管理',
    'Danger Zone': '危险操作',
    'Delete Project': '删除项目',
    'Reset Cache': '重置缓存',
    'Drop All Tabs': '清除所有标签页',
    Dashboard: '仪表盘',
    Overview: '概览',
    Members: '成员',
    Webhooks: 'Webhooks',
    'Add Webhook': '添加 Webhook',
    'Delete Webhook': '删除 Webhook',

    // ---- 数据管理页
    Columns: '列',
    Column: '列',
    'Display as': '显示方式',
    'List view': '列表视图',
    'Grid view': '网格视图',
    'Switch to list view': '切换为列表视图',
    'Switch to grid view': '切换为网格视图',
    'Grid settings': '网格设置',
    'Increase columns number': '增加列数',
    'Decrease columns number': '减少列数',
    'Label Tasks As Displayed': '按当前显示内容标注任务',
    'Tasks Actions': '任务操作',
    'Copy Task ID': '复制任务 ID',
    'Copy Cell Contents': '复制单元格内容',
    'View Task Source': '查看任务源数据',
    'Compare All Annotations': '对比全部标注',
    'Task Preview': '任务预览',
    'No tasks available': '暂无任务',
    'No tasks found': '未找到任务',
    'No tasks available for review or labeling': '暂无待标注或待审核的任务',
    'Tasks imported to this project will appear here': '导入到本项目的任务会显示在这里',
    'Try adjusting or clearing the filters to see more results': '试着调整或清除筛选条件以查看更多结果',
    'Search Results': '搜索结果',
    'Clear Search': '清除搜索',
    'Show all authors': '显示全部作者',
    Annotator: '标注员',
    Created: '创建时间',
    Skipped: '已跳过',
    Total: '总计',
    Completed: '已完成',
    ID: 'ID',

    // ---- 筛选
    Filter: '筛选',
    Filters: '筛选',
    'All fields': '所有字段',
    'No filters applied': '未应用筛选条件',
    'Copy filters': '复制筛选条件',
    'Paste filters': '粘贴筛选条件',
    'Undo paste': '撤销粘贴',
    'Undo paste — restore previous filters': '撤销粘贴 — 恢复之前的筛选条件',
    'Pin filters to sidebar': '将筛选条件固定到侧边栏',
    'Unpin filters': '取消固定筛选条件',
    contains: '包含',
    'not contains': '不包含',
    equal: '等于',
    'not equal': '不等于',
    'is not': '不是',
    'includes all': '包含全部',
    'does not include all': '不包含全部',
    'not between': '不在区间内',

    // ---- 标注页：界面设置面板
    'Labeling Interface Settings': '标注界面设置',
    'Show Annotations panel': '显示标注面板',
    'Show image in fullsize': '全尺寸显示图像',
    'Show Predictions panel': '显示预标注面板',
    'Labeling hotkeys': '标注快捷键',
    'Enables quick selection of labels using hotkeys': '启用后可用快捷键快速选择标签',
    'Enable labeling hotkeys': '启用标注快捷键',
    'Show hotkeys on tooltips': '在提示中显示快捷键',
    'Displays keybindings on tools and actions tooltips': '在工具和操作的悬浮提示中显示快捷键',
    'Show hotkey tooltips': '显示快捷键提示',
    'Show hotkeys on labels': '在标签上显示快捷键',
    'Displays keybindings on labels': '在标签上显示快捷键绑定',
    'Show labels hotkey tooltips': '显示标签快捷键提示',
    'Show region labels': '显示区域标签',
    'Display region label names': '显示区域的标签名称',
    'Show labels inside the regions': '在区域内部显示标签',
    'Keep label selected after creating a region': '创建区域后保持标签选中',
    'Allows continuous region creation using the selected label': '允许用同一个标签连续创建区域',
    'Select region after creating it': '创建后选中该区域',
    'Automatically selects newly created regions': '自动选中新建的区域',
    'Select regions after creating': '创建后选中区域',
    'Show line numbers': '显示行号',
    'Identify and reference specific lines of text in your document': '在文档中定位并引用特定行',
    'Show line numbers for Text': '为文本显示行号',
    'Keep selected tool': '保持选中的工具',
    'Persists the selected tool across tasks': '跨任务保持当前选中的工具',
    'Remember Selected Tool': '记住所选工具',
    'Pixel smoothing on zoom': '缩放时像素平滑',
    'Smooth image pixels when zoomed in': '放大时对图像像素做平滑处理',
    'Enable image smoothing when zoom': '缩放时启用图像平滑',
    'Invert zoom direction': '反转缩放方向',
    'Invert the direction of scroll-to-zoom': '反转滚轮缩放的方向',
    'Enable inverted zoom direction': '启用反转缩放方向',
    'Increase size': '增大尺寸',
    'Decrease size': '减小尺寸',

    // ---- 标注页：底部栏 / 提交
    'Postpone task': '稍后处理',
    'Previous task': '上一个任务',
    'Next task': '下一个任务',
    'No previous task': '没有上一个任务',
    'Submit an annotation to continue': '提交标注后才能继续',
    'This task cannot be skipped': '此任务不可跳过',
    'Cancel skip': '取消跳过',
    'You have unsaved changes': '有未保存的更改',
    Hotkeys: '快捷键',
    'Import Hotkeys': '导入快捷键',
    'Annotation History': '标注历史',
    'Annotation Results': '标注结果',

    // ---- 视频 / 时间轴
    Play: '播放',
    Pause: '暂停',
    'Playback Settings': '播放设置',
    'Playback speed': '播放速度',
    'Increase or decrease the playback speed': '调节播放速度',
    'Loop Timeline Regions': '循环播放时间轴区域',
    'Video settings': '视频设置',
    Video: '视频',
    Fullscreen: '全屏',
    'Hop backward': '向后跳跃',
    'Hop forward': '向前跳跃',
    'Step backward': '后退一帧',
    'Step forward': '前进一帧',
    'Media fast forward': '快进',
    'Media rewind': '快退',
    'Skip to end': '跳到结尾',
    'Skip to start': '跳到开头',
    'Toggle Timeline': '显示/隐藏时间轴',
    'Toggle Interpolation': '切换插值',
    'Toggle Keypoint': '切换关键帧',
    'Buffering Media Source': '正在缓冲媒体',
    'Unable to play': '无法播放',
    'Video hop size': '视频跳跃步长',
    'Allow drawing outside of video boundaries': '允许在视频边界之外绘制',
    'Start frame': '起始帧',
    'End frame': '结束帧',
    Frame: '帧',
    Frames: '帧',
    Speed: '速度',
    Volume: '音量',
    'Zoom In': '放大',
    'Zoom Out': '缩小',

    // ---- 区域 / Outliner 面板
    'Delete Region': '删除区域',
    'Unlock Region': '解锁区域',
    'Delete selected region': '删除选中的区域',
    'Delete Relation': '删除关联',
    'Group by Label': '按标签分组',
    'Group by Tool': '按工具分组',
    'Grouped by Label': '已按标签分组',
    'Grouped by Tool': '已按工具分组',
    'Group Manually': '手动分组',
    'Manually Grouped': '已手动分组',
    Manual: '手动',
    'Hide all': '全部隐藏',
    'Show all': '全部显示',
    'Hide all regions': '隐藏所有区域',
    'Show all regions': '显示所有区域',
    'Order by newest': '按最新排序',
    'Order by oldest': '按最旧排序',
    'Order by Time': '按时间排序',
    'Order by Score': '按分数排序',
    'Order by Media Start Time': '按媒体起始时间排序',
    'By Label': '按标签',
    'By Tool': '按工具',
    'By Time': '按时间',
    'By Score': '按分数',
    'By Media Start Time': '按媒体起始时间',
    Regions: '区域',
    Region: '区域',
    Labels: '标签',
    Label: '标签',

    // ---- 登录 / 账户
    Email: '邮箱',
    'Email address': '邮箱地址',
    Password: '密码',
    'Sign in': '登录',
    'Sign up': '注册',
    'Log in': '登录',
    'Log out': '退出登录',
    'Forgot password?': '忘记密码？',
    'Access Token': '访问令牌',
    'Personal Access Token': '个人访问令牌',
    'Copy to clipboard': '复制到剪贴板',

    // ---- 导入 / 导出流程
    'Import Settings & Preview': '导入设置与预览',
    'Review & Confirm': '检查并确认',
    'Configure Connection': '配置连接',
    'Select Provider': '选择存储服务',
    'Expected Input Preview': '预期输入预览',
    'Select an option': '请选择一个选项',
    'You must upgrade your plan to import data': '需升级套餐才能导入数据',
    'Create a Model': '创建模型',
    'Open Reader View': '打开阅读视图',
    'Focus previous task': '聚焦上一个任务',
    'Focus next task': '聚焦下一个任务',

    // ---- 首页 / 项目列表
    'Welcome 👋': '欢迎 👋',
    "Let's get you started.": '让我们开始吧。',
    'Create your first project': '创建你的第一个项目',
    'Create one and start labeling your data.': '创建一个项目，开始标注你的数据。',
    'It looks like your team is growing!': '看起来你的团队正在壮大！',
    'Created Projects': '创建的项目',
    'Projects contributed to': '参与的项目',
    'Contributed to': '参与',
    'Annotations Submitted': '已提交标注',
    'Last Activity': '最近活动',
    'Registration date': '注册日期',
    'Browse Templates': '浏览模板',
    'Custom template': '自定义模板',
    'Customize': '自定义',
    'See all tags': '查看全部标签',
    'Project was deleted or not yet created': '项目已删除或尚未创建',
    "Heidi doesn't see any projects here!": '这里还没有任何项目！',
    'This template requires more data then you have for now': '该模板需要更多数据，当前数据量不足',
    'Workspace': '工作区',
    'Organization': '组织',
    'Organization ID': '组织 ID',
    'User ID': '用户 ID',
    'My role': '我的角色',
    'Owner': '所有者',
    'Membership Info': '成员信息',
    'Add Members': '添加成员',
    'Invite Members': '邀请成员',
    'Personal Info': '个人信息',
    'Email Preferences': '邮件偏好',
    'New Auth Token': '新建授权令牌',
    'Create New Token': '创建新令牌',
    'Revoke': '撤销',
    'Revoke Token': '撤销令牌',
    'Manage your access tokens securely': '安全地管理你的访问令牌',
    'Copy your new access token from below and keep it secure.': '从下方复制你的新访问令牌并妥善保管。',
    'API Documentation': 'API 文档',
    'API Token Settings': 'API 令牌设置',
    'API Tokens Settings': 'API 令牌设置',

    // ---- 数据管理页
    'Data Import': '数据导入',
    'Import Configuration': '导入配置',
    'Import Process': '导入过程',
    'Import Error': '导入错误',
    'Configure Import Settings & Preview Data': '配置导入设置并预览数据',
    'Configure data': '配置数据',
    'Configure settings': '配置设置',
    'Drag & drop files here': '将文件拖拽到此处',
    'Choose Different File': '选择其他文件',
    'No Files Found': '未找到文件',
    'No Preview Available': '无可预览内容',
    'Files Preview': '文件预览',
    'All Tasks Files': '全部任务文件',
    'Total size': '总大小',
    'List of tasks': '任务列表',
    'Tasks are ordered by Task ID': '任务按 ID 排序',
    'Tasks are chosen with uniform random': '任务均匀随机抽取',
    'No items selected': '未选择任何项目',
    'Selected items': '已选项目',
    'Minimize or expand bulk actions sidebar': '收起/展开批量操作侧栏',
    'Allow Duplicate': '允许重复',
    'Treat CSV/TSV as': 'CSV/TSV 解析方式',
    'Include files from all nested folders': '包含所有子文件夹中的文件',
    'Use regex patterns to filter which files are imported': '用正则表达式过滤要导入的文件',
    'Add filter for long list of labels': '为较长的标签列表添加筛选',

    // ---- 数据类型
    'Text': '文本',
    'Plain Text': '纯文本',
    'HTML / HyperText': 'HTML / 超文本',
    'Markdown': 'Markdown',
    'PDF': 'PDF',
    'Audio': '音频',
    'Images': '图片',
    'Videos': '视频',
    'Tabular': '表格',
    'Structured data': '结构化数据',
    'Time Series or Whole Text File': '时序数据或整文本文件',
    'Line': '行',

    // ---- 标注页：工具悬浮提示（鼠标悬停才看得到，漏了等于没翻）
    'Select the rectangle annotation tool': '选择矩形标注工具',
    'Select the ellipse tool': '选择椭圆工具',
    'Select the polygon annotation tool': '选择多边形标注工具',
    'Select the key point annotation tool': '选择关键点标注工具',
    'Select the brush tool': '选择画笔工具',
    'Select the eraser tool': '选择橡皮擦工具',
    'Select the magic wand tool for smart region selection': '选择魔棒工具，智能选取区域',
    'Select the move tool to reposition annotations': '选择移动工具以调整标注位置',
    'Use the auto-detect tool to automatically suggest regions': '用自动检测工具自动推荐区域',
    'Create a copy of the selected region': '复制选中的区域',
    'Create a relation between selected regions': '在选中的区域之间建立关联',
    'Delete currently selected region': '删除当前选中的区域',
    'Delete selected segment': '删除选中的片段',
    'Deselect the currently selected region': '取消选中当前区域',
    'Lock or unlock the selected region': '锁定/解锁选中的区域',
    'Edit metadata for selected region': '编辑选中区域的元数据',
    'Remove all regions': '移除所有区域',
    'Show or hide the selected region': '显示/隐藏选中的区域',
    'Show or hide all regions': '显示/隐藏所有区域',
    'Cycle through all regions': '在所有区域间循环切换',
    'Move focus to the first focusable region': '将焦点移到第一个可聚焦区域',
    'Pan around the image': '平移图像',
    'Zoom in on the image': '放大图像',
    'Zoom out of the image': '缩小图像',
    'Zoom to fit the full image in view': '缩放以适应完整图像',
    'Rotate the image 90° to the left': '将图像向左旋转 90°',
    'Rotate the image 90° to the right': '将图像向右旋转 90°',
    'Show controls to rotate image': '显示旋转图像的控制项',
    'Show controls to zoom in and out': '显示缩放控制项',
    'Draw a rotated rectangle using 3-point selection': '用三点选择绘制旋转矩形',
    'Extend the region to the left': '向左扩展区域',
    'Extend the region to the right': '向右扩展区域',
    'Extend region left significantly': '向左大幅扩展区域',
    'Extend region right significantly': '向右大幅扩展区域',
    'Shrink the region from the left': '从左侧收缩区域',
    'Shrink the region from the right': '从右侧收缩区域',
    'Shrink region from left significantly': '从左侧大幅收缩区域',
    'Shrink region from right significantly': '从右侧大幅收缩区域',
    'Increase tool size': '增大工具尺寸',
    'Decrease tool size': '减小工具尺寸',
    'Width of region borders': '区域边框宽度',
    'Submit the current annotation': '提交当前标注',
    'Skip the current task': '跳过当前任务',
    'Undo last action': '撤销上一步操作',
    'Redo previously undone action': '重做刚才撤销的操作',
    'Exit relation mode and unselect region': '退出关联模式并取消选中',
    'Toggle video playback': '播放/暂停视频',
    'Toggle audio playback': '播放/暂停音频',
    'Seek video forward': '视频快进',
    'Seek video backward': '视频快退',
    'Rewind the audio by 1 second': '音频后退 1 秒',
    'Jump to first frame': '跳到第一帧',
    'Jump to last frame': '跳到最后一帧',
    'Jump to next keyframe': '跳到下一个关键帧',
    'Jump to previous keyframe': '跳到上一个关键帧',
    'Step back one frame': '后退一帧',
    'Step forward one frame': '前进一帧',
    'Step one frame backward': '后退一帧',
    'Step one frame forward': '前进一帧',
    'View next image': '查看下一张图',
    'View previous image': '查看上一张图',
    'Select text by words': '按词选择文本',
    'Select all text in current phrase and create annotation': '选中当前段落的全部文本并创建标注',
    'Navigate to the next phrase in paragraph view': '跳转到段落视图中的下一段',
    'Navigate to the previous phrase in paragraph view': '跳转到段落视图中的上一段',
    'Navigate to the next region within current phrase': '跳转到当前段落中的下一个区域',
    'Navigate to the previous region within current phrase': '跳转到当前段落中的上一个区域',

    // ---- 标注页：面板标题 / 快捷键分组
    'Editor': '编辑器',
    'Tools': '工具',
    'Labeling': '标注',
    'Annotation Settings': '标注设置',
    'Annotation settings': '标注设置',
    'Annotation Actions': '标注操作',
    'Region Management': '区域管理',
    'Video Controls': '视频控制',
    'Audio Controls': '音频控制',
    'Time Series Controls': '时序控制',
    'Image Gallery Navigation': '图片库导航',
    'Paragraph Navigation': '段落导航',
    'Shortcuts for controlling video playback and navigation': '视频播放与导航快捷键',
    'Shortcuts for controlling audio playback and navigation': '音频播放与导航快捷键',
    'Shortcuts for controlling tools panel when labeling images': '标注图片时的工具面板快捷键',
    'Shortcuts for manipulating time series data regions': '时序数据区域操作快捷键',
    'Shortcuts for navigating between images in multi-image tasks': '多图任务中切换图片的快捷键',
    'Text editing shortcuts': '文本编辑快捷键',
    'Hotkeys JSON': '快捷键 JSON',
    'Reset Hotkeys to Defaults?': '将快捷键恢复为默认？',
    'Reset Link': '重置链接',
    'Click to set shortcut': '点击设置快捷键',
    'Press keys now...': '请按键…',
    'Instructions': '说明',
    'Write instructions to help users complete labeling tasks.': '编写说明，帮助标注人员完成任务。',
    'Use new line as a separator to add multiple labels': '用换行分隔以添加多个标签',

    // ---- 云存储
    'Cloud Storage': '云存储',
    'Add Source Storage': '添加源存储',
    'Add Target Storage': '添加目标存储',
    'Storage Location': '存储位置',
    'Storage Sync Error Log': '存储同步错误日志',
    'Sync Storage': '同步存储',
    'Deleting storage': '正在删除存储',
    'Amazon S3': 'Amazon S3',
    'Amazon S3 with IAM Role': 'Amazon S3（IAM 角色）',
    'Azure Blob Storage': 'Azure Blob 存储',
    'Azure Blob Storage with Service Principal': 'Azure Blob 存储（服务主体）',
    'Google Cloud Storage': 'Google 云存储',
    'Redis Storage': 'Redis 存储',
    'Local Files': '本地文件',
    'Local Storage documentation': '本地存储文档',
    'Local file serving is disabled': '本地文件服务已禁用',
    'Choose your cloud storage provider': '选择你的云存储服务商',
    'Select the cloud storage service where your data is stored': '选择存放数据的云存储服务',
    'Choose how to interpret your data from storage': '选择如何解析存储中的数据',
    'Import your data from cloud storage providers': '从云存储服务商导入数据',
    'Provider': '服务商',
    'Prefix': '前缀',
    'Your storage account key': '你的存储账户密钥',
    'Your redis password': '你的 Redis 密码',
    'Leave blank to inherit from Google Application Credentials.': '留空则继承 Google 应用凭据。',
    'If unchecked, annotations will not be deleted from storage': '取消勾选则不会从存储中删除标注。',

    // ---- 模型 / 预标注
    'Model': '模型',
    'Create Model': '创建模型',
    'Connect Model': '连接模型',
    'Delete ML Backend': '删除 ML 后端',
    'Training': '训练',
    'Start Training': '开始训练',
    'Start Model Training': '开始训练模型',
    'Batch predictions': '批量预测',
    'Predictions List': '预测列表',
    'Delete Predictions': '删除预测',
    'Predicting': '预测中',
    'Prelabeling': '预标注',

    // ---- 设置 / 账户 / Webhook
    'General Settings': '常规设置',
    'Send Request': '发送请求',
    'Test Request': '测试请求',
    'Send Test Request': '发送测试请求',
    'Send Payload for': '发送负载用于',
    'Request Sent!': '请求已发送！',
    'Contact your administrator to create Webhooks': '请联系管理员创建 Webhook',
    'Error loading settings.': '设置加载失败。',
    'Error occurred': '发生错误',
    'Unable to load tokens list': '无法加载令牌列表',
    'Failed to load history': '历史记录加载失败',
    'No history available': '暂无历史记录',
    'Reload': '重新加载',
    'Revoke access': '撤销访问',

    // ---- 导出
    'Export timed out': '导出超时',
    'Export timeout in Community Edition': '社区版的导出超时限制',
    'Having a timeout or trouble exporting large projects?': '导出大型项目时超时或遇到问题？',
    'Files are being prepared. It might take long time.': '文件正在准备中，可能需要较长时间。',
    'Something went wrong, the sample data could not be loaded.': '出错了，示例数据无法加载。',

    // ---- 通用字段标签
    'Name': '名称',
    'Value': '值',
    'Description': '描述',
    'Comments': '评论',
    'Actions': '操作',
    'Preview': '预览',
    'View All': '查看全部',
    'Select All': '全选',
    'Save Changes': '保存更改',
    'Validate and Save': '验证并保存',
    'Reset to Defaults': '恢复默认',
    'Retry': '重试',
    'Copied': '已复制',
    'Connected': '已连接',
    'Disconnected': '未连接',
    'Connection failed': '连接失败',
    'Check Connection': '检查连接',
    'Successfully connected!': '连接成功！',
    'Ready to Connect': '准备连接',
    'Is Active': '是否启用',
    'Learn more': '了解更多',
    'Did you know?': '你知道吗？',
    'Loading...': '加载中…',
    'No data': '无数据',
    'No options found.': '未找到选项。',
    'You are about to delete the project': '你即将删除该项目',
    'You are about to drop all tabs for': '你即将清除以下项目的所有标签页',
    'You are about to reset the cache for': '你即将重置以下项目的缓存',
    'This action cannot be undone.': '此操作无法撤销。',

    // ---- 第二批：数据管理空状态 / 排序 / 批量操作
    'Clear Filters': '清除筛选条件',
    'Order by': '排序方式',
    'Nothing found': '未找到内容',
    "Can't find task": '找不到任务',
    'Click to load': '点击加载',
    'Fit images to width': '图片适应宽度',
    'Move sidepanel to the bottom': '将侧边面板移到底部',
    'Toggle bulk sidebar minimization': '切换批量侧栏折叠状态',
    'Focus on the open task column': '聚焦到「待标注」列',
    'Focus on the closed task column': '聚焦到「已完成」列',
    'Label All Tasks': '标注全部任务',
    'Start labeling tasks': '开始标注任务',
    'Start labeling and track your results': '开始标注并跟踪你的成果',
    'Import data to get your project started': '导入数据以开始你的项目',
    'See docs on importing data': '查看数据导入文档',
    'Tasks assigned to you will appear here': '分配给你的任务会显示在这里',
    'Tasks will appear here when they become available': '任务可用时会显示在这里',
    "Tasks you've labeled will appear here": '你标注过的任务会显示在这里',
    'Try adjusting the filter or similarity search parameters': '试着调整筛选条件或相似度检索参数',
    'Adjust or remove filters to view': '调整或移除筛选条件以查看',
    'Adjust or remove the filters to view': '调整或移除筛选条件以查看',
    'Press the button below to see any synced records': '点击下方按钮查看已同步的记录',
    'Hang tight! Records are syncing in the background': '请稍候，记录正在后台同步',
    'Project has been deleted or not yet created.': '项目已删除或尚未创建。',
    "You're almost there!": '马上就好！',
    'Oops...': '哎呀…',
    'Errors occurred': '出现错误',
    'Failed to load': '加载失败',
    'Failed to sync data': '数据同步失败',
    'Storage sync': '存储同步',
    'Connect Cloud Storage': '连接云存储',
    'Add URL': '添加 URL',
    'Add Inside': '在内部添加',
    'Network is reachable': '网络可访问',
    'Downloading image': '正在下载图片',
    'Loading file...': '正在加载文件…',
    'Loading comments...': '正在加载评论…',
    'Loading actions...': '正在加载操作…',
    'Use [arrow keys] to navigate.': '使用方向键导航。',
    'Press Shift + Enter to Add': '按 Shift + Enter 添加',
    'Are you sure?': '确定吗？',
    'Delete annotation?': '删除标注？',
    'Ground Truth': '基准真值',
    'Compare All': '对比全部',
    'Relations': '关联关系',
    'Link regions to define relationships between them': '关联区域以定义它们之间的关系',
    'State History': '状态历史',
    'Task Data': '任务数据',
    'Task Summary': '任务摘要',
    'History': '历史',
    'Summary': '摘要',
    'Config': '配置',
    'Custom': '自定义',
    'Default': '默认',
    'Debug': '调试',
    'Color Scheme': '配色方案',
    'Distribution': '分布',
    'Where': '条件',
    'Recent': '最近',
    'Scale': '比例',
    'Zoom 100%': '缩放 100%',
    'Zoom To Fit': '适应窗口',
    'Spectrogram Settings': '声谱图设置',
    'Spectogram dB': '声谱图 dB',
    'FFT Samples': 'FFT 采样点数',
    'Windowing Function': '窗函数',
    'Side-by-side': '并排显示',
    'Serialize Current Annotation': '序列化当前标注',
    'Serialize All Annotations': '序列化全部标注',
    'Selected Message': '选中的消息',
    'You can use hypertext here': '此处可使用超文本',
    'Request': '请求',
    'Response': '响应',
    'Agreement': '协议',
    'Beta': '测试版',
    'Go Back': '返回',

    // ---- 导出 / 导入 / 首页卡片（含企业版引流文案，社区版上也会显示）
    'Enterprise Feature': '企业版功能',
    'Unlock faster access provisioning': '解锁更快的权限开通',
    'Apply your AWS spend to Label Studio Enterprise': '将你的 AWS 支出用于 Label Studio 企业版',
    'View JSON input format': '查看 JSON 输入格式',
    'Upload Image': '上传图片',
    'Interactive': '交互式',
    'Code': '代码',
    'Set': '设置',
    'Please select': '请选择',
    'Select date': '选择日期',
    'Select time': '选择时间',
    'All regions hidden': '所有区域已隐藏',
    'All tasks in the queue have been completed': '队列中的所有任务均已完成',
    'Read Documentation': '阅读文档',
    'Read more on that here.': '点此了解更多。',
    'URL is valid': 'URL 有效',
    'Keyboard Shortcuts': '键盘快捷键',
    'Shortcut': '快捷键',
    'Display Labels by default in Results panel': '在结果面板中默认显示标签',
    'Go to Previous Task': '转到上一个任务',
    'Next Task': '下一个任务',
    'Hop backward quickly': '快速后退',
    'Hop forward quickly': '快速前进',
    'Was skipped': '曾被跳过',
    'Yes': '是',
    'No': '否',
    'Data': '数据',
    'Info': '信息',
    'Sample': '示例',
    'Parquet': 'Parquet',

    // ---- 文档 / 社区 / 企业版引流（社区版界面上同样会显示这些入口）
    'Documentation': '文档',
    'Repository': '代码仓库',
    'Release Notes': '发布说明',
    'LabelStud.io Blog': 'LabelStud.io 博客',
    'Slack': 'Slack',
    'Slack Community': 'Slack 社区',
    'Ask on Slack': '在 Slack 上提问',
    'Share knowledge with the community': '与社区分享经验',
    'Save time with Auto-Labeling': '用自动标注节省时间',
    'Evaluate GenAI models': '评估 GenAI 模型',
    'Labeling for GenAI': 'GenAI 标注',
    'Want to automate task distribution?': '想自动分配任务？',
    'Want to simplify and secure logging in?': '想让登录更简单更安全？',
    'Label Studio Enterprise': 'Label Studio 企业版',
    'Enterprise': '企业版',
    'System': '系统',
    'Time': '时间',
    'See docs': '查看文档',
    'No ratings': '暂无评分',
    'Move focus to the next task': '将焦点移到下一个任务',
    'Move focus to the previous task': '将焦点移到上一个任务',
  };

  // 小写索引，用来兜住全大写按钮（如 SAVE / DELETE）
  const ZH_LOWER = new Map();
  for (const [k, v] of Object.entries(ZH)) {
    const low = k.toLowerCase();
    if (!ZH_LOWER.has(low)) ZH_LOWER.set(low, v);
  }

  const ATTRS = ['placeholder', 'title', 'aria-label', 'alt'];
  const SKIP_TAGS = new Set([
    'SCRIPT', 'STYLE', 'NOSCRIPT', 'TEXTAREA', 'CODE', 'PRE', 'SVG', 'PATH',
  ]);
  const MAX_LEN = 90; // 超过这个长度基本不是 UI 文案，放过

  // 分出「首尾标点 + 正文」，用来实现容错匹配：
  // LS 里 "Saved!"、"Total:"、"URL:" 这类带标点的文案很常见，
  // 只比正文、保留原标点，就不需要为每个变体都单列词条。
  const PUNC = /^([^\w一-鿿]*)([\s\S]*?)([^\w一-鿿]*)$/;

  function lookup(t) {
    if (Object.prototype.hasOwnProperty.call(ZH, t)) return ZH[t];
    const v = ZH_LOWER.get(t.toLowerCase());
    return v === undefined ? null : v;
  }

  function tr(raw) {
    if (typeof raw !== 'string') return null;
    const t = raw.trim();
    if (!t || t.length > MAX_LEN) return null;
    const hit = lookup(t);
    if (hit !== null) return hit;
    // 精确没中，去掉首尾标点再试一次，命中后把标点原样拼回去
    const m = PUNC.exec(t);
    if (m && m[2]) {
      const inner = m[2].trim();
      if (inner && inner !== t) {
        const h = lookup(inner);
        if (h !== null) return m[1] + h + m[3];
      }
    }
    return null;
  }

  // 处于 contenteditable 内的文本不翻，免得干扰正在编辑的内容。
  // 用属性判断兜底：jsdom 之类的环境里 isContentEditable 恒为 false。
  function inEditable(node) {
    const el = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
    if (!el) return false;
    if (el.isContentEditable) return true;
    if (el.closest && el.closest('[contenteditable]')) return true;
    return false;
  }

  // 熔断：同一个文本节点最多翻译这么多次就永久跳过。
  // 原因：我们改 DOM 后，React 可能在下一轮渲染把它改回英文，我们再改、它再改……
  // 形成「我们 vs React」的拉锯，页面就会疯狂重绘。次数封顶后必然收敛。
  const MAX_PER_NODE = 3;
  const hits = new WeakMap();

  function applyText(node) {
    if (inEditable(node)) return false;
    const n = hits.get(node) || 0;
    if (n >= MAX_PER_NODE) return false;
    const r = tr(node.nodeValue);
    if (r === null) return false;
    const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(node.nodeValue);
    const next = m[1] + r + m[3];
    if (next === node.nodeValue) return false;
    node.nodeValue = next;
    hits.set(node, n + 1);
    return true;
  }

  function applyElement(el) {
    if (SKIP_TAGS.has(el.tagName)) return;
    for (const a of ATTRS) {
      if (!el.hasAttribute(a)) continue;
      const v = el.getAttribute(a);
      const r = tr(v);
      if (r === null || r === v) continue;
      el.setAttribute(a, v.replace(v.trim(), r));
    }
  }

  // 单次 flush 最多处理这么多节点，超了就剩下的留给下一轮。
  // LS 标注页 DOM 很大（视频时间轴每帧都在变），不设上限会一次扫几千个节点把 CPU 打满。
  const MAX_NODES_PER_FLUSH = 1500;

  // 翻译一棵子树（root 自身可能是文本节点，也可能是元素）
  function scan(root) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) {
      applyText(root);
      return;
    }
    if (root.nodeType !== Node.ELEMENT_NODE) return;
    if (root.tagName === 'CANVAS' || root.tagName === 'VIDEO') return;
    applyElement(root);
    const walker = document.createTreeWalker(
      root,
      NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT,
    );
    let n = walker.nextNode();
    let budget = MAX_NODES_PER_FLUSH;
    while (n && budget-- > 0) {
      if (n.nodeType === Node.TEXT_NODE) applyText(n);
      else applyElement(n);
      n = walker.nextNode();
    }
  }

  // ---------------------------------------------------- 观察器（防抖 + 收敛）
  let timer = null;
  const queue = new Set();

  const observer = new MutationObserver((mutations) => {
    for (const m of mutations) {
      if (m.type === 'characterData') queue.add(m.target);
      else if (m.target && m.target.nodeType !== Node.TEXT_NODE) queue.add(m.target);
    }
    if (timer) return;
    timer = setTimeout(flush, 120); // 放宽防抖，别追着时间轴的每帧更新跑
  });

  function flush() {
    timer = null;
    if (!queue.size) return;
    const targets = Array.from(queue);
    queue.clear();

    observer.disconnect(); // 翻译期间断开，避免自己改 DOM 触发自己
    for (const t of targets) {
      if (t.isConnected) scan(t);
    }
    if (document.title) {
      const r = tr(document.title);
      if (r) document.title = r;
    }
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ATTRS,
    });
  }

  // ------------------------------------------------------------ 开关（Ctrl+\）
  function setupToggle() {
    const KEY = 'lsZhDisabled';
    document.addEventListener('keydown', (e) => {
      if (e.ctrlKey && e.key === '\\') {
        const off = localStorage.getItem(KEY) === '1';
        localStorage.setItem(KEY, off ? '0' : '1');
        location.reload();
      }
    });
    return localStorage.getItem(KEY) !== '1';
  }

  function banner() {
    const d = document.createElement('div');
    d.textContent = '中文界面已启用 · 按 Ctrl + \\ 切回英文';
    d.style.cssText =
      'position:fixed;right:12px;bottom:12px;z-index:99999;' +
      'padding:6px 12px;border-radius:6px;font:13px/1.6 system-ui,sans-serif;' +
      'background:#1f2937;color:#fff;opacity:.92;box-shadow:0 2px 10px rgba(0,0,0,.25);' +
      'transition:opacity .4s;pointer-events:none;';
    document.body.appendChild(d);
    setTimeout(() => {
      d.style.opacity = '0';
      setTimeout(() => d.remove(), 600);
    }, 2600);
  }

  // 自检：如果页面被异常频繁地重载（短时间内多次启动本脚本），
  // 说明可能形成了刷新循环 —— 那就永久停用自己，优先保证页面能用。
  // 正常情况下刷新几次也不会触发；真出问题时能自动止损，不需要用户干预。
  function guardReloadLoop() {
    const KEY = 'lsZhBoot';
    const now = Date.now();
    let rec = { n: 0, t: now };
    try {
      rec = JSON.parse(sessionStorage.getItem(KEY) || 'null') || rec;
    } catch (e) { /* 忽略解析错误 */ }
    if (now - rec.t < 8000) {
      rec.n += 1;
      if (rec.n >= 4) {
        try {
          localStorage.setItem('lsZhDisabled', '1');
          sessionStorage.removeItem(KEY);
        } catch (e) { /* 忽略 */ }
        return false;
      }
    } else {
      rec = { n: 1, t: now };
    }
    try { sessionStorage.setItem(KEY, JSON.stringify(rec)); } catch (e) { /* 忽略 */ }
    return true;
  }

  // 逃生通道：地址栏加 ?nozh=1 强制英文并记住选择。
  // 万一中文界面在某台机器上出问题，用它就能正常干活，不至于完全用不了。
  function noZhRequested() {
    if (!/[?&]nozh=1\b/.test(location.search)) return false;
    try { localStorage.setItem('lsZhDisabled', '1'); } catch (e) { /* 忽略 */ }
    return true;
  }

  // 自动打开「显示区域标签」（showLabels）。
  // LSF 的 SettingsStore.js 里 showLabels 默认 false，且整份设置存在
  // localStorage 的 "labelStudio:settings" —— 服务端改不了，只能浏览器端补。
  // 默认关闭时框上不会显示标签名，标注员根本不知道框里框的是什么。
  //
  // 只修正一次：写 lsZhLabelsFixed 标记后不再干预，之后用户在设置里怎么改都尊重。
  // 返回 true 表示需要刷新一次才能让已初始化的 LSF 读到新值。
  function ensureShowLabels() {
    const KEY = 'labelStudio:settings';
    const DONE = 'lsZhLabelsFixed';
    let s = {};
    try { s = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { s = {}; }
    if (s && typeof s === 'object' && s.showLabels === true) return false; // 已经是开的
    try {
      if (localStorage.getItem(DONE)) return false; // 修正过一次了，别再管
    } catch (e) { /* 忽略 */ }
    if (!s || typeof s !== 'object') s = {};
    s.showLabels = true;
    try {
      localStorage.setItem(KEY, JSON.stringify(s));
      localStorage.setItem(DONE, '1');
    } catch (e) {
      return false; // 写不进去就算了，别为此刷新
    }
    return true;
  }

  function boot() {
    if (!document.body) return setTimeout(boot, 100);
    if (!setupToggle()) return; // 用户关掉了
    if (noZhRequested()) return; // 显式要求英文
    // 第一次进来把 showLabels 打开并刷新一次；之后不再干预
    if (ensureShowLabels()) {
      location.reload();
      return;
    }
    if (!guardReloadLoop()) return; // 检测到异常重载，自动停用
    scan(document.body);
    const r = tr(document.title);
    if (r) document.title = r;
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ATTRS,
    });
    banner();
  }

  boot();
})();
