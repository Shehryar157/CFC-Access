@echo off
rem Steam launch option:  "C:\Users\Administrator\source\CFCAccess\launch.bat" %command%
rem Steam replaces %command% with the game's own command line and passes it
rem to us as %*. We start the mod in the background, then run the game.
start "" pythonw "%~dp0run.py" --with-game
%*
