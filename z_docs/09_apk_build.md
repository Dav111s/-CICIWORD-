# 「萃词 Lexera」安卓 APK 打包指南

## 一、环境要求（缺一不可）
打包是 Flet 调用 Flutter + Android 工具链完成的，本机需安装：

1. **Flutter SDK**（flet 0.28.3 依赖 Flutter 构建 APK）
   - https://docs.flutter.dev/get-started/install/windows
   - 安装后把 `flutter\bin` 加入 PATH，`flutter doctor` 确认 Android toolchain 项通过。
2. **JDK**（Flutter 建议 OpenJDK 17）
   - 安装后 `java -version` 能输出版本号。
3. **Android SDK + SDK Platform + Build-Tools**
   - 通过 Android Studio 或命令行 `sdkmanager` 安装。
   - 设置环境变量 `ANDROID_HOME`（或 `ANDROID_SDK_ROOT`）指向 SDK 根目录。
   - 首次构建需联网下载 Gradle 与依赖。
4. **flet-cli**（`flet build` 命令本体）
   - 当前环境 `flet build` 报 `WinError 5`（权限不足），需以管理员身份运行：
     ```
     pip install "flet[all]==0.28.3" --upgrade
     ```
   - 或单独装：`pip install flet-cli==0.28.3`。

> 本机现状：以上 4 项均缺失，因此当前无法直接 `flet build apk`。装齐后再执行下面步骤。

## 二、项目准备

1. **移动依赖**：`requirements-mobile.txt` 已精简为仅 `flet==0.28.3`
   （numpy/torch/onnxruntime 是废弃代码 ai/memory_model.py 的依赖，已不参与运行，无需打进 APK）。
2. **图标 / 启动图**（可选，不提供则用 flet 默认图标）：
   - `assets/icon.png`（建议 1024×1024）
   - `assets/splash.png`（竖屏启动图）
3. **数据目录**：`paths.py` 支持环境变量 `WORD_APP_DATA_DIR` 注入安卓私有可写目录。
   建议在 `main()` 启动时按需处理（当前桌面端默认写项目根目录，安卓端应用私有目录可写）。
   如无特殊需求，flet 打包后默认工作目录即应用私有目录，可直接运行。

## 三、构建命令

```powershell
# 1) 切到项目根目录
cd C:\Users\DavisStark\PycharmProjects\word_app

# 2) 构建 APK（包名 = org.project = com.lexera.ciciword）
flet build apk --org com.lexera --project ciciword --product "萃词"

# 如需要指定权限/额外包，可加：
#   --android-permissions android.permission.INTERNET
#   --include-packages flet
```

- 产物路径：`build/apk/`（文件名类似 `ciciword-release.apk`）。
- 首次构建会下载 Gradle 依赖，耗时较长、需保持联网。

## 四、常见问题

1. **`flet build` 提示要升级 flet-cli / WinError 5**：以管理员运行
   `pip install "flet[all]==0.28.3" --upgrade`，或修复 venv 目录写权限。
2. **`flutter doctor` 报 Android license 未接受**：运行 `flutter doctor --android-licenses` 一路 `y`。
3. **图标缺失**：flet 会用默认图标，不影响构建；要自定义就在 `assets/` 放 `icon.png`/`splash.png`。
4. **应用签名**：默认用 debug 签名可直接安装调试；上架需用 `--base64-credentials` 配置正式签名。

## 五、安装到手机

```powershell
# 手机开启 USB 调试后：
adb install build/apk/ciciword-release.apk
# 或直接把 APK 文件传到手机点击安装

---

# （续）APK 打包踩坑历程（按日期）

## 2026-08-28
- 明确本机 4 项环境缺失（Flutter / JDK / Android SDK / flet-cli），暂无法 `flet build apk`。

## 2026-08-29
- 逐项补齐环境：JDK 17（Microsoft，`C:\Users\DavisStark\java\17.0.13+11`）、Flutter 3.29.2、Android SDK（android-35 / build-tools 34.0.0）、git（`E:\Git\cmd`）、本地构建模板 + 最小依赖。
- 阻塞：文件策略回退 workspace-write 导致 subprocess 命名管道挂起，构建中断；用户决定「先不打包了」。

## 当前状态
- APK / 桌面 exe 打包暂停，待后续恢复（批量识别、记忆算法等其余功能同步暂停，等待下一步指示）。
```

## 2026-09-03
- 打包无新进展，维持「先不打包了」；词库数据源改为 `data/builtin` 下 7 份 JSON，由 `data/bank.py` 代码内合并生成总词库。
