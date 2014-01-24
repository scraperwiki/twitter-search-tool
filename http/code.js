// Show very general purpose error
var something_went_wrong = function(content) {
    console.log("something_went_wrong", content)
    fix_button_texts()
    $('pre,.alert-error,.help-inline').remove()
    var p = $('<p>').addClass('alert alert-error').html('<b>Something went wrong!</b> Click here to show technical details.').on('click', function() {
        $(this).next('pre').toggle()
    }).css('cursor', 'pointer')
    var pre = $('<pre>').html(content).hide()
    $('body').prepend(pre)
    $('body').prepend(p)
}

// Handle response from exec of twsearch.py
var done_exec_main = function(content, rename) {
    console.log(content)
    try {
        response = JSON.parse(content)

        // Handle various known responses
        if (response['status'] == 'auth-redirect') {
            scraperwiki.tool.redirect(response['url'])
            return
        }

        // Show whatever we would on loading page
        // i.e. read status from database that twsearch.py set
        show_hide_stuff(null, rename)
    } catch(e) {
        // Otherwise an unknown error - e.g. an unexpected stack trace
        something_went_wrong(content)
        return
    }
}

// Event function for when they click on the Go!, Refresh! or Reauthenticate buttons.
// Calls out to the Python script twsearch.py, which does the actual Twitter
// calling.
var scrape_action = function() {
    $('pre, .alert-error, .help-inline').remove()
    $('.control-group').removeClass('error')

    var q = $('#q').val()

    $(this).addClass('loading').html('Loading&hellip;').attr('disabled', true)

    // show_hide_stuff will check this variable later and contact intercom.io
    window.trackSearch = true

    // Pass various OAuth bits of data to the Python script that is going to do the work
    scraperwiki.exec('echo ' + scraperwiki.shellEscape(q) + '>query.txt; ONETIME=1 tool/twsearch.py "' + callback_url + '" "' + oauth_verifier + '"',
        function(content) {
        // Set it going immediately in the background for a bit more instant gratification
            scraperwiki.exec('tool/twsearch.py >/dev/null 2>&1 &')
        done_exec_main(content, true)
    },
        function(obj, err, exception) {
            something_went_wrong(err + "! " + exception)
        }
    )
}

// Button to toggle monitoring mode
var toggle_monitoring_mode = function() {
    var new_mode
    if (this.checked) {
        new_mode = 'monitoring'
        scraperwiki.reporting.user({increments: {ts_schedules: 1}})
    } else {
        new_mode = 'clearing-backlog'
        scraperwiki.reporting.user({increments: {ts_schedules: -1}})
    }

    var $checkbox = $(this)
    $checkbox.hide().next().show()

    scraperwiki.exec('MODE=' + new_mode + ' ONETIME=1 tool/twsearch.py "' + callback_url + '" "' + oauth_verifier + '"',
        function(data) {
            $checkbox.show().next().hide()
            done_exec_main(data)
        },
        function(obj, err, exception) {
            something_went_wrong(err + "! " + exception)
        }
    )
}


// Show rate liit and so on
var diagnostics_action = function() {
    var $link = $(this)
    if ($('#diagnostics-area .alert').is(":visible")) {
        $('#diagnostics-area .alert').slideUp(400)
        return
    }
    $link.next().show()

    // Pass various OAuth bits of data to the Python script that is going to do the work
    scraperwiki.exec('tool/twsearch.py diagnostics',
        function (content) {
            $link.next().hide()
            var diagnostics
        try {
            diagnostics = JSON.parse(content)
        } catch(e) {
            console.log("caught!!")
            // Otherwise an unknown error - e.g. an unexpected stack trace
            something_went_wrong(content)
            return
        }
        console.log(diagnostics)
        var html = ''
        if ('mode' in diagnostics) {
            html += 'Mode is <b>' + diagnostics.mode + '</b>. '
        }
        if ('status' in diagnostics) {
            html += 'Status <b>' + diagnostics.status + '</b>. '
        }
        if ('user' in diagnostics) {
            html += 'Authenticated user is <b>@' + diagnostics.user + '</b>. '
            html += 'There are <b>' + diagnostics.remaining + '/' + diagnostics.limit + '</b> search API calls left, '
            html += 'resetting <b>' + moment.unix(diagnostics.reset).fromNow() + "</b>. "
        }
        if (!('crontab' in diagnostics)) {
            html += 'Not scheduled. '
        } else if (diagnostics.crontab.match(/no crontab/)) {
            html += 'Not scheduled. '
        } else {
            html += 'Scheduled to update at <b>' + parseInt(diagnostics.crontab) + ' minutes</b> past the hour. '
        }
        $('#diagnostics-area .alert').html(html).slideDown(400)
    },
        function(obj, err, exception) {
            something_went_wrong(err + "! " + exception)
        }
    )
}


// Clear data and start again
var clear_action = function() {
    $(this).addClass('loading').html('Clearing&hellip;').attr('disabled', true)
    $('pre,.alert-error,.help-inline').remove()

    scraperwiki.dataset.name("Search for Tweets")
    scraperwiki.reporting.user({increments: {ts_resets: 1}})
    scraperwiki.exec("tool/twsearch.py clean-slate",
    function(content) {
        done_exec_main(content, false)
    },
        function(obj, err, exception) {
            something_went_wrong(err + "! " + exception)
        }
    )
}

 // Buttons show "Loading..." and so on while working. This puts all their text back after.
var fix_button_texts = function() {
    $('#reauthenticate').removeClass('loading').html('Reauthenticate').attr('disabled', false)
    $('#submit').removeClass('loading').html('Search').attr('disabled', false)
    $('#clear-data').removeClass('loading').html('Search for something else*').attr('disabled', false)
}

// Show the right form (get settings, or the refresh data one)
var show_hide_stuff = function(done, rename) {
    // Find out what user it is
    scraperwiki.exec('touch query.txt; cat query.txt', function(data) {
        data = $.trim(data)
        $('#q').val(data)
        $('.search-query').text(data)

        if (rename) {
            scraperwiki.dataset.name("Tweets matching '" + data + "'")
        }

        // Show right form
        scraperwiki.sql('select * from __status where id = "tweets"', function(results){
            results = results[0]
            console.log(results)

            $('.settings').hide()
            fix_button_texts()

            if (results['current_status'] == 'rate-limit') {
                var p = $('<p>').addClass('alert alert-warning').html('<b>Twitter is rate limiting you!</b> Things to try: <ul> <li>Reduce the number of Twitter tools you have</li> <li>Check for <a href="https://twitter.com/settings/applications">other Twitter applications</a> and revoke access</li> </ul>')
                $('body').prepend(p)
                results['current_status'] = 'ok-updating'
            }

            if (results['current_status'] == 'clean-slate') {
                $('#settings-get').show()
            } else if (results['current_status'] == 'invalid-query') {
        console.log(results)
                var p = $('<p>').addClass('alert alert-warning').html("<b>That query didn't work!</b> It isn't a valid Twitter search.")
                $('body').prepend(p)
                $('#settings-get').show()
            } else if (results['current_status'] == 'near-not-supported') {
        console.log(results)
                var p = $('<p>').addClass('alert alert-warning').html("<b>That query didn't work!</b> Twitter's API doesn't support using 'near:' to find Tweets close to a place.")
                $('body').prepend(p)
                $('#settings-get').show()
            } else if (results['current_status'] == 'auth-redirect') {
                // if during auth, click it
                if (oauth_verifier) {
                    $('#settings-get').show()
                    $("#submit").trigger("click")
                } else {
                    $('#settings-auth').show()
                    $('#settings-clear').show()
        }
                // Rename the dataset in the user interface
                scraperwiki.dataset.name("Tweets matching '" + data + "'")
            } else if (results['current_status'] == 'ok-updating') {
                $('#settings-' + results['mode']).show()
                $('#settings-monitor-choice').show()
                $('#monitor-future-tweets').attr('checked', results['mode'] == 'monitoring')
        scraperwiki.sql('select min(created_at) as min, max(created_at) as max from tweets', function(range){
                    $(".date-range").html("<br>from " + moment(range[0]['min']).format("Do MMM YYYY") + " to " + moment(range[0]['max']).format("Do MMM YYYY"))
        })
                $('#settings-clear').show()
                if(window.trackSearch) {
                    scraperwiki.reporting.user({increments: {ts_searches: 1}})
                }
            } else {
                alert("Unknown internal state: " + results['current_status'])
            }
            if (done) {
                done()
            }
        }, function(results) {
            // this is bad as it will masks real errors - we have to show the form as
            // no SQLite database gives an error
            fix_button_texts()
            $('#settings-get').show()
            if (done) {
                done()
            }
        })
    }, function(obj, err, exception) {
       something_went_wrong(err + "! " + exception)
    })
}

// Get OAuth parameters that we need from the URL
var settings = scraperwiki.readSettings()
var callback_url
var oauth_verifier
scraperwiki.tool.getURL(function(our_url) {
    console.log(our_url)
    var url = $.url(our_url)
    oauth_verifier = url.param('oauth_verifier')
    // remove query parameters for the callback URL, so they don't stack up if we
    // go multiple times to Twitter
    callback_url = url.attr('base') + url.attr('path')
    // only when we have the callback URL, allow the submit button to be clicked
    $("#submit,#reauthenticate,#clear-data").removeAttr("disabled")
})

$(document).ready(function() {
    show_hide_stuff()

    $('#q').on('keypress', function(e){
      if(e.which == 13){
        $('#submit').trigger('click')
      }
    })

    $('#clear-data').on('click', clear_action)
    $('#submit, #reauthenticate').on('click', scrape_action)
    $('#monitor-future-tweets').on('change', toggle_monitoring_mode)
    $('#diagnostics').on('click', diagnostics_action)
})
