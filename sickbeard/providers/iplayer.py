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
import tempfile
import os
import glob
import shutil

import sickbeard
import generic

from sickbeard import logger
from sickbeard import tvcache
from sickbeard.common import Quality
from sickbeard.helpers import searchDBForShow, listMediaFiles, isMediaFile
from sickbeard.processTV import processDir
from sickbeard.name_parser.parser import NameParser

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
    if iplayer_q in ('flashhigh', 'iphone', 'flashlow', 'flashstd', 'flashnormal', 'n95_wifi', 'n95_3g'):
        return Quality.SDTV
    else:
        # everything else is unknown for now
        return Quality.UNKNOWN
    
def iplayerQualityToSbQualityString(iplayer_q):
    """
    Given an iPlayer quality, returns a string which SB will thing is about the same quality.
    (per rules in sickbeard.common.Quality.nameQuality)
    """
    if iplayer_q == 'flashhd':
        return '720p.web.dl'
    if iplayer_q == 'flashvhigh':
        return 'hr.ws.pdtv.x264'
    if iplayer_q in ('flashhigh', 'iphone', 'flashlow', 'flashstd', 'flashnormal', 'n95_wifi', 'n95_3g'):
        return 'HDTV.XviD'
    else:
        return iplayer_q

def _downloadPid(pid, with_subs=True, with_metadata=True):
    """
    Download a pid.
    This is a blocking call, so call in it's own thread (or somewhere that
    blocking doesn't matter), as this may take quite some time to run.
    
    @param pid: (string) pid to download
    @param with_subs: (bool) download subs also if available
    @param with_metadata: (bool) download xbmc metadata 
    """
        
    tmp_dir = tempfile.mkdtemp()
    
    cmd = [ sickbeard.IPLAYER_GETIPLAYER_PATH,
                '--get',
                '--pid=' + pid,
                '--nocopyright', 
                '--attempts=10',
                '--modes=best',
                '--force',  # stop complaints about already being downloaded
                #'--subtitles',
                '--file-prefix="<nameshort>-<senum>-<pid>.<mode>"',
                '--output="' + tmp_dir + '"',   # we save to tmp_dir first
                ]
    
    if with_subs:
        cmd.append('--subtitles')
    
    if with_metadata:
        cmd.append('--metadata=xbmc')
        
    cmd = " ".join(cmd) 
        
    logger.log(u"get_iplayer (cmd) = "+repr(cmd), logger.DEBUG)
        
    # we need a shell b/c it's a perl script and it will need to find the 
    # interpreter
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                         shell=True, universal_newlines=True) 

    while p.poll() is None:
        line = p.stdout.readline()
        if line:
            logger.log(u"RUNNING iPLAYER: "+line.rstrip(), logger.DEBUG)
    
    logger.log(u"RUNNING iPLAYER: process has ended, returncode was " + 
               repr(p.returncode) , logger.DEBUG)
    
    # We will need to rename some of the files in the folder to ensure that
    # sb is comfortable with them.
    videoFiles = listMediaFiles(tmp_dir)
    for videoFile in videoFiles:
        filePrefix, fileExt = os.path.splitext(videoFile)
        if fileExt and fileExt[0] == '.': 
            fileExt = fileExt[1:]
        
        # split again to get the quality
        filePrePrefix, fileQuality = os.path.splitext(filePrefix)   
        if fileQuality and fileQuality[0] == '.': 
            fileQuality = fileQuality[1:]   
        qual_str = iplayerQualityToSbQualityString(fileQuality)
        
        # reassemble the filename again, with new quality
        newFilePrefix = filePrePrefix + '.' + qual_str
        newFileName = newFilePrefix + '.' + fileExt
        
        if newFileName != videoFile:    # just in case!
            logger.log('Renaming {0} to {1}'.format(videoFile, newFileName), logger.DEBUG)
            os.rename(videoFile, newFileName)
            
            # Also need to rename any associated files (nfo and srt)
            for otherFile in glob.glob(newFilePrefix + '.*'):
                if otherFile == newFileName:
                    continue
                otherFilePrefix, otherFileExt = os.path.splitext(otherFile)
                newOtherFile = newFilePrefix + otherFileExt
                logger.log('Renaming {0} to {1}'.format(otherFile, newOtherFile), logger.DEBUG)
                os.rename(otherFile, newOtherFile)
            
    
    # Ok, we're done with *our* post-processing, so let SB do its own.
    processResult = processDir(tmp_dir)
    logger.log(u"processDir returned " + processResult , logger.DEBUG)
    
    files_remaining = os.listdir(tmp_dir)
    can_delete = True
    for filename in files_remaining:
        fullFilePath = os.path.join(tmp_dir, filename)
        isVideo = isMediaFile(fullFilePath)
        if isVideo:
            can_delete = False # keep the folder - something prob went wrong
            logger.log('Found a media file after processing, something probably went wrong: ' + fullFilePath, logger.MESSAGE)
        else:
            logger.log('Extra file left over (will be deleted if no media found): ' + fullFilePath, logger.DEBUG)
    
    # tidy up - delete our temp dir

    if can_delete:
        logger.log('Removing temp dir: ' + tmp_dir, logger.DEBUG)
        shutil.rmtree(tmp_dir)
            

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
        Overridden to handle iplayer snatch.
        The .url property of result should be an iplayer pid.
        """
        logger.log(u"Downloading a result from " + self.name+" at " + result.url)
        
        t = threading.Thread(target=_downloadPid, args=(result.url,True,True))
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
                       'categories',
                     # 'desc',  'thumbnail', 
                     #'web', 'channel', 'categories',  'duration', 
                     #  'available', 'timeadded' 
                     ]
        
        cmd = [ sickbeard.IPLAYER_GETIPLAYER_PATH,
                '--listformat',
                '"<' + (('>' + FIELD_SEP + '<').join(fieldnames)) + '>"', 
                '--nocopyright', 
                #'--since 24', # only shows added in the last 24 hours    
                ]
        
        cmd = " ".join(cmd) # not quite sure why, but Popen doesn't like the list
        
        logger.log(u"get_iplayer (cmd) = "+repr(cmd), logger.DEBUG)
        
        # we need a shell b/c it's a perl script and it will need to find the 
        # interpreter
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                             shell=True, universal_newlines=True) 
        out, err = p.communicate()
        
        #logger.log(u"get_iplayer (out) = "+repr(out), logger.DEBUG)
        logger.log(u"get_iplayer (err) = "+repr(err), logger.DEBUG)
        
        logger.log(u"Clearing "+self.provider.name+" cache and updating with new information")
        self._clearCache()
        
        for line in out.splitlines():
            line = line.decode('utf-8')
            logger.log(u"Got line: "+repr(line), logger.DEBUG)
            fields = line.split(FIELD_SEP)
            
            if len(fields) != len(fieldnames):
                logger.log(u"Ignoring line '%s', it has the wrong number of fields"%line, logger.DEBUG)
                continue
            
            fkeyed = dict((fieldname, fields[fieldnames.index(fieldname)]) for fieldname in fieldnames)
            
            # for now we ignore anything that doesn't have an episodenum (yes, we'll miss ABD b/c of this)
            if fkeyed['episodenum'] is u'':
                continue
            
            # if the seriesnum is blank, make is series 1 (that's how tvdb works)
            if fkeyed['seriesnum'] is u'':
                fkeyed['seriesnum'] = u'1'
                
            # often the 'name' will have the series number tagged onto the end
            match = re.match('^(?P<showname>.*): Series ' + fkeyed['seriesnum'] + '$', fkeyed['name'], re.IGNORECASE)
            if match:
                fkeyed['name'] = match.group('showname')
                
            logger.log(repr(fkeyed), logger.DEBUG)
            
            fakeFilename = u'%s S%sE%s - %s' % (fkeyed['name'], fkeyed['seriesnum'], fkeyed['episodenum'], fkeyed['episode'])
            fakeUrl = fkeyed['pid']
            
            # Sometimes pid is preceeded with 'Added: ', if so we remove it
            if fakeUrl.startswith(u'Added: '):
                fakeUrl = fakeUrl[7:]
            
            # is this one of the shows in the db?
            #fromDb = searchDBForShow(fkeyed['name'])
            #if fromDb:
            #    (tvdb_id, show_name) = fromDb
            
            # for now, let's just pretend everything is HD
            #qual = Quality.HDWEBDL
            
            # it looks like anything available in HD has 'HD' in the categories.
            # so use that as our quality flag
            cats = fkeyed['categories'].split(',')
            if u'HD' in cats:
                qual = Quality.HDWEBDL
            else:
                qual = Quality.SDTV
                
            # get the tvdb_id also (SB has some trouble identifying the series here otherwise)
            tvdb_id = NameParser.series_name_to_tvdb_id(fkeyed['name'])
            
            logger.log(u"Adding item from iPlayer to cache: "+fakeFilename, logger.DEBUG)
            self._addCacheEntry(name=fakeFilename, url=fakeUrl, season=int(fkeyed['seriesnum']),
                                episodes=[int(fkeyed['episodenum'])], quality=qual,
                                tvdb_id=tvdb_id)
            
        self.setLastUpdate()  # record the feed as being updated

provider = IplayerProvider()
