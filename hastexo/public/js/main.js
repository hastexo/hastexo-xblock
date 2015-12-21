var stack, check;
var status_timer, keepalive_timer, idle_timer, check_timer;
var timeouts = {
    status: 10000,
    keepalive: 60000,
    idle: 600000,
    check: 5000
};

function HastexoXBlock(runtime, element) {
    function get_user_stack_status() {
        $('#launch_pending').dialog();
        $.ajax({
            type: 'POST',
            url: runtime.handlerUrl(element, 'get_user_stack_status'),
            data: '{}',
            success: function(data) {
                var changed = false;
                if (!stack || stack.status !== data.status) {
                    changed = true;
                    stack = data;
                }
                if (changed) {
                    update_user_stack_status(stack);
                } else if (stack.status == 'PENDING') {
                    if (status_timer) clearTimeout(status_timer);
                    status_timer = setTimeout(get_user_stack_status, timeouts['status']);
                }
            },
            dataType: 'json'
        });
    }

    function update_user_stack_status(stack) {
        if (stack.status == 'CREATE_COMPLETE' || stack.status == 'RESUME_COMPLETE') {
            /* Start the terminal.  Certain GateOne tasks must be delayed
             * manually, or risk failure during inter-dependency checking. */
            GateOne.Base.superSandbox("GateOne.MyModule", ["GateOne.Input", "GateOne.Terminal", "GateOne.Terminal.Input"], function(window, undefined) {
                setTimeout(function() {
                    var c = GateOne.Utils.getNode('#container');
                    var term_num = GateOne.Terminal.newTerminal(null, null, c);
                    setTimeout(function() {
                        var s = 'ssh://' + stack.user + '@' + stack.ip + ':22/?identities=' + stack.key + '\n';
                        GateOne.Terminal.sendString(s);
                        setTimeout(function() {
                            /* Update screen dimensions. */
                            GateOne.Terminal.sendDimensions();

                            /* Display assessment test button. */
                            $(element).find('.check').show();

                            /* Reset keepalive timer. */
                            if (keepalive_timer) clearTimeout(keepalive_timer);
                            keepalive_timer = setTimeout(keepalive, timeouts['keepalive']);

                            /* Reset idle timer. */
                            if (idle_timer) clearTimeout(idle_timer);
                            idle_timer = setTimeout(idle, timeouts['idle']);

                            /* Close the dialog. */
                            $.dialog.close();
                        }, 750);
                    }, 250);
                }, 100);
            });
        } else if (stack.status == 'PENDING') {
            if (status_timer) clearTimeout(status_timer);
            status_timer = setTimeout(get_user_stack_status, timeouts['status']);
        } else {
            /* Unexpected status.  Display error message. */
            var dialog = $('#launch_error');
            dialog.find('.error_msg').html(stack.error_msg);
            dialog.find('input.ok').one('click', function() {
                $.dialog.close();
            });
            dialog.find('input.retry').one('click', function() {
                $.dialog.close();
                location.reload();
            });
            dialog.dialog();
        }
    }

    function keepalive() {
        $.ajax({
            type: 'POST',
            url: runtime.handlerUrl(element, 'keepalive'),
            data: '{}',
            success: function() {
                if (keepalive_timer) clearTimeout(keepalive_timer);
                keepalive_timer = setTimeout(keepalive, timeouts['keepalive']);
            },
            dataType: 'json'
        });
    }

    function get_check_status() {
        $('#check_pending').dialog();
        $.ajax({
            type: 'POST',
            url: runtime.handlerUrl(element, 'get_check_status'),
            data: '{}',
            success: function(data) {
                var changed = false;
                if (!check || check.status !== data.status) {
                    changed = true;
                    check = data;
                }
                if (changed) {
                    var dialog;
                    if (check.status == 'COMPLETE') {
                        dialog = $('#check_complete');
                        dialog.find('.check_pass').html(data.pass);
                        dialog.find('.check_total').html(data.total);
                        dialog.find('input.ok').one('click', function() {
                            $.dialog.close();
                        });
                        dialog.dialog();
                    } else if (check.status == 'PENDING') {
                        dialog = $('#check_pending');
                        dialog.dialog();
                        if (check_timer) clearTimeout(check_timer);
                        check_timer = setTimeout(get_check_status, timeouts['check']);
                    } else {
                        /* Unexpected status.  Display error message. */
                        dialog = $('#check_error');
                        dialog.find('.error_msg').html(check.error_msg);
                        dialog.find('input.ok').one('click', function() {
                            $.dialog.close();
                        });
                        dialog.find('input.retry').one('click', function() {
                            $.dialog.close();
                            get_check_status();
                        });
                        dialog.dialog();
                    }
                } else if (check.status == 'PENDING') {
                    if (check_timer) clearTimeout(check_timer);
                    check_timer = setTimeout(get_check_status, timeouts['check']);
                }
            },
            dataType: 'json'
        });
    }

    function idle() {
        /* We're idle.  Stop the keepalive timer and clear stack info.  */
        clearTimeout(keepalive_timer);
        stack = null;

        var dialog = $('#idle');
        dialog.find('input.ok').one('click', function() {
            /* Close the old terminal. A new one will be created after the
             * stack reaches the appropriate state. */
            GateOne.Terminal.closeTerminal(1);

            /* Start over. */
            get_user_stack_status();
        });
        dialog.dialog();
    }

    /* Reset the idle timeout on every key press. */
    $(element).keydown(function() {
        if (idle_timer) clearTimeout(idle_timer);
        idle_timer = setTimeout(idle, timeouts['idle']);
    });

    /* Bind check button action. */
    $(element).find('p.check input').on('click', get_check_status);

    /* edX recreates the DOM for every vertical unit when navigating to and
     * from them.  However, after navigating away from a lab unit (but
     * remaining on the section) GateOne will remain initialized, any
     * terminals will remain open, and any timeouts will continue to run.
     * Thus, one must take care not to reinitialize GateOne. */
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
        /* If the stack status is known, the keepalive timer hasn't been
         * stopped, and we can simply recover the existing
         * workspace.  If it doesn't exist, we create a new one.*/
        if (stack) {
            if (GateOne.Terminal.terminals[1]) {
                /* Recover existing workspace. */
                GateOne.Utils.removeElement(GateOne.prefs.goDiv);
                var c = GateOne.Utils.getNode('#gateonecontainer');
                var w = GateOne.Terminal.terminals[1].where;
                c.appendChild(w);

                /* Scroll to the bottom of the terminal manually. */
                GateOne.Utils.scrollToBottom('#go_default_term1_pre');

                /* Display assessment test button. */
                $(element).find('.check').show();

                /* Reset keepalive timer. */
                if (keepalive_timer) clearTimeout(keepalive_timer);
                keepalive_timer = setTimeout(keepalive, timeouts['keepalive']);

                /* Reset idle timer. */
                if (idle_timer) clearTimeout(idle_timer);
                idle_timer = setTimeout(idle, timeouts['idle']);
            } else {
                update_user_stack_status(stack);
            }

        /* We don't know the stack status.  Ask the server, but first close
         * any existing terminals. */
        } else {
            if (GateOne.Terminal.terminals[1]) {
                /* Recover existing workspace. */
                GateOne.Utils.removeElement(GateOne.prefs.goDiv);
                var c = GateOne.Utils.getNode('#gateonecontainer');
                var w = GateOne.Terminal.terminals[1].where;
                c.appendChild(w);

                /* Close the old terminal. A new one will be created after the
                 * stack reaches the appropriate state. */
                GateOne.Terminal.closeTerminal(1);
            }

            /* Start over. */
            get_user_stack_status();
        }
    }
}
