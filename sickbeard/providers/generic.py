# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
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

from __future__ import with_statement # This isn't required in Python 2.6

import datetime
import os
import sys
import re
import urllib2
import copy
import traceback
import re
import base64

import sickbeard

from sickbeard import helpers, classes, logger, db

from sickbeard.common import Quality, MULTI_EP_RESULT, SEASON_RESULT
from sickbeard import tvcache
from sickbeard import encodingKludge as ek
from sickbeard.exceptions import ex

from lib.hachoir_parser import createParser

from sickbeard.name_parser.parser import NameParser, InvalidNameException

class GenericProvider:

    NZB = "nzb"
    TORRENT = "torrent"
    VOD = "strm"    # just to keep SB happy, not really an extension like the other two.

    def __init__(self, name):

        # these need to be set in the subclass
        self.providerType = None
        self.name = name
        self.url = ''

        self.supportsBacklog = False

        self.cache = tvcache.TVCache(self)

    def getID(self):
        return GenericProvider.makeID(self.name)

    @staticmethod
    def makeID(name):
        return re.sub("[^\w\d_]", "_", name).lower()

    def imageName(self):
        return self.getID() + '.png'

    def _checkAuth(self):
        return

    def isActive(self):
        if self.providerType == GenericProvider.NZB and sickbeard.USE_NZBS:
            return self.isEnabled()
        elif self.providerType == GenericProvider.TORRENT and sickbeard.USE_TORRENTS:
            return self.isEnabled()
        elif self.providerType == GenericProvider.VOD and sickbeard.USE_VODS:
            return self.isEnabled()
        else:
            return False

    def isEnabled(self):
        """
        This should be overridden and should return the config setting eg. sickbeard.MYPROVIDER
        """
        return False

    def getResult(self, episodes):
        """
        Returns a result of the correct type for this provider
        """

        if self.providerType == GenericProvider.NZB:
            result = classes.NZBSearchResult(episodes)
        elif self.providerType == GenericProvider.TORRENT:
            result = classes.TorrentSearchResult(episodes)
        elif self.providerType == GenericProvider.VOD:
            result = classes.VODSearchResult(episodes)
        else:
            result = classes.SearchResult(episodes)

        result.provider = self

        return result


    def getURL(self, url, headers=None):
        """
        By default this is just a simple urlopen call but this method should be overridden
        for providers with special URL requirements (like cookies)
        """

        if not headers:
            headers = []

        result = helpers.getURL(url, headers)

        if result is None:
            logger.log(u"Error loading "+self.name+" URL: " + url, logger.ERROR)
            return None

        return result

    def downloadResult(self, result):
        """
        Save the result to disk.
        """

        logger.log(u"Downloading a result from " + self.name+" at " + result.url)

        data = self.getURL(result.url)

        if data == None:
            return False

        # use the appropriate watch folder
        if self.providerType == GenericProvider.NZB:
            saveDir = sickbeard.NZB_DIR
            writeMode = 'w'
        elif self.providerType == GenericProvider.TORRENT:
            saveDir = sickbeard.TORRENT_DIR
            writeMode = 'wb'
        else:
            return False

        # use the result name as the filename
        fileName = ek.ek(os.path.join, saveDir, helpers.sanitizeFileName(result.name) + '.' + self.providerType)

        logger.log(u"Saving to " + fileName, logger.DEBUG)

        try:
            fileOut = open(fileName, writeMode)
            fileOut.write(data)
            fileOut.close()
            helpers.chmodAsParent(fileName)
        except IOError, e:
            logger.log("Unable to save the file: "+ex(e), logger.ERROR)
            return False

        # as long as it's a valid download then consider it a successful snatch
        return self._verify_download(fileName)

    def _verify_download(self, file_name=None):
        """
        Checks the saved file to see if it was actually valid, if not then consider the download a failure.
        Returns a Boolean
        """
        
        logger.log(u"Verifying Download %s" % file_name, logger.DEBUG)

        if self.providerType == GenericProvider.TORRENT:
            # According to /usr/share/file/magic/archive, the magic number for
            # torrent files is 
            #    d8:announce
            # So instead of messing with buggy parsers (as was done here before)
            # we just check for this magic instead.
            # Note that a significant minority of torrents have a not-so-magic of "d12:_info_length",
            # which while not explicit in the spec is valid bencode and works with Transmission and uTorrent.
            try:
                with open(file_name, "rb") as f:
                    magic = f.read(16)
                    if magic[:11] == "d8:announce" or magic == "d12:_info_length":
                        return True
                    else:
                        logger.log("Magic number for %s is neither 'd8:announce' nor 'd12:_info_length', got '%s' instead" % (file_name, magic), logger.WARNING)
                        #logger.log(f.read())
                        return False
            except Exception, eparser:
                logger.log("Failed to read magic numbers from file: "+ex(eparser), logger.ERROR)
                logger.log(traceback.format_exc(), logger.DEBUG)
                return False

        return True

    def searchRSS(self):
        self.cache.updateCache()
        return self.cache.findNeededEpisodes()

    def getQuality(self, item):
        """
        Figures out the quality of the given RSS item node
        
        item: An xml.dom.minidom.Node representing the <item> tag of the RSS feed
        
        Returns a Quality value obtained from the node's data 
        """
        (title, url) = self._get_title_and_url(item) #@UnusedVariable
        quality = Quality.nameQuality(title)
        return quality

    def _doSearch(self):
        return []

    def _get_season_search_strings(self, show, season, episode=None):
        return []

    def _get_episode_search_strings(self, ep_obj):
        return []
    
    def _get_title_and_url(self, item):
        """
        Retrieves the title and URL data from the item XML node
        item: An xml.dom.minidom.Node representing the <item> tag of the RSS feed
        Returns: A tuple containing two strings representing title and URL respectively
        """
        title = helpers.get_xml_text(item.getElementsByTagName('title')[0])
        try:
            url = helpers.get_xml_text(item.getElementsByTagName('link')[0])
            if url:
                url = url.replace('&amp;','&')
        except IndexError:
            url = None
        
        return (title, url)
    
    def findEpisode(self, episode, manualSearch=False):

        self._checkAuth()

        logger.log(u"Searching "+self.name+" for " + episode.prettyName())

        self.cache.updateCache()
        results = self.cache.searchCache(episode, manualSearch)
        logger.log(u"Cache results: "+str(results), logger.DEBUG)
        logger.log(u"manualSearch: "+str(manualSearch), logger.DEBUG)

        # if we got some results then use them no matter what.
        # OR
        # return anyway unless we're doing a manual search
        if results or not manualSearch:
            return results

        itemList = []
        
        # create a copy of the episode, using scene numbering
        episode_scene = copy.copy(episode)
        episode_scene.convertToSceneNumbering()

        for cur_search_string in self._get_episode_search_strings(episode_scene):
            itemList += self._doSearch(cur_search_string, show=episode.show)

        for item in itemList:

            (title, url) = self._get_title_and_url(item)

            # parse the file name
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

            quality = self.getQuality(item)

            if not episode.show.wantEpisode(episode.season, episode.episode, quality, manualSearch):
                logger.log(u"Ignoring result "+title+" because we don't want an episode that is "+Quality.qualityStrings[quality], logger.DEBUG)
                continue

            logger.log(u"Found result " + title + " at " + url, logger.DEBUG)

            result = self.getResult([episode])
            result.url = url
            result.name = title
            result.quality = quality

            results.append(result)

        return results



    def findSeasonResults(self, show, season):

        itemList = []
        results = {}

        for curString in self._get_season_search_strings(show, season):
            itemList += self._doSearch(curString)

        for item in itemList:

            (title, url) = self._get_title_and_url(item)

            quality = self.getQuality(item)

            # parse the file name
            try:
                myParser = NameParser(False)
                parse_result = myParser.parse(title, True)
            except InvalidNameException:
                logger.log(u"Unable to parse the filename "+title+" into a valid episode", logger.WARNING)
                continue

            if not show.air_by_date:
                # this check is meaningless for non-season searches
                if (parse_result.season_number != None and parse_result.season_number != season) or (parse_result.season_number == None and season != 1):
                    logger.log(u"The result "+title+" doesn't seem to be a valid episode for season "+str(season)+", ignoring")
                    continue

                # we just use the existing info for normal searches
                actual_season = season
                actual_episodes = parse_result.episode_numbers
            
            else:
                if not parse_result.air_by_date:
                    logger.log(u"This is supposed to be an air-by-date search but the result "+title+" didn't parse as one, skipping it", logger.DEBUG)
                    continue
                
                myDB = db.DBConnection()
                sql_results = myDB.select("SELECT season, episode FROM tv_episodes WHERE showid = ? AND airdate = ?", [show.tvdbid, parse_result.air_date.toordinal()])

                if len(sql_results) != 1:
                    logger.log(u"Tried to look up the date for the episode "+title+" but the database didn't give proper results, skipping it", logger.WARNING)
                    continue
                
                actual_season = int(sql_results[0]["season"])
                actual_episodes = [int(sql_results[0]["episode"])]

            # make sure we want the episode
            wantEp = True
            for epNo in actual_episodes:
                if not show.wantEpisode(actual_season, epNo, quality):
                    wantEp = False
                    break
            
            if not wantEp:
                logger.log(u"Ignoring result "+title+" because we don't want an episode that is "+Quality.qualityStrings[quality], logger.DEBUG)
                continue

            logger.log(u"Found result " + title + " at " + url, logger.DEBUG)

            # make a result object
            epObj = []
            for curEp in actual_episodes:
                epObj.append(show.getEpisode(actual_season, curEp))

            result = self.getResult(epObj)
            result.url = url
            result.name = title
            result.quality = quality

            if len(epObj) == 1:
                epNum = epObj[0].episode
            elif len(epObj) > 1:
                epNum = MULTI_EP_RESULT
                logger.log(u"Separating multi-episode result to check for later - result contains episodes: "+str(parse_result.episode_numbers), logger.DEBUG)
            elif len(epObj) == 0:
                epNum = SEASON_RESULT
                result.extraInfo = [show]
                logger.log(u"Separating full season result to check for later", logger.DEBUG)

            if epNum in results:
                results[epNum].append(result)
            else:
                results[epNum] = [result]


        return results

    def findPropers(self, date=None):

        results = self.cache.listPropers(date)

        return [classes.Proper(x['name'], x['url'], datetime.datetime.fromtimestamp(x['time'])) for x in results]


class NZBProvider(GenericProvider):

    def __init__(self, name):

        GenericProvider.__init__(self, name)

        self.providerType = GenericProvider.NZB
        
        
# This is a list of sites that serve torrent files given the associated hash.
# They will be tried in order, so put the most reliable at the top.
MAGNET_TO_TORRENT_URLS = ['http://torrage.com/torrent/%s.torrent',
                          'http://zoink.it/torrent/%s.torrent',
                          'http://torcache.net/torrent/%s.torrent',
                          'http://torrage.ws/torrent/%s.torrent', 
                         ]

class TorrentProvider(GenericProvider):

    def __init__(self, name):

        GenericProvider.__init__(self, name)

        self.providerType = GenericProvider.TORRENT
        
    def getHashFromMagnet(self, magnet):
        """
        Pull the hash from a magnet link (if possible).
        Handles the various possible encodings etc. 
        (returning a 40 byte hex string).  
        Returns None on failure
        """
        logger.log('magnet: ' + magnet, logger.DEBUG)
        info_hash_search = re.search('btih:([0-9A-Z]+)', magnet, re.I)
        if info_hash_search:
            torrent_hash = info_hash_search.group(1)
            
            # hex hashes will be 40 characters long, base32 will be 32 chars long
            if len(torrent_hash) == 32:
                # convert the base32 to base 16
                logger.log('base32_hash: ' + torrent_hash, logger.DEBUG)
                torrent_hash = base64.b16encode(base64.b32decode(torrent_hash, True))
            elif len(torrent_hash) <> 40:
                logger.log('Torrent hash length (%d) is incorrect (should be 40), returning None' % (len(torrent_hash)), logger.DEBUG)
                return None
                
            logger.log('torrent_hash: ' + torrent_hash, logger.DEBUG)
            return torrent_hash.upper()
        else:
            # failed to pull info hash
            return None
        
    def magnetToTorrent(self, magnet):
        """
        This returns a single (best guess) url for a torrent file for the passed-in
        magnet link.
        For now it just uses the first entry from MAGNET_TO_TORRENT_URLS.
        If there's any problem with the magnet link, this will return None.
        """
        torrent_hash = self.getHashFromMagnet(magnet)
        if torrent_hash:
            return MAGNET_TO_TORRENT_URLS[0] % torrent_hash.upper()
        else:
            # failed to pull info hash
            return None

    def urlIsBlacklisted(self, url):
        """
        For now this is just a hackish way of blacklisting direct links to 
        extratorrent.com (which, despite appearing to be .torrent links, are
        actualling advertisement pages)
        """
        if url is None:
            return False
        if url.startswith('http://extratorrent.com/') or url.startswith('https://extratorrent.com/'):
            return True
        return False
    
    def getURL(self, url, headers=None):
        """
        Overridden to deal with possible magnet links (but still best to not
        pass magnet links to this - downloadResult has better handling with fallbacks)
        """
        if url and url.startswith('magnet:'):
            torrent_url = self.magnetToTorrent(url)
            if torrent_url:
                logger.log(u"Changed magnet %s to %s" % (url, torrent_url), logger.DEBUG)
                url = torrent_url
            else:
                logger.log(u"Failed to handle magnet url %s, skipping..." % url, logger.DEBUG)
                return None
            
        # magnet link fixed, just call the base class
        return GenericProvider.getURL(self, url, headers)
    
    def downloadResult(self, result):
        """
        Overridden to handle magnet links (using multiple fallbacks)
        """
        logger.log(u"Downloading a result from " + self.name+" at " + result.url)
        
        if result.url and result.url.startswith('magnet:'):
            torrent_hash = self.getHashFromMagnet(result.url)
            if torrent_hash:
                urls = [url_fmt % torrent_hash for url_fmt in MAGNET_TO_TORRENT_URLS]
            else:
                logger.log(u"Failed to handle magnet url %s, skipping..." % torrent_hash, logger.DEBUG)
                return False
        else:
            urls = [result.url]
            
        # use the result name as the filename
        fileName = ek.ek(os.path.join, sickbeard.TORRENT_DIR, helpers.sanitizeFileName(result.name) + '.' + self.providerType)
            
        for url in urls:
            logger.log(u"Trying d/l url: " + url, logger.DEBUG)
            data = self.getURL(url)
            
            if data == None:
                logger.log(u"Got no data for " + url, logger.DEBUG)
                # fall through to next iteration
            elif not data.startswith("d8:announce") and not data.startswith("d12:_info_length"):
                logger.log(u"d/l url %s failed, not a valid torrent file" % (url), logger.MESSAGE)
            else:
                try:
                    fileOut = open(fileName, 'wb')
                    fileOut.write(data)
                    fileOut.close()
                    helpers.chmodAsParent(fileName)
                except IOError, e:
                    logger.log("Unable to save the file: "+ex(e), logger.ERROR)
                    return False
                
                logger.log(u"Success with url: " + url, logger.DEBUG)
                return True
        else:
            logger.log(u"All d/l urls have failed.  Sorry.", logger.MESSAGE)
            return False
        
        
        return False



class VODProvider(GenericProvider):
    """
    Video-On-Demand provider
    """
    
    def __init__(self, name):
        GenericProvider.__init__(self, name)
        self.providerType = GenericProvider.VOD

    
