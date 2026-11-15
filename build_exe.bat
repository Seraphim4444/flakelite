@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === FlakeLite: сборка FlakeLite.exe ===
echo.
python -m pip install --quiet --disable-pip-version-check pyinstaller
if errorlevel 1 goto err
python -m PyInstaller --noconfirm --clean --onefile --noconsole ^
    --name FlakeLite --icon flake.ico programm.py
if errorlevel 1 goto err
echo.
echo Готово: dist\FlakeLite.exe
echo Этот файл можно переносить на другой компьютер с Windows 10/11.
pause
exit /b 0
:err
echo.
echo Не удалось собрать exe. Проверьте, что установлен Python и PyInstaller.
pause
exit /b 1
