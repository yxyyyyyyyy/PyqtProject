$ErrorActionPreference = "Stop"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

pyinstaller --clean --noconfirm packaging\spbb_app.spec

