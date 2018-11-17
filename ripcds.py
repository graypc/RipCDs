#!/usr/bin/env python

from __future__ import unicode_literals
import musicbrainzngs
import sys
import json
import sys
import os
import datetime
import time
import argparse
import select
from subprocess import Popen, PIPE, STDOUT
from termios import tcflush, TCIOFLUSH

class Album:
    image = None

    def toString(self):
        return "Artist[" + self.artist + "] Title[" + self.title + \
                "] Tracks[" + str(self.tracks) + "]"

    def __init__(self, artist, title, tracks):
        self.artist = artist
        self.title = title
        self.tracks = tracks
        self.image = None

musicbrainzngs.set_useragent(
    "python-musicbrainzngs-example",
    "0.1",
    "https://github.com/alastair/python-musicbrainzngs/",
)

def getMusicBrainzReleases(discId):
    try:
        releases = musicbrainzngs.get_releases_by_discid(discId,
                includes=["recordings", "artists"])
        return releases

    except musicbrainzngs.ResponseError as err:
        if err.cause.code == 404:
            log("ERROR.  Disc not found")
        else:
            log("ERROR. Received bad response from the MB server")
    
    return None

def getMusicBrainzArt(release):
    try:
        image = musicbrainzngs.get_image_front(release["id"], size="250")
        return image

    except musicbrainzngs.ResponseError as err:
        if err.cause.code == 404:
            log("ERROR.  Image not found")
        else:
            log("ERROR. Received bad response from the MB server")

    return None

def processCdStub(cdStub):
    #print json.dumps(cdStub, indent = 2)
    tracks = {}
    num = 0
    for track in cdStub["track-list"]:
        num = num + 1
        #print json.dumps(track, indent = 2)
        tracks[int(num)] = track["title"]

    album = Album(
            cdStub["artist"],
            cdStub["title"],
            tracks)
    return album

def processDisc(disc):
    # Disc can have several duplicate releases for different countries
    # Set the default release to the first one
    release = disc["release-list"][0]

    # Search all releases for the one from USA
    for rel in disc["release-list"]:
        country = rel.get("country")
        if (not (country == None)):
            if country == "US":
                release = rel

    if release == None:
        log("ERROR.  Failed to find release")
        return None

    tracks = {}
    for track in release["medium-list"][0]["track-list"]:
        tracks[int(track["number"])] = track["recording"]["title"]

    album = Album(
            release["artist-credit"][0]["artist"]["sort-name"],
            release["title"],
            tracks)

    album.image = getMusicBrainzArt(release)
    return album

def getAlbumMeta(discId):
    log("Getting data for " + discId)

    releases = getMusicBrainzReleases(discId)
    
    if (releases == None):
        log("ERROR.  releases == None")
        return None

    #print json.dumps(releases, indent = 2)
    #return

    # Get the disc
    disc = releases.get("disc")

    if (not (disc == None)):
        return processDisc(disc)
    
    cdStub = releases.get("cdstub")

    if (not (cdStub == None)):
        return processCdStub(cdStub)

    log("ERROR.  Unknown sub type.")
    return None

def log(msg):
    print msg
    logFile = open("log.txt", "a")
    logFile.write(str(datetime.datetime.now()) + " " + msg + "\n")
    logFile.close()

def getMusicBrainzIdFromCD():
    cmd = ["cddainfo"]
    lines = runShellCommand(cmd, False).split("\n")
    key = "MusicBrainz disc ID : "
    for line in lines:
        if not line.find("No medium found") == -1:
            return ""

        # CD is present
        index = line.find(key)
        if not index == -1:
            return line[len(key):]

    # CD is present but does not contain ID
    log("ERROR.  Metadata not present.")
    return ""

def getNumTracksFromCD():
    cmd = ["cddainfo"]
    lines = runShellCommand(cmd, False).split("\n")
    
    lineNum = len(lines) - 1

    while (lineNum >= 0) :
        line = lines[lineNum]
        if (len(line)) :
            return line.split()[0]

        lineNum = lineNum - 1

    return 0

def runShellCommand(cmd, interruptable):
    p = Popen(cmd, shell=False, stdout=PIPE, stderr=STDOUT)

    if (interruptable):
        startTime = datetime.datetime.now()

        while (p.poll() is None):
            msg = "\rElapsed time --> " + str(datetime.datetime.now() - startTime) + \
                    " Hit <Enter> to skip this song"

            sys.stdout.write(msg)
            sys.stdout.flush()

            [i, o, e] = select.select([sys.stdin], [], [], 1)
            
            if (i):
                print i 
                p.kill()
                log("ERROR.  Interrupting process");
                break;

    out, err = p.communicate()
    tcflush(sys.stdin, TCIOFLUSH)
    if (err):
        log("ERROR runShellCommand().  " + err)
        return ""

    return out

def getAlbumManually(artist, album) :
    numTracks = getNumTracksFromCD()
    tracks = {}

    msg = str(numTracks) + " tracks on disc.  Provide names? [y/n]"
    reply = raw_input(msg)
    trackData = False
    if (reply == "y" or reply == "Y"):
        trackData = True

    for i in range(int(numTracks)) :
        if (trackData):
            tracks[i+1] = raw_input("Track " + str(i+1) + " name:")
        else:
            tracks[i+1] = ""

    return Album(artist, album, tracks)

def ripAlbum(destDir, album):
    log(album.toString())
    artistDir = destDir + "/" + album.artist
    albumDir = artistDir + "/" + album.title

    # Make a directory for the artist
    if (not os.path.isdir(artistDir)):
        log("Creating directory [" + artistDir + "]")
        os.mkdir(artistDir)

    # Make a directory for the album
    if (os.path.isdir(albumDir)):
        log("WARNING.  Duplicate album.  [" + album.artist +
                "] [" + album.title + "]")
        runShellCommand(["eject"], False)
        return
 
    log("Creating directory [" + albumDir + "]")
    os.mkdir(albumDir)
        
    # Sample command to rip tracks.
    # cdda2track -t mp3 --dir data/ --no-freedb --default --format "junk.mp3" 2
    for trackNum, trackTitle in album.tracks.iteritems():
        trackNumStr = str(trackNum)
        if len(trackNumStr) == 1:
            trackNumStr = "0" + trackNumStr

        title = trackNumStr + " - " + trackTitle + ".mp3"

        cmd = ["cdda2track", "-t", "mp3", "--dir", albumDir, "--no-freedb", 
                "--default", "--format", title , str(trackNum)]
        log(" ".join(cmd))
        out = runShellCommand(cmd, True)

    if (album.image == None):
        log("ERROR.  Covert art not available.")
    else:
        imageFile = open(albumDir + "/CoverArt", "wb")
        imageFile.write(bytearray(album.image))
        imageFile.close()

        # Add cover art to all mp3s in the directory.  Example
        # covertag -r --front-cover=data/Johnson\,\ Jack/In\ Between\ Dreams/CoverArt 
        #     data/Johnson\,\ Jack/In\ Between\ Dreams/*.mp3
        cmd = ["covertag", "-r", "--front-cover=" + albumDir + "/CoverArt",
                albumDir + "/*.mp3"]

        log(" ".join(cmd))
        out = runShellCommand(cmd, False)

    runShellCommand(["eject"], False)

if __name__ == '__main__':
    reload(sys)
    sys.setdefaultencoding("utf8")
    
    parser = argparse.ArgumentParser(description = 
            "Root directory to store albums.")

    parser.add_argument("--dir", required=True, 
            help = "Directory to store albums")
    parser.add_argument("--discId", required=False, 
            help = "Musicbranz discID.  If known")
    parser.add_argument("--artist", required=False, 
            help = "Manually provide the artist")
    parser.add_argument("--album", required=False, 
            help = "Manually provide the album")

    args = parser.parse_args()

    album = None

    if (args.artist or args.album) :
        album = getAlbumManually(args.artist, args.album)
        ripAlbum(args.dir, album)
        sys.exit(0)

    elif (args.discId) :
        album = getAlbumMeta(args.discId)
        ripAlbum(args.dir, album)
        sys.exit(0)

    while (True):
        time.sleep(1)

        musicBrainzId = getMusicBrainzIdFromCD()

        if (not musicBrainzId):
            runShellCommand(["eject"], False)
            continue

        album = getAlbumMeta(musicBrainzId)

        if (not album):
            runShellCommand(["eject"], False)
            continue

        ripAlbum(args.dir, album)
    
    sys.exit(0)
