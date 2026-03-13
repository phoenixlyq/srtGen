# SrtGen

基于 Whisper.NET 的视频字幕生成工具，支持 GPU 加速和多语言识别。

## 功能特性

- **视频提取** - 支持主流视频格式（MP4、MKV、AVI、MOV、FLV、WebM）
- **语音识别** - 使用 Whisper.NET 引擎进行高精度语音转文字
- **GPU 加速** - 支持 Vulkan GPU 加速（AMD/NVIDIA 显卡）
- **多语言** - 支持中文、日语、英语、韩语、法语、德语、西班牙语、俄语及自动检测
- **字幕生成** - 生成标准 SRT 格式字幕文件
- **智能分段** - VAD 语音检测、智能去重、上下文优化
- **翻译支持** - 可对接 Ollama 进行字幕翻译

## 环境要求

- Python 3.11+
- .NET Runtime 8.0+
- Vulkan 支持（可选，用于 GPU 加速）

## 安装

### 1. 安装依赖

```bash
# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install moviepy pythonnet ttkbootstrap
```

### 2. 配置 Whisper.NET

需要下载 Whisper.NET 相关的 DLL 文件，详见 [Whisper.NET 安装指南](whisper_net_setup.md)。

目录结构：
```
deps/
├── Whisper.net.dll
├── Microsoft.Extensions.AI.Abstractions.dll
├── System.Memory.dll
├── ...
└── native/
    ├── whisper.dll
    ├── ggml-whisper.dll
    └── ...
```

### 3. 下载语音模型

从 [whisper.cpp models](https://github.com/ggerganov/whisper.cpp/tree/master/models) 下载 `.bin` 模型文件，放置到 `models/` 目录。

推荐模型：
- `ggml-large-v3-turbo.bin` - 效果好、速度快（推荐）
- `ggml-base.bin` - 轻量级模型

## 使用方法

### 图形界面

```bash
python main.py
```

操作步骤：
1. 选择视频文件
2. 选择目标语言（或自动检测）
3. 选择语音模型
4. 点击开始生成字幕

### 输出

生成的 SRT 字幕文件与视频文件在同一目录。

## 配置说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| 语言 | 识别语言 | 自动检测 |
| 智能分段 | 启用语音分段 | 是 |
| VAD 检测 | 语音活动检测 | 是 |
| GPU 加速 | Vulkan 加速 | 是 |

## GPU 加速

支持的显卡：
- **AMD** - RX 400 系列及以上（需要 Vulkan 支持）
- **NVIDIA** - GTX 600 系列及以上
- **Intel/AMD 核显** - 部分支持 Vulkan 的集成显卡

检查 Vulkan 支持：
```bash
vulkaninfo
```

## 常见问题

### Native Library not found

确保 `deps/native/` 目录包含以下 DLL 文件：
- `whisper.dll`
- `ggml-whisper.dll`
- `ggml-vulkan-whisper.dll`
- `ggml-base-whisper.dll`

### GPU 加速不工作

1. 更新显卡驱动到最新版本
2. 运行 `vulkaninfo` 确认 Vulkan 支持
3. 在设置中确认已启用 GPU 选项

### 识别结果异常重复

程序已内置去重逻辑，如仍有问题：
1. 启用"禁用上下文"选项
2. 调整静音阈值参数

## 项目结构

```
SrtGen/
├── main.py              # 主程序入口（GUI）
├── transcriber.py       # Whisper 转录核心
├── translator.py        # 翻译模块
├── srt_translate.py     # SRT 翻译工具
├── audio_utils.py       # 音频处理
├── text_utils.py        # 文本处理
├── app_models.py        # 数据模型
├── deps/                # DLL 依赖
└── models/              # 语音模型
```

## 依赖

### Python

- moviepy - 视频/音频处理
- pythonnet - .NET 互操作
- ttkbootstrap - GUI 界面

### DLL

- Whisper.net.dll - Whisper.NET 核心
- Microsoft.Extensions.AI.Abstractions.dll - AI 抽象层
- ggml-vulkan-whisper.dll - Vulkan GPU 加速
- whisper.dll - Whisper 核心

## 许可证

MIT License

## 致谢

- [Whisper.NET](https://github.com/sandrohanea/whisper.net)
- [whisper.cpp](https://github.com/ggerganov/whisper.cpp)
- [MoviePy](https://github.com/Zulko/moviepy)
- [pythonnet](https://github.com/pythonnet/pythonnet)
