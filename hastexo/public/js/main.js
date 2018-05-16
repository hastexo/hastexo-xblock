function HastexoXBlock(runtime, element, configuration) {
    "use strict";

    // State
    var stack = undefined;
    var check = undefined;
    var status_timer = undefined;
    var keepalive_timer = undefined;
    var idle_timer = undefined;
    var check_timer = undefined;
    var terminal_client = undefined;
    var terminal_element = undefined;
    var terminal_connected = false;

    var init = function() {
        /* Bind reset button action. */
        $(element).find('.buttons .reset').on('click', reset_dialog);

        /* Display progress check button, if there are tests. */
        if (configuration.has_tests) {
            var button = $(element).find('.buttons .check');
            button.show();
            button.on('click', get_check_status);
        }

        /* Display ports dropdown, if there are any. */
        if (configuration.ports.length > 0) {
            var select = $(element).find('.buttons .port');
            $.each(configuration.ports, function(i, port) {
                select.append($('<option>', {
                    value: port,
                    text: configuration.port_names[i],
                    selected: port == configuration.port ? true : false
                }));
            });
            select.show();
            select.change(function() {
                var port = parseInt($(this).val());
                try {
                    terminal_connect(stack, port);
                } catch (e) {
                    /* Connection error.  Display error message. */
                    var dialog = $('#launch_error');
                    dialog.find('.message').html('Could not connect to your lab environment:');
                    dialog.find('.error_msg').html(e);
                    dialog.find('input.ok').one('click', function() {
                        $.dialog.close();
                    });
                    dialog.find('input.retry').one('click', function() {
                        $.dialog.close();
                        location.reload();
                    });
                    dialog.dialog(element);
                }

                if (terminal_connected) {
                    configuration.port = port;

                    /* Reset keepalive timer. */
                    if (configuration.timeouts['keepalive']) {
                        if (keepalive_timer) clearTimeout(keepalive_timer);
                        keepalive_timer = setTimeout(
                            keepalive,
                            fuzz_timeout(configuration.timeouts['keepalive'])
                        );
                    }

                    /* Reset idle timer. */
                    if (configuration.timeouts['idle']) {
                        if (idle_timer) clearTimeout(idle_timer);
                        idle_timer = setTimeout(idle, configuration.timeouts['idle']);
                    }

                    $.ajax({
                        type: 'POST',
                        url: runtime.handlerUrl(element, 'set_port'),
                        data: JSON.stringify({
                            port: port
                        }),
                        dataType: 'json'
                    });
                } else {
                    /* Reset to previous selection. */
                    $(this).find('option[value="' + configuration.port + '"]').prop('selected', true);
                }
            });
        }

        /* Set container CSS class, if graphical. */
        if (configuration.protocol != "ssh") {
            $('#container').addClass('graphical');
        }

        /* Process terminal URL. */
        var prot_map = {
            "http:":  "ws:",
            "https:": "wss:"
        };
        var terminal_http_url = location.protocol + '//' + location.hostname + configuration.terminal_url;
        var terminal_ws_url = prot_map[location.protocol] + '//' + location.hostname + configuration.terminal_url;

        /* Load app dynamically. */
        $.cachedScript(terminal_http_url + '/guacamole-common-js/all.min.js').done(function() {
            terminal_client = new Guacamole.Client(
                new Guacamole.WebSocketTunnel(terminal_ws_url + "websocket-tunnel")
            );
            terminal_element = terminal_client.getDisplay().getElement();

            /* Show the terminal.  */
            $("#terminal").append(terminal_element);

            /* Disconnect on tab close. */
            window.onunload = function() {
                terminal_client.disconnect();
            };

            /* Mouse handling */
            var mouse = new Guacamole.Mouse(terminal_element);

            mouse.onmousedown =
            mouse.onmouseup   =
            mouse.onmousemove = function(mouseState) {
                terminal_client.sendMouseState(mouseState);

                /* Reset the idle timeout on mouse action. */
                if (configuration.timeouts['idle']) {
                    if (idle_timer) clearTimeout(idle_timer);
                    idle_timer = setTimeout(idle, configuration.timeouts['idle']);
                }
            };

            /* Keyboard handling.  */
            var keyboard = new Guacamole.Keyboard(terminal_element);
            var ctrl, shift = false;

            keyboard.onkeydown = function (keysym) {
                var cancel_event = true;

                /* Don't cancel event on paste shortcuts. */
                if (keysym == 0xFFE1 /* shift */
                    || keysym == 0xFFE3 /* ctrl */
                    || keysym == 0xFF63 /* insert */
                    || keysym == 0x0056 /* V */
                    || keysym == 0x0076 /* v */
                ) {
                    cancel_event = false;
                }

                /* Remember when ctrl or shift are down. */
                if (keysym == 0xFFE1) {
                    shift = true;
                } else if (keysym == 0xFFE3) {
                    ctrl = true;
                }

                /* Delay sending final stroke until clipboard is updated. */
                if ((ctrl && shift && keysym == 0x0056) /* ctrl-shift-V */
                    || (ctrl && keysym == 0x0076) /* ctrl-v */
                    || (shift && keysym == 0xFF63) /* shift-insert */
                ) {
                    window.setTimeout(function() {
                        terminal_client.sendKeyEvent(1, keysym);
                    }, 50);
                } else {
                    terminal_client.sendKeyEvent(1, keysym);
                }

                return !cancel_event;
            };

            keyboard.onkeyup = function (keysym) {
                /* Remember when ctrl or shift are released. */
                if (keysym == 0xFFE1) {
                    shift = false;
                } else if (keysym == 0xFFE3) {
                    ctrl = false;
                }

                /* Delay sending final stroke until clipboard is updated. */
                if ((ctrl && shift && keysym == 0x0056) /* ctrl-shift-v */
                    || (ctrl && keysym == 0x0076) /* ctrl-v */
                    || (shift && keysym == 0xFF63) /* shift-insert */
                ) {
                    window.setTimeout(function() {
                        terminal_client.sendKeyEvent(0, keysym);
                    }, 50);
                } else {
                    terminal_client.sendKeyEvent(0, keysym);
                }
            };

            $(terminal_element)
                /* Set tabindex so that element can be focused.  Otherwise, no
                 * keyboard events will be registered for it. */
                .attr('tabindex', 1)
                /* Focus on the element based on mouse movement.  Simply
                 * letting the user click on it doesn't work. */
                .hover(
                    function() {
                       $(this).focus();
                    }, function() {
                       $(this).blur();
                    }
                )
                /* Release all keys when the element loses focus. */
                .blur(function() {
                    keyboard.reset();
                });

            /* Handle paste events when the element is in focus. */
            $(document).on('paste', function(e) {
                var text = e.originalEvent.clipboardData.getData('text/plain');
                if ($(terminal_element).is(":focus")) {
                    terminal_client.setClipboard(text);
                }
            });

            /* Error handling. */
            terminal_client.onerror = function(guac_error) {
                /* Reset and disconnect. */
                if (keepalive_timer) clearTimeout(keepalive_timer);
                if (idle_timer) clearTimeout(idle_timer);
                stack = null;
                terminal_client.disconnect();

                var dialog = $('#launch_error');
                var dialog_message =
                    "Could not connect to your lab environment. " +
                    "The client detected an unexpected error. " +
                    "The server's error message was:";
                var error_message = guac_error.message;
                /* Special-case the unhelpful "Aborted. See logs"
                 * message, indicating that although we did have a
                 * working connection earlier, we've now lost it (as
                 * opposed to never being able to connect to the
                 * upstream web socket at all). For any other message,
                 * just pass through the error received from
                 * upstream. */
                if (guac_error.message.toLowerCase().startsWith('aborted')) {
                    dialog_message = "Lost connection to your lab environment."
                    error_message =
                        "The remote server unexpectedly disconnected. " +
                        "You can try closing your browser window, " +
                        "and returning to this page in a few minutes.";
                }
                dialog.find('.message').html(dialog_message);
                dialog.find('.error_msg').html(error_message);
                dialog.find('input.ok').one('click', function() {
                    $.dialog.close();
                });
                dialog.find('input.retry').one('click', function() {
                    $.dialog.close();
                    location.reload();
                });
                dialog.dialog(element);
            };

            get_user_stack_status(true);
        });
    };

    /* Returns a fuzzy timeout that varies between plus or minus 25% of the
     * base value. */
    var fuzz_timeout = function(timeout) {
        var range = Math.floor(timeout * 0.25);
        var fuzz = Math.random() * (range * 2 + 1) - range;

        return timeout + fuzz;
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
            } else if (stack.status == 'LAUNCH_PENDING') {
                if (status_timer) clearTimeout(status_timer);
                status_timer = setTimeout(
                    get_user_stack_status,
                    fuzz_timeout(configuration.timeouts['status'])
                );
            }
        }).fail(function(request, text, error) {
            update_user_stack_status({
                status: 'ERROR',
                error_msg: text + ': ' + error
            });
        });
    };

    var terminal_connect = function(stack, port = '') {
        if (terminal_connected) {
            terminal_client.disconnect()
            terminal_connected = false;
        }

        try {
            terminal_client.connect($.param({
                'protocol': configuration.protocol,
                'width': $('#terminal').width(),
                'height': $('#terminal').height(),
                'ip': stack.ip,
                'port': port,
                'user': stack.user,
                'key': stack.key,
                'password': stack.password
            }));
            terminal_connected = true;
        } catch (e) {
            console.warn(e);
            terminal_connected = false;
            throw e;
        }
    };

    var update_user_stack_status = function (stack) {
        if (stack.status == 'CREATE_COMPLETE' || stack.status == 'RESUME_COMPLETE') {
            /* Connect to the terminal server. */
            try {
                terminal_connect(stack, configuration.port);
            } catch (e) {
                /* Connection error.  Display error message. */
                var dialog = $('#launch_error');
                dialog.find('.message').html('Could not connect to your lab environment:');
                dialog.find('.error_msg').html(e);
                dialog.find('input.ok').one('click', function() {
                    $.dialog.close();
                });
                dialog.find('input.retry').one('click', function() {
                    $.dialog.close();
                    location.reload();
                });
                dialog.dialog(element);
            }

            if (terminal_connected) {
                /* Reset keepalive timer. */
                if (configuration.timeouts['keepalive']) {
                    if (keepalive_timer) clearTimeout(keepalive_timer);
                    keepalive_timer = setTimeout(
                        keepalive,
                        fuzz_timeout(configuration.timeouts['keepalive'])
                    );
                }

                /* Reset idle timer. */
                if (configuration.timeouts['idle']) {
                    if (idle_timer) clearTimeout(idle_timer);
                    idle_timer = setTimeout(idle, configuration.timeouts['idle']);
                }
            }

            /* Close the dialog. */
            $.dialog.close();
        } else if (stack.status == 'LAUNCH_PENDING') {
            if (status_timer) clearTimeout(status_timer);
            status_timer = setTimeout(
                get_user_stack_status,
                fuzz_timeout(configuration.timeouts['status'])
            );
        } else {
            /* Unexpected status.  Display error message. */
            var dialog = $('#launch_error');
            dialog.find('.message').html('There was a problem preparing your lab environment:');
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
                keepalive_timer = setTimeout(
                    keepalive,
                    fuzz_timeout(configuration.timeouts['keepalive'])
                );
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
                if (check.status == 'CHECK_PROGRESS_COMPLETE') {
                    dialog = $('#check_complete');
                    dialog.find('.check_pass').html(data.pass);
                    dialog.find('.check_total').html(data.total);
                    dialog.find('input.ok').one('click', function() {
                        $.dialog.close();
                    });
                    dialog.dialog(element);
                } else if (check.status == 'CHECK_PROGRESS_PENDING') {
                    dialog = $('#check_pending');
                    dialog.dialog(element);
                    if (check_timer) clearTimeout(check_timer);
                    check_timer = setTimeout(get_check_status, configuration.timeouts['check']);
                } else {
                    /* Unexpected status.  Display error message. */
                    show_error(check.error_msg);
                }
            } else if (check.status == 'CHECK_PROGRESS_PENDING') {
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

        /* Disconnect terminal. */
        terminal_client.disconnect()

        var dialog = $('#idle');
        dialog.find('input.ok').one('click', function() {
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

            /* Disconnect terminal. */
            terminal_client.disconnect()

            /* Start over. */
            get_user_stack_status(true, true);
        });

        dialog.dialog(element);
    };

    init();
}
