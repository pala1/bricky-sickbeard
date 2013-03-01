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
#
# @author: Dermot Buckley <dermot@buckley.ie>

import re
import subprocess
import threading
import sickbeard
import generic

from sickbeard import logger
from sickbeard import tvcache
from sickbeard.common import Quality
from sickbeard.helpers import searchDBForShow

def iplayerQualityToSbQuality(iplayer_q):
    """
    iplayer ref: http://beebhack.wikia.com/wiki/IPlayer_TV#Comparison_Table
    SB ref: https://code.google.com/p/sickbeard/wiki/QualitySettings
    
    @param iplayer_q: (string) quality, one of flashhd,flashvhigh,flashhigh,flashstd,flashnormal,flashlow,n95_wifi
    @return: (int) one of the sickbeard.common.Quality values 
    """
    if iplayer_q == 'flashhd':
        return Quality.HDWEBDL
    if iplayer_q == 'flashvhigh':
        return Quality.HDTV
    if iplayer_q == 'flashhigh':
        return Quality.SDTV
    else:
        # everything else is assumed to be SDTV (but is probably lower)
        return Quality.SDTV

def _snatchPid(pid, with_subs=True, out_dir=None):
    """
    Download a pid.
    This is a blocking call, so call in it's own thread (or somewhere that
    blocking doesn't matter), as this may take quite some time to run.
    
    @param pid: (string) pid to download
    @param with_subs: (bool) download subs also if available
    @param out_dir: (string) path to output dir.  Defaults to TV_DOWNLOAD_DIR 
    """
    
    if out_dir is None:
        out_dir = sickbeard.TV_DOWNLOAD_DIR
    
    cmd = [ sickbeard.IPLAYER_GETIPLAYER_PATH,
                '--get',
                '--pid ' + pid,
                '--nocopyright', 
                '--modes best',
                #'--subtitles',
                '--file-prefix "<nameshort>-<senum>-<pid>.<mode>"',
                '--output "' + out_dir + '"',
                ]
    
    if with_subs:
        cmd.append('--subtitles')
        
    cmd = " ".join(cmd) 
        
    logger.log(u"get_iplayer (cmd) = "+repr(cmd), logger.DEBUG)
        
    # we need a shell b/c it's a perl script and it will need to find the 
    # interpreter
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                         shell=True, universal_newlines=True) 
    #out, err = p.communicate()
    for line in iter(p.stdout.readline, ''):
        logger.log(u"RUNNING iPLAYER: "+line.rstrip(), logger.DEBUG)

    p.wait()
    
    return (p.stdout, p.stderr)

class IplayerProvider(generic.VODProvider):

    def __init__(self):
        generic.VODProvider.__init__(self, "iPlayer")
        self.supportsBacklog = False
        self.cache = IplayerCache(self)
        self.url = 'http://www.bbc.co.uk/iplayer'

    def isEnabled(self):
        return sickbeard.IPLAYER
    
    def downloadResult(self, result):
        """
        Overridden to handle iplayer snatched.
        The .url property of result should be an iplayer pid.
        """
        logger.log(u"Downloading a result from " + self.name+" at " + result.url)
        
        target_dir = sickbeard.TV_DOWNLOAD_DIR
        
        t = threading.Thread(target=_snatchPid, args=(result.url,True,target_dir))
        t.start() 
        
        return True # for now we assume success

class IplayerCache(tvcache.TVCache):

    def __init__(self, provider):
        tvcache.TVCache.__init__(self, provider)
        self.minTime = 15

    def updateCache(self):

        if not self.shouldUpdate():
            return
        
        FIELD_SEP = '|||' 
        
        fieldnames = [ 'pid', 'index', 'name', 'seriesnum', 'episode', 
                       'episodenum', 'versions', 'type',
                     # 'desc',  'thumbnail', 
                     #'web', 'channel', 'categories',  'duration', 
                     #  'available', 'timeadded' 
                     ]
        
        cmd = [ sickbeard.IPLAYER_GETIPLAYER_PATH,
                '--listformat',
                '"<' + (('>' + FIELD_SEP + '<').join(fieldnames)) + '>"', 
                '--nocopyright', 
                '--since 24', # only shows added in the last 24 hours    
                ]
        
        cmd = " ".join(cmd) # not quite sure why, but Popen doesn't like the list
        
        logger.log(u"get_iplayer (cmd) = "+repr(cmd), logger.DEBUG)
        
        # we need a shell b/c it's a perl script and it will need to find the 
        # interpreter
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                             shell=True, universal_newlines=True) 
        out, err = p.communicate()
        
        #logger.log(u"get_iplayer (out) = "+repr(out), logger.DEBUG)
        logger.log(u"get_iplayer (err) = "+repr(err), logger.DEBUG)
        
        logger.log(u"Clearing "+self.provider.name+" cache and updating with new information")
        self._clearCache()
        
        for line in out.splitlines():
            #logger.log(u"Got line: "+repr(line), logger.DEBUG)
            fields = line.split(FIELD_SEP)
            
            if len(fields) != len(fieldnames):
                logger.log(u"Ignoring line '%s', it has the wrong number of fields"%line, logger.DEBUG)
                continue
            
            fkeyed = dict((fieldname, fields[fieldnames.index(fieldname)]) for fieldname in fieldnames)
            
            # for now we ignore anything that doesn't have an episodenum (yes, we'll miss ABD b/c of this)
            if fkeyed['episodenum'] is '':
                continue
            
            # if the seriesnum is blank, make is series 1 (that's how tvdb works)
            if fkeyed['seriesnum'] is '':
                fkeyed['seriesnum'] = '1'
                
            # often the 'name' will have the series number tagged onto the end
            match = re.match('^(?P<showname>.*): Series ' + fkeyed['seriesnum'] + '$', fkeyed['name'], re.IGNORECASE)
            if match:
                fkeyed['name'] = match.group('showname')
                
            logger.log(repr(fkeyed), logger.DEBUG)
            
            fakeFilename = u'%s S%sE%s - %s' % (fkeyed['name'], fkeyed['seriesnum'], fkeyed['episodenum'], fkeyed['episode'])
            fakeUrl = fkeyed['pid']
            
            # is this one of the shows in the db?
            #fromDb = searchDBForShow(fkeyed['name'])
            #if fromDb:
            #    (tvdb_id, show_name) = fromDb
            
            # for now, let's just pretend everything is HD
            qual = Quality.HDWEBDL
            
            logger.log(u"Adding item from iPlayer to cache: "+fakeFilename, logger.DEBUG)
            self._addCacheEntry(name=fakeFilename, url=fakeUrl, season=int(fkeyed['seriesnum']),
                                episodes=[int(fkeyed['episodenum'])], quality=qual)
            
        self.setLastUpdate()  # record the feed as being updated

provider = IplayerProvider()
