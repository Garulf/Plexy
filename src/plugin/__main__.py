import asyncio
import tempfile
from functools import lru_cache, wraps
from pathlib import Path

from plexapi.base import PlexPartialObject
from plexapi.exceptions import BadRequest, Unauthorized
from plexapi.playqueue import PlayQueue
from plexapi.server import PlexServer
from plexapi.utils import download
from pyflowlauncher import Plugin, Result
from requests.exceptions import RequestException

plugin = Plugin()

ICON = str(Path(__file__).resolve().parent.parent / "icon.png")
THUMB_DIR = Path(tempfile.gettempdir()) / "Plexy"
DEFAULT_BASEURL = "http://localhost:32400"
TIMEOUT = 30


def threaded(func):
    """Run a blocking plexapi call off the event loop so queries stay cancellable."""
    @wraps(func)
    async def wrapper(*args):
        return await asyncio.to_thread(func, *args)
    return wrapper


@lru_cache(maxsize=1)
def _connect(baseurl: str, token: str) -> PlexServer:
    return PlexServer(baseurl, token, timeout=TIMEOUT)


def server() -> PlexServer:
    baseurl = plugin.settings.get("baseurl") or DEFAULT_BASEURL
    token = plugin.settings.get("token") or ""
    return _connect(baseurl, token)


def find_media(plex: PlexServer, query: str) -> list:
    query = query.strip().lower()
    if not query:
        return plex.library.onDeck()
    searchable = plex
    # "<library name>: <term>" restricts the search to one library, ignoring whitespace
    prefix, sep, term = query.partition(":")
    if sep:
        for section in plex.library.sections():
            if section.title.replace(" ", "").lower() == prefix.replace(" ", ""):
                searchable, query = section, term.strip()
                break
    try:
        items = searchable.search(query)
    except BadRequest:
        return []
    # hub search also returns tags (actors, genres, ...) which aren't openable media
    return [item for item in items if isinstance(item, PlexPartialObject)]


def download_thumb(plex: PlexServer, item) -> str:
    path = THUMB_DIR / f"{item.ratingKey}.jpg"
    if path.exists():
        return str(path)
    thumb = item.grandparentThumb if item.type == "episode" else getattr(item, "thumb", None)
    if not thumb:
        return ICON
    try:
        download(
            plex.transcodeImage(thumb, 100, 100),
            plex._token,
            filename=path.name,
            savepath=str(THUMB_DIR),
        )
    except (RequestException, OSError):
        return ICON
    return str(path)


@plugin.on_method
async def query(query: str):
    try:
        plex = await asyncio.to_thread(server)
        items = await asyncio.to_thread(find_media, plex, query)
    except (RequestException, Unauthorized):
        yield Result(
            title="Error: Unable to connect to Plex server.",
            subtitle="Please check your settings.",
            icon=ICON,
        ).add_action(plugin.launcher.api.open_setting_dialog())
        return
    if not items:
        yield Result(title="No Results Found!", icon=ICON)
        return
    thumbs = await asyncio.gather(
        *(asyncio.to_thread(download_thumb, plex, item) for item in items)
    )
    for index, (item, thumb) in enumerate(zip(items, thumbs)):
        yield Result(
            title=item.title,
            subtitle=" ".join(getattr(item, "summary", "").split()),
            icon=thumb,
            # keep Plex's relevance order
            score=len(items) - index,
            context_data=[item.ratingKey],
        ).add_action(
            plugin.launcher.api.open_url(item.getWebURL(base=f"{plex._baseurl}/web/index.html"))
        )


@plugin.on_method
async def context_menu(data: list):
    key = data[0]
    plex = await asyncio.to_thread(server)
    clients, media = await asyncio.gather(
        asyncio.to_thread(plex.clients),
        asyncio.to_thread(plex.fetchItem, key),
    )
    for client in clients:
        yield Result(
            title=client.title,
            subtitle=client.product,
            icon=ICON,
        ).add_action(play, [client.title, key])
    watched = getattr(media, "isPlayed", None)
    if watched is True:
        yield Result(title="Mark Unwatched", icon=ICON).add_action(mark_unwatched, [key])
    elif watched is False:
        yield Result(title="Mark Watched", icon=ICON).add_action(mark_watched, [key])


@plugin.on_method
@threaded
def play(client_name: str, key: int):
    plex = server()
    client = plex.client(client_name)
    media = plex.fetchItem(key)
    queue = PlayQueue.create(plex, media, continuous=True)
    client.playMedia(queue, offset=getattr(media, "viewOffset", 0) or 0)


@plugin.on_method
@threaded
def mark_watched(key: int):
    server().fetchItem(key).markPlayed()


@plugin.on_method
@threaded
def mark_unwatched(key: int):
    server().fetchItem(key).markUnplayed()


plugin.run()
