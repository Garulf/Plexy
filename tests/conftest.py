from types import SimpleNamespace
from uuid import UUID
from xml.etree import ElementTree

import pytest
from plexapi.audio import Track
from plexapi.collection import Collection
from plexapi.media import Genre
from plexapi.server import PlexServer
from plexapi.video import Episode, Movie

import plexy

BASEURL = "http://192.168.1.20:32400"
TOKEN = "fake-token"

MOVIES = """
<Video ratingKey="101" key="/library/metadata/101" type="movie" title="Toy Story" year="1995"
    duration="4860000" contentRating="G" thumb="/library/metadata/101/thumb/1"
    summary="Cowboy doll Woody's place as Andy's favourite toy
    is threatened by Buzz Lightyear." />
<Video ratingKey="102" key="/library/metadata/102" type="movie" title="Toy Story 2" year="1999"
    duration="5520000" contentRating="G" viewCount="1" viewOffset="65000"
    thumb="/library/metadata/102/thumb/1" summary="Woody is snatched by a toy collector." />
<Video ratingKey="201" key="/library/metadata/201" type="movie" title="Cars" year="2006"
    duration="7020000" contentRating="G" summary="" />
"""
EPISODE = """
<Video ratingKey="301" key="/library/metadata/301" type="episode" title="The Vanishing of Will Byers"
    grandparentTitle="Stranger Things" parentIndex="1" index="1" year="2016" duration="2940000"
    contentRating="TV-14" grandparentThumb="/library/metadata/300/thumb/1"
    thumb="/library/metadata/301/thumb/1" summary="A boy disappears." />
"""
TRACK = """
<Track ratingKey="401" key="/library/metadata/401" type="track" title="You've Got a Friend in Me"
    grandparentTitle="Randy Newman" parentTitle="Toy Story" duration="124000" summary="" />
"""
COLLECTION = """
<Directory ratingKey="501" key="/library/collections/501/children" type="collection"
    title="Toy Story Collection" subtype="movie" summary="Pixar's films about the secret life of toys." />
"""
GENRE = '<Genre id="1" tag="Animation" filter="genre=1" />'


def parse(cls, server, xml, parent=None):
    return cls(server, ElementTree.fromstring(xml.strip()), parent=parent)


def parse_all(cls, server, xml):
    return [cls(server, element) for element in ElementTree.fromstring(f"<root>{xml}</root>")]


class FakeSection:
    def __init__(self, title, items):
        self.title = title
        self.items = items
        self.queries = []

    def search(self, query):
        self.queries.append(query)
        return [item for item in self.items if query in item.title.lower()]


class FakeClient:
    def __init__(self, title, product):
        self.title = title
        self.product = product
        self.played = []

    def playMedia(self, media, offset=0):
        self.played.append((media, offset))


class FakePlex(PlexServer):
    """A PlexServer with canned library contents instead of HTTP."""

    def __init__(self, baseurl=BASEURL, token=TOKEN):
        self._baseurl = baseurl
        self._token = token
        self.machineIdentifier = "a1b2c3d4"
        self.queries = []
        self.search_error = None
        self.marked = []
        self.movies = parse_all(Movie, self, MOVIES)
        self.episode = parse(Episode, self, EPISODE)
        self.track = parse(Track, self, TRACK)
        self.collection = parse(Collection, self, COLLECTION)
        self.genre = parse(Genre, self, GENRE, parent=self.movies[0])
        self.sections_ = [
            FakeSection("Movies", self.movies),
            FakeSection("TV Shows", [self.episode]),
            FakeSection("Music", [self.track]),
        ]
        self.clients_ = [FakeClient("SHIELD Android TV", "Plex for Android (TV)")]
        self.library_ = SimpleNamespace(sections=lambda: self.sections_, onDeck=lambda: [self.episode, self.movies[1]])

    @property
    def library(self):
        return self.library_

    def items(self):
        return [*self.movies, self.episode, self.track, self.collection]

    def search(self, query):
        self.queries.append(query)
        if self.search_error:
            raise self.search_error
        matches = [item for item in self.items() if query in item.title.lower()]
        return [self.genre, *matches]

    def fetchItem(self, ekey):
        for item in self.items():
            if item.ratingKey == int(ekey):
                item._autoReload = False
                item.markPlayed = lambda item=item: self.marked.append(("played", item.ratingKey))
                item.markUnplayed = lambda item=item: self.marked.append(("unplayed", item.ratingKey))
                return item
        raise LookupError(ekey)

    def clients(self):
        return self.clients_

    def client(self, name):
        return next(client for client in self.clients_ if client.title == name)

    def transcodeImage(self, imageUrl, height, width, **kwargs):
        return f"{self._baseurl}/photo/:/transcode?url={imageUrl}&width={width}&height={height}"


class FakeServiceInfo:
    """Stands in for zeroconf.ServiceInfo, answering from a canned mDNS cache."""

    cache = {}

    def __init__(self, type_, name):
        self.name = name
        self.properties = {}

    def load_from_cache(self, zc):
        if self.name not in self.cache:
            return False
        self.properties = self.cache[self.name]
        return True


def cast_info(name, model, uuid, cast_type="cast", capabilities=None, host="192.168.1.31"):
    from pychromecast.models import CastInfo, MDNSServiceInfo

    service = f"{name.replace(' ', '-')}._googlecast._tcp.local."
    if capabilities is not None:
        FakeServiceInfo.cache[service] = {b"ca": str(capabilities).encode()}
    return CastInfo(
        services={MDNSServiceInfo(service)},
        uuid=UUID(uuid),
        model_name=model,
        friendly_name=name,
        host=host,
        port=8009,
        cast_type=cast_type,
        manufacturer="Google Inc.",
    )


class FakeCastBrowser:
    def __init__(self, devices):
        self.devices = {device.uuid: device for device in devices}
        self.zc = object()


@pytest.fixture(autouse=True)
def no_discovery(monkeypatch):
    monkeypatch.setattr(plexy, "cast_browser", lambda: None)


@pytest.fixture
def plex(monkeypatch):
    fake = FakePlex()
    connections = {}

    def connect(baseurl, token):
        if baseurl == fake._baseurl:
            return fake
        return connections.setdefault(baseurl, FakePlex(baseurl, token))

    monkeypatch.setattr(plexy, "_connect", connect)
    monkeypatch.setattr(plexy.plugin.launcher, "_settings", {"baseurl": fake._baseurl, "token": TOKEN})
    fake.connections = connections
    return fake


@pytest.fixture
def thumbs(tmp_path, monkeypatch):
    downloads = []

    def download(url, token, filename, savepath):
        downloads.append(url)
        (tmp_path / filename).write_bytes(b"jpeg")

    monkeypatch.setattr(plexy, "THUMB_DIR", tmp_path)
    monkeypatch.setattr(plexy, "download", download)
    return downloads


@pytest.fixture
def devices():
    FakeServiceInfo.cache.clear()
    return [
        cast_info("Living Room TV", "Google TV Streamer", "11111111-1111-1111-1111-111111111111", capabilities=5),
        cast_info("Kitchen speaker", "Google Nest Mini", "22222222-2222-2222-2222-222222222222", cast_type="audio", capabilities=4),
        cast_info("Bedroom TV", "Chromecast Ultra", "33333333-3333-3333-3333-333333333333"),
        cast_info("Whole house", "Google Cast Group", "44444444-4444-4444-4444-444444444444", cast_type="group"),
    ]


@pytest.fixture
def browser(devices, monkeypatch):
    import zeroconf

    fake = FakeCastBrowser(devices)
    monkeypatch.setattr(plexy, "cast_browser", lambda: fake)
    monkeypatch.setattr(zeroconf, "ServiceInfo", FakeServiceInfo)
    return fake


@pytest.fixture
def messages(monkeypatch):
    sent = []

    async def invoke(command):
        sent.append(command["Parameters"])

    monkeypatch.setattr(plexy.plugin.launcher.api, "invoke", invoke)
    return sent

