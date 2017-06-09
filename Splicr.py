#!/usr/bin/env python3

from flask import Flask
from flask import render_template, url_for, redirect
from flask_uuid import FlaskUUID

import json
import urllib
import sys
import os

# Youtube API
from apiclient.discovery import build
from apiclient.errors import HttpError
from oauth2client.tools import argparser

DEVELOPER_KEY = os.environ['YOUTUBE_KEY']
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

app = Flask(__name__)
FlaskUUID(app)

#
# App route definitions. (Entrypoints.)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search')
@app.route('/search/<terms>')
def search(terms=None):
    if terms is None:
        return redirect(url_for('index'))

    terms = urllib.parse.unquote(terms)
    albums = mb_search(terms)
    return render_template('search.html', terms=terms, albums=albums)

@app.route('/album')
@app.route('/album/<uuid:uuid>')
def album(uuid=None):
    if uuid is None:
        return redirect(url_for('index'))

    album = Album.get(uuid)
    return render_template('album.html', album=album,
                           ytid=yt_lucky(album.artist + ' ' + album.tracks[0].title))
@app.route('/track')
@app.route('/track/<uuid:uuid>')
def track(uuid=None):
    if uuid is None:
        return redirect(url_for('index'))

    track = Track.get(uuid)
    return render_template('track.html', track=track,
                           ytid=yt_lucky(track.artist + ' ' + track.title))

@app.route('/ytid')
@app.route('/ytid/<string:terms>')
def ytid(terms=None):
    if terms is None:
        return redirect(url_for('index'))

    terms = urllib.parse.unquote(terms)
    return json.dumps({'ytid' : yt_lucky(terms)})


#
# Musicbrainz fns and class definitions


class Album:
    '''Musicbrainz Album (release)'''

    def __init__(self, uuid):
        self.uuid   = uuid
        self.asin   = ''
        self.title  = ''
        self.artist = '' # problematic (think: compilations)
        self.tracks = []

        # These relate to musicbrainz search.
        self.score = ''
        self.terms = ''

    @staticmethod
    def get(uuid):

        MB_FMT = 'http://musicbrainz.org/ws/2/release/%s?inc=recordings&fmt=json'
        response      = urllib.request.urlopen( MB_FMT % uuid )
        response_json = json.loads(response.read().decode('utf-8')) # FIXME encoding?

        album = Album(uuid)
        album.title  = response_json['title']
        album.asin   = response_json['asin']
        album.artist = ''

        for medium in response_json['media']:
            for track in medium['tracks']:
                album.tracks.append(Track(track['recording']['id'],
                                          title=track['title']))

        return album

class Track:
    '''Musicbrainz Track (recording)'''
    def __init__(self, uuid, asin='', artist='', title=''):
        self.uuid   = uuid
        self.asin   = asin
        self.title  = title
        self.artist = artist

    @staticmethod
    def get(uuid):

        MB_FMT = 'http://musicbrainz.org/ws/2/recording/%s?inc=artist-credits&fmt=json'
        print(MB_FMT % uuid, file=sys.stderr)
        response      = urllib.request.urlopen( MB_FMT % uuid )
        response_json = json.loads(response.read().decode('utf-8')) # FIXME encoding?

        track       = Track(uuid)
        track.title = response_json['title']

        credits     = response_json['artist-credit']
        for credit in credits:
            if len(track.artist) == 0:
                track.artist = credit['artist']['name'] # FIXME just one for now.

        return track


def mb_search(terms):
    '''Returns a list of dicts representing mbrainz releases.
    score <- search relevance
    title <- release title
    uuid  <- mbrainz uuid'''

    terms  = urllib.parse.quote(terms)
    MB_FMT = 'http://musicbrainz.org/ws/2/release/?query=%s&fmt=json&type=album|ep'
    response      = urllib.request.urlopen( MB_FMT % terms )
    response_json = json.loads(response.read().decode('utf-8')) # FIXME encoding?

    albums = []
    for release in response_json['releases']:
        album = {}
        album['score'] = release['score']
        album['title'] = release['title']
        album['uuid']  = release['id']
        albums.append(album)

    return albums

#
# Youtube Fns

def yt_lucky(terms=None):
    '''Returns the youtube video id (eg: "VQbqeLTMre8") of the
    top search result for terms'''
    youtube = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
                    developerKey=DEVELOPER_KEY)

    response = youtube.search().list(
        q=terms,
        part="id,snippet",
        maxResults=20
    ).execute()

    ytid = ''
    for result in response.get("items", []):
        if result["id"]["kind"] == "youtube#video":
            return result["id"]["videoId"]

if __name__ == '__main__': app.run()
