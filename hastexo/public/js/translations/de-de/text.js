
            (function(global){
                var HastexoI18N = {
                  init: function() {


'use strict';
{
  const globals = this;
  const django = globals.django || (globals.django = {});


  django.pluralidx = function(n) {
    const v = n == 1 ? 0 : n != 0 && n % 1000000 == 0 ? 1 : 2;
    if (typeof v === 'boolean') {
      return v ? 1 : 0;
    } else {
      return v;
    }
  };


  /* gettext library */

  django.catalog = django.catalog || {};

  const newcatalog = {
    "After you reset, you will need to retrace your steps up to this point.": "Nach dem Zur\u00fccksetzen m\u00fcssen alle Arbeitsschritte bis hierher wiederholt werden.",
    "Are you sure?": "Sicher?",
    "Attention!": "Achtung!",
    "Click 'OK' to return to your terminal in this window.": "Mit Klick auf 'OK' l\u00e4sst sich die \u00dcbungsumgebung wieder in diesem Fenster aktivieren.",
    "Could not connect to your lab environment. The client detected an unexpected error. The server's error message was:": "Kann keine Verbindung zur \u00dcbungsumgebung herstellen. Ein unerwarteter Fehler ist aufgetreten. Die Fehlermeldung des Servers lautet:",
    "Could not connect to your lab environment:": "Keine Verbindung zur \u00dcbungsumgebung.",
    "Don't panic!  It may take a few minutes.": "Keine Panik! Es dauert ein paar Minuten.",
    "Hints": "Anmerkungen",
    "In a timed exam, the timer will continue to run while your environment is being reset.": "In einer zeitlich beschr\u00e4nkten Pr\u00fcfung l\u00e4uft die Zeit w\u00e4hrend des Zur\u00fccksetzens weiter.",
    "Lost connection to your lab environment.": "Verbindung zur \u00dcbungsumgebung verloren.",
    "Please wait": "Bitte warten",
    "Progress check result": "Ergebnis der Fortschrittspr\u00fcfung",
    "Resetting will return your lab environment to a pristine state.": "Das Zur\u00fccksetzen stellt den Urzustand der \u00dcbungsumgebung wieder her.",
    "Sorry!": "Entschuldigung!",
    "The remote server unexpectedly disconnected. You can try closing your browser window, and returning to this page in a few minutes.": "Der Server hat unerwartet die Verbindung abgebrochen. M\u00f6glicherweise l\u00e4sst sich die Verbindung durch Schlie\u00dfen und (nach einigen Minuten) Wieder\u00f6ffnen des Browserfensters wieder herstellen.",
    "There was a problem checking your progress:": "Es gab ein Problem bei der Fortschrittspr\u00fcfung:",
    "There was a problem preparing your lab environment:": "Bei der Herstellung der \u00dcbungsumgebung ist ein Problem aufgetreten:",
    "This may take several minutes to complete.": "Dies wird einige Minuten dauern.",
    "Timeout when checking progress.": "Zeit\u00fcberschreitung bei der Fortschrittspr\u00fcfung.",
    "Timeout when launching stack.": "Zeit\u00fcberschreitung beim Starten des Stacks.",
    "Unexpected result: ": "Unerwartetes Ergebnis: ",
    "We think you're busy elsewhere.": "Mit etwas anderem besch\u00e4ftigt?",
    "We're preparing your lab environment.": "\u00dcbungsumgebung wird vorbereitet.",
    "Working": "Bearbeitung",
    "You cannot undo this action.": "Dieser Vorgang l\u00e4sst sich nicht r\u00fcckg\u00e4ngig machen.",
    "You completed {passed} out of {total} tasks.": "{passed} von insgesamt {total} Aufgaben wurden korrekt erf\u00fcllt.",
    "You've been inactive here for a while, so we paused your lab environment.": "Die \u00dcbungsumgebung wurde pausiert.",
    "You've reached the time limit allocated to you for using labs.": "Die Zeitbeschr\u00e4nkung f\u00fcr die Nutzung der \u00dcbungsumgebung wurde \u00fcberschritten.",
    "Your lab environment is undergoing automatic maintenance. Please try again in a few minutes.": "Ihr \u00dcbungsumgebung befindet sich im Wartungszustand. Sie steht in ein paar Minuten wieder zur Verf\u00fcgung.",
    "Your lab environment is undergoing maintenance": "Ihre \u00dcbungsumgebung wird gerade gewartet",
    "Your lab is currently active in a separate window.": "Die \u00dcbungsumgebung l\u00e4uft derzeit in einem anderen Fenster."
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
    "DATETIME_FORMAT": "j. F Y H:i",
    "DATETIME_INPUT_FORMATS": [
      "%d.%m.%Y %H:%M:%S",
      "%d.%m.%Y %H:%M:%S.%f",
      "%d.%m.%Y %H:%M",
      "%Y-%m-%d %H:%M:%S",
      "%Y-%m-%d %H:%M:%S.%f",
      "%Y-%m-%d %H:%M",
      "%Y-%m-%d"
    ],
    "DATE_FORMAT": "j. F Y",
    "DATE_INPUT_FORMATS": [
      "%d.%m.%Y",
      "%d.%m.%y",
      "%Y-%m-%d"
    ],
    "DECIMAL_SEPARATOR": ",",
    "FIRST_DAY_OF_WEEK": 1,
    "MONTH_DAY_FORMAT": "j. F",
    "NUMBER_GROUPING": 3,
    "SHORT_DATETIME_FORMAT": "d.m.Y H:i",
    "SHORT_DATE_FORMAT": "d.m.Y",
    "THOUSAND_SEPARATOR": ".",
    "TIME_FORMAT": "H:i",
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
