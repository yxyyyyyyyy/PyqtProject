#!/bin/bash

echo "======================================"
echo "    桌宠 - macOS 打包脚本"
echo "======================================"
echo ""

if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
fi

echo "🔧 激活虚拟环境..."
source venv/bin/activate

echo "📚 安装依赖..."
pip install -r requirements.txt

echo "⚡ 开始打包..."
pyinstaller --clean desktop_pet.spec

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 打包成功！"
    echo "📦 输出位置: dist/桌宠.app"
    echo ""
    
    read -p "是否创建 DMG 安装包? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "📦 创建 DMG..."
        hdiutil create -volname "桌宠" -srcfolder dist/桌宠.app -ov -format UDZO DesktopPet.dmg
        echo "✅ DMG 创建成功: DesktopPet.dmg"
    fi
else
    echo ""
    echo "❌ 打包失败！"
    exit 1
fi

echo ""
echo "======================================"
