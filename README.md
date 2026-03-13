# SrtGen - 视频转字幕工具

一个基于 Whisper.NET 的视频字幕生成工具，支持 GPU 加速和多种语言识别。

## ✨ 功能特性

- 🎬 **视频提取** - 支持 MP4、MKV、AVI、MOV、FLV、WebM 等格式
- 🎯 **语音识别** - 使用 Whisper.NET 引擎进行高精度语音转文字
- 🚀 **GPU 加速** - 支持 Vulkan GPU 加速（AMD/NVIDIA 显卡）
- 🌍 **多语言** - 支持中文、日语、英语、韩语、法语、德语、西班牙语、俄语
- 📝 **字幕生成** - 生成标准 SRT 格式字幕文件
- 🔧 **智能分段** - VAD 语音检测 + 智能去重 + 上下文优化
- 🔄 **翻译支持** - 可对接 Ollama 进行字幕翻译

## 📦 安装

### 1. 环境要求

- Python 3.11+
- .NET Runtime 8.0+（[下载链接](https://dotnet.microsoft.com/download/dotnet)）
- Vulkan 支持（可选，用于 GPU 加速）

### 2. 安装依赖

```bash
# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -r requirements.txt
```

### 3. 下载 DLL 文件

Whisper.NET 需要额外的 DLL 文件，请参考 [Whisper.NET 安装指南](whisper_net_setup.md) 下载并放置到 `deps/` 目录。

### 4. 下载语音模型

从 [whisper.cpp models](https://github.com/ggerganov/whisper.cpp/tree/master/models) 下载 `.bin` 模型文件，放到 `models/` 目录。

推荐模型：`ggml-large-v3-turbo.bin`（效果好、速度快）

## 🚀 使用方法

### 图形界面

```bash
python main.py
```

1. 选择视频文件
2. 选择目标语言
3. 选择语音模型
4. 点击"开始"按钮

### 命令行（待实现）

```bash
python main.py --input video.mp4 --output subtitle.srt --language zh
```

## 📁 项目结构

```
SrtGen/
├── main.py              # 主程序（GUI 入口）
├── transcriber.py       # Whisper 转录核心
├── translator.py        # 翻译模块（Ollama）
├── srt_translate.py     # SRT 翻译工具
├── audio_utils.py       # 音频处理工具
├── text_utils.py        # 文本处理工具
├── app_models.py        # 数据模型
├── deps/                # DLL 依赖文件
│   ├── *.dll           # 托管 DLL
│   └── native/         # 原生 DLL
└── models/             # 语音模型文件
```

## ⚙️ 配置说明

### 转录配置

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `language` | 识别语言 | `auto`（自动检测） |
| `segment_enable` | 启用智能分段 | `true` |
| `segment_len` | 分段长度（秒） | `10.0` |
| `vad_enable` | 启用 VAD 检测 | `true` |
| `no_context` | 禁用上下文 | `false` |
| `no_speech_threshold` | 静音阈值 | `0.6` |
| `logprob_threshold` | 对数概率阈值 | `-1.0` |

### GPU 加速

- **AMD 显卡**：RX 400 系列及以上，需要 Vulkan 支持
- **NVIDIA 显卡**：GTX 600 系列及以上
- **集成显卡**：部分 Intel/AMD 核显支持 Vulkan

检查 Vulkan 支持：
```bash
vulkaninfo
```

## 🔧 开发

```bash
# 安装开发依赖
uv sync --dev

# 运行测试
pytest test/

# 代码格式化
ruff format .
ruff check .
```

## 📝 依赖说明

### Python 依赖

| 包 | 用途 |
|----|------|
| `moviepy` | 视频/音频处理 |
| `pythonnet` | .NET 互操作 |
| `ttkbootstrap` | GUI 界面 |
| `py-curses-editor` | 文本编辑 |

### DLL 依赖

| 文件 | 版本 | 用途 |
|------|------|------|
| `Whisper.net.dll` | 1.9.0 | Whisper.NET 核心 |
| `Microsoft.Extensions.AI.Abstractions.dll` | 10.0.0 | AI 抽象层 |
| `System.Memory.dll` | 4.6.3 | 内存管理 |
| `ggml-vulkan-whisper.dll` | - | Vulkan GPU 加速 |
| `whisper.dll` | - | Whisper 核心 |

详细 DLL 下载指南见：[whisper_net_setup.md](whisper_net_setup.md)

## ❓ 常见问题

### Native Library not found

检查 `deps/native/` 目录是否包含以下 DLL：
- `whisper.dll`
- `ggml-whisper.dll`
- `ggml-vulkan-whisper.dll`
- `ggml-base-whisper.dll`

### GPU 加速不工作

1. 更新显卡驱动
2. 运行 `vulkaninfo` 确认 Vulkan 支持
3. 在设置中启用 GPU 选项

### 识别结果重复

程序已内置去重逻辑，如仍有问题可调整：
- 启用"禁用上下文"选项
- 降低 `no_speech_threshold` 值

## 📄 许可证

MIT License

## 🙏 致谢

- [Whisper.NET](https://github.com/sandrohanea/whisper.net)
- [whisper.cpp](https://github.com/ggerganov/whisper.cpp)
- [MoviePy](https://github.com/Zulko/moviepy)
- [pythonnet](https://github.com/pythonnet/pythonnet)
