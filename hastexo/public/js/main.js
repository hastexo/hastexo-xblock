function HastexoXBlock(runtime, element, configuration) {
    "use strict";

    // State
    var stack = undefined;
    var check = undefined;
    var status_timer = undefined;
    var keepalive_timer = undefined;
    var idle_timer = undefined;
    var check_timer = undefined;

    var init = function() {
        /* Reset the idle timeout on every key press. */
        $(element).keydown(function() {
            if (configuration.timeouts['idle']) {
                if (idle_timer) clearTimeout(idle_timer);
                idle_timer = setTimeout(idle, configuration.timeouts['idle']);
            }
        });

        /* Bind reset button action. */
        $(element).find('.buttons .reset').on('click', reset_dialog);

        /* Display progress check button, if there are tests. */
        if (configuration.has_tests) {
            var button = $(element).find('.buttons .check');
            button.show();
            button.on('click', get_check_status);
        }

        /* edX recreates the DOM for every vertical unit when navigating to and
         * from them.  However, after navigating away from a lab unit (but
         * remaining on the section) GateOne will remain initialized, any
         * terminals will remain open, and any timeouts will continue to run.
         * Thus, one must take care not to reinitialize GateOne. */
        if (typeof GateOne == 'undefined') {
            var terminal_url;

            /* Test if terminal URL is absolute. */
            var is_absolute = new RegExp('^(?:[a-z]+:)?//', 'i');
            var is_port = new RegExp('^:');
            if (is_absolute.test(configuration.terminal_url)) {
                terminal_url = configuration.terminal_url;
            } else if (is_port.test(configuration.terminal_url)) {
                terminal_url = location.protocol + '//' + location.hostname + configuration.terminal_url;
            } else {
                terminal_url = location.origin + configuration.terminal_url;
            }

            /* Load GateOne dynamically. */
            $.cachedScript(terminal_url + '/static/gateone.js').done(function() {
                GateOne.init({
                    url: terminal_url,
                    embedded: true,
                    goDiv: '#gateone',
                    logLevel: 'WARNING'
                });

                get_user_stack_status(true);
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

                    /* Reset keepalive timer. */
                    if (configuration.timeouts['keepalive']) {
                        if (keepalive_timer) clearTimeout(keepalive_timer);
                        keepalive_timer = setTimeout(keepalive, configuration.timeouts['keepalive']);
                    }

                    /* Reset idle timer. */
                    if (configuration.timeouts['idle']) {
                        if (idle_timer) clearTimeout(idle_timer);
                        idle_timer = setTimeout(idle, configuration.timeouts['idle']);
                    }
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
                get_user_stack_status(true);
            }
        }
    };

    var get_user_stack_status = function(initialize = false, reset = false) {
        $('#launch_pending').dialog(element);
        $.ajax({
            type: 'POST',
            url: runtime.handlerUrl(element, 'get_user_stack_status'),
            data: JSON.stringify({
                initialize: initialize,
                reset: reset
            }),
            dataType: 'json'
        }).done(function(data) {
            var changed = false;
            if (!stack || stack.status !== data.status) {
                changed = true;
                stack = data;
            }
            if (changed) {
                update_user_stack_status(stack);
            } else if (stack.status == 'PENDING') {
                if (status_timer) clearTimeout(status_timer);
                status_timer = setTimeout(
                    get_user_stack_status,
                    configuration.timeouts['status']
                );
            }
        }).fail(function(request, text, error) {
            update_user_stack_status({
                status: 'ERROR',
                error_msg: text + ': ' + error
            });
        });
    };

    var update_user_stack_status = function (stack) {
        if (stack.status == 'CREATE_COMPLETE' || stack.status == 'RESUME_COMPLETE') {
            /* Start the terminal.  Certain GateOne tasks must be delayed
             * manually, or risk failure during inter-dependency checking. */
            GateOne.Base.superSandbox("GateOne.MyModule", ["GateOne.Input", "GateOne.Terminal", "GateOne.Terminal.Input"], function(window, undefined) {
                setTimeout(function() {
                    var c = GateOne.Utils.getNode('#container');
                    var term_num = GateOne.Terminal.newTerminal(null, null, c);
                    setTimeout(function() {
                        var s = 'ssh://' + stack.user + '@' + stack.ip + ':22/?provider=' + configuration.provider + '&identity=' + stack.key + '\n';
                        GateOne.Terminal.sendString(s);
                        setTimeout(function() {
                            /* Update screen dimensions. */
                            GateOne.Terminal.sendDimensions();

                            /* Reset keepalive timer. */
                            if (configuration.timeouts['keepalive']) {
                                if (keepalive_timer) clearTimeout(keepalive_timer);
                                keepalive_timer = setTimeout(keepalive, configuration.timeouts['keepalive']);
                            }

                            /* Reset idle timer. */
                            if (configuration.timeouts['idle']) {
                                if (idle_timer) clearTimeout(idle_timer);
                                idle_timer = setTimeout(idle, configuration.timeouts['idle']);
                            }

                            /* Close the dialog. */
                            $.dialog.close();
                        }, 750);
                    }, 250);
                }, 100);
            });
        } else if (stack.status == 'PENDING') {
            if (status_timer) clearTimeout(status_timer);
            status_timer = setTimeout(get_user_stack_status, configuration.timeouts['status']);
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
            dialog.dialog(element);
        }
    };

    var keepalive = function() {
        $.ajax({
            type: 'POST',
            url: runtime.handlerUrl(element, 'keepalive'),
            data: '{}',
            dataType: 'json'
        }).always(function() {
            if (configuration.timeouts['keepalive']) {
                if (keepalive_timer) clearTimeout(keepalive_timer);
                keepalive_timer = setTimeout(keepalive, configuration.timeouts['keepalive']);
            }
        });
    };

    var get_check_status = function() {
        $('#check_pending').dialog(element);

        var show_error = function(error_msg) {
            var dialog = $('#check_error');
            dialog.find('.error_msg').html(error_msg);
            dialog.find('input.ok').one('click', function() {
                $.dialog.close();
            });
            dialog.find('input.retry').one('click', function() {
                $.dialog.close();
                get_check_status();
            });
            dialog.dialog(element);
        };

        $.ajax({
            type: 'POST',
            url: runtime.handlerUrl(element, 'get_check_status'),
            data: '{}',
            dataType: 'json'
        }).done(function(data) {
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
                    dialog.dialog(element);
                } else if (check.status == 'PENDING') {
                    dialog = $('#check_pending');
                    dialog.dialog(element);
                    if (check_timer) clearTimeout(check_timer);
                    check_timer = setTimeout(get_check_status, configuration.timeouts['check']);
                } else {
                    /* Unexpected status.  Display error message. */
                    show_error(check.error_msg);
                }
            } else if (check.status == 'PENDING') {
                if (check_timer) clearTimeout(check_timer);
                check_timer = setTimeout(get_check_status, configuration.timeouts['check']);
            }
        }).fail(function(request, text, error) {
            show_error(text + ': ' + error);
        });
    };

    var idle = function() {
        /* We're idle.  Stop the keepalive timer and clear stack info.  */
        clearTimeout(keepalive_timer);
        stack = null;

        var dialog = $('#idle');
        dialog.find('input.ok').one('click', function() {
            /* Close the old terminal. A new one will be created after the
             * stack reaches the appropriate state. */
            GateOne.Terminal.closeTerminal(1);

            /* Start over. */
            get_user_stack_status(true);
        });
        dialog.dialog(element);
    };

    var reset_dialog = function() {
        var dialog = $('#reset_dialog');

        dialog.find('input.cancel').one('click', function() {
            $.dialog.close();
        });

        dialog.find('input.reset').one('click', function() {
            $.dialog.close();
            /* Close old terminals. */
            for (var term in GateOne.Terminal.terminals) {
                GateOne.Terminal.closeTerminal(term);
            }
            get_user_stack_status(true, true);
        });

        dialog.dialog(element);
    };

    init();
}
