import asyncio
import ipaddress
import socket
import tempfile
import threading
from functools import lru_cache, wraps
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from plexapi.base import PlexPartialObject
from plexapi.exceptions import BadRequest, Unauthorized
from plexapi.playqueue import PlayQueue
from plexapi.server import PlexServer
from plexapi.utils import download
from pyflowlauncher import Plugin, Result
from pyflowlauncher.models.result import PreviewInfo
from requests.exceptions import RequestException

plugin = Plugin()

ICON = str(Path(__file__).resolve().parent.parent / "icon.png")
CAST_ICON = str(Path(__file__).resolve().parent.parent / "cast.png")
THUMB_DIR = Path(tempfile.gettempdir()) / "Plexy"
DEFAULT_BASEURL = "http://localhost:32400"
TIMEOUT = 30
CAST_DISCOVERY_WAIT = 3
CAST_TIMEOUT = 10
CAST_PORT = 8009
# "ca" capability bit a cast device advertises over mDNS when it has a screen
CAST_VIDEO_OUT = 1


def threaded(func):
    """Run a blocking plexapi call off the event loop so queries stay cancellable."""
    @wraps(func)
    async def wrapper(*args):
        return await asyncio.to_thread(func, *args)
    return wrapper


@lru_cache(maxsize=2)
def _connect(baseurl: str, token: str) -> PlexServer:
    return PlexServer(baseurl, token, timeout=TIMEOUT)


def server() -> PlexServer:
    baseurl = plugin.settings.get("baseurl") or DEFAULT_BASEURL
    token = plugin.settings.get("token") or ""
    return _connect(baseurl, token)


_cast_browser = None
_cast_browser_lock = threading.Lock()


def cast_browser():
    """Browse for Chromecasts in the background; found devices accumulate in browser.devices."""
    global _cast_browser
    with _cast_browser_lock:
        if _cast_browser is None:
            try:
                from pychromecast.discovery import CastBrowser, SimpleCastListener
                from zeroconf import Zeroconf

                browser = CastBrowser(SimpleCastListener(), Zeroconf())
                browser.start_discovery()
                _cast_browser = browser
            except Exception:  # casting is optional, e.g. the mDNS port may be unavailable
                plugin.logger.exception("Chromecast discovery failed")
        return _cast_browser


def supports_video(device, zc) -> bool:
    from pychromecast.const import CAST_TYPE_CHROMECAST
    from pychromecast.models import MDNSServiceInfo
    from zeroconf import ServiceInfo

    for service in device.services:
        if isinstance(service, MDNSServiceInfo):
            info = ServiceInfo("_googlecast._tcp.local.", service.name)
            capabilities = info.properties.get(b"ca") if info.load_from_cache(zc) else None
            if capabilities and capabilities.isdigit():
                return bool(int(capabilities) & CAST_VIDEO_OUT)
    # pychromecast only knows the type of models in its table; don't hide devices it doesn't
    return device.cast_type in (CAST_TYPE_CHROMECAST, None)


def cast_subtitle(model) -> str:
    if not model:
        return "Chromecast"
    # avoid "Chromecast · Chromecast Ultra"
    return model if "chromecast" in model.lower() else f"Chromecast · {model}"


async def cast_devices(video: bool) -> list:
    browser = await asyncio.to_thread(cast_browser)
    if browser is None:
        return []
    # discovery starts on the first query, so give it a moment if nothing has answered yet
    for _ in range(CAST_DISCOVERY_WAIT * 10):
        if browser.devices:
            break
        await asyncio.sleep(0.1)
    devices = list(browser.devices.values())
    if video:
        devices = [device for device in devices if supports_video(device, browser.zc)]
    return sorted(devices, key=lambda device: device.friendly_name or "")


def server_reachable_from(host: str) -> PlexServer:
    """The Chromecast streams from the server itself, so it can't use a localhost URL."""
    plex = server()
    url = urlparse(plex._baseurl)
    try:
        loopback = ipaddress.ip_address(url.hostname).is_loopback
    except ValueError:
        loopback = url.hostname == "localhost"
    if not loopback:
        return plex
    # the address this PC uses to reach the Chromecast is one the Chromecast can reach back
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect((host, CAST_PORT))
        address = sock.getsockname()[0]
    return _connect(f"{url.scheme}://{address}:{url.port or 32400}", plex._token)


def find_media(plex: PlexServer, query: str) -> list:
    items = _search(plex, query)
    for item in items:
        # search results already hold what we display; don't refetch each item for missing fields
        item._autoReload = False
    return items


def _search(plex: PlexServer, query: str) -> list:
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


def download_image(plex: PlexServer, item, name: str, width: int, height: int):
    path = THUMB_DIR / name
    if path.exists():
        return str(path)
    thumb = item.grandparentThumb if item.type == "episode" else getattr(item, "thumb", None)
    if not thumb:
        return None
    try:
        download(
            plex.transcodeImage(thumb, height, width),
            plex._token,
            filename=path.name,
            savepath=str(THUMB_DIR),
        )
    except (RequestException, OSError):
        return None
    return str(path)


def describe(item) -> str:
    """Details line plus summary for the preview panel, e.g. "2010 · 1h 43m · PG"."""
    details = []
    if item.type == "episode":
        details.append(f"{item.grandparentTitle} {item.seasonEpisode.upper()}")
    elif item.type in ("album", "track"):
        details.append(getattr(item, "grandparentTitle", None) or getattr(item, "parentTitle", None))
    details.append(getattr(item, "year", None))
    duration = getattr(item, "duration", None)
    if duration:
        hours, minutes = divmod(round(duration / 60000), 60)
        details.append(f"{hours}h {minutes}m" if hours else f"{minutes}m")
    details.append(getattr(item, "contentRating", None))
    line = " · ".join(str(detail) for detail in details if detail)
    summary = getattr(item, "summary", "").strip()
    return "\n\n".join(part for part in (line, summary) if part)


def preview(item, poster) -> PreviewInfo:
    return PreviewInfo(
        PreviewImagePath=poster,
        Description=describe(item),
        IsMedia=poster is not None,
        PreviewDeligate="",
    )


@plugin.on_method
async def query(query: str):
    asyncio.get_running_loop().run_in_executor(None, cast_browser)
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
    images = await asyncio.gather(*(
        asyncio.to_thread(download_image, plex, item, name, width, height)
        for item in items
        for name, width, height in (
            (f"{item.ratingKey}.jpg", 100, 100),
            (f"{item.ratingKey}-poster.jpg", 400, 600),
        )
    ))
    for index, item in enumerate(items):
        thumb, poster = images[2 * index:2 * index + 2]
        yield Result(
            title=item.title,
            subtitle=" ".join(getattr(item, "summary", "").split()),
            icon=thumb or ICON,
            preview=preview(item, poster),
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
    # speakers can take music, but anything else needs a screen
    media_type = getattr(media, "listType", None) or getattr(media, "playlistType", None)
    devices = await cast_devices(video=media_type != "audio")
    for client in clients:
        yield Result(
            title=client.title,
            subtitle=client.product,
            icon=ICON,
        ).add_action(play, [client.title, key, media.title])
    for device in devices:
        yield Result(
            title=device.friendly_name,
            subtitle=cast_subtitle(device.model_name),
            icon=CAST_ICON,
        ).add_action(cast, [str(device.uuid), key, media.title])
    watched = getattr(media, "isPlayed", None)
    if watched is True:
        yield Result(title="Mark Unwatched", icon=ICON).add_action(mark_unwatched, [key])
    elif watched is False:
        yield Result(title="Mark Watched", icon=ICON).add_action(mark_watched, [key])


_background_tasks = set()


def in_background(coro) -> None:
    """Answer the action straight away so Flow isn't left waiting on the cast."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def send_to(name: str, title: str, func, *args) -> None:
    try:
        await asyncio.to_thread(func, *args)
    except Exception as error:
        plugin.logger.exception("Casting to %s failed", name)
        message = (f"Couldn't cast to {name}", str(error) or type(error).__name__)
    else:
        message = (f"Casting to {name}", title)
    await plugin.launcher.api.invoke(plugin.launcher.api.show_msg(*message, ICON))


def _play(client_name: str, key: int):
    plex = server()
    client = plex.client(client_name)
    media = plex.fetchItem(key)
    queue = PlayQueue.create(plex, media, continuous=True)
    client.playMedia(queue, offset=getattr(media, "viewOffset", 0) or 0)


@plugin.on_method
async def play(client_name: str, key: int, title: str):
    in_background(send_to(client_name, title, _play, client_name, key))


def _cast(device, key: int):
    import pychromecast
    from pychromecast.controllers.plex import PlexController

    if device is None:
        raise LookupError("The Chromecast is no longer on the network.")
    media = server_reachable_from(device.host).fetchItem(key)
    chromecast = pychromecast.get_chromecast_from_cast_info(device, cast_browser().zc)
    try:
        chromecast.wait(timeout=CAST_TIMEOUT)
        controller = PlexController()
        chromecast.register_handler(controller)
        offset = (getattr(media, "viewOffset", 0) or 0) // 1000
        controller.block_until_playing(media, timeout=CAST_TIMEOUT, offset=offset)
    finally:
        # also stops the connection thread, which otherwise retries forever
        chromecast.disconnect(timeout=CAST_TIMEOUT)


@plugin.on_method
async def cast(uuid: str, key: int, title: str):
    device = cast_browser().devices.get(UUID(uuid))
    name = device.friendly_name if device else "Chromecast"
    in_background(send_to(name, title, _cast, device, key))


@plugin.on_method
@threaded
def mark_watched(key: int):
    server().fetchItem(key).markPlayed()


@plugin.on_method
@threaded
def mark_unwatched(key: int):
    server().fetchItem(key).markUnplayed()


plugin.run()
