@echo off
chcp 65001 >nul
echo Создание структуры папок КП_База...

mkdir data 2>nul
mkdir projects 2>nul
mkdir templates\mappings 2>nul
mkdir scripts 2>nul
mkdir "КП_Итоговые" 2>nul

echo.
echo Готово! Структура создана в текущей папке:
echo   data\           — база цен (локально, не в Git)
echo   projects\       — КП по объектам
echo   templates\      — шаблоны и карты заказчиков
echo   scripts\        — скрипты подстановки цен
echo   КП_Итоговые\    — готовые КП
echo.
pause
