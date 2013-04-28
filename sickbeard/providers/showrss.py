# @author: Dermot Buckley <dermot@buckley.ie>
# Adapted from ezrss.py, original author of which is Nic Wolfe <nic@wolfeden.ca>
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
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.

from xml.dom.minidom import parseString
from pprint import pprint

import re
import time
import sickbeard
import generic

from sickbeard import helpers
from sickbeard import logger
from sickbeard import tvcache
from sickbeard.scene_exceptions import get_scene_exceptions

# use the built-in if it's available (python 2.6), if not use the included library
try:
    import json
except ImportError:
    from lib import simplejson as json

UPDATE_INTERVAL = 432000 # 5 days
ATTEMPT_EXCEPTIONS_IF_NOT_KNOWN = True
SHOW_LOOKUP_URL = 'http://show-api.buckley.ie/api/show'

class ShowRssProvider(generic.TorrentProvider):
    

    def __init__(self):

        generic.TorrentProvider.__init__(self, "ShowRSS")
        self.supportsBacklog = True
        self.cache = ShowRssCache(self)
        self.url = 'http://showrss.karmorra.info/'

    def isEnabled(self):
        return sickbeard.SHOWRSS
        
    def imageName(self):
        return 'showrss.png'
    
    def findSeasonResults(self, show, season):
        
        #logger.log(u'ShowRssProvider.findSeasonResults ' + str(show) + ' Season: ' + str(season), logger.DEBUG)
        results = {}
        if show.air_by_date:
            logger.log(u"ShowRSS doesn't support air-by-date backlog", logger.WARNING)
            return results  
        results = generic.TorrentProvider.findSeasonResults(self, show, season)
        return results
    
    
    @classmethod
    def _get_showrss_id(cls, tvdb_id):
        try:
            unusedVar = cls.knownShows
        except AttributeError:
            cls.knownShows = {}
            
        try:
            cachedResult = cls.knownShows[str(tvdb_id)]
            if time.time() < (cachedResult['mtime'] + UPDATE_INTERVAL):
                # cached result is still considered current, use it
                return cachedResult['response']
            # otherwise we just fall through to lookup
        except KeyError:
            pass    # no cached value, just fall through to lookup
            
        
        url = SHOW_LOOKUP_URL + '?tvdb_id=' + str(tvdb_id)
        data = helpers.getURL(url)
        result = json.loads(data)
        if not result:
            logger.log(u"Empty lookup result -> failed to find show id", logger.DEBUG)
            return None
        if result['error']:
            logger.log(u"Lookup failed: " + result['errorMessage'], logger.DEBUG)
            return None
        
        # result is good, store it for later
        cls.knownShows[str(tvdb_id)] = {'mtime': time.time(), 
                                        'response': result['show']['showrss_id'] }
        
        return result['show']['showrss_id']
    
    
    def _doSearch(self, search_params, show=None):
    
        # we just need one "param" for now, the ShowRssId
        if not 'ShowRssId' in search_params:
            logger.log(u"No ShowRssId passed into _doSearch, search ignored.", logger.WARNING)
            return []
        
      
        searchURL = '%sfeeds/%d.rss' % (self.url, search_params['ShowRssId'])

        logger.log(u"Search string: " + searchURL, logger.DEBUG)

        data = self.getURL(searchURL)

        if not data:
            return []
        
        try:
            parsedXML = parseString(data)
            items = parsedXML.getElementsByTagName('item')
        except Exception, e:
            logger.log(u"Error trying to load ShowRSS RSS feed: " + e, logger.ERROR)
            logger.log(u"RSS data: "+data, logger.DEBUG)
            return []
        
        results = []

        for curItem in items:
            
            (title, url) = self._get_title_and_url(curItem)
            
            if not title or not url:
                logger.log(u"The XML returned from the ShowRSS feed is incomplete, this result is unusable: "+data, logger.ERROR)
                continue
    
            results.append(curItem)

        return results
    
    def _get_season_search_strings(self, show, season=None):
    
        params = {}
        if not show:
            return params
        
        ShowRssId = self._get_showrss_id(show.tvdbid)
        if ShowRssId:
            params['ShowRssId'] = int(ShowRssId)
            return [params]
        
        logger.log(u"Show %s doesn't appear to be known to ShowRSS" % show.name, logger.MESSAGE)
        return []
    
    def _get_episode_search_strings(self, ep_obj):
        if not ep_obj:
            return [{}]
        # we can only usefully query by show, so do that.
        return self._get_season_search_strings(ep_obj.show)
    
    def _get_title_and_url(self, item):
        (title, url) = generic.TorrentProvider._get_title_and_url(self, item)
                
        # Sometimes showrss adds an unnecessary "HD 720p: " to the start of the show
        # name (unnecessary b/c the same info is also after the show name), which
        # throws off the name regexes.  So trim it off if present.
        if title and title.startswith(u"HD 720p: "):
            title = title[9:]
            logger.log(u"Trimmed 'HD 720p: ' from title to get %s" % title, logger.DEBUG)

        return (title, url)


class ShowRssCache(tvcache.TVCache):

    def __init__(self, provider):

        tvcache.TVCache.__init__(self, provider)

        # only poll ShowRss every 15 minutes max
        self.minTime = 15


    def _getRSSData(self):
        url = self.provider.url + 'feeds/all.rss'   # this is the "global" feed

        logger.log(u"ShowRSS cache update URL: "+ url, logger.DEBUG)

        data = self.provider.getURL(url)

        return data

    def _parseItem(self, item):

        (title, url) = self.provider._get_title_and_url(item)

        if not title or not url:
            logger.log(u"The XML returned from the ShowRss RSS feed is incomplete, this result is unusable", logger.ERROR)
            return
            
        if url and self.provider.urlIsBlacklisted(url):
            logger.log(u"url %s is blacklisted, skipping..." % url, logger.DEBUG)
            return

        logger.log(u"Adding item from RSS to cache: "+title, logger.DEBUG)

        self._addCacheEntry(title, url)


provider = ShowRssProvider()
