#!/usr/bin/python

import os
import json
import urllib
import sys
import collections
import dateutil.parser
import requests

import scraperwiki

from secrets import *

# Make sure you install "twitter":
# http://pypi.python.org/pypi/twitter
# http://mike.verdone.ca/twitter/
# https://github.com/sixohsix/twitter
# Which also is imported with:
import twitter

# Detect if on command line (cron or testing) or not
in_cli = False
if len(sys.argv) == 1:
    in_cli = True

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
    # and we've been redirected to. Check we are and ask for the permenanet tokens.
    oauth_token, oauth_token_secret = read_token_file(CREDS_PRE_VERIFIY)
    twitter = Twitter(auth=OAuth( oauth_token, oauth_token_secret, consumer_key, consumer_secret), format='', api_version=None)
    oauth_token, oauth_token_secret = parse_oauth_tokens(twitter.oauth.access_token(oauth_verifier=oauth_verifier))
    write_token_file(verified_token_filename, oauth_token, oauth_token_secret)
    return oauth_token, oauth_token_secret

if not os.path.exists(CREDS_VERIFIED):
    if len(sys.argv) < 3:
        result = "need-oauth"
    else:
        (callback_url, oauth_verifier) = (sys.argv[1], sys.argv[2])
        result = oauth_url_dance(CONSUMER_KEY, CONSUMER_SECRET, callback_url, oauth_verifier, CREDS_PRE_VERIFIY, CREDS_VERIFIED)
    # a string means a URL for a redirect (otherwise we get a tuple back with auth tokens in)
    if type(result) == str:
        print result
        requests.post("https://x.scraperwiki.com/api/status", data={'type':'error', 'message':'Authentication failed, fix in settings'})
        sys.exit()

oauth_token, oauth_token_secret = read_token_file(CREDS_VERIFIED)
tw = twitter.Twitter(auth=twitter.OAuth( oauth_token, oauth_token_secret, CONSUMER_KEY, CONSUMER_SECRET))

# XXX We're going to need to check for exceptions like this and delete the auth files and reauth
# You can get these exceptions either just above, or in the dance too - basically in the whole file...
#twitter.api.TwitterHTTPError: Twitter sent status 401 for URL: 1.1/followers/list.json using parameters: (oauth_consumer_key=3CejKAAW7OGqni9lxuU09g&oauth_nonce=14791547903118891158&oauth_signature_method=HMAC-SHA1&oauth_timestamp=1360055733&oauth_token=PFcsB0z7nf7kNDVq030T6VZSK1PwTMLjuLxLi6U7PU&oauth_version=1.0&screen_name=spikingneural&oauth_signature=szYU8AYsfSp3m5Kzo%2FYGnKHZyP8%3D)
#details: {"errors":[{"message":"Invalid or expired token","code":89}]}


#########################################################################
# Helper functions

def save_user(user, table_name):
    data = collections.OrderedDict()

    data['id'] = user['id']
    data['name'] = user['name']
    data['screen_name'] = user['screen_name']
    data['created_at'] = dateutil.parser.parse(user['created_at'])

    data['description'] = user['description']
    data['url'] = user['url']
    data['profile_image_url_https'] = user['profile_image_url_https']

    data['statuses_count'] = user['statuses_count']
    data['followers_count'] = user['followers_count']
    data['following_count'] = user['friends_count']

    data['location'] = user['location']
    
    scraperwiki.sqlite.save(['id'], data, table_name=table_name)


#########################################################################
# Main code

# Read parameters
screen_name = open("user.txt").read().strip()

# Do the hard work
try:
    # print json.dumps(tw.application.rate_limit_status())

    # Save data about followers...

    # always get the first page - right now that gets most recent new followers
    #print "doing first page"
    result = tw.followers.list(screen_name=screen_name)
    for user in result['users']:
        save_user(user, "twitter_followers")
    next_cursor = result['next_cursor']
    next_cursor = scraperwiki.sqlite.get_var('next_cursor_followers', next_cursor)

    # save data about the source user in another table (e.g. has total number of followers in it)
    profile = tw.users.lookup(screen_name=screen_name)
    save_user(profile[0], "twitter_main")

    # do backlog, if we're running from the cli (not from user interaction, as too slow!)
    if in_cli:
        # then proceed with other pages from the cursor:
        while next_cursor != 0:
            #print "doing next cursor", next_cursor
            result = tw.followers.list(screen_name=screen_name, cursor=next_cursor)
            for user in result['users']:
                save_user(user, "twitter_followers")
            next_cursor = result['next_cursor']
            scraperwiki.sqlite.save_var('next_cursor_followers', next_cursor)
    else:
        print "first-few-ok"
        requests.post("https://x.scraperwiki.com/api/status", data={'type':'ok', 'message':'First few followers have been fetched. Others will gradually be added over the coming hours.'})

except twitter.api.TwitterHTTPError, e:
    print e.response_data
    obj = json.loads(e.response_data)
    # if (obj['errors'][0]['code'] == 34): # auth failed
    # if (obj['errors'][0]['code'] == 88): # rate limited
    requests.post("https://x.scraperwiki.com/api/status", data={'type':'error', 'message':obj['errors'][0]['message']})
    sys.exit()

print "all-done-ok"
requests.post("https://x.scraperwiki.com/api/status", data={'type':'ok', 'message':'All up to date'})



