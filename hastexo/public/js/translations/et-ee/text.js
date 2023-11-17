
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
    "After you reset, you will need to retrace your steps up to this point.": "Peale taastamist pead k\u00f5ik oma senised sammud kuni praeguseni uuesti l\u00e4bima.",
    "Are you sure?": "Kas oled kindel?",
    "Attention!": "T\u00e4helepanu!",
    "Click 'OK' to return to your terminal in this window.": "Vajuta 'OK', et naaseda oma laborikeskkonda selles aknas.",
    "Could not connect to your lab environment. The client detected an unexpected error. The server's error message was:": "Laborikeskkonnaga ei \u00f5nnestunud \u00fchendust luua. Klient tuvastas ootamatu vea. Serveri veateade oli:",
    "Could not connect to your lab environment:": "Laborikeskkonnaga ei \u014dnnestunud \u00fchendust luua.",
    "Don't panic!  It may take a few minutes.": "Ole mureta! Siin v\u00f5ib m\u00f5ni minut aega minna.",
    "Hints": "Vihjed",
    "In a timed exam, the timer will continue to run while your environment is being reset.": "Ajastatud eksami k\u00e4igus, taimer t\u00f6\u00f6tab keskkonna taastamise ajal edasi.",
    "Lost connection to your lab environment.": "\u00dchendus sinu laborikeskkonnaga katkes.",
    "Please wait": "Palun oota",
    "Progress check result": "Kontrollitud tulemus",
    "Resetting will return your lab environment to a pristine state.": "Taastamine viib sinu laborikeskkonna tagasi algsesse seisu.",
    "Sorry!": "Vabandust!",
    "The remote server unexpectedly disconnected. You can try closing your browser window, and returning to this page in a few minutes.": "Kaugserver katkestas ootamatult \u00fchenduse. V\u00f5ite proovida brauseriakna sulgeda ja m\u00f5ne minuti p\u00e4rast sellele lehele naasta.",
    "There was a problem checking your progress:": "Tulemuste kontolli k\u00e4igus esines t\u00f5rge:",
    "There was a problem preparing your lab environment:": "Sinu laborikeskkonna ettevalmistamisel esines t\u00f5rge:",
    "This may take several minutes to complete.": "See v\u00f5ib m\u00f5ni minut aega v\u00f5tta.",
    "Timeout when checking progress.": "Tulemuste kontrollimiseks seatud ajalimiit t\u00e4is.",
    "Timeout when launching stack.": "Keskkonna loomiseks seatud ajalimiit t\u00e4is.",
    "Unexpected result: ": "Ootamatu tulemus: ",
    "We think you're busy elsewhere.": "Arvame, et oled mujal h\u00f5ivatud.",
    "We're preparing your lab environment.": "Valmistame sinu laborikeskkonda.",
    "Working": "T\u00f6\u00f6 k\u00e4ib",
    "You cannot undo this action.": "Seda toimingut ei saa tagasi v\u00f5tta.",
    "You completed {passed} out of {total} tasks.": "L\u00e4bisid edukalt {passed} \u00fclesannet {total}-st.",
    "You've been inactive here for a while, so we paused your lab environment.": "Oled siin juba m\u00f5nda aega mitteaktiivne olnud seet\u00f5ttu peatasime sinu laborikeskkonna.",
    "You've reached the time limit allocated to you for using labs.": "Oled j\u00f5udnud sinule laborite kasutamiseks m\u00e4\u00e4ratud ajalimiidini.",
    "Your lab environment is undergoing automatic maintenance. Please try again in a few minutes.": "Teie laborikeskkond on hetkel automaatsel hooldusel. Palun proovi m\u00f5ne minuti p\u00e4rast uuesti.",
    "Your lab environment is undergoing maintenance": "Teie laborikeskkond on hetkel hoolduses",
    "Your lab is currently active in a separate window.": "Sinu laborikeskkond on hetkel aktiivne teises aknas."
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
    "DATE_FORMAT": "j. F Y",
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
    "DECIMAL_SEPARATOR": ",",
    "FIRST_DAY_OF_WEEK": 0,
    "MONTH_DAY_FORMAT": "j. F",
    "NUMBER_GROUPING": 0,
    "SHORT_DATETIME_FORMAT": "m/d/Y P",
    "SHORT_DATE_FORMAT": "d.m.Y",
    "THOUSAND_SEPARATOR": "\u00a0",
    "TIME_FORMAT": "G:i",
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
