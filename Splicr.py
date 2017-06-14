#!/usr/bin/env python3

from flask import Flask
from flask import render_template, url_for, redirect
from flask_uuid import FlaskUUID

from functools import partial

import json
import urllib
import sys
import os

# Youtube API
from apiclient.discovery import build
from apiclient.errors import HttpError
from oauth2client.tools import argparser

GA_TRACKING_ID = os.environ['GA_TRACKING_ID']


DEVELOPER_KEY = os.environ['YOUTUBE_KEY']
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

render = partial(render_template, GA_TRACKING_ID=GA_TRACKING_ID)

app = Flask(__name__)
FlaskUUID(app)

@app.route('/')
def index():
    return render('index.html')

@app.route('/search/album')
@app.route('/search/album/<terms>')
def album_search(terms=None):
    if terms is None:
        return redirect(url_for('index'))

    terms = urllib.parse.unquote(terms)
    albums = MusicBrainz.album_search(terms)
    return render('album-search.html', terms=terms, albums=albums)

@app.route('/search/artist')
@app.route('/search/artist/<terms>')
def artist_search(terms=None):
    if terms is None:
        return redirect(url_for('index'))

    terms = urllib.parse.unquote(terms)
    artists = MusicBrainz.artist_search(terms)
    return render('artist-search.html', terms=terms, artists=artists)

@app.route('/album')
@app.route('/album/<uuid:uuid>')
def album(uuid=None):
    if uuid is None:
        return redirect(url_for('index'))

    album = Album.get(uuid)
    return render('album.html', album=album,
                  ytid=yt_lucky(album.artist + ' ' + album.tracks[0].title))


@app.route('/artist')
@app.route('/artist/<uuid:uuid>')
def artist(uuid=None):
    if uuid is None:
        return redirect(url_for('index'))
    artist = Artist.get(uuid)
    return render('artist.html', artist=artist)

@app.route('/track')
@app.route('/track/<uuid:uuid>')
def track(uuid=None):
    if uuid is None:
        return redirect(url_for('index'))

    track = Track.get(uuid)
    return render('track.html', track=track,
                           ytid=yt_lucky(track.artist + ' ' + track.title))

@app.route('/ytid')
@app.route('/ytid/<uuid:uuid>')
def ytid(uuid=None):
    if uuid is None:
        return redirect(url_for('index'))

    track = Track.get(uuid)
    return yt_lucky(track.artist + ' ' + track.title)

#
# Musicbrainz fns and class definitions

class Artist:
    '''MusicBrainz Artists and Associated Albums'''

    def __init__(self, uuid):
        self.uuid = uuid
        self.asin = ''
        self.name = ''
        self.albums = []

    @staticmethod
    def get(uuid):
        MB_FMT = 'http://musicbrainz.org/ws/2/artist/%s?inc=releases&fmt=json&type=album|ep'
        response      = urllib.request.urlopen( MB_FMT % uuid )
        response_json = json.loads(response.read().decode('utf-8')) # FIXME encoding?

        artist = Artist(uuid)
        artist.name  = response_json['name']

        for release in response_json['releases']:
            artist.albums.append({ 'uuid' : release['id'],
                                   'title' : release['title']} )

        return artist

        
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

class MusicBrainz:
    @staticmethod
    def album_search(terms):
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
            skip = False
            album = {}
            album['score'] = release['score']
            album['title'] = release['title']
            album['uuid']  = release['id']
            album['artist'] = release['artist-credit'][0]['artist']['name']
            album['artist_uuid'] = release['artist-credit'][0]['artist']['id']
        
            # skip albums we already have, for more presentable search results.
            for a in albums:
                if a['artist'] == album['artist'] and a['title'] == album['artist']:
                    skip = True
            if not skip:
                albums.append(album)

        return albums

    @staticmethod
    def artist_search(terms):
        '''Returns a list of dicts representing mbrainz releases.
        score <- search relevance
        name  <- artist name
        uuid  <- mbrainz uuid'''

        terms  = urllib.parse.quote(terms)
        MB_FMT = 'http://musicbrainz.org/ws/2/artist/?query=%s&fmt=json'
        response      = urllib.request.urlopen( MB_FMT % terms )
        response_json = json.loads(response.read().decode('utf-8')) # FIXME encoding?

        artists = []
        for a in response_json['artists']:
            skip = False
            artist = {}
            artist['score'] = a['score']
            artist['name'] = a['name']
            artist['uuid']  = a['id']

            # skip albums we already have, for more presentable search results.
            #for a in albums:
            #    if a['artist'] == album['artist'] and a['title'] == album['artist']:
            #        skip = True
            #if not skip:
            #    albums.append(album)
            artists.append(artist)
            
        return artists




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
