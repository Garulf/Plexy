import os
import sys
import tempfile
import webbrowser
import urllib.parse

from flox import Flox, ICON_APP_ERROR

from plexapi.server import PlexServer
from plexapi.utils import download
from plexapi.exceptions import BadRequest


class Plexy(Flox):

    def _connect_plex(self):
        self._baseurl = self.settings.get("baseurl", "https://localhost:32400")
        self._token = self.settings.get("token", "")
        self._plex = PlexServer(self._baseurl, self._token, timeout=120)

    def query(self, query):
        self._connect_plex()
        q = query.lower()
        if q == '':
            self.on_deck()
            return

        sections = self._plex.library.sections()
        for section in sections:
            # ignore whitespace for section names
            if q.replace(" ", "").startswith(
                f"{section.title.replace(' ', '').lower()}:"
            ):
                # remove section filter from query
                q = q.split(":")[1]
                search_section = section
                break
        else:
            search_section = self._plex
        try:
            self.search(search_section, q)
        except BadRequest:
            pass
        if len(self._results) == 0:
            self.add_item(title="No Results Found!", icon=ICON_APP_ERROR, context="")

    def context_menu(self, data):
        key = data[0]
        self._connect_plex()
        for client in self._plex.clients():
            self.client_item(client, key)

    def media_item(self, media):
        self.add_item(
            title=media.title,
            subtitle=media.summary.replace("\r", " ").replace("\n", ""),
            icon=self.download_thumb(media),
            method="browser",
            parameters=[self._plex._baseurl, self._plex.machineIdentifier, media.key],
            context=[media.ratingKey],
        )

    def client_item(self, client, key):
        subtitle = "Not Playing"
        if client.isPlayingMedia():
            subtitle = "Playing"
        self.add_item(
            title=client.title,
            subtitle=subtitle,
            icon=self.icon,
            method="play",
            parameters=[client.title, key],
        )

    def search(self, section, query):
        for item in section.search(query):
            if item.type != "tag":
                try:
                    self.media_item(item)
                except AttributeError:
                    pass

    def on_deck(self):
        for item in self._plex.library.onDeck():
            self.media_item(item)

    def set_setting(self, setting, q):
        self.settings[setting] = str(q)
        self.change_query(self.action_keyword + " ", True)

    def reset_login(self):
        self.settings["token"] = None
        self.settings["baseurl"] = None

    def download_thumb(self, item):
        file_name = f"{item.ratingKey}.jpg"
        save_path = os.path.join(tempfile.gettempdir(), self.id)
        full_path = os.path.join(save_path, file_name)
        if not os.path.exists(full_path):
            thumb = item.thumb or item.grandparentThumb
            if item.type == "episode":
                thumb = item.grandparentThumb
            thumb_url = self._plex.transcodeImage(thumb, 100, 100)

            download(
                thumb_url,
                self.settings["token"],
                filename=file_name,
                savepath=save_path,
            )
        return full_path

    def play(self, client, key):
        self._connect_plex()
        client = self._plex.client(client)
        media = self._plex.fetchItem(key)
        offset = media.viewOffset or 0
        client.playMedia(media, offset=offset)

    def mark_watched(self, key):
        self._connect_plex()
        media = self._plex.fetchItem(key)
        media.markWatched()

    def browser(self, baseurl, machine, key):
        key = key.replace("/", "%2F")
        url = f"{baseurl}/web/index.html#!/server/{machine}/details?key={key}"
        webbrowser.open(url)


if __name__ == "__main__":
    Plexy()
