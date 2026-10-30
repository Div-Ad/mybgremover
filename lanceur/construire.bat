@echo off
rem Construit MyBGRemover.exe (icone comprise) et le lance a chaque ouverture de session
rem Windows, en mode serveur seul : l'app installee depuis Chrome le trouve toujours pret.
cd /d "%~dp0.."
%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe /nologo /target:winexe /optimize /codepage:65001 ^
  /win32icon:lanceur\icone.ico /reference:System.Windows.Forms.dll ^
  /out:MyBGRemover.exe lanceur\Lanceur.cs || goto erreur
powershell -NoProfile -Command "$r = (Resolve-Path .).Path; $l = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup') + '\MyBGRemover.lnk'); $l.TargetPath = \"$r\MyBGRemover.exe\"; $l.Arguments = '--serveur'; $l.WorkingDirectory = $r; $l.IconLocation = \"$r\MyBGRemover.exe,0\"; $l.Description = 'Serveur de MyBGRemover'; $l.Save(); Remove-Item ([Environment]::GetFolderPath('Programs') + '\MyBGRemover.lnk') -ErrorAction SilentlyContinue" || goto erreur
echo MyBGRemover.exe construit ; le serveur demarrera avec Windows.
echo Ouvre MyBGRemover.exe une fois, puis installe l'app depuis Chrome (icone Installer de la barre d'adresse).
goto :eof
:erreur
echo Echec de la construction.
exit /b 1
