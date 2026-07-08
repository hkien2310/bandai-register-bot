@echo off
cd /d "%~dp0"
echo Dang don dep thu muc build cu...
rmdir /s /q build
rmdir /s /q dist

echo Dang build BandaiRegister...
pyinstaller --clean -y RegisterBot.spec
if %ERRORLEVEL% neq 0 (
    echo [LOI] PyInstaller build that bai!
    pause
    exit /b %ERRORLEVEL%
)

echo Tao thu muc Release...
if exist "Release" rmdir /s /q "Release"
mkdir "Release"

echo Copy file thuc thi vao Release...
if not exist "dist\BandaiRegister.exe" (
    echo [LOI] Khong tim thay dist\BandaiRegister.exe. PyInstaller co the da gap loi.
    pause
    exit /b 1
)
copy "dist\BandaiRegister.exe" "Release\"

echo Copy file cau hinh...
copy "config.json" "Release\"
echo Tao thu muc data trong...
if not exist "Release\data" mkdir "Release\data"

echo Copy Playwright browsers...
xcopy "%USERPROFILE%\AppData\Local\ms-playwright" "Release\ms-playwright-browsers" /E /I /H /Y

echo Hoan thanh!
pause
