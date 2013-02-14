// Show very general purpose error
var something_went_wrong = function(content) {
    fix_button_texts()
    $('pre,.alert,.help-inline').remove()
    var p = $('<p>').addClass('alert alert-error').html('<b>Something went wrong!</b> Click here to show technical details.').on('click', function() {
        $(this).next('pre').toggle()
    }).css('cursor', 'pointer')
    var pre = $('<pre>').html(content).hide()
    $('body').prepend(pre)
    $('body').prepend(p)
}

// Handle response from exec of get.py
var done_exec_main = function(content) {
    console.log(content)
    try {
        response = JSON.parse(content)

        // Handle various known responses
        if (response['status'] == 'auth-redirect') {
            scraperwiki.tool.redirect(response['url'])
            return
        }

        if (response['status'] == 'ok-updating') {
            var datasetUrl = "/dataset/" + scraperwiki.box
            scraperwiki.tool.redirect(datasetUrl)
            return
        }

        // Show whatever we would on loading page
        // i.e. read status from database that get.py set
        show_hide_stuff()
    } catch(e) {
        // Otherwise an unknown error - e.g. an unexpected stack trace
        something_went_wrong(content)
        return
    }
}

// Event function for when they click on the Go!, Refresh! or Reauthenticate buttons.
// Calls out to the Python script get.py, which does the actual Twitter
// calling. 
var scrape_action = function() {
    $('pre,.alert,.help-inline').remove()
    $('.control-group').removeClass('error')

    var q = $('#q').val()
    q = q.replace(/^@/,'')
    if (q.match(/[^a-zA-Z0-9_]/)) {
        $(".control-group").addClass('error')
        $(".controls").append('<span class="help-inline">Twitter user names only use the alphabet, numbers and _</span>')
        return
    }

    $(this).addClass('loading').html('Loading&hellip;').attr('disabled', true)

    // Rename the dataset in the user interface
    // (only when they press the main submit button - not for refreshes)
    if ($(this).attr('id') == 'submit') {
        scraperwiki.tool.rename("@" + q + "'s Twitter followers")
    }

    // Pass various OAuth bits of data to the Python script that is going to do the work
    scraperwiki.exec('echo ' + escapeshell(q) + '>user.txt; tool/get.py "' + callback_url + '" "' + oauth_verifier + '"', 
        done_exec_main, 
        function(obj, err, exception) {
            something_went_wrong(err + "! " + exception)
        }
    )
}

// Clear data and start again
var clear_action = function() {
    $(this).addClass('loading').html('Clearing&hellip;').attr('disabled', true)
    $('pre,.alert,.help-inline').remove()

    scraperwiki.tool.rename("Get Twitter followers")
    scraperwiki.exec("tool/get.py clean-slate",
        done_exec_main,
        function(obj, err, exception) {
            something_went_wrong(err + "! " + exception) 
        }
    )
}

// Buttons show "Loading..." and so on while working. This puts all their text back after.
var fix_button_texts = function() {
    $('#reauthenticate').removeClass('loading').html('Reauthenticate').attr('disabled', false)
    $('#refresh').removeClass('loading').html('Refresh!').attr('disabled', false)
    $('#submit').removeClass('loading').html('Go!').attr('disabled', false)
    $('#clear-data').removeClass('loading').html('Clear data').attr('disabled', false)
}
 
// Show the right form (get settings, or the refresh data one)
var show_hide_stuff = function(done) {
    // Find out what user it is
    scraperwiki.exec('touch user.txt; cat user.txt', function(data) {
        data = $.trim(data)
        $('#q').val(data)
        $('.who').text(data)

        // Show right form
        scraperwiki.sql('select * from status where id = "followers"', function(results){
            results = results[0]
            console.log(results)

            $('.settings').hide()
            fix_button_texts()
       
            $('.batch_got').text(results['batch_got'])
            $('.batch_expected').text(results['batch_expected'])
            var tweets_per_request = 20
            var request_per_hour = 15 // we run @hourly in cron, and grab 15 each time until Twitter stops us
            var hours_left = Math.round((results['batch_expected'] - results['batch_got']) / request_per_hour / tweets_per_request)
            var days_left = Math.round(hours_left / 24)
            if (hours_left <= 1) {
                eta = "1 hour"
            } else if (hours_left < 13) {
                eta = hours_left + " hours"
            } else if (days_left < 2) {
                eta = "1 day"
            } else {
                eta = days_left + " days"
            }
            $('#eta').text(eta)

            $('#got-some').hide()
            $('#got-all').hide()
            if (results['batch_got'] == results['batch_expected']) {
                $('#got-all').show()
            } else {
                $('#got-some').show()
            }

            $('pre,.alert,.help-inline').remove()
            $('.control-group').removeClass('error')

            if (results['current_status'] == 'auth-redirect') {
                $('#settings-auth').show()
                $('#settings-clear').show()
                // if during auth, click it
                if (oauth_verifier) {
                    $("#reauthenticate").trigger("click")
                }
            } else if (results['current_status'] == 'not-there') {
                $('#settings-get').show()
                var p = $('<p>').addClass('alert alert-error').html("<b>User not found on Twitter!</b> Check the spelling and that they have an account and try again.")
                $('body').prepend(p)
            } else if (results['current_status'] == 'rate-limit') {
                $('#settings-working').show()
                var p = $('<p>').addClass('alert alert-warning').html('<b>Twitter is rate limiting you!</b> Things to try: <ul> <li>Reduce the number of Twitter tools you have</li> <li>Check for <a href="https://twitter.com/settings/applications">other Twitter applications</a> and revoke access</li> </ul>')
                $('body').prepend(p)
                $('#settings-clear').show()
            } else if (results['current_status'] == 'ok-updating') {
                $('#settings-working').show()
                $('#settings-clear').show()
            } else if (results['current_status'] == 'clean-slate') {
                $('#settings-get').show()
            } else {
                alert("Unknown internal state: " + results['current_status'])
            }
            if (done) {
                done()
            }
        }, function(results) {
            // this is bad as it will masks real errors - we have to show the form as
            // no SQLite database gives an error
            $('#settings-get').show()
            if (done) {
                done()
            }
        })
    }, function(obj, err, exception) {
       something_went_wrong(err + "! " + exception)
    })
}

var escapeshell = function(cmd) {
    return "'"+cmd.replace(/'/g,"'\\''")+"'";
};

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
    $("#submit,#refresh,#reauthenticate,#clear-data").removeAttr("disabled")
})

$(document).ready(function() {
    show_hide_stuff()

    $('#q').on('keypress', function(e){
      if(e.which == 13){
        $('#submit').trigger('click')
      }
    })

    $('#clear-data').on('click', clear_action)
    $('#submit,#reauthenticate,#refresh').on('click', scrape_action)
})