# Whisper.NET 安装指南

## 这是什么？

Whisper.NET 是一个语音识别引擎，可以让你的 AMD 显卡通过 Vulkan 加速来识别语音（不用 NVIDIA 的 CUDA）。

---

## 第一步：下载 DLL 文件

### 需要下载的文件列表

**托管 DLL**（下载后放到 `deps/` 文件夹）：

| 文件名 | 版本 | 下载链接 |
|--------|------|----------|
| Whisper.net.dll | 1.9.0 | [点击下载](https://www.nuget.org/packages/Whisper.net/1.9.0) |
| Microsoft.Extensions.AI.Abstractions.dll | 10.0.0 | [点击下载](https://www.nuget.org/packages/Microsoft.Extensions.AI.Abstractions/10.0.0) |
| Microsoft.Bcl.AsyncInterfaces.dll | 10.0.0 | [点击下载](https://www.nuget.org/packages/Microsoft.Bcl.AsyncInterfaces/10.0.0) |
| System.Memory.dll | 4.6.3 | [点击下载](https://www.nuget.org/packages/System.Memory/4.6.3) |
| System.Buffers.dll | 4.6.1 | [点击下载](https://www.nuget.org/packages/System.Buffers/4.6.1) |
| System.Runtime.CompilerServices.Unsafe.dll | 6.1.2 | [点击下载](https://www.nuget.org/packages/System.Runtime.CompilerServices.Unsafe/6.1.2) |
| System.Numerics.Vectors.dll | 4.6.1 | [点击下载](https://www.nuget.org/packages/System.Numerics.Vectors/4.6.1) |

**Native DLL**（下载后放到 `deps/native/` 文件夹）：

从 [Whisper.net.Runtime.Vulkan 1.9.0](https://www.nuget.org/packages/Whisper.net.Runtime.Vulkan/1.9.0) 下载，解压后把 `build/win-x64/` 文件夹里的**所有 DLL 文件**都复制到 `deps/native/`。

NuGet 包里包含这些文件（全部需要）：

| 文件名 | 大小 | 用途 |
|--------|------|------|
| whisper.dll | 473KB | 语音识别核心 |
| libwhisper.dll | 473KB | whisper.dll 的别名（必需） |
| ggml-whisper.dll | 66KB | 计算库 |
| libggml-whisper.dll | 66KB | ggml-whisper.dll 的别名 |
| ggml-base-whisper.dll | 528KB | 基础库（必需依赖） |
| libggml-base-whisper.dll | 528KB | ggml-base-whisper.dll 的别名 |
| ggml-cpu-whisper.dll | 590KB | CPU 后备 |
| libggml-cpu-whisper.dll | 590KB | ggml-cpu-whisper.dll 的别名 |
| ggml-vulkan-whisper.dll | 45MB | GPU 加速（Vulkan） |
| libggml-vulkan-whisper.dll | 45MB | ggml-vulkan-whisper.dll 的别名 |

### 如何从 NuGet 下载？

1. 点击上面的链接打开 NuGet 页面
2. 点击 **"Download package"** 下载 `.nupkg` 文件
3. 把 `.nupkg` 文件后缀改成 `.zip`，用解压软件打开
4. 找到里面的 DLL 文件：
   - 托管 DLL 在 `lib/netstandard2.0/` 文件夹里
   - Native DLL 在 `build/win-x64/` 文件夹里

---

## 第二步：下载语音模型

从 [ggerganov/whisper.cpp models](https://github.com/ggerganov/whisper.cpp/tree/master/models) 下载 `.bin` 格式的模型文件，放到 `models/` 文件夹。

推荐下载：`ggml-large-v3-turbo.bin`（效果好、速度快）

---

## 第三步：检查文件结构

确保你的目录结构是这样的：

```
pyvideotrans/
├─ models/
│  └─ ggml-large-v3-turbo.bin    ← 语音模型
└─ deps/
   ├─ Whisper.net.dll            ← 下面 7 个是托管 DLL
   ├─ Microsoft.Extensions.AI.Abstractions.dll
   ├─ Microsoft.Bcl.AsyncInterfaces.dll
   ├─ System.Memory.dll
   ├─ System.Buffers.dll
   ├─ System.Runtime.CompilerServices.Unsafe.dll
   ├─ System.Numerics.Vectors.dll
   └─ native/                     ← 把 NuGet 包里 build/win-x64/ 的所有 DLL 复制到这里
      ├─ whisper.dll
      ├─ libwhisper.dll
      ├─ ggml-whisper.dll
      ├─ libggml-whisper.dll
      ├─ ggml-base-whisper.dll
      ├─ libggml-base-whisper.dll
      ├─ ggml-cpu-whisper.dll
      ├─ libggml-cpu-whisper.dll
      ├─ ggml-vulkan-whisper.dll
      └─ libggml-vulkan-whisper.dll
```

---

## 第四步：开始使用

1. 打开 pyVideoTrans
2. 在"语音识别"下拉框选择 **"Whisper.NET"**
3. 选择你下载的模型文件
4. 点击开始

---

## 遇到问题？

### 提示 "Native Library not found" 或错误代码 `0x8007007E`

- 检查 `deps/native/` 文件夹里是否有 4 个 DLL 文件
- 检查文件名是否正确

### GPU 加速不工作

- 更新显卡驱动
- AMD 显卡需要支持 Vulkan（RX 400 系列及以上）
- NVIDIA 显卡需要 GTX 600 系列及以上

### 提示 pythonnet 初始化失败

- 安装 [.NET Runtime](https://dotnet.microsoft.com/download/dotnet)（选最新的 .NET 8 或 .NET 9）

### 想确认显卡是否支持 Vulkan

打开命令行，输入：
```
vulkaninfo
```
如果显示显卡信息就说明支持。