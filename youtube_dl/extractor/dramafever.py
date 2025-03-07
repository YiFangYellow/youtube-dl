# encoding: utf-8
from __future__ import unicode_literals

import itertools

from .amp import AMPIE
from ..compat import (
    compat_HTTPError,
    compat_urllib_parse,
    compat_urlparse,
)
from ..utils import (
    ExtractorError,
    clean_html,
    sanitized_Request,
)


class DramaFeverBaseIE(AMPIE):
    _LOGIN_URL = 'https://www.dramafever.com/accounts/login/'
    _NETRC_MACHINE = 'dramafever'

    _CONSUMER_SECRET = 'DA59dtVXYLxajktV'

    _consumer_secret = None

    def _get_consumer_secret(self):
        mainjs = self._download_webpage(
            'http://www.dramafever.com/static/51afe95/df2014/scripts/main.js',
            None, 'Downloading main.js', fatal=False)
        if not mainjs:
            return self._CONSUMER_SECRET
        return self._search_regex(
            r"var\s+cs\s*=\s*'([^']+)'", mainjs,
            'consumer secret', default=self._CONSUMER_SECRET)

    def _real_initialize(self):
        self._login()
        self._consumer_secret = self._get_consumer_secret()

    def _login(self):
        (username, password) = self._get_login_info()
        if username is None:
            return

        login_form = {
            'username': username,
            'password': password,
        }

        request = sanitized_Request(
            self._LOGIN_URL, compat_urllib_parse.urlencode(login_form).encode('utf-8'))
        response = self._download_webpage(
            request, None, 'Logging in as %s' % username)

        if all(logout_pattern not in response
               for logout_pattern in ['href="/accounts/logout/"', '>Log out<']):
            error = self._html_search_regex(
                r'(?s)class="hidden-xs prompt"[^>]*>(.+?)<',
                response, 'error message', default=None)
            if error:
                raise ExtractorError('Unable to login: %s' % error, expected=True)
            raise ExtractorError('Unable to log in')


class DramaFeverIE(DramaFeverBaseIE):
    IE_NAME = 'dramafever'
    _VALID_URL = r'https?://(?:www\.)?dramafever\.com/drama/(?P<id>[0-9]+/[0-9]+)(?:/|$)'
    _TEST = {
        'url': 'http://www.dramafever.com/drama/4512/1/Cooking_with_Shin/',
        'info_dict': {
            'id': '4512.1',
            'ext': 'flv',
            'title': 'Cooking with Shin 4512.1',
            'description': 'md5:a8eec7942e1664a6896fcd5e1287bfd0',
            'thumbnail': 're:^https?://.*\.jpg',
            'timestamp': 1404336058,
            'upload_date': '20140702',
            'duration': 343,
        },
        'params': {
            # m3u8 download
            'skip_download': True,
        },
    }

    def _real_extract(self, url):
        video_id = self._match_id(url).replace('/', '.')

        try:
            info = self._extract_feed_info(
                'http://www.dramafever.com/amp/episode/feed.json?guid=%s' % video_id)
        except ExtractorError as e:
            if isinstance(e.cause, compat_HTTPError):
                raise ExtractorError(
                    'Currently unavailable in your country.', expected=True)
            raise

        series_id, episode_number = video_id.split('.')
        episode_info = self._download_json(
            # We only need a single episode info, so restricting page size to one episode
            # and dealing with page number as with episode number
            r'http://www.dramafever.com/api/4/episode/series/?cs=%s&series_id=%s&page_number=%s&page_size=1'
            % (self._consumer_secret, series_id, episode_number),
            video_id, 'Downloading episode info JSON', fatal=False)
        if episode_info:
            value = episode_info.get('value')
            if value:
                subfile = value[0].get('subfile') or value[0].get('new_subfile')
                if subfile and subfile != 'http://www.dramafever.com/st/':
                    info.setdefault('subtitles', {}).setdefault('English', []).append({
                        'ext': 'srt',
                        'url': subfile,
                    })

        return info


class DramaFeverSeriesIE(DramaFeverBaseIE):
    IE_NAME = 'dramafever:series'
    _VALID_URL = r'https?://(?:www\.)?dramafever\.com/drama/(?P<id>[0-9]+)(?:/(?:(?!\d+(?:/|$)).+)?)?$'
    _TESTS = [{
        'url': 'http://www.dramafever.com/drama/4512/Cooking_with_Shin/',
        'info_dict': {
            'id': '4512',
            'title': 'Cooking with Shin',
            'description': 'md5:84a3f26e3cdc3fb7f500211b3593b5c1',
        },
        'playlist_count': 4,
    }, {
        'url': 'http://www.dramafever.com/drama/124/IRIS/',
        'info_dict': {
            'id': '124',
            'title': 'IRIS',
            'description': 'md5:b3a30e587cf20c59bd1c01ec0ee1b862',
        },
        'playlist_count': 20,
    }]

    _PAGE_SIZE = 60  # max is 60 (see http://api.drama9.com/#get--api-4-episode-series-)

    def _real_extract(self, url):
        series_id = self._match_id(url)

        series = self._download_json(
            'http://www.dramafever.com/api/4/series/query/?cs=%s&series_id=%s'
            % (self._consumer_secret, series_id),
            series_id, 'Downloading series JSON')['series'][series_id]

        title = clean_html(series['name'])
        description = clean_html(series.get('description') or series.get('description_short'))

        entries = []
        for page_num in itertools.count(1):
            episodes = self._download_json(
                'http://www.dramafever.com/api/4/episode/series/?cs=%s&series_id=%s&page_size=%d&page_number=%d'
                % (self._consumer_secret, series_id, self._PAGE_SIZE, page_num),
                series_id, 'Downloading episodes JSON page #%d' % page_num)
            for episode in episodes.get('value', []):
                episode_url = episode.get('episode_url')
                if not episode_url:
                    continue
                entries.append(self.url_result(
                    compat_urlparse.urljoin(url, episode_url),
                    'DramaFever', episode.get('guid')))
            if page_num == episodes['num_pages']:
                break

        return self.playlist_result(entries, series_id, title, description)
