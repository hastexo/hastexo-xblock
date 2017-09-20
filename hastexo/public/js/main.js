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
            get_user_stack_status(true);
        });
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
            /* Set container CSS class, if graphical. */
            if (configuration.protocol != "ssh") {
                $('#container').addClass('graphical');
            }

            /* Start the terminal.  */
            var display = document.getElementById("terminal");

            display.appendChild(terminal_client.getDisplay().getElement());

            terminal_client.onerror = function(guac_error) {
                /* Unexpected status.  Display error message. */
                var dialog = $('#launch_error');
                dialog.find('.error_msg').html(guac_error.message);
                dialog.find('input.ok').one('click', function() {
                    $.dialog.close();
                });
                dialog.find('input.retry').one('click', function() {
                    $.dialog.close();
                    location.reload();
                });
                dialog.dialog(element);
            };

            var data = $.param({
                'protocol': configuration.protocol,
                'width': $('#terminal').width(),
                'height': $('#terminal').height(),
                'ip': stack.ip,
                'user': stack.user,
                'key': stack.key,
                'password': stack.password
            });

            terminal_client.connect(data);

            window.onunload = function() {
                terminal_client.disconnect();
            };

            /* Mouse handling */
            var mouse = new Guacamole.Mouse(terminal_client.getDisplay().getElement());

            mouse.onmousedown =
            mouse.onmouseup   =
            mouse.onmousemove = function(mouseState) {
                terminal_client.sendMouseState(mouseState);
            };

            /* Keyboard handling */
            var keyboard = new Guacamole.Keyboard(document);

            keyboard.onkeydown = function (keysym) {
                terminal_client.sendKeyEvent(1, keysym);
            };

            keyboard.onkeyup = function (keysym) {
                terminal_client.sendKeyEvent(0, keysym);
            };

            // Release all keys when window loses focus
            window.onblur = function () {
                keyboard.reset();
            };

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
            /* Disconnect terminal. */
            terminal_client.disconnect()

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
