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
                /* Start the keepalive. */
                setTimeout(keepalive, 60000);
            } else if (status == 'CREATE_FAILED' || status == 'RESUME_FAILED') {
                $('.error').show();
            } else if (status == 'PENDING') {
                $('.pending').show();
                setTimeout(get_user_stack_status, 10000);
            }
        } else if (status == 'PENDING') {
            setTimeout(get_user_stack_status, 10000);
        }
    }

    function start_new_terminal(ip) {
        GateOne.init({
            url: terminal_href,
            embedded: true,
            style: {
                'background-color': 'rgba(0, 0, 0, 0.85)',
                'box-shadow': '.5em .5em .5em black',
                'margin-bottom': '0.5em'
            }
        });

        GateOne.Base.superSandbox("GateOne.MyModule", ["GateOne.Terminal"], function(window, undefined) {
            var container = GateOne.Utils.getNode('#container');
            setTimeout(function() {
                var term_num = GateOne.Terminal.newTerminal(null, null, container);
                setTimeout(function() {
                    GateOne.Terminal.sendString('ssh://training@' + ip + ':22/?identities=id_rsa\n');
                }, 500);
            }, 100);
        });
    }

    /* Called on page load. */
    $(function ($) {
        get_terminal_href();
    });
}
