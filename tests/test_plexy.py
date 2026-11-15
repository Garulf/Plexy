import asyncio
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import plexy
import pytest
from conftest import FakePlex
from plexapi.exceptions import BadRequest, Unauthorized
from requests.exceptions import ConnectionError

LIVING_ROOM = "11111111-1111-1111-1111-111111111111"
start_cast_browser = plexy.cast_browser


def run(results):
    async def collect():
        return [result.to_json() async for result in results]

    return asyncio.run(collect())


def titles(results):
    return [result["Title"] for result in results]


def test_search_keeps_plex_order_and_opens_plex_web(plex, thumbs):
    results = run(plexy.query("toy"))
    assert titles(results) == ["Toy Story", "Toy Story 2", "Toy Story Collection"]
    assert [result["Score"] for result in results] == [3, 2, 1]
    first = results[0]
    assert first["SubTitle"] == "Cowboy doll Woody's place as Andy's favourite toy is threatened by Buzz Lightyear."
    assert first["ContextData"] == [101]
    assert first["JsonRPCAction"]["Method"] == "Flow.Launcher.OpenUrl"
    assert first["JsonRPCAction"]["Parameters"][0] == (
        f"{plex._baseurl}/web/index.html#!/server/a1b2c3d4/details?key=%2Flibrary%2Fmetadata%2F101"
    )


def test_search_skips_tags_and_does_not_refetch_items(plex, thumbs):
    results = plexy.find_media(plex, "  Toy ")
    assert plex.queries == ["toy"]
    assert plex.genre not in results
    assert all(item._autoReload is False for item in results)


def test_empty_query_lists_on_deck(plex, thumbs):
    assert titles(run(plexy.query(""))) == ["The Vanishing of Will Byers", "Toy Story 2"]


@pytest.mark.parametrize("query", ["movies: toy", "Movies:toy", "m o v i e s : toy"])
def test_library_prefix_searches_one_library(plex, thumbs, query):
    assert titles(run(plexy.query(query))) == ["Toy Story", "Toy Story 2"]
    assert plex.queries == []
    assert plex.sections_[0].queries == ["toy"]


def test_library_prefix_ignores_spaces_in_library_names(plex, thumbs):
    assert titles(run(plexy.query("tvshows: will"))) == ["The Vanishing of Will Byers"]


def test_unknown_library_prefix_searches_everything(plex, thumbs):
    assert titles(run(plexy.query("cartoons: toy"))) == ["No Results Found!"]
    assert plex.queries == ["cartoons: toy"]


def test_bad_search_shows_no_results(plex, thumbs):
    plex.search_error = BadRequest("(400) bad_request")
    assert titles(run(plexy.query("toy"))) == ["No Results Found!"]


@pytest.mark.parametrize("error", [ConnectionError("refused"), Unauthorized("(401) unauthorized")])
def test_connection_error_opens_settings(plex, monkeypatch, error):
    def fail(baseurl, token):
        raise error

    monkeypatch.setattr(plexy, "_connect", fail)
    (result,) = run(plexy.query("toy"))
    assert result["Title"] == "Error: Unable to connect to Plex server."
    assert result["JsonRPCAction"]["Method"] == "Flow.Launcher.OpenSettingDialog"


def test_default_server_url_when_unset(plex, monkeypatch):
    seen = []
    monkeypatch.setattr(plexy, "_connect", lambda baseurl, token: seen.append((baseurl, token)))
    monkeypatch.setattr(plexy.plugin.launcher, "_settings", {})
    plexy.server()
    assert seen == [("http://localhost:32400", "")]


def test_thumbnails_and_posters_are_downloaded_once(plex, thumbs, tmp_path):
    results = run(plexy.query("toy story"))
    assert results[0]["IcoPath"] == str(tmp_path / "101.jpg")
    assert results[0]["Preview"]["PreviewImagePath"] == str(tmp_path / "101-poster.jpg")
    assert results[0]["Preview"]["IsMedia"] is True
    assert f"{plex._baseurl}/photo/:/transcode?url=/library/metadata/101/thumb/1&width=400&height=600" in thumbs
    count = len(thumbs)
    run(plexy.query("toy story"))
    assert len(thumbs) == count


def test_items_without_artwork_fall_back_to_the_plugin_icon(plex, thumbs):
    (result,) = run(plexy.query("cars"))
    assert result["IcoPath"] == plexy.ICON
    assert result["Preview"]["PreviewImagePath"] is None
    assert result["Preview"]["IsMedia"] is False


def test_episode_artwork_uses_the_show_poster(plex, thumbs):
    plexy.download_image(plex, plex.episode, "301.jpg", 100, 100)
    assert thumbs == [f"{plex._baseurl}/photo/:/transcode?url=/library/metadata/300/thumb/1&width=100&height=100"]


def test_failed_download_has_no_image(plex, thumbs, monkeypatch):
    def fail(*args, **kwargs):
        raise ConnectionError("timed out")

    monkeypatch.setattr(plexy, "download", fail)
    assert plexy.download_image(plex, plex.movies[0], "101.jpg", 100, 100) is None


def test_describe(plex):
    movie, _, cars = plex.movies
    assert plexy.describe(movie) == (
        "1995 · 1h 21m · G\n\nCowboy doll Woody's place as Andy's favourite toy"
        "     is threatened by Buzz Lightyear."
    )
    assert plexy.describe(cars) == "2006 · 1h 57m · G"
    assert plexy.describe(plex.episode).startswith("Stranger Things S01E01 · 2016 · 49m · TV-14\n\n")
    assert plexy.describe(plex.track) == "Randy Newman · 2m"


@pytest.mark.parametrize("model, subtitle", [
    (None, "Chromecast"),
    ("Chromecast Ultra", "Chromecast Ultra"),
    ("Google TV Streamer", "Chromecast · Google TV Streamer"),
])
def test_cast_subtitle(model, subtitle):
    assert plexy.cast_subtitle(model) == subtitle


def test_video_devices_are_the_ones_with_a_screen(browser):
    devices = asyncio.run(plexy.cast_devices(video=True))
    assert [device.friendly_name for device in devices] == ["Bedroom TV", "Living Room TV"]


def test_music_can_go_to_every_device(browser):
    devices = asyncio.run(plexy.cast_devices(video=False))
    assert [device.friendly_name for device in devices] == ["Bedroom TV", "Kitchen speaker", "Living Room TV", "Whole house"]


def test_no_devices_when_discovery_is_unavailable():
    assert asyncio.run(plexy.cast_devices(video=True)) == []


def test_discovery_starts_once_and_is_reused(monkeypatch):
    import pychromecast.discovery
    import zeroconf

    started = []

    class FakeBrowser:
        def __init__(self, listener, zc):
            self.zc = zc

        def start_discovery(self):
            started.append(self)

    monkeypatch.setattr(plexy, "_cast_browser", None)
    monkeypatch.setattr(zeroconf, "Zeroconf", object)
    monkeypatch.setattr(pychromecast.discovery, "CastBrowser", FakeBrowser)
    assert start_cast_browser() is start_cast_browser()
    assert len(started) == 1


def test_discovery_failure_is_logged_not_raised(monkeypatch):
    import pychromecast.discovery
    import zeroconf

    def fail(*args):
        raise OSError("address in use")

    monkeypatch.setattr(plexy, "_cast_browser", None)
    monkeypatch.setattr(zeroconf, "Zeroconf", object)
    monkeypatch.setattr(pychromecast.discovery, "CastBrowser", fail)
    assert start_cast_browser() is None


def test_context_menu_for_a_movie(plex, browser):
    menu = run(plexy.context_menu([101]))
    assert titles(menu) == ["SHIELD Android TV", "Bedroom TV", "Living Room TV", "Mark Watched"]
    shield, _, living_room, watched = menu
    assert shield["SubTitle"] == "Plex for Android (TV)"
    assert shield["JsonRPCAction"]["Method"] == "play"
    assert shield["JsonRPCAction"]["Parameters"] == ["SHIELD Android TV", 101, "Toy Story"]
    assert living_room["SubTitle"] == "Chromecast · Google TV Streamer"
    assert living_room["IcoPath"] == plexy.CAST_ICON
    assert living_room["JsonRPCAction"]["Parameters"] == [LIVING_ROOM, 101, "Toy Story"]
    assert watched["JsonRPCAction"] == {"Method": "mark_watched", "Parameters": [101], "DontHideAfterAction": False}


def test_context_menu_for_watched_music(plex, browser):
    plex.track.viewCount = 3
    menu = run(plexy.context_menu([401]))
    assert titles(menu) == ["SHIELD Android TV", "Bedroom TV", "Kitchen speaker", "Living Room TV", "Whole house", "Mark Unwatched"]
    assert menu[-1]["JsonRPCAction"]["Method"] == "mark_unwatched"


def test_mark_watched_and_unwatched(plex):
    asyncio.run(plexy.mark_watched(101))
    asyncio.run(plexy.mark_unwatched(102))
    assert plex.marked == [("played", 101), ("unplayed", 102)]


async def finish_background_tasks():
    await asyncio.gather(*plexy._background_tasks)


def test_play_on_a_plex_client_resumes(plex, messages, monkeypatch):
    queues = []
    monkeypatch.setattr(plexy.PlayQueue, "create", lambda server, media, continuous: queues.append(media) or "queue")

    async def play():
        await plexy.play("SHIELD Android TV", 102, "Toy Story 2")
        await finish_background_tasks()

    asyncio.run(play())
    assert [media.title for media in queues] == ["Toy Story 2"]
    assert plex.clients_[0].played == [("queue", 65000)]
    assert messages == [["Casting to SHIELD Android TV", "Toy Story 2", plexy.ICON]]


class FakeChromecast:
    def __init__(self):
        self.handlers = []
        self.disconnected = False

    def wait(self, timeout):
        pass

    def register_handler(self, handler):
        self.handlers.append(handler)

    def disconnect(self, timeout):
        self.disconnected = True


class FakePlexController:
    played = []

    def block_until_playing(self, media, timeout, offset):
        self.played.append((media.title, media._server._baseurl, offset))


@pytest.fixture
def chromecast(monkeypatch):
    import pychromecast
    import pychromecast.controllers.plex

    device = FakeChromecast()
    FakePlexController.played = []
    monkeypatch.setattr(pychromecast, "get_chromecast_from_cast_info", lambda info, zc: device)
    monkeypatch.setattr(pychromecast.controllers.plex, "PlexController", FakePlexController)
    return device


def cast(uuid, key, title):
    async def go():
        await plexy.cast(uuid, key, title)
        await finish_background_tasks()

    asyncio.run(go())


def test_cast_to_a_chromecast_resumes_and_disconnects(plex, browser, chromecast, messages):
    cast(LIVING_ROOM, 102, "Toy Story 2")
    assert FakePlexController.played == [("Toy Story 2", plex._baseurl, 65)]
    assert chromecast.disconnected
    assert messages == [["Casting to Living Room TV", "Toy Story 2", plexy.ICON]]


def test_cast_failure_is_reported(plex, browser, chromecast, messages):
    def fail(self, media, timeout, offset):
        raise TimeoutError()

    FakePlexController.block_until_playing = fail
    try:
        cast(LIVING_ROOM, 101, "Toy Story")
    finally:
        del FakePlexController.block_until_playing
    assert chromecast.disconnected
    assert messages == [["Couldn't cast to Living Room TV", "TimeoutError", plexy.ICON]]


def test_cast_to_a_device_that_left_the_network(plex, browser, messages):
    cast("99999999-9999-9999-9999-999999999999", 101, "Toy Story")
    assert messages == [["Couldn't cast to Chromecast", "The Chromecast is no longer on the network.", plexy.ICON]]


@pytest.mark.parametrize("baseurl", ["http://localhost:32400", "http://127.0.0.1:32400"])
def test_chromecast_gets_a_reachable_server_url(plex, monkeypatch, baseurl):
    local = FakePlex(baseurl)
    monkeypatch.setattr(plexy, "server", lambda: local)

    class FakeSocket:
        def __init__(self, family, kind):
            assert (family, kind) == (socket.AF_INET, socket.SOCK_DGRAM)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def connect(self, address):
            assert address == ("192.168.1.31", plexy.CAST_PORT)

        def getsockname(self):
            return ("192.168.1.10", 50000)

    monkeypatch.setattr(plexy.socket, "socket", FakeSocket)
    reachable = plexy.server_reachable_from("192.168.1.31")
    assert reachable._baseurl == "http://192.168.1.10:32400"
    assert reachable._token == local._token


def test_lan_server_url_is_used_as_is(plex):
    assert plexy.server_reachable_from("192.168.1.31") is plex


def test_plugin_methods_are_registered():
    names = set(plexy.plugin._event_handler._events)
    assert {"query", "context_menu", "play", "cast", "mark_watched", "mark_unwatched"} <= names


@pytest.mark.parametrize("data", [None, []])
def test_context_menu_of_results_without_media_is_empty(plex, data):
    assert run(plexy.context_menu(data)) == []


class FakeWebServer(BaseHTTPRequestHandler):
    status = 200
    body = b""

    def do_GET(self):
        self.send_response(self.status)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args):
        pass


@pytest.fixture
def web_server():
    httpd = HTTPServer(("127.0.0.1", 0), FakeWebServer)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()


@pytest.mark.parametrize("status, body", [
    (404, b"Not Found"),
    (502, b"Bad Gateway"),
    (200, b"<html><body><p>Sign in to QuickConnect<br></body></html>"),
])
def test_url_that_is_not_a_plex_server_opens_settings(web_server, monkeypatch, status, body):
    monkeypatch.setattr(FakeWebServer, "status", status)
    monkeypatch.setattr(FakeWebServer, "body", body)
    monkeypatch.setattr(plexy.plugin.launcher, "_settings", {"baseurl": web_server, "token": "fake-token"})
    (result,) = run(plexy.query("toy"))
    assert result["Title"] == "Error: Unable to connect to Plex server."
    assert result["JsonRPCAction"]["Method"] == "Flow.Launcher.OpenSettingDialog"


def test_changed_settings_apply_to_the_next_query(monkeypatch):
    from pyflowlauncher.jsonrpc import JsonRPCV2Client
    from pyflowlauncher.launcher import FlowLauncherV2

    requests = [
        {"id": 1, "method": "query", "params": [{"search": "toy"}, {"baseurl": "http://localhost:32400", "token": "old"}]},
        {"id": 2, "method": "query", "params": [{"search": "toy"}, {"baseurl": "https://plex.example.com", "token": "new"}]},
        {"id": 3, "method": "close", "params": []},
    ]

    connected = threading.Semaphore(0)

    async def messages(self):
        for request in requests:
            yield request
            if request["method"] == "query":
                await asyncio.to_thread(connected.acquire, timeout=5)

    monkeypatch.setattr(JsonRPCV2Client, "messages", messages)
    launcher = FlowLauncherV2()
    launcher._client.send = lambda message: None
    monkeypatch.setattr(plexy.plugin, "_launcher", launcher)
    connections = []

    def connect(baseurl, token):
        connections.append((baseurl, token))
        connected.release()
        raise ConnectionError("refused")

    monkeypatch.setattr(plexy, "_connect", connect)
    plexy.plugin.run()
    assert connections == [("http://localhost:32400", "old"), ("https://plex.example.com", "new")]


def test_items_without_a_summary(plex, thumbs):
    plex.track.summary = None
    (result,) = run(plexy.query("friend"))
    assert result["SubTitle"] == ""
    assert result["Preview"]["Description"] == "Randy Newman · 2m"
