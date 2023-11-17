function HastexoGuacamoleClient(configuration) {
    "use strict";

    // State
    var guac_client = undefined;
    var idle_timer = undefined;
    var keepalive_timer = undefined;
    var terminal_client = undefined;
    var terminal_connected = false;
    var terminal_element = undefined;


    // Process terminal URL.
    var prot_map = {
        "http:":  "ws:",
        "https:": "wss:"
    };
    var terminal_ws_url = prot_map[location.protocol] + '//' + location.hostname + configuration.terminal_url;

    // Initialize Guacamole Client
    guac_client = new Guacamole.Client(
        new Guacamole.WebSocketTunnel(terminal_ws_url + "websocket-tunnel")
    );

    terminal_element = guac_client.getDisplay().getElement();

    /* Mouse handling */
    var mouse = new Guacamole.Mouse(terminal_element);

    mouse.onmousedown =
    mouse.onmouseup   =
    mouse.onmousemove = function(mouseState) {
        guac_client.sendMouseState(mouseState);

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
                guac_client.sendKeyEvent(1, keysym);
            }, 50);
        } else {
            guac_client.sendKeyEvent(1, keysym);
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
                guac_client.sendKeyEvent(0, keysym);
            }, 50);
        } else {
            guac_client.sendKeyEvent(0, keysym);
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
            var x = window.scrollX, y = window.scrollY;
            $(this).focus();
            window.scrollTo(x, y);
            }, function() {
            $(this).blur();
            }
        )
        /* Release all keys when the element loses focus. */
        .blur(function() {
            keyboard.reset();
        });

    /* Handle copy events from within the terminal. */
    guac_client.onclipboard = function(stream, mimetype) {
        var reader = new Guacamole.StringReader(stream);

        reader.ontext = function(text) {
            terminal_client.onclipboard(text);
        }
    }

    guac_client.onerror = function(error) {
        terminal_client.onerror(error);
    }

    /* Returns a fuzzy timeout that varies between plus or minus 25% of the
     * base value. */
    var fuzz_timeout = function(timeout) {
        var range = Math.floor(timeout * 0.25);
        var fuzz = Math.random() * (range * 2 + 1) - range;

        return timeout + fuzz;
    };

    var keepalive = function() {
        $.ajax({
            type: 'POST',
            headers: {
                'X-CSRFToken': configuration.csrftoken
            },
            url: configuration.keepalive_url,
            mode: 'same-origin',
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

    var idle = function() {
        clearTimeout(keepalive_timer);
        guac_client.disconnect()
        terminal_connected = false;
        terminal_client.onidle(false);
    };

    terminal_client = {
        connect(port = '') {
            var port = ((port) ? port : configuration.port)
            if (terminal_connected) {
                guac_client.disconnect();
                terminal_connected = false;
            }
        
            try {
                guac_client.connect($.param({
                    'stack': configuration.stack_name,
                    'read_only': configuration.read_only,
                    'width': configuration.width,
                    'height': configuration.height,
                    'port': port,
                }));
                terminal_connected = true;
            } catch (e) {
                console.warn(e);
                terminal_connected = false;
                throw e;
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
        },

        disconnect() {
            if (keepalive_timer) clearTimeout(keepalive_timer);
            if (idle_timer) clearTimeout(idle_timer);
            guac_client.disconnect();
            terminal_connected = false;
        },

        getDisplay() {
            return guac_client.getDisplay();
        },

        onclipboard(text) {
            return text;
        },

        paste(text) {
            if ($(terminal_element).is(":focus")) {
                var stream = guac_client.createClipboardStream('text/plain');
                var writer = new Guacamole.StringWriter(stream);
                writer.sendText(text);
                writer.sendEnd();
            }
        },

        onerror(error) {
            throw error;
        },

        onidle(pause) {
            return pause;
        }
    }

    return terminal_client;
}
