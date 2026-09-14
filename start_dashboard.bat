@echo off
cd /d "%~dp0\frontend"
if not exist node_modules ( npm install )
echo.
echo   Dashboard  ->  http://localhost:5173
echo.
npm run dev
