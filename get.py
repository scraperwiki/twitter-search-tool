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

import scraperwiki

from secrets import *

# Make sure you install "twitter":
# http://pypi.python.org/pypi/twitter
# http://mike.verdone.ca/twitter/
# https://github.com/sixohsix/twitter
# Which also is imported with:
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
    # and we've been redirected to. Check we are and ask for the permenanet tokens.
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
            set_status_and_exit(result, 'error', 'Authentication failed, fix in settings')

    oauth_token, oauth_token_secret = read_token_file(CREDS_VERIFIED)
    tw = twitter.Twitter(auth=twitter.OAuth( oauth_token, oauth_token_secret, CONSUMER_KEY, CONSUMER_SECRET))
    return tw

# XXX We're going to need to check for exceptions like this and delete the auth files and reauth
# You can get these exceptions either just above, or in the dance too - basically in the whole file...
#twitter.api.TwitterHTTPError: Twitter sent status 401 for URL: 1.1/followers/list.json using parameters: (oauth_consumer_key=3CejKAAW7OGqni9lxuU09g&oauth_nonce=14791547903118891158&oauth_signature_method=HMAC-SHA1&oauth_timestamp=1360055733&oauth_token=PFcsB0z7nf7kNDVq030T6VZSK1PwTMLjuLxLi6U7PU&oauth_version=1.0&screen_name=spikingneural&oauth_signature=szYU8AYsfSp3m5Kzo%2FYGnKHZyP8%3D)
#details: {"errors":[{"message":"Invalid or expired token","code":89}]}

#########################################################################
# Helper functions

# Stores one Twitter user in the ScraperWiki database
def save_user(batch, user, table_name):
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

    data['batch'] = batch
    
    scraperwiki.sqlite.save(['id'], data, table_name=table_name)

# After detecting an auth failed error mid work, call this
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
def set_status_and_exit(output, typ, message):
    print output
    #print typ, message
    requests.post("https://x.scraperwiki.com/api/status", data={'type':typ, 'message':message})
    sys.exit()


#########################################################################
# Main code

pages_got = 0
try:
    screen_name = open("user.txt").read().strip()

    # Connect to Twitter
    tw = do_tool_oauth()
    print json.dumps(tw.application.rate_limit_status()) # if we ever need the rate limit status

    # A batch is one scan through the list of followers - we have to scan as we only
    # get 20 per API call, and have 15 API calls / 15 minutes (as of Feb 2013).
    # The cursor is Twitter's identifier of where in the current batch we are.
    current_batch = scraperwiki.sqlite.get_var('current_batch', 1)
    next_cursor = scraperwiki.sqlite.get_var('next_cursor_followers', -1)
    next_cursor = -1

    # Get as many pages in the batch as we can (most likely 15!)
    while True:
        if next_cursor == -1:
            result = tw.followers.list(screen_name=screen_name)
        else:
            result = tw.followers.list(screen_name=screen_name, cursor=next_cursor)
        pages_got += 1
        for user in result['users']:
            save_user(current_batch, user, "twitter_followers")
        next_cursor = result['next_cursor']
        scraperwiki.sqlite.save_var('next_cursor_followers', next_cursor)

        if next_cursor == 0:
            # We've finished a batch
            current_batch += 1
            scraperwiki.sqlite.save_var('current_batch', current_batch)
            scraperwiki.sqlite.save_var('next_cursor_followers', -1)
            break

except twitter.api.TwitterHTTPError, e:
    if "Twitter sent status 401 for URL" in str(e):
        clear_auth_and_restart()

    # https://dev.twitter.com/docs/error-codes-responses
    obj = json.loads(e.response_data)
    code = obj['errors'][0]['code'] 
    # authentication failure
    if (code in [32, 89]):
        clear_auth_and_restart()
    # rate limit exceeded
    if (code == 88 and pages_got > 0):
        # provided we got at least one page, rate limit isn't an error but expected
        pass
    else:
        set_status_and_exit(e.response_data, 'error', obj['errors'][0]['message'])
except httplib.IncompleteRead, e:
    # I think this is effectively a rate limit error - so only count if it was first error
    if pages_got == 0:
        faked_response_data = {"errors":[{"message":"Twitter broke the connection","code":-100}]}
        set_status_and_exit(faked_response_data, 'error', "Twitter unexpectedly broke the connection")

# Save data about the source user in another table (e.g. has total number of followers in it)
profile = tw.users.lookup(screen_name=screen_name)
save_user(None, profile[0], "twitter_main")

# How far are we in the most recent finished batch?
try:
    got_so_far = scraperwiki.sqlite.select("count(*) as c from twitter_followers where batch = %d" % current_batch - 1)[0]['c']
except:
    got_so_far = 0
# Or if that was the first batch, the current running batch
if got_so_far == 0:
    try:
        got_so_far = scraperwiki.sqlite.select("count(*) as c from twitter_followers where batch = %d" % current_batch)[0]['c']
    except:
        got_so_far = 0
expected = profile[0]['followers_count']
scraperwiki.sqlite.save_var('batch_got', got_so_far)
scraperwiki.sqlite.save_var('batch_expected', expected)

# Save progress message
if got_so_far == expected:
    set_status_and_exit("ok-updating", 'ok', "Fully up to date")
else:
    set_status_and_exit("ok-updating", 'error', "Running... %d/%d" % (got_so_far, expected))





