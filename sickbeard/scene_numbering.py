'''
Created on Sep 20, 2012

@author: dermot
'''

from sickbeard import logger
from sickbeard import db

_schema_created = False
def _check_for_schema():
    global _schema_created
    if not _schema_created:
        myDB = db.DBConnection()
        myDB.action('CREATE TABLE if not exists scene_numbering (tvdb_id INTEGER KEY, season INTEGER, episode INTEGER, scene_season INTEGER, scene_episode)')
        _schema_created = True
        
        
def get_scene_numbering(tvdb_id, season, episode):
    """
    Returns a tuple, (season, episode), with the scene numbering (if there is one),
    otherwise returns the tvdb numbering.
    (so the return values will always be set)
    """
    _check_for_schema()
    myDB = db.DBConnection()
        
    rows = myDB.select("SELECT scene_season, scene_episode FROM scene_numbering WHERE tvdb_id = ? and season = ? and episode = ?", [tvdb_id, season, episode])
    if rows:
        return (int(rows[0]["scene_season"]), int(rows[0]["scene_episode"]))
    else:
        return (season, episode)
    
def get_scene_numbering_for_show(tvdb_id):
    """
    Returns a dict of (season, episode) : (sceneSeason, sceneEpisode) mappings
    for an entire show.  Both the keys and value of the dict are tuples.
    Will be empty if there are no scene numbers set
    """
    _check_for_schema()
    myDB = db.DBConnection()
        
    rows = myDB.select('''SELECT season, episode, scene_season, scene_episode 
                        FROM scene_numbering WHERE tvdb_id = ?
                        ORDER BY season, episode''', [tvdb_id])
    result = {}
    for row in rows:
        result[(int(row['season']), int(row['episode']))] = (int(row['scene_season']), int(row['scene_episode']))
        
    return result
    
def set_scene_numbering(tvdb_id, season, episode, sceneSeason=None, sceneEpisode=None):
    """
    Set scene numbering for a season/episode.
    To clear the scene numbering, leave both sceneSeason and sceneEpisode as None.
    
    """
    _check_for_schema()
    myDB = db.DBConnection()
    
    # sanity
    if sceneSeason == None: sceneSeason = season
    if sceneEpisode == None: sceneEpisode = episode
    
    # delete any existing record first
    myDB.action('DELETE FROM scene_numbering where tvdb_id = ? and season = ? and episode = ?', [tvdb_id, season, episode])
    
    # now, if the new numbering is not the default, we save a new record
    if season != sceneSeason or episode != sceneEpisode:
        myDB.action("INSERT INTO scene_numbering (tvdb_id, season, episode, scene_season, scene_episode) VALUES (?,?,?,?,?)", [tvdb_id, season, episode, sceneSeason, sceneEpisode])
            