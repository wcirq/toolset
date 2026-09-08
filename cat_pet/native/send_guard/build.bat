@echo off
setlocal
set "PROJECT=%~dp0CoolCatSendGuard.vcxproj"
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if exist "%VSWHERE%" goto vswhere_found
echo Visual Studio Build Tools not found: %VSWHERE%
exit /b 1

:vswhere_found
set "RESULT_FILE=%TEMP%\coolcat_send_msbuild_%RANDOM%_%RANDOM%.txt"
"%VSWHERE%" -latest -products * -requires Microsoft.Component.MSBuild -find MSBuild\**\Bin\MSBuild.exe > "%RESULT_FILE%"
set /p "MSBUILD="<"%RESULT_FILE%"
del /q "%RESULT_FILE%" >nul 2>&1
if defined MSBUILD goto msbuild_found
echo MSBuild not found. Install Desktop development with C++.
exit /b 1

:msbuild_found
"%MSBUILD%" "%PROJECT%" /m /t:Build /p:Configuration=Release /p:Platform=x64 /v:minimal
if not "%errorlevel%"=="0" (
  echo.
  echo If LNK1104 names CoolCatSendGuardV2_64.dll, the existing DLL is locked by a running CoolCat/Python process or security software.
)
exit /b %errorlevel%
