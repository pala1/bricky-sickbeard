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
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.

from xml.dom.minidom import parseString
from pprint import pprint
from bs4 import BeautifulSoup

import time
import sickbeard
import generic

from sickbeard import helpers
from sickbeard import logger
from sickbeard import tvcache
from sickbeard.scene_exceptions import get_scene_exceptions

UPDATE_INTERVAL = 432000 # 5 days
ATTEMPT_EXCEPTIONS_IF_NOT_KNOWN = True

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
        
        logger.log(u'ShowRssProvider.findSeasonResults ' + str(show) + ' Season: ' + str(season), logger.DEBUG)
        
        results = {}
        
        if show.air_by_date:
            logger.log(u"ShowRSS doesn't support air-by-date backlog", logger.WARNING)
            return results
        
        results = generic.TorrentProvider.findSeasonResults(self, show, season)
        
        return results
    
    
    knownShows = None   # pulled in from ShowRss as needed
    mtime = 0   # this is the last update timestamp
    
    def _getShowRssIdForShow(self, showName):
        """
        Get the show id (used by ShowRSS) for a show name.
        Returns None if unknown or not found.
        """

        if self.knownShows == None or (time.time() > (self.mtime + UPDATE_INTERVAL)):
            # pull in the list of feeds from the browse page
            logger.log(u"ShowRssProvider doing lookup of id mapping", logger.DEBUG)
            rawPage = self.getURL('%s?cs=feeds' % (self.url))
            soup = BeautifulSoup(rawPage)
            #logger.log(u"ShowRSS rawPage is as follows: %s" % (soup.prettify()), logger.DEBUG)
            select = soup.find('select', { 'name' : "show" })
            
            if select:
                #logger.log(u"ShowRSS show select is as follows: %s" % (select.prettify()), logger.DEBUG)
                
                self.knownShows = {}
                for option in select.children:
                    if u'value' in option.attrs:
                        try:
                            self.knownShows[unicode(option.string)] = int(option[u'value'])
                        except ValueError:
                            # ValueError will be raised when option[u'value'] is not an integer.  We can 
                            # safely ignore when this happens
                            pass
                        
                logger.log(u"knownShows: " + str(self.knownShows), logger.DEBUG)
                self.mtime = time.time()
            else:
                logger.log(u"Couldn't find the select named 'show' on the showRss browse page, falling back to static list of known shows", logger.WARNING)
                self.mtime = time.time()
                self.knownShows = {
                    '2 Broke Girls': 378, 
                    '30 Rock': 2, 
                    '30 Seconds': 225, 
                    '90210': 3, 
                    'A Gifted Man': 381, 
                    'Against the Wall': 384, 
                    'Alcatraz': 422, 
                    'Alphas': 352, 
                    'America\'s Got Talent': 450, 
                    'America\'s Next Top Model': 113, 
                    'American Dad!': 4    , 
                    'American Horror Story': 401, 
                    'American Idol': 84, 
                    'Anger Management': 454, 
                    'Archer': 213, 
                    'Arctic Air': 421, 
                    'Are You There, Chelsea?': 434, 
                    'Awake': 431, 
                    'Awkward.': 372, 
                    'Beaver Falls': 387, 
                    'Beavis and Butt-Head': 405, 
                    'Bedlam': 332, 
                    'Being Erica': 119, 
                    'Being Human': 139, 
                    'Being Human (US)': 425, 
                    'Big Brother': 171, 
                    'Big Brother\'s Little Brother': 167, 
                    'Black Gold': 198, 
                    'Blue Bloods': 311, 
                    'Blue Mountain State': 410, 
                    'Boardwalk Empire': 292, 
                    'Bob\'s Burgers': 323, 
                    'Body of Proof': 342, 
                    'Bones': 6    , 
                    'Bored to Death': 214, 
                    'Breaking Bad': 77, 
                    'Breaking In': 437, 
                    'Breakout Kings': 343, 
                    'Bunheads': 460, 
                    'Burn Notice': 101, 
                    'Californication': 8    , 
                    'Castle (2009)': 109, 
                    'Chaos': 339, 
                    'Chase': 317, 
                    'Chemistry': 398, 
                    'Chuck': 10, 
                    'Combat Hospital': 356, 
                    'Common Law (2012)': 445, 
                    'Community': 215, 
                    'Continuum': 446, 
                    'Cougar Town': 218, 
                    'Covert Affairs': 285, 
                    'Criminal Minds': 18, 
                    'CSI: Crime Scene Investigation': 19, 
                    'CSI: Miami': 20, 
                    'CSI: NY': 21, 
                    'Curb Your Enthusiasm': 147, 
                    'Dallas (2012)': 458, 
                    'Damages': 22, 
                    'Dan For Mayor': 262, 
                    'Dancing With the Stars': 140, 
                    'Deadliest Catch': 78, 
                    'Deadliest Warrior': 127, 
                    'Death Valley': 379, 
                    'Desperate Housewives': 23, 
                    'Dexter': 24, 
                    'Dirty Jobs': 85, 
                    'Doctor Who (2005)': 103, 
                    'Don\'t Trust the B---- in Apartment 23': 442, 
                    'Downton Abbey': 383, 
                    'Drop Dead Diva': 183, 
                    'Eastbound & Down': 159, 
                    'Endgame': 340, 
                    'Episodes': 325, 
                    'Eternal Law': 417, 
                    'Eureka': 108, 
                    'Fairly Legal': 333, 
                    'Falling Skies': 351, 
                    'Family Guy': 27, 
                    'Fear Factor': 411, 
                    'Fifth Gear': 155, 
                    'Flashpoint': 87, 
                    'Franklin & Bash': 360, 
                    'Fresh Meat': 395, 
                    'Fringe': 28, 
                    'Futurama': 276, 
                    'Game of Thrones': 350, 
                    'GCB': 441, 
                    'Girls': 444, 
                    'Glee': 31, 
                    'Gossip Girl': 32, 
                    'Grey\'s Anatomy': 34, 
                    'Grimm': 403, 
                    'Happily Divorced': 359, 
                    'Happy Endings': 370, 
                    'Harry\'s Law': 337, 
                    'Hart of Dixie': 375, 
                    'Haven': 284, 
                    'Hawaii Five-0': 306, 
                    'Hell On Wheels': 409, 
                    'Hell\'s Kitchen (US)': 120, 
                    'Hiccups': 354, 
                    'Homeland': 400, 
                    'Hot In Cleveland': 287, 
                    'House': 36, 
                    'House of Lies': 413, 
                    'How I Met Your Mother': 37, 
                    'How Not To Live Your Life': 210, 
                    'Human Target': 246, 
                    'Hustle': 174, 
                    'In Plain Sight': 104, 
                    'InSecurity': 345, 
                    'It\'s Always Sunny in Philadelphia': 114, 
                    'Jane By Design': 452, 
                    'Justified': 260, 
                    'Kidnap And Ransom': 328, 
                    'King (2011)': 432, 
                    'Kitchen Nightmares': 165, 
                    'L.A. Ink': 294, 
                    'Last Comic Standing': 272, 
                    'Last Man Standing': 408, 
                    'Late Night With David Letterman': 248, 
                    'Law & Order: Los Angeles': 308, 
                    'Law & Order: Special Victims Unit': 129, 
                    'Law and Order: UK': 244, 
                    'Level Up': 451, 
                    'Leverage': 86, 
                    'Life\'s Too Short': 419, 
                    'Line of Duty': 462, 
                    'Little Mosque on the Prairie': 222, 
                    'Longmire': 456, 
                    'Lost Girl': 296, 
                    'Louie': 278, 
                    'Luck': 426, 
                    'Mad Men': 42, 
                    'Magic City': 438, 
                    'Make it or Break it': 254, 
                    'Man Up!': 407, 
                    'Man vs. Wild': 126, 
                    'Melissa & Joey': 315, 
                    'Men at Work': 447, 
                    'Men of a Certain Age': 241, 
                    'Merlin': 45, 
                    'Midsomer Murders': 303, 
                    'Mike & Molly': 313, 
                    'Misfits': 243, 
                    'Missing (2012)': 435, 
                    'Mock the Week': 461, 
                    'Modern Family': 221, 
                    'Monsterquest': 189, 
                    'MythBusters': 46, 
                    'Napoleon Dynamite': 420, 
                    'NCIS': 47, 
                    'NCIS: Los Angeles': 207, 
                    'Necessary Roughness': 358, 
                    'New Girl': 396, 
                    'New Tricks': 191, 
                    'Nikita': 297, 
                    'Nurse Jackie': 169, 
                    'Once Upon a Time (2011)': 402, 
                    'One Tree Hill': 51, 
                    'Packed to the Rafters': 203, 
                    'Pan Am': 382, 
                    'Parenthood (2010)': 255, 
                    'Parks and Recreation': 138, 
                    'Person of Interest': 388, 
                    'Planet Dinosaur': 399, 
                    'Portlandia': 329, 
                    'Pretty Little Liars': 283, 
                    'Prime Suspect (US)': 389, 
                    'Primeval': 320, 
                    'Private Practice': 99, 
                    'Project Runway': 157, 
                    'Psych': 111, 
                    'Psychoville': 180, 
                    'QI': 240, 
                    'Raising Hope': 302, 
                    'Real Time With Bill Maher': 97, 
                    'Rescue Me': 118, 
                    'Revenge': 393, 
                    'Ringer': 397, 
                    'Rizzoli & Isles': 289, 
                    'Robot Chicken': 83, 
                    'Rookie Blue': 279, 
                    'Royal Pains': 163, 
                    'Rules of Engagement': 141, 
                    'Run\'s House': 152, 
                    'Sanctuary': 145, 
                    'Saturday Night Live': 91, 
                    'Saving Hope': 453, 
                    'Scandal (2012)': 439, 
                    'Shameless': 326, 
                    'Sherlock': 286, 
                    'Single Ladies': 353, 
                    'Skins': 58, 
                    'Smash (2012)': 427, 
                    'So You Think You Can Dance': 92, 
                    'Sons of Anarchy': 200, 
                    'Sons of Guns': 404, 
                    'South Park': 60, 
                    'Southland': 75, 
                    'Spartacus': 424, 
                    'Spicks and Specks': 158, 
                    'Star Wars - The Clone Wars': 61, 
                    'Strike Back': 386, 
                    'Suburgatory': 406, 
                    'Suits': 367, 
                    'Supernatural': 62, 
                    'Survivor': 90, 
                    'Switched at Birth': 363, 
                    'Teen Wolf': 364, 
                    'Terra Nova': 374, 
                    'The Amazing Race': 122, 
                    'The Apprentice': 172, 
                    'The Apprentice UK': 173, 
                    'The Big Bang Theory': 5    , 
                    'The Big C': 290, 
                    'The Body Farm': 377, 
                    'The Borgias': 338, 
                    'The Cleveland Show': 224, 
                    'The Client List': 440, 
                    'The Closer': 14, 
                    'The Colbert Report': 15, 
                    'The Daily Show Nederlandse Editie': 82, 
                    'The Exes': 457, 
                    'The Fades': 392, 
                    'The Finder': 418, 
                    'The Firm': 416, 
                    'The Fixer': 206, 
                    'The Game': 412, 
                    'The Glades': 288, 
                    'The Good Wife': 208, 
                    'The Hour': 371, 
                    'The Increasingly Poor Decisions of Todd Margaret': 310, 
                    'The IT Crowd': 38, 
                    'The Killing': 347, 
                    'The Late Late Show with Craig Ferguson': 261, 
                    'The League': 238, 
                    'The Life & Times of Tim': 259, 
                    'The Listener': 156, 
                    'The Lying Game': 380, 
                    'The Marriage Ref': 267, 
                    'The Mentalist': 44, 
                    'The Middle': 227, 
                    'The Newsroom (2012)': 455, 
                    'The Nine Lives of Chloe King': 355, 
                    'The Office (US)': 50, 
                    'The Onion News Network': 346, 
                    'The Penguins of Madagascar': 96, 
                    'The Playboy Club': 390, 
                    'The Protector': 361, 
                    'The Ricky Gervais Show': 256, 
                    'The River': 428, 
                    'The Royal Bodyguard': 415, 
                    'The Sarah Jane Adventures': 234, 
                    'The Secret Circle': 369, 
                    'The Secret Life of the American Teenager': 149, 
                    'The Simpsons': 57, 
                    'The Soul Man': 459, 
                    'The Soup': 414, 
                    'The Tonight Show with Jay Leno': 263, 
                    'The Ultimate Fighter Live': 76, 
                    'The Universe': 199, 
                    'The Vampire Diaries': 205, 
                    'The Venture Bros.': 233, 
                    'The Voice (US)': 429, 
                    'The Walking Dead': 318, 
                    'The X Factor': 197, 
                    'ThunderCats (2011)': 365, 
                    'Top Chef': 100, 
                    'Top Gear': 117, 
                    'Top Gear Australia': 154, 
                    'Torchwood': 201, 
                    'Touch (2012)': 423, 
                    'Treme': 268, 
                    'Tron: Uprising': 449, 
                    'True Blood': 79, 
                    'Two and a Half Men': 63, 
                    'Ugly Americans': 264, 
                    'Underbelly': 65, 
                    'Undercover Boss': 258, 
                    'Unforgettable': 376, 
                    'Unsupervised': 433, 
                    'Up All Night': 366, 
                    'Veep': 443, 
                    'Wallander': 247, 
                    'Warehouse 13': 182, 
                    'Web Therapy': 357, 
                    'Weeds': 68, 
                    'White Collar': 236, 
                    'Whitney': 368, 
                    'Who Do You Think You Are?': 266, 
                    'Wild Boys': 385, 
                    'Wilfred (US)': 362, 
                    'Workaholics': 373, 
                    'You Have Been Watching': 195, 
                    }
            
            
        if showName in self.knownShows:
            return self.knownShows[showName]
        else:
            return None
    
    
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
            logger.log(u"Error trying to load EZRSS RSS feed: " + e, logger.ERROR)
            logger.log(u"RSS data: "+data, logger.DEBUG)
            return []
        
        results = []

        for curItem in items:
            
            (title, url) = self._get_title_and_url(curItem)
            
            if not title or not url:
                logger.log(u"The XML returned from the EZRSS RSS feed is incomplete, this result is unusable: "+data, logger.ERROR)
                continue
    
            results.append(curItem)

        return results
    
    def _get_season_search_strings(self, show, season=None):
    
        params = {}
    
        if not show:
            return params
        
        ShowRssId = self._getShowRssIdForShow(show.name)
        if ShowRssId:
            params['ShowRssId'] = ShowRssId
            return [params]
        
        if ATTEMPT_EXCEPTIONS_IF_NOT_KNOWN:
            for otherName in get_scene_exceptions(show.tvdbid):
                ShowRssId = self._getShowRssIdForShow(otherName)
                if ShowRssId:
                    params['ShowRssId'] = ShowRssId
                    return [params]
        
        logger.log(u"Show %s doesn't appear to be known to ShowRSS" % show.name, logger.MESSAGE)
        return []


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

        logger.log(u"Adding item from RSS to cache: "+title, logger.DEBUG)

        self._addCacheEntry(title, url)

provider = ShowRssProvider()