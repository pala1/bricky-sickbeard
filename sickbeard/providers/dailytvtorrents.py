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
#
# @author: Dermot Buckley <dermot@buckley.ie>
# Adapted from ezrss.py, original author of which is Nic Wolfe <nic@wolfeden.ca>
#

from xml.dom.minidom import parseString
from pprint import pprint
from httplib import BadStatusLine

import time
import sickbeard
import generic
import urllib, urllib2
import copy
import StringIO, zlib, gzip
import socket
import traceback


try:
    import lib.simplejson as json 
except:
    import json 

from sickbeard import helpers
from sickbeard import logger
from sickbeard import tvcache
from sickbeard.common import Quality, USER_AGENT
from sickbeard.scene_exceptions import get_scene_exceptions
from sickbeard.name_parser.parser import NameParser, InvalidNameException

UPDATE_INTERVAL = 432000 # 5 days
ATTEMPT_EXCEPTIONS_IF_NOT_KNOWN = True

class DailyTvTorrentsProvider(generic.TorrentProvider):
    

    def __init__(self):
        generic.TorrentProvider.__init__(self, "DailyTvTorrents")
        self.supportsBacklog = True
        self.cache = DailyTvTorrentsCache(self)
        self.url = 'http://www.dailytvtorrents.org/'

    def isEnabled(self):
        return sickbeard.DAILYTVTORRENTS
        
    def imageName(self):
        return 'missing.png'
    
    def findEpisode (self, episode, manualSearch=False):

        self._checkAuth()

        logger.log(u"Searching "+self.name+" for " + episode.prettyName())

        self.cache.updateCache()
        results = self.cache.searchCache(episode, manualSearch)
        logger.log(u"Cache results: "+str(results), logger.DEBUG)

        # if we got some results then use them no matter what.
        # OR
        # return anyway unless we're doing a manual search
        if results or not manualSearch:
            return results
        
        # create a copy of the episode, using scene numbering
        episode_scene = copy.copy(episode)
        episode_scene.convertToSceneNumbering()
        
        simple_show_name = self._get_simple_name_for_show(episode.show)
        if not simple_show_name:
            logger.log(u"Show %s not known to dtvt, not running any further search." % (episode.show.name), logger.MESSAGE)
            return results
        
        query_params = { 'show_name': simple_show_name }
        if episode.show.air_by_date:
            query_params['episode_num'] = str(episode.airdate)
        else:
            query_params['episode_num'] = 'S%02dE%02d' % (episode.season, episode.episode)
        
        api_result = self._api_call('1.0/torrent.getInfosAll', query_params)
        
        if api_result:
            for cur_result in api_result:
                #{                
                #    "name": "Futurama.S06E23.720p.HDTV.x264-IMMERSE",
                #    "quality": "720",
                #    "age": 47406999,
                #    "data_size": 369900878,
                #    "seeds": 2,
                #    "leechers": 0,
                #    "link": "http:\/\/www.dailytvtorrents.org\/dl\/9pa\/Futurama.S06E23.720p.HDTV.x264-IMMERSE.DailyTvTorrents.torrent"
                #}
                title = cur_result['name']
                url = cur_result['link']
                
                try:
                    myParser = NameParser()
                    parse_result = myParser.parse(title, True)
                except InvalidNameException:
                    logger.log(u"Unable to parse the filename "+title+" into a valid episode", logger.WARNING)
                    continue
                
                if episode.show.air_by_date:
                    if parse_result.air_date != episode.airdate:
                        logger.log("Episode "+title+" didn't air on "+str(episode.airdate)+", skipping it", logger.DEBUG)
                        continue
                elif parse_result.season_number != episode.season or episode.episode not in parse_result.episode_numbers:
                    logger.log("Episode "+title+" isn't "+str(episode.season)+"x"+str(episode.episode)+", skipping it", logger.DEBUG)
                    continue
                
                #quality = cur_result['quality'] - actually, we get a bit more info 
                # from the torrent name, so let's use that instead.
                quality = Quality.nameQuality(title)
                
                if not episode.show.wantEpisode(episode.season, episode.episode, quality, manualSearch):
                    logger.log(u"Ignoring result "+title+" because we don't want an episode that is "+Quality.qualityStrings[quality], logger.DEBUG)
                    continue
                
                logger.log(u"Found result " + title + " at " + url, logger.DEBUG)

                result = self.getResult([episode])
                result.url = url
                result.name = title
                result.quality = quality

                results.append(result)
        else:
            logger.log(u"No result from api call 1.0/torrent.getInfosAll", logger.WARNING)

        return results
    
    def findSeasonResults(self, show, season):
        
        logger.log(u'DailyTvTorrentsProvider.findSeasonResults ' + str(show) + ' Season: ' + str(season), logger.DEBUG)
        
        results = {}
        
        if show.air_by_date:
            logger.log(u"DailyTvTorrents doesn't support air-by-date backlog", logger.WARNING)
            return results
        
        results = generic.TorrentProvider.findSeasonResults(self, show, season)
        
        return results
    
    def _get_season_search_strings(self, show, season=None):
    
        params = {}
    
        if not show:
            return params
        
        #params['show_name'] = helpers.sanitizeSceneName(show.name).replace('.',' ').encode('utf-8')
        params['simple_show_name'] = self._get_simple_name_for_show(show)
          
        if season != None:
            params['season'] = season
    
        return [params]
    
    def _api_call(self, fnName, params = dict()):
        """
        Wrapper for simple json api call.
            
        @param fnName: string, something like '1.0/torrent.getInfo'
        @param params: dict of params, if any
        @return: mixed - returns json result as an object, or None on failure.
        """
        try:
            paramsEnc = urllib.urlencode(params)
            
            opener = urllib2.build_opener()
            opener.addheaders = [('User-Agent', USER_AGENT), ('Accept-Encoding', 'gzip,deflate')]
            
            usock = opener.open('http://api.dailytvtorrents.org/%s?%s' % (fnName, paramsEnc))
            url = usock.geturl()
            encoding = usock.info().get("Content-Encoding")
    
            if encoding in ('gzip', 'x-gzip', 'deflate'):
                content = usock.read()
                if encoding == 'deflate':
                    data = StringIO.StringIO(zlib.decompress(content))
                else:
                    data = gzip.GzipFile(fileobj=StringIO.StringIO(content))
                result = data.read()
    
            else:
                result = usock.read()
    
            usock.close()
            
            if result:
                return json.loads(result)
            else:
                return None   
    
        except urllib2.HTTPError, e:
            if e.code == 404:
                # for a 404, we fake an empty result
                return None
            logger.log(u"HTTP error " + str(e.code) + " while calling DailyTvTorrents api " + fnName, logger.ERROR)
            return None
        except urllib2.URLError, e:
            logger.log(u"URL error " + str(e.reason) + " while calling DailyTvTorrents api " + fnName, logger.ERROR)
            return None
        except BadStatusLine:
            logger.log(u"BadStatusLine error while calling DailyTvTorrents api " + fnName, logger.ERROR)
            return None
        except socket.timeout:
            logger.log(u"Timed out while calling DailyTvTorrents api " + fnName, logger.ERROR)
            return None
        except ValueError:
            logger.log(u"Unknown error while calling DailyTvTorrents api " + fnName, logger.ERROR)
            return None
        except IOError, e:
            logger.log(u"Error trying to communicate with dailytvtorrents: "+repr(e), logger.ERROR)
            return None
        except Exception:
            logger.log(u"Unknown exception while calling DailyTvTorrents api " + fnName + ": " + traceback.format_exc(), logger.ERROR)
            return None
    
    _simple_show_names = dict() # populated as needed, saves repeated lookups
    
    def _show_name_to_simple_name(self, show_name):
        """
        The site has a concept of 'simple name' for each show, which is uses
        as a search term.  So for a show like '666 Park Avenue', the simple
        name is '666-park-avenue'.
        We need the simple name to do any searches.
        
        Returns a string on success, false on failure
        """
        if show_name in self._simple_show_names:
            return self._simple_show_names[show_name]
        
        logger.log(u"DailyTvTorrents looking up simple show name for : "+ show_name, logger.DEBUG)
        result = self._api_call('1.0/shows.search', {"query": show_name})
        if result:
            simple_name = result['shows'][0]['name']
            self._simple_show_names[show_name] = simple_name
            logger.log(u"DailyTvTorrents got simple name : "+ simple_name, logger.DEBUG)
            return simple_name
        else:
            self._simple_show_names[show_name] = False
            return False
        
    def _get_simple_name_for_show(self, show):
        """
        Return the simple name for a show, if known.
        @param param: sickbeard.tv.TVShow
        @return: string on success, False on failure. 
        """
        possibleNames = [show.name] + show.getAlternateNames()
        for tryName in possibleNames:
            res = self._show_name_to_simple_name(tryName)
            if res:
                return res
        return False
        
    
    def _doSearch(self, search_params, show=None):
        """
        For now this is an rss search.  I think this is currently only used for season
        searches as episode searches are handled by 'findEpisode', which doesn't call
        this.
        (dtvt doesn't have a suitable api for season searches, so this is probably best left as-is)
        """
        
        # For now we *only* use the show_name param, everything else is ignored
        # (this might change in the future if we use their API)
        if not 'simple_show_name' in search_params:
            logger.log(u"No simple_show_name passed into _doSearch, search ignored.", logger.WARNING)
            return []
        
      
        simple_show_name = search_params['simple_show_name']
        if not simple_show_name: # it could be present, but false
            logger.log(u"Show %s not known to dtvt, not running search." % (search_params['show_name']), logger.WARNING)
            return []
            
        searchURL = '%srss/show/%s?norar=yes&items=all' % (self.url, simple_show_name)
        logger.log(u"Search string: " + searchURL, logger.DEBUG)
        data = self.getURL(searchURL)

        if not data:
            return []
        
        try:
            parsedXML = parseString(data)
            items = parsedXML.getElementsByTagName('item')
        except Exception, e:
            logger.log(u"Error trying to load dtvt RSS feed: " + e, logger.ERROR)
            logger.log(u"RSS data: "+data, logger.DEBUG)
            return []
        
        results = []

        for curItem in items:
            
            (title, url) = self._get_title_and_url(curItem)
            
            if not title or not url:
                logger.log(u"The XML returned from the dtvt feed is incomplete, this result is unusable: "+data, logger.ERROR)
                continue
    
            results.append(curItem)

        return results
    
    def _get_title_and_url(self, item):
        #(title, url) = generic.TorrentProvider._get_title_and_url(self, item)

        title = helpers.get_xml_text(item.getElementsByTagName('title')[0], mini_dom=True)
        url = item.getElementsByTagName('enclosure')[0].getAttribute('url').replace('&amp;','&')

        return (title, url)
    
    def getQuality(self, item):
        """
        Figures out the quality of the given RSS item node
        item: An xml.dom.minidom.Node representing the <item> tag of the RSS feed
        Returns a Quality value obtained from the node's data
        
        Overridden here because dtvt has its own quirky way of doing quality. 
        """
        (title, url) = self._get_title_and_url(item) #@UnusedVariable
        if title:
            if title.endswith(' [HD]'):
                return Quality.SDTV
            elif title.endswith(' [720]'):
                return Quality.HDTV
            elif title.endswith(' [1080]'):
                return Quality.FULLHDTV # best choice available I think
            
        quality = Quality.nameQuality(title)
        return quality


class DailyTvTorrentsCache(tvcache.TVCache):

    def __init__(self, provider):
        tvcache.TVCache.__init__(self, provider)
        # only poll DailyTvTorrents every 30 minutes max
        # (bumped up from 15 mins b/c we run very close to 3MB limit every day)
        self.minTime = 30


    def _getRSSData(self):
        url = self.provider.url + 'rss/allshows?norar=yes'   # alternate option is single=yes (limits to torrents with just one file)
        logger.log(u"DailyTvTorrents cache update URL: "+ url, logger.DEBUG)
        data = self.provider.getURL(url)

        return data

    def _parseItem(self, item):
        (title, url) = self.provider._get_title_and_url(item)
        if not title or not url:
            logger.log(u"The XML returned from the DailyTvTorrents RSS feed is incomplete, this result is unusable", logger.ERROR)
            return
            
        if url and self.provider.urlIsBlacklisted(url):
            logger.log(u"url %s is blacklisted, skipping..." % url, logger.DEBUG)
            return
        
        if title:
            if title.endswith(' [HD]'):
                quality = Quality.SDTV
            elif title.endswith(' [720]'):
                quality = Quality.HDTV
            elif title.endswith(' [1080]'):
                quality = Quality.FULLHDTV # best choice available I think
            else:
                quality = None # just fall through to sb quality processing
        else:
            quality = None

        logger.log(u"Adding item from RSS to cache: "+title, logger.DEBUG)
        self._addCacheEntry(name=title, url=url, quality=quality)

provider = DailyTvTorrentsProvider()
