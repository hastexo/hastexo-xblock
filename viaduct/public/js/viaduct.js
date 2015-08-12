/* Javascript for ViaductXBlock. */
function ViaductXBlock(runtime, element) {
    var terminal_href;
    var status;

    function get_terminal_href() {
        $.ajax({
            type: 'POST',
            url: runtime.handlerUrl(element, 'get_terminal_href'),
            data: '{}',
            success: update_terminal_href,
            dataType: 'json'
        });
    }

    function keepalive() {
        $.ajax({
            type: 'POST',
            url: runtime.handlerUrl(element, 'keepalive'),
            data: '{}',
            success: update_keepalive,
            dataType: 'json'
        });
    }

    function update_terminal_href(result) {
        terminal_href = result.terminal_href;
        get_user_stack_status();
    }

    function update_keepalive(result) {
        /* Schedule a new keepalive. */
        setTimeout(keepalive, 60000);
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

    function update_user_stack_status(result) {
        var changed = false;
        if (status !== result.status) {
            changed = true;
            status = result.status;
        }

        /* If there was a change in status, update the screen. */
        if (changed) {
            $('.pending').hide();
            $('.error').hide();
            if (status == 'CREATE_COMPLETE' || status == 'RESUME_COMPLETE') {
                start_new_terminal(result.ip);
                setTimeout(keepalive, 60000);
            } else if (status == 'PENDING') {
                $('.pending').show();
                setTimeout(get_user_stack_status, 10000);
            } else {
                /* Unexpected status.  Display error message. */
                $('.error_msg').html(result.error_msg);
                $('.error').show();
            }
        } else if (status == 'PENDING') {
            setTimeout(get_user_stack_status, 10000);
        }
    }

    function start_new_terminal(ip) {
        GateOne.init({
            url: terminal_href,
            embedded: true,
            goDiv: '#gateone',
            logLevel: 'WARNING'
        });

        GateOne.Base.superSandbox("GateOne.MyModule", ["GateOne.Input", "GateOne.Terminal", "GateOne.Terminal.Input"], function(window, undefined) {
            var container = GateOne.Utils.getNode('#container');
            setTimeout(function() {
                var term_num = GateOne.Terminal.newTerminal(null, null, container);
                setTimeout(function() {
                    GateOne.Terminal.sendString('ssh://training@' + ip + ':22/?identities=id_rsa\n');
                    setTimeout(function() {
                        GateOne.Terminal.sendDimensions();
                    }, 750);
                }, 250);
            }, 100);
        });
    }

    /* edX recreates the DOM for every vertical unit when navigating to and
     * from them.  However, after navigating away from a lab unit (but
     * remaining on the section) GateOne will remain initialized, any
     * terminals will remain open, and any timeouts will continue to run.
     * Thus, one must take care not to reinitialize GateOne, and to
     * retrieve the open terminal if necessary. */
    $(function ($) {
        var go = GateOne;
        if (!go.initialized) {
            get_terminal_href();
        } else {
            var t = go.Terminal;
            var u = go.Utils;
            if (t.terminals[1] && t.terminals[1].where) {
                /* Hide the pending message. */
                $('.pending').hide();

                /* Remove the empty goDiv. */
                u.removeElement(go.prefs.goDiv);

                /* Move the old goDiv to its correct place. */
                var container = u.getNode('#gateonecontainer');
                container.appendChild(t.terminals[1].where);

                /* Scroll the terminal to the bottom. */
                go.Utils.scrollToBottom('#go_default_term1_pre');
            }
        }
    });
}
