
            (function(global){
                var HastexoI18N = {
                  init: function() {


'use strict';
{
  const globals = this;
  const django = globals.django || (globals.django = {});


  django.pluralidx = function(n) {
    const v = (n != 1);
    if (typeof v === 'boolean') {
      return v ? 1 : 0;
    } else {
      return v;
    }
  };


  /* gettext library */

  django.catalog = django.catalog || {};

  const newcatalog = {
    "After you reset, you will need to retrace your steps up to this point.": "\u0906\u092a\u0915\u0947 \u0926\u094d\u0935\u093e\u0930\u093e \u0930\u0940\u0938\u0947\u091f \u0915\u0930\u0928\u0947 \u0915\u0947 \u092c\u093e\u0926, \u0906\u092a\u0915\u094b \u0907\u0938 \u092c\u093f\u0902\u0926\u0941 \u0924\u0915 \u0905\u092a\u0928\u0947 \u0915\u0926\u092e\u094b\u0902 \u0915\u094b \u092a\u0941\u0928\u0903 \u092a\u094d\u0930\u093e\u092a\u094d\u0924 \u0915\u0930\u0928\u0947 \u0915\u0940 \u0906\u0935\u0936\u094d\u092f\u0915\u0924\u093e \u0939\u094b\u0917\u0940\u0964",
    "Are you sure?": "\u0915\u094d\u092f\u093e \u0906\u092a\u0915\u094b \u092f\u0915\u0940\u0928 \u0939\u0948?",
    "Attention!": "\u0927\u094d\u092f\u093e\u0928!",
    "Click 'OK' to return to your terminal in this window.": "\u0907\u0938 \u0935\u093f\u0902\u0921\u094b \u092e\u0947\u0902 \u0905\u092a\u0928\u0947 \u091f\u0930\u094d\u092e\u093f\u0928\u0932 \u092a\u0930 \u0932\u094c\u091f\u0928\u0947 \u0915\u0947 \u0932\u093f\u090f '\u0913\u0915\u0947' \u092a\u0930 \u0915\u094d\u0932\u093f\u0915 \u0915\u0930\u0947\u0902\u0964",
    "Could not connect to your lab environment. The client detected an unexpected error. The server's error message was:": "\u0938\u0930\u094d\u0935\u0930 \u0915\u093e \u0924\u094d\u0930\u0941\u091f\u093f \u0938\u0902\u0926\u0947\u0936 \u0925\u093e:",
    "Could not connect to your lab environment:": "\u0906\u092a\u0915\u0947 \u092a\u094d\u0930\u092f\u094b\u0917\u0936\u093e\u0932\u093e \u092a\u0930\u093f\u0935\u0947\u0936 \u0938\u0947 \u0915\u0928\u0947\u0915\u094d\u091f \u0928\u0939\u0940\u0902 \u0939\u094b \u0938\u0915\u093e:",
    "Don't panic!  It may take a few minutes.": "\u0918\u092c\u0921\u093c\u093e\u090f\u0902 \u0928\u0939\u0940\u0902! \u0907\u0938\u092e\u0947\u0902 \u0915\u0941\u091b \u092e\u093f\u0928\u091f \u0932\u0917 \u0938\u0915\u0924\u0947 \u0939\u0948\u0902\u0964",
    "Hints": "\u0938\u0902\u0915\u0947\u0924",
    "In a timed exam, the timer will continue to run while your environment is being reset.": "\u090f\u0915 \u0938\u092e\u092f\u092c\u0926\u094d\u0927 \u092a\u0930\u0940\u0915\u094d\u0937\u093e \u092e\u0947\u0902, \u091f\u093e\u0907\u092e\u0930 \u0924\u092c \u0924\u0915 \u091a\u0932\u0924\u093e \u0930\u0939\u0947\u0917\u093e \u091c\u092c \u0924\u0915 \u0915\u093f \u0906\u092a\u0915\u093e \u0935\u093e\u0924\u093e\u0935\u0930\u0923 \u0930\u0940\u0938\u0947\u091f \u0915\u093f\u092f\u093e \u091c\u093e \u0930\u0939\u093e \u0939\u0948\u0964",
    "Lost connection to your lab environment.": "\u0906\u092a\u0915\u0947 \u092a\u094d\u0930\u092f\u094b\u0917\u0936\u093e\u0932\u093e \u0935\u093e\u0924\u093e\u0935\u0930\u0923 \u0938\u0947 \u0938\u0902\u092c\u0902\u0927 \u091f\u0942\u091f \u0917\u092f\u093e\u0964",
    "Please wait": "\u0915\u0943\u092a\u092f\u093e \u092a\u094d\u0930\u0924\u0940\u0915\u094d\u0937\u093e \u0915\u0930\u0947\u0902",
    "Progress check result": "\u092a\u094d\u0930\u0917\u0924\u093f \u091c\u093e\u0902\u091a \u092a\u0930\u093f\u0923\u093e\u092e",
    "Resetting will return your lab environment to a pristine state.": "\u0930\u0940\u0938\u0947\u091f \u0915\u0930\u0928\u0947 \u0938\u0947 \u0906\u092a\u0915\u093e \u0932\u0948\u092c \u0935\u093e\u0924\u093e\u0935\u0930\u0923 \u090f\u0915 \u092a\u0941\u0930\u093e\u0928\u0940 \u0938\u094d\u0925\u093f\u0924\u093f \u092e\u0947\u0902 \u0935\u093e\u092a\u0938 \u0906 \u091c\u093e\u090f\u0917\u093e\u0964",
    "Sorry!": "\u092e\u093e\u092b\u093c \u0915\u0930\u0928\u093e!",
    "The remote server unexpectedly disconnected. You can try closing your browser window, and returning to this page in a few minutes.": "\u0926\u0942\u0930\u0938\u094d\u0925 \u0938\u0930\u094d\u0935\u0930 \u0905\u0928\u092a\u0947\u0915\u094d\u0937\u093f\u0924 \u0930\u0942\u092a \u0938\u0947 \u0921\u093f\u0938\u094d\u0915\u0928\u0947\u0915\u094d\u091f \u0939\u094b \u0917\u092f\u093e. \u0906\u092a \u0905\u092a\u0928\u0940  \u092c\u094d\u0930\u093e\u0909\u091c\u093c\u0930 \u0935\u093f\u0902\u0921\u094b' \u0915\u094b \u092c\u0902\u0926 \u0915\u0930\u0928\u0947 \u0914\u0930 \u0915\u0941\u091b \u0939\u0940 \u092e\u093f\u0928\u091f\u094b\u0902 \u092e\u0947\u0902 \u0907\u0938 \u092a\u0943\u0937\u094d\u0920 \u092a\u0930 \u0932\u094c\u091f\u0928\u0947 \u0915\u093e \u092a\u094d\u0930\u092f\u093e\u0938 \u0915\u0930 \u0938\u0915\u0924\u0947 \u0939\u0948\u0902\u0964",
    "There was a problem checking your progress:": "\u0906\u092a\u0915\u0940 \u092a\u094d\u0930\u0917\u0924\u093f \u0915\u0940 \u091c\u093e\u0901\u091a \u0915\u0930\u0928\u0947 \u092e\u0947\u0902 \u0938\u092e\u0938\u094d\u092f\u093e \u0939\u0941\u0908:",
    "There was a problem preparing your lab environment:": "\u0906\u092a\u0915\u0940 \u092a\u094d\u0930\u092f\u094b\u0917\u0936\u093e\u0932\u093e \u0915\u0947 \u0935\u093e\u0924\u093e\u0935\u0930\u0923 \u0915\u094b \u0924\u0948\u092f\u093e\u0930 \u0915\u0930\u0928\u0947 \u092e\u0947\u0902 \u0915\u094b\u0908 \u0938\u092e\u0938\u094d\u092f\u093e \u0925\u0940:",
    "This may take several minutes to complete.": "\u0907\u0938\u0947 \u092a\u0942\u0930\u093e \u0939\u094b\u0928\u0947 \u092e\u0947\u0902 \u0915\u0908 \u092e\u093f\u0928\u091f \u0932\u0917 \u0938\u0915\u0924\u0947 \u0939\u0948\u0902\u0964",
    "Timeout when checking progress.": "\u092a\u094d\u0930\u0917\u0924\u093f \u0915\u0940 \u091c\u093e\u0901\u091a \u0915\u0930\u0924\u0947 \u0938\u092e\u092f \u0938\u092e\u092f\u092c\u093e\u0939\u094d\u092f\u0964",
    "Timeout when launching stack.": "\u0938\u094d\u091f\u0948\u0915 \u0932\u0949\u0928\u094d\u091a \u0915\u0930\u0924\u0947 \u0938\u092e\u092f \u091f\u093e\u0907\u092e\u0906\u0909\u091f\u0964",
    "Unexpected result: ": "\u0905\u0928\u092a\u0947\u0915\u094d\u0937\u093f\u0924 \u092a\u0930\u093f\u0923\u093e\u092e:",
    "We think you're busy elsewhere.": "\u0939\u092e\u0947\u0902 \u0932\u0917\u0924\u093e \u0939\u0948 \u0915\u093f \u0906\u092a \u0915\u0939\u0940\u0902 \u0914\u0930 \u0935\u094d\u092f\u0938\u094d\u0924 \u0939\u0948\u0902\u0964",
    "We're preparing your lab environment.": "\u0939\u092e \u0906\u092a\u0915\u093e \u092a\u094d\u0930\u092f\u094b\u0917\u0936\u093e\u0932\u093e \u0935\u093e\u0924\u093e\u0935\u0930\u0923 \u0924\u0948\u092f\u093e\u0930 \u0915\u0930 \u0930\u0939\u0947 \u0939\u0948\u0902\u0964",
    "Working": "\u0915\u093e\u0930\u094d\u092f\u0930\u0924",
    "You cannot undo this action.": "\u0906\u092a \u0907\u0938 \u0915\u094d\u0930\u093f\u092f\u093e \u0915\u094b \u092a\u0942\u0930\u094d\u0935\u0935\u0924 \u0928\u0939\u0940\u0902 \u0915\u0930 \u0938\u0915\u0924\u0947\u0964",
    "You completed {passed} out of {total} tasks.": "\u0906\u092a\u0928\u0947 {passed} \u0915\u093e\u0930\u094d\u092f\u094b\u0902 \u092e\u0947\u0902 \u0938\u0947 {total} \u0915\u0930 \u0932\u093f\u090f \u0939\u0948\u0902\u0964",
    "You've been inactive here for a while, so we paused your lab environment.": "\u0906\u092a \u092f\u0939\u093e\u0902 \u0915\u0941\u091b \u0938\u092e\u092f \u0938\u0947 \u0928\u093f\u0937\u094d\u0915\u094d\u0930\u093f\u092f \u0939\u0948\u0902, \u0907\u0938\u0932\u093f\u090f \u0939\u092e\u0928\u0947 \u0906\u092a\u0915\u0947 \u092a\u094d\u0930\u092f\u094b\u0917\u0936\u093e\u0932\u093e \u092a\u0930\u093f\u0935\u0947\u0936 \u0915\u094b \u0930\u094b\u0915 \u0926\u093f\u092f\u093e \u0939\u0948\u0964",
    "You've reached the time limit allocated to you for using labs.": "\u0906\u092a \u092a\u094d\u0930\u092f\u094b\u0917\u0936\u093e\u0932\u093e\u0913\u0902 \u0915\u093e \u0909\u092a\u092f\u094b\u0917 \u0915\u0930\u0928\u0947 \u0915\u0947 \u0932\u093f\u090f \u0906\u092a\u0915\u094b \u0906\u0935\u0902\u091f\u093f\u0924 \u0938\u092e\u092f \u0938\u0940\u092e\u093e \u0924\u0915 \u092a\u0939\u0941\u0901\u091a \u091a\u0941\u0915\u0947 \u0939\u0948\u0902\u0964",
    "Your lab environment is undergoing automatic maintenance. Please try again in a few minutes.": "\u0906\u092a\u0915\u093e \u092a\u094d\u0930\u092f\u094b\u0917\u0936\u093e\u0932\u093e \u0935\u093e\u0924\u093e\u0935\u0930\u0923 \u0938\u094d\u0935\u091a\u093e\u0932\u093f\u0924 \u0930\u0916\u0930\u0916\u093e\u0935 \u0915\u0947 \u0926\u094c\u0930 \u0938\u0947 \u0917\u0941\u091c\u0930 \u0930\u0939\u093e \u0939\u0948\u0964 \u0915\u0943\u092a\u092f\u093e \u092a\u0941\u0928: \u092a\u094d\u0930\u092f\u093e\u0938 \u0915\u0930\u0947\u0902 \u0915\u0941\u091b \u092e\u093f\u0928\u091f\u094b\u0902 \u092e\u0947\u0902\u0964",
    "Your lab environment is undergoing maintenance": "\u0906\u092a\u0915\u0947 \u092a\u094d\u0930\u092f\u094b\u0917\u0936\u093e\u0932\u093e \u0935\u093e\u0924\u093e\u0935\u0930\u0923 \u0915\u093e \u0930\u0916\u0930\u0916\u093e\u0935 \u0915\u093f\u092f\u093e \u091c\u093e \u0930\u0939\u093e \u0939\u0948",
    "Your lab is currently active in a separate window.": "\u0906\u092a\u0915\u0940 \u092a\u094d\u0930\u092f\u094b\u0917\u0936\u093e\u0932\u093e \u0935\u0930\u094d\u0924\u092e\u093e\u0928 \u092e\u0947\u0902 \u090f\u0915 \u0905\u0932\u0917 \u0935\u093f\u0902\u0921\u094b \u092e\u0947\u0902 \u0938\u0915\u094d\u0930\u093f\u092f \u0939\u0948\u0964"
  };
  for (const key in newcatalog) {
    django.catalog[key] = newcatalog[key];
  }


  if (!django.jsi18n_initialized) {
    django.gettext = function(msgid) {
      const value = django.catalog[msgid];
      if (typeof value === 'undefined') {
        return msgid;
      } else {
        return (typeof value === 'string') ? value : value[0];
      }
    };

    django.ngettext = function(singular, plural, count) {
      const value = django.catalog[singular];
      if (typeof value === 'undefined') {
        return (count == 1) ? singular : plural;
      } else {
        return value.constructor === Array ? value[django.pluralidx(count)] : value;
      }
    };

    django.gettext_noop = function(msgid) { return msgid; };

    django.pgettext = function(context, msgid) {
      let value = django.gettext(context + '\x04' + msgid);
      if (value.includes('\x04')) {
        value = msgid;
      }
      return value;
    };

    django.npgettext = function(context, singular, plural, count) {
      let value = django.ngettext(context + '\x04' + singular, context + '\x04' + plural, count);
      if (value.includes('\x04')) {
        value = django.ngettext(singular, plural, count);
      }
      return value;
    };

    django.interpolate = function(fmt, obj, named) {
      if (named) {
        return fmt.replace(/%\(\w+\)s/g, function(match){return String(obj[match.slice(2,-2)])});
      } else {
        return fmt.replace(/%s/g, function(match){return String(obj.shift())});
      }
    };


    /* formatting library */

    django.formats = {
    "DATETIME_FORMAT": "N j, Y, P",
    "DATETIME_INPUT_FORMATS": [
      "%Y-%m-%d %H:%M:%S",
      "%Y-%m-%d %H:%M:%S.%f",
      "%Y-%m-%d %H:%M",
      "%m/%d/%Y %H:%M:%S",
      "%m/%d/%Y %H:%M:%S.%f",
      "%m/%d/%Y %H:%M",
      "%m/%d/%y %H:%M:%S",
      "%m/%d/%y %H:%M:%S.%f",
      "%m/%d/%y %H:%M"
    ],
    "DATE_FORMAT": "j F Y",
    "DATE_INPUT_FORMATS": [
      "%Y-%m-%d",
      "%m/%d/%Y",
      "%m/%d/%y",
      "%b %d %Y",
      "%b %d, %Y",
      "%d %b %Y",
      "%d %b, %Y",
      "%B %d %Y",
      "%B %d, %Y",
      "%d %B %Y",
      "%d %B, %Y"
    ],
    "DECIMAL_SEPARATOR": ".",
    "FIRST_DAY_OF_WEEK": 0,
    "MONTH_DAY_FORMAT": "j F",
    "NUMBER_GROUPING": 0,
    "SHORT_DATETIME_FORMAT": "m/d/Y P",
    "SHORT_DATE_FORMAT": "d-m-Y",
    "THOUSAND_SEPARATOR": ",",
    "TIME_FORMAT": "g:i A",
    "TIME_INPUT_FORMATS": [
      "%H:%M:%S",
      "%H:%M:%S.%f",
      "%H:%M"
    ],
    "YEAR_MONTH_FORMAT": "F Y"
  };

    django.get_format = function(format_type) {
      const value = django.formats[format_type];
      if (typeof value === 'undefined') {
        return format_type;
      } else {
        return value;
      }
    };

    /* add to global namespace */
    globals.pluralidx = django.pluralidx;
    globals.gettext = django.gettext;
    globals.ngettext = django.ngettext;
    globals.gettext_noop = django.gettext_noop;
    globals.pgettext = django.pgettext;
    globals.npgettext = django.npgettext;
    globals.interpolate = django.interpolate;
    globals.get_format = django.get_format;

    django.jsi18n_initialized = true;
  }
};


                  }
                };
                HastexoI18N.init();
                global.HastexoI18N = HastexoI18N;
            }(this));
