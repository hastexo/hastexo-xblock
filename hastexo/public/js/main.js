function HastexoXBlock(runtime, element, configuration) {
    "use strict";

    // State
    var stack = undefined;
    var check = undefined;
    var status_timer = undefined;
    var check_timer = undefined;
    var terminal_client = undefined;
    var terminal_element = undefined;
    var dialog_container = undefined;
    var gettext = undefined;
    var lab_new_window = undefined;

    if ('HastexoI18N' in window) {
        gettext = function(string) {
            return window.HastexoI18N.gettext(string);
        };

    } else {
        // No translations
        gettext = function(string) { return string; };
    }

    var init = function() {

        if (configuration.hidden) {
            $('.xblock-student_view-hastexo').hide();
            get_user_stack_status(true);
        } else {
            /* Construct the layout for instructions and terminal */
            construct_layout();
        }

        /* Set dialog container. */
        dialog_container = $(element).find('.hastexblock')[0];

        /* Bind reset button action. */
        $(element).find('.buttons.bar > .reset').on('click', reset_dialog);

        $(element).find('.buttons.bar > .launch').on('click', launch_new_window);

        /* Display progress check button, if there are tests. */
        if (configuration.has_tests) {
            var button = $(element).find('.buttons .check');
            button.attr("value", configuration.progress_check_label);
            button.show();
            button.on('click', get_check_status);
        }

        /* Display ports dropdown, if there are any. */
        if (configuration.ports.length > 0) {
            var select = $(element).find('.buttons .port');
            $.each(configuration.ports, function(i, port) {
                select.append($('<option>', {
                    value: port['number'],
                    text: port['name'],
                    selected: port['number'] == configuration.port ? true : false
                }));
            });
            select.show();
            select.change(function() {
                var port = parseInt($(this).val());
                $.ajax({
                    type: 'POST',
                    url: runtime.handlerUrl(element, 'set_port'),
                    data: JSON.stringify({
                        port: port
                    }),
                    dataType: 'json'
                }).done(function() {
                    location.reload();
                });
            });
        }

        /* Set container CSS class, if graphical. */
        if (configuration.protocol != "ssh") {
            $('#container').addClass('graphical');
        }

        // Configure the size of the lab window.
        configuration['width'] = $('#terminal').width();
        configuration['height'] = $('#terminal').height()

        /* Initialize Guacamole Client */
        terminal_client = HastexoGuacamoleClient(configuration)
        terminal_element = terminal_client.getDisplay().getElement();

        /* Show the terminal.  */
        $("#terminal").append(terminal_element);

        /* Disconnect on tab close. */
        window.onunload = function() {
            terminal_client.disconnect();
        };

        /* Error handling. */
        terminal_client.onerror = function(guac_error) {
            /* Reset and disconnect. */
            stack = null;
            terminal_client.disconnect();

            var dialog = $('#launch_error');
            var dialog_message = gettext(
                "Could not connect to your lab environment. " +
                "The client detected an unexpected error. " +
                "The server's error message was:");
            var error_message = guac_error.message;
            /* Special-case the unhelpful "Aborted. See logs"
                * message, indicating that although we did have a
                * working connection earlier, we've now lost it (as
                * opposed to never being able to connect to the
                * upstream web socket at all). For any other message,
                * just pass through the error received from
                * upstream. */
            if (guac_error.message.toLowerCase().startsWith('aborted')) {
                dialog_message = gettext("Lost connection to your lab environment.");
                error_message = gettext(
                    "The remote server unexpectedly disconnected. " +
                    "You can try closing your browser window, " +
                    "and returning to this page in a few minutes.");
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
            dialog.dialog(dialog_container);
        };

        terminal_client.onidle = function(pause) {
            /* We're idle; clear stack info.  */
            stack = null;
    
            var dialog = $('#idle');
            if (pause) {
                dialog.find('.message').html(gettext('Your lab is currently active in a separate window.'));
            }
            dialog.find('input.ok').one('click', function() {
                if (lab_new_window) {
                    // We're coming back to LMS from a separate lab window
                    lab_new_window.close()
                }
                /* Start over. */
                location.reload();
            });
            dialog.dialog(dialog_container);
        };

        /* Handle paste events. */
        $(document).on('paste', function(e) {
            var text = e.originalEvent.clipboardData.getData('text/plain');
            terminal_client.paste(text);
        });

        // handle copy events from within the terminal.
        terminal_client.onclipboard = function(text) {
            try {
                navigator.clipboard.writeText(text);
            } catch (error) {
                // Write failed.
                console.warn("Failed to write to clipboard");
                console.error(error);
            }
        }

        get_user_stack_status(true);
    };

    var construct_layout = function() {
        var instructions_layout = configuration.instructions_layout;

        /* 'above' is the default layout and doesn't require any changes */
        if (instructions_layout != 'above') {
            /* check if an element with a class "lab_instructions" exists */
            if ($('.lab_instructions')[0]) {

                /* define the layout object for terminal */
                var terminal;

                /* define the layout object for lab intructions */
                var lab_instructions;

                /* find the parent of vertical elements */
                var layout_parent = $('.vert-mod');

                /* find the vertical element that contains the terminal */
                var terminal_parent = $('#terminal').closest('.vert');

                /* check if lab instructions are in a nested block */
                if ($(terminal_parent).find('.lab_instructions').length > 0) {
                    /* Consider the terminal parent as the parent of our layout objects */
                    layout_parent = terminal_parent
                    lab_instructions = $('.lab_instructions')
                    terminal = $('.hastexblock')
                }
                else {
                    /* find the vertical element that contains the lab instructions */
                    lab_instructions = $('.lab_instructions').closest('.vert');
                    terminal = terminal_parent
                }
                if (instructions_layout === 'left' || instructions_layout === 'right') {
                    $('.lab_instructions').addClass('instructions-side-view');
                    $('#container').addClass('terminal-side-view');
                    $(layout_parent).addClass('content-side-by-side');
                    /* Make sure the xblock fits to content area */
                    $(layout_parent).height($('.hastexblock').height() + 20);

                    $(lab_instructions).css({
                        'float': [instructions_layout],
                        'width' : '40%',
                        'height': '100%'
                    });
                    $(terminal).css({
                        ['margin-' + instructions_layout] : '40%',
                        'height': '100%'
                    });
                    /* if terminal is on the left side, move terminal buttons to the left as well */
                    if (instructions_layout === 'right') {
                        $(element).find('.buttons').css({'text-align': 'left'});
                    };
                }
                if (instructions_layout === 'below') {
                    $(lab_instructions).insertAfter($(terminal));
                };
            } else {
                console.warn('Unable to modify content layout, elements not found');
            };
        };
    };

    /* Returns a fuzzy timeout that varies between plus or minus 25% of the
     * base value. */
    var fuzz_timeout = function(timeout) {
        var range = Math.floor(timeout * 0.25);
        var fuzz = Math.random() * (range * 2 + 1) - range;

        return timeout + fuzz;
    };

    var get_user_stack_status = function(initialize = false, reset = false) {
        $('#launch_pending').dialog(dialog_container);
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
            if (changed && !configuration.hidden) {
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

    var update_user_stack_status = function (stack) {
        if (stack.status == 'CREATE_COMPLETE' || stack.status == 'RESUME_COMPLETE') {
            if (stack.error_msg && stack.error_msg.includes("You've reached the time limit")) {
                var dialog = $('#launch_error');
                dialog.find('.header').html(gettext('Attention!'));
                dialog.find('.message').html(gettext(stack.error_msg));
                dialog.find('.error_msg').hide()
                dialog.find('input.retry').hide()
                dialog.find('input.ok').one('click', function() {
                    $.dialog.close();
                });
                dialog.dialog(dialog_container);
            }
            /* Connect to the terminal server. */
            try {
                terminal_client.connect();
            } catch (e) {
                /* Connection error.  Display error message. */
                var dialog = $('#launch_error');
                dialog.find('.message').html(gettext('Could not connect to your lab environment:'));
                dialog.find('.error_msg').html(e);
                dialog.find('input.ok').one('click', function() {
                    $.dialog.close();
                });
                dialog.find('input.retry').one('click', function() {
                    $.dialog.close();
                    location.reload();
                });
                dialog.dialog(dialog_container);
            }

            /* Close the dialog when user acknowledgement is not required. */
            if (!stack.error_msg && !stack.error_msg.includes("You've reached the time limit")) {
                $.dialog.close();
            };
        } else if (stack.status == 'LAUNCH_PENDING') {
            if (status_timer) clearTimeout(status_timer);
            status_timer = setTimeout(
                get_user_stack_status,
                fuzz_timeout(configuration.timeouts['status'])
            );
        } else if (stack.status == 'SUSPEND_PENDING' || stack.status == 'DELETE_PENDING') {
            /* Stack is pending.  Display retry message. */
            var dialog = $('#launch_error');
            var dialog_msg = gettext("Your lab environment is undergoing maintenance");
            var error_msg = gettext(
                "Your lab environment is undergoing automatic maintenance. " +
                "Please try again in a few minutes.");
            dialog.find('.message').html(dialog_msg);
            dialog.find('.error_msg').html(error_msg);
            dialog.find('input.ok').one('click', function() {
                $.dialog.close();
            });
            dialog.find('input.retry').one('click', function() {
                $.dialog.close();
                location.reload();
            });
            dialog.dialog(dialog_container);
        } else {
            /* Unexpected status.  Display error message. */
            var dialog = $('#launch_error');
            dialog.find('.message').html(gettext('There was a problem preparing your lab environment:'));
            dialog.find('.error_msg').html(stack.error_msg);
            dialog.find('input.ok').one('click', function() {
                $.dialog.close();
            });
            dialog.find('input.retry').one('click', function() {
                $.dialog.close();
                location.reload();
            });
            dialog.dialog(dialog_container);
        }
    };

    var get_check_status = function() {
        $('#check_pending').dialog(dialog_container);

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
            dialog.dialog(dialog_container);
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
                    var result_message = gettext(
                        // {passed} and {total} are to be replaced, do not translate.
                        "You completed {passed} out of {total} tasks.");
                    result_message = result_message.replace('{passed}', data.pass.toString()).replace('{total}', data.total.toString());
                    dialog = $('#check_complete');
                    dialog.find('.check_result_heading').html(gettext(configuration.progress_check_result_heading));
                    dialog.find('.check_result_message').html(result_message);
                    dialog.find('input.ok').one('click', function() {
                        $.dialog.close();
                    });
                    var hints_title = dialog.find('.hints_title').hide();
                    var hints = dialog.find('.hints').empty().hide();
                    if (configuration.show_feedback) {
                        if (configuration.show_hints_on_error) {
                            if (data.errors.length > 0) {
                                $.each(data.errors, function(i, error) {
                                    var pre = $('<pre>', {text: error});
                                    var li = $('<li>').append(pre);
                                    hints.append(li);
                                });
                                hints_title.show();
                                hints.show();
                            }
                        }
                    } else {
                        dialog.find('.check_result_message').hide()
                    }
                    dialog.dialog(dialog_container);
                } else if (check.status == 'CHECK_PROGRESS_PENDING') {
                    dialog = $('#check_pending');
                    dialog.dialog(dialog_container);
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

    var reset_dialog = function() {
        var dialog = $('#reset_dialog');

        /* add an extra warning text for timed exams */
        if ($(".exam-timer-clock")[0]){
            $('.exam-warning').css('display', 'inline-block');
        }

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

        dialog.dialog(dialog_container);
    };

    var launch_new_window = function() {
        terminal_client.onidle(true);
        
        lab_new_window = window.open(
            runtime.handlerUrl(element, 'launch_new_window'));
    }

    init();
}
