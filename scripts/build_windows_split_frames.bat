@echo off
setlocal

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

pyinstaller --clean --noconfirm packaging\split_frames.spec

