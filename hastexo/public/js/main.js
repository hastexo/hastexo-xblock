/* A cached version of jQuery's getScript. */
jQuery.cachedScript = function(url, options) {
    options = $.extend( options || {}, {
        dataType: "script",
        cache: true,
        url: url
    });

    return jQuery.ajax(options);
};

/* Globals. */
var timeout;

function HastexoXBlock(runtime, element) {
    var status;

    function keepalive() {
        $.ajax({
            type: 'POST',
            url: runtime.handlerUrl(element, 'keepalive'),
            data: '{}',
            success: function() {timeout = setTimeout(keepalive, 60000);},
            dataType: 'json'
        });
    }

    function get_user_stack_status() {
        $.ajax({
            type: 'POST',
            url: runtime.handlerUrl(element, 'get_user_stack_status'),
            data: '{}',
            success: update_user_stack_status,
            dataType: 'json'
        });
    }

    function update_user_stack_status(data) {
        var changed = false;
        if (status !== data.status) {
            changed = true;
            status = data.status;
        }

        /* If there was a change in status, update the screen. */
        if (changed) {
            $('.pending').hide();
            $('.error').hide();
            if (status == 'CREATE_COMPLETE' || status == 'RESUME_COMPLETE') {
                start_new_terminal(data.ip, data.user, data.key);
                timeout = setTimeout(keepalive, 60000);
            } else if (status == 'PENDING') {
                $('.pending').show();
                timeout = setTimeout(get_user_stack_status, 10000);
            } else {
                /* Unexpected status.  Display error message. */
                $('.error_msg').html(data.error_msg);
                $('.error').show();
            }
        } else if (status == 'PENDING') {
            timeout = setTimeout(get_user_stack_status, 10000);
        }
    }

    function start_new_terminal(ip, user, key) {
        GateOne.Base.superSandbox("GateOne.MyModule", ["GateOne.Input", "GateOne.Terminal", "GateOne.Terminal.Input"], function(window, undefined) {
            var container = GateOne.Utils.getNode('#container');
            setTimeout(function() {
                var term_num = GateOne.Terminal.newTerminal(null, null, container);
                setTimeout(function() {
                    GateOne.Terminal.sendString('ssh://' + user + '@' + ip + ':22/?identities=' + key + '\n');
                    setTimeout(function() {
                        GateOne.Terminal.sendDimensions();
                    }, 750);
                }, 250);
            }, 100);
        });
    }

    $(function ($) {
        /* edX recreates the DOM for every vertical unit when navigating to and
         * from them.  However, after navigating away from a lab unit (but
         * remaining on the section) GateOne will remain initialized, any
         * terminals will remain open, and any timeouts will continue to run.
         * Thus, one must take care not to reinitialize GateOne, and to
         * retrieve the open terminal if necessary. */
        if (typeof GateOne == 'undefined') {
            /* Load GateOne dynamically. */
            $.cachedScript('/terminal/static/gateone.js').done(function() {
                GateOne.init({
                    url: window.location.origin + '/terminal/',
                    embedded: true,
                    goDiv: '#gateone',
                    logLevel: 'WARNING'
                });

                get_user_stack_status();
            });
        } else {
            var g = GateOne;
            var t = g.Terminal;
            var u = g.Utils;

            if (t.terminals[1] && t.terminals[1].where) {
                /* Hide the pending message. */
                $('.pending').hide();

                /* Remove the empty goDiv. */
                u.removeElement(g.prefs.goDiv);

                /* Move the old goDiv to its correct place. */
                var container = u.getNode('#gateonecontainer');
                container.appendChild(t.terminals[1].where);

                /* Scroll the terminal to the bottom. */
                u.scrollToBottom('#go_default_term1_pre');
            }
        }
    });
}
