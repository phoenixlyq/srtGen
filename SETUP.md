# Whisper.NET Setup (Vulkan, Windows)

This project uses Whisper.NET 1.9.0 with the Vulkan runtime (AMD GPU).

## Required packages and versions

Core:
- Whisper.net 1.9.0 (use `lib/netstandard2.0/Whisper.net.dll`)
- Whisper.net.Runtime.Vulkan 1.9.0 (use `build/win-x64/*.dll`)

Managed dependencies (place in `deps/`):
- Microsoft.Extensions.AI.Abstractions 10.0.0
- Microsoft.Bcl.AsyncInterfaces 10.0.0
- System.Memory 4.6.3
- System.Buffers 4.6.1
- System.Runtime.CompilerServices.Unsafe 6.1.2
- System.Numerics.Vectors 4.6.1

Native runtime DLLs (place in `deps/native/` and/or `deps/runtimes/win-x64/native/`):
- whisper.dll
- ggml-whisper.dll
- ggml-vulkan-whisper.dll
- ggml-cpu-whisper.dll
- ggml-base-whisper.dll

## Recommended directory layout

```
your_app/
├─ main.py
├─ models/
│  ├─ ggml-base.bin
│  ├─ ggml-small.bin
│  ├─ ggml-medium.bin
│  ├─ ggml-large-v2.bin
│  ├─ ggml-large-v3.bin
│  └─ ggml-large-v3-turbo.bin
└─ deps/
   ├─ Whisper.net.dll
   ├─ Microsoft.Extensions.AI.Abstractions.dll
   ├─ Microsoft.Bcl.AsyncInterfaces.dll
   ├─ System.Memory.dll
   ├─ System.Buffers.dll
   ├─ System.Runtime.CompilerServices.Unsafe.dll
   ├─ System.Numerics.Vectors.dll
   ├─ native/
   │  ├─ whisper.dll
   │  ├─ ggml-whisper.dll
   │  ├─ ggml-vulkan-whisper.dll
   │  ├─ ggml-cpu-whisper.dll
   │  └─ ggml-base-whisper.dll
   └─ runtimes/
      └─ win-x64/
         └─ native/
            ├─ whisper.dll
            ├─ ggml-whisper.dll
            ├─ ggml-vulkan-whisper.dll
            ├─ ggml-cpu-whisper.dll
            └─ ggml-base-whisper.dll
```

Either `deps/native` or `deps/runtimes/win-x64/native` is enough. Keeping both is fine.

## Download with NuGet

```powershell
nuget.exe install Whisper.net -Version 1.9.0 -OutputDirectory C:\Users\phoen\packages
nuget.exe install Whisper.net.Runtime.Vulkan -Version 1.9.0 -OutputDirectory C:\Users\phoen\packages

nuget.exe install Microsoft.Extensions.AI.Abstractions -Version 10.0.0 -OutputDirectory C:\Users\phoen\packages
nuget.exe install Microsoft.Bcl.AsyncInterfaces -Version 10.0.0 -OutputDirectory C:\Users\phoen\packages
nuget.exe install System.Memory -Version 4.6.3 -OutputDirectory C:\Users\phoen\packages
nuget.exe install System.Buffers -Version 4.6.1 -OutputDirectory C:\Users\phoen\packages
nuget.exe install System.Runtime.CompilerServices.Unsafe -Version 6.1.2 -OutputDirectory C:\Users\phoen\packages
nuget.exe install System.Numerics.Vectors -Version 4.6.1 -OutputDirectory C:\Users\phoen\packages
```

## Copy commands (from NuGet cache)

```powershell
# Whisper.net.dll
Copy-Item "C:\Users\phoen\packages\Whisper.net.1.9.0\Whisper.net.1.9.0\lib\netstandard2.0\Whisper.net.dll" `
  "D:\SoftWareDevelop\PycharmProjects\SrtGen\deps\" -Force

# Managed dependencies
Copy-Item "C:\Users\phoen\packages\Microsoft.Extensions.AI.Abstractions.10.0.0\lib\netstandard2.0\Microsoft.Extensions.AI.Abstractions.dll" `
  "D:\SoftWareDevelop\PycharmProjects\SrtGen\deps\" -Force
Copy-Item "C:\Users\phoen\packages\Microsoft.Bcl.AsyncInterfaces.10.0.0\lib\netstandard2.0\Microsoft.Bcl.AsyncInterfaces.dll" `
  "D:\SoftWareDevelop\PycharmProjects\SrtGen\deps\" -Force
Copy-Item "C:\Users\phoen\packages\System.Memory.4.6.3\lib\netstandard2.0\System.Memory.dll" `
  "D:\SoftWareDevelop\PycharmProjects\SrtGen\deps\" -Force
Copy-Item "C:\Users\phoen\packages\System.Buffers.4.6.1\lib\netstandard2.0\System.Buffers.dll" `
  "D:\SoftWareDevelop\PycharmProjects\SrtGen\deps\" -Force
Copy-Item "C:\Users\phoen\packages\System.Runtime.CompilerServices.Unsafe.6.1.2\lib\netstandard2.0\System.Runtime.CompilerServices.Unsafe.dll" `
  "D:\SoftWareDevelop\PycharmProjects\SrtGen\deps\" -Force
Copy-Item "C:\Users\phoen\packages\System.Numerics.Vectors.4.6.1\lib\netstandard2.0\System.Numerics.Vectors.dll" `
  "D:\SoftWareDevelop\PycharmProjects\SrtGen\deps\" -Force

# Vulkan native DLLs
Copy-Item "C:\Users\phoen\packages\Whisper.net.Runtime.Vulkan.1.9.0\Whisper.net.Runtime.Vulkan.1.9.0\build\win-x64\*.dll" `
  "D:\SoftWareDevelop\PycharmProjects\SrtGen\deps\native\" -Force
```

## Notes

- Model files must be `.bin` in `models/` and match the GUI dropdown names.
- If you hit error `0x8007007E`, it is usually missing runtime dependencies or DLL search paths.
- If needed, you can temporarily copy native DLLs to the project root to verify path issues.
