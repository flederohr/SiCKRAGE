#!/usr/bin/env python2
# -*- coding: utf-8 -*-
# Author: echel0n <sickrage.tv@gmail.com>
# URL: http://www.github.com/sickragetv/sickrage/
#
# This file is part of SickRage.
#
# SickRage is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickRage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickRage.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

import re
import traceback
import urllib

import sickrage
from core.caches import tv_cache
from core.helpers import bs4_parser
from providers import TorrentProvider


class TorrentBytesProvider(TorrentProvider):
    def __init__(self):

        super(TorrentBytesProvider, self).__init__("TorrentBytes")

        self.supportsBacklog = True

        self.username = None
        self.password = None
        self.ratio = None
        self.minseed = None
        self.minleech = None
        self.freeleech = False

        self.urls = {'base_url': 'https://www.torrentbytes.net',
                     'login': 'https://www.torrentbytes.net/takelogin.php',
                     'detail': 'https://www.torrentbytes.net/details.php?id=%s',
                     'search': 'https://www.torrentbytes.net/browse.php?search=%s%s',
                     'download': 'https://www.torrentbytes.net/download.php?id=%s&name=%s'}

        self.url = self.urls['base_url']

        self.categories = "&c41=1&c33=1&c38=1&c32=1&c37=1"

        self.proper_strings = ['PROPER', 'REPACK']

        self.cache = TorrentBytesCache(self)

    def _doLogin(self):

        login_params = {'username': self.username,
                        'password': self.password,
                        'login': 'Log in!'}

        response = self.getURL(self.urls['login'], post_data=login_params, timeout=30)
        if not response:
            sickrage.srCore.LOGGER.warning("Unable to connect to provider")
            return False

        if re.search('Username or password incorrect', response):
            sickrage.srCore.LOGGER.warning("Invalid username or password. Check your settings")
            return False

        return True

    def _doSearch(self, search_params, search_mode='eponly', epcount=0, age=0, epObj=None):

        results = []
        items = {'Season': [], 'Episode': [], 'RSS': []}

        if not self._doLogin():
            return results

        for mode in search_params.keys():
            sickrage.srCore.LOGGER.debug("Search Mode: %s" % mode)
            for search_string in search_params[mode]:

                if mode is not 'RSS':
                    sickrage.srCore.LOGGER.debug("Search string: %s " % search_string)

                searchURL = self.urls['search'] % (urllib.quote(search_string), self.categories)
                sickrage.srCore.LOGGER.debug("Search URL: %s" % searchURL)

                data = self.getURL(searchURL)
                if not data:
                    continue

                try:
                    with bs4_parser(data) as html:
                        # Continue only if one Release is found
                        empty = html.find('Nothing found!')
                        if empty:
                            sickrage.srCore.LOGGER.debug("Data returned from provider does not contain any torrents")
                            continue

                        torrent_table = html.find('table', attrs={'border': '1'})
                        torrent_rows = torrent_table.find_all('tr') if torrent_table else []

                        for result in torrent_rows[1:]:
                            cells = result.find_all('td')
                            size = None
                            link = cells[1].find('a', attrs={'class': 'index'})

                            full_id = link[b'href'].replace('details.php?id=', '')
                            torrent_id = full_id.split("&")[0]

                            # Free leech torrents are marked with green [F L] in the title (i.e. <font color=green>[F&nbsp;L]</font>)
                            freeleechTag = cells[1].find('font', attrs={'color': 'green'})
                            if freeleechTag and freeleechTag.text == '[F&nbsp;L]':
                                isFreeleechTorrent = True
                            else:
                                isFreeleechTorrent = False

                            if self.freeleech and not isFreeleechTorrent:
                                continue

                            try:
                                if link.has_key('title'):
                                    title = cells[1].find('a', {'class': 'index'})['title']
                                else:
                                    title = link.contents[0]
                                download_url = self.urls['download'] % (torrent_id, link.contents[0])
                                seeders = int(cells[8].find('span').contents[0])
                                leechers = int(cells[9].find('span').contents[0])

                                # Need size for failed downloads handling
                                if size is None:
                                    if re.match(r'[0-9]+,?\.?[0-9]*[KkMmGg]+[Bb]+', cells[6].text):
                                        size = self._convertSize(cells[6].text)
                                        if not size:
                                            size = -1

                            except (AttributeError, TypeError):
                                continue

                            if not all([title, download_url]):
                                continue

                            # Filter unseeded torrent
                            if seeders < self.minseed or leechers < self.minleech:
                                if mode is not 'RSS':
                                    sickrage.srCore.LOGGER.debug(
                                            "Discarding torrent because it doesn't meet the minimum seeders or leechers: {} (S:{} L:{})".format(
                                                    title, seeders, leechers))
                                continue

                            item = title, download_url, size, seeders, leechers
                            if mode is not 'RSS':
                                sickrage.srCore.LOGGER.debug("Found result: %s " % title)

                            items[mode].append(item)

                except Exception as e:
                    sickrage.srCore.LOGGER.error("Failed parsing provider. Traceback: %s" % traceback.format_exc())

            # For each search mode sort all the items by seeders if available
            items[mode].sort(key=lambda tup: tup[3], reverse=True)

            results += items[mode]

        return results

    def seedRatio(self):
        return self.ratio

    @staticmethod
    def _convertSize(sizeString):
        size = sizeString[:-2]
        modifier = sizeString[-2:]
        size = float(size)
        if modifier in 'KB':
            size *= 1024
        elif modifier in 'MB':
            size *= 1024 ** 2
        elif modifier in 'GB':
            size *= 1024 ** 3
        elif modifier in 'TB':
            size *= 1024 ** 4
        return int(size)


class TorrentBytesCache(tv_cache.TVCache):
    def __init__(self, provider_obj):
        tv_cache.TVCache.__init__(self, provider_obj)

        # only poll TorrentBytes every 20 minutes max
        self.minTime = 20

    def _getRSSData(self):
        search_params = {'RSS': ['']}
        return {'entries': self.provider._doSearch(search_params)}
