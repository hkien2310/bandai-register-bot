#!/bin/bash
echo "Đang dọn dẹp thư mục build cũ..."
rm -rf build
rm -rf dist

echo "Đang build BandaiRegister..."
pyinstaller --clean -y RegisterBot.spec

echo "Tạo thư mục Release..."
mkdir -p Release
rm -rf Release/*

echo "Copy file thực thi vào Release..."
if [ -d "dist/BandaiRegister.app" ]; then
    cp -r dist/BandaiRegister.app Release/
else
    cp dist/BandaiRegister Release/
fi

echo "Copy file cấu hình..."
cp config.json Release/

echo "Tạo thư mục data trống..."
mkdir -p Release/data

echo "Copy Playwright browsers..."
cp -R ~/Library/Caches/ms-playwright Release/ms-playwright-browsers

echo "Hoàn thành!"
