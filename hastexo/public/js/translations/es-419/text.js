
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
  "After you reset, you will need to retrace your steps up to this point.": "Despu\u00e9s de reiniciar, deber\u00e1 volver sobre sus pasos hasta este punto.",
  "Are you sure?": "\u00bfEst\u00e1s seguro?",
  "Attention!": "\u00a1Atenci\u00f3n!",
  "Click 'OK' to return to your terminal in this window.": "Haga clic en 'OK' para reanudarlo en esta ventana.",
  "Could not connect to your lab environment. The client detected an unexpected error. The server's error message was:": "No se pudo conectar a su entorno de laboratorio. El cliente detect\u00f3 un error inesperado. El mensaje de error del servidor fue:",
  "Could not connect to your lab environment:": "No se pudo conectar al entorno de su laboratorio.",
  "Don't panic!  It may take a few minutes.": "\u00a1No entrar en p\u00e1nico! Puede tomar unos minutos.",
  "Hints": "Consejos",
  "In a timed exam, the timer will continue to run while your environment is being reset.": "En un examen cronometrado, el cron\u00f3metro seguir\u00e1 funcionando mientras se restablece su entorno.",
  "Lost connection to your lab environment.": "P\u00e9rdida de conexi\u00f3n con su entorno de laboratorio.",
  "Please wait": "Por favor espere",
  "Progress check result": "Resultado de la comprobaci\u00f3n de progreso",
  "Resetting will return your lab environment to a pristine state.": "El reinicio devolver\u00e1 el entorno de su laboratorio a un estado impecable.",
  "Sorry!": "\u00a1Lo siento!",
  "The remote server unexpectedly disconnected. You can try closing your browser window, and returning to this page in a few minutes.": "El servidor remoto se desconect\u00f3 inesperadamente. Puede intentar cerrar la ventana de su navegador y regresar a esta p\u00e1gina en unos minutos.",
  "There was a problem checking your progress:": "Hubo un problema al verificar tu progreso:",
  "There was a problem preparing your lab environment:": "Hubo un problema al preparar su entorno de laboratorio:",
  "This may take several minutes to complete.": "Esto puede tardar varios minutos en completarse.",
  "Timeout when checking progress.": "Tiempo de espera al comprobar el progreso.",
  "Timeout when launching stack.": "Tiempo de espera al iniciar la pila.",
  "Unexpected result: ": "Resultado inesperado: ",
  "We think you're busy elsewhere.": "Creemos que est\u00e1s ocupado en otra parte.",
  "We're preparing your lab environment.": "Estamos preparando su entorno de laboratorio",
  "Working": "Trabajando",
  "You cannot undo this action.": "No puede deshacer esta acci\u00f3n.",
  "You completed {passed} out of {total} tasks.": "Has completado {passed} de {total} tareas.",
  "You've been inactive here for a while, so we paused your lab environment.": "Ha estado inactivo aqu\u00ed durante un tiempo, por lo que detuvimos su entorno de laboratorio.",
  "You've reached the time limit allocated to you for using labs.": "Ha alcanzado el l\u00edmite de tiempo que se le ha asignado para usar los laboratorios.",
  "Your lab environment is undergoing automatic maintenance. Please try again in a few minutes.": "Su entorno de laboratorio est\u00e1 en mantenimiento autom\u00e1tico. Vuelve a intentarlo en unos minutos.",
  "Your lab environment is undergoing maintenance": "Su entorno de laboratorio est\u00e1 en mantenimiento",
  "Your lab is currently active in a separate window.": "Su laboratorio est\u00e1 actualmente activo en una ventana separada."
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
  "DATETIME_FORMAT": "j \\d\\e F \\d\\e Y \\a \\l\\a\\s H:i",
  "DATETIME_INPUT_FORMATS": [
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M:%S.%f",
    "%d/%m/%Y %H:%M",
    "%d/%m/%y %H:%M:%S",
    "%d/%m/%y %H:%M:%S.%f",
    "%d/%m/%y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d"
  ],
  "DATE_FORMAT": "j \\d\\e F \\d\\e Y",
  "DATE_INPUT_FORMATS": [
    "%d/%m/%Y",
    "%d/%m/%y",
    "%Y-%m-%d"
  ],
  "DECIMAL_SEPARATOR": ",",
  "FIRST_DAY_OF_WEEK": 1,
  "MONTH_DAY_FORMAT": "j \\d\\e F",
  "NUMBER_GROUPING": 3,
  "SHORT_DATETIME_FORMAT": "d/m/Y H:i",
  "SHORT_DATE_FORMAT": "d/m/Y",
  "THOUSAND_SEPARATOR": ".",
  "TIME_FORMAT": "H:i",
  "TIME_INPUT_FORMATS": [
    "%H:%M:%S",
    "%H:%M:%S.%f",
    "%H:%M"
  ],
  "YEAR_MONTH_FORMAT": "F \\d\\e Y"
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
