# Windows 打包与分发（exe）

这个项目包含两类可执行程序：

- 桌宠 GUI：`index.py`（需要把 `assets/` 一起打包）
- 素材拆帧工具：`untils/split_frames.py`（命令行工具）

## 1) 在 Windows 上构建 exe（推荐）

PyInstaller 不能在 macOS 上直接产出 Windows 的 `.exe`，建议在 Windows 10/11 上打包。

注意：你当前在 macOS 的 zsh 终端里执行 `.\scripts\build_windows_setup.ps1` 会报错是正常的（那是 Windows PowerShell 语法）。

### 方式 A：一键脚本（PowerShell）

在项目根目录打开 PowerShell：

```powershell
.\scripts\build_windows_app.ps1
```

工具脚本：

```powershell
.\scripts\build_windows_split_frames.ps1
```

输出位置：

- 桌宠：`dist\蒜皮宝宝\蒜皮宝宝.exe`
- 工具：`dist\split_frames\split_frames.exe`

### 方式 C：没有 Windows 电脑也能打包（GitHub Actions）

仓库已提供自动构建工作流：[build-windows-installer.yml](file:///Users/yxy/LearningStageProject/PyQt6/蒜皮宝宝/.github/workflows/build-windows-installer.yml)

使用方式：

1. 把项目推到 GitHub
2. 打开仓库 → Actions → Build Windows installer → Run workflow
3. 构建完成后在 Artifacts 下载 `setup_蒜皮宝宝.exe`

### 方式 B：bat

```bat
scripts\build_windows_app.bat
```

## 2) 分发给别人“安装即用”

最简单的方式是把整个 `dist\蒜皮宝宝\` 文件夹打包成 zip 发出去，对方解压后双击 `蒜皮宝宝.exe` 即可。

如果你需要“安装程序 setup.exe”（带开始菜单快捷方式、卸载等），已提供 Inno Setup 脚本与一键构建脚本。

### 2.1 安装 Inno Setup

到官网安装 Inno Setup（安装后会提供 `iscc.exe` 编译器）。

### 2.2 一键生成 setup.exe

在项目根目录打开 PowerShell：

```powershell
.\scripts\build_windows_setup.ps1
```

输出位置：

- 安装包：`dist_installer\setup_蒜皮宝宝.exe`

### 2.3 自定义安装包信息（可选）

可以在 [installer_inno.iss](file:///Users/yxy/LearningStageProject/PyQt6/蒜皮宝宝/packaging/installer_inno.iss) 顶部修改：

- `MyAppName` / `MyAppVersion`
- 安装默认目录、是否需要管理员权限、是否创建桌面图标等

## 3) 资源路径说明

代码已改为使用“脚本所在目录/打包解包目录”定位 `assets/`，不依赖当前工作目录。

也可以手动指定素材目录：

```bat
蒜皮宝宝.exe --assets-dir D:\xxx\assets
```
