@echo off
chcp 65001 >nul
cd /d "%~dp0"

set /p VIDEO_URL="請貼上要處理的YouTube網址（直接按Enter使用.env裡現有的網址）: "

if not "%VIDEO_URL%"=="" (
    powershell -Command "(Get-Content .env -Encoding UTF8) -replace 'SOURCE_VIDEO_URL=.*', 'SOURCE_VIDEO_URL=%VIDEO_URL%' | Set-Content .env -Encoding UTF8"
)

call .venv\Scripts\activate
cd src
python pipeline.py
cd ..
pause