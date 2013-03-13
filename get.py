#!/usr/bin/python

import os
import json
import urllib
import sys
import collections
import dateutil.parser
import requests
import subprocess
import httplib
import sqlite3
import datetime
import scraperwiki

from secrets import *

# Make sure you install this version of "twitter":
# http://pypi.python.org/pypi/twitter
# http://mike.verdone.ca/twitter/
# https://github.com/sixohsix/twitter
import twitter

#########################################################################
# Authentication to Twitter

# This is designed to, when good, be submitted as a patch to add to twitter.oauth_dance (which
# currently only has a function for PIN authentication, not redirect)
from twitter.api import Twitter
from twitter.oauth import OAuth, write_token_file, read_token_file
from twitter.oauth_dance import parse_oauth_tokens
def oauth_url_dance(consumer_key, consumer_secret, callback_url, oauth_verifier, pre_verify_token_filename, verified_token_filename):
    # Verification happens in two stages...

    # 1) If we haven't done a pre-verification yet... Then we get credentials from Twitter
    # that will be used to sign our redirect to them, find the redirect, and instruct the Javascript
    # that called us to do the redirect.
    if not os.path.exists(CREDS_PRE_VERIFIY):
        twitter = Twitter(auth=OAuth('', '', consumer_key, consumer_secret), format='', api_version=None)
        oauth_token, oauth_token_secret = parse_oauth_tokens(twitter.oauth.request_token(oauth_callback = callback_url))
        write_token_file(pre_verify_token_filename, oauth_token, oauth_token_secret)

        oauth_url = 'https://api.twitter.com/oauth/authorize?' + urllib.urlencode({ 'oauth_token': oauth_token })
        return oauth_url

    # 2) We've done pre-verification, hopefully the user has authed us in Twitter
    # and we've been redirected to. Check we are and ask for the permanent tokens.
    oauth_token, oauth_token_secret = read_token_file(CREDS_PRE_VERIFIY)
    twitter = Twitter(auth=OAuth( oauth_token, oauth_token_secret, consumer_key, consumer_secret), format='', api_version=None)
    oauth_token, oauth_token_secret = parse_oauth_tokens(twitter.oauth.access_token(oauth_verifier=oauth_verifier))
    write_token_file(verified_token_filename, oauth_token, oauth_token_secret)
    return oauth_token, oauth_token_secret


def do_tool_oauth():
    if not os.path.exists(CREDS_VERIFIED):
        if len(sys.argv) < 3:
            result = "need-oauth"
        else:
            (callback_url, oauth_verifier) = (sys.argv[1], sys.argv[2])
            result = oauth_url_dance(CONSUMER_KEY, CONSUMER_SECRET, callback_url, oauth_verifier, CREDS_PRE_VERIFIY, CREDS_VERIFIED)
        # a string means a URL for a redirect (otherwise we get a tuple back with auth tokens in)
        if type(result) == str:
            set_status_and_exit('auth-redirect', 'error', 'Permission needed from Twitter', { 'url': result } )

    oauth_token, oauth_token_secret = read_token_file(CREDS_VERIFIED)
    tw = twitter.Twitter(auth=twitter.OAuth( oauth_token, oauth_token_secret, CONSUMER_KEY, CONSUMER_SECRET))
    return tw

#########################################################################
# Helper functions

# Stores one Twitter user in the ScraperWiki database
def save_tweet(tweet, table_name):
    data = collections.OrderedDict()

    data['id'] = tweet['id']
    data['tweet_url'] = "https://twitter.com/" + tweet['user']['screen_name'] + "/status/" + str(tweet['id'])
    data['created_at'] = dateutil.parser.parse(tweet['created_at'])

    data['text'] = tweet['text']
    data['lang'] = tweet['lang']

    data['retweet_count'] = tweet['retweet_count']
    # favorites count?
    # conversation thread length?

    data['screen_name'] = tweet['user']['screen_name']
    data['in_reply_to_screen_name'] = tweet['in_reply_to_screen_name']
    data['in_reply_to_status_id'] = tweet['in_reply_to_status_id']

    try:
        data['lat'] = tweet['geo']['coordinates'][0]
        data['lng'] = tweet['geo']['coordinates'][1]
    except:
        pass

    # Other ideas:
    # first URL from entities
    # first user mention from entities
    # first hash tag from entities
    # first media (twitpic) url from entities (media_url_https)

    scraperwiki.sqlite.save(['id'], data, table_name=table_name)

# Afer detecting an auth failed error mid work, call this
def clear_auth_and_restart():
    # remove auth files and respawn
    try:
        os.remove(CREDS_PRE_VERIFIY)
        os.remove(CREDS_VERIFIED)
    except OSError:
        # don't worry if the files aren't there
        pass
    subprocess.call(sys.argv)
    sys.exit()

# Signal back to the calling Javascript, to the database, and custard's status API, our status
def set_status_and_exit(status, typ, message, extra = {}):
    extra['status'] = status
    print json.dumps(extra)

    requests.post("https://x.scraperwiki.com/api/status", data={'type':typ, 'message':message})

    data = { 'id': 'tweets', 'current_status': status }
    scraperwiki.sqlite.save(['id'], data, table_name='status')

    sys.exit()

#########################################################################
# Main code

pages_got = 0
try:
    # Parameters to this command vary:
    #   a. None: try and scrape Twitter followers
    #   b. callback_url oauth_verifier: have just come back from Twitter with these oauth tokens
    #   c. "clean-slate": wipe database and start again
    if len(sys.argv) > 1 and sys.argv[1] == 'clean-slate':
        scraperwiki.sqlite.execute("drop table if exists tweets")
        scraperwiki.sqlite.execute("drop table if exists status")
        os.system("crontab -r >/dev/null 2>&1")
        set_status_and_exit('clean-slate', 'error', 'No query set')
        sys.exit()

    # Make the tweets table *first* with dumb data, calling DumpTruck directly,
    # so it appears before the status one in the list
    scraperwiki.sqlite.dt.create_table({'id': 1}, 'tweets')

    # Get query we're working on from file we store it in
    query_terms = open("query.txt").read().strip()

    # Connect to Twitter
    tw = do_tool_oauth()

    # Things basically working, so make sure we run again
    # os.system("crontab tool/crontab")

    # Get Tweets
    results = tw.search.tweets(q=query_terms)
    for tweet in results['statuses']:
        #print tweet
        save_tweet(tweet, 'tweets')
    #print tw.application.rate_limit_status()

except twitter.api.TwitterHTTPError, e:
    print e
    if "Twitter sent status 401 for URL" in str(e):
        clear_auth_and_restart()

    # https://dev.twitter.com/docs/error-codes-responses
    obj = json.loads(e.response_data)
    code = obj['errors'][0]['code'] 
    # authentication failure
    if (code in [32, 89]):
        clear_auth_and_restart()
    # rate limit exceeded
    if code == 34:
        set_status_and_exit('not-there', 'error', 'User not on Twitter')
    if code == 88:
        # provided we got at least one page, rate limit isn't an error but expected
        if pages_got == 0:
            set_status_and_exit('rate-limit', 'error', 'Twitter is rate limiting you')
    else:
        # anything else is an unexpected error - if ones occur a lot, add the above instead
        raise
except httplib.IncompleteRead, e:
    # I think this is effectively a rate limit error - so only count if it was first error
    if pages_got == 0:
        set_status_and_exit('rate-limit', 'error', 'Twitter broke the conncetion')

# Save progress message
set_status_and_exit("ok-updating", 'ok', '')






