# Author: Dermot Buckley <dermot@buckley.ie>
#
# This file is part of Sick Beard.
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.


import os

import sickbeard
import generic

from sickbeard import helpers
from sickbeard import encodingKludge as ek

from sickbeard import logger
from sickbeard import tvcache

CONFIG_SEP = '|||'


class AnyRssProvider(generic.TorrentProvider):

    def __init__(self, name, url):

        generic.TorrentProvider.__init__(self, name)
        self.cache = AnyRssCache(self)
        self.url = url
        self.enabled = True
        self.supportsBacklog = False

    def configStr(self):
        return self.name + CONFIG_SEP + str(int(self.enabled)) + CONFIG_SEP + self.url
    
    @classmethod
    def fromConfigStr(cls, configString):
        name, enabled, url = configString.split(CONFIG_SEP)
        p = cls(name, url)
        p.enabled = enabled
        return p

    def imageName(self):
        if ek.ek(os.path.isfile, ek.ek(os.path.join, sickbeard.PROG_DIR, 'data', 'images', 'providers', self.getID() + '.png')):
            return self.getID() + '.png'
        return 'anyrss.png'

    def isEnabled(self):
        return self.enabled
    
    def _get_title_and_url(self, item):
        title = helpers.get_xml_text(item.getElementsByTagName('title')[0])
        
        # Finding the url for the torrent can be a bit tricky, as everyone seems to have their own
        # ideas as to where it should be.
        # cf. http://www.bittorrent.org/beps/bep_0036.html (but note that this isn't entirely reliable, 
        # or indeed correct).
        
        # If there's an 'enclosure' tag, then we can be reasonably confident that
        # its url attribute will be the torrent url.
        url = None
        try:
            url = item.getElementsByTagName('enclosure')[0].getAttribute('url').replace('&amp;','&')
        except IndexError:
            # next port-of-call is the 'link' tag, we use this if it looks like
            # a torrent link
            url = helpers.get_xml_text(item.getElementsByTagName('link')[0])
            if url.startswith('magnet:') or url.endswith('.torrent'):
                # found!
                pass
            else:
                # link tag doesn't look like a torrent, look for a torrent tag
                try:
                    torrTag = item.getElementsByTagName('torrent')[0]
                    try:
                        url = helpers.get_xml_text(torrTag.getElementsByTagName('magnetURI')[0])
                    except IndexError:
                        # No magnetURI?  then use the infoHash
                        infoHash = helpers.get_xml_text(torrTag.getElementsByTagName('infoHash')[0])
                        url = 'magnet:?xt=urn:btih:' + infoHash
                except IndexError:
                    # no torrent tag?  They I guess we just have to use the link
                    # tag, even if it doesn't look like a torrent
                    url = helpers.get_xml_text(item.getElementsByTagName('link')[0])
                    
        if url:
            url = url.replace('&amp;','&')

        return (title, url)


class AnyRssCache(tvcache.TVCache):

    def __init__(self, provider):

        tvcache.TVCache.__init__(self, provider)
        self.minTime = 15

    def _getRSSData(self):

        url = self.provider.url
        logger.log(u"AnyRssCache cache update URL: " + url, logger.DEBUG)
        data = self.provider.getURL(url)
        return data

    def _parseItem(self, item):
        
        (title, url) = self.provider._get_title_and_url(item)
        if not title or not url:
            logger.log(u"The XML returned from the PublicHD RSS feed is incomplete, this result is unusable", logger.ERROR)
            return

        logger.log(u"Adding item from RSS to cache: " + title, logger.DEBUG)
        self._addCacheEntry(title, url)

