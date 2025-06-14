import urwid
import random
import string
import hashlib
import requests
import vlc
import argparse
import configparser
import click
import os
import time

import gettext
import locale


DEFAULT_CONFIG_PATH = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), ".nocp", "config.ini")

__version__ = "0.2.1"


def load_config(config_path):
    config = configparser.ConfigParser()
    if os.path.exists(config_path):
        config.read(config_path)
        return config["DEFAULT"]
    return {}


def save_config(username, password, server_url, config_path, lang):
    config = configparser.ConfigParser()
    config['DEFAULT'] = {
        'username': username,
        'password': password,
        'server_url': server_url,
        'lang': lang
    }
    config_dir = os.path.dirname(config_path)
    os.makedirs(config_dir, exist_ok=True)
    with open(config_path, 'w') as configfile:
        config.write(configfile)


class Generic:

    def __init__(self, **kw):
        for elt in kw:
            setattr(self, elt, kw[elt])


class Song(Generic):

    def __init__(self, **kw):
        Generic.__init__(self, **kw)

    @property
    def timer(self):
        return f"{self.duration // 60}:{self.duration % 60:02d}"

    @property
    def streamUrl(self):
        params = self.nav.build_params()
        params['id'] = self.id
        req = requests.Request('GET', f"{self.nav.url}/stream.view", params=params)
        return req.prepare().url


class Album(Generic):

    def __init__(self, **kw):
        Generic.__init__(self, **kw)

    @property
    def songs(self):
        data = self.nav.request("getMusicDirectory.view", id=self.id)
        songs = [Song(nav=self.nav, prev=None, next=None, **song) for song in data['subsonic-response']['directory']['child']]
        for i, song in enumerate(songs):
            song.next = songs[i + 1] if i + 1 < len(songs) else None
            song.prev = songs[i - 1] if i - 1 >= 0 else None
        return songs


class Artist(Generic):

    def __init__(self, **kw):
        Generic.__init__(self, **kw)

    @property
    def albums(self):
        data = self.nav.request("getArtist.view", id=self.id)
        albums = data['subsonic-response']['artist']['album']
        return [Album(nav=self.nav, **album) for album in albums]


class Radio(Generic):

    def __init__(self, **kw):
        Generic.__init__(self, **kw)

    @property
    def title(self):
        return self.name


class Playlist(Generic):

    def __init__(self, **kw):
        Generic.__init__(self, **kw)

    @property
    def songs(self):
        data = self.nav.request("getPlaylist.view", id=self.id)
        songs = [Song(nav=self.nav, next=None, **song) for song in data['subsonic-response']['playlist'].get('entry', [])]
        for i, song in enumerate(songs):
            song.next = songs[i + 1] if i + 1 < len(songs) else None
            song.prev = songs[i - 1] if i - 1 >= 0 else None
        return songs


class Navidrome:

    def __init__(self, url, username, client, password, version):
        self.url = url
        self.username = username
        self.client = client
        self.password = password
        self.version = version
        self.salt = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        self.token = hashlib.md5((self.password + self.salt).encode('utf-8')).hexdigest()

    def build_params(self):
        return {
            'u': self.username,
            't': self.token,
            's': self.salt,
            'v': self.version,
            'c': self.client,
            'f': 'json'
        }

    def request(self, view, **kw):
        params = self.build_params()
        for elt in kw:
            params[elt] = kw[elt]
        response = requests.get(f"{self.url}/{view}", params=params)
        return response.json()

    @property
    def artists(self):
        data = self.request("getArtists.view")
        artists = data['subsonic-response']['artists']['index']
        result = []
        for index in artists:
            for artist in index['artist']:
                result.append(Artist(nav=self, **artist))
        return result

    @property
    def radios(self):
        data = self.request("getInternetRadioStations.view")
        stations = data['subsonic-response'].get('internetRadioStations', {}).get('internetRadioStation', [])
        return [Radio(nav=self, **station) for station in stations]

    @property
    def playlists(self):
        data = self.request("getPlaylists.view")
        playlists = data['subsonic-response']['playlists']['playlist']
        return [Playlist(nav=self, **playlist) for playlist in playlists]


class HelpOverlay(urwid.WidgetWrap):
    def __init__(self, on_exit):
        shortcuts = [
            "🎵 " + _("Music") + " : m",
            "📻 " + _("Radio") + " : r",
            "📂 " + _("Playlists") + " : l",
            "🔊 " + _("Volume") + " : v",
            "❓ " + _("Help") + " : h",
            "⏹ " + _("Quit") + " : q",
            _("pause/play") + " : <space>",
            _("Next") + " : n",
            _("Previous") + " : p",
            "",
            _("Navigation") + " : ↑ ↓",
            _("Change panel") + " : tab",
            _("Select") + " : enter",
            _("Quit this help") + " : esc",
            "",
            _("version {__version__}").format(__version__=__version__),
        ]
        help_text = urwid.Text("\n".join(shortcuts), align='left')
        padded = urwid.Padding(help_text, left=2, right=2)
        box = urwid.LineBox(urwid.Filler(padded, valign='top'), title="❓ " + _("Keyboard shortcut"))
        super().__init__(box)
        self.on_exit = on_exit

    def selectable(self):
        return True

    def keypress(self, size, key):
        if key in ('esc', 'enter'):
            self.on_exit()
            return None
        return key


class VolumeGauge(urwid.WidgetWrap):
    def __init__(self, on_exit, on_change=None, initial=50):
        self.value = initial
        self.on_change = on_change
        self.on_exit = on_exit
        self.gauge = urwid.Text(self.render_gauge(), align='center')
        self.layout = urwid.Filler(self.gauge, valign='middle')
        super().__init__(urwid.LineBox(self.layout, title="🔊 " + _("Volume")))

    def render_gauge(self):
        filled = int(self.value // 5)
        empty = 20 - filled
        bar = "\n".join([" "] * empty + ["██"] * filled)
        return f"Volume: {self.value}%\n\n{bar}"

    def selectable(self):
        return True

    def keypress(self, size, key):
        if key == 'up':
            self.value = min(100, self.value + 5)
        elif key == 'down':
            self.value = max(0, self.value - 5)
        elif key in ('esc', 'enter'):
            self.on_exit()
            return None
        self.gauge.set_text(self.render_gauge())
        if self.on_change:
            self.on_change(self.value)
        return None


class PlainButton(urwid.WidgetWrap):
    def __init__(self, label_widget, on_press=None, user_data=None):
        self.label_widget = label_widget
        self.attr_map = urwid.AttrMap(label_widget, None, focus_map='reversed')
        super().__init__(self.attr_map)
        self._on_press = on_press
        self._user_data = user_data

    def selectable(self):
        return True

    def keypress(self, size, key):
        if key == 'enter' and self._on_press:
            self._on_press(self, self._user_data)
            return None
        return key

    def get_label(self):
        if isinstance(self.label_widget, urwid.Columns):
            return self.label_widget.contents[0][0].get_text()[0]
        return self.label_widget.get_text()[0]

    def set_selected(self, selected):
        self.attr_map.set_attr_map({None: 'selected' if selected else None})

    def mouse_event(self, size, event, button, x, y, focus):
        if event == 'mouse press' and button == 1:  # bouton gauche
            if self._on_press:
                self._on_press(self, self._user_data)
            return True
        return False


class MusicBrowser:
    def __init__(self, nav):
        self.nav = nav
        self.mode = "music"
        self.selected_artist = None
        self.selected_album = None
        self.selected_playlist = None
        self.focus_index = 0
        self.playlist_focus_index = 0
        self.playlist_focus_list = [None, None]  # placeholders

        self.artist_listbox = urwid.ListBox(urwid.SimpleFocusListWalker([]))
        self.album_listbox = urwid.ListBox(urwid.SimpleFocusListWalker([]))
        self.song_listbox = urwid.ListBox(urwid.SimpleFocusListWalker([]))
        self.radio_listbox = urwid.ListBox(urwid.SimpleFocusListWalker([]))
        self.playlist_listbox = urwid.ListBox(urwid.SimpleFocusListWalker([]))
        self.playlist_song_listbox = urwid.ListBox(urwid.SimpleFocusListWalker([]))

        self.playlist_focus_list = [self.playlist_listbox, self.playlist_song_listbox]

        self.footer_left = urwid.Text("🎵 " + _("No current songs"), align='left')
        self.footer_right = urwid.Text("00:00", align='right')
        self.footer_columns = urwid.Columns([self.footer_left, self.footer_right])

        self.focus_list = [self.artist_listbox, self.album_listbox, self.song_listbox]

        self.left_panel = urwid.LineBox(self.artist_listbox, title="🎤 " + _("Artists"))
        self.top_right = urwid.LineBox(self.album_listbox, title="💿 " + _("Albums"))
        self.bottom_right = urwid.LineBox(self.song_listbox, title="🎵 " + _("Songs"))

        self.radio_panel = urwid.LineBox(self.radio_listbox, title="📻 " + _("Radios"))

        self.playlist_panel = urwid.Pile([
            ('weight', 1, urwid.LineBox(self.playlist_listbox, title="📂 " + _("Playlists"))),
            ('weight', 1, urwid.LineBox(self.playlist_song_listbox, title="🎵 " + _("Songs")))
        ])

        self.right_panel = urwid.Pile([
            ('weight', 1, self.top_right),
            ('weight', 1, self.bottom_right)
        ])

        self.main_columns = urwid.Columns([
            ('weight', 1, self.left_panel),
            ('weight', 2, self.right_panel)
        ])

        self.main_layout = urwid.Frame(body=self.main_columns, footer=urwid.LineBox(self.footer_columns))

        self.loop = urwid.MainLoop(
            self.main_layout,
            palette=[
                ('reversed', 'standout', ''),
                ('selected', 'dark green', ''),
            ],
            unhandled_input=self.handle_input,
            handle_mouse=True
        )
        self.update_artist_list()
        self.update_radio_list()
        self.update_playlist_list()

    def update_artist_list(self):
        artists = self.nav.artists
        self.artist_listbox.body.clear()
        for artist in artists:
            txt = urwid.Text(artist.name)
            btn = PlainButton(txt, on_press=self.on_artist_selected, user_data=artist)
            self.artist_listbox.body.append(btn)
        self.on_artist_selected(None, artists[0])

    def update_album_list(self, albums):
        self.album_listbox.body.clear()
        for album in albums:
            txt = urwid.Text(album.name)
            btn = PlainButton(txt, on_press=self.on_album_selected, user_data=album)
            self.album_listbox.body.append(btn)

    def update_song_list(self, songs):
        self.song_listbox.body.clear()
        for song in songs:
            row = urwid.Columns([
                urwid.Text(song.title),
                urwid.Text(str(song.timer), align='right')
            ])
            btn = PlainButton(row, on_press=self.on_song_selected, user_data=song)
            self.song_listbox.body.append(btn)

    def update_radio_list(self):
        self.radio_listbox.body.clear()
        for radio in self.nav.radios:
            txt = urwid.Text(radio.name)
            btn = PlainButton(txt, on_press=self.on_radio_selected, user_data=radio)
            self.radio_listbox.body.append(btn)

    def update_playlist_list(self):
        playlists = self.nav.playlists
        self.playlist_listbox.body.clear()
        for playlist in playlists:
            txt = urwid.Text(playlist.name)
            btn = PlainButton(txt, on_press=self.on_playlist_selected, user_data=playlist)
            self.playlist_listbox.body.append(btn)
        self.on_playlist_selected(None, playlists[0])

    def update_playlist_song_list(self, songs):
        self.playlist_song_listbox.body.clear()
        for song in songs:
            txt = urwid.Text(song.title)
            btn = PlainButton(txt, on_press=self.on_song_selected, user_data=song)
            self.playlist_song_listbox.body.append(btn)

    def clear_selection(self, listbox):
        for btn in listbox.body:
            btn.set_selected(False)

    def on_artist_selected(self, button, artist):
        self.selected_artist = artist
        self.clear_selection(self.artist_listbox)
        for btn in self.artist_listbox.body:
            if btn.get_label() == artist.name:
                btn.set_selected(True)
                break
        albums = artist.albums
        self.update_album_list(albums)
        if len(albums) > 0:
            self.on_album_selected(None, albums[0])

    def on_album_selected(self, button, album):
        self.selected_album = album
        self.clear_selection(self.album_listbox)
        for btn in self.album_listbox.body:
            if btn.get_label() == album.name:
                btn.set_selected(True)
                break
        songs = album.songs
        self.update_song_list(songs)

    def on_song_selected(self, button, song):
        self.current_song = song
        self.clear_selection(self.song_listbox)
        self.clear_selection(self.playlist_song_listbox)
        for listbox in [self.song_listbox, self.playlist_song_listbox]:
            for btn in listbox.body:
                if btn.get_label() == song.title:
                    btn.set_selected(True)
                    break
        self.play_song()

    def play_song(self, bystop=True):
        try:
            full_url = requests.Request('GET', self.current_song.streamUrl).prepare().url
            if hasattr(self, 'player') and self.player:
                if self.player.get_state() != vlc.State.Ended:
                    self.player.stop()
            self.player = vlc.MediaPlayer(full_url)
            self.player.play()
            self.player.event_manager().event_attach(
                vlc.EventType.MediaPlayerEndReached,
                self.on_song_end
            )
            self.update_footer_now_playing()
            self.loop.set_alarm_in(1, self.update_playback_time)
        except Exception as e:
            self.footer_left.set_text("❌ " + _("VLC playback error : {error}").format(error=str(e)))

    def on_song_end(self, event=None):
        if self.current_song.next is not None:
            self.current_song = self.current_song.next
            self.loop.set_alarm_in(0.1, lambda loop, user_data: self.play_song())

    def on_song_prev(self, event=None):
        if self.current_song.prev is not None:
            self.current_song = self.current_song.prev
            self.play_song()

    def update_footer_now_playing(self):
        if self.current_song:
            self.footer_left.set_text(f"🎵 {self.current_song.title}")

    def update_playback_time(self, loop=None, user_data=None):
        if self.player and self.player.is_playing():
            ms = self.player.get_time()
            if ms != -1:
                seconds = ms // 1000
                minutes = seconds // 60
                seconds = seconds % 60
                self.footer_right.set_text(f"{minutes:02}:{seconds:02}")
            self.loop.set_alarm_in(1, self.update_playback_time)

    def on_radio_selected(self, button, radio):
        self.current_song = radio
        self.clear_selection(self.radio_listbox)
        for btn in self.radio_listbox.body:
            if btn.get_label() == radio.name:
                btn.set_selected(True)
                break
        try:
            full_url = requests.Request('GET', radio.streamUrl).prepare().url
            if hasattr(self, 'player') and self.player:
                self.player.stop()
            self.player = vlc.MediaPlayer(full_url)
            self.player.play()
            self.update_footer_now_playing()
            self.loop.set_alarm_in(1, self.update_playback_time)
        except Exception as e:
            self.footer_left.set_text("❌ " + _("VLC playback error : {error}").format(error=str(e)))

    def on_playlist_selected(self, button, playlist):
        self.selected_playlist = playlist.name
        self.clear_selection(self.playlist_listbox)
        for btn in self.playlist_listbox.body:
            if btn.get_label() == playlist.name:
                btn.set_selected(True)
                break
        songs = playlist.songs
        self.update_playlist_song_list(songs)

    def handle_input(self, key):
        if isinstance(key, str):
            if key in ('q', 'Q'):
                raise urwid.ExitMainLoop()
            elif key == 'tab':
                if self.mode == "music":
                    self.move_focus(1)
                elif self.mode == "playlist":
                    self.move_playlist_focus(1)
            elif key == 'enter':
                self.trigger_selection()
            elif key.lower() == 'v':
                self.show_volume_gauge()
            elif key.lower() == 'r':
                self.switch_to_radio_view()
            elif key.lower() == 'm':
                self.switch_to_music_view()
            elif key.lower() == 'h':
                self.show_help_overlay()
            elif key.lower() == 'l':
                self.switch_to_playlist_view()
            elif key.lower() == 'n':
                self.on_song_end()
            elif key.lower() == 'p':
                self.on_song_prev()
            elif key == ' ':
                if self.player:
                    state = self.player.get_state()
                    if state in [vlc.State.Playing]:
                        self.player.pause()
                    elif state in [vlc.State.Paused]:
                        self.player.play()

    def move_focus(self, step):
        self.focus_index = (self.focus_index + step) % 3
        if self.focus_index == 0:
            self.main_columns.focus_position = 0
        else:
            self.main_columns.focus_position = 1
            self.right_panel.focus_position = self.focus_index - 1

    def move_playlist_focus(self, step):
        self.playlist_focus_index = (self.playlist_focus_index + step) % 2
        self.playlist_panel.focus_position = self.playlist_focus_index

    def trigger_selection(self):
        if self.mode == "music":
            listbox = self.focus_list[self.focus_index]
        elif self.mode == "radio":
            listbox = self.radio_listbox
        elif self.mode == "playlist":
            listbox = self.playlist_focus_list[self.playlist_focus_index]
        else:
            return

        focus_widget, _ = listbox.get_focus()
        if isinstance(focus_widget.base_widget, PlainButton):
            focus_widget.base_widget.keypress((0,), 'enter')

    def switch_to_radio_view(self):
        self.mode = "radio"
        self.main_layout.body = self.radio_panel

    def switch_to_music_view(self):
        self.mode = "music"
        self.main_layout.body = self.main_columns

    def switch_to_playlist_view(self):
        self.mode = "playlist"
        self.main_layout.body = self.playlist_panel

    def show_help_overlay(self):
        def exit_help():
            self.loop.widget = self.main_layout
        help_overlay = HelpOverlay(on_exit=exit_help)
        overlay = urwid.Overlay(help_overlay, self.main_layout, 'center', 40, 'middle', 20)
        self.loop.widget = overlay

    def show_volume_gauge(self):
        def exit_gauge():
            self.loop.widget = self.main_layout

        def on_change_volume(value):
            if hasattr(self, 'player') and self.player:
                self.player.audio_set_volume(value)

        if hasattr(self, 'player') and self.player:
            volume = self.player.audio_get_volume()
        else:
            volume = 50
        gauge = VolumeGauge(on_exit=exit_gauge, on_change=on_change_volume, initial=volume)
        overlay = urwid.Overlay(gauge, self.main_layout, 'center', 20, 'middle', 25)
        self.loop.widget = overlay

    def run(self):
        self.loop.run()


def setup_gettext(lang):
    lang_code = lang.split("_")[0]
    try:
        localedir = os.path.join(os.path.dirname(__file__), "locales")
        trans = gettext.translation("messages", localedir=localedir, languages=[lang_code])
        trans.install()
    except FileNotFoundError:
        gettext.install("messages")


@click.command()
@click.option('--server-url', help="URL of server")
@click.option('--username', help="Login of user")
@click.option('--password', hide_input=True, help="Password")
@click.option('--config-path', default=DEFAULT_CONFIG_PATH, help="Path to the configuration file")
@click.option('--lang', default=None, help="Lang")
@click.pass_context
def main(ctx, server_url, username, password, config_path, lang):
    lang = lang or locale.getlocale()[0] or "en_US"
    setup_gettext(lang)
    config = load_config(config_path)
    server_url = server_url or config.get("server_url")
    username = username or config.get("username")
    password = password or config.get("password")

    if not password or not username or not server_url:
        click.echo(ctx.get_help())
        ctx.exit(1)
    else:
        save_config(username, password, server_url, config_path, lang)

    nav = Navidrome(server_url, username, "nocp", password, "1.16.1")
    app = MusicBrowser(nav)
    app.run()


if __name__ == "__main__":
    main()
