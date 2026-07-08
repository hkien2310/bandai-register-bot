@echo off
echo Dang don dep thu muc build cu...
rmdir /s /q build
rmdir /s /q dist

echo Dang build BandaiRegister...
pyinstaller --clean -y RegisterBot.spec

echo Tao thu muc Release...
if not exist "Release" mkdir Release
del /q "Release\*"

echo Copy file thuc thi vao Release...
copy "dist\BandaiRegister.exe" "Release\"

echo Copy file cau hinh...
copy "config.json" "Release\"
echo Tao thu muc data trong...
if not exist "Release\data" mkdir "Release\data"

echo Copy Playwright browsers...
xcopy "%USERPROFILE%\AppData\Local\ms-playwright" "Release\ms-playwright-browsers" /E /I /H /Y

echo Hoan thanh!
pause
