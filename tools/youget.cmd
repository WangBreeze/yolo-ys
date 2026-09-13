@echo off
call "%~dp0video.cmd" download %*
exit /b %errorlevel%
