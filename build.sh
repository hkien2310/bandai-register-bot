#!/bin/bash
echo "Đang dọn dẹp thư mục build cũ..."
rm -rf build
rm -rf dist

echo "Đang build BandaiRegister..."
pyinstaller --clean -y RegisterBot.spec
if [ $? -ne 0 ]; then
    echo "[LỖI] PyInstaller build thất bại!"
    exit 1
fi

echo "Tạo thư mục Release..."
rm -rf Release
mkdir -p Release

echo "Copy file thực thi vào Release..."
if [ -d "dist/BandaiRegister.app" ]; then
    cp -r dist/BandaiRegister.app Release/
elif [ -f "dist/BandaiRegister" ]; then
    cp dist/BandaiRegister Release/
else
    echo "[LỖI] Không tìm thấy file build trong thư mục dist!"
    exit 1
fi

echo "Copy file cấu hình..."
cp config.json Release/

echo "Tạo thư mục data trống..."
mkdir -p Release/data

echo "Copy Playwright browsers..."
cp -R ~/Library/Caches/ms-playwright Release/ms-playwright-browsers

echo "Hoàn thành!"
