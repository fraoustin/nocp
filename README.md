# Navidrome On Console Player

NOCP (Navidrome On Console Player) is a console audio player designed to be powerful and easy to use inpired bien MOCP (Music On Console Player).

## install

> pip install nocp

## usage

> nocp --help

> nocp --server-url http://myserver-navidrome/rest --username myusername --password mypassword

after just

> nocp

## addshorcut

on ubuntu, create file ~/.local/share/applications/nocp.desktop

```
[Desktop Entry]
Type=Application
Name=Nocp
Exec=gnome-terminal -- bash -c 'nocp; exec bash'
Icon=utilities-terminal
Terminal=false
```

and

> chmod +x ~/.local/share/applications/nocp.desktop