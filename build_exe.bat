@echo off
rem 打包单文件 exe (免 Python 双击即用)。产物: dist\X7PrintStudio.exe
python -m pip install --disable-pip-version-check -r requirements.txt || goto :err
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name X7PrintStudio ^
  --collect-all lzo ^
  main.py || goto :err
echo.
echo 打包完成: dist\X7PrintStudio.exe
exit /b 0
:err
echo 打包失败, 请查看上方错误信息
pause
exit /b 1
