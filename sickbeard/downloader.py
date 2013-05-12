'''
Created on Apr 24, 2013

@author: Dermot Buckley, dermot@buckley.ie
'''
from __future__ import with_statement # This isn't required in Python 2.6

import time
import os.path
import pickle
import hashlib
import threading

from sickbeard import logger
from sickbeard import version
from sickbeard import helpers
from sickbeard.exceptions import ex
from sickbeard.helpers import isMediaFile
from sickbeard import postProcessor
from sickbeard import exceptions
from sickbeard.tv import TVEpisode, TVShow
import sickbeard

LIBTORRENT_AVAILABLE = False

try:
    #http://www.rasterbar.com/products/libtorrent/manual.html
    import libtorrent as lt
    logger.log('libtorrent import succeeded, libtorrent is available', logger.MESSAGE)
    LIBTORRENT_AVAILABLE = True
except ImportError:
    logger.log('libtorrent import failed, functionality will not be available', logger.MESSAGE)
    
# the number of seconds we wait after adding a torrent to see signs of download beginning
TORRENT_START_WAIT_TIMEOUT_SECS = 90

# The actual running lt session.  Obtain it by calling _get_session() - which
# will create it if needed.
_lt_sess = None

# a list of running torrents, each entry being a dict with torrent properties.
running_torrents = []


def get_running_torrents():
    """
    This is just a public accessor for running_torrents.
    @return: (list)
    """
    global running_torrents
    return running_torrents



def download_from_torrent(torrent, postProcessingDone=False, start_time=None, key=None, episodes=[]):
    """
    Download the files from a magnet link or torrent url.
    Returns True if the download begins, and forks off a thread to complete the download.
    Note: This function will block until the download gives some indication that it
    has started correctly (or TORRENT_START_WAIT_TIMEOUT_SECS is reached).
    
    @param torrent: (string) url (http or https) to a torrent file, a raw torrent file, or a magnet link.
    @param postProcessingDone: (bool) If true, the torrent will be flagged as "already post processed".
    @param start_time: (int) Start time timestamp.  If None (the default), the current timestamp is used. 
    @param key: (string) Unique key to identify torrent.  Just used internally.  If none, a default is generated. 
    @param episodes: ([TVEpisode]) list of TVEpisode objects for which the download applies.
    @return: (bool) True if the download *starts*, False otherwise.
    """
    global running_torrents
    
    #logger.log(u'episodes: {0}'.format(repr(episodes)), logger.DEBUG)
    
    try:
        sess = _get_session()
        atp = {}    # add_torrent_params
        atp["save_path"] = _get_save_path(True)
        atp["storage_mode"] = lt.storage_mode_t.storage_mode_sparse
        atp["paused"] = False
        atp["auto_managed"] = True
        atp["duplicate_is_error"] = True
        have_torrentFile = False
        if torrent.startswith('magnet:') or torrent.startswith('http://') or torrent.startswith('https://'):
            logger.log(u'Adding torrent to session: {0}'.format(torrent), logger.DEBUG)
            atp["url"] = torrent
            name_to_use = None
            total_size_to_use = -1
        else:
            e = lt.bdecode(torrent)
            info = lt.torrent_info(e)
            name_to_use = info.name()
            total_size_to_use = info.total_size()
            logger.log(u'Adding torrent to session: {0}'.format(name_to_use), logger.DEBUG)
            have_torrentFile = True
                
            try:
                atp["resume_data"] = open(os.path.join(atp["save_path"], name_to_use + '.fastresume'), 'rb').read()
            except:
                pass
    
            atp["ti"] = info
        
        start_time = time.time()
        h = sess.add_torrent(atp)
    
        #handles.append(h)
        running_torrents.append({
            'lock': threading.Lock(),
            'name': name_to_use,
            'torrent': torrent,
            'key': md5(torrent) if key is None else key,
            'handle': h,
            'post_processed': postProcessingDone,
            'have_torrentFile': have_torrentFile,
            'start_time': time.time() if start_time is None else start_time,
            'status': 'added',
            'progress': -1.0,  # i.e. unknown
            'rate_down': -1,
            'rate_up': -1,
            'total_size': total_size_to_use,
            'ratio': 0.0,
            'paused': False,
            'error': None,
            'episodes': episodes,
        })
        running_torrent_ptr = running_torrents[len(running_torrents) - 1]
    
        h.set_max_connections(128)
        h.set_max_uploads(-1)
        
        startedDownload = False
        while not startedDownload:
            time.sleep(0.5)
            if h.has_metadata():
                s = h.status(0x0) # 0x0 because we don't want any of the optional info
                i = h.get_torrent_info()
                name = i.name()
                running_torrent_ptr['status'] = str(s.state)
                running_torrent_ptr['name'] = name
                running_torrent_ptr['total_size'] = i.total_size()
                running_torrent_ptr['paused'] = s.paused;
                running_torrent_ptr['error'] = s.error;
                if s.state in [lt.torrent_status.seeding, 
                               lt.torrent_status.downloading,
                               lt.torrent_status.finished, 
                               lt.torrent_status.downloading_metadata]:
                    logger.log(u'Torrent "{0}" has state "{1}" ({2}), interpreting as downloading'.format(name, s.state, repr(s.state)), 
                               logger.MESSAGE)
                    return True
            else:
                # no metadata?  Definitely not started yet then!
                pass
            
            # check for timeout
            if time.time() - start_time > TORRENT_START_WAIT_TIMEOUT_SECS:
                logger.log(u'Torrent has failed to start within timeout {0}secs.  Removing'.format(TORRENT_START_WAIT_TIMEOUT_SECS),
                           logger.WARNING)
                _remove_torrent_by_handle(h)
                return False
                
    except Exception, e:
        logger.log('Error trying to download via libtorrent: ' + ex(e), logger.ERROR)
        return False
    
def delete_torrent(key, deleteFilesToo=True):
    """
    Delete a running torrent by key.
    @return: (bool, string) Tuple with (success, errorMessage)
    """
    global running_torrents
    theEntry = next(d for d in running_torrents if d['key'] == key)
    if theEntry:
        _remove_torrent_by_handle(theEntry['handle'], deleteFilesToo)
        return (True, u'')
    else:
        return (False, u'Torrent not found')
    
def set_max_dl_speed(max_dl_speed):
    """
    Set the download rate limit for libtorrent if it's running
    @param max_dl_speed: integer.  Rate in kB/s 
    """
    sess = _get_session(False)
    if sess:
        _lt_sess.set_download_rate_limit(max_dl_speed * 1024)

def set_max_ul_speed(max_ul_speed):
    """
    Set the upload rate limit for libtorrent if it's running
    @param max_ul_speed: integer.  Rate in kB/s 
    """
    sess = _get_session(False)
    if sess:
        _lt_sess.set_upload_rate_limit(max_ul_speed * 1024)
    
def _get_session(createIfNeeded=True):
    global _lt_sess
    if _lt_sess is None and createIfNeeded:
        _lt_sess = lt.session()
        _lt_sess.set_download_rate_limit(sickbeard.LIBTORRENT_MAX_DL_SPEED * 1024)
        _lt_sess.set_upload_rate_limit(sickbeard.LIBTORRENT_MAX_UL_SPEED * 1024)
        
        settings = lt.session_settings()
        settings.user_agent = 'sickbeard_bricky-{0}/{1}'.format(version.SICKBEARD_VERSION.replace(' ', '-'), lt.version)
        settings.rate_limit_utp = True # seems this is rqd, otherwise uTP connections don't obey the rate limit
        
        settings.active_downloads = 8
        settings.active_seeds = 12
        settings.active_limit = 20
        
        _lt_sess.listen_on(6881, 6891)
        _lt_sess.set_settings(settings)
        _lt_sess.set_alert_mask(lt.alert.category_t.error_notification |
                                #lt.alert.category_t.port_mapping_notification |
                                lt.alert.category_t.storage_notification |
                                #lt.alert.category_t.tracker_notification |
                                lt.alert.category_t.status_notification |
                                lt.alert.category_t.performance_warning)
        
    return _lt_sess

def _get_save_path(ensureExists=False):
    """
    Get the save path for torrent data
    """
    pth = os.path.join(sickbeard.LIBTORRENT_WORKING_DIR, 'data')
    if ensureExists and not os.path.exists(pth):
            os.makedirs(pth)
    return pth

def _get_running_path(ensureExists=False):
    """
    Get the save path for running torrent info
    """
    pth = os.path.join(sickbeard.LIBTORRENT_WORKING_DIR, 'running')
    if ensureExists and not os.path.exists(pth):
            os.makedirs(pth)
    return pth

# def add_suffix(val):
#     prefix = ['B', 'kB', 'MB', 'GB', 'TB']
#     for i in range(len(prefix)):
#         if abs(val) < 1000:
#             if i == 0:
#                 return '%5.3g%s' % (val, prefix[i])
#             else:
#                 return '%4.3g%s' % (val, prefix[i])
#         val /= 1000
# 
#     return '%6.3gPB' % val

def md5(string):
    hasher = hashlib.md5()
    hasher.update(string)
    return hasher.hexdigest()

def _remove_torrent_by_handle(h, deleteFilesToo=True):
    global running_torrents
    sess = _get_session(False)
    if sess:
        theEntry = next(d for d in running_torrents if d['handle'] == h)
        running_torrents.remove(theEntry)
        try:
            fr_file = os.path.join(_get_save_path(),
                                   theEntry['handle'].get_torrent_info().name() + '.fastresume')
            os.remove(fr_file)
        except Exception:
            pass
        sess.remove_torrent(theEntry['handle'], 1 if deleteFilesToo else 0)
        
def _get_running_torrents_pickle_path(createDirsIfNeeded=False):
    torrent_save_dir = _get_running_path(createDirsIfNeeded)
    return os.path.join(torrent_save_dir, 'running_torrents.pickle')
        
def _load_saved_torrents(deleteSaveFile=True):
    torrent_save_file = _get_running_torrents_pickle_path(False)
    if os.path.isfile(torrent_save_file):
        try:
            data_from_pickle = pickle.load(open(torrent_save_file, "rb"))
            for td in data_from_pickle:
                if 'episodes' not in td: # older pickles won't have this
                    td['episodes'] = []
                tvEpObjs = []
                for ep in td['episodes']:
                    shw = helpers.findCertainShow(sickbeard.showList, ep['tvdbid'])
                    tvEpObjs.append(TVEpisode(show=shw, season=ep['season'], episode=ep['episode']))
                download_from_torrent(td['torrent'], 
                                      postProcessingDone=td['post_processed'],
                                      start_time=td['start_time'],
                                      key=td['key'],
                                      episodes=tvEpObjs)
        except Exception, e:
            logger.log(u'Failure while reloading running torrents: {0}'.format(ex(e)), logger.ERROR)
        if deleteSaveFile:
            os.remove(torrent_save_file)
    
def _save_running_torrents():
    global running_torrents
    if len(running_torrents):
        data_to_pickle = []
        for torrent_data in running_torrents:
            
            # we can't pick TVEpisode objects, so we just pickle the useful info
            # from the, namely the show, season, and episode.
            eps = []
            for ep in torrent_data['episodes']:
                eps.append({'tvdbid': ep.show.tvdbid, 'season': ep.season, 'episode': ep.episode })
            
            data_to_pickle.append({
                'torrent'           : torrent_data['torrent'],
                'post_processed'    : torrent_data['post_processed'],
                'start_time'        : torrent_data['start_time'],
                'key'               : torrent_data['key'],
                'episodes'          : eps,
            })
            #logger.log(repr(data_to_pickle), logger.DEBUG)
        torrent_save_file = _get_running_torrents_pickle_path(True)
        logger.log(u'Saving running torrents to "{0}"'.format(torrent_save_file), logger.DEBUG)
        pickle.dump(data_to_pickle, open(torrent_save_file, "wb"))


class TorrentProcessHandler():
    def __init__(self):
        self.shutDownImmediate = False
        self.loadedRunningTorrents = False
        self.amActive = False # just here to keep the scheduler class happy!
        self.lastTorrentStatusLogTS = 0 # timestamp of last log of torrent status
    
    def run(self):
        """
        Called every few seconds to handle any running/finished torrents
        """
        
        if not LIBTORRENT_AVAILABLE:
            return
        
        if not self.loadedRunningTorrents:
            torrent_save_file = _get_running_torrents_pickle_path(False)
            if os.path.isfile(torrent_save_file):
                logger.log(u'Saved torrents found in {0}, loading'.format(torrent_save_file), logger.DEBUG)
                _load_saved_torrents()
            
            self.loadedRunningTorrents = True    

        sess = _get_session(False)
        if sess is not None:
            while 1:
                a = sess.pop_alert()
                if not a: break
                
                if type(a) == str:
                    logger.log(u'{0}'.format(a), logger.DEBUG)
                else:
                    logger.log(u'({0}): {1}'.format(type(a).__name__, a.message()), logger.DEBUG)
                    
            logTorrentStatus = (time.time() - self.lastTorrentStatusLogTS) >= 600
                
            for torrent_data in running_torrents:
                if torrent_data['handle'].has_metadata():
                    ti = torrent_data['handle'].get_torrent_info()
                    name = ti.name()
                    torrent_data['name'] = name
                    torrent_data['total_size'] = ti.total_size()
                    
                    if not torrent_data['have_torrentFile']:
                        # if this was a magnet or url, and we now have downloaded the metadata
                        # for it, best to save it locally in case we need to resume
                        ti = torrent_data['handle'].get_torrent_info()
                        torrentFile = lt.create_torrent(ti)
                        torrent_data['torrent'] = lt.bencode(torrentFile.generate())
                        torrent_data['have_torrentFile'] = True
                        logger.log(u'Created torrent file for {0} as metadata d/l is now complete'.format(name), logger.DEBUG)

                else:
                    name = '-'
                    
                s = torrent_data['handle'].status()                    
                torrent_data['status'] = str(s.state)
                torrent_data['progress'] = s.progress
                torrent_data['rate_down'] = s.download_rate
                torrent_data['rate_up'] = s.upload_rate
                torrent_data['paused'] = s.paused;
                torrent_data['error'] = s.error;
                
                #currentRatio = 0.0 if s.total_download == 0 else float(s.total_upload)/float(s.total_download)
                currentRatio = 0.0 if s.all_time_download == 0 else float(s.all_time_upload)/float(s.all_time_download)
                torrent_data['ratio'] = currentRatio
                
                if s.state in [lt.torrent_status.seeding,
                               lt.torrent_status.finished]:
                    with torrent_data['lock']:
                        # this is the post-processing & removing code, so make sure that there's
                        # only one thread doing either here, as the two could easily interfere with
                        # one another
                        if not torrent_data['post_processed']:
                            # torrent has just completed download, so we need to do
                            # post-processing on it.
                            ti = torrent_data['handle'].get_torrent_info()
                            any_file_success = False
                            for f in ti.files():
                                fullpath = os.path.join(sickbeard.LIBTORRENT_WORKING_DIR, 'data', f.path)
                                logger.log(u'Post-processing "{0}"'.format(fullpath), logger.DEBUG)
                                if isMediaFile(fullpath):
                                    logger.log(u'this is a media file', logger.DEBUG)
                                    try:
                                        processor = postProcessor.PostProcessor(fullpath, name)
                                        if processor.process(forceKeepOriginalFiles=True):
                                            logger.log(u'Success post-processing "{0}"'.format(fullpath), logger.DEBUG)
                                            any_file_success = True
                                    except exceptions.PostProcessingFailed, e:
                                        logger.log(u'Failed post-processing file "{0}" with error "{1}"'.format(fullpath, ex(e)), 
                                                   logger.ERROR)
                                        
                            if not any_file_success:
                                logger.log(u'When post-processing the completed torrent {0}, no useful files were found.'.format(name), logger.ERROR)
                                
                            torrent_data['post_processed'] = True
                        else:
                            # post-processing has already been performed.  So we just 
                            # need to ensure check the ratio and delete the torrent
                            # if we're good.
                            if currentRatio >= sickbeard.LIBTORRENT_SEED_TO_RATIO:
                                logger.log(u'Torrent "{0}" has seeded to ratio {1}.  Removing it.'.format(name, currentRatio), logger.MESSAGE)
                                deleteFilesToo = True
                                if not torrent_data['post_processed']:
                                    logger.log(u'Torrent has not been post_processed.  Keeping files.', logger.MESSAGE)
                                    deleteFilesToo = False
                                _remove_torrent_by_handle(torrent_data['handle'], deleteFilesToo)
                            else:
                                if logTorrentStatus:
                                    self.lastTorrentStatusLogTS = time.time()
                                    logger.log(u'"{0}" seeding {1:.3f}'.format(name, currentRatio), logger.DEBUG)
                elif s.state == lt.torrent_status.downloading:
                    if logTorrentStatus:
                        self.lastTorrentStatusLogTS = time.time()
                        logger.log(u'"{0}" downloading {1:.2f}%'.format(name, s.progress * 100.0), logger.DEBUG)
                        
            if self.shutDownImmediate:
                # there's an immediate shutdown waiting to happen, save any running torrents
                # and get ready to stop
                logger.log(u"Torrent shutdown immediate", logger.DEBUG)
                sess.pause()
                for torrent_data in running_torrents:
                    h = torrent_data['handle']
                    if not h.is_valid() or not h.has_metadata():
                        continue
                    data = lt.bencode(torrent_data['handle'].write_resume_data())
                    save_path = _get_save_path(True)
                    tname = h.get_torrent_info().name()
                    logger.log(u'Saving fastresume data for "{0}"'.format(tname), logger.DEBUG)
                    open(os.path.join(save_path, tname + '.fastresume'), 'wb').write(data)
                
                _save_running_torrents()
                
                # We do this to encourage cleanup of the session (in particular
                # closing any open file handles).
                del sess
                _lt_sess = None
                
                # normally this wouldn't matter of course, because we'd be truly
                # shutting down, but often the case is that sickbeard is actually
                # restarting, so we don't benefit from the cleanup associated with
                # stopping the main thread.
                
