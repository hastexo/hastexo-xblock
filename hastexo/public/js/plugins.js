/* A cached version of jQuery's getScript. */
jQuery.cachedScript = function(url, options) {
    options = $.extend( options || {}, {
        dataType: "script",
        cache: true,
        url: url
    });

    return jQuery.ajax(options);
};

/* A very, very simple jQuery dialog.    Based on
 * http://github.com/kylefox/jquery-modal. */
(function($) {
    var current = null;

    $.dialog = function(el, element, options) {
        $.dialog.close();
        var remove, target;
        this.$body = $('body');
        this.$block = $(element);
        this.options = $.extend({}, $.dialog.defaults, options);
        this.$elm = el;
        this.$body.append(this.$elm);
        this.open();
    };

    $.dialog.prototype = {
        constructor: $.dialog,

        open: function() {
            var m = this;
            this.block();
            this.show();
        },

        close: function() {
            this.unblock();
            this.hide();
        },

        block: function() {
            this.overlay = $('<div class="dialog-overlay"></div>');
            this.$block.css('position', 'relative');
            this.$block.append(this.overlay);
        },

        unblock: function() {
            this.overlay.children().appendTo(this.$body);
            this.overlay.remove();
            this.$block.css('position', '');
        },

        show: function() {
            this.$elm.addClass(this.options.dialogClass + ' current');
            this.$elm.appendTo(this.overlay);
            this.$elm.show();
        },

        hide: function() {
            this.$elm.removeClass('current');
            var _this = this;
            this.$elm.hide(0);
        },
    };

    $.dialog.close = function(event) {
        if (!current)
            return;

        if (event)
            event.preventDefault();

        current.close();
        var that = current.$elm;
        current = null;
        return that;
    };

    /* Returns if there currently is an active dialog. */
    $.dialog.isActive = function () {
        return current ? true : false;
    }

    $.dialog.defaults = {
        dialogClass: 'dialog'
    };

    $.fn.dialog = function(element, options){
        if (this.length === 1) {
            current = new $.dialog(this, element, options);
        }
        return this;
    };
})(jQuery);
