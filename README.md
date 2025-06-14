# Navidrome On Console Player

NOCP (Navidrome On Console Player) is a console audio player designed to be powerful and easy to use inpired bien MOCP (Music On Console Player).

![custom-field](nocpglobal.png "Nocp")


## install

> pip install nocp

## usage

> nocp --help

> nocp --server-url http://myserver-navidrome/rest --username myusername --password mypassword --lang en_US

after just

> nocp

You can access to three views

- listing song (shorcut **m**)
- listing radio (shorcut **r**)
- listing playlist (shorcut **l**)

You can access to

- help (shorcut **h**)
- volume (shorcut **v**)

You can listen to a song by selecting it and pressing "Enter"

![custom-field](nocpaction.png "help")


## addshorcut

on ubuntu, create file ~/.local/share/applications/nocp.desktop

```
[Desktop Entry]
Type=Application
Name=Nocp
Exec=gnome-terminal -- bash -c 'nocp; exit;'
Icon=utilities-terminal
Terminal=false
```

and

> chmod +x ~/.local/share/applications/nocp.desktop


## todo

- traduction
- random listen