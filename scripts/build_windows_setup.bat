@echo off
setlocal

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

pyinstaller --clean --noconfirm packaging\spbb_app.spec

where iscc >nul 2>nul
if errorlevel 1 (
  echo 未找到 iscc.exe（Inno Setup 编译器）。请先安装 Inno Setup，然后重开终端再运行。
  exit /b 1
)

iscc packaging\installer_inno.iss

