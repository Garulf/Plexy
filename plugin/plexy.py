import os
import sys
import tempfile
import webbrowser
import urllib.parse

from flox import Flox, ICON_APP_ERROR

from plexapi.server import PlexServer
from plexapi.utils import download


class Plexy(Flox):

    def __init__(self):
        super().__init__()

    def _connect_plex(self):
        self._baseurl = self.settings.get('baseurl', None)
        self._token = self.settings.get('token', None)
        self._plex = PlexServer(self._baseurl, self._token, timeout=120)

    def query(self, query):
        q = query.lower()
        if not self.settings.get('baseurl', None):
            self.add_item(
                title=f'{query}',
                subtitle='Please enter your Plex server\'s URL (e.g. http://127.0.0.1:32400).',
                method='set_setting',
                parameters=['baseurl', query],
                hide=True
            )
        elif not self.settings.get('token', None):
            self.add_item(
                title=f'{query}',
                subtitle='Please enter your Plex server token above.',
                method='set_setting',
                parameters=['token', query],
                hide=True
            )
        else:
            self._connect_plex()
            sections = self._plex.library.sections()
            for section in sections:
                # ignore whitespace for section names
                if q.replace(' ', '').startswith(f"{section.title.replace(' ', '').lower()}:"):
                    # remove section filter from query
                    q = q.split(':')[1]
                    search_section = section
                    break
            else:
                search_section = self._plex
            for item in search_section.search(q):
                if item.type != 'tag':
                    try:
                        icon = self.download_thumb(item)
                        title = f"{item.title} - {item.year}"
                        self.add_item(
                            title=title,
                            subtitle=item.summary.replace('\r', ' ').replace('\n', ''),
                            icon=icon,
                            method='browser',
                            parameters=[self._plex._baseurl, self._plex.machineIdentifier, item.key],
                            context=[item.ratingKey]
                        )
                    except AttributeError:
                        pass
        if len(self._results) == 0:
            self.add_item(
                title='No Results Found!',
                icon=ICON_APP_ERROR,
                context=''
            )

    def context_menu(self, data):
        key = data[0]
        self.add_item(
            title='Reset Login',
            subtitle='Reset all user login information...',
            method='reset_login'
        )
        self._connect_plex()
        for client in self._plex.clients():
            subtitle = 'Not Playing'
            if client.isPlayingMedia():
                subtitle = 'Playing'
            self.add_item(
                title=client.title,
                subtitle=subtitle,
                method='play',
                parameters=[client.title, key]
            )

    def set_setting(self, setting, q):
        self.settings[setting] = str(q)
        self.change_query(self.action_keyword + ' ', True)


    def reset_login(self):
        self.settings['token'] = None
        self.settings['baseurl'] = None

    def download_thumb(self, item):
        file_name = f"{item.ratingKey}.jpg"
        save_path = os.path.join(tempfile.gettempdir(), self.id)
        full_path = os.path.join(save_path, file_name)
        if not os.path.exists(full_path):
            thumb = item.thumb or item.grandparentThumb
            if item.type == 'episode':
                thumb = item.grandparentThumb
            thumb_url = self._plex.transcodeImage(thumb, 100, 100)

            download(
                thumb_url, 
                self.settings['token'],
                filename=file_name,
                savepath=save_path
            )
        return full_path

    def play(self, client, key):
        self._connect_plex()
        client = self._plex.client(client)
        media = self._plex.fetchItem(key)
        offset = media.viewOffset or 0
        client.playMedia(media, offset=offset)


    def browser(self, baseurl, machine, key):
        key = key.replace('/', '%2F')
        url = f"{baseurl}/web/index.html#!/server/{machine}/details?key={key}"
        webbrowser.open(url)


if __name__ == '__main__':
    Plexy()